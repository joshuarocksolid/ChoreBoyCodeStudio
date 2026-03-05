#!/usr/bin/env python
"""
Probe 1: Environment Fingerprint
Tests the AppRun Python environment's ability to load C extensions.
This probe has ZERO tree-sitter dependencies -- it tests the environment itself.
"""
from __future__ import annotations

import importlib.machinery
import os
import platform
import struct
import sys
import sysconfig
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/tree_sitter_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


def info(label, value):
    results.append(f"  {label}: {value}")


print("=== Probe 1: Environment Fingerprint ===\n")

results.append("[Runtime]")
info("Python version", sys.version)
info("Executable", sys.executable)
info("Platform", platform.platform())
info("Machine", platform.machine())
info("Pointer size", f"{struct.calcsize('P') * 8}-bit")
info("Probe root", probe_root)

section("Python ABI / Extension Tags")
soabi = sysconfig.get_config_var("SOABI")
info("SOABI", soabi)
info("EXT_SUFFIX", sysconfig.get_config_var("EXT_SUFFIX"))
info("EXTENSION_SUFFIXES", importlib.machinery.EXTENSION_SUFFIXES)
info("MULTIARCH", sysconfig.get_config_var("MULTIARCH"))

wheel_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
info("Expected wheel cpython tag", wheel_tag)

vendored_so_suffix = f".cpython-39-x86_64-linux-gnu.so"
expected_suffix = sysconfig.get_config_var("EXT_SUFFIX")
if expected_suffix == vendored_so_suffix:
    ok("Vendored .so suffix matches runtime", vendored_so_suffix)
else:
    info(
        "MISMATCH",
        f"Vendored .so uses '{vendored_so_suffix}' but runtime expects '{expected_suffix}'",
    )

section("glibc version")
try:
    glibc_ver = platform.libc_ver()
    info("libc", f"{glibc_ver[0]} {glibc_ver[1]}")
except Exception:
    fail("platform.libc_ver()")

try:
    confstr_val = os.confstr("CS_GNU_LIBC_VERSION")
    info("CS_GNU_LIBC_VERSION", confstr_val)
except (ValueError, OSError, AttributeError):
    info("CS_GNU_LIBC_VERSION", "not available")

try:
    import ctypes
    libc = ctypes.CDLL("libc.so.6")
    gnu_get_libc_version = libc.gnu_get_libc_version
    gnu_get_libc_version.restype = ctypes.c_char_p
    ver = gnu_get_libc_version().decode()
    info("gnu_get_libc_version()", ver)

    parts = ver.split(".")
    major, minor = int(parts[0]), int(parts[1])
    if major > 2 or (major == 2 and minor >= 17):
        ok("glibc >= 2.17 (manylinux2014)", ver)
    else:
        info("BLOCKER", f"glibc {ver} < 2.17, manylinux2014 wheels will NOT load")
except Exception:
    fail("ctypes glibc check")

section("C extension loading (built-in modules)")
builtin_c_modules = ["_json", "_struct", "_sqlite3", "zlib", "math", "_hashlib"]
for mod_name in builtin_c_modules:
    try:
        mod = __import__(mod_name)
        mod_file = getattr(mod, "__file__", "built-in")
        ok(mod_name, mod_file)
    except Exception:
        fail(mod_name)

section("ctypes / dlopen capability")
try:
    import ctypes
    ok("ctypes import", ctypes.__file__)
except Exception:
    fail("ctypes import")

try:
    import ctypes.util
    libc_path = ctypes.util.find_library("c")
    info("find_library('c')", libc_path)
    if libc_path:
        handle = ctypes.CDLL(libc_path)
        ok("CDLL(libc)", "dlopen works")
    else:
        handle = ctypes.CDLL("libc.so.6")
        ok("CDLL('libc.so.6')", "direct path dlopen works")
except Exception:
    fail("dlopen test")

section("sys.path entries")
for i, p in enumerate(sys.path):
    info(f"  [{i}]", p)

section("Vendored .so file inventory")
vendor_dir = os.path.join(probe_root, "vendor")
if os.path.isdir(vendor_dir):
    so_files = []
    for dirpath, _dirnames, filenames in os.walk(vendor_dir):
        for fn in filenames:
            if fn.endswith(".so"):
                full = os.path.join(dirpath, fn)
                relpath = os.path.relpath(full, vendor_dir)
                size = os.path.getsize(full)
                so_files.append((relpath, size))
    if so_files:
        for relpath, size in sorted(so_files):
            info(f"  {relpath}", f"{size:,} bytes")
    else:
        info("WARNING", "No .so files found in vendor/")
else:
    info("WARNING", f"vendor/ directory not found at {vendor_dir}")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe1_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 1 ===")
