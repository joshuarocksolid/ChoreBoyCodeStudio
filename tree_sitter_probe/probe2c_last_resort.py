#!/usr/bin/env python
"""
Probe 2c: Last-Resort Workarounds for C Extension Loading
Tests memfd_create + /proc/self/fd/ and scans all candidate paths
for an exec-enabled writable location.
"""
from __future__ import annotations

import ctypes
import importlib.machinery
import importlib.util
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

BINDING_SO = os.path.join(
    vendor_dir, "tree_sitter", "_binding.cpython-39-x86_64-linux-gnu.so"
)

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
    results_path = os.path.join(results_dir, "probe2c_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


print("=== Probe 2c: Last-Resort Workarounds ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])
info("Executable", sys.executable)
info("Kernel", os.uname().release)

# ── Section 1: statvfs scan ──────────────────────────────────────────────

section("Workaround A: statvfs scan for exec-enabled writable paths")

uid = os.getuid()
candidate_paths = [
    "/dev/shm",
    "/run",
    f"/run/user/{uid}",
    "/var/tmp",
    "/var/run",
    "/opt",
    "/opt/freecad/usr/lib/python3.9",
    "/opt/freecad/usr/lib/python3.9/lib-dynload",
]

for p in sys.path:
    if p and p not in candidate_paths and os.path.isdir(p):
        candidate_paths.append(p)

viable_paths = []

for candidate in candidate_paths:
    if not os.path.exists(candidate):
        info(f"  {candidate}", "does not exist")
        continue

    try:
        st = os.statvfs(candidate)
        noexec = bool(st.f_flag & os.ST_NOEXEC)
        writable = os.access(candidate, os.W_OK)
        status_parts = []
        status_parts.append("NOEXEC" if noexec else "exec-ok")
        status_parts.append("writable" if writable else "read-only")
        info(f"  {candidate}", " | ".join(status_parts))

        if not noexec and writable:
            viable_paths.append(candidate)
    except Exception as e:
        info(f"  {candidate}", f"statvfs error: {e}")

if viable_paths:
    ok("Viable paths found", ", ".join(viable_paths))
else:
    info("RESULT", "No writable + exec-enabled paths found via statvfs")

# ── Section 2: try CDLL from viable paths ────────────────────────────────

section("Workaround A (cont): CDLL load from viable paths")

path_that_works = None

if not viable_paths:
    info("SKIP", "No viable paths to test")
else:
    for vp in viable_paths:
        test_dir = None
        try:
            test_dir = tempfile.mkdtemp(prefix="ts_", dir=vp)
            dst = os.path.join(test_dir, os.path.basename(BINDING_SO))
            shutil.copy2(BINDING_SO, dst)
            handle = ctypes.CDLL(dst)
            ok(f"CDLL from {vp}", f"handle={handle}")
            path_that_works = vp
            break
        except Exception as e:
            info(f"  CDLL from {vp}", f"FAILED: {e}")
        finally:
            if test_dir and os.path.exists(test_dir):
                shutil.rmtree(test_dir, ignore_errors=True)

# ── Section 3: memfd_create ──────────────────────────────────────────────

section("Workaround B: memfd_create + /proc/self/fd/")

memfd_works = False
memfd_fd = None

if not hasattr(os, "memfd_create"):
    info("os.memfd_create", "NOT AVAILABLE (requires Python 3.8+)")
else:
    info("os.memfd_create", "available")

    try:
        so_bytes = open(BINDING_SO, "rb").read()
        info(".so file size", f"{len(so_bytes):,} bytes")

        memfd_fd = os.memfd_create("ts_binding_probe", 0)
        ok("memfd_create()", f"fd={memfd_fd}")

        written = os.write(memfd_fd, so_bytes)
        ok("write to memfd", f"{written:,} bytes written")

        os.lseek(memfd_fd, 0, os.SEEK_SET)

        memfd_path = f"/proc/self/fd/{memfd_fd}"
        info("memfd path", memfd_path)

        exists = os.path.exists(memfd_path)
        info("/proc/self/fd/ accessible", str(exists))

        if exists:
            try:
                handle = ctypes.CDLL(memfd_path)
                ok("CDLL from memfd", f"handle={handle}")
                memfd_works = True
            except OSError as e:
                info("CDLL from memfd", f"FAILED: {e}")
        else:
            info("CDLL from memfd", "SKIPPED: /proc/self/fd/ not accessible")
    except Exception:
        fail("memfd_create sequence")

# ── Section 4: full import via memfd ─────────────────────────────────────

section("Workaround B (cont): full tree-sitter import via memfd")

memfd_fds = {}

if not memfd_works:
    info("SKIP", "memfd CDLL did not work, cannot proceed")
else:
    all_so_files = {
        "tree_sitter._binding": os.path.join(
            vendor_dir, "tree_sitter", "_binding.cpython-39-x86_64-linux-gnu.so"
        ),
        "tree_sitter_languages.core": os.path.join(
            vendor_dir, "tree_sitter_languages", "core.cpython-39-x86_64-linux-gnu.so"
        ),
    }

    languages_so = os.path.join(vendor_dir, "tree_sitter_languages", "languages.so")

    memfd_fds = {}

    try:
        for mod_name, so_path in all_so_files.items():
            so_data = open(so_path, "rb").read()
            fd = os.memfd_create(mod_name.replace(".", "_"), 0)
            os.write(fd, so_data)
            os.lseek(fd, 0, os.SEEK_SET)
            memfd_path = f"/proc/self/fd/{fd}"
            memfd_fds[mod_name] = (fd, memfd_path)
            info(f"  memfd for {mod_name}", f"fd={fd}, path={memfd_path}")

        lang_fd = os.memfd_create("languages_so", 0)
        lang_data = open(languages_so, "rb").read()
        os.write(lang_fd, lang_data)
        os.lseek(lang_fd, 0, os.SEEK_SET)
        lang_memfd_path = f"/proc/self/fd/{lang_fd}"
        memfd_fds["languages.so"] = (lang_fd, lang_memfd_path)
        info(f"  memfd for languages.so", f"fd={lang_fd}, path={lang_memfd_path}")

        ok("All memfds created")
    except Exception:
        fail("memfd creation for all .so files")
        memfd_works = False

    if memfd_works:
        try:
            binding_fd, binding_path = memfd_fds["tree_sitter._binding"]

            spec = importlib.util.spec_from_file_location(
                "tree_sitter._binding",
                binding_path,
                submodule_search_locations=[],
            )
            if spec and spec.loader:
                binding_mod = importlib.util.module_from_spec(spec)
                sys.modules["tree_sitter._binding"] = binding_mod
                spec.loader.exec_module(binding_mod)
                ok("tree_sitter._binding loaded via memfd")
            else:
                info("tree_sitter._binding", "spec_from_file_location returned None")
                memfd_works = False
        except Exception:
            fail("tree_sitter._binding import via memfd")
            memfd_works = False

    if memfd_works:
        try:
            ts_init = os.path.join(vendor_dir, "tree_sitter", "__init__.py")
            spec_ts = importlib.util.spec_from_file_location(
                "tree_sitter",
                ts_init,
                submodule_search_locations=[os.path.join(vendor_dir, "tree_sitter")],
            )
            if spec_ts and spec_ts.loader:
                ts_mod = importlib.util.module_from_spec(spec_ts)
                sys.modules["tree_sitter"] = ts_mod
                spec_ts.loader.exec_module(ts_mod)
                ok("import tree_sitter via memfd", f"classes: {dir(ts_mod)}")

                from tree_sitter import Language, Parser
                ok("Language + Parser imported")
                parser = Parser()
                ok("Parser() created")
            else:
                info("tree_sitter", "spec_from_file_location returned None")
                memfd_works = False
        except Exception:
            fail("tree_sitter import via memfd")
            memfd_works = False

    if memfd_works:
        try:
            core_fd, core_path = memfd_fds["tree_sitter_languages.core"]

            spec_core = importlib.util.spec_from_file_location(
                "tree_sitter_languages.core",
                core_path,
                submodule_search_locations=[],
            )
            if spec_core and spec_core.loader:
                core_mod = importlib.util.module_from_spec(spec_core)
                sys.modules["tree_sitter_languages.core"] = core_mod
                spec_core.loader.exec_module(core_mod)
                ok("tree_sitter_languages.core loaded via memfd")
            else:
                info("tree_sitter_languages.core", "spec returned None")
                memfd_works = False
        except Exception:
            fail("tree_sitter_languages.core import via memfd")
            memfd_works = False

    if memfd_works:
        try:
            tsl_init = os.path.join(vendor_dir, "tree_sitter_languages", "__init__.py")
            spec_tsl = importlib.util.spec_from_file_location(
                "tree_sitter_languages",
                tsl_init,
                submodule_search_locations=[
                    os.path.join(vendor_dir, "tree_sitter_languages")
                ],
            )
            if spec_tsl and spec_tsl.loader:
                tsl_mod = importlib.util.module_from_spec(spec_tsl)
                sys.modules["tree_sitter_languages"] = tsl_mod
                spec_tsl.loader.exec_module(tsl_mod)
                ok("import tree_sitter_languages via memfd")
            else:
                info("tree_sitter_languages", "spec returned None")
                memfd_works = False
        except Exception:
            fail("tree_sitter_languages import via memfd")
            memfd_works = False

# ── Section 5: parse test ────────────────────────────────────────────────

section("Proof of life: parse Python code")

parse_test_dir = None

if not memfd_works and not path_that_works:
    info("SKIP", "No working workaround to test parsing")
else:
    try:
        if memfd_works:
            from tree_sitter_languages import get_language, get_parser
        elif path_that_works:
            parse_test_dir = tempfile.mkdtemp(prefix="ts_full_", dir=path_that_works)
            shutil.copytree(
                os.path.join(vendor_dir, "tree_sitter"),
                os.path.join(parse_test_dir, "tree_sitter"),
            )
            shutil.copytree(
                os.path.join(vendor_dir, "tree_sitter_languages"),
                os.path.join(parse_test_dir, "tree_sitter_languages"),
            )
            sys.path.insert(0, parse_test_dir)
            from tree_sitter_languages import get_language, get_parser

        language = get_language("python")
        parser = get_parser("python")
        ok("Language + Parser ready")

        sample = b'def hello(name):\n    print(f"Hello {name}")\n    return True\n'
        tree = parser.parse(sample)
        root = tree.root_node
        ok("Parse", f"root='{root.type}', children={root.named_child_count}")

        query = language.query(
            "(function_definition name: (identifier) @fn)\n"
            "(call function: (identifier) @call)\n"
            "(string) @string\n"
        )
        captures = query.captures(root)
        ok("Query captures", f"{len(captures)} captures")
        for node, name in captures:
            info(f"    @{name}", f"'{node.text.decode()}'")

        info("", "")
        ok("TREE-SITTER FULLY WORKS via workaround")
    except Exception:
        fail("Parse test")
    finally:
        if parse_test_dir and os.path.exists(parse_test_dir):
            shutil.rmtree(parse_test_dir, ignore_errors=True)

# ── Section 6: summary ──────────────────────────────────────────────────

section("=== VERDICT ===")
info("", "")

if memfd_works:
    info("RESULT", "tree-sitter is VIABLE via memfd_create workaround")
    info("", "")
    info("HOW", "At CBCS startup, before importing tree_sitter:")
    info("  1", "Read .so files from vendor/ on disk")
    info("  2", "Write each to memfd_create() file descriptor")
    info("  3", "Use importlib to load modules from /proc/self/fd/{fd}")
    info("  4", "Then import tree_sitter / tree_sitter_languages normally")
    info("", "")
    info("COST", "~85 MB RAM for the languages.so memfd (one-time at startup)")
elif path_that_works:
    info("RESULT", f"tree-sitter is VIABLE via exec-enabled path: {path_that_works}")
    info("", "")
    info("HOW", "At CBCS startup:")
    info("  1", f"Copy vendor .so files to {path_that_works}/ts_vendor/")
    info("  2", "Add that path to sys.path")
    info("  3", "Import tree_sitter normally")
else:
    info("RESULT", "tree-sitter is NOT VIABLE on ChoreBoy")
    info("", "")
    info("REASON", "All writable paths have noexec; memfd_create also blocked or unavailable")
    info("", "")
    info("RECOMMENDATION", "Use Pygments (pure Python) for syntax highlighting")
    info("  -", "500+ languages, zero C extensions, zero noexec risk")
    info("  -", "Already designed as Phase 1-3 of the highlighting plan")
    info("  -", "Reclassify tree-sitter from 'optional Phase 4' to 'not viable'")

write_results()

for key, (fd, _) in list(memfd_fds.items()) if memfd_works else []:
    try:
        os.close(fd)
    except OSError:
        pass

print("\n=== END Probe 2c ===")
