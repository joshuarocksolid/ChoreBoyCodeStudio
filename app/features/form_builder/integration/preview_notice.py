"""Preview of a form that uses your own classes: what is sent, and what the user is told (M5.4, UX-CUST-008, 009).

The editor never imports project code (CONTRACTS section 10.4). It sends the
preview child the generated module (built in memory from the open, unsaved
form) and the list of own classes. The child imports each class, builds one
instance on a hidden parent and falls back to a stand-in of the base class
when that fails (FB602). Here:

* ``promoted_for`` lists the classes to import. A form outside a project sends
  them with no module, so the child draws stand-ins and imports nothing.
* ``PreviewNotices.preview`` sends one ``LoadForm`` for a form tab and, from the
  answer, shows the security info bar (first Preview of a project in a session),
  the stand-in toast and the FB602 row in Problems.
* ``parse_failure`` reads the child's FB602 report into the Problems sentence.

Opening a ``.ui`` file never runs code; only this request does, and only in the child.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.features.form_builder.engine.codegen.api import generate_form_module
from app.features.form_builder.engine.diagnostics import CODES, DiagnosticLocation, FormDiagnostic
from app.features.form_builder.engine.ipc.protocol import (
    Appearance,
    ErrorReport,
    LoadForm,
    PromotedClass,
    Response,
)
from app.features.form_builder.engine.project.custom_widgets import module_for_header, module_parts
from app.features.form_builder.engine.ui4.nodes import CustomWidgetNode, WidgetNode
from app.features.form_builder.engine.ui4.schema import HeaderDecl
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.preview_control import methods_for
from app.features.form_builder.integration.custom_registry import project_root_of
from app.features.form_builder.integration.toast import ToastNote
from app.features.form_builder.qtside.dialogs.promote import friendly_of

logger = logging.getLogger(__name__)

SOURCE = "preview"
OUTSIDE_PROJECT = "Preview shows stand-ins for your own classes, because this form isn't in a project."
GOT_IT = "Got it"
SHOW_PROBLEM = "Show problem"

#: Projects whose security note was shown in this editor session (UX-CUST-009).
_NOTED: Set[str] = set()

_FAILED = re.compile(r"^Custom widget (\S+) could not load")
_FILE_LINE = re.compile(r'File "([^"]+)", line (\d+)')


def forget_noted() -> None:
    """Start a new session for the security note (tests)."""
    _NOTED.clear()


@dataclass(frozen=True)
class OwnClass:
    class_name: str
    module: str
    extends: str
    #: Project file for the module, as the note shows it ("widgets/till_display.py").
    file: str


def own_classes(document: Any) -> Tuple[OwnClass, ...]:
    """Classes the form declares from a Python module, in declaration order. Reads declarations only."""
    found: List[OwnClass] = []
    for node in document.ui.children("customwidgets"):
        if not isinstance(node, CustomWidgetNode) or not node.class_name or "::" in node.class_name:
            continue
        header = node.field("header")
        module = module_for_header(header.text) if isinstance(header, HeaderDecl) else None
        if not module or not node.extends:
            continue
        parts = module_parts(module) or ()
        found.append(OwnClass(node.class_name, module, node.extends, "/".join(parts) + ".py"))
    return tuple(found)


def promoted_for(document: Any, project_root: Optional[str]) -> Tuple[PromotedClass, ...]:
    """What the child imports. With no project the module is empty: stand-ins only, nothing imported."""
    return tuple(
        PromotedClass(item.class_name, item.module if project_root else "", item.extends)
        for item in own_classes(document)
    )


def used_classes(document: Any) -> Tuple[OwnClass, ...]:
    """The declared own classes that at least one widget uses."""
    used = {node.class_name for node in document.iter_widgets()}
    return tuple(item for item in own_classes(document) if item.class_name in used)


def security_sentence(classes: Tuple[OwnClass, ...]) -> str:
    """The info bar text (UX_SPEC 13.2.5, UX-CUST-009)."""
    first = classes[0]
    more = ", and %d more" % (len(classes) - 1) if len(classes) > 1 else ""
    return (
        "Preview runs code from this project: %s (%s)%s. "
        "Code Studio runs it only in the preview window, never in the editor." % (first.class_name, first.file, more)
    )


def build_load_form(
    session: Any,
    path: str,
    view_id: str,
    *,
    request_id: str = "",
    appearance: Optional[Appearance] = None,
) -> LoadForm:
    """The preview request for the open, unsaved form. ``appearance`` is the user's style and screen (M5.5a)."""
    document = session.document
    root = project_root_of(session)
    scope = session.scope
    source: Optional[str] = None
    module_name = "ui_preview"
    if root and scope.generates:
        made = generate_form_module(document, scope=scope, source_bytes=None)
        if made.text is not None:
            source = made.text
            module_name = scope.module_name or module_name
    return LoadForm(
        request_id=request_id or uuid.uuid4().hex,
        view_id=view_id,
        form_path=path,
        module_name=module_name,
        module_source=source,
        ui_xml=None if source is not None else write_ui(document).text,
        project_root=root,
        sys_path=(root,) if root else (),
        appearance=appearance if appearance is not None else Appearance(),
        keep_values=False,
        revision=int(document.revision),
        promoted=promoted_for(document, root),
        form_methods=methods_for(document),
    )


