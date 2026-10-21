"""Register form-builder parity markers for the pytest scanner."""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        'parity(*ids): proves R3 parity items, e.g. parity("R3-145"); read by tools/form_builder_parity.py',
    )
    config.addinivalue_line(
        "markers",
        'pain(*ids): proves ranked pains, e.g. pain("P-3"); read by tools/form_builder_parity.py',
    )
    config.addinivalue_line(
        "markers",
        'logic(*ids): proves logic scenarios and features, e.g. logic("L-line-total-live")',
    )
