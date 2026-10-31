# pyright: reportAttributeAccessIssue=false
"""M7.0s protocol: optional run_behavior, and log kinds that still parse."""

from __future__ import annotations

import json

import pytest

from app.features.form_builder.engine.ipc.protocol import (
    FRAME_PREFIX,
    LOG_KINDS,
    PROTOCOL_VERSION,
    Appearance,
    LoadForm,
    decode_line,
    encode_frame,
)

pytestmark = pytest.mark.unit


def _load() -> LoadForm:
    return LoadForm(
        request_id="l",
        view_id="view",
        form_path="form.ui",
        module_name="ui_form",
        module_source=None,
        ui_xml=None,
        project_root=None,
        sys_path=(),
        appearance=Appearance(),
        keep_values=False,
        revision=1,
    )


def _body(message: LoadForm) -> dict:
    frame = encode_frame(message)
    return json.loads(frame[len(FRAME_PREFIX) :].strip())


def _decode_body(body: dict) -> object:
    line = FRAME_PREFIX + json.dumps(body)
    return decode_line(line)


def test_protocol_version_stays_one() -> None:
    assert PROTOCOL_VERSION == 1


def test_a_load_form_without_run_behavior_is_the_old_child() -> None:
    body = _body(_load())
    assert body["run_behavior"] is True
    del body["run_behavior"]
    decoded = _decode_body(body)
    assert isinstance(decoded, LoadForm)
    assert decoded.run_behavior is True


def test_run_behavior_false_decodes_false() -> None:
    body = _body(_load())
    body["run_behavior"] = False
    decoded = _decode_body(body)
    assert isinstance(decoded, LoadForm)
    assert decoded.run_behavior is False


def test_log_kinds_step_and_would_call_decode() -> None:
    assert LOG_KINDS == ("rule", "check", "step", "would_call", "needs_value")
    for kind in ("step", "would_call", ""):
        decoded = _decode_body(
            {
                "type": "log",
                "view_id": "view",
                "stream": "stdout",
                "level": "info",
                "text": "line",
                "ts_ms": 1,
                "kind": kind,
            }
        )
        assert getattr(decoded, "kind") == kind
