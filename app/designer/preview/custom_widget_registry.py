"""Custom-widget preview registry and safety helpers."""

from __future__ import annotations

from dataclasses import dataclass

from app.designer.model import UIModel


@dataclass(frozen=True)
class CustomWidgetPreviewEntry:
    """Preview metadata for one promoted/custom widget class."""

    class_name: str
    header: str
    extends: str


@dataclass(frozen=True)
class PreviewSafetyDecision:
    """Decision payload describing preview isolation requirements."""

    requires_isolation: bool
    message: str


def preview_registry_from_model(model: UIModel) -> list[CustomWidgetPreviewEntry]:
    """Map UI model custom-widgets metadata into preview registry entries."""
    entries: list[CustomWidgetPreviewEntry] = []
    for custom_widget in model.custom_widgets:
        entries.append(
            CustomWidgetPreviewEntry(
                class_name=custom_widget.class_name,
                header=custom_widget.header,
                extends=custom_widget.extends,
            )
        )
    return entries


def requires_isolated_preview(model: UIModel) -> bool:
    """Return True when preview should run in isolated runner process."""
    return len(model.custom_widgets) > 0


def promoted_class_names(model: UIModel) -> tuple[str, ...]:
    """Return deterministic promoted class names for diagnostics."""
    names = [item.class_name for item in model.custom_widgets]
    return tuple(sorted(set(names)))


def build_preview_safety_decision(model: UIModel) -> PreviewSafetyDecision:
    """Determine whether preview must run in isolated process mode."""
    if requires_isolated_preview(model):
        custom_names = ", ".join(promoted_class_names(model))
        return PreviewSafetyDecision(
            requires_isolation=True,
            message=(
                "Preview blocked in editor process for promoted/custom widgets "
                f"({custom_names}). Use isolated runner preview mode."
            ),
        )
    return PreviewSafetyDecision(
        requires_isolation=False,
        message="Preview can run in editor process.",
    )
