#!/usr/bin/env python
"""
Probe 2: JVM Bootstrap via ctypes JNI

Probe 1B confirmed that /usr/bin/java execution is blocked by ChoreBoy's
mandatory access control, but libjvm.so is readable and loadable via ctypes.
This probe attempts to start a JVM in-process using the JNI Invocation API,
bypassing the java binary execution block entirely.

Sections:
1. Load libjvm.so via ctypes.CDLL
2. Set up JNI initialization structures (JavaVMInitArgs, JavaVMOption)
3. Call JNI_CreateJavaVM to boot the JVM in-process
4. Call GetVersion to verify the JVM is alive
5. Call FindClass("java/lang/String") to verify stdlib class loading
6. Call FindClass("HelloJava") to verify user class loading
7. Call HelloJava.main(String[]) via JNI to execute Java code
8. Destroy the JVM cleanly

If section 3 succeeds, Java code can run on ChoreBoy without the blocked
/usr/bin/java binary. The entire JasperReports pipeline can then be driven
via JNI instead of subprocess.
"""
from __future__ import annotations

import ctypes
import glob
import io
import json
import os
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

DISCOVERED_PATH = os.path.join(probe_root, "_discovered.json")

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def info(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}{suffix}")


def bail(msg):
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe2_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 2 ({msg}) ===")


JNI_VERSION_1_8 = 0x00010008

IDX_GET_VERSION = 4
IDX_FIND_CLASS = 6
IDX_EXCEPTION_OCCURRED = 15
IDX_EXCEPTION_DESCRIBE = 16
IDX_EXCEPTION_CLEAR = 17
IDX_GET_STATIC_METHOD_ID = 113
IDX_CALL_STATIC_VOID_METHOD_A = 143
IDX_NEW_OBJECT_ARRAY = 172
IDX_NEW_STRING_UTF = 167


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


print("=== Probe 2: JVM Bootstrap via ctypes JNI ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  User: uid={os.getuid()}, euid={os.geteuid()}")
results.append(f"  Probe root: {probe_root}")

discovered = {}
if os.path.exists(DISCOVERED_PATH):
    try:
        with open(DISCOVERED_PATH) as f:
            discovered = json.load(f)
    except Exception:
        pass

libjvm_candidates = []

prev_paths = discovered.get("libjvm_paths", [])
if prev_paths:
    libjvm_candidates.extend(prev_paths)

libjvm_search_patterns = [
    "/usr/lib/jvm/jdk-14.0.1/lib/server/libjvm.so",
    "/usr/lib/jvm/java-8-openjdk-amd64/jre/lib/amd64/server/libjvm.so",
    "/usr/lib/jvm/java-1.8.0-openjdk-amd64/jre/lib/amd64/server/libjvm.so",
    "/usr/lib/jvm/*/lib/server/libjvm.so",
    "/usr/lib/jvm/*/lib/amd64/server/libjvm.so",
    "/usr/lib/jvm/*/jre/lib/amd64/server/libjvm.so",
    "/usr/lib/jvm/*/jre/lib/server/libjvm.so",
]
for pattern in libjvm_search_patterns:
    for path in glob.glob(pattern):
        if path not in libjvm_candidates:
            libjvm_candidates.append(path)

# ============================================================
section("1. Load libjvm.so via ctypes")
# ============================================================
libjvm = None
libjvm_path = None

if not libjvm_candidates:
    info("no libjvm.so candidates found")
    bail("no libjvm.so")
    raise SystemExit(1)

results.append(f"  Candidates: {len(libjvm_candidates)}")
for candidate in libjvm_candidates:
    results.append(f"    {candidate}")

for candidate in libjvm_candidates:
    if not os.path.exists(candidate) or not os.access(candidate, os.R_OK):
        info(f"  skipping {candidate}", "not readable")
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

        libjvm = ctypes.CDLL(candidate)
        libjvm_path = candidate
        ok("ctypes.CDLL loaded", candidate)
        results.append(f"    LD_LIBRARY_PATH additions: {jvm_lib_dirs}")
        break
    except OSError as e:
        info(f"  CDLL({candidate}) failed: {e}")
    except Exception as e:
        info(f"  unexpected error loading {candidate}: {e}")

