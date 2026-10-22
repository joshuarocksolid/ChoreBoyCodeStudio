"""Preview child and pool, using this interpreter as the child."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import textwrap
import threading
import time
import uuid
from dataclasses import replace
from typing import List, Optional

import pytest

from app.features.form_builder.engine.ipc.protocol import (
    FRAME_PREFIX,
    PROTOCOL_NAME,
    Appearance,
    ErrorReport,
    Hello,
    LoadForm,
    Log,
    Ping,
    PromotedClass,
    Response,
    decode_line,
    encode_frame,
)
from app.features.form_builder.engine.ipc.timing import DirectorConfig
from app.features.form_builder.qtside.preview.launch import (
    apprun_preview_command,
    current_runtime_python,
    python_preview_command,
    repo_root,
)
from app.features.form_builder.qtside.preview.pool import PreviewPool

_LABEL = textwrap.dedent(
    """
    from PySide6.QtWidgets import QLabel

    class Ui_Form(object):
        def setupUi(self, Form):
            Form.setObjectName("Form")
            label = QLabel(Form)
            label.setObjectName("title")
            label.setText("hello")
    """
)

_BOOM_UI = textwrap.dedent(
    """\
    <?xml version="1.0" encoding="UTF-8"?>
    <ui version="4.0">
     <class>Form</class>
     <widget class="QWidget" name="Form">
      <widget class="Boom" name="boom"/>
     </widget>
     <customwidgets>
      <customwidget>
       <class>Boom</class>
       <extends>QWidget</extends>
       <header>boom_mod</header>
      </customwidget>
     </customwidgets>
    </ui>
    """
)


def _pump(qapp, predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _config() -> DirectorConfig:
    return DirectorConfig(
        handshake_timeout=20.0,
        request_timeout=10.0,
        shutdown_grace=0.4,
        ping_interval=30.0,
        prewarm=True,
    )


def _kill_preview(pid: int) -> None:
    """Kill the preview session, including an AppRun shell's grandchild."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        os.kill(pid, signal.SIGKILL)


def _configured_preview_command() -> List[str]:
    """Python child, or AppRun when ``CBCS_FB_APPRUN`` / ``CBCS_FB_APPRUN_11`` is a file."""
    primary = os.environ.get("CBCS_FB_APPRUN", "").strip()
    configured = primary or os.environ.get("CBCS_FB_APPRUN_11", "").strip()
    root = repo_root()
    if not configured:
        return python_preview_command(current_runtime_python(), root)
    if not os.path.isfile(configured):
        pytest.skip("CBCS_FB_APPRUN is not a file: %s" % configured)
    return apprun_preview_command(configured, root)


def _make_pool(
    config: Optional[DirectorConfig] = None,
    command: Optional[List[str]] = None,
) -> PreviewPool:
    root = repo_root()
    return PreviewPool(
        command=command or python_preview_command(current_runtime_python(), root),
        config=config or _config(),
        root=root,
    )


def _load(
    view_id: str, *, source, root, entries, xml=None, promoted=(), revision=1
) -> LoadForm:
    return LoadForm(
        request_id=uuid.uuid4().hex,
        view_id=view_id,
        form_path="form.ui",
        module_name="ui_%s" % view_id,
        module_source=source,
        ui_xml=xml,
        project_root=root,
        sys_path=tuple(entries),
        appearance=Appearance(),
        keep_values=False,
        revision=revision,
        promoted=tuple(promoted),
    )


def _wait(pool, qapp, message, timeout=15.0):
    box = {}

    def on_response(item) -> None:
        if isinstance(item, Response) and item.request_id == message.request_id:
            box["item"] = item

    pool.request(message, on_response)
    assert _pump(qapp, lambda: "item" in box, timeout), pool.status()
    return box["item"]


@pytest.fixture
def pool(qapp):
    del qapp
    created = _make_pool()
    yield created
    created.shutdown()


