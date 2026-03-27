"""Preview variant presets for Designer form rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class PreviewVariant:
    """Describes one preview rendering preset."""

    variant_id: str
    label: str
    style_name: Optional[str] = None
    viewport_size: Optional[Tuple[int, int]] = None


_PREVIEW_VARIANTS: tuple[PreviewVariant, ...] = (
    PreviewVariant(
        variant_id="default",
        label="Default",
    ),
    PreviewVariant(
        variant_id="fusion",
        label="Fusion Style",
        style_name="Fusion",
    ),
    PreviewVariant(
        variant_id="phone_portrait",
        label="Phone Portrait",
        viewport_size=(390, 844),
    ),
    PreviewVariant(
        variant_id="tablet_portrait",
        label="Tablet Portrait",
        viewport_size=(768, 1024),
    ),
)


def preview_variants() -> Sequence[PreviewVariant]:
    """Return known preview variant presets."""
    return _PREVIEW_VARIANTS


def preview_variant_by_id(variant_id: str) -> Optional[PreviewVariant]:
    """Resolve preview variant by id."""
    for variant in _PREVIEW_VARIANTS:
        if variant.variant_id == variant_id:
            return variant
    return None
