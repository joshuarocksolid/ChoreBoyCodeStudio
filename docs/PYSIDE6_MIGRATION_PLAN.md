# PySide6 migration plan

Date: 2026-10-20. Status: plan only. No application code was changed.

## Goal

ChoreBoy Code Studio (CBCS) has to start and run on two runtimes from one codebase:

| Runtime | Python | Qt binding | Where we can test it today |
| --- | --- | --- | --- |
| ChoreBoy production, current | 3.9.2 | PySide2 / Qt 5.15.2 | ChoreBoy VM, `/opt/freecad/AppRun` on Cloud (3.11.13, PySide2 5.15.15) |
| ChoreBoy FreeCAD 1.1 (test update, about 2026-09-29) | 3.11 (assumed) | PySide6 only (assumed) | `/Applications/FreeCAD.app` on the Mac: FreeCAD 1.1.3, Python 3.11.14, PySide6 6.8.3 |

All code stays Python 3.9 syntax. The 1.1 image itself has not been probed. Its Python and PySide versions above come from the upstream release and the Mac app. Probing it is step 0.1.

Background research: `docs/form_builder/research/B_qt_runtime_platform.md`. It has the module matrix for every local FreeCAD tree. This plan doesn't repeat that matrix. It does re-measure the API breaks on CBCS's own code.

## Summary

- **The port is smaller than the import count suggests.** We aliased `PySide2` onto PySide6 6.8.3 in-process and patched `QAction`, `QActionGroup` and `QShortcut` back onto `QtWidgets`. With that alone, the real editor starts and shows its main window on two runtimes: Python 3.9.23 and FreeCAD.app 1.1.3 (Python 3.11.14). In both cases the only warning was `exec_` deprecation.
- **Unit suite under the same alias:** 2330 tests. 2240 pass, 45 skip and 37 fail. Of the 37 failures, 20 also fail on PySide2 on this Mac. 8 more tests segfault the process, so they were deselected. That leaves **25 PySide6-only regressions**. They come from 4 root causes, and 3 of those 4 live in test code.
- **The real hazards are runtime-only.** Several PySide6 enum types reject `int()`. A Python exception raised inside a Qt virtual override now propagates out of a synchronous `sendEvent`, and under `QTest.keyPress` it segfaults. The test suite only exercises a few of these paths.
- **The compat layer is one self-contained file plus thin submodules.** It is `app/qt/qt_compat.py`, which imports only the standard library. `app/qt/QtCore.py`, `QtGui.py`, `QtWidgets.py` and the other submodules re-export from it. The same `qt_compat.py` gets copied into user projects and builder output.
- **A mechanical codemod covers most of the work.** It rewrites 563 `PySide2` import sites in 273 files. About 15 call sites need hand edits.
- **Effort:** about **12–16 engineer-days** from compat module to a PySide6 CI lane, plus ChoreBoy 1.1 image verification. That excludes the cp311 vendor bundle (Phase 4), which adds about 3–4 days.

---

## 1. Inventory

Counts are from `git ls-files` on this branch, at `791bbf0` plus the merge of `origin/main`.

### 1.1 Files that import PySide2

| Area | Files | Import sites | Notes |
| --- | ---: | ---: | --- |
| `app/` | 135 | 280 | shell 103, editors 20, features 3, intelligence 2, ui 2, bootstrap 1, project 1, support 1, syntax 1, treesitter 1 |
| `tests/` | 122 | 268 | 106 `pytest.importorskip("PySide2…")` calls; 11 modules copy the `QActionGroup = qt_gui.QActionGroup` patch |
| `testing/main_window_test_helpers.py` | 1 | 2 | already patches `QActionGroup` from `QtGui` |
| `run_editor.py` | 1 | 1 | `importlib.import_module("PySide2.QtWidgets")` |
| `templates/qt_app/` | 2 | 2 | `main.py` (`QApplication`, `app.exec_()`), `app/main_window.py` |
| `example_projects/crud_showcase/` | 4 | 10 | `main.py`, `app/main_window.py`, `app/icons.py`, `app/theme.py` |
| `SmokeQtApp/`, `SmokeCrudExample/`, `TaskTracker/` | 7 | 13 | tracked smoke and demo projects |
| `packaging/install.py` | 1 | 3 | **the installer GUI runs on the target machine**, with `QThread` and `Signal` |
| `scripts/generate_icon_pngs.py` | 1 | 4 | dev-only, uses `QtSvg.QSvgRenderer` |
| **Total** | **274** | **563** | 0 files mention PySide6, shiboken or qtpy |

Import shapes across the repo:

```text
197 from PySide2.QtWidgets import …     109 from PySide2.QtGui import …     109 from PySide2.QtCore import …
 13 import PySide2.QtWidgets [as …]       11 import PySide2.QtGui [as …]       3 import PySide2.QtCore
 13 import PySide2                        12 from PySide2 import QtX            3 from PySide2.QtSvg import QSvgRenderer
  3 importlib.import_module("PySide2.…")  (run_editor.py:59, app/shell/menus.py:164-165)
```

### 1.2 PySide2 named as data, not imports

These keep working after the import rename. They still have to be updated, or PySide6 users get wrong output.