@pytest.mark.integration
@pytest.mark.pain("P-11")
def test_two_forms_share_one_warm_child(pool, qapp):
    host = os.getpid()
    started = time.monotonic()
    pool.note_form_opened()
    assert _pump(qapp, lambda: pool.status().state == "ready", 20), pool.status()
    cold = time.monotonic() - started
    first = _wait(pool, qapp, _load("one", source=_LABEL, root=None, entries=()))
    warm_started = time.monotonic()
    second = _wait(pool, qapp, _load("two", source=_LABEL, root=None, entries=()))
    warm = time.monotonic() - warm_started
    print("PREVIEW_TIMING cold_s=%.3f warm_s=%.3f" % (cold, warm))
    assert first.ok and second.ok
    assert first.result["texts"]["title"] == "hello"
    assert len(pool.spawn_monotonic) == 1
    assert pool.status().child_pid
    assert os.getpid() == host


@pytest.mark.integration
@pytest.mark.pain("P-7")
def test_custom_widget_init_error_is_fb602_and_the_editor_stays_up(
    pool, qapp, tmp_path
):
    host = os.getpid()
    module = tmp_path / "boom_mod.py"
    module.write_text(
        "from PySide6.QtWidgets import QWidget\n"
        "class Boom(QWidget):\n"
        "    def __init__(self, parent=None):\n"
        "        raise RuntimeError('boom-init')\n",
        encoding="utf-8",
    )
    reports = []
    pool.subscribe(
        None,
        lambda item: reports.append(item) if isinstance(item, ErrorReport) else None,
    )
    response = _wait(
        pool,
        qapp,
        _load(
            "boom-view",
            source=None,
            root=str(tmp_path),
            entries=(str(tmp_path),),
            xml=_BOOM_UI,
            promoted=(PromotedClass("Boom", "boom_mod", "QWidget"),),
        ),
    )
    assert response.ok, response.detail
    assert "boom" in response.result["stubs"]
    assert _pump(qapp, lambda: any(item.code == "FB602" for item in reports), 5)
    assert pool.status().state == "ready"
    assert os.getpid() == host


@pytest.mark.integration
def test_user_input_does_not_eat_frames(qapp):
    pool = _make_pool(command=_configured_preview_command())
    try:
        source = textwrap.dedent(
            """
            import sys
            from PySide6.QtWidgets import QLabel

            class Ui_Form(object):
                def setupUi(self, Form):
                    label = QLabel(Form)
                    label.setObjectName("out")
                    label.setText(repr(sys.stdin.readline()))
            """
        )
        response = _wait(
            pool, qapp, _load("stdin", source=source, root=None, entries=())
        )
        assert response.ok, response.detail
        assert response.result["texts"]["out"] == "''"
        pong = _wait(pool, qapp, Ping(request_id=uuid.uuid4().hex))
        assert pong.ok
        assert pong.result == "pong"
    finally:
        pool.shutdown()


@pytest.mark.integration
def test_stdout_noise_does_not_break_frames(pool, qapp):
    source = textwrap.dedent(
        """
        import os
        from PySide6.QtWidgets import QLabel

        class Ui_Form(object):
            def setupUi(self, Form):
                os.write(1, b"BANNER\\n")
                print("hello-user")
                label = QLabel(Form)
                label.setObjectName("title")
                label.setText("still-here")
        """
    )
    logs = []
    pool.subscribe(
        None, lambda item: logs.append(item) if isinstance(item, Log) else None
    )
    response = _wait(pool, qapp, _load("noise", source=source, root=None, entries=()))
    assert response.ok, response.detail
    assert response.result["texts"]["title"] == "still-here"
    assert _pump(
        qapp, lambda: any("BANNER" in line for line in pool.stderr_tail()), 5
    ), pool.stderr_tail()
    assert any("hello-user" in item.text for item in logs)
    assert pool.status().state == "ready"


