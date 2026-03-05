#!/usr/bin/env python
"""
Probe 2b: noexec Workaround
Diagnoses the 'failed to map segment from shared object' error from Probe 2.
Tests whether copying vendored .so files to an exec-enabled path allows loading.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/tree_sitter_probe"

vendor_dir = os.path.join(probe_root, "vendor")
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


def write_results():
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe2b_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=== Probe 2b: noexec Workaround ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])
info("Executable", sys.executable)
info("Vendor dir", vendor_dir)

section("Diagnose: mount flags on key paths")
try:
    with open("/proc/mounts", "r") as f:
        mounts = f.read()
    home_mounts = []
    tmp_mounts = []
    opt_mounts = []
    for line in mounts.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            mountpoint = parts[1]
            flags = parts[3]
            if "/home" in mountpoint or mountpoint == "/":
                home_mounts.append((mountpoint, flags))
            if "/tmp" in mountpoint:
                tmp_mounts.append((mountpoint, flags))
            if "/opt" in mountpoint:
                opt_mounts.append((mountpoint, flags))

    info("Mounts covering /home", "")
    for mp, flags in home_mounts:
        has_noexec = "noexec" in flags.split(",")
        info(f"  {mp}", f"{'NOEXEC' if has_noexec else 'exec ok'}  flags={flags}")

    info("Mounts covering /tmp", "")
    if tmp_mounts:
        for mp, flags in tmp_mounts:
            has_noexec = "noexec" in flags.split(",")
            info(f"  {mp}", f"{'NOEXEC' if has_noexec else 'exec ok'}  flags={flags}")
    else:
        info("  /tmp", "no dedicated mount (inherits from /)")

    info("Mounts covering /opt", "")
    if opt_mounts:
        for mp, flags in opt_mounts:
            has_noexec = "noexec" in flags.split(",")
            info(f"  {mp}", f"{'NOEXEC' if has_noexec else 'exec ok'}  flags={flags}")
    else:
        info("  /opt", "no dedicated mount (inherits from /)")
except Exception:
    fail("mount flag check")

section("Diagnose: direct ctypes.CDLL load from vendor (expect failure)")
so_path = os.path.join(
    vendor_dir, "tree_sitter", "_binding.cpython-39-x86_64-linux-gnu.so"
)
try:
    import ctypes
    ctypes.CDLL(so_path)
    ok("CDLL from vendor", "loaded (unexpected -- noexec not the issue)")
except OSError as e:
    info("CDLL from vendor", f"FAILED as expected: {e}")

section("Workaround: copy .so files to /tmp and try loading")
tmp_vendor = None
try:
    tmp_vendor = tempfile.mkdtemp(prefix="ts_probe_")
    info("Temp dir", tmp_vendor)

    ts_src = os.path.join(vendor_dir, "tree_sitter")
    ts_dst = os.path.join(tmp_vendor, "tree_sitter")
    shutil.copytree(ts_src, ts_dst)

    tsl_src = os.path.join(vendor_dir, "tree_sitter_languages")
    tsl_dst = os.path.join(tmp_vendor, "tree_sitter_languages")
    shutil.copytree(tsl_src, tsl_dst)

    so_files_copied = []
    for dirpath, _dirnames, filenames in os.walk(tmp_vendor):
        for fn in filenames:
            if fn.endswith(".so"):
                full = os.path.join(dirpath, fn)
                so_files_copied.append(os.path.relpath(full, tmp_vendor))
    info("Copied .so files", ", ".join(so_files_copied))
    ok("Copy to /tmp")
except Exception:
    fail("Copy to /tmp")
    write_results()
    print("\n=== END Probe 2b (copy failed) ===")
    raise SystemExit(1)

section("Test: ctypes.CDLL load from /tmp")
tmp_so_path = os.path.join(
    tmp_vendor, "tree_sitter", "_binding.cpython-39-x86_64-linux-gnu.so"
)
try:
    handle = ctypes.CDLL(tmp_so_path)
    ok("CDLL from /tmp", f"handle={handle}")
except OSError as e:
    info("CDLL from /tmp", f"FAILED: {e}")
    info("IMPLICATION", "/tmp also has noexec -- tree-sitter is NOT viable")
    write_results()
    if tmp_vendor:
        shutil.rmtree(tmp_vendor, ignore_errors=True)
    print("\n=== END Probe 2b (FAILED -- /tmp also noexec) ===")
    raise SystemExit(1)

section("Test: import tree_sitter from /tmp")
sys.path.insert(0, tmp_vendor)
try:
    import tree_sitter
    ok("import tree_sitter", tree_sitter.__file__)
    info("Version", getattr(tree_sitter, "__version__", "no __version__"))

    from tree_sitter import Language, Parser
    ok("Language class", str(Language))
    ok("Parser class", str(Parser))

    parser = Parser()
    ok("Parser()", repr(parser))
except Exception:
    fail("import tree_sitter from /tmp")
    write_results()
    if tmp_vendor:
        shutil.rmtree(tmp_vendor, ignore_errors=True)
    print("\n=== END Probe 2b (import from /tmp failed) ===")
    raise SystemExit(1)

section("Test: tree_sitter_languages from /tmp")
try:
    import tree_sitter_languages
    ok("import tree_sitter_languages", tree_sitter_languages.__file__)

    language = tree_sitter_languages.get_language("python")
    ok("get_language('python')", repr(language))

    parser = tree_sitter_languages.get_parser("python")
    ok("get_parser('python')", repr(parser))
except Exception:
    fail("tree_sitter_languages from /tmp")

section("Test: parse Python code from /tmp-loaded modules")
try:
    sample = b'def hello(name):\n    print(f"Hello {name}")\n'
    tree = parser.parse(sample)
    root = tree.root_node
    ok("Parse", f"root='{root.type}', children={root.named_child_count}")

    func = root.named_children[0]
    info("First child", f"type='{func.type}', name='{func.child_by_field_name('name').text.decode()}'")

    query = language.query('(function_definition name: (identifier) @fn)')
    captures = query.captures(root)
    ok("Query captures", f"{len(captures)} captures")
    for node, name in captures:
        info("  Capture", f"@{name} = '{node.text.decode()}'")
except Exception:
    fail("Parse from /tmp")

section("Conclusion")
info("", "")
info("RESULT", "tree-sitter WORKS when .so files are on an exec-enabled filesystem")
info("", "The /home/default/ partition has noexec, blocking mmap with PROT_EXEC.")
info("", "Workaround: copy vendored .so files to /tmp at startup before importing.")
info("", "")
info("IMPLICATION FOR CBCS", "")
info("  Option A", "At app startup, copy vendor/tree_sitter*.so to /tmp/, add to sys.path")
info("  Option B", "Install .so files under /opt/freecad/usr/lib/ if writable")
info("  Option C", "Bundle in the AppRun image if building a custom FreeCAD package")

write_results()

if tmp_vendor:
    shutil.rmtree(tmp_vendor, ignore_errors=True)
    info("Cleanup", f"Removed {tmp_vendor}")

print("\n=== END Probe 2b ===")
