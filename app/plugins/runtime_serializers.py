from __future__ import annotations

from typing import Any

from app.core.models import CapabilityProbeReport, RuntimeIssue, RuntimeIssueReport
from app.intelligence.diagnostics_service import CodeDiagnostic
from app.packaging.packager import PackageResult
from app.packaging.models import DependencyAuditReport
from app.python_tools.models import PythonTextTransformResult
from app.run.problem_parser import ProblemEntry
from app.run.pytest_runner_service import PytestRunResult
from app.support.diagnostics import ProjectHealthReport
from app.templates.template_service import TemplateMetadata


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


def serialize_problem_entry(entry: ProblemEntry) -> dict[str, Any]:
    return {
        "file_path": entry.file_path,
        "line_number": entry.line_number,
        "context": entry.context,
        "message": entry.message,
    }


def serialize_package_result(result: PackageResult) -> dict[str, Any]:
    return result.to_dict()


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


def serialize_runtime_issue_result(result: RuntimeIssueReport | list[RuntimeIssue]) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(result, RuntimeIssueReport):
        return result.to_dict()
    return [item.to_dict() for item in result]


def serialize_capability_probe_report(report: CapabilityProbeReport) -> dict[str, Any]:
    return report.to_dict()


def serialize_project_health_report(report: ProjectHealthReport) -> dict[str, Any]:
    return report.to_dict()
