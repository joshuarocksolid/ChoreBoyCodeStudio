"""Preview director lifecycle, driven with a fake clock and no process."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.features.form_builder.engine.ipc.director import (
    Deliver,
    KillChild,
    PreviewDirector,
    SpawnChild,
    WriteFrame,
)
from app.features.form_builder.engine.ipc.protocol import (
    FRAME_PREFIX,
    Appearance,
    ErrorReport,
    Grab,
    Hello,
    LoadForm,
    Ready,
    Response,
    decode_line,
    encode_frame,
)
from app.features.form_builder.engine.ipc.timing import (
    SHUTDOWN_GRACE_SECONDS,
    DirectorConfig,
)


def _form(request_id: str, view_id: str) -> LoadForm:
    return LoadForm(
        request_id=request_id,
        view_id=view_id,
        form_path="form.ui",
        module_name="ui_form",
        module_source=None,
        ui_xml="<ui/>",
        project_root=None,
        sys_path=(),
        appearance=Appearance(),
        keep_values=False,
        revision=1,
    )


def _written(effects):
    found = []
    for effect in effects:
        if isinstance(effect, WriteFrame):
            # splitlines() treats the frame's leading record separator as a break.
            for line in effect.text.split("\n"):
                if line:
                    found.append(decode_line(line))
    return found


def _codes(effects):
    return [
        effect.message.code
        for effect in effects
        if isinstance(effect, Deliver) and isinstance(effect.message, ErrorReport)
    ]


def _has(effects, kind) -> bool:
    return any(isinstance(effect, kind) for effect in effects)


def _ready_message() -> Ready:
    return Ready(
        child_pid=4,
        python="3.9.2",
        qt_version="6.8.3",
        pyside_version="6.8.3",
        freecadgui=False,
    )


def _handshake(director: PreviewDirector, spawn_effects, now: float):
    hello = next(item for item in _written(spawn_effects) if isinstance(item, Hello))
    director.on_stdout(now, encode_frame(_ready_message()))
    return director.on_stdout(
        now,
        encode_frame(
            Response(request_id=hello.request_id, ok=True, result={"ready": True})
        ),
    )


@pytest.mark.unit
def test_backoff_schedule_then_circuit_and_retry():
    director = PreviewDirector(
        host_pid=7,
        config=DirectorConfig(prewarm=True, handshake_timeout=100, request_timeout=100),
    )
    assert _has(director.note_form_opened(0), SpawnChild)

    died = director.on_exit(0, -6)
    assert _has(died, SpawnChild)
    assert "FB601" in _codes(died)

    died = director.on_exit(0, -6)
    assert not _has(died, SpawnChild)
    assert director.status(0).next_restart_in == 1

    assert _has(director.advance(1), SpawnChild)
    died = director.on_exit(1, -6)
    assert director.status(1).next_restart_in == 4

    assert _has(director.advance(5), SpawnChild)
    died = director.on_exit(5, -6)
    assert director.status(5).next_restart_in == 15

    assert _has(director.advance(20), SpawnChild)
    died = director.on_exit(20, -6)
    assert director.status(20).state == "circuit_open"
    assert "FB605" in _codes(died)
    assert director.advance(200) == ()

    assert _has(director.retry(200), SpawnChild)
    assert director.status(200).state == "starting"


@pytest.mark.unit
def test_old_crashes_leave_the_window():
    director = PreviewDirector(
        host_pid=1,
        config=DirectorConfig(prewarm=True, backoff=(0.0, 50.0), crash_window=30.0),
    )
    director.note_form_opened(0)
    director.on_exit(0, 1)
    director.on_exit(10, 1)
    assert director.status(10).crashes_in_window == 2
    assert director.status(35).crashes_in_window == 1

    assert _has(director.advance(60), SpawnChild)
    died = director.on_exit(60, 1)
    assert director.status(55).crashes_in_window == 1
    assert _has(died, SpawnChild)


@pytest.mark.unit
def test_protocol_mismatch_stays_open_when_the_user_retries():
    director = PreviewDirector(host_pid=1, config=DirectorConfig(prewarm=True))
    spawned = director.note_form_opened(0)
    hello = next(item for item in _written(spawned) if isinstance(item, Hello))
    bad = director.on_stdout(
        1,
        encode_frame(
            Response(
                request_id=hello.request_id,
                ok=False,
                error="protocol_mismatch",
                detail="child version 1",
            )
        ),
    )
    assert "FB603" in _codes(bad)
    director.on_exit(1, 3)
    assert director.status(1).state == "circuit_open"
    assert director.retry(2) == ()
    assert director.status(2).state == "circuit_open"


@pytest.mark.unit
def test_bare_exit_3_is_a_crash():
    director = PreviewDirector(
        host_pid=1,
        config=DirectorConfig(prewarm=True, backoff=(30.0,)),
    )
    director.note_form_opened(0)
    effects = director.on_exit(1, 3)
    assert "FB601" in _codes(effects)
    assert not _has(effects, SpawnChild)
    assert director.status(1).state == "backoff"
    assert _has(director.retry(2), SpawnChild)


@pytest.mark.unit
def test_load_during_open_circuit_is_what_retry_sends():
    director = PreviewDirector(
        host_pid=1,
        config=DirectorConfig(prewarm=False, backoff=()),
    )
    spawned = director.request(0, _form("load-1", "view"))
    ready = _handshake(director, spawned, 1)
    sent = next(item for item in _written(ready) if isinstance(item, LoadForm))
    director.on_stdout(
        1,
        encode_frame(Response(request_id=sent.request_id, ok=True, result={})),
    )
    director.on_exit(2, 1)
    assert director.status(2).state == "circuit_open"
    refused = director.request(3, replace(_form("load-2", "view"), revision=2))
    busy = [
        effect.message
        for effect in refused
        if isinstance(effect, Deliver) and isinstance(effect.message, Response)
    ]
    assert busy[0].ok is False
    assert busy[0].error == "busy"
    assert not _has(refused, SpawnChild)
    restarted = director.retry(4)
    assert _has(restarted, SpawnChild)
    ready = _handshake(director, restarted, 5)
    resent = [item for item in _written(ready) if isinstance(item, LoadForm)]
    assert [item.revision for item in resent] == [2]


@pytest.mark.unit
def test_three_protocol_violations_kill_the_child():
    director = PreviewDirector(host_pid=1, config=DirectorConfig(prewarm=True))
    spawned = director.note_form_opened(0)
    _handshake(director, spawned, 1)
    bad = FRAME_PREFIX + "{]\n"
    director.on_stdout(2, bad)
    director.on_stdout(2, bad)
    third = director.on_stdout(2, bad)
    assert _has(third, KillChild)
    assert "FB601" in _codes(third)


@pytest.mark.unit
def test_request_timeout_is_a_crash():
    director = PreviewDirector(
        host_pid=1,
        config=DirectorConfig(prewarm=True, request_timeout=20, ping_interval=1000),
    )
    spawned = director.note_form_opened(0)
    _handshake(director, spawned, 1)
    director.request(1, Grab(request_id="g", view_id="v"))
    effects = director.advance(21)
    assert _has(effects, KillChild)
    crashed = [
        effect.message
        for effect in effects
        if isinstance(effect, Deliver) and isinstance(effect.message, Response)
    ]
    assert crashed[0].request_id == "g"
    assert crashed[0].error == "crashed"


@pytest.mark.unit
def test_two_missed_pings_are_a_hang():
    director = PreviewDirector(
        host_pid=1,
        config=DirectorConfig(
            prewarm=False,
            ping_interval=5,
            missed_pings=2,
            request_timeout=100,
        ),
    )
    spawned = director.request(0, _form("load-1", "view"))
    ready = _handshake(director, spawned, 1)
    sent = next(item for item in _written(ready) if isinstance(item, LoadForm))
    director.on_stdout(
        1, encode_frame(Response(request_id=sent.request_id, ok=True, result={}))
    )
    director.advance(6)
    director.advance(11)
    effects = director.advance(16)
    assert _has(effects, KillChild)
    assert "FB601" in _codes(effects)


@pytest.mark.unit
def test_second_load_coalesces_the_one_still_waiting():
    director = PreviewDirector(host_pid=1, config=DirectorConfig(prewarm=False))
    spawned = director.request(0, _form("a", "view"))
    effects = director.request(0, _form("b", "view"))
    coalesced = [
        effect.message
        for effect in effects
        if isinstance(effect, Deliver) and isinstance(effect.message, Response)
    ]
    assert coalesced[0].request_id == "a"
    assert coalesced[0].result == {"coalesced": True}
    ready = _handshake(director, spawned, 1)
    sent = [item for item in _written(ready) if isinstance(item, LoadForm)]
    assert [item.request_id for item in sent] == ["b"]


@pytest.mark.unit
def test_prewarm_off_waits_for_the_first_request():
    director = PreviewDirector(host_pid=1, config=DirectorConfig(prewarm=False))
    assert director.note_form_opened(0) == ()
    assert director.status(0).state == "stopped"
    assert _has(director.request(1, _form("a", "view")), SpawnChild)


@pytest.mark.unit
def test_shutdown_does_not_report_a_crash():
    director = PreviewDirector(host_pid=1, config=DirectorConfig(prewarm=True))
    spawned = director.note_form_opened(0)
    _handshake(director, spawned, 1)
    effects = director.shutdown(2)
    assert _has(effects, WriteFrame)
    assert "FB601" not in _codes(effects)
    assert _has(director.advance(2 + SHUTDOWN_GRACE_SECONDS), KillChild)
    exited = director.on_exit(5, -15)
    assert exited == ()
    assert director.status(5).state == "stopped"


@pytest.mark.unit
def test_crash_reloads_the_last_successful_load():
    director = PreviewDirector(
        host_pid=1,
        config=DirectorConfig(prewarm=False, handshake_timeout=30, request_timeout=30),
    )
    spawned = director.request(0, _form("a", "view"))
    ready = _handshake(director, spawned, 1)
    sent = next(item for item in _written(ready) if isinstance(item, LoadForm))
    director.on_stdout(
        1, encode_frame(Response(request_id=sent.request_id, ok=True, result={}))
    )
    died = director.on_exit(2, -11)
    assert _has(died, SpawnChild)
    reloaded = _handshake(director, died, 3)
    again = [item for item in _written(reloaded) if isinstance(item, LoadForm)]
    assert len(again) == 1
    assert again[0].view_id == "view"
    assert again[0].request_id != "a"


@pytest.mark.unit
def test_clean_exit_with_no_views_stops():
    director = PreviewDirector(host_pid=1, config=DirectorConfig(prewarm=True))
    spawned = director.note_form_opened(0)
    _handshake(director, spawned, 1)
    assert director.on_exit(2, 0) == ()
    assert director.status(2).state == "stopped"