| Location | What |
| --- | --- |
| `app/bootstrap/capability_probe.py:26,121-123` | `PYSIDE2_IMPORT_CHECK_ID = "pyside2_import"`, `check_pyside2_availability()` imports `"PySide2"` |
| `app/support/runtime_explainer.py:219-232` | user-facing text "built around the PySide2 runtime" |
| `app/intelligence/api_index.py:60-130` | static completion index keyed `PySide2`, `PySide2.QtWidgets`, … |
| `app/intelligence/runtime_api_index.json` | 12 `PySide2` keys plus `"runtime": "FreeCAD AppRun / PySide2"` |
| `app/intelligence/trusted_runtime_whitelist.py:11` | `TRUSTED_RUNTIME_ROOTS` lists `PySide2` only |
| `app/editors/markdown_rendering.py:38` | docstring only |
| `templates/qt_app/template.json`, `README.md` | "Starter GUI app using PySide2 imports" |
| `tools/dune/file_roles.py:30-41` | denies `PySide2` in 8 non-UI packages; does not know `PySide6` |
| `scripts/resolve_pyright_extrapaths.sh`, `scripts/setup_freecad_dev.sh`, `scripts/cloud_setup_screenshot_runtime.sh` | look for a `PySide2` site-packages dir |
| `AGENTS.md`, `docs/*` (≈30 files), `.cursor/skills/verify-cbcs/*` | prose and commands |

### 1.3 Places that do not touch Qt

`app/runner/`, `app/run/`, `run_runner.py` and `run_plugin_host.py` import no Qt. User code runs in a separate AppRun process, and that process picks its own binding. `file_roles.py` already keeps Qt out of `app.core`, `app.bootstrap`, `app.run`, `app.intelligence`, `app.persistence`, `app.plugins`, `app.packaging`, and all of `app.project` except `project_tree_widget.py`.

---

## 2. API breaks, measured

Every row was executed, not just looked up. The PySide6 runs used `/Applications/FreeCAD.app/Contents/Resources/bin/python` (6.8.3, Python 3.11.14). The PySide2 runs used `/Users/local/opt/freecad/bin/python` (5.15.15, Python 3.9.23). We ran one binding per process with `QT_QPA_PLATFORM=offscreen`. The CBCS-site counts come from `rg` plus an AST walk over `app/`, `run_editor.py`, `templates/` and `example_projects/`.

### 2.1 Breaks that fail on PySide6 6.8.3

| Break | PySide6 6.8.3 result | CBCS sites | Fix |
| --- | --- | --- | --- |
| `QAction`, `QActionGroup`, `QShortcut` moved `QtWidgets`→`QtGui` (`QUndoStack`/`QUndoCommand` too) | `hasattr(QtWidgets,"QAction")` is `False` | **11 in app:** imports in `action_registry.py`, `debug_panel/debug_panel_widget.py`, `outline/outline_header.py` (+`QActionGroup`), `project_tree_context_menu.py`, `run_with_arguments_dialog.py` (`QShortcut`), `shell_preferences_runtime.py` (`QShortcut`); attribute use `ctx.qt_widgets.QAction/QActionGroup` in `file_menu_builder.py:147`, `view_menu_builder.py:106,123`, `menu_action_builder.py:22`. Tests: `test_toolbar.py` + 11 modules with the helper patch | compat `QtWidgets` re-exports them from `QtGui` when missing |
| `int()` on many enum members | `int(Qt.ControlModifier)`, `int(Qt.LeftButton)`, `int(Qt.ItemIsEnabled)`, `int(Qt.Checked)`, `int(QSizePolicy.Expanding)` raise `TypeError`. `int(Qt.AlignCenter)`, `int(Qt.Popup)`, `int(Qt.Key_A)`, `int(QEvent.KeyPress)` still work | **1 live break:** `app/project/project_tree_widget.py:62` `QKeySequence(key \| int(modifiers))`. Safe today: `int(Qt.Align*)` ×6, `int(Qt.Popup)` in `quick_open_dialog.py:258`; `python_console_widget.py:828 _enum_int` already uses `.value` | compat `enum_value(x)` (`getattr(x,"value",x)` then `int`); or build `QKeyCombination` |
| `QPalette.Background/Foreground`, `Qt.MidButton`, `QFontMetrics.width`, `QLayout.setMargin`, `QWheelEvent.delta`, `QPlainTextEdit.setTabStopWidth`, `QHeaderView.setResizeMode`, `QAbstractItemView.viewOptions`, `QRegExp`, `QTextCodec`, `QDesktopWidget` | all absent | **0 in app.** `example_projects/crud_showcase/app/main_window.py:120` already guards `fm.width` with `hasattr(fm,"horizontalAdvance")` | none; add them to a lint gate (§5.4) so they stay at 0 |
| `QComboBox.activated[str]` / `currentIndexChanged[str]` | `IndexError: Signature … not found` | 0 (`run_arguments_editor.py:67` uses `activated[int]`, which still works) | lint gate |
| `QFont.setWeight(int)` | `TypeError` for a plain int (`setWeight(75)`); `QFont.DemiBold` works | 0 (all sites pass `QFont.<Weight>`) | lint gate |
| `QSvgWidget` in `QtSvg` | moved to `QtSvgWidgets` | 0 (CBCS uses only `QtSvg.QSvgRenderer`, which stays) | compat exposes `QtSvgWidgets` for the builder |
| Instance-level enum access, `cursor.End` | `AttributeError: 'QTextCursor' object has no attribute 'End'` | 0 in app; **3 in `tests/unit/editors/test_semantic_editor_interactions.py:59,325,338`**, which causes 16 test failures | use `QTextCursor.End` (class access) |

### 2.2 Works but deprecated on 6.8.3 (warns; removal in a later 6.x)

