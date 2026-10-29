# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Own classes in the preview child (M5.4, UX-CUST-008, 009; CONTRACTS 10.4; P-7 and the security rule)."""

from __future__ import annotations

import sys
import textwrap
import uuid
from pathlib import Path
from typing import List

import pytest

from app.features.form_builder.engine.ipc.protocol import (
    Appearance,
    ErrorReport,
    LoadForm,
    PromotedClass,
    Response,
)
from app.features.form_builder.engine.ipc.timing import DirectorConfig
from app.features.form_builder.integration import preview_notice
from app.features.form_builder.qtside.preview.child import modules
from app.features.form_builder.qtside.preview.launch import current_runtime_python, python_preview_command, repo_root
from app.features.form_builder.qtside.preview.pool import PreviewPool
from tests.form_builder.preview.test_child_and_pool import _pump

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


def _write(root: Path, name: str, body: str) -> None:
    path = root / (name.replace(".", "/") + ".py")
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "__init__.py").touch()
    path.write_text(textwrap.dedent(body), encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.syspath_prepend(str(tmp_path))
    yield tmp_path
    for name in list(sys.modules):
        if name.split(".")[0] in ("shopw", "okmod"):
            sys.modules.pop(name, None)
    modules.purge_project_modules(str(tmp_path))


def test_a_class_that_raises_becomes_a_stand_in_with_its_file_and_line(project: Path) -> None:
    _write(
        project,
        "shopw.broken",
        """\
        from PySide6.QtWidgets import QLabel

        class Broken(QLabel):
            def __init__(self, parent=None):
                super().__init__(parent)
                raise RuntimeError("the till is closed")
        """,
    )
    cls, error = modules.install_promoted(PromotedClass("Broken", "shopw.broken", "QLabel"))
    assert cls._cbcs_stub is True and cls.__name__ == "Broken"
    assert type(error).__name__ == "RuntimeError"
    assert str(error).splitlines()[0] == "the till is closed"
    assert 'broken.py", line 6' in str(error)
    # The generated module's own import now gets the stand-in, not the code that failed.
    imported = __import__("shopw.broken", fromlist=["Broken"])
    assert imported.Broken is cls
    # The next load drops it, so an edited file is imported again.
    modules.purge_project_modules(str(project))
    assert "shopw.broken" not in sys.modules


def test_a_class_that_hangs_or_quits_falls_back_and_the_child_goes_on(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modules, "CLASS_SECONDS", 0.3)
    _write(
        project,
        "shopw.hangs",
        """\
        from PySide6.QtWidgets import QWidget

        class Spin(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                while True:
                    pass

        class Quits(QWidget):
            def __init__(self, parent=None):
                super().__init__(parent)
                raise SystemExit(3)
        """,
    )
    cls, error = modules.install_promoted(PromotedClass("Spin", "shopw.hangs", "QWidget"))
    assert cls._cbcs_stub is True and type(error).__name__ == "ClassTimedOut"
    cls, error = modules.install_promoted(PromotedClass("Quits", "shopw.hangs", "QWidget"))
    assert cls._cbcs_stub is True and type(error).__name__ == "SystemExit"
    # Both stand-ins answer the one fake module.
    fake = sys.modules["shopw.hangs"]
    assert fake.Spin._cbcs_stub and fake.Quits._cbcs_stub


def test_the_whole_load_has_a_time_budget(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modules, "CLASS_SECONDS", 0.2)
    monkeypatch.setattr(modules, "LOAD_SECONDS", 0.3)
    _write(project, "shopw.slow", "import time\ntime.sleep(5)\n")
    modules.purge_project_modules(str(project))
    started = __import__("time").monotonic()
    for index in range(4):
        cls, error = modules.install_promoted(PromotedClass("C%d" % index, "shopw.slow", "QWidget"))
        assert cls._cbcs_stub is True and error is not None
    assert __import__("time").monotonic() - started < 2.0


def test_a_good_class_next_to_a_failing_one_in_the_same_module_still_imports(project: Path) -> None:
    _write(
        project,
        "okmod.pair",
        """\
        from PySide6.QtWidgets import QLabel

        class Good(QLabel):
            pass

        class Bad(QLabel):
            def __init__(self, parent=None):
                raise ValueError("bad")
        """,
    )
    good, error = modules.install_promoted(PromotedClass("Good", "okmod.pair", "QLabel"))
    assert error is None and not getattr(good, "_cbcs_stub", False)
    bad, error = modules.install_promoted(PromotedClass("Bad", "okmod.pair", "QLabel"))
    assert bad._cbcs_stub is True
    fake = sys.modules["okmod.pair"]
    assert fake.Good is good and fake.Bad is bad


def test_no_module_means_a_stand_in_and_an_import_never_happens(project: Path) -> None:
    cls, error = modules.install_promoted(PromotedClass("Anything", "", "QPushButton"))
    assert cls._cbcs_stub is True and error is None
    for hostile in ("os.system('x')", "..up", "a b"):
        cls, error = modules.install_promoted(PromotedClass("X", hostile, "QWidget"))
        assert cls._cbcs_stub is True and type(error).__name__ == "ImportError"


# ----------------------------------------------------------------------------- host + a real child

_SHOP = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Till</class>
 <widget class="QWidget" name="Till">
  <layout class="QVBoxLayout" name="box">
   <item><widget class="QLabel" name="totalLabel"/></item>
   <item><widget class="QLabel" name="hangLabel"/></item>
  </layout>
 </widget>
 <customwidgets>
  <customwidget><class>TillDisplay</class><extends>QLabel</extends><header location="local">shopw/till.h</header></customwidget>
  <customwidget><class>Spinner</class><extends>QLabel</extends><header location="local">shopw/spin.h</header></customwidget>
 </customwidgets>
 <resources/>
 <connections/>
</ui>
""".replace('name="totalLabel"', 'name="totalLabel"').replace(
    '<widget class="QLabel" name="totalLabel"/>', '<widget class="TillDisplay" name="totalLabel"/>'
).replace('<widget class="QLabel" name="hangLabel"/>', '<widget class="Spinner" name="hangLabel"/>')


def _surface() -> object:
    class _Bar:
        shown: List[str] = []

        def show_choices(self, text, choices):  # noqa: ANN001, ANN201
            self.shown.append(text)

        def isVisible(self):  # noqa: ANN201, N802
            return False

        def dismiss(self):  # noqa: ANN201
            return None

    class _Surface:
        def __init__(self) -> None:
            self._notice = _Bar()
            self.said: List[str] = []
            self._preview_listener = None

        def narrate(self, sentence: str) -> None:
            self.said.append(sentence)

        def request_preview(self, path: str) -> None:
            return None

    return _Surface()


def test_a_hanging_class_is_a_stand_in_in_a_real_child_and_the_preview_stays_open(tmp_path: Path) -> None:
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.session import FormSession

    root = tmp_path / "shop"
    _write(
        root,
        "shopw.till",
        """\
        from PySide6.QtWidgets import QLabel

        class TillDisplay(QLabel):
            def text(self):
                return "till:" + super().text()
        """,
    )
    _write(
        root,
        "shopw.spin",
        """\
        from PySide6.QtWidgets import QLabel

        class Spinner(QLabel):
            def __init__(self, parent=None):
                super().__init__(parent)
                while True:
                    pass
        """,
    )
    (root / "forms").mkdir()
    path = str(root / "forms" / "till.ui")
    scope = FormScope(
        kind="project", ui_path=path, project_root=str(root), generated_path=str(root / "forms" / "ui_till.py"),
        window_path=str(root / "forms" / "till_window.py"), module_name="forms.ui_till",
    )
    session = FormSession.open(_SHOP, path=path, scope=scope)
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(handshake_timeout=20.0, request_timeout=15.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True),
        root=repo_root(),
    )
    surface = _surface()
    notices = preview_notice.PreviewNotices(surface, session, pool)
    preview_notice.forget_noted()
    try:
        before = set(sys.modules)
        notices.preview(path)
        from app.qt.QtWidgets import QApplication

        assert _pump(QApplication.instance(), lambda: notices.last_response is not None, 40.0), pool.status()
        response = notices.last_response
        assert response.ok, response.detail
        assert response.result["stubs"] == ["hangLabel"]
        assert response.result["texts"]["totalLabel"] == "till:"
        assert pool.status().state == "ready"
        rows = [d for d in session.diagnostics.all() if d.code == "FB602"]
        assert len(rows) == 1
        assert rows[0].message.startswith("Preview used a stand-in for Spinner: ClassTimedOut")
        assert surface._notice.shown[0].startswith("Preview runs code from this project: TillDisplay (shopw/till.py), and 1 more.")
        assert not [name for name in set(sys.modules) - before if name.split(".")[0] == "shopw"]
    finally:
        notices.close()
        pool.shutdown()
        session.dispose()


def test_a_form_outside_a_project_sends_no_module_and_says_so(tmp_path: Path) -> None:
    from app.features.form_builder.engine.project.forms import FormScope
    from app.features.form_builder.engine.session import FormSession
    from app.qt.QtWidgets import QApplication

    path = str(tmp_path / "till.ui")
    session = FormSession.open(_SHOP, path=path, scope=FormScope(kind="external", ui_path=path))
    sent = preview_notice.build_load_form(session, path, "v")
    assert sent.project_root is None and sent.sys_path == () and sent.module_source is None
    assert [p.header_module for p in sent.promoted] == ["", ""]
    pool = PreviewPool(
        command=python_preview_command(current_runtime_python(), repo_root()),
        config=DirectorConfig(handshake_timeout=20.0, request_timeout=15.0, shutdown_grace=0.4, ping_interval=30.0, prewarm=True),
        root=repo_root(),
    )
    surface = _surface()
    notices = preview_notice.PreviewNotices(surface, session, pool)
    try:
        notices.preview(path)
        assert _pump(QApplication.instance(), lambda: notices.last_response is not None, 40.0)
        assert notices.last_response.ok, notices.last_response.detail
        assert sorted(notices.last_response.result["stubs"]) == ["hangLabel", "totalLabel"]
        assert surface.said[-1] == "Preview shows stand-ins for your own classes, because this form isn't in a project."
        assert surface._notice.shown == []
        assert not [d for d in session.diagnostics.all() if d.code == "FB602"]
    finally:
        notices.close()
        pool.shutdown()
        session.dispose()