@pytest.mark.integration
def test_project_modules_are_dropped_when_the_root_changes(pool, qapp, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    sample = project_a / "samplemod.py"
    sample.write_text("TOKEN = 'one'\n", encoding="utf-8")
    source = textwrap.dedent(
        """
        import samplemod
        from PySide6.QtWidgets import QLabel

        class Ui_Form(object):
            def setupUi(self, Form):
                label = QLabel(Form)
                label.setObjectName("token")
                label.setText(samplemod.TOKEN)
        """
    )
    other = textwrap.dedent(
        """
        from PySide6.QtWidgets import QLabel

        class Ui_Form(object):
            def setupUi(self, Form):
                label = QLabel(Form)
                label.setObjectName("title")
                label.setText("b")
        """
    )
    first = _wait(
        pool,
        qapp,
        _load("view-a", source=source, root=str(project_a), entries=(str(project_a),)),
    )
    assert first.ok, first.detail
    assert first.result["texts"]["token"] == "one"
    sample.write_text("TOKEN = 'two'\n", encoding="utf-8")
    second = _wait(
        pool,
        qapp,
        _load("view-b", source=other, root=str(project_b), entries=(str(project_b),)),
    )
    assert second.ok, second.detail
    third = _wait(
        pool,
        qapp,
        _load("view-a2", source=source, root=str(project_a), entries=(str(project_a),)),
    )
    assert third.ok, third.detail
    assert third.result["texts"]["token"] == "two"


@pytest.mark.integration
@pytest.mark.pain("P-11")
@pytest.mark.timeout(60)
def test_infinite_loop_is_killed_and_the_editor_stays_up(qapp):
    host = os.getpid()
    pool = _make_pool(
        replace(
            _config(),
            ping_interval=0.25,
            missed_pings=2,
            request_timeout=30.0,
            backoff=(30.0, 30.0, 30.0, 30.0),
        ),
        command=_configured_preview_command(),
    )
    try:
        source = textwrap.dedent(
            """
            while True:
                pass

            class Ui_Form(object):
                def setupUi(self, Form):
                    pass
            """
        )

        box = []

        def on_response(item) -> None:
            if isinstance(item, Response) and not item.ok:
                box.append(item)
                pool.shutdown()

        message = _load("hung", source=source, root=None, entries=())
        pool.request(message, on_response)
        assert _pump(qapp, lambda: bool(box), 20), pool.status()
        assert box[0].error == "crashed"
        assert any(item.code == "FB601" for item in pool.diagnostics())
        assert os.getpid() == host
        assert pool.status().state in {"stopped", "stopping"}
    finally:
        pool.shutdown()


@pytest.mark.integration
@pytest.mark.pain("P-11")
@pytest.mark.timeout(45)
def test_abort_reports_a_crash_and_the_editor_stays_up(qapp):
    host = os.getpid()
    pool = _make_pool(
        replace(_config(), backoff=(30.0,), request_timeout=15.0),
        command=_configured_preview_command(),
    )
    try:
        source = textwrap.dedent(
            """
            import os
            from PySide6.QtWidgets import QWidget

            class Ui_Form(object):
                def setupUi(self, Form):
                    os.abort()
            """
        )
        response = _wait(
            pool, qapp, _load("abort", source=source, root=None, entries=()), timeout=20
        )
        assert response.error == "crashed"
        detail = response.detail or ""
        assert "exit -6" in detail or "exit 134" in detail, detail
        assert any(item.code == "FB601" for item in pool.diagnostics())
        assert os.getpid() == host
        pool.shutdown()
    finally:
        pool.shutdown()


@pytest.mark.integration
@pytest.mark.pain("P-11")
@pytest.mark.timeout(120)
def test_kill_follows_backoff_and_retry_brings_the_form_back(qapp):
    host = os.getpid()
    pool = _make_pool(
        replace(
            _config(),
            backoff=(0.0, 1.0, 4.0, 15.0),
            crash_window=120.0,
            request_timeout=20.0,
            handshake_timeout=20.0,
        ),
        command=_configured_preview_command(),
    )
    try:
        first = _wait(pool, qapp, _load("kept", source=_LABEL, root=None, entries=()))
        assert first.ok, first.detail
        gaps = []
        for delay in (0.0, 1.0, 4.0, 15.0):
            crashes = len(pool.crash_monotonic)
            spawns = len(pool.spawn_monotonic)
            assert _pump(
                qapp,
                lambda: pool.status().state == "ready"
                and pool.status().child_pid is not None,
                20,
            ), pool.status()
            pid = pool.status().child_pid
            assert pid is not None
            _kill_preview(pid)
            assert _pump(qapp, lambda: len(pool.crash_monotonic) > crashes, 10)
            assert _pump(qapp, lambda: len(pool.spawn_monotonic) > spawns, delay + 8)
            gaps.append(pool.spawn_monotonic[-1] - pool.crash_monotonic[-1])
        assert gaps[0] < 0.75
        assert abs(gaps[1] - 1.0) < 0.75
        assert abs(gaps[2] - 4.0) < 0.75
        assert abs(gaps[3] - 15.0) < 1.5
        crashes = len(pool.crash_monotonic)
        spawns = len(pool.spawn_monotonic)
        assert _pump(
            qapp,
            lambda: pool.status().state == "ready"
            and pool.status().child_pid is not None,
            20,
        )
        pid = pool.status().child_pid
        assert pid is not None
        _kill_preview(pid)
        assert _pump(
            qapp, lambda: pool.status().state == "circuit_open", 10
        ), pool.status()
        assert len(pool.spawn_monotonic) == spawns
        assert len(pool.crash_monotonic) > crashes
        pool.retry()
        assert _pump(qapp, lambda: pool.status().state == "ready", 20), pool.status()
        restored = _wait(
            pool, qapp, _load("kept", source=_LABEL, root=None, entries=())
        )
        assert restored.ok, restored.detail
        assert os.getpid() == host
    finally:
        pool.shutdown()


@pytest.mark.integration
@pytest.mark.timeout(30)
def test_child_exits_3_on_a_protocol_mismatch():
    env = dict(os.environ)
    env["CBCS_QT_API"] = "pyside6"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    root = repo_root()
    previous = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not previous else root + os.pathsep + previous
    proc = subprocess.Popen(
        python_preview_command(current_runtime_python(), root),
        cwd=root,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )
    lines: queue.Queue = queue.Queue()

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=_read, daemon=True).start()
    try:
        ready = _next_frame(lines, 20)
        assert type(ready).__name__ == "Ready"
        assert proc.stdin is not None
        proc.stdin.write(
            encode_frame(
                Hello(
                    request_id="bad",
                    protocol=PROTOCOL_NAME,
                    version=99,
                    session_token="tok",
                    host_pid=os.getpid(),
                )
            )
        )
        proc.stdin.flush()
        answer = _next_frame(lines, 10)
        assert isinstance(answer, Response)
        assert answer.error == "protocol_mismatch"
        assert proc.wait(timeout=10) == 3
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait(timeout=5)


