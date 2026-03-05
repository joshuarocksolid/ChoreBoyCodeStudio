#!/usr/bin/env python
"""
Probe 2: tree-sitter Core Import
Tests whether the vendored tree-sitter 0.21.3 C extension loads
and basic objects can be created.
"""
from __future__ import annotations

import os
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/tree_sitter_probe"

vendor_dir = os.path.join(probe_root, "vendor")
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)

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


print("=== Probe 2: tree-sitter Core Import ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])
info("Executable", sys.executable)
info("Vendor dir", vendor_dir)

section("tree_sitter package import")
try:
    import tree_sitter
    ok("import tree_sitter")
    info("tree_sitter.__file__", tree_sitter.__file__)
    info("tree_sitter version", getattr(tree_sitter, "__version__", "no __version__"))
except ImportError:
    fail("import tree_sitter")
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe2_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print("\n=== END Probe 2 (FAILED -- import) ===")
    raise SystemExit(1)

section("C extension binding")
try:
    from tree_sitter import _binding
    ok("import tree_sitter._binding")
    info("_binding.__file__", _binding.__file__)
except ImportError:
    fail("import tree_sitter._binding")

section("Core class imports")
try:
    from tree_sitter import Language
    ok("Language class", str(Language))
except Exception:
    fail("Language import")

try:
    from tree_sitter import Parser
    ok("Parser class", str(Parser))
except Exception:
    fail("Parser import")

try:
    from tree_sitter import Node
    ok("Node class", str(Node))
except Exception:
    fail("Node import")

try:
    from tree_sitter import Tree
    ok("Tree class", str(Tree))
except Exception:
    fail("Tree import")

try:
    from tree_sitter import TreeCursor
    ok("TreeCursor class", str(TreeCursor))
except Exception:
    fail("TreeCursor import")

section("Parser object creation")
try:
    parser = Parser()
    ok("Parser()", repr(parser))
except Exception:
    fail("Parser()")

section("Language.build_library availability")
try:
    has_build = hasattr(Language, "build_library")
    info("Language.build_library", "available" if has_build else "not found")
except Exception:
    fail("Language.build_library check")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe2_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 2 ===")