| API | Measured | CBCS sites |
| --- | --- | --- |
| `exec_()` on `QApplication`/`QDialog`/`QMenu` | works; **`DeprecationWarning: 'exec_' will be removed in the future`** | 36 tracked call sites: 25 in `app/` (20 files), `run_editor.py:33`, `templates/qt_app/main.py`, `example_projects/crud_showcase` ×2, `packaging/install.py`, the rest in `SmokeQtApp`, `SmokeCrudExample`, `TaskTracker` |
| `QMouseEvent.pos()/x()/y()/globalPos()` | works, `DeprecationWarning` | `code_editor_chrome_mixin.py:52` (`event.pos().y()` on a mouse event), `outline_header.py:219`, `project_tree_widget.py:91` (drag/drop event `pos()`, also deprecated), `code_editor_paste_hint_mixin.py:85,88` and `python_console_widget.py:461` are `QContextMenuEvent` (**not deprecated**). `code_editor_diagnostics.py:110-122` is `QHelpEvent` (**not deprecated**) |
| `Qt.CTRL + Qt.Key_S` | works, `DeprecationWarning` for `+`; `\|` gives `QKeyCombination` | 0 |
| `QFontDatabase()` instance | works, deprecated | 0 |
| `QTextCharFormat.setFontFamily` | works, deprecated (`setFontFamilies`) | `app/features/markdown/markdown_preview_enhancements.py:60` |
| `AA_EnableHighDpiScaling` etc. | works, deprecated | 0 |

### 2.3 Not a break on 6.8.3

These were checked: unscoped enums such as `Qt.AlignLeft`, `QSizePolicy.Expanding`, `QStyle.PE_*`, `QEvent.KeyPress`, `QDialog.Accepted == 1` and `QMessageBox.Yes | No`. So were `Qt.UserRole + 1`, `modifiers() & Qt.ControlModifier`, `Signal`/`Slot`/`Property`, `QtSvg.QSvgRenderer`, `QtUiTools.QUiLoader`, `QtPrintSupport`, `QTextDocument.setMarkdown`, `QFontMetrics.horizontalAdvance`, `setTabStopDistance`, `QFileSystemModel` (still in `QtWidgets`), `QScreen`/`primaryScreen`, and `QStandardPaths`. All of these behave as they do on PySide2. That is **387 unscoped `Qt.<Name>` uses that need no change now**.

### 2.4 Behavioral differences (no exception at the call site)

1. **Exceptions in virtual overrides propagate differently.**
   - Raise inside `keyPressEvent` and deliver the event synchronously with `QApplication.sendEvent`. On PySide6 the exception re-raises at the `sendEvent` call site as `TypeError: Error calling Python override of QTreeWidget::keyPressEvent(): …`. On PySide2 it was printed and swallowed.
   - Send the same event through `QTest.keyPress` and **the process segfaults (rc 139) with no Python traceback**. This caused all 7 crashes in `tests/unit/project/test_project_tree_widget_delete_signal.py`. The trigger is the `int(modifiers)` break at `project_tree_widget.py:62`.
   - A posted event delivered by the event loop prints the traceback and continues, the same as on PySide2.
   - Consequence: any latent bug in an override surfaces as a crash or an escaped exception on PySide6. The probe scripts are `p6c.py`/`p6d.py` in §6.4.
2. **Calling a protected paint method outside a paint event segfaults.** `tests/unit/shell/test_outline_panel.py:368` calls `tree.drawBranches(painter, …)` directly. `outline_tree.py:95` then calls `super().drawBranches`, and that crashes Qt 6. This is a test-shape problem; the app never calls it this way. Rewrite the test to `grab()` the widget.
3. **The tab-bar font does not stick.** `settings_dialog.py:209-212` calls `setPixelSize(12)` and then `tab_bar.setFont(…)`. On PySide6, `tab_bar.font().pixelSize()` returns `-1`. The test is `test_settings_dialog_tab_bar_prevents_label_clipping`. The likely cause is Qt 6 font-resolve or stylesheet propagation. Check it visually; this one may be real UI drift.
4. **One binding per process.** Loading PySide2 and PySide6 in one process aborts with signal 139 (see research B). The probe must never import the binding it is not going to use.
5. **Patching shiboken classes is unsafe.** On PySide2, `QMenu.exec = QMenu.exec_` followed by `menu.exec(QPoint)` **segfaults**. `QDialog` and `QApplication` survive the same patch. So the compat layer must not alias `exec` onto PySide2 classes. It uses a helper function instead (§3.2).

---

## 3. `qt_compat` design

### 3.1 Placement and the `file_roles` rules

```text
app/qt/
  __init__.py        # empty docstring; no Qt import at package import time
  qt_compat.py       # THE canonical, self-contained file (stdlib-only imports)
  QtCore.py          # thin re-export submodules, one per Qt module CBCS uses
  QtGui.py
  QtWidgets.py
  QtSvg.py
  QtSvgWidgets.py
  QtPrintSupport.py
  QtUiTools.py
  QtTest.py          # tests only
```

`app/qt` matches no existing `FileRole` pattern, so it is allowed today. Change `tools/dune/file_roles.py` in the same PR:

