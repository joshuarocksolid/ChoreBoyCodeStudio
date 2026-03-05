from __future__ import annotations

import ctypes
import glob
import json
import logging
import os
import re
import threading
from typing import List, Optional, Tuple

from .errors import JVMError

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

logger = logging.getLogger(__name__)


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
_libjvm_path: Optional[str] = None
_jvm_ptr = None
_env_ptr = None
_classpath_entries: List[str] = []
_boot_lib_root: Optional[str] = None
_jvm_lock = threading.Lock()
_stdout_capture_lock = threading.Lock()


def _get_jni_func(env_ptr, index: int, restype, argtypes):
    env_deref = ctypes.cast(env_ptr, ctypes.POINTER(ctypes.c_void_p))
    func_table = ctypes.cast(env_deref[0], ctypes.POINTER(ctypes.c_void_p))
    func_ptr = func_table[index]
    if not func_ptr:
        return None
    prototype = ctypes.CFUNCTYPE(restype, *argtypes)
    return prototype(func_ptr)


def _check_jni_exception(env_ptr) -> bool:
    exc_check = _get_jni_func(
        env_ptr, IDX_EXCEPTION_OCCURRED, ctypes.c_void_p, [ctypes.c_void_p]
    )
    if exc_check is None:
        return False
    exc = exc_check(env_ptr)
    if exc:
        exc_describe = _get_jni_func(env_ptr, IDX_EXCEPTION_DESCRIBE, None, [ctypes.c_void_p])
        if exc_describe:
            exc_describe(env_ptr)
        exc_clear = _get_jni_func(env_ptr, IDX_EXCEPTION_CLEAR, None, [ctypes.c_void_p])
        if exc_clear:
            exc_clear(env_ptr)
        return True
    return False


def _read_discovered_candidates(discovered_path: str) -> List[str]:
    candidates: List[str] = []
    if not os.path.exists(discovered_path):
        return candidates
    try:
        with open(discovered_path, "r", encoding="utf-8") as handle:
            discovered = json.load(handle)
    except Exception:
        return candidates

    libjvm_path = discovered.get("libjvm_path")
    if libjvm_path:
        candidates.append(libjvm_path)
    for path in discovered.get("libjvm_paths", []):
        if path not in candidates:
            candidates.append(path)
    return candidates


def _find_libjvm_candidates(lib_root: str) -> List[str]:
    candidates: List[str] = []
    discovered_candidates = _read_discovered_candidates(os.path.join(lib_root, "_discovered.json"))
    for path in discovered_candidates:
        if path not in candidates:
            candidates.append(path)

    sibling_probe_discovered = os.path.join(
        os.path.dirname(lib_root), "jasper_probe", "_discovered.json"
    )
    for path in _read_discovered_candidates(sibling_probe_discovered):
        if path not in candidates:
            candidates.append(path)

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


def _prepare_ld_library_path(libjvm_path: str) -> List[str]:
    jvm_lib_dir = os.path.dirname(libjvm_path)
    jvm_base = libjvm_path
    for _ in range(4):
        jvm_base = os.path.dirname(jvm_base)

    additions = [jvm_lib_dir]
    for subpath in [
        "lib",
        "lib/server",
        "lib/jli",
        "jre/lib/amd64",
        "jre/lib/amd64/server",
        "jre/lib/amd64/jli",
    ]:
        candidate = os.path.join(jvm_base, subpath)
        if os.path.isdir(candidate):
            additions.append(candidate)

    existing = os.environ.get("LD_LIBRARY_PATH", "")
    existing_parts = [part for part in existing.split(os.pathsep) if part]
    merged: List[str] = []
    for part in additions + existing_parts:
        if part not in merged:
            merged.append(part)
    os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(merged)
    return merged


def _load_libjvm(lib_root: str):
    global _libjvm
    global _libjvm_path
    if _libjvm is not None:
        return _libjvm

    candidates = _find_libjvm_candidates(lib_root)
    if not candidates:
        raise JVMError("No libjvm.so candidates found on this system")

    load_errors: List[str] = []
    for candidate in candidates:
        if not os.path.exists(candidate):
            continue
        if not os.access(candidate, os.R_OK):
            continue

        try:
            _prepare_ld_library_path(candidate)
            _libjvm = ctypes.CDLL(candidate)
            _libjvm_path = candidate
            logger.info("Loaded libjvm from %s", candidate)
            return _libjvm
        except OSError as exc:
            load_errors.append("{}: {}".format(candidate, exc))

    if load_errors:
        raise JVMError("Could not load libjvm.so. Last errors: {}".format(" | ".join(load_errors)))
    raise JVMError("Could not load libjvm.so from discovered candidates")


