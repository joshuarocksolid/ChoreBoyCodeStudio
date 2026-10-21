"""Tree-sitter colors. SQL stays plain text."""

from __future__ import annotations

from scenarios.common import open_file, open_project, write_tree
from scenarios.ctx import Ctx

SAMPLES = {
    "sample.py": ("def hi():\n    return 1\n", 0, "keyword", "#0000ff", "TreeSitter"),
    "sample.json": ('{"a": 1}\n', 0, "punctuation", "#000000", "TreeSitter"),
    "sample.md": ("# Title\n", 0, "markdown_heading", "#800000", "TreeSitter"),
    "sample.yaml": ("name: value\n", 0, "json_key", "#0451a5", "TreeSitter"),
    "sample.html": ('<p class="x">\n', 1, "tag", "#267f99", "TreeSitter"),
    "sample.sql": ("SELECT 1\n", 0, "plain", "", "none"),
}


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-ts", wait_ready=90)
    label = ctx.wait_chip("Runtime ready", timeout=30)
    root = "/home/default/verify-ts"
    write_tree(ctx, root, {name: body for name, (body, _c, _t, _color, _kind) in SAMPLES.items()}, "verify-ts", "sample.py")
    open_project(ctx, root)
    for name, (_body, column, token, color, kind) in SAMPLES.items():
        open_file(ctx, root + "/" + name)
        described = ctx.eval(_DESCRIBE % column, wait=20)
        ctx.shot("ts-" + name.replace("sample.", ""), selector="#shell.mainWindow", kind="crop")
        if kind == "none":
            ok = "none" in described.splitlines()[0].lower() or "None" in described
            ctx.check(name, ok, "no highlighter", described[:300])
        else:
            ok = token in described and color in described.lower()
            ctx.check(name, ok, token + " " + color, described[:400])
    ctx.check("chip-still-ready", "Runtime ready" in ctx.chip(), "chip stays Runtime ready", label)
    ctx.check("no-error-dialog", "Traceback" not in ctx.eval("print('ok')\n", wait=10), "no dialog", "ok")


_DESCRIBE = r"""
win = next(w for w in app.topLevelWidgets() if type(w).__name__ == "MainWindow")
ed = win._editor_tab_workflow.active_editor_widget()
hl = getattr(ed, "_highlighter", None)
print(type(hl).__name__ if hl is not None else "none")
if hl is not None and hasattr(hl, "describe_position"):
    print(hl.describe_position(0, %d))
"""
