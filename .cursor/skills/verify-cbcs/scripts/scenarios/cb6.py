"""CB-6 five packaging reports."""

from __future__ import annotations

import json

from scenarios.ctx import Ctx

CASES = {
    "a": {"main.py": 'import subprocess\nsubprocess.Popen(["/opt/freecad/AppRun", "app.py"])\n'},
    "b": {"main.py": 'import subprocess\nsubprocess.run(["pdftoppm", "-png", "in.pdf", "out"])\n'},
    "c": {"main.py": 'print("ok")\n', "unused_mod.py": "import missing_mod_unused_cb6\n"},
    "d": {"main.py": "import helper_cb6\n", "helper_cb6.py": "import missing_mod_reachable_cb6\n"},
    "e": {"main.py": 'import subprocess\nsubprocess.run(["/bin/sh", "-c", "ls"])\n'},
}

EXPECT = {
    "a": ("success", "AppRun"),
    "b": ("blocked", "pdftoppm"),
    "c": ("success", "missing_mod_unused_cb6"),
    "d": ("blocked", "missing_mod_reachable_cb6"),
    "e": ("success", "/bin/sh"),
}


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-cb6")
    for letter, files in CASES.items():
        outcome = ctx.eval_json(
            _ONE % (json.dumps(letter), json.dumps(json.dumps(files))),
            wait=90,
        )
        ctx.shot("cb6-%s-report" % letter, kind="window")
        kind, needle = EXPECT[letter]
        blob = json.dumps(outcome)
        if kind == "success":
            ok = outcome.get("success") is True and needle in blob
        else:
            ok = outcome.get("success") is False and needle in blob
        ctx.check("cb6-" + letter, ok, kind + " mentioning " + needle, blob[:500])
        ctx.metric(letter, outcome)


_ONE = r"""
import json, os
from pathlib import Path
from PySide2.QtWidgets import QApplication
from app.packaging.packager import package_project
from app.shell.runtime_center_dialog import RuntimeCenterDialog
letter = %s
files = json.loads(%s)
root = Path("/home/default/verify-pkg") / letter
out = Path("/home/default/verify-pkg-out") / letter
(root / "cbcs").mkdir(parents=True, exist_ok=True)
meta = {
    "schema_version": 2, "name": "pkg-" + letter, "project_id": "proj_pkg_" + letter,
    "default_entry": "main.py", "default_argv": [], "env_overrides": {},
    "exclude_patterns": ["vendor"], "run_configs": [], "project_notes": "",
    "template": "blank_project", "working_directory": ".",
}
(root / "cbcs" / "project.json").write_text(json.dumps(meta), encoding="utf-8")
for name, body in files.items():
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
out.mkdir(parents=True, exist_ok=True)
result = package_project(project_root=str(root), project_name="pkg-" + letter, entry_file="main.py", output_dir=str(out))
report = result.validation.issue_report
issues = []
for issue in report.issues:
    issues.append({"severity": str(issue.severity), "title": issue.title, "summary": (issue.summary or "")[:240]})
app = QApplication.instance()
win = next(w for w in app.topLevelWidgets() if type(w).__name__=="MainWindow")
dlg = RuntimeCenterDialog(
    title="Packaging Report" if result.success else "Packaging Failed",
    report=report,
    tokens=win._shell_theme_workflow.resolve_theme_tokens(),
    open_help_topic=lambda topic: None,
    presentation="packaging",
    package_location=str(result.artifact_root or ""),
    parent=win,
)
dlg.show()
dlg.raise_()
app.processEvents()
print("JSON:" + json.dumps({
    "success": bool(result.success),
    "error": str(result.error or ""),
    "artifact": str(result.artifact_root or ""),
    "issues": issues,
}))
dlg.close()
"""
