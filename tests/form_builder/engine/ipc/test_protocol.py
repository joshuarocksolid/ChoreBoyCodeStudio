"""Frame codec and the patch-versus-load choice."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.ipc.protocol import (
    FRAME_PREFIX,
    MAX_FRAME_BYTES,
    PROTOCOL_VERSION,
    Appearance,
    CloseView,
    CrashReport,
    ErrorReport,
    FrameDecoder,
    Grab,
    Hello,
    LoadForm,
    Log,
    NeedSecret,
    NoiseLine,
    Ping,
    PromotedClass,
    PropertyPatch,
    ProtocolViolation,
    ProvideSecret,
    Ready,
    ResourceModule,
    Response,
    SetAppearance,
    Shutdown,
    SourceRef,
    TryDataPlan,
    TryStart,
    TryStop,
    UpdateForm,
    ViewClosed,
    decode_line,
    encode_frame,
)
from app.features.form_builder.engine.ipc.refresh import select_form_refresh
from app.features.form_builder.engine.ipc.timing import PREWARM_DEFAULT, prewarm_from_environ


def _samples():
    appearance = Appearance(palette={"window": "#fff"}, device_profile="shop")
    return [
        Hello(
            request_id="h",
            protocol="cbcs_form_preview",
            version=PROTOCOL_VERSION,
            session_token="tok",
            host_pid=4,
        ),
        LoadForm(
            request_id="l",
            view_id="view",
            form_path="form.ui",
            module_name="ui_form",
            module_source="class Ui_Form: pass\n",
            ui_xml=None,
            project_root="/tmp/proj",
            sys_path=("/tmp/proj",),
            appearance=appearance,
            keep_values=True,
            revision=3,
            resource_modules=(ResourceModule(name="pkg.form_rc", source="x = 1\n"),),
            promoted=(PromotedClass(class_name="Meter", header_module="pkg.meter", extends="QWidget"),),
        ),
        UpdateForm(
            request_id="u",
            view_id="view",
            base_revision=3,
            revision=4,
            patches=(PropertyPatch(object_name="title", name="text", value="Hi"),),
        ),
        SetAppearance(request_id="s", view_id="view", appearance=appearance),
        TryStart(
            request_id="t",
            view_id="view",
            module_name="window",
            module_source="pass\n",
            window_class_name="Window",
            base_class="QDialog",
            window_values=(("title", "Hi"),),
            data=TryDataPlan(connections=(("main", {"driver": "sqlite"}),), pg_mode="would_run"),
        ),
        TryStop(request_id="ts", view_id="view"),
        ProvideSecret(request_id="sec", connection="main", secret=None),
        Grab(request_id="g", view_id="view"),
        CloseView(request_id="c", view_id="view"),
        Ping(request_id="p"),
        Shutdown(request_id="bye"),
        Response(request_id="r", ok=False, error="stale", detail="at revision 1"),
        Ready(
            child_pid=9,
            python="3.9.2",
            qt_version="6.8.3",
            pyside_version="6.8.3",
            freecadgui=False,
        ),
        Log(
            view_id="view",
            stream="stdout",
            level="info",
            text="hello",
            ts_ms=1,
            source=SourceRef(object_name="title", rule_path=("cbcsValidate", 0)),
        ),
        ViewClosed(view_id="view", reason="host"),
        ErrorReport(view_id="view", code="FB602", message="nope", traceback="trace"),
        CrashReport(message="died", traceback="trace"),
        NeedSecret(view_id="view", connection="main"),
    ]


@pytest.mark.unit
@pytest.mark.parametrize("message", _samples(), ids=lambda message: type(message).__name__)
def test_frame_round_trip(message):
    frame = encode_frame(message)
    assert frame.startswith(FRAME_PREFIX)
    assert frame.endswith("\n")
    frame.encode("ascii")
    assert decode_line(frame[:-1]) == message


@pytest.mark.unit
def test_unknown_field_is_ignored_and_optional_field_defaults():
    line = FRAME_PREFIX + '{"request_id":"abc","type":"ping","z_extra":1}'
    decoded = decode_line(line)
    assert decoded == Ping(request_id="abc")


@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    ["{", "null", "[]", '{"type":"nope"}', '{"type":"ready","child_pid":true}'],
)
def test_prefixed_garbage_is_a_protocol_violation(body):
    decoded = decode_line(FRAME_PREFIX + body)
    assert isinstance(decoded, ProtocolViolation)


@pytest.mark.unit
def test_noise_line_and_partial_chunks():
    assert decode_line("hello from C") == NoiseLine(stream="stdout", text="hello from C")
    decoder = FrameDecoder()
    frame = encode_frame(Ping(request_id="p"))
    assert decoder.feed(frame[:8]) == ()
    assert decoder.pending
    assert decoder.feed(frame[8:]) == (Ping(request_id="p"),)


@pytest.mark.unit
def test_non_ascii_frame_is_a_protocol_violation():
    decoded = decode_line(FRAME_PREFIX + '{"type":"ping","request_id":"héllo"}')
    assert isinstance(decoded, ProtocolViolation)


@pytest.mark.unit
def test_oversized_chunk_is_a_violation_and_the_decoder_recovers():
    decoder = FrameDecoder()
    huge = "x" * (MAX_FRAME_BYTES + 1)
    overflow = decoder.feed(huge)
    assert isinstance(overflow[0], ProtocolViolation)
    assert decoder.pending == ""
    assert decoder.feed(encode_frame(Ping(request_id="after"))) == (Ping(request_id="after"),)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("names", "patched", "structural", "expected"),
    [
        (("title", "ok"), ("title",), False, "patch"),
        (("title", "title"), ("title",), False, "load"),
        (("title",), ("title",), True, "load"),
        (("title",), (), False, "load"),
        (("title",), ("missing",), False, "load"),
    ],
)
def test_select_form_refresh(names, patched, structural, expected):
    assert (
        select_form_refresh(names=names, patched_names=patched, structural=structural)
        == expected
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", PREWARM_DEFAULT),
        ("0", False),
        ("off", False),
        ("false", False),
        ("no", False),
        ("1", True),
        ("on", True),
        ("yes", True),
    ],
)
def test_prewarm_env(raw, expected):
    assert prewarm_from_environ({"CBCS_FORM_PREVIEW_PREWARM": raw}) is expected
