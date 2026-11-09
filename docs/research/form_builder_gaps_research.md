# Form builder remaining gaps

The goal is one research note of every remaining gap in the visual Qt form builder, which landed on main as PR #225 in squash `b4d1f241`. The problem is that the build trail's open items were trimmed off main, so a later agent cannot tell which ones are still real. The smallest change that meets the goal is this file. No product code and no tests were edited.

Evidence is `origin/main` at `b4d1f241ab8836993f1ee46c029ea7f2de45e09b` unless a line says otherwise. Trail reports are `git show form-builder-trail-m10:docs/form_builder/orch/<file>`. Those reports are not on main. Commit `2a86e8c1` removed them.

Each item says whether it is still real, the evidence, the root cause, a proposed fix, a size (S/M/L), a risk, and a dispatch brief. S is one module and its test. M crosses a feature boundary. L is a runtime or rollout decision.

## 1. Form-open timing

Still real as a measurement gap. The 800 ms budget was not measured on the workload it names.

The M10.1b timer is `from_table` in `docs/form_builder/orch/probe_m10_vm/apps.py` on tag `form-builder-trail-m10`, lines 135-137. It starts `time.perf_counter`, calls `drive.run_modal(start_click, fill)`, and stores `drive.timings["%s_open_form_ms" % app]`. `start_click` opens the from-table card. `fill` drives the dialog and clicks Create. `docs/form_builder/orch/m10_1b_run.md` on the same tag records customer 3738 ms and products 5691 ms, and says the timer wraps the from-table dialog.

The budget is UX-M8-003 in `docs/form_builder/UX_SPEC.md` line 3306, the VM cell "Open a bound form". The workload is a SQLite shop database with 100,000 invoices, both lookups (2,000 customers and 5,000 products), and record 1 with 20 lines. The limit is 800 ms on the VM. The M10 probe did not load that database. A timer around an empty demo database would still not meet the row.

The product work to time is the generated window, not the designer. `app/features/form_builder/engine/codegen/window_template.py` lines 103-106 build `__init__` so it calls `self.ui.setupUi(self)`. `app/features/form_builder/engine/codegen/emit.py` line 1903 ends `setupUi` with `self._cbcs_setup(...)`. `app/features/form_builder/engine/codegen/expanders/record.py` lines 160-162 append `_open_line(...)` at priority 890. `_open_line` at lines 1862-1869 returns `self.cbcs_open()`, `self._cbcs_open_last()`, or `self._cbcs_open_new()`. Line 352 sets `self._cbcs_ready = True` after the fetched row is written onto the widgets. `FormSurface.showEvent` in `app/features/form_builder/integration/surface.py` line 1052 is the designer surface. It applies layout and prewarms Preview. It is the wrong hook for UX-M8-003.

**Root cause.** The probe timed the editor dialog that creates the form. The budget is the generated form opening a large record set.

**Proposed fix.** Keep Create outside the timer. After the form is saved, import the generated window module under the FreeCAD 1.1 AppRun, against a database that matches the UX-M8-003 row. Start `perf_counter` immediately before `Window()`. Stop when `_cbcs_ready` is true. Do not pump the from-table dialog inside that interval. Record the number beside `os.getloadavg` when AppArmor allows it. The M10 report says `getloadavg` raises under AppArmor, so an empty load column is expected on that image.

**Size.** S for the probe. The generator already has the hooks.

**Risk.** Low for the probe. A miss against 800 ms becomes a product investigation, not a probe change.

**Dispatch brief.**

- Goal. Time only generated-window open against UX-M8-003's 800 ms VM budget.
- Files. A new probe script next to the old one. Read `apps.py` on the tag so the new timer does not copy `from_table`. Do not change product code unless the ready flag is the wrong stop point.
- Constraints. Python 3.9. Run on the FreeCAD 1.1 image (ChoreBoyExp), not the from-table dialog. The database must be the 100,000-invoice shape, not the demo shop.
- Success. The script prints one millisecond value whose start is `Window()` and whose stop is `_cbcs_ready is True`, and it does not include `formBuilder.fromTable`.

## 2. Preview theme

Still real. Preview chrome is snapshotted when the window opens or when the Preview style or screen changes. A later editor theme change does not reach the child.

`app/features/form_builder/integration/preview_control.py` `appearance` reads `current_theme_tokens()` and stores `shell_chrome_pairs` on `Appearance.chrome`. `_push` sends `SetAppearance` only from style and screen changes, and only while the window is open. `app/shell/shell_preferences_runtime.py` `handle_set_theme` updates the mode, persists it, and calls `apply_theme_styles`. It never touches `PreviewControl`. `app/features/form_builder/qtside/preview/launch.py` `preview_command` starts a separate AppRun child when that file exists. `app/features/form_builder/qtside/preview/pool.py` `_child_env` copies the environment and forces `CBCS_QT_API=pyside6`. The child does not share the editor's `QApplication` palette. `app/features/form_builder/integration/chrome.py` says the child has no shell and the pairs ride on `Appearance.chrome`.

The M10.1b report's "Preview on X11" section says the child stayed on the theme it opened with. That matches this code.

**Root cause.** Theme is an argument on the preview protocol, and the only sender is the Preview style or screen control.

