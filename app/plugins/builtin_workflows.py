from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from app.core import constants
from app.core.models import CapabilityCheckResult, CapabilityProbeReport, ProjectMetadata, RuntimeIssue, RuntimeIssueReport
from app.intelligence.diagnostics_service import CodeDiagnostic, ImportDiagnostic, analyze_python_file
from app.packaging.config import ProjectPackageConfig, parse_project_package_config
from app.packaging.packager import PackageResult, package_project
from app.plugins.workflow_broker import WorkflowBroker
from app.python_tools.black_adapter import format_python_text
from app.python_tools.isort_adapter import organize_imports_text
from app.python_tools.models import PythonTextTransformResult
from app.run.problem_parser import ProblemEntry
from app.run.test_runner_service import (
    PytestRunResult,
    run_pytest_project,
    run_pytest_target,
)
from app.support.diagnostics import DiagnosticItem, ProjectHealthReport
from app.support.runtime_explainer import (
    build_import_issue_report,
    build_project_health_issue_report,
    build_startup_issue_report,
    explain_runtime_message,
)
from app.templates.template_service import TemplateMetadata, TemplateService


def register_builtin_workflow_providers(
    broker: WorkflowBroker,
    *,
    template_service: TemplateService,
) -> None:
    broker.register_builtin_query_provider(
        provider_key="builtin:formatter",
        kind=constants.WORKFLOW_PROVIDER_KIND_FORMATTER,
        title="Built-in Python Formatter",
        languages=("python",),
        file_extensions=(".py", ".pyi", ".pyw", ".fcmacro"),
        handler=_run_builtin_formatter_query,
    )
    broker.register_builtin_query_provider(
        provider_key="builtin:import_organizer",
        kind=constants.WORKFLOW_PROVIDER_KIND_IMPORT_ORGANIZER,
        title="Built-in Python Import Organizer",
        languages=("python",),
        file_extensions=(".py", ".pyi", ".pyw", ".fcmacro"),
        handler=_run_builtin_import_query,
    )
    broker.register_builtin_query_provider(
        provider_key="builtin:diagnostics",
        kind=constants.WORKFLOW_PROVIDER_KIND_DIAGNOSTICS,
        title="Built-in Python Diagnostics",
        languages=("python",),
        file_extensions=(".py", ".pyi", ".pyw", ".fcmacro"),
        handler=_run_builtin_diagnostics_query,
    )
    broker.register_builtin_query_provider(
        provider_key="builtin:templates",
        kind=constants.WORKFLOW_PROVIDER_KIND_TEMPLATE,
        title="Built-in Templates",
        handler=lambda request: _run_builtin_templates_query(request, template_service=template_service),
    )
    broker.register_builtin_query_provider(
        provider_key="builtin:runtime_explainer",
        kind=constants.WORKFLOW_PROVIDER_KIND_RUNTIME_EXPLAINER,
        title="Built-in Runtime Explainer",
        handler=_run_builtin_runtime_explainer_query,
    )
    broker.register_builtin_job_provider(
        provider_key="builtin:pytest",
        kind=constants.WORKFLOW_PROVIDER_KIND_TEST,
        title="Built-in Pytest Runner",
        handler=_run_builtin_pytest_job,
    )
    broker.register_builtin_job_provider(
        provider_key="builtin:packaging",
        kind=constants.WORKFLOW_PROVIDER_KIND_PACKAGING,
        title="Built-in Packager",
        handler=_run_builtin_packaging_job,
    )


def _run_builtin_formatter_query(request: Mapping[str, Any]) -> PythonTextTransformResult:
    return format_python_text(
        _require_string(request, "source_text"),
        file_path=_require_string(request, "file_path"),
        project_root=_require_string(request, "project_root"),
    )


def _run_builtin_import_query(request: Mapping[str, Any]) -> PythonTextTransformResult:
    return organize_imports_text(
        _require_string(request, "source_text"),
        file_path=_require_string(request, "file_path"),
        project_root=_require_string(request, "project_root"),
    )


