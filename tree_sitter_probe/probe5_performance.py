#!/usr/bin/env python
"""
Probe 5: Performance Benchmarks
Measures tree-sitter parse times, incremental re-parse times,
and compares against Python's ast.parse for the same inputs.
"""
from __future__ import annotations

import ast
import os
import sys
import time
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
    results_path = os.path.join(results_dir, "probe5_results.txt")
    with open(results_path, "w") as f:
        f.write(output)
    print(f"\nResults written to {results_path}")
    print(f"\n=== END Probe 5 ({msg}) ===")
    raise SystemExit(1)


def generate_python_code(num_functions=50, lines_per_func=10):
    parts = ["import os\nimport sys\nimport math\n\n"]
    for i in range(num_functions):
        parts.append(f"def function_{i}(arg1, arg2, arg3=None):\n")
        parts.append(f'    """Docstring for function_{i}."""\n')
        for j in range(lines_per_func):
            parts.append(f"    var_{j} = arg1 + {j} * arg2\n")
            if j % 3 == 0:
                parts.append(f"    if var_{j} > {j * 10}:\n")
                parts.append(f'        print(f"value: {{var_{j}}}")\n')
            if j % 5 == 0:
                parts.append(f"    for x_{j} in range({j + 1}):\n")
                parts.append(f"        var_{j} += x_{j}\n")
        parts.append(f"    return var_{j}\n\n")

    parts.append("\nclass DataProcessor:\n")
    parts.append('    """A sample data processor class."""\n\n')
    for i in range(10):
        parts.append(f"    def method_{i}(self, data):\n")
        parts.append(f"        result = []\n")
        parts.append(f"        for item in data:\n")
        parts.append(f"            if item > {i}:\n")
        parts.append(f"                result.append(item * {i + 1})\n")
        parts.append(f"        return result\n\n")

    parts.append('\nif __name__ == "__main__":\n')
    parts.append("    proc = DataProcessor()\n")
    for i in range(5):
        parts.append(f"    result_{i} = function_{i}({i}, {i+1})\n")
    parts.append('    print("Done")\n')
    return "".join(parts)


