"""Editor-side helpers for trusted runtime introspection via the REPL sidecar."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import logging
import time
from typing import Any, Optional, Protocol

from app.bootstrap.paths import PathInput

from app.intelligence.completion_metrics import log_completion_phase

from app.intelligence.completion_context import CompletionContext, CompletionSyntacticContext
from app.intelligence.completion_models import CompletionItem
from app.intelligence.completion_providers import collect_import_module_bindings
from app.intelligence.runtime_introspection_cache import RuntimeIntrospectionCache
from app.intelligence.runtime_members import (
    RuntimeDetailResult,
    RuntimeListingResult,
    RuntimeMemberDetail,
    RuntimeMemberRef,
    RuntimeUnavailable,
)
from app.intelligence.trusted_runtime_whitelist import is_whitelisted_target_path

_logger = logging.getLogger(__name__)
_IMPORT_WARM_LIMIT = 4


class RuntimeIntrospectionPort(Protocol):
    def list_members(self, *, target_path: str) -> RuntimeListingResult:
        ...

    def resolve_member(self, ref: RuntimeMemberRef) -> RuntimeDetailResult:
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
    project_cache: dict[Any, Any] | None = None,
    state_root: Optional[PathInput] = None,
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
        project_cache=project_cache,
        state_root=state_root,
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
    project_cache: dict[Any, Any] | None = None,
    state_root: Optional[PathInput] = None,
) -> str:
    """Use Jedi inference to map a receiver expression to a whitelisted runtime path."""

    expression = str(base_expression or "").strip()
    if not expression:
        return ""
    position = _receiver_line_column(source_text, cursor_position)
    if position is None:
        return ""
    script = _script_for_inference(
        project_root=project_root,
        current_file_path=current_file_path,
        source_text=source_text,
        project_cache=project_cache,
        state_root=state_root,
    )
    if script is None:
        return ""
    return _infer_whitelisted_at(script, position[0], position[1])


def warm_open_buffer_target(
    *,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    cursor_position: int,
    project_cache: dict[Any, Any],
    state_root: Optional[PathInput],
) -> str:
    """Parse one open buffer and infer its imports, then the cursor receiver.

    The cursor target is what the first Ctrl+Space paints. Import inference
    loads modules such as PySide into the shared Jedi project so that infer
    is not paid again on the keypress.
    """

    script = _script_for_inference(
        project_root=project_root,
        current_file_path=current_file_path,
        source_text=source_text,
        project_cache=project_cache,
        state_root=state_root,
    )
    if script is None:
        return ""
    for line_number, column in _import_infer_sites(source_text):
        try:
            script.infer(line_number, column)
        except Exception:
            _logger.debug("Buffer warmup skipped an import infer", exc_info=True)
    position = _receiver_line_column(source_text, cursor_position)
    if position is None:
        return ""
    return _infer_whitelisted_at(script, position[0], position[1])


def _script_for_inference(
    *,
    project_root: str | None,
    current_file_path: str,
    source_text: str,
    project_cache: dict[Any, Any] | None,
    state_root: Optional[PathInput],
) -> Any:
    if project_cache is not None:
        from app.intelligence.jedi_script_factory import create_script

        try:
            return create_script(
                state_root=state_root,
                project_cache=project_cache,
                project_root=project_root,
                current_file_path=current_file_path,
                source_text=source_text,
            )
        except RuntimeError:
            return None

    started_at = time.perf_counter()
    try:
        import jedi
    except ImportError:
        return None
    try:
        from app.intelligence.jedi_runtime import initialize_jedi_runtime

        initialize_jedi_runtime(state_root)
    except Exception:
        pass
    log_completion_phase("jedi_runtime", (time.perf_counter() - started_at) * 1000.0, site="infer_target")
    try:
        project = None
        if project_root:
            from app.intelligence.jedi_project_cache import get_project

            project = get_project({}, project_root)
        else:
            log_completion_phase("jedi_project_create", 0.0, site="infer_target")
        return jedi.Script(code=source_text, path=current_file_path, project=project)
    except Exception as exc:
        _logger.debug("Jedi script failed for runtime introspection: %s", exc)
        return None


def _receiver_line_column(source_text: str, cursor_position: int) -> tuple[int, int] | None:
    column = max(0, min(cursor_position, len(source_text))) - 1
    while column >= 0 and source_text[column] != ".":
        column -= 1
    if column < 0:
        return None
    column -= 1
    while column >= 0 and source_text[column].isspace():
        column -= 1
    if column < 0:
        return None
    line_number = source_text.count("\n", 0, column + 1) + 1
    line_start = source_text.rfind("\n", 0, column + 1) + 1
    return line_number, column - line_start


def _import_infer_sites(source_text: str) -> list[tuple[int, int]]:
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []
    sites: list[tuple[int, int]] = []
    for node in tree.body:
        aliases: list[ast.alias] = []
        if isinstance(node, ast.Import):
            aliases = list(node.names)
        elif isinstance(node, ast.ImportFrom):
            aliases = list(node.names)
        for alias in aliases:
            if len(sites) >= _IMPORT_WARM_LIMIT:
                return sites
            end_column = alias.end_col_offset
            if alias.lineno is None or end_column is None:
                continue
            sites.append((alias.lineno, max(0, end_column - 1)))
    return sites


def _infer_whitelisted_at(script: Any, line_number: int, column: int) -> str:
    try:
        infer_started = time.perf_counter()
        inferred = script.infer(line_number, column)
        log_completion_phase(
            "jedi_infer_target",
            (time.perf_counter() - infer_started) * 1000.0,
            count=len(inferred),
        )
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
            candidate = f"{module_name}.{name}"
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

    def cached_items(
        self,
        query: RuntimeIntrospectionQuery,
        *,
        max_results: Optional[int] = None,
    ) -> Optional[list[CompletionItem]]:
        listing = self._cache.get(query.target_path)
        if listing is None:
            return None
        return listing.visible(query.member_prefix, limit=max_results)

    def fetch_and_cache_from_runner(
        self,
        query: RuntimeIntrospectionQuery,
        *,
        max_results: Optional[int] = None,
    ) -> list[CompletionItem]:
        if self._runner_port is None:
            return []
        listing = self._runner_port.list_members(target_path=query.target_path)
        if isinstance(listing, RuntimeUnavailable):
            return []
        self._cache.put(listing)
        return listing.visible(query.member_prefix, limit=max_results)

    def resolve_member(self, ref: RuntimeMemberRef) -> Optional[RuntimeMemberDetail]:
        if self._runner_port is None:
            return None
        detail = self._runner_port.resolve_member(ref)
        if isinstance(detail, RuntimeUnavailable):
            return None
        return detail


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
