#!/usr/bin/env python
"""
Probe 3: Language Loading + Python Code Parsing
Tests loading the Python grammar from tree-sitter-languages,
parsing sample code, and walking the AST.
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


def bail(msg):
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe3_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 3 ({msg}) ===")
    raise SystemExit(1)


SAMPLE_CODE = b"""\
import os
import sys

class Calculator:
    \"\"\"A simple calculator class.\"\"\"

    def __init__(self, name="default"):
        self.name = name
        self._history = []

    def add(self, a, b):
        result = a + b
        self._history.append(("add", a, b, result))
        return result

    def divide(self, a, b):
        if b == 0:
            raise ValueError("Cannot divide by zero")
        result = a / b
        self._history.append(("divide", a, b, result))
        return result

    @property
    def history(self):
        return list(self._history)


def main():
    calc = Calculator("probe3")
    print(f"Result: {calc.add(2, 3)}")
    # This is a comment
    for i in range(10):
        calc.add(i, i * 2)

if __name__ == "__main__":
    main()
"""


print("=== Probe 3: Language Loading + Parsing ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])

section("tree_sitter_languages import")
try:
    import tree_sitter_languages
    ok("import tree_sitter_languages")
    info("__file__", tree_sitter_languages.__file__)
except ImportError:
    fail("import tree_sitter_languages")
    bail("tree_sitter_languages import failed")

section("Load Python language")
try:
    language = tree_sitter_languages.get_language("python")
    ok("get_language('python')", repr(language))
except Exception:
    fail("get_language('python')")
    bail("language load failed")

section("Get Python parser")
try:
    parser = tree_sitter_languages.get_parser("python")
    ok("get_parser('python')", repr(parser))
except Exception:
    fail("get_parser('python')")
    bail("parser creation failed")

section("Available languages (sample)")
available = []
test_langs = [
    "python", "javascript", "typescript", "json", "html", "css",
    "bash", "c", "cpp", "rust", "go", "java", "ruby", "yaml",
    "toml", "markdown", "sql", "dockerfile", "make",
]
for lang_name in test_langs:
    try:
        tree_sitter_languages.get_language(lang_name)
        available.append(lang_name)
    except Exception:
        pass
info("Available", ", ".join(available))
info("Count", f"{len(available)} / {len(test_langs)} tested")

section("Parse sample Python code")
try:
    tree = parser.parse(SAMPLE_CODE)
    root = tree.root_node
    ok("parser.parse()", f"root type='{root.type}'")
    info("Root start_point", root.start_point)
    info("Root end_point", root.end_point)
    info("Root child_count", root.child_count)
    info("Root named_child_count", root.named_child_count)
except Exception:
    fail("parser.parse()")
    bail("parse failed")

section("AST structure (top-level children)")
for i in range(root.named_child_count):
    child = root.named_children[i]
    child_detail = ""
    name_node = child.child_by_field_name("name")
    if name_node:
        child_detail = f" name='{name_node.text.decode()}'"
    info(f"  [{i}]", f"{child.type}{child_detail}  ({child.start_point} -> {child.end_point})")

section("TreeCursor walk (node type inventory)")
node_types = {}
cursor = tree.walk()


def walk_tree(cursor, depth=0):
    node_type = cursor.node.type
    node_types[node_type] = node_types.get(node_type, 0) + 1
    if cursor.goto_first_child():
        walk_tree(cursor, depth + 1)
        while cursor.goto_next_sibling():
            walk_tree(cursor, depth + 1)
        cursor.goto_parent()


walk_tree(cursor)
info("Total unique node types", len(node_types))
for nt, count in sorted(node_types.items(), key=lambda x: -x[1])[:20]:
    info(f"    {nt}", f"{count}x")

section("Key node type verification")
expected_types = [
    "module", "class_definition", "function_definition", "identifier",
    "parameters", "block", "if_statement", "for_statement", "comment",
    "string", "import_statement", "call", "return_statement",
]
for nt in expected_types:
    if nt in node_types:
        ok(nt, f"{node_types[nt]}x")
    else:
        info(nt, "NOT FOUND")

section("S-expression (first 500 chars)")
sexp = root.sexp()
info("sexp length", len(sexp))
info("sexp preview", sexp[:500])

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe3_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 3 ===")
