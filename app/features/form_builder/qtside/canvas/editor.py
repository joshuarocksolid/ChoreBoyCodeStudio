"""In-place text editor. The controller opens and closes it."""

from __future__ import annotations

from typing import Callable, Optional

from app.features.form_builder.qtside.canvas.core.gesture import EditorDone
from app.features.form_builder.qtside.canvas.core.space import ViewMap
from app.features.form_builder.qtside.canvas.core.text import TextTarget
from app.features.form_builder.qtside.realize.api import Realizer


class InPlaceEditor:
    def __init__(self, viewport: object, realizer: Realizer, done: Callable[[EditorDone], None]) -> None:
        self._viewport = viewport
        self._realizer = realizer
        self._done = done
        self._target: Optional[TextTarget] = None
        self._view: Optional[ViewMap] = None

    def open(self, target: TextTarget, view: ViewMap) -> None:
        self._target = target
        self._view = view

    def follow(self, view: ViewMap) -> None:
        if self._target is None:
            return
        self._view = view

    def close(self, restore_focus: bool) -> None:
        del restore_focus
        self._target = None
        self._view = None

    def target(self) -> Optional[TextTarget]:
        return self._target
