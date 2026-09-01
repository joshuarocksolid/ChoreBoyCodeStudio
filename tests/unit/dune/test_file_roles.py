from pathlib import Path

import pytest

from tools.dune.check import run
from tools.dune.file_roles import find_file_role_violations

pytestmark = pytest.mark.unit


def _write_source(repo_root: Path, relative_path: str, source: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


@pytest.mark.parametrize(
    ("relative_path", "source", "expected"),
    [
        (
            "app/core/constants.py",
            "import PySide2\n",
            "file-role: app/core/constants.py:1: app.core must not import PySide2",
        ),
        (
            "app/bootstrap/paths.py",
            "from PySide2 import QtCore\n",
            "file-role: app/bootstrap/paths.py:1: app.bootstrap must not import PySide2",
        ),
        (
            "app/run/run_service.py",
            "import PySide2.QtCore\n",
            "file-role: app/run/run_service.py:1: app.run must not import PySide2.QtCore",
        ),
        (
            "app/intelligence/session.py",
            "from PySide2.QtCore import QObject\n",
            "file-role: app/intelligence/session.py:1: app.intelligence must not import PySide2.QtCore",
        ),
        (
            "app/persistence/settings_store.py",
            "import PySide2\n",
            "file-role: app/persistence/settings_store.py:1: app.persistence must not import PySide2",
        ),
        (
            "app/plugins/manifest.py",
            "import PySide2\n",
            "file-role: app/plugins/manifest.py:1: app.plugins must not import PySide2",
        ),
        (
            "app/packaging/models.py",
            "import PySide2\n",
            "file-role: app/packaging/models.py:1: app.packaging must not import PySide2",
        ),
        (
            "app/project/project_service.py",
            "import PySide2\n",
            "file-role: app/project/project_service.py:1: app.project must not import PySide2",
        ),
        (
            "app/shell/main_window.py",
            "from app.runner.runner_main import main\n",
            "file-role: app/shell/main_window.py:1: app.shell must not import app.runner.runner_main",
        ),
        (
            "app/shell/main_window.py",
            "import app.runner\n",
            "file-role: app/shell/main_window.py:1: app.shell must not import app.runner",
        ),
        (
            "app/editors/editor_tab.py",
            "from app.packaging.packager import ProjectPackager\n",
            "file-role: app/editors/editor_tab.py:1: app.editors must not import app.packaging.packager",
        ),
        (
            "app/shell/main_window.py",
            "from ..runner.runner_main import main\n",
            "file-role: app/shell/main_window.py:1: app.shell must not import app.runner.runner_main",
        ),
        (
            "app/runner/runner_main.py",
            "import app.features\n",
            "file-role: app/runner/runner_main.py:1: app.runner must not import app.features",
        ),
        (
            "app/plugins/host_runtime.py",
            "from app.features import registry\n",
            "file-role: app/plugins/host_runtime.py:1: app.plugins.host_runtime must not import app.features",
        ),
    ],
)
def test_forbidden_import_reports_file_role(
    tmp_path: Path,
    relative_path: str,
    source: str,
    expected: str,
) -> None:
    _write_source(tmp_path, relative_path, source)

    assert find_file_role_violations(tmp_path, [relative_path]) == [expected]


@pytest.mark.parametrize(
    ("relative_path", "source"),
    [
        (
            "app/project/project_tree_widget.py",
            "from PySide2.QtWidgets import QTreeWidget\n",
        ),
        (
            "app/shell/repl_session_manager.py",
            "from app.runner.repl_protocol import REPL_CONTROL_PROTOCOL\n",
        ),
        (
            "app/shell/runtime_support_workflow.py",
            "from app.packaging.config import resolve_project_package_config\n",
        ),
        (
            "app/shell/package_wizard_dialog.py",
            "from app.packaging.models import ProjectPackageConfig\n",
        ),
        (
            "app/shell/main_window.py",
            "from app.packaging.layout import resolve_entry_path\n",
        ),
    ],
)
def test_public_role_import_is_allowed(
    tmp_path: Path,
    relative_path: str,
    source: str,
) -> None:
    _write_source(tmp_path, relative_path, source)

    assert find_file_role_violations(tmp_path, [relative_path]) == []


def test_check_reports_planted_core_qt_import(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "dune.yaml").write_text(
        "owners:\n"
        "  platform.core:\n"
        "    - app/core/**\n",
        encoding="utf-8",
    )
    relative_path = "app/core/constants.py"
    _write_source(tmp_path, relative_path, "import PySide2\n")

    exit_code = run(tmp_path, [relative_path])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "file-role: app/core/constants.py:1: "
        "app.core must not import PySide2\n"
    )
