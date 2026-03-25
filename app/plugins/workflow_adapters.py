from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.core import constants
from app.core.models import RuntimeIssue, RuntimeIssueReport, WorkflowPreflightResult
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity
from app.packaging.packager import PackageResult
from app.packaging.models import DependencyAuditRecord, DependencyAuditReport, PackageValidationReport
from app.plugins.workflow_broker import WorkflowBroker, WorkflowProviderDescriptor
from app.python_tools.models import PythonTextTransformResult, PythonToolingSettings
from app.run.problem_parser import ProblemEntry
from app.run.test_runner_service import PytestRunResult
from app.templates.template_service import TemplateMetadata


def format_python_with_workflow(
    broker: WorkflowBroker,
    *,
    source_text: str,
    file_path: str,
    project_root: str,
    preferred_provider_key: str | None = None,
) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        request={
            "source_text": source_text,
            "file_path": file_path,
            "project_root": project_root,
        },
        language="python",
        file_path=file_path,
        preferred_provider_key=preferred_provider_key,
    )
    return descriptor, _coerce_python_text_transform_result(result, file_path=file_path, project_root=project_root)


def organize_imports_with_workflow(
    broker: WorkflowBroker,
    *,
    source_text: str,
    file_path: str,
    project_root: str,
    preferred_provider_key: str | None = None,
) -> tuple[WorkflowProviderDescriptor, PythonTextTransformResult]:
    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_IMPORT_ORGANIZER,
        request={
            "source_text": source_text,
            "file_path": file_path,
            "project_root": project_root,
        },
        language="python",
        file_path=file_path,
        preferred_provider_key=preferred_provider_key,
    )
    return descriptor, _coerce_python_text_transform_result(result, file_path=file_path, project_root=project_root)


def analyze_python_with_workflow(
    broker: WorkflowBroker,
    *,
    file_path: str,
    project_root: str | None = None,
    source: str | None = None,
    known_runtime_modules: frozenset[str] | None = None,
    allow_runtime_import_probe: bool = False,
    selected_linter: str = constants.LINTER_PROVIDER_DEFAULT,
    lint_rule_overrides: Mapping[str, Mapping[str, Any]] | None = None,
    preferred_provider_key: str | None = None,
) -> tuple[WorkflowProviderDescriptor, list[CodeDiagnostic]]:
    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_DIAGNOSTICS,
        request={
            "file_path": file_path,
            "project_root": project_root,
            "source": source,
            "known_runtime_modules": sorted(known_runtime_modules or ()),
            "allow_runtime_import_probe": allow_runtime_import_probe,
            "selected_linter": selected_linter,
            "lint_rule_overrides": dict(lint_rule_overrides or {}),
        },
        language="python",
        file_path=file_path,
        preferred_provider_key=preferred_provider_key,
    )
    return descriptor, _coerce_code_diagnostics(result)


def run_pytest_with_workflow(
    broker: WorkflowBroker,
    *,
    project_root: str,
    target_path: str | None = None,
    timeout_seconds: int = 300,
    preferred_provider_key: str | None = None,
    on_event=None,
) -> tuple[WorkflowProviderDescriptor, PytestRunResult]:
    descriptor, result = broker.run_job(
        kind=constants.WORKFLOW_PROVIDER_KIND_TEST,
        request={
            "project_root": project_root,
            "target_path": target_path,
            "timeout_seconds": timeout_seconds,
        },
        preferred_provider_key=preferred_provider_key,
        on_event=on_event,
        timeout_seconds=float(timeout_seconds) + 5.0,
    )
    return descriptor, _coerce_pytest_run_result(result)


