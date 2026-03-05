#!/usr/bin/env python
"""
Probe 6: tree-sitter + PySide2 Coexistence
Imports both tree-sitter and PySide2 in the same FreeCAD AppRun process.
Parses Python code with tree-sitter and displays the AST in a Qt table.
This mirrors the Django Probe 4 pattern.
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
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 6 ({msg}) ===")
    raise SystemExit(1)


SAMPLE_CODE = b"""\
import os
from pathlib import Path

class FileProcessor:
    \"\"\"Process files in a directory.\"\"\"

    def __init__(self, root_dir: str):
        self.root = Path(root_dir)
        self.processed = []

    def scan(self):
        for path in self.root.iterdir():
            if path.is_file():
                self.processed.append(path.name)
        return len(self.processed)

    @property
    def count(self):
        return len(self.processed)

def main():
    proc = FileProcessor("/tmp")
    n = proc.scan()
    print(f"Found {n} files")

if __name__ == "__main__":
    main()
"""


print("=== Probe 6: tree-sitter + PySide2 Coexistence ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])
info("Executable", sys.executable)

section("tree-sitter import")
try:
    from tree_sitter_languages import get_language, get_parser
    language = get_language("python")
    parser = get_parser("python")
    ok("tree-sitter ready")
except Exception:
    fail("tree-sitter import")
    bail("tree-sitter failed")

section("Parse sample code")
try:
    tree = parser.parse(SAMPLE_CODE)
    root = tree.root_node
    ok("Parse", f"root type='{root.type}', children={root.named_child_count}")
except Exception:
    fail("Parse")
    bail("parse failed")

section("Collect AST data for Qt display")
ast_rows = []
try:
    cursor = tree.walk()

    def collect_nodes(cursor, depth=0):
        node = cursor.node
        text_preview = node.text.decode("utf-8", errors="replace").replace("\n", "\\n")
        if len(text_preview) > 60:
            text_preview = text_preview[:57] + "..."
        ast_rows.append({
            "depth": depth,
            "type": node.type,
            "named": node.is_named,
            "start": f"L{node.start_point[0]+1}:{node.start_point[1]}",
            "end": f"L{node.end_point[0]+1}:{node.end_point[1]}",
            "text": text_preview,
        })
        if cursor.goto_first_child():
            collect_nodes(cursor, depth + 1)
            while cursor.goto_next_sibling():
                collect_nodes(cursor, depth + 1)
            cursor.goto_parent()

    collect_nodes(cursor)
    ok("AST data collected", f"{len(ast_rows)} nodes")
except Exception:
    fail("AST data collection")
    bail("collection failed")

section("Run highlight query")
highlight_captures = []
try:
    query_str = """\
(comment) @comment
(string) @string
(integer) @number
(function_definition name: (identifier) @function.def)
(class_definition name: (identifier) @class.def)
(call function: (identifier) @function.call)
(identifier) @variable
["def" "class" "return" "if" "for" "import" "from"] @keyword
"""
    query = language.query(query_str)
    highlight_captures = query.captures(root)
    ok("Highlight query", f"{len(highlight_captures)} captures")
except Exception:
    fail("Highlight query")

section("PySide2 import")
try:
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QApplication,
        QHeaderView,
        QLabel,
        QMainWindow,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    ok("PySide2.QtWidgets")
except ImportError:
    results.append("  PySide2 not available (expected outside FreeCAD AppRun)")
    results.append("  This probe must be run via /opt/freecad/AppRun")
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print("\n=== END Probe 6 (no PySide2 -- skipped Qt UI) ===")
    raise SystemExit(0)

section("Build Qt UI")
try:
    app = QApplication.instance() or QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("tree-sitter + PySide2 on ChoreBoy - Probe 6")
    window.resize(900, 600)

    central = QWidget()
    layout = QVBoxLayout(central)

    header = QLabel(
        f"tree-sitter 0.21.3 | Python {sys.version.split()[0]} | "
        f"{len(ast_rows)} AST nodes | {len(highlight_captures)} highlight captures"
    )
    layout.addWidget(header)

    splitter = QSplitter(Qt.Vertical)

    ast_table = QTableWidget(min(len(ast_rows), 100), 5)
    ast_table.setHorizontalHeaderLabels(["Depth", "Node Type", "Start", "End", "Text"])
    ast_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)

    for row_idx, row_data in enumerate(ast_rows[:100]):
        indent = "  " * row_data["depth"]
        ast_table.setItem(row_idx, 0, QTableWidgetItem(str(row_data["depth"])))
        ast_table.setItem(row_idx, 1, QTableWidgetItem(f"{indent}{row_data['type']}"))
        ast_table.setItem(row_idx, 2, QTableWidgetItem(row_data["start"]))
        ast_table.setItem(row_idx, 3, QTableWidgetItem(row_data["end"]))
        ast_table.setItem(row_idx, 4, QTableWidgetItem(row_data["text"]))

    splitter.addWidget(ast_table)

    cap_table = QTableWidget(min(len(highlight_captures), 50), 4)
    cap_table.setHorizontalHeaderLabels(["Category", "Node Type", "Location", "Text"])
    cap_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

    for row_idx, (node, capture_name) in enumerate(highlight_captures[:50]):
        text = node.text.decode("utf-8", errors="replace").replace("\n", "\\n")
        if len(text) > 40:
            text = text[:37] + "..."
        cap_table.setItem(row_idx, 0, QTableWidgetItem(f"@{capture_name}"))
        cap_table.setItem(row_idx, 1, QTableWidgetItem(node.type))
        cap_table.setItem(row_idx, 2, QTableWidgetItem(
            f"L{node.start_point[0]+1}:{node.start_point[1]}"
        ))
        cap_table.setItem(row_idx, 3, QTableWidgetItem(text))

    splitter.addWidget(cap_table)
    layout.addWidget(splitter)

    window.setCentralWidget(central)
    ok("Window built")

    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)

    print("\nShowing Qt window... close the window to end the probe.")
    window.show()
    app.exec_()

    print("\n=== END Probe 6 (window closed) ===")

except Exception:
    fail("Qt UI build")
    output = "\n".join(results)
    print(output)
    results_path = os.path.join(results_dir, "probe6_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print("\n=== END Probe 6 (failed) ===")
