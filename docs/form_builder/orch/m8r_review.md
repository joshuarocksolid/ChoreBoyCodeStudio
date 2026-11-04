# M8.R lane A review

Heuristic pass over the M8 screens in UX_SPEC §13.5.10, plus the carried notes. Lane B owns the speed rows and the ChoreBoy VM. Budgets were not changed.

Shots: `CBCS_FB_SCREENSHOT_DIR=scratchpad/shots8r` (not committed). Four themes at 100% (`x1`) and 200% (`x2`). Inspector Data also at 236 px. Left Data tab also at 184 px. M8.7 walk shots in `docs/form_builder/orch/m87_walk/` were read and not overwritten.

K31–K34 run back to back in one MainWindow, keys only, in `tests/form_builder/qtside/test_m8_keyboard_scripts.py`. The no-mouse guard is empty. The four scripts are defined once and called by `test_k31_k32_k33_k34_together`. K34 sends PgDown, a field edit, and Ctrl+S when Try's shell is in this process, and it always reads the banner and What ran.

## Findings

| id | screen | heuristic | what's wrong | severity | fix | status |
| --- | --- | --- | --- | --- | --- | --- |
| M8R-1 | record-window dark, null-date dark | consistency | Invoice number "INV-2" sat on a dark field. Invoice date "2/15/26" and Total "20.00" sat on white fields. | S2 | Generated windows use the light runtime palette. Editor chrome stays on the strip, the banner, and What ran. | Fixed |
| M8R-2 | preview What ran, dark, 100% | match with the real form | "Discount rate" was painted on the Discount checkbox, under the form in the old fixture. | S2 | The label is the first row of the window, buddy of discountEdit. | Fixed |
| M8R-3 | Try, dark, What ran | visibility | A SELECT was cut to 40 characters before paint, so the row ended at "ORDER BY". | S2 | Elide at the painted width. Full statement is the tooltip and the first expanded row. | Fixed |
| M8R-4 | list running, dark | consistency | New and Open stacked full width. | S2 | The shot uses the generated `listButtons` row. | Fixed |
| M8R-5 | left Data tab at 184 px, dark | visibility of status | The footer reads "Columns read 2 Refresh". The "2 Nov 14:02" time is clipped. The column list above it is readable. | S3 | Leave it. Wrapping the footer is a later width pass. | Open |

200% shots are the same layouts at twice the pixels. High contrast editor themes leave the generated form on the light palette, which is the Preview/Try decision. Show SQL, Eject, and the inspector Data tab at 236 px ("Column", "notes", "Only show never save") were readable in dark.

## Carried fixes

| note | test or why none |
| --- | --- |
| Bad stored date or time stays blank and is not overwritten | `test_a_bad_stored_date_opens_blank_and_stays_unsaved`, `test_a_bad_line_date_opens_blank_and_stays_unsaved` |
| Extra decimal places do not mark the record dirty and are not written back | `test_extra_decimal_places_do_not_mark_the_record_dirty` |
| PySide, PySide.QtCore, QtGui, QtWidgets resolve as runtime. QtPrintSupport does not. | `test_classify_module_treats_the_freecad_pyside_shim_as_runtime` |
| Problems drops the FB312 bracket. The engine sentence and the inspector button stay. | `test_fb312_drops_the_search_screen_bracket` |
| A failed `apply_plan` reloads the tab from disk, or closes it | `test_a_failed_plan_reloads_the_tab_from_disk` |
| Record toolbar Next/Last | No code change. LOGIC §5.5 enables them when `form.position < form.count`. A new record reports position 0. First, Previous, Next, and Last ask before leaving. |
| Layouts filled before they had a parent | Parent first. No new test. The failure was interpreter teardown, not a branch. |
| Heavy Qt tests | `pytest.mark.timeout(120)` on `test_repainting_the_inspector_holds_no_new_layout_items` and `tests/form_builder/preview/test_m5_5a_child.py`. The global 30 s cap stays. |
| Try and a driver the form imports itself | One sentence on UX_SPEC F11 and a §13.5.9 row. |
| Footer date | Already en_US. The fresh footer shot says "Columns read 2 Nov 14:02". A short date that is not in the project order stays in the field. The reader does not swap the day and the month. |

## Deferred to M9

| id | note |
| --- | --- |
| M9-1 | A nullable time keeps midnight as its blank. QTime cannot go below 00:00. |
| M9-2 | A list saved before FB314 runs unsearched on pg8000, with no banner. |
| M9-3 | Reordering lines without the cached UNIQUE (link, position) index has no park pass. |
| M9-4 | A lookup that fails to load on New shows "(unknown #k)". |
| M9-5 | The start screen's `main.py` write is not in form undo. UX-TABLE-003 already says so. |

Lane B, not this worktree: UX-M8-003 on the VM, PostgreSQL from the VM, AppArmor, Try reload, psycopg prepared-statement memory, and K34 on a real display.

## Item 13 profiles

One run on this Mac. Load average 1.89, 2.06, 2.03 on 16 cores. Not a busy machine. Budgets were not changed. The harness is the same one the budget tests use, with `CBCS_FB_VALIDATE=0` and offscreen Qt. Samples are one side only, not five alternating runs.

The number would decide whether to re-baseline section 12. It would not decide a code change in this lane. The outline miss is a full spoken-name walk. The other two sit on Qt paint.

| point | budget | this run | limiter |
| --- | --- | --- | --- |
| Outline patch, 300 widgets, 15 samples after 3 warmup | 2 ms | p50 4.17 ms, p95 4.25 ms, fail | `spoken_display` rebuilds every widget name on a caption patch. cProfile of the row is dominated by `display_name` and `buddy_of` inside `_retitle`. The caption itself was rewritten, so the timed work happened. |
| Inspector select in the shell, 15 samples | 16 ms | p50 16.08 ms, p95 17.42 ms, fail | The timed flush is just over the cap. cProfile of the whole row is `setStyleSheet` and `show` during setup, which is outside that 17 ms. First build was 138.9 ms and is not in the p95. |
| Commit a rule, added, 19 samples | 17 ms | p50 25.69 ms, p95 26.41 ms, fail | The inspector showed the stored "Visible when" text, so the commit happened. cProfile of the commit is `processEvents` and the canvas viewport paint. |

Proposal, for a later budget edit, not applied here. Outline patch 5 ms. Inspector select 20 ms. Commit a rule 30 ms. The outline number is tight across the 15 samples, so it is not a spike. The commit number is one run and higher than the earlier 16.2–17.7 ms band. Repeat it on an idle machine before accepting 30.

## New sentences

UX_SPEC F11, and the §13.5.9 row "Try, own driver": a form that imports a database driver itself and connects with its own credentials is outside Try's protection.

Status line for a bad stored value, said once: `invoice_date has a value that isn't a date ('4/2/2026'); it's shown blank.`