def package_project_with_workflow(
    broker: WorkflowBroker,
    *,
    project_root: str,
    project_name: str,
    entry_file: str,
    output_dir: str,
    profile: str,
    package_config: Mapping[str, Any],
    project_metadata: Mapping[str, Any],
    known_runtime_modules: frozenset[str] | None = None,
    preferred_provider_key: str | None = None,
    on_event=None,
) -> tuple[WorkflowProviderDescriptor, PackageResult]:
    descriptor, result = broker.run_job(
        kind=constants.WORKFLOW_PROVIDER_KIND_PACKAGING,
        request={
            "project_root": project_root,
            "project_name": project_name,
            "entry_file": entry_file,
            "output_dir": output_dir,
            "profile": profile,
            "package_config": dict(package_config),
            "project_metadata": dict(project_metadata),
            "known_runtime_modules": sorted(known_runtime_modules or ()),
        },
        preferred_provider_key=preferred_provider_key,
        on_event=on_event,
    )
    return descriptor, _coerce_package_result(result)


def list_templates_with_workflow(
    broker: WorkflowBroker,
    *,
    preferred_provider_key: str | None = None,
) -> tuple[WorkflowProviderDescriptor, list[TemplateMetadata]]:
    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_TEMPLATE,
        request={},
        preferred_provider_key=preferred_provider_key,
    )
    return descriptor, _coerce_template_metadata(result)


def explain_runtime_with_workflow(
    broker: WorkflowBroker,
    *,
    mode: str,
    payload: Mapping[str, Any],
    preferred_provider_key: str | None = None,
) -> tuple[WorkflowProviderDescriptor, RuntimeIssueReport | list[RuntimeIssue]]:
    request = {"mode": mode}
    request.update(dict(payload))
    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_RUNTIME_EXPLAINER,
        request=request,
        preferred_provider_key=preferred_provider_key,
    )
    return descriptor, _coerce_runtime_result(result)


def _coerce_python_text_transform_result(
    raw_value: Any,
    *,
    file_path: str,
    project_root: str,
) -> PythonTextTransformResult:
    if isinstance(raw_value, PythonTextTransformResult):
        return raw_value
    if not isinstance(raw_value, dict):
        raise TypeError("Workflow formatter result must be a PythonTextTransformResult or dict.")
    settings_payload = raw_value.get("settings", {})
    return PythonTextTransformResult(
        formatted_text=_require_string(raw_value, "formatted_text"),
        changed=bool(raw_value.get("changed", False)),
        status=_require_string(raw_value, "status"),
        settings=_coerce_python_tooling_settings(
            settings_payload,
            file_path=file_path,
            project_root=project_root,
        ),
        error_message=_optional_string(raw_value, "error_message"),
    )


def _coerce_python_tooling_settings(
    raw_value: Any,
    *,
    file_path: str,
    project_root: str,
) -> PythonToolingSettings:
    if isinstance(raw_value, PythonToolingSettings):
        return raw_value
    payload = raw_value if isinstance(raw_value, dict) else {}
    return PythonToolingSettings(
        project_root=Path(_optional_string(payload, "project_root") or project_root).expanduser().resolve(),
        file_path=Path(_optional_string(payload, "file_path") or file_path).expanduser().resolve(),
        pyproject_path=(
            Path(payload["pyproject_path"]).expanduser().resolve()
            if isinstance(payload.get("pyproject_path"), str) and payload.get("pyproject_path")
            else None
        ),
        config_source=_optional_string(payload, "config_source") or "defaults",
        config_error=_optional_string(payload, "config_error"),
        python_target_minor=int(payload.get("python_target_minor", 39)),
        black_line_length=int(payload.get("black_line_length", 88)),
        black_target_versions=tuple(payload.get("black_target_versions", [])) if isinstance(payload.get("black_target_versions", []), list) else tuple(),
        black_string_normalization=bool(payload.get("black_string_normalization", True)),
        black_magic_trailing_comma=bool(payload.get("black_magic_trailing_comma", True)),
        black_preview=bool(payload.get("black_preview", False)),
        isort_profile=_optional_string(payload, "isort_profile") or "black",
        isort_line_length=int(payload.get("isort_line_length", 88)),
        isort_src_paths=tuple(
            Path(item).expanduser().resolve()
            for item in payload.get("isort_src_paths", [])
            if isinstance(item, str) and item.strip()
        ),
        isort_known_first_party=tuple(
            item
            for item in payload.get("isort_known_first_party", [])
            if isinstance(item, str) and item.strip()
        ),
    )