@pytest.mark.integration
def test_fixed_promoted_module_loads_after_fb602(pool, qapp, tmp_path):
    module = tmp_path / "boom_mod.py"
    module.write_text("raise ImportError('missing-boom')\n", encoding="utf-8")
    reports = []
    pool.subscribe(
        None,
        lambda item: reports.append(item) if isinstance(item, ErrorReport) else None,
    )
    first = _wait(
        pool,
        qapp,
        _load(
            "boom-view",
            source=None,
            root=str(tmp_path),
            entries=(str(tmp_path),),
            xml=_BOOM_UI,
            promoted=(PromotedClass("Boom", "boom_mod", "QWidget"),),
        ),
    )
    assert first.ok, first.detail
    assert "boom" in first.result["stubs"]
    assert _pump(qapp, lambda: any(item.code == "FB602" for item in reports), 5)
    module.write_text(
        "from PySide6.QtWidgets import QLabel\n"
        "class Boom(QLabel):\n"
        "    def __init__(self, parent=None):\n"
        "        super().__init__(parent)\n"
        "        self.setText('real-boom')\n",
        encoding="utf-8",
    )
    before = len(reports)
    second = _wait(
        pool,
        qapp,
        _load(
            "boom-view",
            source=None,
            root=str(tmp_path),
            entries=(str(tmp_path),),
            xml=_BOOM_UI,
            promoted=(PromotedClass("Boom", "boom_mod", "QWidget"),),
            revision=2,
        ),
    )
    assert second.ok, second.detail
    assert "boom" not in second.result["stubs"]
    assert second.result["texts"]["boom"] == "real-boom"
    assert not any(item.code == "FB602" for item in reports[before:])