@dataclass(frozen=True)
class StandIn:
    class_name: str
    exception: str
    file: str
    line: int

    def sentence(self) -> str:
        """Problems row (UX_SPEC 13.2.10)."""
        where = self.file
        if self.file and self.line:
            where = "%s line %d" % (self.file, self.line)
        if not where:
            return "Preview used a stand-in for %s: %s." % (self.class_name, self.exception)
        return "Preview used a stand-in for %s: %s in %s." % (self.class_name, self.exception, where)


def parse_failure(report: ErrorReport, project_root: Optional[str], fallback_file: Callable[[str], str]) -> Optional[StandIn]:
    """The FB602 report as a stand-in notice, or None when it is some other report."""
    if report.code != "FB602":
        return None
    named = _FAILED.match(report.message or "")
    if named is None:
        return None
    class_name = named.group(1)
    text = report.traceback or ""
    exception = text.split(":", 1)[0].strip() or "Error"
    found = _FILE_LINE.search(text)
    if found is None:
        return StandIn(class_name, exception, fallback_file(class_name), 0)
    return StandIn(class_name, exception, _relative(found.group(1), project_root), int(found.group(2)))


def _relative(path: str, project_root: Optional[str]) -> str:
    if project_root:
        root = os.path.realpath(project_root)
        real = os.path.realpath(path)
        if real == root or real.startswith(root + os.sep):
            return os.path.relpath(real, root).replace(os.sep, "/")
    return os.path.basename(path)


def stand_in_diagnostics(session: Any, failures: Tuple[StandIn, ...]) -> Tuple[FormDiagnostic, ...]:
    """FB602 rows for the Problems panel."""
    info = CODES["FB602"]
    found = []
    document = session.document
    for item in failures:
        user = next((w for w in document.iter_widgets() if w.class_name == item.class_name), None)
        found.append(
            FormDiagnostic(
                code=info.code,
                severity=info.severity,
                message=item.sentence(),
                location=DiagnosticLocation(
                    node_id=user.id if isinstance(user, WidgetNode) else None,
                    object_name=user.object_name if isinstance(user, WidgetNode) else None,
                    property="class",
                    rule_path=(item.class_name,),
                ),
                source=SOURCE,
            )
        )
    return tuple(found)