def _coerce_code_diagnostics(raw_value: Any) -> list[CodeDiagnostic]:
    if isinstance(raw_value, list) and all(isinstance(item, CodeDiagnostic) for item in raw_value):
        return list(raw_value)
    if not isinstance(raw_value, list):
        raise TypeError("Workflow diagnostics result must be a list.")
    diagnostics: list[CodeDiagnostic] = []
    for item in raw_value:
        if isinstance(item, CodeDiagnostic):
            diagnostics.append(item)
            continue
        if not isinstance(item, dict):
            continue
        severity_text = _optional_string(item, "severity") or DiagnosticSeverity.ERROR.value
        diagnostics.append(
            CodeDiagnostic(
                code=_require_string(item, "code"),
                severity=DiagnosticSeverity(severity_text),
                file_path=_require_string(item, "file_path"),
                line_number=int(item.get("line_number", 1)),
                message=_require_string(item, "message"),
                col_start=_optional_int(item, "col_start"),
                col_end=_optional_int(item, "col_end"),
            )
        )
    return diagnostics


def _coerce_pytest_run_result(raw_value: Any) -> PytestRunResult:
    if isinstance(raw_value, PytestRunResult):
        return raw_value
    if not isinstance(raw_value, dict):
        raise TypeError("Workflow pytest result must be a PytestRunResult or dict.")
    failures: list[ProblemEntry] = []
    for item in raw_value.get("failures", []):
        if isinstance(item, ProblemEntry):
            failures.append(item)
            continue
        if not isinstance(item, dict):
            continue
        failures.append(
            ProblemEntry(
                file_path=_require_string(item, "file_path"),
                line_number=int(item.get("line_number", 1)),
                context=_optional_string(item, "context") or "pytest",
                message=_require_string(item, "message"),
            )
        )
    command_payload = raw_value.get("command", [])
    command = [item for item in command_payload if isinstance(item, str)]
    return PytestRunResult(
        command=command,
        project_root=_require_string(raw_value, "project_root"),
        return_code=int(raw_value.get("return_code", 1)),
        stdout=_optional_string(raw_value, "stdout") or "",
        stderr=_optional_string(raw_value, "stderr") or "",
        elapsed_ms=float(raw_value.get("elapsed_ms", 0.0)),
        failures=failures,
    )


def _coerce_package_result(raw_value: Any) -> PackageResult:
    if isinstance(raw_value, PackageResult):
        return raw_value
    if not isinstance(raw_value, dict):
        raise TypeError("Workflow packaging result must be a PackageResult or dict.")
    validation_payload = raw_value.get("validation", {})
    validation = _coerce_package_validation_report(validation_payload)
    return PackageResult(
        profile=_optional_string(raw_value, "profile") or validation.profile,
        success=bool(raw_value.get("success", False)),
        artifact_root=_optional_string(raw_value, "artifact_root") or "",
        manifest_path=_optional_string(raw_value, "manifest_path") or "",
        report_path=_optional_string(raw_value, "report_path") or "",
        readme_path=_optional_string(raw_value, "readme_path") or "",
        install_notes_path=_optional_string(raw_value, "install_notes_path") or "",
        launcher_path=_optional_string(raw_value, "launcher_path"),
        validation=validation,
        error=_optional_string(raw_value, "error"),
    )


def _coerce_template_metadata(raw_value: Any) -> list[TemplateMetadata]:
    if isinstance(raw_value, list) and all(isinstance(item, TemplateMetadata) for item in raw_value):
        return list(raw_value)
    if not isinstance(raw_value, list):
        raise TypeError("Workflow template result must be a list.")
    templates: list[TemplateMetadata] = []
    for item in raw_value:
        if isinstance(item, TemplateMetadata):
            templates.append(item)
            continue
        if not isinstance(item, dict):
            continue
        templates.append(
            TemplateMetadata(
                template_id=_require_string(item, "template_id"),
                display_name=_require_string(item, "display_name"),
                description=_require_string(item, "description"),
                template_version=int(item.get("template_version", 1)),
                source_path=_require_string(item, "source_path"),
            )
        )
    return templates


