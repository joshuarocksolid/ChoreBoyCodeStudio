"""Imported-project signal analysis and runtime warning helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ImportAnalysis:
    """Structured imported-project analysis summary."""

    inferred_entry: str
    detected_signals: list[str]
    runtime_warnings: list[str]
    analysis_timestamp: str

    def to_metadata_payload(self) -> dict[str, object]:
        """Return manifest-friendly import metadata payload."""
        return {
            "source_type": "imported_external",
            "inferred_entry": self.inferred_entry,
            "detected_signals": list(self.detected_signals),
            "runtime_warnings": list(self.runtime_warnings),
            "analysis_timestamp": self.analysis_timestamp,
            "onboarding_completed": False,
        }


def analyze_imported_project(project_root: Path, inferred_entry: str) -> ImportAnalysis:
    """Inspect imported project for signals and compatibility warnings."""
    root = project_root.expanduser().resolve()
    signals: list[str] = []
    warnings: list[str] = []

    if (root / "pyproject.toml").is_file():
        signals.append("pyproject.toml")
    if (root / "setup.cfg").is_file():
        signals.append("setup.cfg")
    if (root / "Pipfile").is_file():
        signals.append("Pipfile")
    if (root / "poetry.lock").is_file():
        signals.append("poetry.lock")
    if (root / "src").is_dir():
        signals.append("src_layout")
    if any((root / name).is_file() for name in ("requirements.txt", "requirements-dev.txt")):
        signals.append("requirements_file")

    if "requirements_file" in signals or "Pipfile" in signals or "poetry.lock" in signals:
        warnings.append(
            "Project declares external dependencies. Ensure required packages are vendored "
            "or available in the constrained AppRun runtime."
        )

    if _project_contains_import(root, ("PyQt5", "PySide6", "tkinter")):
        warnings.append(
            "Project imports desktop GUI toolkits. Verify runtime support for those GUI modules in this environment."
        )

    if _project_contains_import(root, ("subprocess",)):
        warnings.append(
            "Project uses subprocess APIs. Runs in safe mode will block subprocess execution unless safe mode is disabled."
        )

    timestamp = datetime.now(timezone.utc).isoformat()
    return ImportAnalysis(
        inferred_entry=inferred_entry,
        detected_signals=sorted(set(signals)),
        runtime_warnings=warnings,
        analysis_timestamp=timestamp,
    )


def _project_contains_import(project_root: Path, module_names: tuple[str, ...]) -> bool:
    targets = set(module_names)
    for file_path in sorted(project_root.rglob("*.py")):
        if ".cbcs" in file_path.parts:
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for module_name in targets:
            if f"import {module_name}" in text or f"from {module_name} " in text:
                return True
    return False