1. **Extend `denied_imports` on every non-UI role** from `("PySide2",)` to `("PySide2", "PySide6", "shiboken2", "shiboken6", "app.qt")`. Without `app.qt` in the list, `app.core` could reach Qt by importing the compat package. The `app/project/project_tree_widget.py` exception stays.
2. **Add a binding-confinement role.** It applies to `app/**` and denies `PySide2`, `PySide6`, `shiboken2` and `shiboken6`. Its `allowed_files` are the `app/qt/*.py` files. Enable it in Phase 2, after the codemod lands. From then on, only `app/qt/` names a binding.
3. `file_roles` only scans `app/`. Add a similar check, or extend the scan to cover `run_editor.py`, `packaging/install.py`, `templates/` and `example_projects/`. That catches a raw `PySide2` import coming back.

`importlib.import_module("PySide2…")` strings are invisible to the AST check. After the codemod there are none in `app/`. `capability_probe.py` imports by name on purpose and lives in `app.bootstrap`; it goes through `qt_compat.binding_candidates()` (§4) rather than `app.qt` submodules.

### 3.2 `app/qt/qt_compat.py` (sketch, Python 3.9)

```python
"""Pick one Qt binding (PySide6 or PySide2) and smooth over the measured deltas.

Self-contained: imports only the standard library, so the same file can be
copied into user projects and form-builder output.
"""
from __future__ import annotations

import importlib
import importlib.util
import os
from types import ModuleType
from typing import Any, Tuple

ENV_VAR = "CBCS_QT_API"                 # "pyside6" | "pyside2"
_ORDER = ("PySide6", "PySide2")

def binding_candidates() -> Tuple[str, ...]:
    forced = os.environ.get(ENV_VAR, "").strip().lower()
    if forced in ("pyside6", "pyside2"):
        return ("PySide6" if forced == "pyside6" else "PySide2",)
    return _ORDER

def _select() -> str:
    for name in binding_candidates():
        if importlib.util.find_spec(name) is not None:   # no import -> no dual-Qt load
            return name
    raise ImportError("Neither PySide6 nor PySide2 is importable (CBCS_QT_API=%r)"
                      % os.environ.get(ENV_VAR, ""))

QT_API = _select()
IS_QT6 = QT_API == "PySide6"
QtCore = importlib.import_module(QT_API + ".QtCore")
QtGui = importlib.import_module(QT_API + ".QtGui")
QtWidgets = importlib.import_module(QT_API + ".QtWidgets")

for _name in ("QAction", "QActionGroup", "QShortcut", "QUndoCommand", "QUndoGroup", "QUndoStack"):
    if not hasattr(QtWidgets, _name) and hasattr(QtGui, _name):
        setattr(QtWidgets, _name, getattr(QtGui, _name))   # module attr, not a class patch

def import_qt_module(short_name: str) -> ModuleType:
    """QtSvg, QtSvgWidgets, QtUiTools, QtPrintSupport, QtTest ..."""
    if short_name == "QtSvgWidgets" and not IS_QT6:
        return importlib.import_module("PySide2.QtSvg")      # QSvgWidget lives there on Qt 5
    return importlib.import_module(QT_API + "." + short_name)

def exec_qt(obj: Any, *args: Any) -> Any:
    """obj.exec(*args) on PySide6, obj.exec_(*args) on PySide2. Never patch classes."""
    method = getattr(obj, "exec", None) if IS_QT6 else None
    return (method or obj.exec_)(*args)

def enum_value(value: Any) -> int:
    """int() for any Qt enum/flag on both bindings (PySide6 Flag types reject int())."""
    raw = getattr(value, "value", value)
    return int(raw)

def event_pos(event: Any) -> Any:           # QPoint, for mouse/drag/drop events
    pos = getattr(event, "position", None)
    return pos().toPoint() if pos is not None else event.pos()

def event_global_pos(event: Any) -> Any:    # QPoint, for QMouseEvent
    pos = getattr(event, "globalPosition", None)
    return pos().toPoint() if pos is not None else event.globalPos()
```

The submodule shims stay small and keep pyright's types:

```python
# app/qt/QtWidgets.py
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from PySide2.QtWidgets import *          # noqa: F401,F403  - pyright resolves PySide2 stubs
    from PySide2.QtWidgets import QAction, QActionGroup, QShortcut  # noqa: F401
else:
    from app.qt.qt_compat import QtWidgets as _m
    globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
```

Design choices:

- **The default order is PySide6 first, then PySide2.** Today's ChoreBoy and Cloud images have no PySide6, so they select PySide2. A PySide6-only 1.1 image selects PySide6. The hybrid Mac prefixes have both bindings. `run_dev.sh` and `dev_launch_editor.py` pin them with `CBCS_QT_API=pyside2` to keep ChoreBoy parity, and a second dev profile pins `pyside6`.
- **`find_spec` runs before any import**, so a process never loads two bindings.
- **The editor exports `CBCS_QT_API=<chosen>` into child processes.** These are the runner, the plugin host and Test Explorer. Without it, a child on a hybrid tree can pick a different binding from the editor.
- **There is no global monkeypatching of shiboken classes** (see §2.4.5). The only mutation sets attributes on the `QtWidgets` module object.
- **One file serves three consumers.** CBCS imports `app/qt/qt_compat.py`. The form builder's emitted `qt_compat.py` and the `templates/qt_app/qt_compat.py` are byte-identical copies. A dune drift check, in the same style as `feat(dune): fail feature-map drift`, fails CI when a copy diverges. User projects can't import `app.qt`, because packaged apps run without CBCS on `sys.path`.
- **qtpy is not used.** It isn't present on any tree, it would have to be vendored for offline machines, and the measured delta fits in about 80 lines.

### 3.3 Codemod

The codemod is a one-shot script, `tools/qt_codemod.py`. It is deleted after use or kept under `tools/` for user projects. It uses `ast` to find nodes and edits the original source text so formatting is preserved. It is idempotent and has a `--check` mode for CI.

