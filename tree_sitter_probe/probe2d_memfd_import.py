#!/usr/bin/env python
"""Probe 2d: Refined memfd import for tree-sitter on ChoreBoy.

probe2c proved ctypes.CDLL works from memfd but failed at
importlib.util.spec_from_file_location (no file extension on
/proc/self/fd/N so Python cannot pick a loader). This probe
uses ExtensionFileLoader + spec_from_loader to bypass that.

Two strategies are tested:

  Strategy A (minimal): load _binding via memfd, load languages.so
                        via ctypes.CDLL from memfd, construct Language
                        objects directly via pointer. Does NOT need
                        tree_sitter_languages.core at all.

  Strategy B (full):    also load tree_sitter_languages.core via memfd
                        so the convenience get_language/get_parser API
                        works.
"""
from __future__ import annotations

import ctypes
import importlib.machinery
import importlib.util
import os
import sys
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
CORE_SO = os.path.join(
    vendor_dir, "tree_sitter_languages", "core.cpython-39-x86_64-linux-gnu.so"
)
LANGUAGES_SO = os.path.join(
    vendor_dir, "tree_sitter_languages", "languages.so"
)

results: list[str] = []
open_fds: list[int] = []


def section(title: str) -> None:
    results.append(f"\n[{title}]")


def ok(label: str, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def fail(label: str) -> None:
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


def info(label: str, value: object) -> None:
    results.append(f"  {label}: {value}")


def write_results() -> None:
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe2d_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")


def load_so_to_memfd(so_path: str, label: str) -> tuple[int, str]:
    so_bytes = open(so_path, "rb").read()
    fd = os.memfd_create(label, 0)
    os.write(fd, so_bytes)
    os.lseek(fd, 0, os.SEEK_SET)
    open_fds.append(fd)
    memfd_path = f"/proc/self/fd/{fd}"
    info(f"  memfd {label}", f"fd={fd}, size={len(so_bytes):,}")
    return fd, memfd_path


def load_extension_via_memfd(module_name: str, memfd_path: str) -> object:
    loader = importlib.machinery.ExtensionFileLoader(module_name, memfd_path)
    spec = importlib.util.spec_from_loader(module_name, loader, origin=memfd_path)
    if spec is None:
        raise RuntimeError(f"spec_from_loader returned None for {module_name}")
    if spec.loader is None:
        raise RuntimeError(f"spec has no loader for {module_name}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


print("=== Probe 2d: Refined memfd Import ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])
info("Executable", sys.executable)
info("Kernel", os.uname().release)

# ── Step 1: memfd + CDLL baseline re-verify ──────────────────────────

section("Step 1: memfd + CDLL re-verify")

memfd_works = False

if not hasattr(os, "memfd_create"):
    info("RESULT", "os.memfd_create not available -- cannot proceed")
else:
    try:
        _fd, binding_memfd = load_so_to_memfd(BINDING_SO, "ts_binding_verify")
        handle = ctypes.CDLL(binding_memfd)
        ok("CDLL from memfd", f"handle={handle}")
        memfd_works = True
    except Exception:
        fail("CDLL from memfd")

if not memfd_works:
    info("VERDICT", "memfd CDLL baseline failed -- cannot proceed")
    write_results()
    print("\n=== END Probe 2d (early exit) ===")
    raise SystemExit(1)

# ── Step 2: Load _binding via ExtensionFileLoader ────────────────────

section("Step 2: Load _binding via ExtensionFileLoader + spec_from_loader")

binding_loaded = False
fallback_used = None

try:
    _fd2, binding_memfd2 = load_so_to_memfd(BINDING_SO, "ts_binding_import")
    load_extension_via_memfd("tree_sitter._binding", binding_memfd2)
    ok("tree_sitter._binding loaded via ExtensionFileLoader")
    binding_loaded = True
except Exception:
    fail("ExtensionFileLoader for _binding")

if not binding_loaded:
    section("Step 2 fallback A: imp.load_dynamic")
    try:
        import imp
        _fd2b, binding_memfd2b = load_so_to_memfd(BINDING_SO, "ts_binding_imp")
        mod = imp.load_dynamic("tree_sitter._binding", binding_memfd2b)
        sys.modules["tree_sitter._binding"] = mod
        ok("tree_sitter._binding loaded via imp.load_dynamic")
        binding_loaded = True
        fallback_used = "imp.load_dynamic"
    except Exception:
        fail("imp.load_dynamic for _binding")

if not binding_loaded:
    section("Step 2 fallback B: symlink -> memfd")
    try:
        import tempfile
        _fd2c, binding_memfd2c = load_so_to_memfd(BINDING_SO, "ts_binding_sym")
        sym_dir = tempfile.mkdtemp(prefix="ts_sym_")
        sym_path = os.path.join(sym_dir, "_binding.cpython-39-x86_64-linux-gnu.so")
        os.symlink(binding_memfd2c, sym_path)
        info("  symlink", f"{sym_path} -> {binding_memfd2c}")
        loader = importlib.machinery.ExtensionFileLoader("tree_sitter._binding", sym_path)
        spec = importlib.util.spec_from_loader("tree_sitter._binding", loader, origin=sym_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("spec_from_loader returned None via symlink")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["tree_sitter._binding"] = mod
        spec.loader.exec_module(mod)
        ok("tree_sitter._binding loaded via symlink to memfd")
        binding_loaded = True
        fallback_used = "symlink"
    except Exception:
        fail("symlink for _binding")

if not binding_loaded:
    info("VERDICT", "Cannot load _binding C extension by any method -- tree-sitter NOT VIABLE")
    write_results()
    print("\n=== END Probe 2d (early exit) ===")
    raise SystemExit(1)

if fallback_used:
    info("method used", fallback_used)

# ── Step 3: Import tree_sitter package (pure Python) ─────────────────

section("Step 3: Import tree_sitter package from vendor")

ts_imported = False

try:
    if vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)
    import tree_sitter
    from tree_sitter import Language, Parser
    ok("import tree_sitter", f"path={tree_sitter.__file__}")
    parser_obj = Parser()
    ok("Parser() created")
    ts_imported = True
except Exception:
    fail("import tree_sitter")

if not ts_imported:
    info("VERDICT", "tree_sitter package import failed")
    write_results()
    print("\n=== END Probe 2d (early exit) ===")
    raise SystemExit(1)

# ── Step 4: Load languages.so via memfd + ctypes (Strategy A) ────────

section("Step 4: Load languages.so via memfd + ctypes.CDLL")

lang_lib = None

try:
    _fd3, lang_memfd = load_so_to_memfd(LANGUAGES_SO, "ts_languages")
    lang_lib = ctypes.CDLL(lang_memfd)
    ok("languages.so loaded via memfd CDLL", f"handle={lang_lib}")
except Exception:
    fail("languages.so CDLL from memfd")

if lang_lib is None:
    info("VERDICT", "Cannot load languages.so -- grammars unavailable")
    write_results()
    print("\n=== END Probe 2d (early exit) ===")
    raise SystemExit(1)

# ── Step 5: Strategy A -- construct Language directly from pointer ────

section("Step 5: Strategy A -- direct Language construction via pointer")

strategy_a_works = False

try:
    lang_fn = lang_lib.tree_sitter_python
    lang_fn.restype = ctypes.c_void_p
    python_ptr = lang_fn()
    ok("tree_sitter_python() pointer", f"ptr=0x{python_ptr:x}")
    python_lang = Language(python_ptr, "python")
    ok("Language(ptr, 'python') created", f"version={python_lang.version}")
    strategy_a_works = True
except Exception:
    fail("Language construction from pointer")

# ── Step 6: Parse Python code (proof of life) ────────────────────────

section("Step 6: Parse Python code (proof of life)")

parse_works = False

if not strategy_a_works:
    info("SKIP", "Language construction failed")
else:
    try:
        parser_obj.set_language(python_lang)
        ok("parser.set_language(python)")

        sample = (
            b"def greet(name: str) -> str:\n"
            b"    message = f'Hello {name}!'\n"
            b"    print(message)\n"
            b"    return message\n"
        )
        tree = parser_obj.parse(sample)
        root = tree.root_node
        ok("parse", f"root='{root.type}', children={root.named_child_count}")

        cursor = root.walk()
        node_types: list[str] = []
        visited = 0
        while True:
            node_types.append(cursor.node.type)
            visited += 1
            if cursor.goto_first_child():
                continue
            while not cursor.goto_next_sibling():
                if not cursor.goto_parent():
                    break
            else:
                continue
            break
        ok("AST walk", f"{visited} nodes, types={sorted(set(node_types))[:15]}")
        parse_works = True
    except Exception:
        fail("Parse test")

# ── Step 7: Query test (highlighting use case) ───────────────────────

section("Step 7: Highlight query captures")

query_works = False

if not parse_works:
    info("SKIP", "Parse failed")
else:
    try:
        query_src = (
            "(function_definition name: (identifier) @function.def)\n"
            "(call function: (identifier) @function.call)\n"
            "(string) @string\n"
            "(comment) @comment\n"
            "(identifier) @variable\n"
        )
        query = python_lang.query(query_src)
        captures = query.captures(root)
        ok("query.captures()", f"{len(captures)} captures")
        for node, cap_name in captures[:10]:
            info(f"    @{cap_name}", f"'{node.text.decode()}' [{node.start_point}-{node.end_point}]")
        query_works = True
    except Exception:
        fail("Query test")

# ── Step 8: Strategy B -- try tree_sitter_languages.core via memfd ───

section("Step 8: Strategy B -- tree_sitter_languages.core via memfd (bonus)")

strategy_b_works = False

try:
    _fd4, core_memfd = load_so_to_memfd(CORE_SO, "ts_core")
    load_extension_via_memfd("tree_sitter_languages.core", core_memfd)
    ok("tree_sitter_languages.core loaded via ExtensionFileLoader")
    strategy_b_works = True
except Exception:
    fail("tree_sitter_languages.core via memfd")

if strategy_b_works:
    try:
        import tree_sitter_languages
        ok("import tree_sitter_languages")
        tsl_lang = tree_sitter_languages.get_language("python")
        tsl_parser = tree_sitter_languages.get_parser("python")
        ok("get_language/get_parser via tree_sitter_languages")
    except Exception:
        fail("tree_sitter_languages convenience API")
        strategy_b_works = False

# ── Step 9: Additional languages test ────────────────────────────────

section("Step 9: Additional languages (via Strategy A)")

extra_langs_ok = 0
extra_langs_tried = ["javascript", "c", "cpp", "rust", "json", "html", "css", "bash"]

if not strategy_a_works:
    info("SKIP", "Strategy A failed")
else:
    for lang_name in extra_langs_tried:
        try:
            fn = getattr(lang_lib, f"tree_sitter_{lang_name}")
            fn.restype = ctypes.c_void_p
            ptr = fn()
            lang_obj = Language(ptr, lang_name)
            extra_langs_ok += 1
        except Exception:
            info(f"  {lang_name}", "not available in languages.so")
    info("extra languages loaded", f"{extra_langs_ok}/{len(extra_langs_tried)}")

# ── Verdict ──────────────────────────────────────────────────────────

section("=== VERDICT ===")
info("", "")

if strategy_a_works and parse_works and query_works:
    info("RESULT", "tree-sitter is VIABLE on ChoreBoy via memfd")
    info("", "")
    info("WORKING METHOD", "Strategy A (memfd + direct Language pointer)")
    if fallback_used:
        info("  _binding loader", fallback_used)
    else:
        info("  _binding loader", "ExtensionFileLoader + spec_from_loader")
    info("  languages.so", "ctypes.CDLL from memfd")
    info("  Language()", "constructed from ctypes function pointer")
    info("", "")
    info("Strategy B (tree_sitter_languages)", "YES" if strategy_b_works else "NO (but not needed)")
    info("", "")
    info("INTEGRATION PATH", "At CBCS startup:")
    info("  1", "Read _binding .so and languages.so from vendored files")
    info("  2", "Write each to os.memfd_create()")
    info("  3", "Load _binding via ExtensionFileLoader from /proc/self/fd/")
    info("  4", "import tree_sitter (pure Python, finds _binding in sys.modules)")
    info("  5", "Load languages.so via ctypes.CDLL from /proc/self/fd/")
    info("  6", "Construct Language objects via ctypes function pointers")
    info("  7", "Create Parser, call set_language(), ready to parse")
    info("", "")
    total_so_bytes = sum(
        os.path.getsize(p) for p in [BINDING_SO, LANGUAGES_SO] if os.path.exists(p)
    )
    info("MEMORY COST", f"~{total_so_bytes / 1024 / 1024:.1f} MB in memfds (one-time at startup)")
    info("EXTRA LANGUAGES", f"{extra_langs_ok} of {len(extra_langs_tried)} tested")
elif strategy_a_works:
    info("RESULT", "tree-sitter PARTIALLY viable (import works, parse/query failed)")
    info("", "")
    info("INVESTIGATE", "Parser or Language construction issue")
else:
    info("RESULT", "tree-sitter is NOT VIABLE on ChoreBoy")
    info("", "")
    info("RECOMMENDATION", "Use Pygments (pure Python) for syntax highlighting")

write_results()

for fd in open_fds:
    try:
        os.close(fd)
    except OSError:
        pass

print("\n=== END Probe 2d ===")
