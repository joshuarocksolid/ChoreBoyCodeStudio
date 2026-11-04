- M7.5: FormulaEditor.setFocus override reveals Formula mode when Builder is up (comment cites key tests); revisit whether product callers should use present(). Status: Deferred (M9). Not an M8 screen.
- M7.7: closed Enabled-when sentence elides in the default inspector width ("Discount is c… now: no"); outline LEFT_MIN 184 elides the faint object name on nested rows. Decide widths in M7.R. Status: Deferred (M9). The M8 Data tab at 184 px still shows the column names. The timestamp clips (M8R-5, S3).
- M7.7: the walk's `_shot` grabs only MainWindow + active modal because the embedded form root is a parentless WA_DontShowOnScreen top-level (QGraphicsProxyWidget); offscreen reports it visible. Status: Closed. The walk records the window and the modal. The proxy stays offscreen on purpose.
- Try reload ~1.5 s after an edit; check against UX-M7-003 on the VM. Status: Deferred (lane B).
- Perf margins: behavior paint ~15 ms vs 16 ms cap on the Mac; re-measure on the ChoreBoy VM. Status: Deferred (lane B). Budget not changed.
- Non-US short dates don't round-trip through Format (en_US only by decision; confirm the parser rejects rather than corrupts). Status: Closed. A short date that is not in the project order stays in the field and the tooltip says how to type it. The reader does not swap the day and the month.
- Read as text page copies the flat toolbar QSS; move to the shared token/QSS helper so it can't drift. Status: Deferred (M9).
- Method rename rewrites only open forms; closed forms naming the method are not rewritten (decide: rewrite on disk or list them in the preview). Status: Deferred (M9). M7R-11 was not done in this lane.
- M7.7-07: Try mode/What ran not walked on Mac (no /opt/freecad/AppRun); walk it on the ChoreBoy VM. Status: Deferred (lane B).

## Carried to M8 from the M7.R sign-off (2026-11-01)
- Commit a rule, Mac: p95 16.2–17.7 ms across runs against 17 ms (p50 ~15 ms). The VM passes at 33 ms against 50 ms. Look for more margin: per-commit paint/repaint, and the State row update. Status: profiled, not fixed. This Mac, one run, p95 26.41 ms. Proposal in m8r_review.md. Budget not changed.
- Section 12 budgets fail on this Mac under load: outline patch is 4.2 ms against 2 ms, and it fails the same at `3000ecd8`. Inspector select fails intermittently, 29.7 ms against 16 ms. Re-baseline these or fix them; don't silently raise the budget. Status: profiled, not fixed. This run, load about 2 on 16 cores: outline p95 4.25 ms, inspector p95 17.42 ms. Proposal in m8r_review.md. Budgets not changed.
- M7R-11: method rename does not touch forms that aren't open. Status: Deferred (M9).
- The What ran preview shot fixture shows a floating "Discount rate" label under the form, the buddy added for the shot. Lay the fixture out properly. Status: Fixed (this commit). The label is the first row.
- The preview "Window values" strip is dark on a light user form in dark theme. Status: Fixed (this commit). Window values use the light runtime palette.
- The incremental rule graph (`rules._assemble`) is a correctness-sensitive cache. Any new formula-writing path must go through `set_logic`, or the note must be dropped. Status: Closed. This lane adds no formula writer.

## Carried to M8.R from M8.1 (2026-11-02)
- unit-py311 is load-sensitive: at load 50-66 three runs each timed out (30 s per-test cap) in a different pre-existing test (pytest capture, test_no_stale_layout_items 12-37 s, preview child eventFilter). Not an M8.1 regression (base 25 s vs M8.1 12.6 s back to back). Decide in M8.R: raise the cap for known-heavy Qt tests or gate under a load check. Status: Fixed (this commit). Those tests have timeout 120. The global cap stays 30 s. "pytest capture" is a stack frame, not a test name.
- PostgreSQL from the ChoreBoy VM is untested: the VM reached neither the Mac nor Debian on 54329 (AppArmor denies /proc/net/route). Status: Deferred (lane B).

## Carried from M8.6 (2026-11-02)
- To M8.2: FB3xx `run_checks` results are not published onto the Problems panel yet. M8.2 wires them (it owns the binding checks). Status: Closed. `data_checks_bridge.arm` publishes into the session, and Problems reads `session.diagnostics`. The leftover FB312 bracket is stripped at the bridge.
- To M8.R: the footer date uses English month abbreviations, not the locale (en_US only, so acceptable; confirm). Status: Closed. The fresh footer shot says "Columns read 2 Nov 14:02".
- To M8.R: an unparented `QHBoxLayout` filled before `addLayout` crashed at interpreter teardown when the footer and shot tests ran together. Parent layouts first; consider a lint-free review note for other panels. Status: Fixed (this commit). Layouts are parented before they are filled, including What ran's button row.
- To M8.R: the AppArmor proof of the helper under AppRun on the VM was not run (PostgreSQL from the VM is still unreachable). Status: Deferred (lane B).