@pytest.mark.integration
def test_raising_slot_is_fb604_and_the_child_stays_ready(pool, qapp):
    source = textwrap.dedent(
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QLabel

        class Ui_Form(object):
            def setupUi(self, Form):
                label = QLabel(Form)
                label.setObjectName("title")
                label.setText("up")
                QTimer.singleShot(0, lambda: 1/0)
        """
    )
    reports = []
    pool.subscribe(
        None,
        lambda item: reports.append(item) if isinstance(item, ErrorReport) else None,
    )
    pool.note_form_opened()
    assert _pump(qapp, lambda: pool.status().state == "ready", 20), pool.status()
    pid = pool.status().child_pid
    spawns = len(pool.spawn_monotonic)
    response = _wait(
        pool, qapp, _load("slot-view", source=source, root=None, entries=())
    )
    assert response.ok, response.detail
    assert _pump(
        qapp,
        lambda: any(
            item.code == "FB604" and item.view_id == "slot-view" for item in reports
        ),
        5,
    ), [item.code for item in reports]
    assert pool.status().state == "ready"
    assert pool.status().child_pid == pid
    assert len(pool.spawn_monotonic) == spawns
    pong = _wait(pool, qapp, Ping(request_id=uuid.uuid4().hex))
    assert pong.ok
    assert pong.result == "pong"


@pytest.mark.integration
def test_failed_load_still_purges_the_new_project_root(pool, qapp, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    module = project / "widgetmod.py"
    module.write_text(
        "MARKER = 'first'\nclass Widget(object):\n    pass\n", encoding="utf-8"
    )
    failed = _wait(
        pool,
        qapp,
        _load(
            "view",
            source="(\n",
            root=str(project),
            entries=(str(project),),
            promoted=(PromotedClass("Widget", "widgetmod", "QWidget"),),
        ),
    )
    assert not failed.ok
    module.write_text(
        "MARKER = 'second'\nclass Widget(object):\n    pass\n", encoding="utf-8"
    )
    source = textwrap.dedent(
        """
        import widgetmod
        from PySide6.QtWidgets import QLabel

        class Ui_Form(object):
            def setupUi(self, Form):
                label = QLabel(Form)
                label.setObjectName("token")
                label.setText(widgetmod.MARKER)
        """
    )
    loaded = _wait(
        pool,
        qapp,
        _load(
            "view",
            source=source,
            root=str(project),
            entries=(str(project),),
            revision=2,
        ),
    )
    assert loaded.ok, loaded.detail
    assert loaded.result["texts"]["token"] == "second"


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.timeout(45)
def test_stdin_eof_exits_a_child_stuck_in_user_code():
    root = repo_root()
    env = dict(os.environ)
    env["CBCS_QT_API"] = "pyside6"
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    previous = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = root if not previous else root + os.pathsep + previous
    proc = subprocess.Popen(
        _configured_preview_command(),
        cwd=root,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    lines: queue.Queue = queue.Queue()

    def _read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=_read, daemon=True).start()
    try:
        ready = _next_frame(lines, 20)
        assert type(ready).__name__ == "Ready"
        assert proc.stdin is not None
        proc.stdin.write(
            encode_frame(
                _load(
                    "hung",
                    source="while True:\n    pass\n",
                    root=None,
                    entries=(),
                )
            )
        )
        proc.stdin.close()
        try:
            code = proc.wait(timeout=7.5)
        except subprocess.TimeoutExpired:
            err = ""
            if proc.stderr is not None:
                err = proc.stderr.read()
            raise AssertionError("child still running 7.5s after stdin EOF: %s" % err)
        assert code == 0
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.wait(timeout=5)


def _next_frame(lines: queue.Queue, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=0.2)
        except queue.Empty:
            continue
        if line is None:
            break
        if not str(line).startswith(FRAME_PREFIX):
            continue
        decoded = decode_line(str(line).rstrip("\r\n"))
        if type(decoded).__name__ != "NoiseLine":
            return decoded
    raise AssertionError("preview child sent no frame")
