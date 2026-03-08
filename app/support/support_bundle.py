"""Support-bundle generation for field diagnostics."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import zipfile

from app.bootstrap.logging_setup import get_active_log_path
from app.bootstrap.paths import PathInput, project_manifest_path
from app.support.diagnostics import ProjectHealthReport


def build_support_bundle(
    project_root: PathInput,
    *,
    diagnostics_report: ProjectHealthReport | None = None,
    state_root: PathInput | None = None,
    destination_dir: PathInput | None = None,
    last_run_log_path: PathInput | None = None,
) -> Path:
    """Build a zip bundle containing key diagnostics artifacts."""
    resolved_project_root = Path(project_root).expanduser().resolve()
    output_dir = (
        Path(destination_dir).expanduser().resolve()
        if destination_dir is not None
        else Path(tempfile.gettempdir()).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_name = f"cbcs_support_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    bundle_path = output_dir / bundle_name

    manifest_file = project_manifest_path(str(resolved_project_root))
    app_log_file = get_active_log_path(state_root=state_root)
    run_log_file = (
        Path(last_run_log_path).expanduser().resolve()
        if last_run_log_path is not None
        else None
    )

    with zipfile.ZipFile(bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        if manifest_file.exists():
            archive.write(manifest_file, arcname="project/cbcs/project.json")
        if app_log_file is not None and app_log_file.exists():
            archive.write(app_log_file, arcname="global_logs/app.log")
        if run_log_file is not None and run_log_file.exists():
            archive.write(run_log_file, arcname=f"project_logs/{run_log_file.name}")
        if diagnostics_report is not None:
            archive.writestr("diagnostics/project_health.json", json.dumps(diagnostics_report.to_dict(), indent=2, sort_keys=True))

    return bundle_path