**Proposed fix.** After `apply_theme_styles`, walk open form surfaces, take `preview_control`, and call the existing `_push` path (make it a public method if tests should not use the underscore). That sends `SetAppearance` with new chrome pairs. Do not restart the child. The protocol and the child handler already exist (`SetAppearance` in `app/features/form_builder/qtside/preview/child/session.py`).

**Size.** S.

**Risk.** Low. A push during child startup must no-op when `is_open` is false, which `_push` already checks.

**Dispatch brief.**

- Goal. An open Preview window follows View > Theme without a restart.
- Files. `app/shell/shell_preferences_runtime.py`, `app/features/form_builder/integration/preview_control.py`. A unit test that changes theme mode and records one `set_appearance`.
- Constraints. Python 3.9. Import Qt only through `app.qt`. Do not spawn a real AppRun in the unit test. Four themes must all send chrome pairs (light, dark, high-contrast light, high-contrast dark).
- Success. `python3 run_tests.py tests/form_builder/preview/test_m5_5a_child.py -q` with `CBCS_APPRUN` set, plus the new test. On a live editor, switch theme while Preview is open and confirm the chrome pairs change. The form body stays on the runtime palette. That split is already what `apply_shell_chrome` does.

## 3. Leaked widgets

Still real. Form-builder tests build live Qt trees and the session fixture does not destroy them. This run did not remeasure the ~13k figure. The leak mechanism is in the code.

`tests/form_builder/qtside/support.py` `realize` opens a `FormSession`, builds a `Realizer`, and returns both. `opened` is the context manager that calls `realizer.dispose()` and `session.dispose()`. Callers of `realize` that skip `dispose` leave the tree on the session `QApplication`.

`tests/form_builder/inspector/test_m4_visual.py` `_pane` calls `realize`, parents an `InspectorPane` on a new `QWidget`, shows it, and returns the window. `_close` exists and is the caller's job. `tests/form_builder/inspector/m5_5b_support.py` `open_pane` does the same. `tests/form_builder/conftest.py` `qapp` is session-scoped and only clears the clipboard. `tests/conftest.py` `qapp` is the same shape for the rest of the suite.

`QApplication.allWidgets()` stays unsafe at that volume. `app/features/form_builder/qtside/dialogs/from_table.py` already says the list yields destroyed widgets and touching one segfaults the binding, so the dialog records itself instead. Product code still scans the list.

- `app/features/form_builder/integration/settings_ext/connections_page.py` `open_sessions` walks `app.allWidgets()` for `FormSurface`.
- `app/features/form_builder/integration/rename_ext/methods.py` `_surfaces` walks `app.allWidgets()`.
- `app/features/form_builder/integration/run_links_ext/rules.py` `_surface` walks `topLevelWidgets` and then `allWidgets`.

**Root cause.** Widget owners are returned to tests with no fixture teardown, and three product lookups use the global widget list instead of a registry.

**Proposed fix.** Prefer `opened` or a context manager that always disposes. Add a function-scoped autouse fixture in `tests/form_builder/conftest.py` that, after each test, closes and `deleteLater`s new top-level widgets and calls `processEvents`. Count `topLevelWidgets` before and after. Do not call `allWidgets` in that fixture. Once top-level widgets are destroyed, their children go with them. Replace the three product scans with the surface the window already holds (`_form_undo_surface` is what `_surface` checks first). Keep `allWidgets` out of `app/`.

**Size.** M. The fixture is S. Replacing the three scans is the rest.

**Risk.** Medium. A fixture that deletes a widget a later test in the same module still holds will flake. Module-scoped windows such as `tests/form_builder/qtside/test_m5_keyboard_scripts.py` `shop` must be excluded. That fixture already calls `shutdown_main_window_for_test`.

**Dispatch brief.**

- Goal. A PySide6 form-builder unit run ends with the same top-level widget count it started with, and product code does not call `allWidgets`.
- Files. `tests/form_builder/conftest.py`, `tests/form_builder/qtside/support.py`, the `_pane` and `open_pane` helpers, the three product functions above.
- Constraints. Python 3.9. The counter is test-only. Do not call `allWidgets` from `app/` or from the fixture. Skip the fixture when `form_builder_enabled()` is false so the PySide2 shard stays a no-op.
- Success. On a PySide6 AppRun, `python3 run_tests.py tests/form_builder/qtside/test_realize.py tests/form_builder/inspector/test_m4_visual.py -q` prints a leak count of 0. `rg "allWidgets" app/features/form_builder` is empty.

## 4. Project tree reads every `.py` on the UI thread

Still real. The read moved out of the presenter and into the generated-file helper. The presenter still calls it while building each tree row.

`app/shell/project_tree_presenter.py` `build_tree_item` calls `is_generated_module(node.absolute_path)` for every file row. `app/editors/generated_file.py` `is_generated_module` calls `generated_source_basename`. When `text` is omitted, `_header_source` calls `_peek`, which reads `_PEEK_CHARS` (512) from the file on the calling thread. For a `.py` file it also stats a sibling `.ui` or `.qrc` when the form builder is on (`_form_builder_on`). Directories are not peeked. Non-Python files return before the read.

**Root cause.** Generated-file detection is a synchronous disk read inside tree item construction, with no cache.