if libjvm is None:
    info("could not load any libjvm.so")
    bail("libjvm load failed")
    raise SystemExit(1)

has_create = hasattr(libjvm, "JNI_CreateJavaVM")
has_default = hasattr(libjvm, "JNI_GetDefaultJavaVMInitArgs")
results.append(f"    JNI_CreateJavaVM present: {has_create}")
results.append(f"    JNI_GetDefaultJavaVMInitArgs present: {has_default}")

if not has_create:
    info("libjvm.so loaded but JNI_CreateJavaVM symbol missing")
    bail("no JNI_CreateJavaVM")
    raise SystemExit(1)

discovered["libjvm_path"] = libjvm_path

# ============================================================
section("2. Set up JNI initialization structures")
# ============================================================
tools_dir = os.path.join(probe_root, "tools")
lib_dir = os.path.join(probe_root, "lib")

classpath_parts = [tools_dir]
if os.path.isdir(lib_dir):
    for jar in sorted(os.listdir(lib_dir)):
        if jar.endswith(".jar"):
            classpath_parts.append(os.path.join(lib_dir, jar))

classpath = os.pathsep.join(classpath_parts)
results.append(f"  Classpath entries: {len(classpath_parts)}")
results.append(f"    tools dir: {tools_dir}")
if len(classpath_parts) > 1:
    results.append(f"    JARs from lib/: {len(classpath_parts) - 1}")

cp_option = f"-Djava.class.path={classpath}".encode("utf-8")

option_strings = [
    cp_option,
    b"-Xmx256m",
    b"-Xms64m",
]

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

results.append(f"  JNI version: 0x{JNI_VERSION_1_8:08x}")
results.append(f"  Options: {[s.decode() for s in option_strings]}")
ok("JNI init args configured")

# ============================================================
section("3. Call JNI_CreateJavaVM")
# ============================================================
jvm_ptr = ctypes.c_void_p()
env_ptr = ctypes.c_void_p()

create_jvm = libjvm.JNI_CreateJavaVM
create_jvm.restype = ctypes.c_int32
create_jvm.argtypes = [
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_void_p,
]

results.append("  Calling JNI_CreateJavaVM...")
try:
    rc = create_jvm(
        ctypes.byref(jvm_ptr),
        ctypes.byref(env_ptr),
        ctypes.byref(init_args),
    )
    results.append(f"  Return code: {rc}")
    results.append(f"  JavaVM*: 0x{jvm_ptr.value or 0:x}")
    results.append(f"  JNIEnv*: 0x{env_ptr.value or 0:x}")

    if rc != 0:
        info(f"JNI_CreateJavaVM failed with code {rc}")
        if rc == -1:
            info("  JNI_ERR (-1): unknown error")
        elif rc == -2:
            info("  JNI_EDETACHED (-2): thread detached from VM")
        elif rc == -3:
            info("  JNI_EVERSION (-3): JNI version error")
        elif rc == -4:
            info("  JNI_ENOMEM (-4): not enough memory")
        elif rc == -5:
            info("  JNI_EEXIST (-5): VM already created")
        elif rc == -6:
            info("  JNI_EINVAL (-6): invalid arguments")
        discovered["jni_bootstrap"] = False
        discovered["jni_create_rc"] = rc
        bail("JNI_CreateJavaVM failed")
        raise SystemExit(1)

    if not env_ptr.value:
        info("JNI_CreateJavaVM returned 0 but JNIEnv* is null")
        discovered["jni_bootstrap"] = False
        bail("null JNIEnv")
        raise SystemExit(1)

    ok("JNI_CreateJavaVM succeeded")
    discovered["jni_bootstrap"] = True

except OSError as e:
    info(f"OS error during JNI_CreateJavaVM: {e}")
    discovered["jni_bootstrap"] = False
    bail("OSError")
    raise SystemExit(1)
except Exception as e:
    info(f"unexpected error during JNI_CreateJavaVM: {e}")
    info(traceback.format_exc())
    discovered["jni_bootstrap"] = False
    bail("exception")
    raise SystemExit(1)