def _build_classpath(lib_root: str) -> List[str]:
    java_dir = os.path.join(lib_root, "java")
    lib_dir = os.path.join(lib_root, "lib")
    entries = [java_dir]
    if os.path.isdir(lib_dir):
        for jar_name in sorted(os.listdir(lib_dir)):
            if jar_name.endswith(".jar"):
                entries.append(os.path.join(lib_dir, jar_name))
    return entries


def _try_attach_existing(libjvm):
    get_created = libjvm.JNI_GetCreatedJavaVMs
    get_created.restype = ctypes.c_int32
    get_created.argtypes = [
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_int32,
        ctypes.POINTER(ctypes.c_int32),
    ]

    jvm_buffer = ctypes.c_void_p()
    n_vms = ctypes.c_int32(0)
    rc = get_created(ctypes.byref(jvm_buffer), 1, ctypes.byref(n_vms))
    if rc != 0 or n_vms.value == 0:
        return None, None

    jvm_ptr = jvm_buffer
    jvm_deref = ctypes.cast(jvm_ptr, ctypes.POINTER(ctypes.c_void_p))
    jvm_func_table = ctypes.cast(jvm_deref[0], ctypes.POINTER(ctypes.c_void_p))

    attach_current_thread = ctypes.CFUNCTYPE(
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    )(jvm_func_table[4])

    env_ptr = ctypes.c_void_p()
    rc = attach_current_thread(jvm_ptr, ctypes.byref(env_ptr), None)
    if rc != 0 or not env_ptr.value:
        return None, None
    return jvm_ptr, env_ptr


def ensure_jvm(lib_root: Optional[str] = None) -> Tuple[ctypes.c_void_p, ctypes.c_void_p]:
    global _jvm_ptr
    global _env_ptr
    global _classpath_entries
    global _boot_lib_root

    if _jvm_ptr is not None and _env_ptr is not None:
        return _jvm_ptr, _env_ptr

    with _jvm_lock:
        if _jvm_ptr is not None and _env_ptr is not None:
            return _jvm_ptr, _env_ptr

        resolved_lib_root = lib_root or os.path.dirname(os.path.abspath(__file__))
        _boot_lib_root = resolved_lib_root
        _classpath_entries = _build_classpath(resolved_lib_root)

        libjvm = _load_libjvm(resolved_lib_root)

        jvm_ptr, env_ptr = _try_attach_existing(libjvm)
        if jvm_ptr is not None and env_ptr is not None:
            _jvm_ptr = jvm_ptr
            _env_ptr = env_ptr
            logger.info("Attached to existing JVM")
            return _jvm_ptr, _env_ptr

        classpath_value = os.pathsep.join(_classpath_entries)
        option_strings = [
            "-Djava.class.path={}".format(classpath_value).encode("utf-8"),
            b"-Xmx256m",
            b"-Xms64m",
        ]
        option_array_type = JavaVMOption * len(option_strings)
        options = option_array_type()
        for index, option_string in enumerate(option_strings):
            options[index].optionString = option_string
            options[index].extraInfo = None

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
            raise JVMError("JNI_CreateJavaVM failed with code {}".format(rc))
        if not env_ptr.value:
            raise JVMError("JNI_CreateJavaVM returned null JNIEnv pointer")

        _jvm_ptr = jvm_ptr
        _env_ptr = env_ptr
        logger.info("Started new JVM with %d classpath entries", len(_classpath_entries))
        return _jvm_ptr, _env_ptr