**Proposed fix.** Cache the peek result by absolute path and `(mtime_ns, size)`. Invalidate the entry when the tree refresh already knows the file changed. Do not add a background thread for this. A project open already walks the tree on the UI thread. A cache makes the second paint free and keeps the first paint to one short read per `.py`. Lazy expansion already exists (`lazy=True` adds a placeholder child). The leak is the eager branch and any refresh that rebuilds visible rows.

**Size.** S.

**Risk.** Low. A stale cache entry would show the wrong lock icon until the next invalidate. Key the cache on mtime so a save updates it.

**Dispatch brief.**

- Goal. Building the project tree does not re-read unchanged `.py` files.
- Files. `app/editors/generated_file.py`. Callers stay as they are. Add a test that peeks once, writes the file, and peeks again.
- Constraints. Python 3.9. The header check remains the first 512 characters. A sibling `.ui` still counts only when the form builder is on.
- Success. `python3 run_tests.py tests/unit/editors/test_generated_file.py -q`. A second `is_generated_module(path)` with an unchanged mtime does not open the file. Assert that with a counting open wrapper, not by reading a private cache dict.

## 5. Save As retargets before the write

Still real.

`app/shell/save_workflow.py` `handle_save_as_action` resolves the destination, rejects an already-open path, calls `retarget(source, destination)`, then `save_tab(destination, check_stale_disk=False)`. `save_tab` writes through `self._editor_manager().save_tab(file_path)`. On `OSError` or `ValueError` it shows "Save failed" and returns `False`. Nothing moves the tab back to `source`. The tab now names a path that may not exist.

**Root cause.** The editor identity changes before the bytes are on disk.

**Proposed fix.** Write the buffer to the destination first. Retarget only after the write returns. On failure, leave the tab on `source` and leave any partial destination file for the existing error dialog to mention. If a tab is already open on the destination, keep today's refusal.

**Size.** S.

**Risk.** Medium. Retarget also updates dirty state, drafts, and the project tree. The test should fail a write with a directory destination or a mocked `OSError` and assert the open path is still `source`.

**Dispatch brief.**

- Goal. A failed Save As leaves the tab on the original path.
- Files. `app/shell/save_workflow.py`. `tests/unit/shell/test_save_workflow.py` if that module already covers Save As.
- Constraints. Python 3.9. Do not retarget on failure. Do not delete the user's original file.
- Success. `python3 run_tests.py tests/unit/shell/test_save_workflow.py -q`. The new test asserts the tab path and that the original file is unchanged when the write raises `OSError`.

## 6. pg8000 test hard-codes a Mac path

Still real.

`tests/form_builder/engine/test_m8_3c_followup.py` sets `_PG8000` to `/Users/local/Projects/ChoreBoyCodeStudio_artifacts/vendor_pgtest`. `_convert_paramstyle` imports `pg8000.dbapi` and, on `ImportError`, skips unless that directory exists. Cloud and this VM do not have that Mac path, so `test_pg8000_sees_the_authors_sql` skips.

The resolver already exists. `testing/run_form_builder_checks.py` `_pgtest_vendor` walks `_vendor_candidates("vendor_pgtest")` and falls back to `ChoreBoyCodeStudio_artifacts/vendor_pgtest` beside the repo. `run_tests.py` `_pg93_path_insert` puts `resolve_artifacts_dir(repo_root) / "vendor_pgtest"` on `sys.path` only when the pytest args select the `pg93` marker. This test is `pytestmark = pytest.mark.unit`. It never asks for that insert. `scripts/cloud_runtime_lib.sh` `cloud_install_pgtest` installs pg8000 1.31.5 into `$CBCS_ARTIFACTS_DIR/vendor_pgtest` and into the FreeCAD 1.1 prefix.

**Root cause.** One test bypasses the artifacts resolver and the marker-gated path insert.

**Proposed fix.** Delete `_PG8000`. Call the same candidate walk `_pgtest_vendor` uses, or `dev_launch_editor.resolve_artifacts_dir(repo) / "vendor_pgtest"`. Skip with a message that names that directory when `pg8000` is still missing. Do not mark the test `pg93`. It does not need a live server. It needs the library.

**Size.** S.

**Risk.** Low. A machine with neither install still skips. A machine with `vendor_pgtest` runs the scan.

**Dispatch brief.**

- Goal. `test_pg8000_sees_the_authors_sql` runs on cloud when `vendor_pgtest` is installed.
- Files. `tests/form_builder/engine/test_m8_3c_followup.py`. Import the resolver. Do not copy the Mac string.
- Constraints. Python 3.9. No live Postgres. No new dependency pin.
- Success. With `CBCS_ARTIFACTS_DIR` pointing at a tree that contains `vendor_pgtest/pg8000`, `python3 run_tests.py tests/form_builder/engine/test_m8_3c_followup.py::test_pg8000_sees_the_authors_sql -q` passes. With the directory absent, the skip reason names the resolver path, not `/Users/local`.

## 7. Cloud install fallback, dockerd, gdb

The GitHub API fallback and gdb are still real. Starting dockerd is already on main.

`scripts/cloud_runtime_lib.sh` `cloud_download` runs `curl -fL --retry 5 --retry-delay 2` against the URL in `scripts/cloud_runtime_pins.env`. Those URLs are `https://github.com/FreeCAD/FreeCAD/releases/download/...`. A 504 fails the curl after retries. There is no call to `api.github.com`. `scripts/cloud_setup_screenshot_runtime.sh` reaches this through `cloud_install_appimages`.