def _run_builtin_diagnostics_query(request: Mapping[str, Any]) -> list[CodeDiagnostic]:
    known_runtime_modules_payload = request.get("known_runtime_modules", [])
    known_runtime_modules = (
        frozenset(
            item
            for item in known_runtime_modules_payload
            if isinstance(item, str) and item.strip()
        )
        if isinstance(known_runtime_modules_payload, list)
        else None
    )
    return analyze_python_file(
        _require_string(request, "file_path"),
        project_root=_optional_string(request, "project_root"),
        source=_optional_string(request, "source"),
        known_runtime_modules=known_runtime_modules,
        allow_runtime_import_probe=bool(request.get("allow_runtime_import_probe", False)),
        selected_linter=_optional_string(request, "selected_linter") or constants.LINTER_PROVIDER_DEFAULT,
        lint_rule_overrides=_mapping_value(request, "lint_rule_overrides"),
    )


def _run_builtin_templates_query(
    request: Mapping[str, Any],
    *,
    template_service: TemplateService,
) -> list[TemplateMetadata]:
    _ = request
    return template_service.list_templates()


def _run_builtin_runtime_explainer_query(request: Mapping[str, Any]) -> RuntimeIssueReport | list[RuntimeIssue]:
    mode = _optional_string(request, "mode") or "message"
    if mode == "startup":
        return build_startup_issue_report(_parse_capability_probe_report(request.get("report")))
    if mode == "project":
        return build_project_health_issue_report(_parse_project_health_report(request.get("report")))
    if mode == "imports":
        return build_import_issue_report(
            _require_string(request, "project_root"),
            _parse_import_diagnostics(request.get("diagnostics")),
            known_runtime_modules=None,
            allow_runtime_import_probe=bool(request.get("allow_runtime_import_probe", False)),
        )
    return explain_runtime_message(_require_string(request, "message_text"))


