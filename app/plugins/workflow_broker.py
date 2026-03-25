from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any, Callable, Mapping

from app.core import constants
from app.plugins.api_broker import PluginApiBroker, PluginRuntimeJob
from app.plugins.project_config import ProjectPluginConfig, preferred_provider_for
from app.plugins.workflow_catalog import WorkflowProviderCatalog

WorkflowQueryHandler = Callable[[Mapping[str, Any]], Any]
WorkflowJobEventHandler = Callable[[str, Mapping[str, Any]], None]
WorkflowJobHandler = Callable[[Mapping[str, Any], WorkflowJobEventHandler, Callable[[], bool]], Any]


@dataclass(frozen=True)
class WorkflowProviderDescriptor:
    provider_key: str
    kind: str
    lane: str
    title: str
    source_kind: str
    priority: int = 100
    languages: tuple[str, ...] = field(default_factory=tuple)
    file_extensions: tuple[str, ...] = field(default_factory=tuple)
    plugin_id: str | None = None
    plugin_version: str | None = None
    permissions: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WorkflowProviderMetrics:
    provider_key: str
    kind: str
    lane: str
    title: str
    source_kind: str
    invocation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    timeout_count: int = 0
    last_elapsed_ms: float | None = None
    max_elapsed_ms: float | None = None
    last_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_key": self.provider_key,
            "kind": self.kind,
            "lane": self.lane,
            "title": self.title,
            "source_kind": self.source_kind,
            "invocation_count": self.invocation_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "last_elapsed_ms": self.last_elapsed_ms,
            "max_elapsed_ms": self.max_elapsed_ms,
            "last_error": self.last_error,
        }


@dataclass(frozen=True)
class _BuiltinWorkflowProvider:
    descriptor: WorkflowProviderDescriptor
    query_handler: WorkflowQueryHandler | None = None
    job_handler: WorkflowJobHandler | None = None