class PreviewNotices:
    """Sends a form tab's preview and tells the user what happened. One per form tab."""

    def __init__(self, surface: Any, session: Any, pool: Any = None) -> None:
        self._surface = surface
        self._session = session
        self._pool = pool
        self._view_id = "cbcs-form:%s" % uuid.uuid4().hex
        self._failures: List[StandIn] = []
        self._unsubscribe: Optional[Callable[[], None]] = None
        self.last_response: Optional[Response] = None
        #: M5.5a: the user's preview style and screen for a form path (``preview_control``).
        self.appearance_provider: Optional[Callable[[str], Appearance]] = None

    @property
    def view_id(self) -> str:
        return self._view_id

    def preview(self, path: str) -> str:
        """Send the form. Returns the request id."""
        pool = self._pool_or_shared()
        root = project_root_of(self._session)
        classes = used_classes(self._session.document)
        self._failures = []
        self._session.diagnostics.clear(SOURCE)
        if self._unsubscribe is None:
            self._unsubscribe = pool.subscribe(self._view_id, self._on_message)
        if classes:
            if root:
                self._security_note(root, classes)
            else:
                self._say(OUTSIDE_PROJECT)
        provider = self.appearance_provider
        message = build_load_form(
            self._session, path, self._view_id, appearance=provider(path) if provider is not None else None
        )
        return pool.request(message, self._on_response)

    def pool(self) -> Any:
        """The preview pool this form tab talks to."""
        return self._pool_or_shared()

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    # ---- child messages

    def _on_message(self, message: Any) -> None:
        if not isinstance(message, ErrorReport):
            return
        root = project_root_of(self._session)
        found = parse_failure(message, root, self._module_file)
        if found is not None and all(item.class_name != found.class_name for item in self._failures):
            self._failures.append(found)

    def _on_response(self, response: Any) -> None:
        if not isinstance(response, Response):
            return
        self.last_response = response
        if not response.ok:
            self._say("Preview could not open this form.")
            return
        if not self._failures:
            return
        failures = tuple(self._failures)
        self._session.diagnostics.publish(SOURCE, stand_in_diagnostics(self._session, failures))
        self._toast(failures[0])

    # ---- what the user sees

    def _module_file(self, class_name: str) -> str:
        for item in own_classes(self._session.document):
            if item.class_name == class_name:
                return item.file
        return ""

    def _security_note(self, root: str, classes: Tuple[OwnClass, ...]) -> None:
        key = os.path.realpath(root)
        if key in _NOTED:
            return
        notice: Any = getattr(self._surface, "_notice", None)
        show = getattr(notice, "show_choices", None)
        if notice is None or not callable(show):
            return
        if getattr(notice, "isVisible", lambda: False)():
            return
        _NOTED.add(key)
        show(security_sentence(classes), ((GOT_IT, notice.dismiss),))

    def _toast(self, first: StandIn) -> None:
        declared = {item.class_name: item for item in own_classes(self._session.document)}
        base = declared[first.class_name].extends if first.class_name in declared else "QWidget"
        text = "Preview used a plain %s for %s." % (friendly_of(base).lower(), first.class_name)
        toast = getattr(self._surface, "_command_toast", None)
        show = getattr(toast, "show_note", None)
        if not callable(show):
            return

        def reveal(_note: ToastNote) -> None:
            opener = getattr(self._surface, "_show_in_problems", None)
            if callable(opener):
                opener()

        show(ToastNote(text, SHOW_PROBLEM, "", 0), reveal)

    def _say(self, sentence: str) -> None:
        narrate = getattr(self._surface, "narrate", None)
        if callable(narrate):
            narrate(sentence)

    def _pool_or_shared(self) -> Any:
        if self._pool is not None:
            return self._pool
        from app.features.form_builder.qtside.preview.pool import PreviewPool

        return PreviewPool.shared()


def attach(surface: Any, session: Any, pool: Any = None) -> PreviewNotices:
    """Route the form tab's preview request to the notices.

    Hook for M5.5a: ``Ctrl+Shift+R`` (``form.action.preview``, a status sentence in ``surface.py``
    until then) and the Preview window should call ``surface.request_preview(path)``, which reaches
    ``PreviewNotices.preview`` through ``_preview_listener``, so the security note, FB602 rows and
    the stand-in toast come with every preview, however it is started.
    """
    notices = PreviewNotices(surface, session, pool)
    if hasattr(surface, "_preview_listener"):
        surface._preview_listener = notices.preview
    surface.own_class_preview = notices
    return notices


__all__ = [
    "GOT_IT",
    "OUTSIDE_PROJECT",
    "OwnClass",
    "PreviewNotices",
    "SHOW_PROBLEM",
    "StandIn",
    "attach",
    "build_load_form",
    "own_classes",
    "parse_failure",
    "promoted_for",
    "security_sentence",
    "stand_in_diagnostics",
    "used_classes",
]
