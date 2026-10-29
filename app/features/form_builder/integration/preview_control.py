"""One form tab's Preview: the user's style and screen, the open window, Save image's grab (M5.5a).

``PreviewControl`` sits between the form tab and ``PreviewNotices`` (M5.4):

* ``preview`` sends the form through ``PreviewNotices.preview``, so own classes,
  the security note and the stand-in toast come with every preview, and adds the
  user's style and screen to the request (``appearance_provider``).
* ``set_style`` and ``set_screen`` remember the choice per user and, when a
  preview window is open, send ``set_appearance`` to the warm child: no restart
  (UX-PREV-005).
* ``is_open`` follows the child's ``view_closed`` message, so Esc on the preview
  window (which closes it in the child) is seen here.
* ``grab`` asks the open window for its picture (Save image, Print).

The canvas never changes with these choices (D21).
"""

from __future__ import annotations

import base64
import logging
import os
import uuid
from typing import Any, Callable, List, Optional, Tuple

from app.features.form_builder.engine.ipc.protocol import (
    Appearance,
    ChildMessage,
    Grab,
    Response,
    SetAppearance,
    ViewClosed,
)
from app.features.form_builder.integration.memory import PreviewOptionsStore
from app.features.form_builder.engine.preview_options import (
    DEFAULT_SCREEN,
    DEFAULT_STYLE,
    PreviewChoices,
    ScreenProfile,
    all_profiles,
    appearance_for,
    find_profile,
    ordered_styles,
    with_profile,
)
from app.qt.QtWidgets import QStyleFactory

logger = logging.getLogger(__name__)


class PreviewControl:
    def __init__(self, surface: Any, notices: Any, store: Optional[PreviewOptionsStore] = None) -> None:
        self._surface = surface
        self._notices = notices
        self._store = store
        self._choices: Optional[PreviewChoices] = None
        self._profiles: Tuple[ScreenProfile, ...] = ()
        self._open = False
        self._unsubscribe: Optional[Callable[[], None]] = None
        self._child_styles: Tuple[str, ...] = ()
        self.last_look: dict = {}
        notices.appearance_provider = self.appearance
        self._listeners: List[Callable[[], None]] = []

    # ---- the user's choices

    def reload(self) -> None:
        """Read the choices again: Settings > Form designer may have changed them (CONTRACTS section 14)."""
        self._choices = None
        self._loaded()

    def _loaded(self) -> None:
        if self._choices is not None:
            return
        if self._store is None:
            root = getattr(self._surface.window(), "_state_root", None)
            self._store = PreviewOptionsStore(str(root) if root else None)
        self._choices, self._profiles = self._store.load()

    @property
    def choices(self) -> PreviewChoices:
        self._loaded()
        assert self._choices is not None
        return self._choices

    @property
    def profiles(self) -> Tuple[ScreenProfile, ...]:
        """Built-in screens, then the user's."""
        self._loaded()
        return all_profiles(self._profiles)

    def user_profiles(self) -> Tuple[ScreenProfile, ...]:
        self._loaded()
        return self._profiles

    def current_profile(self) -> ScreenProfile:
        return find_profile(self.choices.screen, self.user_profiles())

    def styles(self) -> Tuple[str, ...]:
        """Fusion first, then every style the preview runtime reports (this runtime's list until it has answered)."""
        if not self._child_styles:
            last = self._notices.last_response
            if isinstance(last, Response) and last.ok and isinstance(last.result, dict):
                listed = last.result.get("styles")
                if isinstance(listed, list) and listed:
                    self._child_styles = tuple(str(item) for item in listed)
        reported = self._child_styles or tuple(str(name) for name in QStyleFactory.keys())
        return ordered_styles(reported)

    def on_change(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def set_style(self, name: str) -> None:
        self._loaded()
        self._choices = PreviewChoices(style=name or DEFAULT_STYLE, screen=self.choices.screen)
        self._remember()
        self._push()

    def set_screen(self, name: str) -> None:
        self._loaded()
        self._choices = PreviewChoices(style=self.choices.style, screen=name or DEFAULT_SCREEN)
        self._remember()
        self._push()

    def add_profile(self, profile: ScreenProfile) -> None:
        """Remember a new screen and use it (Add a screen…)."""
        self._loaded()
        self._profiles = with_profile(self._profiles, profile)
        self._choices = PreviewChoices(style=self.choices.style, screen=profile.name)
        self._remember()
        self._push()

    def add_screen_dialog(self) -> Any:
        """Ask for a new screen (Name, Width, Height, Font, Font size, Scale); on Add, remember it and use it."""
        from app.features.form_builder.qtside.preview.screen_dialog import ScreenDialog

        dialog = ScreenDialog(self._surface.window(), self.add_profile)
        dialog.open()
        return dialog

    def _remember(self) -> None:
        if self._store is not None and self._choices is not None:
            self._store.save(self._choices, self._profiles)
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                logger.exception("preview option listener failed")

    # ---- the window

    def appearance(self, path: str) -> Appearance:
        self.reload()
        assert self._choices is not None
        return appearance_for(os.path.basename(path) or "form", self._choices, self._profiles)

    @property
    def is_open(self) -> bool:
        """True while the child has a window for this form. Esc on that window turns it off."""
        if not self._open:
            return False
        last = self._notices.last_response
        return not (last is not None and not last.ok)

    def preview(self, path: Optional[str] = None) -> None:
        """Open or refresh the Preview window with the current, unsaved form."""
        target = path if path is not None else str(self._surface.form_path())
        pool = self._notices.pool()
        if self._unsubscribe is None:
            self._unsubscribe = pool.subscribe(self._notices.view_id, self._on_child)
        self._notices.preview(target)
        self._open = True

    def close(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        self._open = False

    def _on_child(self, message: ChildMessage) -> None:
        if isinstance(message, ViewClosed):
            self._open = False

    def _push(self) -> None:
        """A style or screen change reaches an open window with ``set_appearance``."""
        if not self.is_open:
            return
        path = str(self._surface.form_path())
        message = SetAppearance(
            request_id=uuid.uuid4().hex, view_id=self._notices.view_id, appearance=self.appearance(path)
        )
        self._notices.pool().request(message, self._on_look)

    def _on_look(self, response: Any) -> None:
        if not isinstance(response, Response) or not response.ok or not isinstance(response.result, dict):
            return
        self.last_look = dict(response.result)
        styles = response.result.get("styles")
        if isinstance(styles, list) and styles:
            self._child_styles = tuple(str(item) for item in styles)

    def grab(self, done: Callable[[Optional[bytes]], None]) -> None:
        """The open window as PNG bytes, or None when there is no window (the caller then draws the canvas page)."""
        if not self.is_open:
            done(None)
            return

        def answered(response: Any) -> None:
            png: Optional[bytes] = None
            if isinstance(response, Response) and response.ok and isinstance(response.result, dict):
                text = response.result.get("png_base64")
                if isinstance(text, str):
                    try:
                        png = base64.b64decode(text)
                    except ValueError:
                        png = None
            done(png)

        self._notices.pool().request(Grab(request_id=uuid.uuid4().hex, view_id=self._notices.view_id), answered)


def control_for(surface: Any) -> Optional[PreviewControl]:
    """The form tab's control, or None when the tab has no preview notices yet."""
    return getattr(surface, "preview_control", None)


__all__ = ["PreviewControl", "control_for"]
