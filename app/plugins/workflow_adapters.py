from __future__ import annotations

from typing import Any, Mapping

from app.core import constants
from app.core.models import ProjectMetadata, RuntimeIssue, RuntimeIssueReport
from app.intelligence.diagnostics_service import CodeDiagnostic
from app.packaging.packager import PackageResult
from app.plugins.workflow_broker import WorkflowBroker, WorkflowProviderDescriptor
from app.plugins.workflow_payload_codec import (
    parse_code_diagnostics,
    parse_package_result,
    parse_pytest_run_result,
    parse_python_text_transform_result,
    parse_runtime_result,
    parse_template_metadata,
)
from app.python_tools.models import PythonTextTransformResult
from app.pytest.runner_service import PytestRunResult
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
    return descriptor, parse_python_text_transform_result(
        result,
        file_path=file_path,
        project_root=project_root,
    )


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
    return descriptor, parse_python_text_transform_result(
        result,
        file_path=file_path,
        project_root=project_root,
    )


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
    project_metadata: ProjectMetadata | None = None,
    manifest_materialized: bool = True,
) -> tuple[WorkflowProviderDescriptor, list[CodeDiagnostic]]:
    request: dict[str, Any] = {
        "file_path": file_path,
        "project_root": project_root,
        "source": source,
        "known_runtime_modules": sorted(known_runtime_modules or ()),
        "allow_runtime_import_probe": allow_runtime_import_probe,
        "selected_linter": selected_linter,
        "lint_rule_overrides": dict(lint_rule_overrides or {}),
        "manifest_materialized": manifest_materialized,
    }
    if project_metadata is not None:
        request["project_metadata"] = project_metadata.to_dict()
    descriptor, result = broker.invoke_query(
        kind=constants.WORKFLOW_PROVIDER_KIND_DIAGNOSTICS,
        request=request,
        language="python",
        file_path=file_path,
        preferred_provider_key=preferred_provider_key,
    )
    return descriptor, parse_code_diagnostics(result)


def run_pytest_with_workflow(
    broker: WorkflowBroker,
    *,
    project_root: str,
    target_path: str | None = None,
    target_node_id: str | None = None,
    pytest_args: list[str] | None = None,
    timeout_seconds: int = 300,
    preferred_provider_key: str | None = None,
    on_event=None,
) -> tuple[WorkflowProviderDescriptor, PytestRunResult]:
    normalized_pytest_args = [str(arg) for arg in (pytest_args or []) if str(arg).strip()]
    descriptor, result = broker.run_job(
        kind=constants.WORKFLOW_PROVIDER_KIND_TEST,
        request={
            "project_root": project_root,
            "target_path": target_path,
            "target_node_id": target_node_id,
            "pytest_args": normalized_pytest_args,
            "timeout_seconds": timeout_seconds,
        },
        preferred_provider_key=preferred_provider_key,
        on_event=on_event,
        timeout_seconds=float(timeout_seconds) + 5.0,
    )
    return descriptor, parse_pytest_run_result(result)


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
    return descriptor, parse_package_result(result)


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
    return descriptor, parse_template_metadata(result)


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
    return descriptor, parse_runtime_result(result)