def _coerce_runtime_result(raw_value: Any) -> RuntimeIssueReport | list[RuntimeIssue]:
    if isinstance(raw_value, RuntimeIssueReport):
        return raw_value
    if isinstance(raw_value, list) and all(isinstance(item, RuntimeIssue) for item in raw_value):
        return list(raw_value)
    if not isinstance(raw_value, dict):
        raise TypeError("Workflow runtime explanation result must be a RuntimeIssueReport or dict.")
    if "issues" in raw_value:
        issues_payload = raw_value.get("issues", [])
        issues = _coerce_runtime_issue_list(issues_payload)
        return RuntimeIssueReport(
            workflow=_optional_string(raw_value, "workflow") or "general",
            issues=issues,
        )
    return _coerce_runtime_issue_list(raw_value.get("issues", []))


def _coerce_runtime_issue_list(raw_value: Any) -> list[RuntimeIssue]:
    if not isinstance(raw_value, list):
        return []
    issues: list[RuntimeIssue] = []
    for item in raw_value:
        if isinstance(item, RuntimeIssue):
            issues.append(item)
            continue
        if not isinstance(item, dict):
            continue
        issues.append(
            RuntimeIssue(
                issue_id=_require_string(item, "issue_id"),
                workflow=_require_string(item, "workflow"),
                severity=_require_string(item, "severity"),
                title=_require_string(item, "title"),
                summary=_require_string(item, "summary"),
                why_it_happened=_require_string(item, "why_it_happened"),
                next_steps=list(item.get("next_steps", [])) if isinstance(item.get("next_steps", []), list) else [],
                help_topic=_optional_string(item, "help_topic"),
                evidence=dict(item.get("evidence", {})) if isinstance(item.get("evidence", {}), dict) else {},
            )
        )
    return issues


def _coerce_package_validation_report(raw_value: Any) -> PackageValidationReport:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return PackageValidationReport(
        profile=_optional_string(payload, "profile") or "installable",
        preflight=_coerce_workflow_preflight_result(payload.get("preflight")),
        dependency_audit=_coerce_dependency_audit_report(payload.get("dependency_audit")),
        issue_report=_coerce_runtime_issue_report(payload.get("issue_report")),
    )


def _coerce_workflow_preflight_result(raw_value: Any) -> WorkflowPreflightResult:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return WorkflowPreflightResult(
        workflow=_optional_string(payload, "workflow") or "package",
        issues=_coerce_runtime_issue_list(payload.get("issues")),
        summary=_optional_string(payload, "summary") or "",
    )


def _coerce_dependency_audit_report(raw_value: Any) -> DependencyAuditReport:
    payload = raw_value if isinstance(raw_value, dict) else {}
    records: list[DependencyAuditRecord] = []
    for item in payload.get("records", []) if isinstance(payload.get("records", []), list) else []:
        if not isinstance(item, dict):
            continue
        records.append(
            DependencyAuditRecord(
                source_file=_require_string(item, "source_file"),
                line_number=int(item.get("line_number", 1)),
                module_name=_require_string(item, "module_name"),
                classification=_require_string(item, "classification"),
                resolved_path=_optional_string(item, "resolved_path"),
                detail=_optional_string(item, "detail") or "",
            )
        )
    return DependencyAuditReport(
        project_root=_optional_string(payload, "project_root") or "",
        records=records,
        issues=_coerce_runtime_issue_list(payload.get("issues")),
        summary=_optional_string(payload, "summary") or "",
    )


def _coerce_runtime_issue_report(raw_value: Any) -> RuntimeIssueReport:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return RuntimeIssueReport(
        workflow=_optional_string(payload, "workflow") or "general",
        issues=_coerce_runtime_issue_list(payload.get("issues")),
    )


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_int(payload: Mapping[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, int):
        return value
    return None