class WorkflowBroker:
    def __init__(self, plugin_api_broker: PluginApiBroker) -> None:
        self._plugin_api_broker = plugin_api_broker
        self._catalog = WorkflowProviderCatalog([])
        self._project_config: ProjectPluginConfig | None = None
        self._builtin_providers: dict[str, _BuiltinWorkflowProvider] = {}
        self._metrics: dict[str, WorkflowProviderMetrics] = {}

    def set_plugin_catalog(
        self,
        catalog: WorkflowProviderCatalog,
        *,
        project_config: ProjectPluginConfig | None = None,
    ) -> None:
        self._catalog = catalog
        self._project_config = project_config

    def register_builtin_query_provider(
        self,
        *,
        provider_key: str,
        kind: str,
        title: str,
        handler: WorkflowQueryHandler,
        languages: tuple[str, ...] = (),
        file_extensions: tuple[str, ...] = (),
        priority: int = 1000,
    ) -> None:
        self._builtin_providers[provider_key] = _BuiltinWorkflowProvider(
            descriptor=WorkflowProviderDescriptor(
                provider_key=provider_key,
                kind=kind,
                lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
                title=title,
                source_kind=constants.PLUGIN_SOURCE_BUILTIN,
                priority=priority,
                languages=languages,
                file_extensions=file_extensions,
            ),
            query_handler=handler,
        )

    def register_builtin_job_provider(
        self,
        *,
        provider_key: str,
        kind: str,
        title: str,
        handler: WorkflowJobHandler,
        languages: tuple[str, ...] = (),
        file_extensions: tuple[str, ...] = (),
        priority: int = 1000,
    ) -> None:
        self._builtin_providers[provider_key] = _BuiltinWorkflowProvider(
            descriptor=WorkflowProviderDescriptor(
                provider_key=provider_key,
                kind=kind,
                lane=constants.WORKFLOW_PROVIDER_LANE_JOB,
                title=title,
                source_kind=constants.PLUGIN_SOURCE_BUILTIN,
                priority=priority,
                languages=languages,
                file_extensions=file_extensions,
            ),
            job_handler=handler,
        )

    def list_providers(
        self,
        *,
        kind: str | None = None,
        lane: str | None = None,
        language: str | None = None,
        file_path: str | None = None,
    ) -> list[WorkflowProviderDescriptor]:
        descriptors: list[WorkflowProviderDescriptor] = []
        for builtin in self._builtin_providers.values():
            if not _descriptor_matches(
                builtin.descriptor,
                kind=kind,
                lane=lane,
                language=language,
                file_path=file_path,
            ):
                continue
            descriptors.append(builtin.descriptor)
        for plugin_provider in self._catalog.list_matching(
            kind=kind,
            lane=lane,
            language=language,
            file_path=file_path,
        ):
            descriptors.append(
                WorkflowProviderDescriptor(
                    provider_key=plugin_provider.provider_key,
                    kind=plugin_provider.provider.kind,
                    lane=plugin_provider.provider.lane,
                    title=plugin_provider.provider.title,
                    source_kind=plugin_provider.source_kind,
                    priority=plugin_provider.provider.priority,
                    languages=plugin_provider.provider.languages,
                    file_extensions=plugin_provider.provider.file_extensions,
                    plugin_id=plugin_provider.plugin_id,
                    plugin_version=plugin_provider.plugin_version,
                    permissions=tuple(plugin_provider.provider.permissions),
                )
            )
        descriptors.sort(key=lambda item: (-item.priority, item.provider_key))
        return descriptors

    def list_provider_metrics(self) -> list[dict[str, Any]]:
        metrics = list(self._metrics.values())
        metrics.sort(key=lambda item: item.provider_key)
        return [item.to_dict() for item in metrics]

    def invoke_query(
        self,
        *,
        kind: str,
        request: Mapping[str, Any],
        language: str | None = None,
        file_path: str | None = None,
        preferred_provider_key: str | None = None,
    ) -> tuple[WorkflowProviderDescriptor, Any]:
        descriptor = self._resolve_provider_descriptor(
            kind=kind,
            lane=constants.WORKFLOW_PROVIDER_LANE_QUERY,
            language=language,
            file_path=file_path,
            preferred_provider_key=preferred_provider_key,
        )
        started_at = time.perf_counter()
        try:
            builtin = self._builtin_providers.get(descriptor.provider_key)
            if builtin is not None:
                assert builtin.query_handler is not None
                result = builtin.query_handler(dict(request))
            else:
                result = self._plugin_api_broker.invoke_workflow_query(
                    descriptor.provider_key,
                    dict(request),
                    activation_event=f"on_provider:{kind}",
                )
        except Exception as exc:
            self._record_provider_outcome(
                descriptor,
                elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
                error=str(exc),
            )
            raise
        self._record_provider_outcome(
            descriptor,
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            error=None,
        )
        return descriptor, result

    def run_job(
        self,
        *,
        kind: str,
        request: Mapping[str, Any],
        language: str | None = None,
        file_path: str | None = None,
        preferred_provider_key: str | None = None,
        on_event: WorkflowJobEventHandler | None = None,
        timeout_seconds: float | None = None,
    ) -> tuple[WorkflowProviderDescriptor, Any]:
        descriptor = self._resolve_provider_descriptor(
            kind=kind,
            lane=constants.WORKFLOW_PROVIDER_LANE_JOB,
            language=language,
            file_path=file_path,
            preferred_provider_key=preferred_provider_key,
        )
        started_at = time.perf_counter()
        try:
            builtin = self._builtin_providers.get(descriptor.provider_key)
            if builtin is not None:
                assert builtin.job_handler is not None
                result = builtin.job_handler(
                    dict(request),
                    on_event or _noop_job_event_handler,
                    lambda: False,
                )
            else:
                job = self._plugin_api_broker.start_workflow_job(
                    descriptor.provider_key,
                    dict(request),
                    on_event=on_event,
                    activation_event=f"on_provider:{kind}",
                )
                result = self._plugin_api_broker.wait_for_workflow_job(
                    job,
                    timeout_seconds=timeout_seconds,
                )
        except Exception as exc:
            self._record_provider_outcome(
                descriptor,
                elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
                error=str(exc),
            )
            raise
        self._record_provider_outcome(
            descriptor,
            elapsed_ms=(time.perf_counter() - started_at) * 1000.0,
            error=None,
        )
        return descriptor, result

    def _resolve_provider_descriptor(
        self,
        *,
        kind: str,
        lane: str,
        language: str | None,
        file_path: str | None,
        preferred_provider_key: str | None,
    ) -> WorkflowProviderDescriptor:
        resolved_preference = preferred_provider_key
        if resolved_preference is None:
            resolved_preference = preferred_provider_for(
                kind,
                config=self._project_config,
                language=language,
            )
        builtin_preferred = (
            resolved_preference
            if resolved_preference is not None
            else _default_builtin_provider_key(kind=kind, lane=lane)
        )
        if builtin_preferred is not None:
            builtin = self._builtin_providers.get(builtin_preferred)
            if builtin is not None and _descriptor_matches(
                builtin.descriptor,
                kind=kind,
                lane=lane,
                language=language,
                file_path=file_path,
            ):
                return builtin.descriptor
        plugin_provider = self._catalog.select(
            kind=kind,
            lane=lane,
            preferred_provider_key=resolved_preference,
            language=language,
            file_path=file_path,
        )
        if plugin_provider is None:
            raise LookupError(f"No workflow provider available for kind={kind} lane={lane}")
        return WorkflowProviderDescriptor(
            provider_key=plugin_provider.provider_key,
            kind=plugin_provider.provider.kind,
            lane=plugin_provider.provider.lane,
            title=plugin_provider.provider.title,
            source_kind=plugin_provider.source_kind,
            priority=plugin_provider.provider.priority,
            languages=plugin_provider.provider.languages,
            file_extensions=plugin_provider.provider.file_extensions,
            plugin_id=plugin_provider.plugin_id,
            plugin_version=plugin_provider.plugin_version,
            permissions=tuple(plugin_provider.provider.permissions),
        )

    def _record_provider_outcome(
        self,
        descriptor: WorkflowProviderDescriptor,
        *,
        elapsed_ms: float,
        error: str | None,
    ) -> None:
        existing = self._metrics.get(descriptor.provider_key)
        invocation_count = 1 if existing is None else existing.invocation_count + 1
        success_count = 1 if error is None else 0
        failure_count = 0 if error is None else 1
        timeout_count = 1 if (error is not None and "timed out" in error.lower()) else 0
        if existing is not None:
            success_count += existing.success_count
            failure_count += existing.failure_count
            timeout_count += existing.timeout_count
            max_elapsed_ms = (
                elapsed_ms
                if existing.max_elapsed_ms is None
                else max(existing.max_elapsed_ms, elapsed_ms)
            )
        else:
            max_elapsed_ms = elapsed_ms
        self._metrics[descriptor.provider_key] = WorkflowProviderMetrics(
            provider_key=descriptor.provider_key,
            kind=descriptor.kind,
            lane=descriptor.lane,
            title=descriptor.title,
            source_kind=descriptor.source_kind,
            invocation_count=invocation_count,
            success_count=success_count,
            failure_count=failure_count,
            timeout_count=timeout_count,
            last_elapsed_ms=elapsed_ms,
            max_elapsed_ms=max_elapsed_ms,
            last_error=error,
        )