dockerd is installed and started. `.cursor/Dockerfile` installs `docker.io`. `cloud_install_docker` in `cloud_runtime_lib.sh` installs it on a pod that lacks it. `.cursor/environment.json` `start` is `bash scripts/cloud_start_display.sh`, and that script's `start_dockerd` runs `sudo -n dockerd` when `docker info` is down. A daemon that never becomes ready is logged and does not fail the script. That is intentional in the script's header. Leave it.

gdb is absent. `cloud_install_apt_packages` lists capture and Qt libraries. It does not list gdb. The Dockerfile does not install gdb either. `rg gdb scripts .cursor` on main has no match.

**Root cause.** Release-asset downloads have no second URL, and the image never installs a debugger.

**Proposed fix.** In `cloud_download`, if curl exits on HTTP 502, 503, or 504, ask `https://api.github.com/repos/FreeCAD/FreeCAD/releases/tags/<tag>` for the asset whose name matches the filename, then download `https://api.github.com/repos/FreeCAD/FreeCAD/releases/assets/<id>` with `Accept: application/octet-stream`. Keep the sha256 check. Add `gdb` to the apt list in `cloud_install_apt_packages` and to the Dockerfile so an image rebuild and a plain pod agree. Do not change dockerd.

**Size.** S.

**Risk.** Low. The API path needs no token for public release assets. A rate limit should fall back to the original error, not a partial file.

**Dispatch brief.**

- Goal. A 504 from the FreeCAD release URL still produces an AppImage that matches the pinned sha256, and `gdb` is on `PATH` after cloud setup.
- Files. `scripts/cloud_runtime_lib.sh`, `.cursor/Dockerfile`.
- Constraints. Idempotent. Do not print tokens. Do not change the pinned version or hash.
- Success. `cloud_download` against a URL that returns 504 still leaves a file that `sha256sum -c` accepts. `command -v gdb` succeeds after `cloud_install_apt_packages`. `docker info` still works when the start script has run.

## 8. Stray `scratchpad/m84_timings.txt`

Still real.

`tests/form_builder/qtside/test_m8_4_try_data.py` `test_scratch_session_leaves_the_file_hash_unchanged` calls `_write_timings`. That helper sets `folder` to `Path(__file__).resolve().parents[3] / "scratchpad"`, creates it, and writes `m84_timings.txt`. `parents[3]` from `tests/form_builder/qtside/` is the repo root. `.gitignore` ignores `/artifacts/`. It does not ignore `scratchpad/`.

**Root cause.** A timing log was left on a path inside the work tree.

**Proposed fix.** Write under `artifacts/form_builder/` or skip the file unless an env var is set. The assertions in the test are on the in-memory samples, not on the file.

**Size.** S.

**Risk.** Low.

**Dispatch brief.**

- Goal. The test does not create `scratchpad/` in the repo.
- Files. `tests/form_builder/qtside/test_m8_4_try_data.py`.
- Constraints. Python 3.9. Keep the sample assertions.
- Success. `python3 run_tests.py tests/form_builder/qtside/test_m8_4_try_data.py::test_scratch_session_leaves_the_file_hash_unchanged -q` leaves `git status` without `scratchpad/`. If the log stays, it is under `artifacts/`.

## 9. Empty runtime inventory and the path-cache lock

Both are still real. They are not both in `paths.py`. The empty-inventory case is `app/project/dependency_classifier.py`. The lock gap is `app/bootstrap/paths.py`.

**Empty inventory.** `RuntimeModuleInventory.from_optional_frozenset` maps `None` to `unknown` and an empty frozenset to `empty`. `_classify_import` treats `PySide6` as runtime when `inventory.state != "loaded"`. That includes `empty`. The comment above the branch says to assume PySide6 only when nothing was probed. A loaded inventory that omits PySide6 correctly returns `missing`. The tests in `tests/unit/project/test_dependency_classifier.py` cover the unknown case and the loaded case. They do not cover `empty`.

`app/bootstrap/runtime_module_probe.py` `load_cached_runtime_modules` returns `frozenset(data["modules"])`. A cache file whose `modules` list is empty becomes `empty`, not `unknown`. Packaging then treats generated `PySide6` imports as runtime on a machine that recorded no modules.

This matters for that cache file. It does not matter for a missing cache (`None` stays `unknown`, which is the intended "not probed" assumption). It does not matter for a normal FreeCAD probe that lists `PySide` or `PySide6`.

**Path cache.** `cached_resolve` holds `_RESOLVED_LOCK` only around dict reads and inserts. `Path.resolve` runs after the lock is released. Two failures follow.

1. Thread A misses, drops the lock, and resolves. Thread B runs `invalidate_resolved` for a rename. Thread A takes the lock again and inserts the pre-rename path. The next lookup returns the stale path until another invalidate.
2. `Path.resolve` follows symlinks. That is item 12's runpy failure, not a lock bug.

The window is real for lint workers, which the comment in `paths.py` says share this cache. It is harmless for a single UI thread.

**Proposed fix.** Treat `empty` like `loaded` for the PySide6 branch, so only `unknown` assumes the module exists. Add a test with `RuntimeModuleInventory.from_optional_frozenset(frozenset())`. For the cache, keep resolve outside the lock and store a generation. `invalidate_resolved` bumps the generation. The insert is dropped when the generation changed. Do not hold the lock across `Path.resolve`.

