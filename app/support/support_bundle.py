"""Support-bundle generation for field diagnostics."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import zipfile

from app.bootstrap.logging_setup import get_active_log_path
from app.bootstrap.paths import (
    PathInput,
    global_history_index_path,
    global_plugins_registry_path,
    global_plugins_trust_path,
    project_manifest_path,
    project_plugins_path,
)
from app.core.models import RuntimeIssueReport
from app.persistence.local_history_store import LocalHistoryStore
from app.persistence.settings_service import SettingsService
from app.plugins.discovery import discover_installed_plugins
from app.plugins.project_config import load_project_plugin_config_or_none
from app.plugins.registry_store import load_plugin_registry
from app.plugins.workflow_catalog import WorkflowProviderCatalog
from app.project.project_manifest import deterministic_project_id_for_root, load_project_manifest
from app.shell.settings_models import parse_effective_main_window_settings
from app.support.diagnostics import ProjectHealthReport


def build_support_bundle(
    project_root: PathInput,
    *,
    diagnostics_report: ProjectHealthReport | None = None,
    runtime_issue_report: RuntimeIssueReport | None = None,
    workflow_provider_metrics: list[dict[str, object]] | None = None,
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
        history_diagnostics = _build_local_history_diagnostics(resolved_project_root, state_root=state_root)
        if history_diagnostics is not None:
            archive.writestr("diagnostics/local_history.json", json.dumps(history_diagnostics, indent=2, sort_keys=True))
        plugin_diagnostics = _build_plugin_diagnostics(
            resolved_project_root,
            state_root=state_root,
            workflow_provider_metrics=workflow_provider_metrics,
        )
        if plugin_diagnostics is not None:
            archive.writestr("diagnostics/plugins.json", json.dumps(plugin_diagnostics, indent=2, sort_keys=True))

    return bundle_path


def _build_local_history_diagnostics(
    project_root: Path,
    *,
    state_root: PathInput | None,
) -> dict[str, object] | None:
    history_index = global_history_index_path(state_root)
    if not history_index.exists():
        return None

    manifest_file = project_manifest_path(project_root)
    if manifest_file.exists():
        try:
            project_id = load_project_manifest(manifest_file).project_id
        except Exception:
            project_id = deterministic_project_id_for_root(project_root)
    else:
        project_id = deterministic_project_id_for_root(project_root)

    settings_service = SettingsService(state_root=state_root)
    effective_settings = parse_effective_main_window_settings(
        settings_service.load_global(),
        settings_service.load_project(project_root),
    )
    history_store = LocalHistoryStore(
        state_root=state_root,
        retention_policy=effective_settings.local_history_retention_policy,
    )
    history_entries = history_store.list_global_history_files(project_id=project_id) if project_id is not None else []
    draft_entries = history_store.list_drafts()
    if project_id is not None:
        draft_entries = [entry for entry in draft_entries if entry.project_id == project_id]

    policy = effective_settings.local_history_retention_policy
    return {
        "history_root": str(history_store.history_root),
        "history_index": str(history_store.db_path),
        "project_id": project_id,
        "project_timeline_count": len(history_entries),
        "project_checkpoint_count": sum(entry.checkpoint_count for entry in history_entries),
        "project_deleted_timeline_count": sum(1 for entry in history_entries if entry.is_deleted),
        "project_draft_count": len(draft_entries),
        "retention_policy": {
            "max_checkpoints_per_file": policy.max_checkpoints_per_file,
            "retention_days": policy.retention_days,
            "max_tracked_file_bytes": policy.max_tracked_file_bytes,
            "excluded_glob_patterns": list(policy.excluded_glob_patterns),
        },
    }


def _build_plugin_diagnostics(
    project_root: Path,
    *,
    state_root: PathInput | None,
    workflow_provider_metrics: list[dict[str, object]] | None = None,
) -> dict[str, object] | None:
    discovered = discover_installed_plugins(state_root=state_root, include_bundled=True)
    registry = load_plugin_registry(state_root)
    registry_enabled_map = {
        (entry.plugin_id, entry.version): entry.enabled
        for entry in registry.entries
    }
    project_config = load_project_plugin_config_or_none(str(project_root))
    catalog = WorkflowProviderCatalog.from_plugins(
        discovered,
        enabled_map=registry_enabled_map,
        project_config=project_config,
    )
    return {
        "project_plugin_config": (
            None if project_config is None else project_config.to_dict()
        ),
        "registry_entries": [entry.to_dict() for entry in registry.entries],
        "discovered_plugins": [
            {
                "plugin_id": plugin.plugin_id,
                "version": plugin.version,
                "source_kind": plugin.source_kind,
                "install_path": plugin.install_path,
                "compatibility": (
                    None
                    if plugin.compatibility is None
                    else {
                        "is_compatible": plugin.compatibility.is_compatible,
                        "reasons": list(plugin.compatibility.reasons),
                    }
                ),
                "errors": list(plugin.errors),
                "permissions": list(plugin.manifest.permissions) if plugin.manifest is not None else [],
                "capabilities": list(plugin.manifest.capabilities) if plugin.manifest is not None else [],
                "providers": [
                    provider.to_dict()
                    for provider in (plugin.manifest.workflow_providers if plugin.manifest is not None else [])
                ],
            }
            for plugin in discovered
        ],
        "active_workflow_providers": [
            {
                "provider_key": provider.provider_key,
                "plugin_id": provider.plugin_id,
                "version": provider.plugin_version,
                "source_kind": provider.source_kind,
                "kind": provider.provider.kind,
                "lane": provider.provider.lane,
                "title": provider.provider.title,
                "permissions": list(provider.provider.permissions),
                "capabilities": list(provider.provider.capabilities),
            }
            for provider in catalog.providers
        ],
        "workflow_provider_metrics": list(workflow_provider_metrics or []),
    }