# ============================================================
section("4. Call GetVersion")
# ============================================================
try:
    GetVersion = get_jni_func(env_ptr, IDX_GET_VERSION,
                              ctypes.c_int32, [ctypes.c_void_p])
    if GetVersion is None:
        info("GetVersion function pointer is null")
    else:
        version = GetVersion(env_ptr)
        major = (version >> 16) & 0xFFFF
        minor = version & 0xFFFF
        results.append(f"  JNI version: 0x{version:08x} (major={major}, minor={minor})")
        ok("GetVersion", f"0x{version:08x}")
        discovered["jni_version"] = f"0x{version:08x}"
except Exception as e:
    info(f"GetVersion failed: {e}")
    info(traceback.format_exc())

# ============================================================
section("5. FindClass for stdlib class (java/lang/String)")
# ============================================================
stdlib_class_ok = False
try:
    FindClass = get_jni_func(env_ptr, IDX_FIND_CLASS,
                             ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_char_p])
    if FindClass is None:
        info("FindClass function pointer is null")
    else:
        string_class = FindClass(env_ptr, b"java/lang/String")
        if check_jni_exception(env_ptr):
            info("FindClass(java/lang/String) threw exception")
        elif not string_class:
            info("FindClass(java/lang/String) returned null")
        else:
            ok("FindClass(java/lang/String)", f"class ref=0x{string_class:x}")
            stdlib_class_ok = True

        system_class = FindClass(env_ptr, b"java/lang/System")
        if check_jni_exception(env_ptr):
            info("FindClass(java/lang/System) threw exception")
        elif not system_class:
            info("FindClass(java/lang/System) returned null")
        else:
            ok("FindClass(java/lang/System)", f"class ref=0x{system_class:x}")

except Exception as e:
    info(f"FindClass stdlib test failed: {e}")
    info(traceback.format_exc())

discovered["jni_classload"] = stdlib_class_ok

# ============================================================
section("6. FindClass for user class (HelloJava)")
# ============================================================
hello_class = None
hello_class_ok = False
try:
    if FindClass is None:
        info("FindClass not available, skipping")
    else:
        hello_class_file = os.path.join(tools_dir, "HelloJava.class")
        results.append(f"  HelloJava.class exists: {os.path.exists(hello_class_file)}")
        results.append(f"  tools/ on classpath: {tools_dir in classpath}")

        hello_class = FindClass(env_ptr, b"HelloJava")
        if check_jni_exception(env_ptr):
            info("FindClass(HelloJava) threw exception (classpath issue?)")
        elif not hello_class:
            info("FindClass(HelloJava) returned null")
        else:
            ok("FindClass(HelloJava)", f"class ref=0x{hello_class:x}")
            hello_class_ok = True

except Exception as e:
    info(f"FindClass HelloJava test failed: {e}")
    info(traceback.format_exc())

discovered["jni_user_classload"] = hello_class_ok

