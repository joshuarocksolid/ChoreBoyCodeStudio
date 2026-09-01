"""Project/runtime diagnostics and health-check reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.bootstrap.capability_probe import run_startup_capability_probe
from app.bootstrap.paths import PathInput
from app.core import constants
from app.core.models import CapabilityProbeReport

UNKNOWN_GIT_SHA = "unknown"
_GIT_SHA_LENGTH = 40


@dataclass(frozen=True)
class DiagnosticItem:
    """One diagnostic check result."""

    check_id: str
    is_ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectHealthReport:
    """Aggregate diagnostics for project and runtime checks."""

    project_root: str
    checks: list[DiagnosticItem]

    @property
    def all_ok(self) -> bool:
        return all(check.is_ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": self.project_root,
            "all_ok": self.all_ok,
            "checks": [
                {
                    "check_id": check.check_id,
                    "is_ok": check.is_ok,
                    "message": check.message,
                    "details": dict(check.details),
                }
                for check in self.checks
            ],
        }


def build_project_health_report(
    project_root: str,
    project_checks: list[DiagnosticItem],
    *,
    state_root: PathInput | None = None,
    temp_root: PathInput | None = None,
) -> ProjectHealthReport:
    """Merge project checks with runtime capability probe results."""
    checks = list(project_checks)
    capability_report = run_startup_capability_probe(state_root=state_root, temp_root=temp_root)
    checks.extend(capability_checks_from_probe(capability_report))
    return ProjectHealthReport(project_root=project_root, checks=checks)


def capability_checks_from_probe(capability_report: CapabilityProbeReport) -> list[DiagnosticItem]:
    """Convert capability probe results into diagnostic items."""
    return [
        DiagnosticItem(
            check_id=f"runtime.{check.check_id}",
            is_ok=check.is_available,
            message=check.message,
            details=check.details,
        )
        for check in capability_report.checks
    ]


def resolve_build_identity(*, repo_root: PathInput | None = None) -> tuple[str, str]:
    """Return app version and git SHA for the installed or checked-out tree."""
    root = (
        Path(repo_root).expanduser().resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[2]
    )
    return constants.APP_VERSION, resolve_git_sha(root)


def render_build_identity_text(app_version: str, git_sha: str) -> str:
    """Render the support-bundle build.txt payload."""
    return f"app_version={app_version}\ngit_sha={git_sha}\n"


def resolve_git_sha(repo_root: PathInput) -> str:
    """Read HEAD from a git checkout, including linked worktrees."""
    git_dir = _discover_git_dir(Path(repo_root).expanduser().resolve())
    if git_dir is None:
        return UNKNOWN_GIT_SHA
    head_path = git_dir / "HEAD"
    head = _read_text(head_path)
    if head is None:
        return UNKNOWN_GIT_SHA
    head = head.strip()
    if head.startswith("ref:"):
        sha = _read_ref_sha(git_dir, head.split(":", 1)[1].strip())
        return sha if sha is not None else UNKNOWN_GIT_SHA
    normalized = _normalize_git_sha(head)
    return normalized if normalized is not None else UNKNOWN_GIT_SHA


def _discover_git_dir(start: Path) -> Path | None:
    current = start if start.is_dir() else start.parent
    for candidate in (current, *current.parents):
        git_entry = candidate / ".git"
        if git_entry.is_dir():
            return git_entry
        if git_entry.is_file():
            resolved = _git_dir_from_file(git_entry)
            if resolved is not None:
                return resolved
    return None


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _git_dir_from_file(git_file: Path) -> Path | None:
    text = _read_text(git_file)
    if text is None:
        return None
    text = text.strip()
    if not text.startswith("gitdir:"):
        return None
    raw = text.split(":", 1)[1].strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (git_file.parent / path).resolve()
    return path if path.is_dir() else None


def _read_ref_sha(git_dir: Path, ref: str) -> str | None:
    for base in _git_search_dirs(git_dir):
        ref_path = base / ref
        if ref_path.is_file():
            value = _read_text(ref_path) or ""
            normalized = _normalize_git_sha(value)
            if normalized is not None:
                return normalized
        packed = _sha_from_packed_refs(base / "packed-refs", ref)
        if packed is not None:
            return packed
    return None


def _git_search_dirs(git_dir: Path) -> list[Path]:
    dirs = [git_dir]
    commondir_file = git_dir / "commondir"
    raw = _read_text(commondir_file)
    if raw is None:
        return dirs
    raw = raw.strip()
    if not raw:
        return dirs
    common = Path(raw)
    if not common.is_absolute():
        common = (git_dir / common).resolve()
    if common.is_dir() and common not in dirs:
        dirs.append(common)
    return dirs


def _sha_from_packed_refs(packed_path: Path, ref: str) -> str | None:
    packed_text = _read_text(packed_path)
    if packed_text is None:
        return None
    for line in packed_text.splitlines():
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        normalized = _normalize_git_sha(parts[0])
        if normalized is not None and parts[1] == ref:
            return normalized
    return None


def _normalize_git_sha(value: str) -> str | None:
    candidate = value.strip().lower()
    if len(candidate) != _GIT_SHA_LENGTH:
        return None
    try:
        int(candidate, 16)
    except ValueError:
        return None
    return candidate