**Size.** S for each. They can ship separately.

**Risk.** Low. The empty-inventory change can start flagging PySide6 as missing when a probe saved an empty list. That is the accurate result. Confirm a real probe does not save `modules: []` on success before tightening packaging.

**Dispatch brief.**

- Goal. An empty module cache does not classify PySide6 as runtime, and a rename cannot republish a resolved path that was invalidated mid-resolve.
- Files. `app/project/dependency_classifier.py`, `app/bootstrap/paths.py`, `tests/unit/project/test_dependency_classifier.py`, the existing resolved-path tests.
- Constraints. Python 3.9. `unknown` still assumes PySide6. Do not take the lock during filesystem IO.
- Success. `python3 run_tests.py tests/unit/project/test_dependency_classifier.py -q` includes an empty-inventory assertion that PySide6 is `missing`. A test that invalidates during resolve does not grow the cache with the old path.

## 10. Shop desk and other demo apps

This is not a gap in the editor. It is a limit of the three demo apps.

The M10.1b report says shop desk tabs do not launch the other two installed apps and that there is no cross-project open verb. CBCS today opens another project inside the editor. `app/shell/project_controller.py` `open_project_by_path` confirms "opening another project" and then loads it in the same window. `docs/manual_complete/chapters/050_projects.md` says the new project replaces the current one, and File > New Window is how you keep two. A packaged app is a separate AppRun. Nothing in the form generator emits a command that starts a different project's launcher. "Open another form" in the form builder stays inside the current project's forms folder (`docs/form_builder/manual/steps.md`).

**Root cause.** The demo wanted three apps to launch each other. The product opens projects in the editor and forms in one project.

**Proposed fix.** None for the editor. If the shop desk demo should launch Customer card and Products, add a button in that demo's window file that runs the other install's desktop `Exec`. Do not add a general cross-project command to the generator unless an operator asks for it.

**Size.** S for a demo button. L for a product command.

**Risk.** A product command would be a new workflow with no current user. Skip it.

**Dispatch brief.** Do not dispatch. The operator can ask for a demo-only button that starts the other two desktop files.

## 11. Packaging still lists form files when the builder is off

Still real for the report and the wizard lines. Blocking problems are already suppressed.

`app/features/form_builder/install.py` `form_builder_enabled` is true only when the kill switch is off and `select_binding()` is `PySide6`. `app/packaging/form_files.py` `form_packaging_issues` returns `[]` when that is false. `form_lines` and `form_report_dict` call `inspect_forms` with no gate. `app/packaging/layout.py` `form_package_lines` returns `form_lines`. `app/packaging/artifact_builder.py` spreads `form_report_dict` into `package_report.json`. `tests/unit/packaging/test_form_packaging.py` `test_pyside2_designer_ui_with_a_pixmap_path_adds_no_form_problems` asserts no `package.form.*` issues. It does not assert an empty `forms` list.

**Root cause.** The issue gate and the report were split. Only the issue gate checks the feature flag.

**Proposed fix.** Return `[]` from `form_lines` and `{"forms": []}` from `form_report_dict` when `form_builder_enabled()` is false. Keep scanning when the builder is on.

**Size.** S.

**Risk.** Low. A PySide2 package of a hand-written `.ui` stops listing generated-file rows. The files still copy with the project tree. That matches the issue gate's comment that a Designer `.ui` packages with no form-file problems.

**Dispatch brief.**

- Goal. On PySide2, `package_report.json` has `"forms": []` and the wizard has no form lines.
- Files. `app/packaging/form_files.py`, `tests/unit/packaging/test_form_packaging.py`.
- Constraints. Python 3.9. Do not skip copying the `.ui` file. Do not change the PySide6 report.
- Success. `CBCS_QT_API=pyside2 python3 run_tests.py tests/unit/packaging/test_form_packaging.py::test_pyside2_designer_ui_with_a_pixmap_path_adds_no_form_problems -q`, extended so the report's `forms` list is empty.

## 12. Known fast-shard failures

Ran on `origin/main` `b4d1f241` through `~/opt/freecad/AppRun` (Python 3.9.23, PySide2 and PySide6 both importable). `QT_QPA_PLATFORM=offscreen`. `CBCS_DISABLE_BACKGROUND_RUNTIME=1`. The full tree collection on this AppRun dies first. `tests/form_builder/conftest.py` import hits FreeCAD's `FemMigrateApp` meta path finder (`AttributeError: 'FemMigrateApp' object has no attribute 'find_spec'`). The four tests were run by node id so collection skipped that directory. Result. 3 failed, 1 passed, 3.73 s.

`/opt/freecad/AppRun` is not on this VM. The conda AppRun above is the one `scripts/cloud_setup_screenshot_runtime.sh` installs. Cloud's baked `/opt/freecad` may not have `FemMigrateApp`. Treat the collection error as this runtime, not as a main failure, until it shows up on `/opt/freecad`.

PR #176 is merged (`mergedAt` 2026-11-03, `https://github.com/joshuarocksolid/ChoreBoyCodeStudio/pull/176`). It passes `max_results` into buffer warm-up and resets the status bar when the last tab closes. It does not change REPL completion or hover. Both completion failures below reproduce on `b4d1f241`, which is after that merge.