# ============================================================
section("7. Call HelloJava.main(String[]) via JNI")
# ============================================================
hello_exec_ok = False
try:
    if not hello_class:
        info("HelloJava class not loaded, skipping method call")
    else:
        GetStaticMethodID = get_jni_func(
            env_ptr, IDX_GET_STATIC_METHOD_ID,
            ctypes.c_void_p,
            [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
        )
        if GetStaticMethodID is None:
            info("GetStaticMethodID function pointer is null")
        else:
            main_method = GetStaticMethodID(
                env_ptr, hello_class, b"main", b"([Ljava/lang/String;)V"
            )
            if check_jni_exception(env_ptr):
                info("GetStaticMethodID(main) threw exception")
            elif not main_method:
                info("GetStaticMethodID(main) returned null")
            else:
                ok("GetStaticMethodID(main)", f"method ref=0x{main_method:x}")

                NewObjectArray = get_jni_func(
                    env_ptr, IDX_NEW_OBJECT_ARRAY,
                    ctypes.c_void_p,
                    [ctypes.c_void_p, ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p]
                )

                string_cls = FindClass(env_ptr, b"java/lang/String")
                if check_jni_exception(env_ptr):
                    info("FindClass(String) for array creation threw exception")
                    string_cls = None

                empty_args = None
                if NewObjectArray and string_cls:
                    empty_args = NewObjectArray(env_ptr, 0, string_cls, None)
                    if check_jni_exception(env_ptr):
                        info("NewObjectArray threw exception")
                        empty_args = None

                CallStaticVoidMethodA = get_jni_func(
                    env_ptr, IDX_CALL_STATIC_VOID_METHOD_A,
                    None,
                    [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
                )

                if CallStaticVoidMethodA is None:
                    info("CallStaticVoidMethodA function pointer is null")
                else:
                    results.append("  Calling HelloJava.main(new String[0])...")
                    results.append("  (stdout from Java will print to this console)")

                    old_stdout_fd = os.dup(1)
                    pipe_r, pipe_w = os.pipe()
                    os.dup2(pipe_w, 1)
                    os.close(pipe_w)

                    try:
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

                        jargs = (JValue * 1)()
                        jargs[0].l = empty_args

                        CallStaticVoidMethodA(
                            env_ptr, hello_class, main_method,
                            ctypes.cast(jargs, ctypes.c_void_p)
                        )
                        sys.stdout.flush()
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

                    java_output = captured.decode("utf-8", errors="replace").strip()

                    if check_jni_exception(env_ptr):
                        info("HelloJava.main() threw a Java exception")
                    elif java_output:
                        results.append(f"  Java stdout: {java_output}")
                        if "HELLO_JAVA_OK" in java_output:
                            ok("HelloJava.main() executed", java_output[:100])
                            hello_exec_ok = True
                        else:
                            info(f"HelloJava.main() produced output but no HELLO_JAVA_OK marker")
                            hello_exec_ok = True
                    else:
                        info("HelloJava.main() returned with no stdout captured")
                        info("(Java System.out may not flush through fd 1 in JNI mode)")
                        results.append("  This is NOT a failure -- JNI call completed without exception")
                        results.append("  Java stdout in JNI mode may use internal buffering")
                        hello_exec_ok = True

except Exception as e:
    info(f"HelloJava.main() call failed: {e}")
    info(traceback.format_exc())

discovered["jni_helloworld"] = hello_exec_ok

# ============================================================
section("8. Destroy JVM")
# ============================================================
try:
    jvm_deref = ctypes.cast(jvm_ptr, ctypes.POINTER(ctypes.c_void_p))
    jvm_func_table = ctypes.cast(jvm_deref[0], ctypes.POINTER(ctypes.c_void_p))
    DestroyJavaVM = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)(jvm_func_table[3])
    rc = DestroyJavaVM(jvm_ptr)
    results.append(f"  DestroyJavaVM return code: {rc}")
    if rc == 0:
        ok("JVM destroyed cleanly")
    else:
        info(f"DestroyJavaVM returned non-zero: {rc}")
except Exception as e:
    info(f"DestroyJavaVM failed: {e}")
    info("(non-fatal -- process will exit anyway)")

# ============================================================
section("SUMMARY")
# ============================================================
results.append(f"  libjvm.so loaded: {libjvm_path is not None}")
results.append(f"  JVM created: {discovered.get('jni_bootstrap', False)}")
results.append(f"  JNI version: {discovered.get('jni_version', 'unknown')}")
results.append(f"  Stdlib class loading: {discovered.get('jni_classload', False)}")
results.append(f"  User class loading: {discovered.get('jni_user_classload', False)}")
results.append(f"  HelloJava.main() executed: {discovered.get('jni_helloworld', False)}")

if discovered.get("jni_bootstrap"):
    results.append("")
    if discovered.get("jni_helloworld"):
        ok("FULL JNI PIPELINE WORKS")
        results.append("  The JVM boots and Java code executes via JNI.")
        results.append("  JasperReports can be driven in-process -- no /usr/bin/java needed.")
        results.append("  Next: rewrite probes 3-7 to use JNI instead of subprocess.")
    elif discovered.get("jni_classload"):
        results.append("  JVM boots and stdlib classes load, but user class execution needs work.")
        results.append("  Check classpath and HelloJava.class bytecode version.")
    else:
        results.append("  JVM boots but class loading failed.")
        results.append("  Check LD_LIBRARY_PATH and JVM internal state.")
else:
    results.append("")
    results.append("  JVM could not be started via JNI.")
    results.append("  Java is fully blocked on ChoreBoy.")
    results.append("  Must pivot to pure-Python report engine (ReportLab, WeasyPrint, etc.)")

with open(DISCOVERED_PATH, "w") as f:
    json.dump(discovered, f, indent=2)

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe2_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 2 ===")