def _default_builtin_provider_key(*, kind: str, lane: str) -> str | None:
    defaults = {
        (constants.WORKFLOW_PROVIDER_KIND_FORMATTER, constants.WORKFLOW_PROVIDER_LANE_QUERY): "builtin:formatter",
        (constants.WORKFLOW_PROVIDER_KIND_IMPORT_ORGANIZER, constants.WORKFLOW_PROVIDER_LANE_QUERY): "builtin:import_organizer",
        (constants.WORKFLOW_PROVIDER_KIND_DIAGNOSTICS, constants.WORKFLOW_PROVIDER_LANE_QUERY): "builtin:diagnostics",
        (constants.WORKFLOW_PROVIDER_KIND_TEMPLATE, constants.WORKFLOW_PROVIDER_LANE_QUERY): "builtin:templates",
        (constants.WORKFLOW_PROVIDER_KIND_RUNTIME_EXPLAINER, constants.WORKFLOW_PROVIDER_LANE_QUERY): "builtin:runtime_explainer",
        (constants.WORKFLOW_PROVIDER_KIND_TEST, constants.WORKFLOW_PROVIDER_LANE_JOB): "builtin:pytest",
        (constants.WORKFLOW_PROVIDER_KIND_PACKAGING, constants.WORKFLOW_PROVIDER_LANE_JOB): "builtin:packaging",
    }
    return defaults.get((kind, lane))


def _descriptor_matches(
    descriptor: WorkflowProviderDescriptor,
    *,
    kind: str | None,
    lane: str | None,
    language: str | None,
    file_path: str | None,
) -> bool:
    if kind is not None and descriptor.kind != kind:
        return False
    if lane is not None and descriptor.lane != lane:
        return False
    if language is not None and descriptor.languages:
        if language.lower() not in {value.lower() for value in descriptor.languages}:
            return False
    if file_path is not None and descriptor.file_extensions:
        suffix = file_path.rsplit(".", 1)
        normalized_suffix = f".{suffix[-1].lower()}" if len(suffix) == 2 else ""
        if normalized_suffix not in {value.lower() for value in descriptor.file_extensions}:
            return False
    return True


def _noop_job_event_handler(_event_type: str, _payload: Mapping[str, Any]) -> None:
    return