### `test_build_runpy_bootstrap_payload_includes_path_and_argv`

Failed. The payload contained `runpy.run_path('/agent/repos/ChoreBoyCodeStudio/run_runner.py'...)`. The assertion wants `runpy.run_path('/workspace/run_runner.py'`.

`app/run/runtime_launch.py` `build_runpy_bootstrap_payload` runs `Path.resolve()` on the script and on each path entry, then `apprun_safe_python`. On this VM `/workspace` is a symlink to `/agent/repos/ChoreBoyCodeStudio` (`readlink -f /workspace`). Resolve follows it.

**Root cause.** The test asserts the pre-resolve string. Resolve follows a symlink that exists on this machine. On a machine where `/workspace` is a real directory, the assertion can pass. This is a test coupled to an unresolved path, not a broken launcher.

**Proposed fix.** Assert the resolved path. Keep `Path.resolve`. Add a temp symlink case if the product must preserve a symlink the child can see.

**Size.** S. **Risk.** Low. **Priority.** P2.

**Dispatch brief.** Goal. The test passes when `/workspace` is a symlink. Files. `tests/unit/run/test_runtime_launch.py`. Success. `python3 run_tests.py tests/unit/run/test_runtime_launch.py::test_build_runpy_bootstrap_payload_includes_path_and_argv -q` passes on this VM.

### `test_repl_completion_import_os_dot_uses_static_index_before_jedi`

Failed. No item was labeled `getcwd`.

`app/runner/repl_completion.py` `complete` returns as soon as `_complete_with_static_index` returns any items. `ReplCompletionRequest.max_results` defaults to 100. `provide_api_index_member_items` in `app/intelligence/api_index.py` sorts matches by name and slices to `limit`. `app/intelligence/stdlib_api_index.json` module `os` has 404 members. Alphabetical index of `getcwd` is 102 (the 103rd name). The first 100 are `abc` through `fwalk`. `getcwd` is dropped. Jedi is never called, so the later assertion `jedi_calls == []` was not reached.

**Root cause.** An empty prefix on `os.` is capped at 100 alphabetical names before a common function.

**Proposed fix.** When the member prefix is empty, do not pretend the first 100 names are the module. Rank a short stdlib head (`getcwd`, `path`, `environ`, `listdir`) first, or raise the REPL cap for an empty prefix and let the popup scroll. Keep the cap for a non-empty prefix.

**Size.** S. **Risk.** Low. **Priority.** P1 for the console. A user who types `os.` does not see `getcwd`.

**Dispatch brief.** Goal. `import os` then `os.` offers `getcwd` from the static index and does not call Jedi. Files. `app/intelligence/api_index.py` or `app/runner/repl_completion.py`, and the existing test. Constraints. Python 3.9. Do not load the whole 404 into the UI if the popup cannot hold them. Success. The existing test passes, and a prefix `g` still returns `getcwd`.

### `test_completion_and_hover_after_rename_request_the_new_path`

Failed on hover only. `completion_paths` equaled the moved path. `hover_paths` was empty.

`app/editors/code_editor_diagnostics.py` `event` handles `QEvent.ToolTip`. If `_line_hover_callback` returns true, it returns before `_hover_requester`. Team Sync is always installed (`app/features/spec.py` feature `team-sync` has an install and no `enabled` predicate). `app/features/team_sync/ui/controller.py` `_hover` returns true when the point is on team chrome and there is no blame line. `_pointer_on_team_chrome` treats `local.x() < gutter` as chrome. `line_number_area_width` in `app/editors/code_editor_chrome_mixin.py` is the icon zone plus padding plus digit width, which is greater than 2. The test sends `QHelpEvent` at `QPoint(2, 2)`.

**Root cause.** The test hovers the gutter. Team Sync consumes gutter tooltips. Completion uses a different requester, so that half passes. PR #176 does not touch this path.

**Proposed fix.** Point the test at the text viewport (`x` past `line_number_area_width`). Do not make gutter hovers fall through to semantic hover. The gutter is the blame card's target.

**Size.** S. **Risk.** Low. **Priority.** P2. This is a stale test coordinate, not a broken rename.

**Dispatch brief.** Goal. The test requests hover for the new path. Files. `tests/integration/shell/test_buffer_identity_after_move_integration.py`. Success. That test passes without changing Team Sync.

### `test_dragging_a_tab_sideways_onto_the_other_tab_bar_moves_it`

Passed once on this AppRun. Not reproduced. No root cause. Re-run on the runtime that failed it before changing the drag code.

## 13. ChoreBoy rollout memo

Shipping the form builder onto production ChoreBoys means replacing the FreeCAD those machines run. The builder does not load on today's image, and the code it generates does not import on that image.

**Runtimes.** `docs/DISCOVERY.md` section 1A. Production AppRun is Python 3.9.2. The same document's FreeCAD 1.1 notes. Python 3.11.14, PySide6 6.8.3, PySide2 absent, `os.memfd_create` removed, ctypes jailed to `/opt/freecad`. `docs/PYSIDE6_MIGRATION_PLAN.md` records the same 1.1 image on ChoreBoyExp and says everyday slots were still 3.9.2 and PySide2 on 2026-10-20. `app/features/form_builder/install.py` registers the builder only when `select_binding()` is PySide6. Generated modules import PySide6 (`app/features/form_builder/engine/codegen/emit.py` is a PySide6 module emitter). A form saved on 1.1 does not import on 1.0.

