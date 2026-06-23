"""Editor-side helpers for trusted runtime introspection via the REPL sidecar."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any, Protocol

from app.intelligence.completion_context import CompletionContext, CompletionSyntacticContext
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_providers import collect_import_module_bindings
from app.intelligence.runtime_introspection_cache import RuntimeIntrospectionCache, clone_completion_items
from app.intelligence.trusted_runtime_whitelist import is_whitelisted_target_path

_logger = logging.getLogger(__name__)


class RuntimeIntrospectionPort(Protocol):
    """Minimal runner-side introspection surface."""

    def introspect(
        self,
        *,
        target_path: str,
        member_prefix: str,
        include_private: bool = True,
        max_results: int = 100,
    ) -> Any:
        ...


@dataclass(frozen=True)
class RuntimeIntrospectionQuery:
    """Resolved introspection request derived from editor completion context."""

    target_path: str
    member_prefix: str


def resolve_runtime_introspection_query(context: CompletionContext) -> RuntimeIntrospectionQuery | None:
    """Return a whitelisted introspection target for dotted-member completion."""

    if context.syntactic_context != CompletionSyntacticContext.DOTTED_MEMBER:
        return None

    target_path = _resolve_target_path_from_context(context)
    if not target_path:
        return None
    return RuntimeIntrospectionQuery(target_path=target_path, member_prefix=context.prefix)


def resolve_runtime_introspection_query_with_inference(
    *,
    context: CompletionContext,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
) -> RuntimeIntrospectionQuery | None:
    """Resolve introspection target from import paths or Jedi-inferred types."""

    direct = resolve_runtime_introspection_query(context)
    if direct is not None:
        return direct

    if context.syntactic_context != CompletionSyntacticContext.DOTTED_MEMBER:
        return None

    inferred = infer_trusted_runtime_target_path(
        project_root=project_root,
        current_file_path=current_file_path,
        source_text=source_text,
        base_expression=context.base_expression,
        cursor_position=context.cursor_position,
    )
    if not inferred:
        return None
    return RuntimeIntrospectionQuery(target_path=inferred, member_prefix=context.prefix)


def infer_trusted_runtime_target_path(
    *,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    base_expression: str,
    cursor_position: int,
) -> str:
    """Use Jedi inference to map a receiver expression to a whitelisted runtime path."""

    expression = str(base_expression or "").strip()
    if not expression:
        return ""

    try:
        import jedi
    except ImportError:
        return ""

    try:
        from app.intelligence.jedi_runtime import initialize_jedi_runtime

        initialize_jedi_runtime(None)
    except Exception:
        pass

    column = max(0, min(cursor_position, len(source_text))) - 1
    while column >= 0 and source_text[column] != ".":
        column -= 1
    if column < 0:
        return ""
    column -= 1
    while column >= 0 and source_text[column].isspace():
        column -= 1
    if column < 0:
        return ""

    line_number = source_text.count("\n", 0, column + 1) + 1
    line_start = source_text.rfind("\n", 0, column + 1) + 1
    line_column = column - line_start

    try:
        if project_root:
            from app.bootstrap.paths import project_manifest_path
            from app.project.import_layout import resolve_project_import_layout
            from app.project.project_manifest import load_project_manifest

            root = Path(project_root).expanduser().resolve()
            metadata = None
            manifest_path = project_manifest_path(root)
            if manifest_path.is_file():
                try:
                    metadata = load_project_manifest(manifest_path)
                except Exception:
                    metadata = None
            layout = resolve_project_import_layout(root, metadata)
            project = jedi.Project(
                str(root),
                added_sys_path=layout.jedi_added_sys_path,
                load_unsafe_extensions=False,
                smart_sys_path=True,
            )
            script = jedi.Script(code=source_text, path=current_file_path, project=project)
        else:
            script = jedi.Script(code=source_text, path=current_file_path)
        inferred = script.infer(line_number, line_column)
    except Exception as exc:
        _logger.debug("Jedi infer failed for runtime introspection: %s", exc)
        return ""

    for definition in inferred:
        full_name = str(getattr(definition, "full_name", "") or "").strip()
        if full_name and is_whitelisted_target_path(full_name):
            return full_name
        module_name = str(getattr(definition, "module_name", "") or "").strip()
        name = str(getattr(definition, "name", "") or "").strip()
        if module_name and name:
            candidate = f"{module_name}.{name}" if module_name else name
            if is_whitelisted_target_path(candidate):
                return candidate
        if module_name and is_whitelisted_target_path(module_name):
            return module_name
    return ""


def _resolve_target_path_from_context(context: CompletionContext) -> str:
    trusted = str(context.trusted_runtime_module or "").strip()
    if trusted:
        return trusted

    module_name = str(context.module_name or context.base_expression or "").strip()
    if not module_name:
        return ""

    bindings = collect_import_module_bindings(context.source_text)
    expression_parts = module_name.split(".")
    first = expression_parts[0]
    bound = bindings.get(first, first)
    if bound == first:
        candidate = module_name
    elif len(expression_parts) == 1:
        candidate = bound
    else:
        candidate = ".".join([bound, *expression_parts[1:]])

    if is_whitelisted_target_path(candidate):
        return candidate
    return ""


class RuntimeIntrospectionCoordinator:
    """Session cache + runner port for editor runtime member discovery."""

    def __init__(
        self,
        *,
        cache: RuntimeIntrospectionCache | None = None,
        runner_port: RuntimeIntrospectionPort | None = None,
    ) -> None:
        self._cache = cache or RuntimeIntrospectionCache()
        self._runner_port = runner_port

    @property
    def cache(self) -> RuntimeIntrospectionCache:
        return self._cache

    def set_runner_port(self, runner_port: RuntimeIntrospectionPort | None) -> None:
        self._runner_port = runner_port

    def clear_cache(self) -> None:
        self._cache.clear()

    def cached_items(self, query: RuntimeIntrospectionQuery, *, include_private: bool = True) -> list[CompletionItem] | None:
        cached = self._cache.get(target_path=query.target_path, include_private=include_private)
        if cached is None:
            return None
        return _filter_prefix(clone_completion_items(cached), query.member_prefix)

    def fetch_and_cache_from_runner(
        self,
        query: RuntimeIntrospectionQuery,
        *,
        include_private: bool = True,
        max_results: int = 100,
    ) -> list[CompletionItem]:
        """Fetch members from the runner, store in cache, and return prefix-filtered items."""

        if self._runner_port is None:
            return []

        envelope = self._runner_port.introspect(
            target_path=query.target_path,
            member_prefix="",
            include_private=include_private,
            max_results=max_results,
        )
        items = list(getattr(envelope, "items", []) or [])
        self._cache.put(
            target_path=query.target_path,
            include_private=include_private,
            items=items,
        )
        return _filter_prefix(clone_completion_items(items), query.member_prefix)


def attach_replacement_metadata(
    items: list[CompletionItem],
    *,
    context: CompletionContext,
) -> list[CompletionItem]:
    """Attach buffer replacement ranges and trigger metadata to introspection items."""

    attached: list[CompletionItem] = []
    for item in items:
        attached.append(
            CompletionItem(
                label=item.label,
                insert_text=item.insert_text,
                kind=item.kind,
                detail=item.detail,
                documentation=item.documentation,
                signature=item.signature,
                return_type=item.return_type,
                source_file_path=item.source_file_path,
                engine=item.engine,
                source=item.source,
                confidence=item.confidence,
                semantic_kind=item.semantic_kind,
                replacement_start=context.replacement_range.start,
                replacement_end=context.replacement_range.end,
                trigger_kind=context.trigger_kind,
                trigger_character=context.trigger_character,
                side_effect_risk=item.side_effect_risk,
                item_id=item.item_id,
                context_fingerprint=context.fingerprint,
                resolve_provider=item.resolve_provider,
                resolvable_fields=item.resolvable_fields,
            )
        )
    return attached


def _filter_prefix(items: list[CompletionItem], prefix: str) -> list[CompletionItem]:
    if not prefix:
        return items
    lowered = prefix.lower()
    return [item for item in items if item.label.lower().startswith(lowered)]
