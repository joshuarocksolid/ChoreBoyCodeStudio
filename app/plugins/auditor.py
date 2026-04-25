from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import re

from app.plugins.models import PluginManifest
from app.project.dependency_classifier import COMPILED_EXTENSION_SUFFIXES

_NATIVE_EXTENSION_SUFFIXES = COMPILED_EXTENSION_SUFFIXES
_FORBIDDEN_HIDDEN_PATH_TOKENS = (
    ".cbcs",
    ".choreboy_code_studio",
    ".choreboy_code_studio_state",
    ".pytest_cache",
    ".ropeproject",
    ".jedi",
)
_SUBPROCESS_PATTERN = re.compile(
    r"\bsubprocess\.(Popen|run|call|check_call|check_output)\b|\bfrom\s+subprocess\s+import\b"
)


@dataclass(frozen=True)
class PluginAuditFinding:
    code: str
    message: str
    relative_path: str | None = None

    def to_message(self) -> str:
        if self.relative_path:
            return f"{self.message} ({self.relative_path})"
        return self.message


def audit_plugin_package(plugin_root: Path, manifest: PluginManifest) -> list[PluginAuditFinding]:
    findings: list[PluginAuditFinding] = []
    resolved_root = plugin_root.expanduser().resolve()
    if manifest.runtime_entrypoint and not manifest.runtime_entrypoint.endswith(".py"):
        findings.append(
            PluginAuditFinding(
                code="plugin.runtime_entrypoint_not_python",
                message="Workflow/runtime plugins must use a Python runtime.entrypoint in phase 1.",
                relative_path=manifest.runtime_entrypoint,
            )
        )
    for path in sorted(resolved_root.rglob("*")):
        relative_path = path.relative_to(resolved_root).as_posix()
        if any(part.startswith(".") for part in Path(relative_path).parts):
            findings.append(
                PluginAuditFinding(
                    code="plugin.hidden_path",
                    message="Plugin package must not include hidden files or directories.",
                    relative_path=relative_path,
                )
            )
            continue
        if path.is_file() and path.suffix.lower() in _NATIVE_EXTENSION_SUFFIXES:
            findings.append(
                PluginAuditFinding(
                    code="plugin.native_extension",
                    message="Phase-1 workflow plugins must remain pure Python and cannot ship native extensions.",
                    relative_path=relative_path,
                )
            )
            continue
        if not path.is_file() or path.suffix.lower() != ".py":
            continue
        findings.extend(_audit_python_source(path, resolved_root))
    return findings


def audit_plugin_package_messages(plugin_root: Path, manifest: PluginManifest) -> list[str]:
    return [finding.to_message() for finding in audit_plugin_package(plugin_root, manifest)]


def _audit_python_source(file_path: Path, plugin_root: Path) -> list[PluginAuditFinding]:
    try:
        source_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            PluginAuditFinding(
                code="plugin.source_read_error",
                message=f"Unable to read plugin Python source during audit: {exc}",
                relative_path=file_path.relative_to(plugin_root).as_posix(),
            )
        ]
    relative_path = file_path.relative_to(plugin_root).as_posix()
    findings: list[PluginAuditFinding] = []
    try:
        ast.parse(source_text, filename=str(file_path), feature_version=(3, 9))
    except SyntaxError as exc:
        findings.append(
            PluginAuditFinding(
                code="plugin.python39_incompatible",
                message=(
                    "Plugin Python source must be compatible with Python 3.9 "
                    f"(syntax error at line {exc.lineno})."
                ),
                relative_path=relative_path,
            )
        )
    lowered_source = source_text.lower()
    for token in _FORBIDDEN_HIDDEN_PATH_TOKENS:
        if token.lower() in lowered_source:
            findings.append(
                PluginAuditFinding(
                    code="plugin.hidden_path_reference",
                    message="Plugin source must not rely on hidden project or state directories.",
                    relative_path=relative_path,
                )
            )
            break
    if _SUBPROCESS_PATTERN.search(source_text):
        findings.append(
            PluginAuditFinding(
                code="plugin.subprocess_assumption",
                message=(
                    "Plugin source must not assume unrestricted subprocess execution in phase 1."
                ),
                relative_path=relative_path,
            )
        )
    return findings