def _run_builtin_pytest_job(
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    _ = is_cancelled
    project_root = _require_string(request, "project_root")
    target_path = _optional_string(request, "target_path")
    timeout_seconds = int(request.get("timeout_seconds", 300))
    emit_event("job_started", {"project_root": project_root, "target_path": target_path})
    result = (
        run_pytest_target(project_root, target_path, timeout_seconds=timeout_seconds)
        if target_path
        else run_pytest_project(project_root, timeout_seconds=timeout_seconds)
    )
    emit_event(
        "job_finished",
        {
            "return_code": result.return_code,
            "failure_count": len(result.failures),
            "elapsed_ms": result.elapsed_ms,
        },
    )
    return _pytest_run_result_to_dict(result)


def _run_builtin_packaging_job(
    request: Mapping[str, Any],
    emit_event,
    is_cancelled,
) -> dict[str, Any]:
    _ = is_cancelled
    emit_event("job_started", {"project_root": _require_string(request, "project_root")})
    package_config = _parse_project_package_config(request.get("package_config"))
    project_metadata = _parse_project_metadata(request.get("project_metadata"))
    known_runtime_modules_payload = request.get("known_runtime_modules", [])
    known_runtime_modules = (
        frozenset(
            item
            for item in known_runtime_modules_payload
            if isinstance(item, str) and item.strip()
        )
        if isinstance(known_runtime_modules_payload, list)
        else None
    )
    result = package_project(
        project_root=_require_string(request, "project_root"),
        project_name=_require_string(request, "project_name"),
        entry_file=_require_string(request, "entry_file"),
        output_dir=_require_string(request, "output_dir"),
        profile=_optional_string(request, "profile") or "installable",
        package_config=package_config,
        project_metadata=project_metadata,
        known_runtime_modules=known_runtime_modules,
    )
    emit_event("job_finished", {"success": result.success, "artifact_root": result.artifact_root})
    return result.to_dict()


def _pytest_run_result_to_dict(result: PytestRunResult) -> dict[str, Any]:
    return {
        "command": list(result.command),
        "project_root": result.project_root,
        "return_code": result.return_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed_ms": result.elapsed_ms,
        "failures": [_problem_entry_to_dict(item) for item in result.failures],
    }


def _package_result_to_dict(result: PackageResult) -> dict[str, Any]:
    return result.to_dict()


def _problem_entry_to_dict(entry: ProblemEntry) -> dict[str, Any]:
    return {
        "file_path": entry.file_path,
        "line_number": entry.line_number,
        "context": entry.context,
        "message": entry.message,
    }


def _parse_capability_probe_report(raw_value: Any) -> CapabilityProbeReport:
    checks_payload = raw_value.get("checks", []) if isinstance(raw_value, dict) else []
    checks: list[CapabilityCheckResult] = []
    for item in checks_payload:
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        is_available = item.get("is_available")
        message = item.get("message")
        details = item.get("details", {})
        if not isinstance(check_id, str) or not isinstance(message, str):
            continue
        checks.append(
            CapabilityCheckResult(
                check_id=check_id,
                is_available=bool(is_available),
                message=message,
                details=dict(details) if isinstance(details, dict) else {},
            )
        )
    return CapabilityProbeReport(checks=checks)


def _parse_project_health_report(raw_value: Any) -> ProjectHealthReport:
    if not isinstance(raw_value, dict):
        return ProjectHealthReport(project_root="", checks=[])
    checks_payload = raw_value.get("checks", [])
    checks: list[DiagnosticItem] = []
    for item in checks_payload:
        if not isinstance(item, dict):
            continue
        check_id = item.get("check_id")
        message = item.get("message")
        details = item.get("details", {})
        if not isinstance(check_id, str) or not isinstance(message, str):
            continue
        checks.append(
            DiagnosticItem(
                check_id=check_id,
                is_ok=bool(item.get("is_ok", False)),
                message=message,
                details=dict(details) if isinstance(details, dict) else {},
            )
        )
    return ProjectHealthReport(
        project_root=_optional_string(raw_value, "project_root") or "",
        checks=checks,
    )


def _parse_import_diagnostics(raw_value: Any) -> list[ImportDiagnostic]:
    diagnostics: list[ImportDiagnostic] = []
    if not isinstance(raw_value, list):
        return diagnostics

    for item in raw_value:
        if not isinstance(item, dict):
            continue
        file_path = item.get("file_path")
        line_number = item.get("line_number")
        message = item.get("message")
        if not isinstance(file_path, str) or not isinstance(line_number, int) or not isinstance(message, str):
            continue
        diagnostics.append(
            ImportDiagnostic(
                file_path=file_path,
                line_number=line_number,
                message=message,
            )
        )
    return diagnostics


def _require_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = payload.get(key)
    if isinstance(value, dict):
        return value
    return None


def _parse_project_metadata(raw_value: Any) -> ProjectMetadata | None:
    if not isinstance(raw_value, dict):
        return None
    name = raw_value.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    schema_version = raw_value.get("schema_version", 1)
    if not isinstance(schema_version, int) or schema_version <= 0:
        schema_version = 1
    return ProjectMetadata(
        schema_version=schema_version,
        name=name,
        project_id=_optional_string(raw_value, "project_id") or "proj_legacy_unknown",
        default_entry=_optional_string(raw_value, "default_entry") or "main.py",
        default_argv=[
            item for item in raw_value.get("default_argv", []) if isinstance(item, str)
        ] if isinstance(raw_value.get("default_argv", []), list) else [],
        working_directory=_optional_string(raw_value, "working_directory") or ".",
        template=_optional_string(raw_value, "template") or "utility_script",
        run_configs=list(raw_value.get("run_configs", [])) if isinstance(raw_value.get("run_configs", []), list) else [],
        env_overrides=dict(raw_value.get("env_overrides", {})) if isinstance(raw_value.get("env_overrides", {}), dict) else {},
        project_notes=_optional_string(raw_value, "project_notes") or "",
        exclude_patterns=[
            item for item in raw_value.get("exclude_patterns", []) if isinstance(item, str)
        ] if isinstance(raw_value.get("exclude_patterns", []), list) else [],
    )


def _parse_project_package_config(raw_value: Any) -> ProjectPackageConfig | None:
    if not isinstance(raw_value, dict):
        return None

    return parse_project_package_config(raw_value)