| Pattern | Rewrite |
| --- | --- |
| `from PySide2.QtX import A, B` (incl. multi-line parens) | `from app.qt.QtX import A, B` |
| `from PySide2 import QtCore, QtWidgets` | `from app.qt import QtCore, QtWidgets` |
| `import PySide2.QtX as m` / `import PySide2.QtX` | `from app.qt import QtX as m` / `from app.qt import QtX` and rewrite bare `PySide2.QtX.` attribute chains in that file |
| `import PySide2` (13; mostly tests probing availability) | `from app.qt import qt_compat` + manual review |
| `importlib.import_module("PySide2.QtX")` | `importlib.import_module("app.qt.QtX")` |
| `pytest.importorskip("PySide2.QtX")` (106) | `pytest.importorskip("app.qt.QtX")` (skips cleanly when no binding) |
| the 11 copied `if not hasattr(qt_widgets, "QActionGroup")` blocks + `testing/main_window_test_helpers.py` | delete; compat handles it |
| `x.exec_(…)` (36) | `exec_qt(x, …)` + add `from app.qt.qt_compat import exec_qt` |
| user-facing outside `app/` (`templates/`, `example_projects/`, `Smoke*`, `TaskTracker`, `packaging/install.py`) | `from qt_compat import QtWidgets` style with a copied `qt_compat.py` next to `main.py` |

Hand edits that the codemod flags but does not fix (about 15 sites):

| File:line | Change |
| --- | --- |
| `app/project/project_tree_widget.py:62` | `QKeySequence(key \| enum_value(modifiers))` (**crash on PySide6**) |
| `app/project/project_tree_widget.py:91`, `app/shell/outline/outline_header.py:219`, `app/editors/code_editor_chrome_mixin.py:52` | `event_pos(event)` |
| `app/features/markdown/markdown_preview_enhancements.py:60` | `setFontFamilies([...])` when available |
| `app/shell/settings_dialog.py:209-212` | find out why the tab font is lost on Qt 6; fix or relax the test |
| `app/bootstrap/capability_probe.py`, `app/support/runtime_explainer.py` | §4 |
| `app/intelligence/api_index.py`, `runtime_api_index.json`, `trusted_runtime_whitelist.py` | key the static index by the active `QT_API`; add `PySide6` to trusted roots |
| `tests/unit/editors/test_semantic_editor_interactions.py:59,325,338` | `cursor.End` → `QTextCursor.End` |
| `tests/unit/shell/test_outline_panel.py:368` | stop calling `drawBranches` directly |
| `tests/unit/core/test_models.py`, `tests/unit/bootstrap/test_*probe*.py` | new check id |

The whole diff fits in one PR, which is easier to review than 274 files spread over many PRs. A reviewer reads the codemod and its `--check` output, then the hand-edit commits on their own.

---

## 4. Capability probe

`app/bootstrap/capability_probe.py` today:

- `check_pyside2_availability()` runs `importlib.import_module("PySide2")`. A PySide6-only runtime fails the check and the editor reports itself as broken.
- QtUiTools is never probed, even though `docs/PRD.md:350` asks for it.

The plan:

1. **Rename the check.** `PYSIDE2_IMPORT_CHECK_ID = "pyside2_import"` becomes `QT_BINDING_CHECK_ID = "qt_binding_import"`. Keep `PYSIDE2_IMPORT_CHECK_ID` as a deprecated alias for one release, because support bundles and `runtime_explainer` key on it.
2. **Add `check_qt_binding_availability()`.**
   - Call `qt_compat.binding_candidates()` and keep the first entry where `importlib.util.find_spec` succeeds.
   - Import `<binding>.QtCore`, `.QtGui` and `.QtWidgets`.
   - Report `details={"binding": "PySide6", "binding_version": PySide6.__version__, "qt_version": QtCore.qVersion(), "forced_by_env": bool, "other_binding_present": bool}`.
   - Use `find_spec` only for the other binding and never import it, because importing both crashes on hybrid trees.
   - The probe stays in `app.bootstrap` and names the bindings as strings, so `file_roles` continues to pass.
   - Import `qt_compat` lazily: it imports a binding at module load, and the bootstrap rule will deny `app.qt`. Better: move `binding_candidates()` into a stdlib-only `app/bootstrap/qt_binding_choice.py`, which `app/qt/qt_compat.py` also imports. User copies of `qt_compat.py` inline it.
3. **Add `check_qt_uitools_availability()`.** It imports `<binding>.QtUiTools` and confirms the `QUiLoader` attribute, which research B measured on PySide2 5.15.15 and on PySide6 6.8.3. It is non-fatal: report it as degraded, because only the form builder needs it. Run it in the full probe, not in `run_minimal_startup_capability_probe`.
4. **Update `runtime_explainer.py`.** Change the wording to "Qt for Python (PySide6 or PySide2)". Show which binding is active and the `CBCS_QT_API` hint.
5. **`run_editor._load_qt_runtime`** imports `app.qt.QtWidgets` instead of `"PySide2.QtWidgets"`.
6. **Tests**, all in `tests/unit/bootstrap/test_capability_probe.py`, with `find_spec` and `import_module` monkeypatched:
   - PySide6-only: passes and selects PySide6.
   - PySide2-only: passes and selects PySide2.
   - Neither binding: the check fails with a readable message.
   - `CBCS_QT_API=pyside2` with only PySide6 installed: fails and names the env var.
   - Both installed: the other binding is never imported.

   Each of these is a startup-gating decision, so they pass `testing_when_to_write.mdc`.

