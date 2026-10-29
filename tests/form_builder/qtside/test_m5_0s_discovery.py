"""Every product contributor module of every M5 seam loads: a broken lane file fails here, not quietly."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.features.form_builder.engine import contributors
from tests.form_builder.m5_0s_support import forget_package, make_package

pytestmark = [pytest.mark.unit]


def test_every_seam_loads_its_product_modules_without_a_failure(qapp) -> None:  # type: ignore[no-untyped-def]
    del qapp
    from app.features.form_builder.integration import form_menu_ext, keys_ext, problem_fixes, workbench_ext
    from app.features.form_builder.qtside.canvas import layers
    from app.features.form_builder.qtside.inspector import _properties, editors

    form_menu_ext.load_form_menu_contributors(form_menu_ext)
    keys_ext.load_keys(keys_ext)
    workbench_ext.load_workbench_contributors(workbench_ext)
    layers.load_layers(layers)
    problem_fixes.load_fixes(problem_fixes)
    _properties.load_form_groups(editors)
    assert {name: why for name, why in contributors.FAILURES.items() if name.startswith("app.")} == {}


def test_a_failing_module_is_skipped_and_recorded_and_order_is_by_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = make_package(
        tmp_path,
        monkeypatch,
        "m5_discovery_probe",
        {"b_second": "def hook(seen):\n    seen.append('b')\n", "a_first": "def hook(seen):\n    seen.append('a')\n",
         "c_broken": "def hook(seen):\n    raise RuntimeError('lane bug')\n", "_helper": "raise SystemExit\n"},
    )
    try:
        seen: list = []
        contributors.run_contributors("probe", (package,), "hook", lambda _module, hook: hook(seen))
        contributors.run_contributors("probe", (package,), "hook", lambda _module, hook: hook(seen))
        assert seen == ["a", "b", "a", "b"]
        assert contributors.FAILURES.pop("m5_discovery_probe.c_broken").startswith("probe: RuntimeError")
    finally:
        forget_package("m5_discovery_probe")
