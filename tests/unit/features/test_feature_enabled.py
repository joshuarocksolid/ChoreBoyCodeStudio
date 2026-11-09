"""FeatureSpec.enabled is optional and a failing predicate counts as disabled."""

from __future__ import annotations

import pytest

from app.features.spec import FeatureSpec, feature_is_enabled

pytestmark = pytest.mark.unit


def test_missing_predicate_is_enabled() -> None:
    spec = FeatureSpec(key="always", ownership_globs=())

    assert feature_is_enabled(spec) is True


def test_false_predicate_is_disabled() -> None:
    spec = FeatureSpec(key="off", ownership_globs=(), enabled=lambda: False)

    assert feature_is_enabled(spec) is False


def test_predicate_exception_is_disabled() -> None:
    def boom() -> bool:
        raise RuntimeError("predicate failed")

    spec = FeatureSpec(key="boom", ownership_globs=(), enabled=boom)

    assert feature_is_enabled(spec) is False
