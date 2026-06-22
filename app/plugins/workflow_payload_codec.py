from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.core.models import CapabilityProbeReport, RuntimeIssue, RuntimeIssueReport, WorkflowPreflightResult
from app.intelligence.diagnostics_service import CodeDiagnostic, DiagnosticSeverity
from app.packaging.models import DependencyAuditRecord, DependencyAuditReport, PackageValidationReport
from app.packaging.packager import PackageResult
from app.python_tools.models import PythonTextTransformResult, PythonToolingSettings
from app.run.problem_parser import ProblemEntry
from app.pytest.runner_service import PytestRunResult
from app.support.diagnostics import ProjectHealthReport
from app.templates.template_service import TemplateMetadata

WorkflowIpcPayload = object


def serialize_python_text_transform_result(result: PythonTextTransformResult) -> dict[str, Any]:
    return {
        "formatted_text": result.formatted_text,
        "changed": result.changed,
        "status": result.status,
        "settings": {
            "project_root": str(result.settings.project_root),
            "file_path": str(result.settings.file_path),
            "pyproject_path": None if result.settings.pyproject_path is None else str(result.settings.pyproject_path),
            "config_source": result.settings.config_source,
            "config_error": result.settings.config_error,
            "python_target_minor": result.settings.python_target_minor,
            "black_line_length": result.settings.black_line_length,
            "black_target_versions": list(result.settings.black_target_versions),
            "black_string_normalization": result.settings.black_string_normalization,
            "black_magic_trailing_comma": result.settings.black_magic_trailing_comma,
            "black_preview": result.settings.black_preview,
            "isort_profile": result.settings.isort_profile,
            "isort_line_length": result.settings.isort_line_length,
            "isort_src_paths": [str(item) for item in result.settings.isort_src_paths],
            "isort_known_first_party": list(result.settings.isort_known_first_party),
        },
        "error_message": result.error_message,
    }


def parse_python_text_transform_result(
    raw_value: WorkflowIpcPayload,
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
        settings=_parse_python_tooling_settings(
            settings_payload,
            file_path=file_path,
            project_root=project_root,
        ),
        error_message=_optional_string(raw_value, "error_message"),
    )


def serialize_code_diagnostics(diagnostics: list[CodeDiagnostic]) -> list[dict[str, Any]]:
    return [
        {
            "code": item.code,
            "severity": item.severity.value,
            "file_path": item.file_path,
            "line_number": item.line_number,
            "message": item.message,
            "col_start": item.col_start,
            "col_end": item.col_end,
        }
        for item in diagnostics
    ]


def parse_code_diagnostics(raw_value: WorkflowIpcPayload) -> list[CodeDiagnostic]:
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


def serialize_pytest_run_result(result: PytestRunResult) -> dict[str, Any]:
    return {
        "command": list(result.command),
        "project_root": result.project_root,
        "return_code": result.return_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed_ms": result.elapsed_ms,
        "failures": [serialize_problem_entry(item) for item in result.failures],
    }


def parse_pytest_run_result(raw_value: WorkflowIpcPayload) -> PytestRunResult:
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
        failures.append(parse_problem_entry(item))
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


def serialize_problem_entry(entry: ProblemEntry) -> dict[str, Any]:
    return {
        "file_path": entry.file_path,
        "line_number": entry.line_number,
        "context": entry.context,
        "message": entry.message,
    }


def parse_problem_entry(raw_value: Mapping[str, Any]) -> ProblemEntry:
    return ProblemEntry(
        file_path=_require_string(raw_value, "file_path"),
        line_number=int(raw_value.get("line_number", 1)),
        context=_optional_string(raw_value, "context") or "pytest",
        message=_require_string(raw_value, "message"),
    )


def serialize_package_result(result: PackageResult) -> dict[str, Any]:
    return result.to_dict()


def parse_package_result(raw_value: WorkflowIpcPayload) -> PackageResult:
    if isinstance(raw_value, PackageResult):
        return raw_value
    if not isinstance(raw_value, dict):
        raise TypeError("Workflow packaging result must be a PackageResult or dict.")
    validation_payload = raw_value.get("validation", {})
    validation = _parse_package_validation_report(validation_payload)
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


def serialize_dependency_audit_report(report: DependencyAuditReport) -> dict[str, Any]:
    return report.to_dict()


def serialize_templates(templates: list[TemplateMetadata]) -> list[dict[str, Any]]:
    return [
        {
            "template_id": item.template_id,
            "display_name": item.display_name,
            "description": item.description,
            "template_version": item.template_version,
            "source_path": item.source_path,
        }
        for item in templates
    ]


def parse_template_metadata(raw_value: WorkflowIpcPayload) -> list[TemplateMetadata]:
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


def serialize_runtime_issue_result(
    result: RuntimeIssueReport | list[RuntimeIssue],
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(result, RuntimeIssueReport):
        return result.to_dict()
    return [item.to_dict() for item in result]


def parse_runtime_result(raw_value: WorkflowIpcPayload) -> RuntimeIssueReport | list[RuntimeIssue]:
    if isinstance(raw_value, RuntimeIssueReport):
        return raw_value
    if isinstance(raw_value, list) and all(isinstance(item, RuntimeIssue) for item in raw_value):
        return list(raw_value)
    if not isinstance(raw_value, dict):
        raise TypeError("Workflow runtime explanation result must be a RuntimeIssueReport or dict.")
    if "issues" in raw_value:
        issues_payload = raw_value.get("issues", [])
        issues = _parse_runtime_issue_list(issues_payload)
        return RuntimeIssueReport(
            workflow=_optional_string(raw_value, "workflow") or "general",
            issues=issues,
        )
    return _parse_runtime_issue_list(raw_value.get("issues", []))


def serialize_capability_probe_report(report: CapabilityProbeReport) -> dict[str, Any]:
    return report.to_dict()


def serialize_project_health_report(report: ProjectHealthReport) -> dict[str, Any]:
    return report.to_dict()


def _parse_python_tooling_settings(
    raw_value: WorkflowIpcPayload,
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
        black_target_versions=tuple(payload.get("black_target_versions", []))
        if isinstance(payload.get("black_target_versions", []), list)
        else tuple(),
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


def _parse_runtime_issue_list(raw_value: WorkflowIpcPayload) -> list[RuntimeIssue]:
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


def _parse_package_validation_report(raw_value: WorkflowIpcPayload) -> PackageValidationReport:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return PackageValidationReport(
        profile=_optional_string(payload, "profile") or "installable",
        preflight=_parse_workflow_preflight_result(payload.get("preflight")),
        dependency_audit=_parse_dependency_audit_report(payload.get("dependency_audit")),
        issue_report=_parse_runtime_issue_report(payload.get("issue_report")),
    )


def _parse_workflow_preflight_result(raw_value: WorkflowIpcPayload) -> WorkflowPreflightResult:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return WorkflowPreflightResult(
        workflow=_optional_string(payload, "workflow") or "package",
        issues=_parse_runtime_issue_list(payload.get("issues")),
        summary=_optional_string(payload, "summary") or "",
    )


def _parse_dependency_audit_report(raw_value: WorkflowIpcPayload) -> DependencyAuditReport:
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
        issues=_parse_runtime_issue_list(payload.get("issues")),
        summary=_optional_string(payload, "summary") or "",
    )


def _parse_runtime_issue_report(raw_value: WorkflowIpcPayload) -> RuntimeIssueReport:
    payload = raw_value if isinstance(raw_value, dict) else {}
    return RuntimeIssueReport(
        workflow=_optional_string(payload, "workflow") or "general",
        issues=_parse_runtime_issue_list(payload.get("issues")),
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
