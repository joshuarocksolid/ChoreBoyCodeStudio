"""Unit tests for designer preview variant presets."""

from __future__ import annotations

import pytest

from app.designer.preview import preview_variant_by_id, preview_variants

pytestmark = pytest.mark.unit


def test_preview_variants_include_default_style_and_device_presets() -> None:
    variants = list(preview_variants())
    assert [variant.variant_id for variant in variants] == [
        "default",
        "fusion",
        "phone_portrait",
        "tablet_portrait",
    ]


def test_preview_variant_by_id_returns_expected_variant() -> None:
    fusion = preview_variant_by_id("fusion")
    assert fusion is not None
    assert fusion.style_name == "Fusion"
    assert fusion.viewport_size is None

    phone = preview_variant_by_id("phone_portrait")
    assert phone is not None
    assert phone.style_name is None
    assert phone.viewport_size == (390, 844)

    assert preview_variant_by_id("missing_variant") is None
