"""
Shared JNI helper for jasper_probe scripts.

Boots the JVM in-process via ctypes and provides a high-level interface
to call Java class main() methods and capture their stdout output.

The JVM is created lazily on first call to ensure_jvm() and reused for
all subsequent calls. If a JVM already exists in this process (e.g. from
a prior probe run in the same REPL session), it is attached to rather
than creating a new one.

Never calls DestroyJavaVM -- the JVM lives until the process exits.
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import sys

JNI_VERSION_1_8 = 0x00010008

IDX_GET_VERSION = 4
IDX_FIND_CLASS = 6
IDX_EXCEPTION_OCCURRED = 15
IDX_EXCEPTION_DESCRIBE = 16
IDX_EXCEPTION_CLEAR = 17
IDX_GET_STATIC_METHOD_ID = 113
IDX_CALL_STATIC_VOID_METHOD_A = 143
IDX_NEW_STRING_UTF = 167
IDX_NEW_OBJECT_ARRAY = 172
IDX_SET_OBJECT_ARRAY_ELEMENT = 174


class JavaVMOption(ctypes.Structure):
    _fields_ = [
        ("optionString", ctypes.c_char_p),
        ("extraInfo", ctypes.c_void_p),
    ]


class JavaVMInitArgs(ctypes.Structure):
    _fields_ = [
        ("version", ctypes.c_int32),
        ("nOptions", ctypes.c_int32),
        ("options", ctypes.POINTER(JavaVMOption)),
        ("ignoreUnrecognized", ctypes.c_uint8),
    ]


class JValue(ctypes.Union):
    _fields_ = [
        ("z", ctypes.c_uint8),
        ("b", ctypes.c_int8),
        ("c", ctypes.c_uint16),
        ("s", ctypes.c_int16),
        ("i", ctypes.c_int32),
        ("j", ctypes.c_int64),
        ("f", ctypes.c_float),
        ("d", ctypes.c_double),
        ("l", ctypes.c_void_p),
    ]


_libjvm = None
_jvm_ptr = None
_env_ptr = None


def get_jni_func(env_ptr, index, restype, argtypes):
    env_deref = ctypes.cast(env_ptr, ctypes.POINTER(ctypes.c_void_p))
    func_table = ctypes.cast(env_deref[0], ctypes.POINTER(ctypes.c_void_p))
    func_ptr = func_table[index]
    if not func_ptr:
        return None
    prototype = ctypes.CFUNCTYPE(restype, *argtypes)
    return prototype(func_ptr)


def check_jni_exception(env_ptr):
    exc_check = get_jni_func(env_ptr, IDX_EXCEPTION_OCCURRED,
                             ctypes.c_void_p, [ctypes.c_void_p])
    if exc_check is None:
        return False
    exc = exc_check(env_ptr)
    if exc:
        exc_describe = get_jni_func(env_ptr, IDX_EXCEPTION_DESCRIBE,
                                    None, [ctypes.c_void_p])
        if exc_describe:
            exc_describe(env_ptr)
        exc_clear = get_jni_func(env_ptr, IDX_EXCEPTION_CLEAR,
                                 None, [ctypes.c_void_p])
        if exc_clear:
            exc_clear(env_ptr)
        return True
    return False


def _find_libjvm_candidates(probe_root):
    candidates = []
    discovered_path = os.path.join(probe_root, "_discovered.json")
    if os.path.exists(discovered_path):
        try:
            with open(discovered_path) as f:
                discovered = json.load(f)
            for p in discovered.get("libjvm_paths", []):
                if p not in candidates:
                    candidates.append(p)
            libjvm = discovered.get("libjvm_path")
            if libjvm and libjvm not in candidates:
                candidates.insert(0, libjvm)
        except Exception:
            pass

    search_patterns = [
        "/usr/lib/jvm/jdk-14.0.1/lib/server/libjvm.so",
        "/usr/lib/jvm/java-8-openjdk-amd64/jre/lib/amd64/server/libjvm.so",
        "/usr/lib/jvm/java-1.8.0-openjdk-amd64/jre/lib/amd64/server/libjvm.so",
        "/usr/lib/jvm/*/lib/server/libjvm.so",
        "/usr/lib/jvm/*/lib/amd64/server/libjvm.so",
        "/usr/lib/jvm/*/jre/lib/amd64/server/libjvm.so",
        "/usr/lib/jvm/*/jre/lib/server/libjvm.so",
    ]
    for pattern in search_patterns:
        for path in glob.glob(pattern):
            if path not in candidates:
                candidates.append(path)
    return candidates


def _load_libjvm(probe_root):
    global _libjvm
    if _libjvm is not None:
        return _libjvm

    candidates = _find_libjvm_candidates(probe_root)
    if not candidates:
        raise RuntimeError("No libjvm.so found on this system")

    for candidate in candidates:
        if not os.path.exists(candidate) or not os.access(candidate, os.R_OK):
            continue
        try:
            jvm_lib_dir = os.path.dirname(candidate)
            jvm_base = candidate
            for _ in range(4):
                jvm_base = os.path.dirname(jvm_base)
            jvm_lib_dirs = [jvm_lib_dir]
            for sub in ["lib", "lib/server", "lib/jli", "jre/lib/amd64",
                         "jre/lib/amd64/server", "jre/lib/amd64/jli"]:
                d = os.path.join(jvm_base, sub)
                if os.path.isdir(d):
                    jvm_lib_dirs.append(d)

            old_ld = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = ":".join(jvm_lib_dirs) + ":" + old_ld

            _libjvm = ctypes.CDLL(candidate)
            return _libjvm
        except OSError:
            continue

    raise RuntimeError(
        f"Could not load any libjvm.so (tried {len(candidates)} candidates)"
    )


def _build_classpath(probe_root):
    tools_dir = os.path.join(probe_root, "tools")
    lib_dir = os.path.join(probe_root, "lib")
    parts = [tools_dir]
    if os.path.isdir(lib_dir):
        for jar in sorted(os.listdir(lib_dir)):
            if jar.endswith(".jar"):
                parts.append(os.path.join(lib_dir, jar))
    return os.pathsep.join(parts)


def _try_attach_existing(libjvm):
    get_created = libjvm.JNI_GetCreatedJavaVMs
    get_created.restype = ctypes.c_int32
    get_created.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
    ]
    jvm_buf = ctypes.c_void_p()
    n_vms = ctypes.c_int32(0)
    rc = get_created(ctypes.byref(jvm_buf), 1, ctypes.byref(n_vms))
    if rc != 0 or n_vms.value == 0:
        return None, None

    jvm_ptr = jvm_buf
    jvm_deref = ctypes.cast(jvm_ptr, ctypes.POINTER(ctypes.c_void_p))
    jvm_func_table = ctypes.cast(jvm_deref[0], ctypes.POINTER(ctypes.c_void_p))

    AttachCurrentThread = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    )(jvm_func_table[4])

    env_ptr = ctypes.c_void_p()
    rc = AttachCurrentThread(jvm_ptr, ctypes.byref(env_ptr), None)
    if rc != 0 or not env_ptr.value:
        return None, None

    return jvm_ptr, env_ptr


def ensure_jvm(probe_root):
    global _jvm_ptr, _env_ptr

    if _jvm_ptr is not None and _env_ptr is not None:
        return _jvm_ptr, _env_ptr

    libjvm = _load_libjvm(probe_root)

    jvm_ptr, env_ptr = _try_attach_existing(libjvm)
    if jvm_ptr is not None:
        _jvm_ptr = jvm_ptr
        _env_ptr = env_ptr
        return _jvm_ptr, _env_ptr

    classpath = _build_classpath(probe_root)
    cp_option = f"-Djava.class.path={classpath}".encode("utf-8")

    option_strings = [cp_option, b"-Xmx256m", b"-Xms64m"]
    OptionArray = JavaVMOption * len(option_strings)
    options = OptionArray()
    for i, opt_str in enumerate(option_strings):
        options[i].optionString = opt_str
        options[i].extraInfo = None

    init_args = JavaVMInitArgs()
    init_args.version = JNI_VERSION_1_8
    init_args.nOptions = len(option_strings)
    init_args.options = options
    init_args.ignoreUnrecognized = 1

    jvm_ptr = ctypes.c_void_p()
    env_ptr = ctypes.c_void_p()

    create_jvm = libjvm.JNI_CreateJavaVM
    create_jvm.restype = ctypes.c_int32
    create_jvm.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]

    rc = create_jvm(
        ctypes.byref(jvm_ptr),
        ctypes.byref(env_ptr),
        ctypes.byref(init_args),
    )
    if rc != 0:
        raise RuntimeError(f"JNI_CreateJavaVM failed with code {rc}")
    if not env_ptr.value:
        raise RuntimeError("JNI_CreateJavaVM returned 0 but JNIEnv* is null")

    _jvm_ptr = jvm_ptr
    _env_ptr = env_ptr
    return _jvm_ptr, _env_ptr


def _make_string_array(env_ptr, strings):
    FindClass = get_jni_func(env_ptr, IDX_FIND_CLASS,
                             ctypes.c_void_p,
                             [ctypes.c_void_p, ctypes.c_char_p])
    NewStringUTF = get_jni_func(env_ptr, IDX_NEW_STRING_UTF,
                                ctypes.c_void_p,
                                [ctypes.c_void_p, ctypes.c_char_p])
    NewObjectArray = get_jni_func(env_ptr, IDX_NEW_OBJECT_ARRAY,
                                  ctypes.c_void_p,
                                  [ctypes.c_void_p, ctypes.c_int32,
                                   ctypes.c_void_p, ctypes.c_void_p])
    SetObjectArrayElement = get_jni_func(env_ptr, IDX_SET_OBJECT_ARRAY_ELEMENT,
                                         None,
                                         [ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_int32, ctypes.c_void_p])

    string_class = FindClass(env_ptr, b"java/lang/String")
    if check_jni_exception(env_ptr) or not string_class:
        raise RuntimeError("Could not find java/lang/String class")

    arr = NewObjectArray(env_ptr, len(strings), string_class, None)
    if check_jni_exception(env_ptr) or not arr:
        raise RuntimeError("Could not create String array")

    for i, s in enumerate(strings):
        jstr = NewStringUTF(env_ptr, s.encode("utf-8"))
        if check_jni_exception(env_ptr) or not jstr:
            raise RuntimeError(f"Could not create Java string for: {s}")
        SetObjectArrayElement(env_ptr, arr, i, jstr)
        if check_jni_exception(env_ptr):
            raise RuntimeError(f"Could not set array element {i}")

    return arr


def call_java_main(env_ptr, class_name, args):
    FindClass = get_jni_func(env_ptr, IDX_FIND_CLASS,
                             ctypes.c_void_p,
                             [ctypes.c_void_p, ctypes.c_char_p])
    GetStaticMethodID = get_jni_func(env_ptr, IDX_GET_STATIC_METHOD_ID,
                                     ctypes.c_void_p,
                                     [ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_char_p, ctypes.c_char_p])
    CallStaticVoidMethodA = get_jni_func(env_ptr, IDX_CALL_STATIC_VOID_METHOD_A,
                                         None,
                                         [ctypes.c_void_p, ctypes.c_void_p,
                                          ctypes.c_void_p, ctypes.c_void_p])

    cls = FindClass(env_ptr, class_name.encode("utf-8"))
    if check_jni_exception(env_ptr) or not cls:
        raise RuntimeError(f"FindClass({class_name}) failed")

    main_method = GetStaticMethodID(
        env_ptr, cls, b"main", b"([Ljava/lang/String;)V"
    )
    if check_jni_exception(env_ptr) or not main_method:
        raise RuntimeError(f"GetStaticMethodID(main) failed for {class_name}")

    str_array = _make_string_array(env_ptr, args)

    old_stdout_fd = os.dup(1)
    pipe_r, pipe_w = os.pipe()
    os.dup2(pipe_w, 1)
    os.close(pipe_w)

    java_exception = False
    try:
        jargs = (JValue * 1)()
        jargs[0].l = str_array
        CallStaticVoidMethodA(
            env_ptr, cls, main_method,
            ctypes.cast(jargs, ctypes.c_void_p)
        )
        sys.stdout.flush()
        java_exception = check_jni_exception(env_ptr)
    finally:
        os.dup2(old_stdout_fd, 1)
        os.close(old_stdout_fd)

    captured = b""
    while True:
        chunk = os.read(pipe_r, 4096)
        if not chunk:
            break
        captured += chunk
    os.close(pipe_r)

    output = captured.decode("utf-8", errors="replace").strip()

    if java_exception:
        raise RuntimeError(
            f"{class_name}.main() threw a Java exception. "
            f"Captured output: {output}"
        )

    return output