---

## 5. Test strategy

### 5.1 Runtimes

| Lane | Runtime | Binding | Purpose |
| --- | --- | --- | --- |
| A (existing) | `/opt/freecad/AppRun` (Cloud, 3.11.13) / `~/opt/freecad/AppRun` | PySide2 5.15.15 | regression baseline, unchanged `run_test_shard.py fast` |
| B (new) | `/Applications/FreeCAD.app/Contents/Resources/bin/python` (1.1.3, 3.11.14) | PySide6 6.8.3 | the shape of a 1.1 ChoreBoy runtime |
| C (new, Mac dev) | `/Users/local/opt/freecad/bin/python` (3.9.23) with `CBCS_QT_API=pyside6` | PySide6 6.8.3 | isolates **binding** from **Python version**: same vendor tree as lane A on 3.9 |
| D (gate) | ChoreBoy VM with the 1.1 test update (`run-choreboy-probe` / `run-choreboy-app` skills) | whatever ships | the only real answer; AppArmor, `/bin/sh`-only subprocess, real vendor bundle |

`run_tests.py` reads `CBCS_APPRUN`. Add `CBCS_QT_API` passthrough. Add a `run_test_shard.py fast --qt pyside6` option that sets `CBCS_APPRUN` to the FreeCAD.app python wrapper and sets `CBCS_QT_API=pyside6`. FreeCAD.app has no `AppRun`. A two-line wrapper script under `testing/`, which execs `bin/python "$@"`, satisfies the `AppRun -c` contract. The wrapper must not add `Ext/` to the path, so that user code can't quietly pick up FreeCAD's `PySide` shim.

### 5.2 Spike baseline (what we have today, before any code change)

The spike harness imports PySide6, aliases `sys.modules["PySide2*"]` to it, copies `QAction`, `QActionGroup` and `QShortcut` onto `QtWidgets`, and then runs pytest (§6). It ran `tests/unit` with `-m "not slow and not performance"`, using `vendor_py39` from `ChoreBoyCodeStudio_artifacts`.

| | PySide2 5.15.15 (lane A-equivalent, py3.9.23) | PySide6 6.8.3 alias (lane C, py3.9.23) |
| --- | ---: | ---: |
| collected | 2330 | 2330 |
| passed | 2265 | 2240 |
| skipped | 45 | 45 |
| failed | 20 | 37 |
| segfaulted (deselected) | 0 | 8 |
| **PySide6-only regressions** | | **25** |

The 20 shared failures are Mac-specific, for example `test_memfd_shim` and `test_runtime_child_reaper`; the core `tree_sitter` binding is missing from `vendor_py39` on this Mac. Those failures are identical in both columns and are not migration work.

The 25 PySide6-only regressions:

| Count | Root cause | In |
| ---: | --- | --- |
| 16 | `cursor.End` instance enum access | test helper |
| 7 | `int(modifiers)` → exception in `keyPressEvent` → **segfault** under `QTest.keyPress` | **app** `project_tree_widget.py:62` |
| 1 | direct `drawBranches()` call outside paint → segfault | test shape |
| 1 | tab-bar `pixelSize()` is `-1` | app or Qt 6 behavior, investigate |

Editor start, measured with `run_editor.main()`, a top-level visible-window check after 8 s, and then `quit`:

| Runtime | Result |
| --- | --- |
| `/Users/local/opt/freecad/bin/python` 3.9.23 + PySide6 6.8.3 alias | main window `ChoreBoy Code Studio v0.4.10` visible, rc 0, one `exec_` `DeprecationWarning` |
| FreeCAD.app 1.1.3, Python 3.11.14, PySide6 6.8.3 alias | same; tree-sitter reported unavailable (no cp311 darwin binding), so editor ran with highlighting off |

### 5.3 Which tests to add

Follow `.cursor/rules/testing_when_to_write.mdc`. Most of the risk is covered by running the existing suite on lane B or C. New tests:

1. **Capability probe binding selection** (§4.6). These guard startup gating.
2. **`qt_compat` contract**, one small module run on both lanes:
   - `QtWidgets.QAction is QtGui.QAction` on Qt 6.
   - `exec_qt` works on `QDialog`, `QMenu` and `QApplication`.
   - `enum_value(Qt.ControlModifier)` returns an int.
   - Selecting a binding never imports the other one: check `sys.modules` after the import.
3. **Drift check**: the copies of `qt_compat.py` in templates and builder output are byte-identical. This goes in dune, not pytest.
4. **Template smoke**, `runtime_parity`. A `templates/qt_app` project created from the template starts under each lane's `AppRun -c` and shows its window. Today this test would fail on lane B at `import PySide2`. It is the user-visible break.

Do **not** add per-API pinning tests for every deprecated call. Use the lint gate instead.

### 5.4 Static gate

Add a dune check, or extend `file_roles`, that fails on these patterns in `app/`, `templates/` and `example_projects/`:

- Removed APIs: `QRegExp`, `QDesktopWidget`, `QTextCodec`, `\.width\(` on a `QFontMetrics`, `setMargin(`, `Qt.MidButton`, `QPalette.Background`, `activated[str]` and `currentIndexChanged[str]`.
- `int(` applied to a `Qt.` or `.modifiers()` expression.
- `.exec_(`.
- A raw `PySide2` or `PySide6` import outside `app/qt/`.