**Vendor bundle.** The shipped native contract is CPython 3.9, SOABI `cpython-39-x86_64-linux-gnu` (`AGENTS.md`, `vendor/README.md`). `package.py` downloads those wheels. FreeCAD 1.1 cannot load a `.so` from the CBCS install. `docs/DISCOVERY.md` says a copy under `/home/default` or `/tmp` fails with `failed to map segment`, and the memfd path in section 4E does not work. Tree-sitter on 1.1 has to be the copy in the FreeCAD image, not the cp39 vendor tree. A cp311 vendor tree must not be shipped to 1.0 machines. One artifact cannot feed both images.

**AppArmor.** FreeCAD 1.0, measured 2026-10-20 (`docs/DISCOVERY.md` section 4G). AppRun may exec `/opt/freecad/AppRun`, `/bin/sh`, and `/bin/ls`. It denies bash, `/usr/bin/python3`, `/usr/bin/env`, and git. FreeCAD 1.1 reverses the shell rule. `/bin/sh`, bash, `shell=True`, and git are denied, and an AppRun child is allowed. Preview and packaged apps must keep using AppRun `-c`, not a shell. `apprun_safe_python` exists because 1.1 rejects a slash-free `-c` argument longer than 255 bytes. 1.0 does not. Payloads still go through that helper so one launcher serves both.

**Install path.** Production launch is `/opt/freecad/AppRun`. Desktop `Exec` lines in `docs/DISCOVERY.md` call that path. Replacing `/opt/freecad` is the machine upgrade. CBCS state stays at `/home/default/FreeCAD/CBCS/state` (`docs/ARCHITECTURE.md`). An install of the editor under a versioned directory does not move that state. The FreeCAD upgrade and the CBCS upgrade are different writes.

**Rollback.** Keep the 1.0 tree. A side-by-side `/opt/freecad-1.0` (or the installer that wrote the current tree) can be pointed at by the desktop files. Do not delete 1.0 in the same step that switches `Exec`. Generated form apps are not runnable on the rolled-back image. Editor projects saved as `.ui` plus hand-written Python still open. The visual builder stays hidden on 1.0 because `form_builder_enabled()` is false.

**Which apps depend on 1.0.** The repo does not name a shop application that requires FreeCAD 1.0. The dependency is the machine image. `templates/qt_app/main.py` imports `PySide.QtWidgets`, which follows FreeCAD's shim and therefore follows the image. Apps that import `PySide2` by name break on 1.1, where PySide2 is absent. Apps the form builder generates import `PySide6` and break on 1.0. IntellaQuote is the one desktop name `docs/DISCOVERY.md` records (`/home/default/IntellaQuote.desktop` starts `/opt/freecad/AppRun`). Its source is not in this repo, so this note cannot say whether it imports PySide2 or the shim.

**Decision.** Do not enable the builder on production until those machines run FreeCAD 1.1. Ship the editor build that already hides the builder on PySide2. Upgrade FreeCAD as its own change, with 1.0 left on disk, and re-probe AppArmor, hidden paths, and one shim-based app before deleting 1.0. The operator could instead install 1.1 beside 1.0 and point only form-builder apps at the 1.1 AppRun. That needs a second desktop `Exec` and a support story for two Pythons. It is the safer trial.

## 14. Trail items still open and not in 1 to 13

The M-reports do not use one heading "Open issues". The leftovers are the Deferred, Carried, and Follow-up sections. Items already fixed on main are omitted here. Closed on main, so not dispatched. Method rename of closed forms (`app/features/form_builder/engine/project/closed_forms.py` and `rename_ext/methods.py` `closed_note`). Nullable time blank as a flag (`record.py` `_blank_time_lines`). The pg8000 unsearched banner in newly generated lists (`listing.py` `_cbcs_list_unsearched`). The show path collecting line rows before it fills the header (`record.py` `_cbcs_show`). Unique checks parse as `Unique` (`engine/logic/checks.py`).

### 14.1 Dead connection stays cached

Still real. The generated connections module in `app/features/form_builder/engine/data/connections_module.py` lines 45 and 95-97 stores the DB-API connection in `_OPEN`, and `open_connection` returns it without a ping. `close_all` is the only clear. A server restart leaves the next `work()` on a dead connection.

**Root cause.** The cache key is the connection name, and nothing checks the socket.

**Proposed fix.** On the first use inside `work()`, run a cheap probe for Postgres and reconnect once. Keep SQLite as it is. Do not reconnect in the middle of a nested `work()`.

**Size.** S. **Risk.** Medium. A reconnect must not drop an open transaction. **Priority.** P1.

**Dispatch brief.** Goal. A connection that the server has closed is opened again on the next `work()`. Files. `connections_module.py` and `tests/form_builder/engine/test_m8_1_module.py`. Constraints. Python 3.9. One retry. Nested `work()` still joins the outer connection. Success. A test that closes the cached connection under the name and then `work()`s still runs a query.

### 14.2 `fromisoformat` and a trailing `Z`

Still real on Python 3.9. `app/features/form_builder/engine/data/types.py` line 184 does `fromisoformat(str(value).replace("T", " "))`. That leaves a trailing `Z`. Python 3.9's `fromisoformat` rejects it. The generated record path in `record.py` uses the same replace. Python 3.11 accepts `Z`. Production ChoreBoy is 3.9.

