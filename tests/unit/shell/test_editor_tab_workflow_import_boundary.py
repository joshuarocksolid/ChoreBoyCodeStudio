"""Import boundary tests for editor tab workflow layer."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_WORKFLOW_MODULES = (
    "app/shell/editor_tab_workflow.py",
    "app/shell/editor_tab_workflow_factory.py",
    "app/shell/editor_tab_workflow_mixins.py",
)


@pytest.mark.parametrize("module_path", _WORKFLOW_MODULES)
def test_editor_tab_workflow_layer_does_not_import_shell_composition(module_path: str) -> None:
    source = Path(module_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    composition_imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("app.shell.shell_composition")
    ]
    assert composition_imports == []