This keeps the counts in §2 at 0 as new code lands.

### 5.5 Running PySide6 tests with deprecations as errors

Lane C runs `-W error::DeprecationWarning:PySide6` once per release. When a later 6.x removes `exec_` or `QMouseEvent.pos()`, those removals show up as failures here before they reach users.

---

## 6. Phases, effort and exit criteria

Estimates are focused engineer-days for someone who knows CBCS. Test runs are counted inside each phase.

| Phase | Work | Days | Exit criterion |
| --- | --- | ---: | --- |
| **0. Facts** | 0.1 Probe the real ChoreBoy 1.1 test update with `run-choreboy-probe`: Python version, SOABI, `PySide2` and `PySide6` import, `QtUiTools`, `QtSvgWidgets`, how `AppRun -c` sets `sys.path` (does `Ext/PySide` bind PySide6?), whether `/bin/sh` is the only subprocess, and whether tree_sitter, psycopg and pg8000 are present. 0.2 Commit this plan's spike harness under `testing/` | 1 | probe report in `docs/DISCOVERY.md` §1.1-update |
| **1. Compat module + probe** | `app/qt/` (§3.2), `qt_binding_choice.py`, probe rename and QtUiTools check (§4), `runtime_explainer` text, `file_roles` changes (§3.1, deny `app.qt` in non-UI roles), `CBCS_QT_API` passthrough into runner, plugin host and Test Explorer env | 3 | lane A green; probe tests green; `npx pyright` 0 errors |
| **2. Codemod + hand edits** | run `tools/qt_codemod.py` across `app/`, `tests/`, `testing/`, `run_editor.py`; the ~15 hand edits in §3.3; delete the 11 copied test patches; enable the binding-confinement `file_roles` rule; static gate (§5.4) | 3–4 | lane A green; lane C green except known Mac-only failures; 0 raw `PySide2` imports outside `app/qt/` |
| **3. User-facing code** | `templates/qt_app` (+`qt_compat.py`, `exec_qt`), `example_projects/crud_showcase`, `SmokeQtApp`, `SmokeCrudExample`, `TaskTracker`, `packaging/install.py` (inline copy of `qt_compat.py`, because the installer runs before CBCS is installed); intelligence index keyed by active binding; `template.json`/README/manual chapters 102, 120, 130, 210, 290, 390, 395 | 2–3 | template smoke (§5.3.4) green on lanes A and B |
| **4. Python 3.11 vendor bundle** | the 1.1 image is Python 3.11, so `vendor/tree_sitter/_binding.cpython-39-…so` will not load. `app/treesitter/loader.py:127` already resolves the binding by `SOABI`, so a **dual-ABI** product payload (cp39 and cp311 `_binding` side by side; grammar wheels are abi3) works without a loader change. Generalize `app/packaging/tree_sitter_cp39.py` and `product_builder.py` to a list of target SOABIs; confirm `black==24.10.0`, `jedi`, `rope` on 3.11 (pure Python in `vendor_py39`) | 3–4 | `python package.py` produces a payload whose `validate_choreboy_tree_sitter_bundle` passes for both SOABIs; editor on lane B shows syntax highlighting |
| **5. CI and dev tooling** | lane B/C in `run_test_shard.py` (`--qt pyside6`), `testing/` AppRun wrapper for FreeCAD.app, `run_dev.sh --qt pyside6`, `scripts/setup_freecad_dev.sh` pin, `resolve_pyright_extrapaths.sh` (a second pyright config against PySide6 stubs is optional), `AGENTS.md`/`docs/LOCAL_DEV.md`/`docs/TESTS.md` | 2 | `run_test_shard.py fast` and `fast --qt pyside6` both documented with checkpoint numbers |
| **6. ChoreBoy 1.1 verification** | install the packaged build on the ChoreBoy VM with the 1.1 test update via `run-choreboy-app`; smoke: open project, edit, run `qt_app` template, debug session, REPL, Test Explorer, plugin host, packaging export; repeat on current production image | 2 | both images pass the smoke list in `docs/ACCEPTANCE_TESTS.md` |
| **Total** | | **16–19** (12–16 without Phase 4) | |

Order and dependencies:

- Phase 0.1 can start now and blocks nothing except the Phase 4 scope.
- Phase 1 should land before or together with the form builder's first PR. Both use the same `qt_compat.py`.
- Phases 2 and 3 can be separate PRs after Phase 1.
- Phase 4 can run in parallel with 2 and 3.
- Phase 6 needs all of the above.

Each phase leaves PySide2 production working, so we can stop between phases. Phase 1 alone already lets the probe and `run_editor` accept PySide6. After Phase 2, CBCS starts on a PySide6-only machine. Phase 3 does the same for user projects created from templates.

---

