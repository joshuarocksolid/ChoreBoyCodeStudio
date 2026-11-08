"""QTest driver for the live Code Studio window.

Python 3.9. Screenshots use QScreen.grabWindow so a real X11 display is what
the file shows. A nested modal dialog is filled from a QTimer that fires
inside that dialog's event loop.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, List, Optional

from app.qt.QtCore import QTimer, Qt
from app.qt.QtGui import QGuiApplication
from app.qt.QtTest import QTest
from app.qt.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QWidget,
)


def _key(name: str):
    return getattr(getattr(Qt, "Key", Qt), name)


def _button():
    return getattr(getattr(Qt, "MouseButton", Qt), "LeftButton")


def _mods(*names: str):
    enum = getattr(Qt, "KeyboardModifier", Qt)
    value = getattr(enum, "NoModifier")
    for name in names:
        value = value | getattr(enum, name + "Modifier")
    return value


class Drive:
    def __init__(self, window, qapp, results: Path) -> None:
        self.window = window
        self.qapp = qapp
        self.results = results
        self.results.mkdir(parents=True, exist_ok=True)
        self.steps_path = results / "steps.md"
        self.n = 0
        self.failures: List[str] = []
        self.timings = {}
        self.disk_prompts: List[str] = []
        self.code_note = ""
        self.note = ""
        if not self.steps_path.exists():
            self.steps_path.write_text(
                "# M10.1b steps\n\n"
                "Each line is one user-visible step on the ChoreBoy display.\n\n",
                encoding="utf-8",
            )
        QTimer.singleShot(200, self._watch_symbol_dialog)

    def pump(self, rounds: int = 6) -> None:
        for _ in range(rounds):
            self.qapp.processEvents()
        self._dismiss_unexpected()

    def _dismiss_unexpected(self) -> None:
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QMessageBox):
            self.click_text(modal, "OK") or self.click_text(modal, "Cancel")
            self.qapp.processEvents()

    def _watch_symbol_dialog(self) -> None:
        """Ctrl+R with no form open runs Go to Symbol, which blocks the probe."""
        modal = QApplication.activeModalWidget()
        title = modal.windowTitle() if modal is not None else ""
        if modal is not None and "Go to Symbol" in title:
            if isinstance(modal, QDialog):
                modal.reject()
        QTimer.singleShot(200, self._watch_symbol_dialog)

    def wait_loaded(self, seconds: float = 25) -> bool:
        """The New Project dialog returns while the tree is still scanning."""

        def ready() -> bool:
            current = getattr(self.window, "_current_project_root", None)
            if not callable(current):
                return False
            return bool(current())

        return self.wait(ready, seconds)

    def find(self, name: str) -> Optional[QWidget]:
        """Prefer a visible widget. A closed dialog stays alive and would hide the next one.

        Two open forms each own an outline. ``findChild`` returns only the first,
        which is the form that is not on screen.
        """
        hidden = None
        for widget in QApplication.topLevelWidgets():
            candidates = []
            if widget.objectName() == name:
                candidates.append(widget)
            candidates.extend(widget.findChildren(QWidget, name))
            for candidate in candidates:
                if candidate.isVisible():
                    return candidate
                hidden = candidate
        return hidden

    def action(self, name: str):
        from app.qt.QtWidgets import QAction

        for widget in QApplication.topLevelWidgets():
            found = widget.findChild(QAction, name)
            if found is not None:
                return found
        return None

    def trigger(self, name: str) -> bool:
        act = self.action(name)
        if act is None:
            return False
        act.trigger()
        self.pump()
        return True

    def click(self, widget, pos=None) -> None:
        if widget is None:
            return
        widget.setFocus()
        if pos is None:
            QTest.mouseClick(widget, _button())
        else:
            QTest.mouseClick(widget, _button(), pos=pos)
        self.pump()

    def click_text(self, root, text: str) -> bool:
        if root is None:
            return False
        wanted = text.replace("&", "").lower()
        for button in root.findChildren(QPushButton):
            label = button.text().replace("&", "").strip().lower()
            if not label:
                continue
            if label == wanted or wanted in label:
                self.click(button)
                return True
        return False

    def keys(self, widget, text: str) -> None:
        if widget is None:
            return
        widget.setFocus()
        self.pump(2)
        QTest.keyClicks(widget, text)
        self.pump()

    def press(self, key: str, *mods: str, widget=None) -> None:
        target = widget
        if target is None:
            focus = QApplication.focusWidget()
            popup = QApplication.activePopupWidget()
            if popup is not None and (focus is None or not popup.isAncestorOf(focus)):
                target = popup
            else:
                target = focus or self.window
        QTest.keyClick(target, _key(key), _mods(*mods))
        self.pump()

    def replace_text(self, widget, text: str) -> None:
        if widget is None:
            return
        widget.setFocus()
        self.press("Key_A", "Control", widget=widget)
        self.press("Key_Backspace", widget=widget)
        if text:
            self.keys(widget, text)

    def shot(self) -> str:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return "no screen"
        pixmap = screen.grabWindow(0)
        return "%dx%d" % (pixmap.width(), pixmap.height())

    def save_shot(self, app: str, slug: str) -> str:
        folder = self.results / app
        folder.mkdir(parents=True, exist_ok=True)
        self.n += 1
        name = "%02d-%s.png" % (self.n, slug)
        path = folder / name
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return ""
        pixmap = screen.grabWindow(0)
        pixmap.save(str(path))
        return str(path.relative_to(self.results))

    def step(self, app: str, slug: str, did: str, saw: str, ok: bool) -> None:
        rel = self.save_shot(app, slug)
        mark = "pass" if ok else "fail"
        if not ok:
            self.failures.append("%s/%s: %s" % (app, slug, saw))
        line = "%d. %s / %s. Did: %s. Saw: %s. Shot: %s. %s\n" % (
            self.n,
            app,
            slug,
            did.replace("\n", " "),
            saw.replace("\n", " "),
            rel or "(none)",
            mark,
        )
        with self.steps_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        print(line, end="", flush=True)

    def time_call(self, key: str, fn: Callable[[], object]):
        started = time.perf_counter()
        value = fn()
        self.timings[key] = int((time.perf_counter() - started) * 1000)
        return value

    def wait(self, pred: Callable[[], bool], seconds: float) -> bool:
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            self.pump(2)
            if pred():
                return True
        return False

    def modal(self) -> Optional[QWidget]:
        return QApplication.activeModalWidget()

    def choose_combo(self, name: str, text: str) -> bool:
        box = self.find(name)
        if not isinstance(box, QComboBox):
            return False
        self.click(box)
        index = -1
        for i in range(box.count()):
            if text.lower() in box.itemText(i).lower():
                index = i
                break
        popup = QApplication.activePopupWidget()
        if index < 0:
            if popup is not None:
                popup.close()
            return False
        box.setCurrentIndex(index)
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
        self.pump()
        return text.lower() in box.currentText().lower()

    def click_list_text(self, name: str, text: str) -> bool:
        widget = self.find(name)
        if not isinstance(widget, QListWidget):
            return False
        for i in range(widget.count()):
            item = widget.item(i)
            if item is not None and item.text() == text:
                rect = widget.visualItemRect(item)
                QTest.mouseClick(widget.viewport(), _button(), pos=rect.center())
                self.pump()
                return True
        return False

    def go_to(self, name: str) -> bool:
        canvas = self.find("formBuilder.canvas")
        if canvas is None or not canvas.isVisible():
            self.code_note = "no form canvas for %s" % name
            return False
        self.click(canvas)
        self.press("Key_R", "Control")
        if self.find("formBuilder.goToWidgetSearch") is None:
            self.trigger("form.action.goToWidget")
        search = self.find("formBuilder.goToWidgetSearch")
        if search is None:
            return False
        self.replace_text(search, name)
        self.press("Key_Return")
        return True

    def menu_item(self, prefix: str) -> bool:
        popup = QApplication.activePopupWidget()
        if not isinstance(popup, QMenu):
            return False
        for _ in range(24):
            current = popup.activeAction()
            if current is not None and current.text().startswith(prefix):
                self.press("Key_Return")
                return True
            self.press("Key_Down")
            popup = QApplication.activePopupWidget()
            if not isinstance(popup, QMenu):
                return False
        return False

    def call_method(self, object_name: str, body: str) -> bool:
        """Shift+F10, Write code for…, accept the suggested method, replace pass."""
        self.code_note = ""
        if not self.go_to(object_name):
            self.code_note = "Ctrl+R did not open go-to for %s" % object_name
            return False
        self.press("Key_F10", "Shift")
        if not self.menu_item("Write code for"):
            focus = QApplication.focusWidget()
            self.code_note = "Shift+F10 did not open Write code for (focus %s)" % (
                focus.objectName() if focus is not None else "none"
            )
            return False
        if not self.wait(lambda: self.find("formBuilder.eventPickerMethod") is not None, 4):
            self.code_note = "the method page did not open"
            return False
        self.press("Key_Return")
        focus = self.wait_pass_editor(6)
        if focus is None:
            self.code_note = "pass was not selected in a code editor"
            return False
        self.keys(focus, body)
        self._arm_disk_dialog()
        self.press("Key_S", "Control")
        self.pump(8)
        return True

    def behavior(self) -> None:
        rail = self.find("formBuilder.rightRail.behavior")
        if rail is not None:
            self.click(rail)
        else:
            self.press("Key_B", "Alt")

    def add_check(self, object_name: str, kind_prefix: str, fill: Optional[Callable[[], None]] = None) -> bool:
        if not self.go_to(object_name):
            return False
        self.behavior()
        add = self.find("formBuilder.checks.add")
        if add is None:
            return False
        self.click(add)
        if not self.menu_item(kind_prefix):
            return False
        if not self.wait(lambda: self.find("formBuilder.checks.page") is not None, 4):
            return False
        if fill is not None:
            fill()
        commit = self.find("formBuilder.checks.commit")
        if commit is None:
            return False
        self.click(commit)
        self.pump(6)
        label = self.find("formBuilder.checks.addLabel")
        if label is not None and label.isVisible():
            self.click(label)
        return True

    def select_outline(self, name: str) -> bool:
        """Click an outline row. Ctrl+R only searches the form surface that last had focus.

        The painted caption (the object name) lives in a custom item role, not in
        the column text. A focus-only current-item change is thrown away, so a
        missed click is followed by setCurrentItem, which is the row the user sees.
        """
        from app.qt.QtCore import Qt
        from app.qt.QtWidgets import QTreeWidget, QTreeWidgetItem
        from app.qt.qt_compat import enum_value

        trees = []
        for widget in QApplication.topLevelWidgets():
            for outline in widget.findChildren(QWidget, "formBuilder.outline"):
                if not outline.isVisible():
                    continue
                tree = outline.findChild(QTreeWidget)
                if tree is not None and tree.isVisible():
                    trees.append(tree)
        if not trees:
            self.note = "no visible outline"
            return False
        caption_role = enum_value(getattr(Qt, "UserRole")) + 1

        def matches(item: QTreeWidgetItem) -> bool:
            label = " ".join(item.text(column) for column in range(max(item.columnCount(), 1)))
            tip = item.toolTip(0)
            caption = str(item.data(0, caption_role) or "")
            return name in label or name in tip or name in caption

        def walk(item: QTreeWidgetItem):
            if matches(item):
                return item
            for index in range(item.childCount()):
                child = item.child(index)
                if child is None:
                    continue
                found = walk(child)
                if found is not None:
                    return found
            return None

        target = None
        tree = None
        for candidate in trees:
            for index in range(candidate.topLevelItemCount()):
                top = candidate.topLevelItem(index)
                if top is None:
                    continue
                target = walk(top)
                if target is not None:
                    tree = candidate
                    break
            if target is not None:
                break
        if target is None or tree is None:
            self.note = "outline has no %s (%d trees)" % (name, len(trees))
            return False
        tree.scrollToItem(target)
        rect = tree.visualItemRect(target)
        self.click(tree.viewport(), rect.center())
        self.pump(2)
        if tree.currentItem() is not target:
            # The outline drops a current-row change that arrives without a
            # mouse button. setCurrentItem is the same row a click would pick.
            tree.setFocus()
            self.pump(2)
            tree.setCurrentItem(target)
            self.pump(2)
            self.note = "outline click missed; setCurrentItem"
        else:
            self.note = "outline click"
        return tree.currentItem() is target

    def set_enabled_when(self, object_name: str, formula: str) -> bool:
        # Ctrl+R can report success and still leave another widget selected
        # when two forms are open. The outline row is the one the user sees.
        # A check that just ran already selected the widget, and the Logic
        # tab hides the outline, so a missed row still leaves the Behavior button.
        self.note = ""
        picked = self.select_outline(object_name)
        if not picked:
            self.note = "outline missed (%s); using the current widget" % self.note
        self.behavior()
        button = self.find("formBuilder.state.value.cbcsEnabledWhen")
        if button is None or not button.isVisible():
            return False
        self.click(button)
        editor = self.find("formBuilder.formula")
        if editor is None:
            return False
        self.replace_text(editor, formula)
        self.press("Key_Return", "Control", widget=editor)
        self.pump(6)
        return True

    def save_form(self) -> None:
        self._arm_disk_dialog()
        self.press("Key_S", "Control")
        self.pump(12)

    def _arm_disk_dialog(self) -> None:
        """Ctrl+S can open a disk-conflict dialog. Answer it the way the default button does."""
        state = {"left": 12}

        def answer() -> None:
            if state["left"] <= 0:
                return
            state["left"] -= 1
            for name, label in (
                ("shell.staleSaveDialog", "Save My Version"),
                ("shell.diskChangedDialog", "Keep My Version"),
            ):
                dialog = self.find(name)
                if dialog is not None and dialog.isVisible():
                    self.click_text(dialog, label)
                    self.disk_prompts.append(label)
                    return
            QTimer.singleShot(200, answer)

        QTimer.singleShot(150, answer)

    def show_form_tab(self) -> bool:
        for widget in QApplication.allWidgets():
            if not isinstance(widget, QTabWidget):
                continue
            for i in range(widget.count()):
                if ".ui" in widget.tabText(i):
                    widget.setCurrentIndex(i)
                    self.pump(4)
                    return True
        return False

    def wait_pass_editor(self, seconds: float):
        found = {"widget": None}

        def ready() -> bool:
            for widget in QApplication.allWidgets():
                if not hasattr(widget, "textCursor") or not widget.isVisible():
                    continue
                try:
                    selected = widget.textCursor().selectedText()
                except RuntimeError:
                    continue
                if selected == "pass":
                    found["widget"] = widget
                    return True
            return False

        self.wait(ready, seconds)
        return found["widget"]

    def preview(self) -> bool:
        self.show_form_tab()
        button = self.find("formBuilder.preview")
        if button is not None:
            self.click(button)
        else:
            self.press("Key_R", "Control", "Shift")
        deadline = time.perf_counter() + 6
        while time.perf_counter() < deadline:
            self.qapp.processEvents()
            time.sleep(0.1)
        return True

    def theme(self, mode: str) -> bool:
        return self.trigger("shell.action.view.theme.%s" % mode)

    def mostly_black(self, widget) -> Optional[bool]:
        if widget is None or not widget.isVisible():
            return None
        image = widget.grab().toImage()
        if image.width() < 8 or image.height() < 8:
            return None
        dark = 0
        total = 0
        step_x = max(1, image.width() // 16)
        step_y = max(1, image.height() // 16)
        for y in range(0, image.height(), step_y):
            for x in range(0, image.width(), step_x):
                color = image.pixelColor(x, y)
                total += 1
                if color.red() < 12 and color.green() < 12 and color.blue() < 12:
                    dark += 1
        if total == 0:
            return None
        return dark / total > 0.85

    def run_modal(self, starter: Callable[[], None], fill: Callable[[], None]) -> None:
        state = {"done": False}

        def cap() -> None:
            if state["done"]:
                return
            modal = QApplication.activeModalWidget()
            if isinstance(modal, QDialog):
                modal.reject()

        QTimer.singleShot(250, fill)
        QTimer.singleShot(60000, cap)
        starter()
        state["done"] = True
        self.pump(8)

    def new_project(self, name: str, parent: Path) -> bool:
        parent.mkdir(parents=True, exist_ok=True)
        state = {"phase": "name", "ok": False, "tries": 0}

        def fill() -> None:
            if state["ok"]:
                return
            unsaved = self.find("shell.unsavedChangesDialog")
            if unsaved is not None and unsaved.isVisible():
                self.click_text(unsaved, "Discard Changes")
                QTimer.singleShot(200, fill)
                return
            state["tries"] += 1
            if state["tries"] > 80:
                dialog = self.modal()
                state["tries"] = 0
                state["rejects"] = state.get("rejects", 0) + 1
                if state["rejects"] > 4:
                    if isinstance(dialog, QDialog):
                        dialog.reject()
                    return
                if isinstance(dialog, QDialog) and not isinstance(dialog, (QInputDialog, QFileDialog)):
                    self.click_text(dialog, "Discard Changes") or self.click_text(dialog, "Cancel") or dialog.reject()
                QTimer.singleShot(200, fill)
                return
            dialog = self.modal()
            if state["phase"] == "name":
                if not isinstance(dialog, QInputDialog):
                    QTimer.singleShot(150, fill)
                    return
                edit = dialog.findChild(QLineEdit)
                if edit is None:
                    QTimer.singleShot(150, fill)
                    return
                self.replace_text(edit, name)
                state["phase"] = "dir"
                QTimer.singleShot(200, fill)
                self.click_text(dialog, "OK")
                return
            if not isinstance(dialog, QFileDialog):
                QTimer.singleShot(150, fill)
                return
            edit = dialog.findChild(QLineEdit, "fileNameEdit")
            if edit is None:
                edits = dialog.findChildren(QLineEdit)
                edit = edits[-1] if edits else None
            if edit is not None:
                self.replace_text(edit, str(parent))
            closed = False
            for label in ("Choose", "Open", "Select", "OK"):
                if self.click_text(dialog, label):
                    closed = True
                    break
            if not closed:
                dialog.accept()
            state["ok"] = True

        def start() -> None:
            if not self.trigger("shell.action.file.newProject"):
                state["ok"] = False

        self.run_modal(start, fill)
        return (parent / name).is_dir() or state["ok"]

    def open_settings_connections(self, title: str, code: str, relative_file: str) -> str:
        seen = {"result": ""}

        def fill() -> None:
            if not self.wait(lambda: self.find("shell.settingsDialog") is not None, 8):
                seen["result"] = "settings did not open"
                return
            def connections_ready() -> bool:
                tabs = self.find("shell.settingsDialog.tabs")
                if not isinstance(tabs, QTabWidget):
                    return False
                for i in range(tabs.count()):
                    if tabs.tabText(i) == "Connections":
                        if tabs.currentIndex() != i:
                            tabs.setCurrentIndex(i)
                            self.qapp.processEvents()
                        return self._visible("formBuilder.connections.addSqlite")
                return False

            if not self.wait(connections_ready, 8):
                tabs = self.find("shell.settingsDialog.tabs")
                names = []
                if isinstance(tabs, QTabWidget):
                    names = [tabs.tabText(i) for i in range(tabs.count())]
                add = self.find("formBuilder.connections.addSqlite")
                seen["result"] = "connections add button stayed hidden (tabs=%s add=%s)" % (
                    ",".join(names),
                    "missing" if add is None else "present",
                )
                self.click(self.find("shell.settingsDialog.cancelBtn"))
                return
            self.click(self.find("formBuilder.connections.addSqlite"))
            self.replace_text(self.find("formBuilder.connections.title"), title)
            self.replace_text(self.find("formBuilder.connections.code"), code)
            file_edit = self.find("formBuilder.connections.file")
            self.replace_text(file_edit, relative_file)
            if isinstance(file_edit, QLineEdit):
                file_edit.editingFinished.emit()
            self.pump(4)
            self.click(self.find("formBuilder.connections.test"))
            self.wait(
                lambda: self._label("formBuilder.connections.result") not in ("", "Testing…"),
                8,
            )
            seen["result"] = self._label("formBuilder.connections.result")
            banner = self._label("shell.settingsDialog.validationBanner")
            self.click(self.find("shell.settingsDialog.okBtn"))
            self.pump(4)
            dialog = self.find("shell.settingsDialog")
            if dialog is not None and dialog.isVisible():
                seen["result"] = (seen["result"] + " | still open | " + banner).strip()
                self.click(self.find("shell.settingsDialog.cancelBtn"))

        def start() -> None:
            self.trigger("shell.action.file.settings")

        self.run_modal(start, fill)
        return seen["result"]

    def _visible(self, name: str) -> bool:
        widget = self.find(name)
        return widget is not None and widget.isVisible()

    def _label(self, name: str) -> str:
        widget = self.find(name)
        if isinstance(widget, QLabel):
            return widget.text()
        return ""


def loadavg():
    try:
        return [round(value, 2) for value in os.getloadavg()], ""
    except OSError as exc:
        return None, "%s: %s" % (type(exc).__name__, exc)
