"""PROPOSED for platform.shell by M2.0 (CONTRACTS.md section 11).

A generic registry of tab-content providers. ``EditorTabFactory`` asks the
registry which provider (if any) owns a file before it materializes a tab.
Markdown moves onto this registry (provider id ``markdown``) and
``wrap_tab_content_if_markdown`` / ``EditorTabContentRegistry``'s markdown
fields are deleted. The shell never imports a feature package; features
register providers from their ``install`` function.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, List, Literal, Mapping, Optional, Protocol, Sequence, Tuple

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
    ``publish_problems``: replaces the Problems rows for a path the shell does
    not lint. ``show_problems``: brings the Problems tab forward.
    """

    file_path: str
    initial_text: str
    parent: "QWidget"
    theme: "ShellThemeTokens"
    create_source_editor: Callable[[], "CodeEditorWidget"]
    open_linked_file: Callable[[str], None]
    project_root: Optional[str]
    publish_problems: Callable[[str, List["CodeDiagnostic"]], None]
    show_problems: Callable[[], None]


class TabSurface(Protocol):
    """The tab's content. Everything the shell does to a tab's editor widget today
    goes through this protocol when a provider owns the tab (M2.0 audits every
    ``_editor_widgets_by_path`` call site and routes it here)."""

    def widget(self) -> "QWidget":
        """The widget added to the tab bar."""
        ...

    def content_source(self) -> Optional[TabContentSource]:
        """None: the shell keeps using the source editor's text (Markdown).
        Not None: attached to ``EditorTabState.content_source`` (form builder)."""
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
        """Problems double-click / go-to-line. The form surface selects the node
        named by ``detail['fb_key']``/``fb_object``; returns False when it cannot."""
        ...

    def restore_text(self, text: str, reason: RestoreReason) -> None:
        """Replaces every place the shell calls ``editor_widget.setPlainText`` for
        draft restore, local-history restore and external reload. The form surface
        executes ReplaceDocument (undoable); on a parse error it switches to View
        XML holding ``text`` with a banner, keeping the previous document."""
        ...

    def close_blockers(self) -> Tuple[str, ...]:
        """Plain-word reasons closing needs extra confirmation beyond the shell's
        standard unsaved-changes prompt (e.g. "Try mode is running"). Empty = none."""
        ...

    def file_path_changed(self, new_path: str) -> None:
        ...

    def focus_primary(self) -> None:
        """Focus the surface's main view (canvas, or the XML editor when shown)."""
        ...

    def release(self) -> None:
        """Tab closing: dispose sessions, realize trees, preview views. Idempotent."""
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
        info bar showing ``reason`` (form builder: UiReadError on open)."""
        ...


class ProviderDeclined(Exception):
    def __init__(self, reason: str) -> None:
        ...


class TabContentProviderRegistry:
    """The committed window field ``_tab_content_registry`` becomes this registry.
    It is bound in ``install_editors``, before the FEATURE_SPECS loop, so feature
    installs can register into it. ``_markdown_panes_by_path`` moves under
    markdown's ownership globs. ``register`` is called from feature ``install``
    functions only. Feature install runs before ``install_run_debug``, so
    features look up Run/packaging services lazily, never during install."""

    def register(self, provider: TabContentProvider) -> None:
        """ValueError on a duplicate id or a priority tie."""
        ...

    def provider_for(self, file_path: str, context: TabMatchContext) -> Optional[TabContentProvider]:
        ...

    def surface_for_path(self, file_path: str) -> Optional[TabSurface]:
        ...

    def surfaces(self) -> Tuple[Tuple[str, TabSurface], ...]:
        ...

    def apply_all_themes(self, tokens: "ShellThemeTokens") -> None:
        ...