## 7. Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| **The ChoreBoy 1.1 image differs from FreeCAD.app 1.1.3**: other PySide6 minor, Python 3.11 vs something else, still ships PySide2, missing `QtUiTools` | medium | plan details shift | Phase 0.1 probe first; compat layer is order-based, not version-based |
| **Exceptions in overrides crash or escape on PySide6** (§2.4.1). The suite covers few override paths, so more latent bugs may exist | medium | hard crash in the field, no traceback in logs | keep `faulthandler` on (already in `run_editor.py`); lane C smoke drives real key/mouse paths; `int(` gate (§5.4); consider a `sys.excepthook` + override decorator for hot overrides (`keyPressEvent`, `paintEvent`, `eventFilter`) |
| **Enum `int()` breaks spread beyond the one measured site.** PySide6 6.8 rejects `int()` on `KeyboardModifier`, `MouseButton`, `ItemFlag`, `CheckState`, `SizePolicy` | low (1 live site today) | crash | `enum_value()` + static gate |
| **A later PySide6 removes `exec_` or the unscoped enum names** (387 `Qt.<Name>` uses) | medium over 1–2 years | mass `AttributeError` | Phase 2 replaces `exec_`; unscoped names still resolve in 6.8.3 (measured). The `-W error` lane (§5.5) gives early warning. Moving to scoped enums is a separate codemod we can run later if needed |
| **Two bindings in one process** on hybrid dev trees or in user apps that import FreeCADGui | low on ChoreBoy (one binding), high on Mac dev | signal 139 | `find_spec` before import; `CBCS_QT_API` exported to children; dev scripts pin the binding |
| **User projects already on disk** import `PySide2` and break on the 1.1 image | certain for existing projects | user apps don't start after the update | Phase 3 templates fix *new* projects only; offer a "Port project to qt_compat" command that runs the same codemod on a user project (stretch); document in manual |
| **FreeCAD's `PySide` shim.** User code that does `import PySide` gets PySide6 on 1.1, and `QtWidgets.QAction` is gone (research B) | medium | user app break | manual chapter + template use `qt_compat`; intelligence index stops suggesting `PySide.QtWidgets.QAction` |
| **Python 3.11 vendor bundle** (Phase 4) not ready when the image ships | medium | editor starts, tree-sitter off ("Syntax highlighting off") | the editor degrades rather than failing; dual-ABI payload |
| **Pyright typing through dynamic re-exports** | low | type noise | `TYPE_CHECKING` star-import from PySide2 in `app/qt/Qt*.py` keeps current stubs; a separate PySide6 pyright config is optional |
| **The codemod changes 274 files in one PR** | low | review fatigue, merge conflicts with in-flight branches | mechanical-only commit separated from hand edits; `--check` mode; land at a quiet point; rerun on rebases |
| **Visual and behavioral drift on Qt 6**: fonts (§2.4.3), high DPI is always on, style differences | medium | cosmetic | Phase 6 screenshot pass on the VM; fix case by case |

---

## Appendix A. Spike harness

The harness is not committed. Phase 0.2 commits it under `testing/`. It is a copy of what produced §5.2.

```python
# run_spike.py <pyside2|pyside6> <repo> <vendor_dir> [pytest args...]
import os, sys
binding, repo, vendor = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [repo, vendor]; os.chdir(repo)
if binding == "pyside6":
    import PySide6
    from PySide6 import QtCore, QtGui, QtWidgets, QtSvg, QtSvgWidgets, QtPrintSupport, QtUiTools, QtTest
    import shiboken6
    for name in ("QAction", "QActionGroup", "QShortcut", "QUndoCommand", "QUndoGroup", "QUndoStack"):
        setattr(QtWidgets, name, getattr(QtGui, name))
    sys.modules["PySide2"] = PySide6
    for sub in ("QtCore", "QtGui", "QtWidgets", "QtSvg", "QtPrintSupport", "QtUiTools", "QtTest"):
        sys.modules["PySide2." + sub] = sys.modules["PySide6." + sub]
    sys.modules["shiboken2"] = shiboken6
import pytest
sys.exit(pytest.main(["--import-mode=importlib", "-p", "no:cacheprovider", *sys.argv[4:]]))
```

```bash
QT_QPA_PLATFORM=offscreen CBCS_DISABLE_BACKGROUND_RUNTIME=1 \
  /Users/local/opt/freecad/bin/python -X faulthandler run_spike.py pyside6 "$PWD" \
  ~/Projects/ChoreBoyCodeStudio_artifacts/vendor_py39 tests/unit/shell -q -m "not slow and not performance"
```

We ran it one `tests/unit/<dir>` at a time, so that a segfault only stops its own directory. After each crash we deselected the faulting test, as reported by faulthandler's `Current thread` frame, and reran that directory.

The editor-start spike used the same alias. It wrapped `run_editor._load_qt_runtime` so the main window class arms a `QTimer` that lists visible top-levels and quits. It ran with `HOME` pointed at a scratch dir on FreeCAD.app.

## Appendix B. Probe one-liners used for §2

```bash
# PySide6 6.8.3 / Python 3.11.14
QT_QPA_PLATFORM=offscreen /Applications/FreeCAD.app/Contents/Resources/bin/python -I -c '
from PySide6 import QtWidgets, QtGui; from PySide6.QtCore import Qt
a = QtWidgets.QApplication([])
print(hasattr(QtWidgets, "QAction"), hasattr(QtGui, "QAction"))   # False True
print(int(Qt.AlignCenter))                                         # 132
int(Qt.ControlModifier)                                            # TypeError'

# Exception inside an override during QTest.keyPress -> rc 139 on PySide6, survives on PySide2
# (p6c.py: QTreeWidget subclass whose keyPressEvent does QKeySequence(e.key() | int(e.modifiers())))

# Class patch that crashes PySide2 5.15.15
QT_QPA_PLATFORM=offscreen /Users/local/opt/freecad/bin/python -I -c '
from PySide2 import QtWidgets, QtCore; QtWidgets.QMenu.exec = QtWidgets.QMenu.exec_
a = QtWidgets.QApplication([]); m = QtWidgets.QMenu(); m.addAction("x")
QtCore.QTimer.singleShot(50, m.close); m.exec(QtCore.QPoint(0, 0))'   # rc 139
```
