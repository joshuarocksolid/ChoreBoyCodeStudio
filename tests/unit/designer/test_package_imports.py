"""Import smoke for Designer package scaffolding."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_designer_packages_import_without_side_effects() -> None:
    import app.designer.canvas  # noqa: F401
    import app.designer.commands  # noqa: F401
    import app.designer.connections  # noqa: F401
    import app.designer.inspector  # noqa: F401
    import app.designer.io  # noqa: F401
    import app.designer.layout  # noqa: F401
    import app.designer.modes  # noqa: F401
    import app.designer.model  # noqa: F401
    import app.designer.palette  # noqa: F401
    import app.designer.preview  # noqa: F401
    import app.designer.properties  # noqa: F401
    import app.designer.validation  # noqa: F401
