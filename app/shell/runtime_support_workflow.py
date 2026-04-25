"""Runtime support, health-check, bundle, and packaging shell workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide2.QtWidgets import QDialog, QMessageBox, QWidget

from app.bootstrap.paths import project_logs_dir
from app.core.models import CapabilityProbeReport, LoadedProject, RuntimeIssue, RuntimeIssueReport
from app.packaging.config import resolve_project_package_config
from app.plugins.workflow_adapters import package_project_with_workflow
from app.plugins.workflow_broker import WorkflowBroker
from app.support.diagnostics import ProjectHealthReport, run_project_health_check
from app.support.runtime_explainer import (
    build_project_health_issue_report,
    build_startup_issue_report,
    merge_runtime_issue_reports,
)
from app.support.support_bundle import build_support_bundle
from app.shell.background_tasks import GeneralTaskScheduler
from app.shell.package_wizard_dialog import PackageProjectWizard


class RuntimeSupportWorkflow:
    """Owns project health, support bundle, and project packaging actions."""

    def __init__(
        self,
        *,
        parent: QWidget,
        state_root: str | None,
        background_tasks: GeneralTaskScheduler,
        workflow_broker: WorkflowBroker,
        loaded_project: Callable[[], LoadedProject | None],
        startup_report: Callable[[], CapabilityProbeReport | None],
        latest_health_report: Callable[[], ProjectHealthReport | None],
        set_latest_health_report: Callable[[ProjectHealthReport], None],
        latest_import_issue_report: Callable[[], RuntimeIssueReport],
        latest_run_issue_report: Callable[[], RuntimeIssueReport],
        latest_package_issue_report: Callable[[], RuntimeIssueReport],
        set_latest_package_issue_report: Callable[[RuntimeIssueReport], None],
        set_latest_runtime_issue_report: Callable[[RuntimeIssueReport], None],
        build_runtime_issue_report: Callable[[], RuntimeIssueReport],
        open_runtime_center_dialog: Callable[..., None],
        active_run_session_log_path: Callable[[], str | None],
        known_runtime_modules: Callable[[], frozenset[str] | None],
    ) -> None:
        self._parent = parent
        self._state_root = state_root
        self._background_tasks = background_tasks
        self._workflow_broker = workflow_broker
        self._loaded_project = loaded_project
        self._startup_report = startup_report
        self._latest_health_report = latest_health_report
        self._set_latest_health_report = set_latest_health_report
        self._latest_import_issue_report = latest_import_issue_report
        self._latest_run_issue_report = latest_run_issue_report
        self._latest_package_issue_report = latest_package_issue_report
        self._set_latest_package_issue_report = set_latest_package_issue_report
        self._set_latest_runtime_issue_report = set_latest_runtime_issue_report
        self._build_runtime_issue_report = build_runtime_issue_report
        self._open_runtime_center_dialog = open_runtime_center_dialog
        self._active_run_session_log_path = active_run_session_log_path
        self._known_runtime_modules = known_runtime_modules

    def handle_project_health_check_action(self) -> None:
        loaded_project = self._loaded_project()
        if loaded_project is None:
            QMessageBox.warning(self._parent, "Health check unavailable", "Open a project before running diagnostics.")
            return

        project_root = loaded_project.project_root
        state_root = self._state_root

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return run_project_health_check(project_root, state_root=state_root)

        def on_success(report) -> None:  # type: ignore[no-untyped-def]
            self._set_latest_health_report(report)
            self._set_latest_runtime_issue_report(self._build_runtime_issue_report())
            self._open_runtime_center_dialog(title="Project Health Check")

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self._parent, "Project health check", f"Health check failed: {exc}")

        self._background_tasks.run(key="project_health_check", task=task, on_success=on_success, on_error=on_error)

    def handle_generate_support_bundle_action(self) -> None:
        loaded_project = self._loaded_project()
        if loaded_project is None:
            QMessageBox.warning(self._parent, "Support bundle unavailable", "Open a project before generating support bundle.")
            return
        project_root = loaded_project.project_root
        state_root = self._state_root
        latest_run_log_path = self.resolve_latest_run_log_path()
        latest_report = self._latest_health_report()
        startup_report = self._startup_report()
        latest_import_issue_report = self._latest_import_issue_report()
        latest_run_issue_report = self._latest_run_issue_report()
        latest_package_issue_report = self._latest_package_issue_report()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            report = latest_report
            if report is None:
                report = run_project_health_check(project_root, state_root=state_root)
            reports_for_bundle = [
                build_startup_issue_report(startup_report)
                if startup_report is not None
                else RuntimeIssueReport(workflow="startup", issues=[]),
                build_project_health_issue_report(report),
            ]
            if latest_import_issue_report.issues:
                reports_for_bundle.append(latest_import_issue_report)
            if latest_run_issue_report.issues:
                reports_for_bundle.append(latest_run_issue_report)
            if latest_package_issue_report.issues:
                reports_for_bundle.append(latest_package_issue_report)
            runtime_issue_report = merge_runtime_issue_reports(
                *reports_for_bundle,
                workflow="runtime_center",
            )
            bundle_path = build_support_bundle(
                project_root,
                diagnostics_report=report,
                runtime_issue_report=runtime_issue_report,
                workflow_provider_metrics=self._workflow_broker.list_provider_metrics(),
                state_root=state_root,
                destination_dir=project_root,
                last_run_log_path=latest_run_log_path,
            )
            return (report, runtime_issue_report, bundle_path)

        def on_success(payload) -> None:  # type: ignore[no-untyped-def]
            report, runtime_issue_report, bundle_path = payload
            self._set_latest_health_report(report)
            self._set_latest_runtime_issue_report(runtime_issue_report)
            QMessageBox.information(self._parent, "Support bundle created", f"Bundle written to:\n{bundle_path}")

        def on_error(exc: Exception) -> None:
            QMessageBox.warning(self._parent, "Support bundle", f"Support bundle generation failed: {exc}")

        self._background_tasks.run(key="support_bundle", task=task, on_success=on_success, on_error=on_error)

    def handle_package_project_action(self) -> None:
        loaded_project = self._loaded_project()
        if loaded_project is None:
            QMessageBox.warning(self._parent, "Package unavailable", "Open a project before packaging.")
            return
        project_root = loaded_project.project_root
        project_metadata = loaded_project.metadata
        try:
            package_config = resolve_project_package_config(
                project_root=project_root,
                project_metadata=project_metadata,
            )
        except Exception as exc:
            QMessageBox.warning(
                self._parent,
                "Package Project",
                f"Unable to load cbcs/package.json:\n{exc}",
            )
            return
        wizard = PackageProjectWizard(
            project_root=project_root,
            project_metadata=project_metadata,
            package_config=package_config,
            parent=self._parent,
        )
        if wizard.exec_() != QDialog.Accepted:
            return
        output_dir = wizard.output_dir
        selected_profile = wizard.selected_profile
        reviewed_package_config = wizard.build_package_config()

        def task(_cancel_event) -> object:  # type: ignore[no-untyped-def]
            return package_project_with_workflow(
                self._workflow_broker,
                project_root=project_root,
                project_name=project_metadata.name,
                entry_file=project_metadata.default_entry,
                output_dir=output_dir,
                profile=selected_profile,
                package_config=reviewed_package_config.to_dict(),
                project_metadata=project_metadata.to_dict(),
                known_runtime_modules=self._known_runtime_modules(),
            )

        def on_success(result) -> None:  # type: ignore[no-untyped-def]
            provider, result = result
            self._set_latest_package_issue_report(result.validation.issue_report)
            self._set_latest_runtime_issue_report(self._build_runtime_issue_report())
            if result.success:
                QMessageBox.information(
                    self._parent,
                    "Package created",
                    f"Project packaged via {provider.title} to:\n{result.artifact_root}\n\n"
                    f"Generated files:\n"
                    f"- package_manifest.json\n"
                    f"- package_report.json\n"
                    f"- {Path(result.readme_path).name}\n"
                    f"- {Path(result.install_notes_path).name}\n"
                    + (
                        f"- {Path(result.launcher_path).name}\n"
                        if result.launcher_path
                        else ""
                    ),
                )
                if result.validation.issue_report.issues:
                    self._open_runtime_center_dialog(
                        title="Packaging Report",
                        report=result.validation.issue_report,
                    )
            else:
                latest_package_issue_report = result.validation.issue_report
                if not latest_package_issue_report.issues:
                    latest_package_issue_report = RuntimeIssueReport(
                        workflow="package",
                        issues=[
                            RuntimeIssue(
                                issue_id="package.export_failed",
                                workflow="package",
                                severity="blocking",
                                title="Packaging failed",
                                summary=result.error or "Packaging failed unexpectedly.",
                                why_it_happened=(
                                    "The export step encountered a filesystem or packaging problem after the initial validation checks."
                                ),
                                next_steps=[
                                    "Review the packaging error details.",
                                    "Choose a different output location if the destination may be restricted or stale.",
                                    "Re-run packaging after fixing the reported issue.",
                                ],
                                help_topic="packaging_backup",
                                evidence={
                                    "artifact_root": result.artifact_root,
                                    "profile": result.profile,
                                },
                            )
                        ],
                    )
                    self._set_latest_package_issue_report(latest_package_issue_report)
                    self._set_latest_runtime_issue_report(self._build_runtime_issue_report())
                self._open_runtime_center_dialog(
                    title="Packaging Failed",
                    report=latest_package_issue_report,
                )

        def on_error(exc: Exception) -> None:
            latest_package_issue_report = RuntimeIssueReport(
                workflow="package",
                issues=[
                    RuntimeIssue(
                        issue_id="package.export_exception",
                        workflow="package",
                        severity="blocking",
                        title="Packaging failed unexpectedly",
                        summary=str(exc),
                        why_it_happened="The packaging workflow raised an unexpected exception before it could finish cleanly.",
                        next_steps=[
                            "Review the error details and retry packaging.",
                            "Choose a different output location if the destination may be restricted.",
                            "Generate a support bundle if the error persists.",
                        ],
                        help_topic="packaging_backup",
                        evidence={"project_root": project_root, "output_dir": output_dir},
                    )
                ],
            )
            self._set_latest_package_issue_report(latest_package_issue_report)
            self._set_latest_runtime_issue_report(self._build_runtime_issue_report())
            self._open_runtime_center_dialog(
                title="Packaging Failed",
                report=latest_package_issue_report,
            )

        self._background_tasks.run(key="package_project", task=task, on_success=on_success, on_error=on_error)

    def resolve_latest_run_log_path(self) -> str | None:
        active_log = self._active_run_session_log_path()
        if active_log and Path(active_log).exists():
            return active_log
        loaded_project = self._loaded_project()
        if loaded_project is None:
            return None
        log_dir = project_logs_dir(loaded_project.project_root)
        if not log_dir.exists():
            return None
        candidate_logs = sorted(log_dir.glob("run_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not candidate_logs:
            return None
        return str(candidate_logs[0].resolve())
