#!/usr/bin/env python
"""
Probe 4: Highlight Query Execution
Tests tree-sitter query patterns for syntax highlighting --
the actual feature that would power highlighting in CBCS.
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
    results_path = os.path.join(results_dir, "probe4_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 4 ({msg}) ===")
    raise SystemExit(1)


SAMPLE_CODE = b"""\
import os
from sys import argv

CONSTANT_VALUE = 42
_private = "hello"

class MyClass(object):
    \"\"\"Docstring for MyClass.\"\"\"

    class_var = True

    def __init__(self, name: str, count: int = 0):
        self.name = name
        self.count = count

    def process(self, data):
        if not data:
            return None
        for item in data:
            if item > CONSTANT_VALUE:
                print(f"Big: {item}")
            elif item < 0:
                raise ValueError("Negative!")
        return len(data)

    @staticmethod
    def helper():
        pass

    @property
    def info(self):
        return f"{self.name}: {self.count}"


def standalone_func(x, y=10):
    # A regular comment
    result = x + y * 2
    return result


# Module-level call
if __name__ == "__main__":
    obj = MyClass("test", count=5)
    val = standalone_func(3)
    print(val)
"""

HIGHLIGHT_QUERY = """\
(comment) @comment

(string) @string

(integer) @number
(float) @number
(true) @boolean
(false) @boolean
(none) @constant.builtin

(identifier) @variable

(function_definition name: (identifier) @function.def)
(class_definition name: (identifier) @class.def)
(decorator (identifier) @decorator)
(decorator (attribute attribute: (identifier) @decorator))

(call function: (identifier) @function.call)
(call function: (attribute attribute: (identifier) @method.call))

(parameter (identifier) @parameter)
(default_parameter name: (identifier) @parameter)
(typed_parameter (identifier) @parameter)
(typed_default_parameter name: (identifier) @parameter)

(import_statement module_name: (dotted_name (identifier) @module))
(import_from_statement module_name: (dotted_name (identifier) @module))

(attribute attribute: (identifier) @property)

(assignment left: (identifier) @variable.def)

(type (identifier) @type)

["def" "class" "return" "if" "elif" "else" "for" "while"
 "import" "from" "as" "pass" "raise" "and" "or" "not" "in"
 "is" "with" "try" "except" "finally" "yield" "lambda"
 "global" "nonlocal" "del" "assert" "break" "continue"] @keyword

["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "." ":" ";"] @punctuation.delimiter
["=" "+" "-" "*" "/" "%" "**" "//" "|" "&" "^" "~"
 "<" ">" "<=" ">=" "==" "!=" "+=" "-=" "*=" "/="
 "and" "or" "not" "in" "is"] @operator

(self) @variable.builtin
"""


print("=== Probe 4: Highlight Query Execution ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])

section("Setup parser and language")
try:
    from tree_sitter_languages import get_language, get_parser
    language = get_language("python")
    parser = get_parser("python")
    ok("Language + Parser ready")
except Exception:
    fail("Setup")
    bail("setup failed")

section("Parse sample code")
try:
    tree = parser.parse(SAMPLE_CODE)
    root = tree.root_node
    ok("Parse", f"{root.named_child_count} top-level nodes")
except Exception:
    fail("Parse")
    bail("parse failed")

section("Create highlight query")
try:
    query = language.query(HIGHLIGHT_QUERY)
    ok("Query compiled", repr(query))
except Exception:
    fail("Query compilation")
    bail("query compile failed")

section("Execute query.captures()")
try:
    captures = query.captures(root)
    ok("captures()", f"{len(captures)} captures")
except Exception:
    fail("captures()")
    bail("captures failed")

section("Capture categories breakdown")
categories = {}
for node, capture_name in captures:
    categories[capture_name] = categories.get(capture_name, 0) + 1
for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
    info(f"  @{cat}", f"{count}x")

section("Execute query.matches()")
try:
    matches = query.matches(root)
    ok("matches()", f"{len(matches)} matches")
except Exception:
    fail("matches()")

section("Sample captures (first 30)")
lines = SAMPLE_CODE.decode().splitlines()
for i, (node, capture_name) in enumerate(captures[:30]):
    text = node.text.decode().replace("\n", "\\n")
    if len(text) > 50:
        text = text[:47] + "..."
    info(
        f"  [{i}]",
        f"@{capture_name:<22s} L{node.start_point[0]+1}:{node.start_point[1]:<3d} '{text}'",
    )

section("Viewport-restricted query (lines 8-25 only)")
try:
    viewport_captures = query.captures(
        root,
        start_point=(7, 0),
        end_point=(25, 0),
    )
    ok("Viewport captures", f"{len(viewport_captures)} in lines 8-25")
    vp_cats = {}
    for node, capture_name in viewport_captures:
        vp_cats[capture_name] = vp_cats.get(capture_name, 0) + 1
    for cat, count in sorted(vp_cats.items(), key=lambda x: -x[1])[:10]:
        info(f"    @{cat}", f"{count}x")
except Exception:
    fail("Viewport captures")

section("Key highlight coverage check")
expected_highlights = {
    "keyword": "def, class, return, if, for, etc.",
    "string": "string literals",
    "comment": "# comments",
    "function.def": "function definition names",
    "class.def": "class definition names",
    "function.call": "function call names",
    "variable": "identifiers",
    "parameter": "function parameters",
}
for cat, desc in expected_highlights.items():
    count = categories.get(cat, 0)
    if count > 0:
        ok(f"@{cat}", f"{count}x -- {desc}")
    else:
        info(f"@{cat}", f"NOT CAPTURED -- {desc}")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe4_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 4 ===")