def _make_string_array(env_ptr, strings: List[str]):
    find_class = _get_jni_func(
        env_ptr, IDX_FIND_CLASS, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p]
    )
    new_string_utf = _get_jni_func(
        env_ptr, IDX_NEW_STRING_UTF, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p]
    )
    new_object_array = _get_jni_func(
        env_ptr,
        IDX_NEW_OBJECT_ARRAY,
        ctypes.c_void_p,
        [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p],
    )
    set_object_array_element = _get_jni_func(
        env_ptr,
        IDX_SET_OBJECT_ARRAY_ELEMENT,
        None,
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p],
    )

    if not find_class or not new_string_utf or not new_object_array or not set_object_array_element:
        raise JVMError("Required JNI functions for String[] marshaling are unavailable")

    string_class = find_class(env_ptr, b"java/lang/String")
    if _check_jni_exception(env_ptr) or not string_class:
        raise JVMError("Could not resolve java/lang/String")

    array_handle = new_object_array(env_ptr, len(strings), string_class, None)
    if _check_jni_exception(env_ptr) or not array_handle:
        raise JVMError("Could not allocate Java String[]")

    for index, value in enumerate(strings):
        java_str = new_string_utf(env_ptr, value.encode("utf-8"))
        if _check_jni_exception(env_ptr) or not java_str:
            raise JVMError("Could not create Java string for argument index {}".format(index))
        set_object_array_element(env_ptr, array_handle, index, java_str)
        if _check_jni_exception(env_ptr):
            raise JVMError("Could not set Java String[] element {}".format(index))

    return array_handle


def call_java_main(env_ptr, class_name: str, args: List[str]) -> str:
    _, default_env = ensure_jvm()
    target_env = env_ptr if env_ptr is not None else default_env

    find_class = _get_jni_func(
        target_env, IDX_FIND_CLASS, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p]
    )
    get_static_method_id = _get_jni_func(
        target_env,
        IDX_GET_STATIC_METHOD_ID,
        ctypes.c_void_p,
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p],
    )
    call_static_void_method_a = _get_jni_func(
        target_env,
        IDX_CALL_STATIC_VOID_METHOD_A,
        None,
        [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
    )

    if not find_class or not get_static_method_id or not call_static_void_method_a:
        raise JVMError("Required JNI functions for class invocation are unavailable")

    java_class = find_class(target_env, class_name.encode("utf-8"))
    if _check_jni_exception(target_env) or not java_class:
        raise JVMError("FindClass failed for {}".format(class_name))

    main_method = get_static_method_id(
        target_env, java_class, b"main", b"([Ljava/lang/String;)V"
    )
    if _check_jni_exception(target_env) or not main_method:
        raise JVMError("main(String[]) not found for {}".format(class_name))

    safe_args = [str(item) for item in (args or [])]
    arg_array = _make_string_array(target_env, safe_args)

    with _stdout_capture_lock:
        old_stdout_fd = os.dup(1)
        pipe_read, pipe_write = os.pipe()
        os.dup2(pipe_write, 1)
        os.close(pipe_write)

        raised_java_exception = False
        try:
            call_args = (JValue * 1)()
            call_args[0].l = arg_array
            call_static_void_method_a(
                target_env,
                java_class,
                main_method,
                ctypes.cast(call_args, ctypes.c_void_p),
            )
            raised_java_exception = _check_jni_exception(target_env)
        finally:
            os.dup2(old_stdout_fd, 1)
            os.close(old_stdout_fd)

        captured = b""
        while True:
            chunk = os.read(pipe_read, 4096)
            if not chunk:
                break
            captured += chunk
        os.close(pipe_read)

    output = captured.decode("utf-8", errors="replace").strip()
    logger.debug("Java main call class=%s args=%d bytes=%d", class_name, len(safe_args), len(captured))

    if raised_java_exception:
        raise JVMError(
            "{}.main raised a Java exception. Captured stdout: {}".format(
                class_name, output
            )
        )
    return output


def status() -> str:
    if _jvm_ptr is not None and _env_ptr is not None:
        return "running"
    return "not_started"


def _parse_version_from_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    match = re.search(r"/jdk-([0-9]+(?:\.[0-9]+){1,3})/", path)
    if match:
        return match.group(1)
    match = re.search(r"/java-([0-9]+(?:\.[0-9]+){0,3})", path)
    if match:
        return match.group(1)
    return None


def java_version() -> str:
    by_path = _parse_version_from_path(_libjvm_path)
    if by_path:
        return by_path

    if _env_ptr is None:
        return "unknown"

    get_version = _get_jni_func(_env_ptr, IDX_GET_VERSION, ctypes.c_int32, [ctypes.c_void_p])
    if not get_version:
        return "unknown"
    jni_version = int(get_version(_env_ptr))
    major = (jni_version >> 16) & 0xFFFF
    minor = jni_version & 0xFFFF
    return "jni-{}.{}".format(major, minor)


def classpath() -> List[str]:
    if _classpath_entries:
        return list(_classpath_entries)
    lib_root = _boot_lib_root or os.path.dirname(os.path.abspath(__file__))
    return _build_classpath(lib_root)

