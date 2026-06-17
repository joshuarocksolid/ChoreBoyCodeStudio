"""Generate app/intelligence/stdlib_api_index.json from the active Python runtime.

Run via FreeCAD AppRun for Python 3.9 parity on ChoreBoy:

    ~/opt/freecad/AppRun -c "import runpy; runpy.run_path('scripts/generate_stdlib_api_index.py', run_name='__main__')"

Or from repo root with Cloud dev AppRun:

    /opt/freecad/AppRun -c "import os, runpy, sys; root='...'; os.chdir(root); sys.path.insert(0, root); runpy.run_path('scripts/generate_stdlib_api_index.py', run_name='__main__')"
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.intelligence.completion_models import CompletionKind
from app.project.dependency_classifier import STDLIB_TOP_LEVELS

OUTPUT_PATH = REPO_ROOT / "app" / "intelligence" / "stdlib_api_index.json"


def _kind_for_member(module: Any, name: str) -> str:
    try:
        value = getattr(module, name)
    except Exception:
        return CompletionKind.ATTRIBUTE.value
    if inspect.ismodule(value):
        return CompletionKind.MODULE.value
    if inspect.isclass(value):
        return CompletionKind.CLASS.value
    if inspect.isfunction(value) or inspect.isbuiltin(value):
        return CompletionKind.FUNCTION.value
    if inspect.ismethod(value) or inspect.ismethoddescriptor(value):
        return CompletionKind.METHOD.value
    if isinstance(value, property):
        return CompletionKind.PROPERTY.value
    return CompletionKind.ATTRIBUTE.value


def _members_for_module(module_name: str) -> list[dict[str, str]]:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return []

    members: list[dict[str, str]] = []
    try:
        names = sorted(name for name in dir(module) if name and not name.startswith("_"))
    except Exception:
        return []

    for name in names:
        members.append(
            {
                "name": name,
                "kind": _kind_for_member(module, name),
                "detail": f"{module_name} stdlib member",
            }
        )
    return members


def build_index() -> dict[str, Any]:
    modules: dict[str, list[dict[str, str]]] = {}
    skipped: list[str] = []
    for module_name in sorted(STDLIB_TOP_LEVELS):
        entries = _members_for_module(module_name)
        if entries:
            modules[module_name] = entries
        else:
            skipped.append(module_name)
    return {
        "metadata": {
            "schema_version": 1,
            "source": "generate_stdlib_api_index.py",
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "module_count": len(modules),
            "skipped_modules": skipped,
            "notes": "Regenerate with scripts/generate_stdlib_api_index.py via AppRun Python 3.9.",
        },
        "modules": modules,
    }


def main() -> int:
    payload = build_index()
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    module_count = payload["metadata"]["module_count"]
    print(f"Wrote {OUTPUT_PATH} ({module_count} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
