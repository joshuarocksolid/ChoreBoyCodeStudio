"""Cold and warm preview start through the FreeCAD 1.1 AppRun."""

from __future__ import annotations

import os
import time
import uuid

import pytest

from app.features.form_builder.engine.ipc.protocol import Appearance, LoadForm
from app.features.form_builder.engine.ipc.timing import DirectorConfig
from app.features.form_builder.qtside.preview.launch import apprun_preview_command, default_apprun, repo_root
from app.features.form_builder.qtside.preview.pool import PreviewPool
from tests.form_builder.preview.test_child_and_pool import _LABEL, _pump, _wait

_SOURCE = _LABEL


def _load(view_id: str) -> LoadForm:
    return LoadForm(
        request_id=uuid.uuid4().hex,
        view_id=view_id,
        form_path="form.ui",
        module_name="ui_%s" % view_id,
        module_source=_SOURCE,
        ui_xml=None,
        project_root=None,
        sys_path=(),
        appearance=Appearance(),
        keep_values=False,
        revision=1,
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(180)
@pytest.mark.pain("P-11")
def test_apprun_cold_handshake_and_warm_load(qapp):
    apprun = default_apprun()
    if not os.path.isfile(apprun):
        pytest.skip("FreeCAD 1.1 AppRun is not installed at %s" % apprun)
    pool = PreviewPool(
        command=apprun_preview_command(apprun, repo_root()),
        config=DirectorConfig(
            handshake_timeout=60.0,
            request_timeout=30.0,
            shutdown_grace=2.0,
            ping_interval=30.0,
            prewarm=True,
        ),
        root=repo_root(),
    )
    try:
        started = time.monotonic()
        pool.note_form_opened()
        assert _pump(qapp, lambda: pool.status().state == "ready", 60), pool.status()
        cold = time.monotonic() - started
        first = _wait(pool, qapp, _load("apprun-one"), timeout=30)
        warm_started = time.monotonic()
        second = _wait(pool, qapp, _load("apprun-two"), timeout=30)
        warm = time.monotonic() - warm_started
        line = "PREVIEW_TIMING cold_s=%.3f warm_s=%.3f spawns=%s" % (
            cold,
            warm,
            len(pool.spawn_monotonic),
        )
        print(line)
        with open("/tmp/cbcs-preview-timing.txt", "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        assert first.ok, first.detail
        assert second.ok, second.detail
        assert len(pool.spawn_monotonic) == 1
    finally:
        pool.shutdown()