def bench(fn, iterations=10):
    times = []
    result = None
    for _ in range(iterations):
        t0 = time.perf_counter()
        result = fn()
        t1 = time.perf_counter()
        times.append(t1 - t0)
    times.sort()
    median = times[len(times) // 2]
    return median, min(times), max(times), result


print("=== Probe 5: Performance Benchmarks ===\n")

results.append("[Runtime]")
info("Python", sys.version.split()[0])

section("Setup")
try:
    from tree_sitter_languages import get_language, get_parser
    language = get_language("python")
    parser = get_parser("python")
    ok("tree-sitter ready")
except Exception:
    fail("Setup")
    bail("setup failed")

small_code = generate_python_code(num_functions=10, lines_per_func=5)
medium_code = generate_python_code(num_functions=30, lines_per_func=10)
large_code = generate_python_code(num_functions=80, lines_per_func=15)

small_bytes = small_code.encode("utf-8")
medium_bytes = medium_code.encode("utf-8")
large_bytes = large_code.encode("utf-8")

info("Small file", f"{len(small_code.splitlines())} lines, {len(small_bytes):,} bytes")
info("Medium file", f"{len(medium_code.splitlines())} lines, {len(medium_bytes):,} bytes")
info("Large file", f"{len(large_code.splitlines())} lines, {len(large_bytes):,} bytes")

section("tree-sitter: Full parse (small)")
ts_s_med, ts_s_mn, ts_s_mx, tree_small = bench(lambda: parser.parse(small_bytes), iterations=20)
info("Median", f"{ts_s_med*1000:.3f} ms")
info("Min/Max", f"{ts_s_mn*1000:.3f} / {ts_s_mx*1000:.3f} ms")

section("tree-sitter: Full parse (medium)")
ts_m_med, ts_m_mn, ts_m_mx, tree_medium = bench(lambda: parser.parse(medium_bytes), iterations=20)
info("Median", f"{ts_m_med*1000:.3f} ms")
info("Min/Max", f"{ts_m_mn*1000:.3f} / {ts_m_mx*1000:.3f} ms")

section("tree-sitter: Full parse (large)")
ts_l_med, ts_l_mn, ts_l_mx, tree_large = bench(lambda: parser.parse(large_bytes), iterations=10)
info("Median", f"{ts_l_med*1000:.3f} ms")
info("Min/Max", f"{ts_l_mn*1000:.3f} / {ts_l_mx*1000:.3f} ms")

section("tree-sitter: Incremental re-parse (medium, single-line edit)")
incr_m_med = None
try:
    tree_for_edit = parser.parse(medium_bytes)

    edit_line = 50
    edit_col = 4
    old_line_text = medium_code.splitlines()[edit_line]
    new_line_text = "    new_variable = 999  # edited line"

    lines = medium_code.splitlines(True)
    old_byte_offset = sum(len(l.encode("utf-8")) for l in lines[:edit_line]) + edit_col
    old_end_byte = old_byte_offset + len(old_line_text.encode("utf-8")) - edit_col
    new_end_byte = old_byte_offset + len(new_line_text.encode("utf-8"))

    tree_for_edit.edit(
        start_byte=old_byte_offset,
        old_end_byte=old_end_byte,
        new_end_byte=new_end_byte,
        start_point=(edit_line, edit_col),
        old_end_point=(edit_line, len(old_line_text)),
        new_end_point=(edit_line, edit_col + len(new_line_text)),
    )

    lines[edit_line] = lines[edit_line][:edit_col] + new_line_text + "\n"
    edited_bytes = "".join(lines).encode("utf-8")

    incr_m_med, mn, mx, _ = bench(
        lambda: parser.parse(edited_bytes, tree_for_edit), iterations=20
    )
    info("Median", f"{incr_m_med*1000:.3f} ms")
    info("Min/Max", f"{mn*1000:.3f} / {mx*1000:.3f} ms")
    ok("Incremental parse works")
except Exception:
    fail("Incremental parse")

section("tree-sitter: Incremental re-parse (large, single-line edit)")
incr_l_med = None
try:
    tree_for_edit_lg = parser.parse(large_bytes)

    edit_line = 100
    edit_col = 4
    old_line_text_lg = large_code.splitlines()[edit_line]
    new_line_text_lg = "    edited_value = 12345  # changed"

    lines_lg = large_code.splitlines(True)
    old_byte_offset_lg = sum(len(l.encode("utf-8")) for l in lines_lg[:edit_line]) + edit_col
    old_end_byte_lg = old_byte_offset_lg + len(old_line_text_lg.encode("utf-8")) - edit_col
    new_end_byte_lg = old_byte_offset_lg + len(new_line_text_lg.encode("utf-8"))

    tree_for_edit_lg.edit(
        start_byte=old_byte_offset_lg,
        old_end_byte=old_end_byte_lg,
        new_end_byte=new_end_byte_lg,
        start_point=(edit_line, edit_col),
        old_end_point=(edit_line, len(old_line_text_lg)),
        new_end_point=(edit_line, edit_col + len(new_line_text_lg)),
    )

    lines_lg[edit_line] = lines_lg[edit_line][:edit_col] + new_line_text_lg + "\n"
    edited_bytes_lg = "".join(lines_lg).encode("utf-8")

    incr_l_med, mn, mx, _ = bench(
        lambda: parser.parse(edited_bytes_lg, tree_for_edit_lg), iterations=20
    )
    info("Median", f"{incr_l_med*1000:.3f} ms")
    info("Min/Max", f"{mn*1000:.3f} / {mx*1000:.3f} ms")
    ok("Large incremental parse works")
except Exception:
    fail("Large incremental parse")

section("ast.parse comparison (small)")
median_ast_s, mn_s, mx_s, _ = bench(lambda: ast.parse(small_code), iterations=20)
info("Median", f"{median_ast_s*1000:.3f} ms")

section("ast.parse comparison (medium)")
median_ast_m, mn_m, mx_m, _ = bench(lambda: ast.parse(medium_code), iterations=20)
info("Median", f"{median_ast_m*1000:.3f} ms")

section("ast.parse comparison (large)")
median_ast_l, mn_l, mx_l, _ = bench(lambda: ast.parse(large_code), iterations=10)
info("Median", f"{median_ast_l*1000:.3f} ms")

section("tree-sitter: Query performance (medium file)")
try:
    highlight_query_str = """\
(comment) @comment
(string) @string
(integer) @number
(function_definition name: (identifier) @function.def)
(class_definition name: (identifier) @class.def)
(call function: (identifier) @function.call)
(identifier) @variable
["def" "class" "return" "if" "for" "while" "import" "from"] @keyword
"""
    query = language.query(highlight_query_str)
    tree_q = parser.parse(medium_bytes)

    median_q, mn_q, mx_q, captures = bench(
        lambda: query.captures(tree_q.root_node), iterations=20
    )
    info("Captures", f"{len(captures)} tokens")
    info("Median", f"{median_q*1000:.3f} ms")
    info("Min/Max", f"{mn_q*1000:.3f} / {mx_q*1000:.3f} ms")
    ok("Query execution")
except Exception:
    fail("Query performance")

section("Summary")
info("", "")
info("             ", "ts full    | ts incr    | ast.parse")
incr_m_str = f"{incr_m_med*1000:.3f} ms" if incr_m_med else "n/a"
incr_l_str = f"{incr_l_med*1000:.3f} ms" if incr_l_med else "n/a"
info("Small ", f"{ts_s_med*1000:.3f} ms  | n/a        | {median_ast_s*1000:.3f} ms")
info("Medium", f"{ts_m_med*1000:.3f} ms  | {incr_m_str:<10s} | {median_ast_m*1000:.3f} ms")
info("Large ", f"{ts_l_med*1000:.3f} ms  | {incr_l_str:<10s} | {median_ast_l*1000:.3f} ms")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe5_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 5 ===")
