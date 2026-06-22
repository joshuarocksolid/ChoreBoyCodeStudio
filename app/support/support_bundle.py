"""Support-bundle generation for field diagnostics."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import zipfile

from app.bootstrap.logging_setup import get_active_log_path, get_subsystem_logger
from app.bootstrap.paths import (
    PathInput,
    global_plugins_registry_path,
    global_plugins_trust_path,
    project_manifest_path,
    project_plugins_path,
)
from app.core.models import RuntimeIssueReport
from app.support.diagnostics import ProjectHealthReport

_LOGGER = get_subsystem_logger("support")


def build_support_bundle(
    project_root: PathInput,
    *,
    diagnostics_report: ProjectHealthReport | None = None,
    runtime_issue_report: RuntimeIssueReport | None = None,
    local_history_diagnostics: dict[str, object] | None = None,
    plugin_diagnostics: dict[str, object] | None = None,
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
    _LOGGER.info("Building support bundle for %s", resolved_project_root)

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
        project_plugins_file = project_plugins_path(str(resolved_project_root))
        if project_plugins_file.exists():
            archive.write(project_plugins_file, arcname="project/cbcs/plugins.json")
        if app_log_file is not None and app_log_file.exists():
            archive.write(app_log_file, arcname="global_logs/app.log")
        plugin_registry_file = global_plugins_registry_path(state_root)
        if plugin_registry_file.exists():
            archive.write(plugin_registry_file, arcname="plugins/registry.json")
        plugin_trust_file = global_plugins_trust_path(state_root)
        if plugin_trust_file.exists():
            archive.write(plugin_trust_file, arcname="plugins/trust.json")
        if run_log_file is not None and run_log_file.exists():
            archive.write(run_log_file, arcname=f"project_logs/{run_log_file.name}")
        if diagnostics_report is not None:
            archive.writestr("diagnostics/project_health.json", json.dumps(diagnostics_report.to_dict(), indent=2, sort_keys=True))
        if runtime_issue_report is not None:
            archive.writestr(
                "diagnostics/runtime_explanations.json",
                json.dumps(runtime_issue_report.to_dict(), indent=2, sort_keys=True),
            )
        if local_history_diagnostics is not None:
            archive.writestr("diagnostics/local_history.json", json.dumps(local_history_diagnostics, indent=2, sort_keys=True))
        if plugin_diagnostics is not None:
            archive.writestr("diagnostics/plugins.json", json.dumps(plugin_diagnostics, indent=2, sort_keys=True))

    _LOGGER.info("Support bundle written to %s", bundle_path)
    return bundle_path
