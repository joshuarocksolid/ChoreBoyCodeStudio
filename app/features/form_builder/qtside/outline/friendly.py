"""Friendly class words for outline captions."""

from __future__ import annotations

from app.features.form_builder.qtside.inspector.words import class_words


def friendly_of(qt_class: str) -> str:
    return class_words(qt_class).friendly