## Carried from M8.3a / M8.3b
- Generated dialogs have no palette of their own: in dark, spin boxes, toolbar buttons and table viewports draw light next to dark line edits (seen in M8.2 null-date, M8.3a lookup-also, M8.3c list-running shots). Status: Fixed (this commit). Preview and Try pin the light runtime palette. Shots in four themes.
- A bad stored date string (`''`, `'4/2/2026'`) stops a record window (and a lines grid) from opening with ValueError. Status: Fixed (this commit). SQLite tests on the record and on a line.
- A decimal with more places than the column scale is rounded by QDoubleSpinBox on open-close and the form goes dirty. Status: Fixed (this commit). The dirty check and the UPDATE compare values rounded to the widget's decimals.
- Lines: reorder + add without the cached UNIQUE (link, position) index has no park pass (no end-user reorder control yet). A `CHECK (position > 0)` would reject the park pass. Status: Deferred (M9-3).
- Lines: a lookup load failure on New is reported once; the lookup column shows "(unknown #k)". Status: Deferred (M9-4).
- A nullable time keeps midnight as its blank (QTime can't go below 00:00), on record fields and grid cells. Status: Deferred (M9-1).
- FB312's Problems text still carries "[Use a search screen instead]"; the inspector hides it until M8.3d registers `register_search_screen`. Status: Fixed (this commit). Problems drops the bracket. The inspector button stays.

## Carried from M8.3c
- Grok saw one bus error in Qt garbage collection inside `read_ui` when running M8.2/M8.3b/M8.3c tests in one process (at `test_a_failed_line_lookup_still_saves_the_lines`). The lead's rerun of all M8.2/3/6 tests in one process (139 passed) did not reproduce it. Watch for it in M8.R. Status: Closed. Not reproduced here. Watch it if a later run dies in `read_ui`.
- A list saved before FB314's pg8000 refusal existed runs unsearched on pg8000 with no banner (the editor shows FB314). Status: Deferred (M9-2).
- New and Open in the M8.3c running-list fixture stack full-width; M8.3d's generated list screens set the real layout. Status: Fixed (this commit). The shot uses `listButtons`.

## From M8.3d (#209)
- `new_form.py` `_create_planned`: if `apply_plan` raises while the form's tab already has a session open, the file on disk is the rendered form but the tab can still hold the empty document; a later save from that tab could overwrite it. Close or reload the tab on that path. Status: Fixed (this commit). The tab reloads from disk, or closes if the write failed.
- The record toolbar's Next/Last stay enabled while "New invoice" is shown; check against UX_SPEC record toolbar states. Status: Closed. LOGIC §5.5 enables Next and Last when `form.position < form.count`. A new record reports position 0, so they stay enabled while earlier records exist. First, Previous, Next, and Last ask before leaving. UX_SPEC F8 points at that table.

## From M8.4 (#210)
- Documented caveat: in rollback mode `nextval` and a `setval` inside a user function advance sequences (warned once). Confirm the UX copy for that warning in the persona walk. Status: Closed. F11 already sends that warning to What ran.
- Out of scope but worth a sentence in docs: a form that imports psycopg itself and connects with the connections.json credentials bypasses Try entirely. Status: Fixed (this commit). The sentence is on F11 and in §13.5.9.
- psycopg keeps up to ~100 prepared statements per Try connection (prepare=True); fine for a session, check memory on the VM. Status: Deferred (lane B).
- What ran caps statements at 40 characters before paint (SELECTs end in "ORDER BY …"). Status: Fixed (this commit). Elide at the painted width. Full text in the tooltip and the expanded row.

## From M8.7
- Developer walk: "1 error" appears after typing a hook with `from PySide.QtWidgets import QMessageBox` in invoice_window.py. Confirm it's the editor's import check not knowing FreeCAD's `PySide` shim (fine on ChoreBoy?) and decide the right diagnostic. Status: Fixed (this commit). Those four modules classify as runtime even when the inventory is loaded without them. QtPrintSupport stays missing.
- Try is only verified child-side (M8.4 tests); the walk can't see the preview process. Do the K34 Try walk on the VM with a real display in M8.R. Status: Deferred (lane B) for the real display. The Mac script reads the banner and What ran, and sends the keys when the shell is in-process.
- After Eject plus an edit of the window file, one Undo is refused ("invoice_window.py changed after Eject…"), as specified; check the persona finds the way out. Status: Closed. The refusal is the specified way out.
- Form undo doesn't cover a main.py written by the start-screen choice (UX-TABLE-003). Status: Deferred (M9-5).
