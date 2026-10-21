"""Registry of tab-content providers.

``EditorTabFactory`` asks the registry which provider owns a file before it
materializes a tab. Features register providers from their ``install`` function.
The shell does not import a feature package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, List, Literal, Mapping, Optional, Protocol, Sequence, Tuple

from app.editors.tab_content_source import TabContentSource

if TYPE_CHECKING:  # pragma: no cover
    from app.editors.code_editor_widget import CodeEditorWidget
    from app.intelligence.diagnostics_models import CodeDiagnostic
    from app.qt.QtWidgets import QWidget
    from app.shell.theme_tokens import ShellThemeTokens

RestoreReason = Literal["draft", "history", "external_reload"]


@dataclass(frozen=True)
class TabMatchContext:
    """``project_root``: the open project's root or None. ``forced_text``: True when
    the user chose "Open as text" (the provider must not match)."""

    project_root: Optional[str]
    forced_text: bool = False


@dataclass(frozen=True)
class TabSurfaceRequest:
    """What the shell gives a provider when a tab opens.

    ``initial_text``: the file content (or restored-history content).
    ``create_source_editor``: builds a fully bound ``CodeEditorWidget`` for this
    path (the same construction, preferences, completion, bindings, language mode
    and ``shell.editorTabs.textEditor`` object name as a normal text tab,
    registered with the workspace controller). Providers call it eagerly
    (Markdown) or lazily (form builder: first View XML). It may be called at most
    once per surface.
    ``open_linked_file``: opens another path in the editor.
    """

    file_path: str
    initial_text: str
    parent: "QWidget"
    theme: "ShellThemeTokens"
    create_source_editor: Callable[[], "CodeEditorWidget"]
    open_linked_file: Callable[[str], None]
    project_root: Optional[str]


class TabSurface(Protocol):
    """The tab's content. The shell routes provider-owned tabs through this protocol."""

    def widget(self) -> "QWidget":
        """The widget added to the tab bar."""
        ...

    def content_source(self) -> Optional[TabContentSource]:
        """None: the shell keeps using the source editor's text (Markdown).
        Not None: attached to ``EditorTabState.content_source``."""
        ...

    def source_editor(self) -> "Optional[CodeEditorWidget]":
        """The source editor if it has been created (for find, go-to-line, debug
        execution markers), else None."""
        ...

    def apply_theme(self, tokens: "ShellThemeTokens") -> None:
        ...

    def set_diagnostics(self, diagnostics: "Sequence[CodeDiagnostic]") -> None:
        """Called by ProblemsController.push_diagnostics_to_editor."""
        ...

    def reveal(self, line: int, detail: "Optional[Mapping[str, str]]") -> bool:
        """Problems double-click / go-to-line. Returns False when it cannot."""
        ...

    def restore_text(self, text: str, reason: RestoreReason) -> None:
        """Draft restore, local-history restore, and external reload."""
        ...

    def close_blockers(self) -> Tuple[str, ...]:
        """Plain-word reasons closing needs extra confirmation beyond the shell's
        standard unsaved-changes prompt. Empty = none."""
        ...

    def file_path_changed(self, new_path: str) -> None:
        ...

    def focus_primary(self) -> None:
        """Focus the surface's main view."""
        ...

    def release(self) -> None:
        """Tab closing: dispose the surface. Idempotent."""
        ...


class TabContentProvider(Protocol):
    provider_id: str
    #: Higher wins when several providers match; ties are a registration error.
    priority: int

    def matches(self, file_path: str, context: TabMatchContext) -> bool:
        """Pure path test; must not read the file or import Qt-heavy modules."""
        ...

    def create_surface(self, request: TabSurfaceRequest) -> TabSurface:
        """May raise ``ProviderDeclined(reason)`` to fall back to a text tab with an
        info bar showing ``reason``."""
        ...


class ProviderDeclined(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class _PathBinding:
    """A path owns one surface and the provider that created it."""

    surface: TabSurface
    provider_id: str


class TabContentProviderRegistry:
    """Bound on the main window by the platform. ``register`` is called from
    feature ``install`` functions only.

    The shell records opened surfaces with ``bind``, ``unbind``, ``rekey`` and
    ``forget_all``. ``surface_for_source_editor`` finds the surface whose source
    editor is a given widget.
    """

    def __init__(self) -> None:
        self._providers: Dict[str, TabContentProvider] = {}
        self._surfaces: Dict[str, _PathBinding] = {}

    def register(self, provider: TabContentProvider) -> None:
        """ValueError on a duplicate id or a priority tie."""
        provider_id = provider.provider_id
        if provider_id in self._providers:
            raise ValueError(f"duplicate tab content provider id {provider_id}")
        for existing in self._providers.values():
            if existing.priority == provider.priority:
                raise ValueError(
                    f"tab content provider {provider_id} ties priority {provider.priority} "
                    f"with {existing.provider_id}"
                )
        self._providers[provider_id] = provider

    def provider_for(self, file_path: str, context: TabMatchContext) -> Optional[TabContentProvider]:
        if context.forced_text:
            return None
        matches: List[TabContentProvider] = [
            provider
            for provider in self._providers.values()
            if provider.matches(file_path, context)
        ]
        if not matches:
            return None
        return max(matches, key=lambda provider: provider.priority)

    def bind(self, file_path: str, surface: TabSurface, provider_id: str) -> None:
        if file_path in self._surfaces:
            raise ValueError(f"tab content path already bound: {file_path}")
        self._surfaces[file_path] = _PathBinding(surface=surface, provider_id=provider_id)

    def unbind(self, file_path: str) -> Optional[TabSurface]:
        binding = self._surfaces.pop(file_path, None)
        if binding is None:
            return None
        return binding.surface

    def rekey(self, old_path: str, new_path: str) -> None:
        if old_path not in self._surfaces:
            return
        if new_path != old_path and new_path in self._surfaces:
            raise ValueError(f"tab content path already bound: {new_path}")
        binding = self._surfaces.pop(old_path)
        self._surfaces[new_path] = binding

    def forget_all(self) -> None:
        self._surfaces.clear()

    def surface_for_path(self, file_path: str) -> Optional[TabSurface]:
        binding = self._surfaces.get(file_path)
        if binding is None:
            return None
        return binding.surface

    def provider_id_for(self, file_path: str) -> Optional[str]:
        binding = self._surfaces.get(file_path)
        if binding is None:
            return None
        return binding.provider_id

    def path_for_source_editor(self, editor: object) -> Optional[str]:
        for file_path, binding in self._surfaces.items():
            if binding.surface.source_editor() is editor:
                return file_path
        return None

    def surface_for_source_editor(self, editor: object) -> Optional[TabSurface]:
        file_path = self.path_for_source_editor(editor)
        if file_path is None:
            return None
        return self.surface_for_path(file_path)

    def surfaces(self) -> Tuple[Tuple[str, TabSurface], ...]:
        return tuple(
            sorted(
                ((file_path, binding.surface) for file_path, binding in self._surfaces.items()),
                key=lambda item: item[0],
            )
        )

    def apply_all_themes(self, tokens: "ShellThemeTokens") -> None:
        for _file_path, surface in self.surfaces():
            surface.apply_theme(tokens)