**Root cause.** The parser assumes a 3.11 `fromisoformat`.

**Proposed fix.** Strip one trailing `Z` and treat the clock as UTC, or reject it with the existing unparsed-value note. Do it in `types.py` and in the generated copy so they stay aligned.

**Size.** S. **Risk.** Low. **Priority.** P2.

**Dispatch brief.** Goal. `2026-01-01T00:00:00Z` parses on Python 3.9. Files. `app/features/form_builder/engine/data/types.py`, the generated datetime lines in `record.py`, a unit test. Success. The test passes under `~/opt/freecad/AppRun` (3.9).

### 14.3 Lookup miss shows `(unknown #k)`

Still real. `app/features/form_builder/engine/codegen/expanders/lookups.py` line 290 adds `"(unknown #%s)"` when the combo has no row. `rows.py` line 1079 does the same for a line-grid editor. The M8.R deferral M9-4 said a failed lookup on New reports once and then shows that text. The text is still what the generator emits.

**Root cause.** A missing lookup row has a visible placeholder and no second attempt.

**Proposed fix.** Keep the placeholder so the raw key still round-trips. Reload the lookup when the connection recovers, and clear the placeholder when the key appears. Do not block the record on a failed lookup.

**Size.** S. **Risk.** Low. **Priority.** P2.

**Dispatch brief.** Goal. After a failed lookup, a successful reload replaces `(unknown #k)` with the label. Files. `lookups.py`, the lookup tests under `tests/form_builder/engine`. Success. A test that fails the first load and succeeds the second shows the label.

### 14.4 Start-screen `main.py` is outside form undo

Still real. `app/features/form_builder/integration/new_form.py` lines 159-163 say the form undo step does not cover `main.py`. The open tab is reloaded from disk. That is the M9-5 deferral (UX-TABLE-003).

**Root cause.** The start card writes a project file through the editor, not through the form command log.

**Proposed fix.** Leave it. The comment matches the spec. An undo stack that includes `main.py` would mix project creation with form edits. **Priority.** P2. Do not dispatch unless the operator wants that undo.

### 14.5 Try keeps prepared statements

Still real. `app/features/form_builder/qtside/preview/child/try_connections.py` line 1583 calls `driver.execute(..., prepare=True)` for psycopg. The M8.4 note deferred a memory check on the VM. Nothing in the repo records that measurement.

**Root cause.** Each distinct statement can stay prepared for the life of the Try connection.

**Proposed fix.** Measure first. If a long Try session grows without bound, set `prepare=False` or cap the connection's prepared cache. Do not change it on a guess.

**Size.** S after a measurement. **Risk.** Low. **Priority.** P2.

**Dispatch brief.** Goal. Say whether a Try session's prepared-statement count grows with distinct SQL. Files. `try_connections.py` only if the count grows. Success. A note with the count before and after a few hundred distinct statements.

## Priority

**P0.** Item 13. The builder and its generated modules need FreeCAD 1.1, and production machines run 1.0. Shipping the feature onto those machines before the image changes hides the builder or breaks the generated import.

**P0.** Item 5. Save As points the tab at the new path before the write. A failed write leaves the user on a missing file.

**P1.** Item 2. Preview ignores a live theme change. The protocol for a push already exists.

**P1.** Item 3. Test widgets leak, and three product paths still call `allWidgets`, which the from-table dialog already treats as a segfault.

**P1.** Item 4. Every project-tree `.py` row reads the disk on the UI thread.

**P1.** Item 12, the REPL `os.` cap. `getcwd` is past the first 100 names, so the console omits it. The hover failure is a gutter coordinate, not this priority.

**P1.** Item 14.1. A dead Postgres connection is reused until `close_all`.

**P1.** Item 1. The 800 ms number was not measured. The rollout story should not quote it until the generated-window timer exists. The work itself is a probe, not a product patch.

**P2.** Item 6. The pg8000 scan skips on cloud because of a Mac path.

**P2.** Item 7. Release downloads have no API fallback, and gdb is not installed. dockerd already starts.

**P2.** Item 8. One test writes `scratchpad/m84_timings.txt` into the repo.

**P2.** Item 9. Empty inventory pretends PySide6 exists. The path-cache insert can revive a renamed path. Both are narrow.

**P2.** Item 10. Shop desk not launching the other demos is not an editor gap.

**P2.** Item 11. The package report still lists forms on PySide2. Export is not blocked.

**P2.** Item 12, the runpy assertion and the hover coordinate. The sideways tab drag passed once here.

**P2.** Items 14.2, 14.3, 14.4, 14.5. Timestamp `Z`, the unknown-lookup placeholder, `main.py` undo, and prepared statements.

## Surprises

- The empty-inventory bug is in `dependency_classifier.py`, not `paths.py`. The lock gap is in `paths.py`.
- PR #176 is already merged and does not fix either completion failure that still fails.
- The sideways tab-drag test passed on this AppRun.
- Whole-tree pytest on `~/opt/freecad/AppRun` aborts in `tests/form_builder` because `FemMigrateApp` has no `find_spec`. Node ids avoid it.
- M7R-11 (closed forms and method rename) is implemented. The trail still calls it deferred.
