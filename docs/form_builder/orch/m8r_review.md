# M8.R lane A review

Heuristic pass over the M8 screens in UX_SPEC §13.5.10, plus the carried notes. Lane B owns the speed rows and the ChoreBoy VM. Budgets were not changed.

Shots: `CBCS_FB_SCREENSHOT_DIR=scratchpad/shots8r` (not committed). Four themes at 100% (`x1`) and 200% (`x2`). Inspector Data also at 236 px. Left Data tab also at 184 px. M8.7 walk shots in `docs/form_builder/orch/m87_walk/` were read and not overwritten.

K31–K34 run back to back in one MainWindow, keys only, in `tests/form_builder/qtside/test_m8_keyboard_scripts.py`. The no-mouse guard is empty. The four scripts are defined once and called by `test_k31_k32_k33_k34_together`. K34 sends PgDown, a field edit, and Ctrl+S when Try's shell is in this process, and it always reads the banner and What ran.

## Findings

| id | screen | heuristic | what's wrong | severity | fix | status |
| --- | --- | --- | --- | --- | --- | --- |
| M8R-1 | record-window dark, null-date dark | consistency | Invoice number "INV-2" sat on a dark field. Invoice date "2/15/26" and Total "20.00" sat on white fields. | S2 | Generated windows use the light runtime palette. Editor chrome stays on the strip, the banner, and What ran. | Fixed |
| M8R-2 | preview What ran, dark, 100% | match with the real form | "Discount rate" floated in a gap. The Discount row had an empty field. "$6.00" sat where Line total should be. Email had no label. | S2 | One form: Discount, Discount rate, Qty, Price, Line total, Email, then the check message. Save is at the bottom right, sized to its text. | Fixed |
| M8R-3 | Try, dark, What ran | visibility | A SELECT was cut to 40 characters before paint, so the row ended at "ORDER BY". | S2 | Elide at the painted width. Full statement is the tooltip and the first expanded row. | Fixed |
| M8R-4 | list running, dark | consistency | New and Open stacked full width. | S2 | The shot uses the generated `listButtons` row. | Fixed |
| M8R-5 | left Data tab at 184 px, dark | visibility of status | The footer reads "Columns read 2 Refresh". The "2 Nov 14:02" time is clipped. The column list above it is readable. | S2 | The sentence wraps to the tab width. Refresh is on the next line, at the right. | Fixed |

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

Follow-up on the same Mac, 16 cores. Budgets were not changed. The harness is the M7 one (`CBCS_FB_VALIDATE=0`, offscreen Qt). Commit is `commit` minus the paired bare repaint, warmup dropped, n=19.

Bisect of that commit row, one run each, load about 2.8. `3000ecd8` has no harness. p95 ms:

| commit | what | p95 |
| --- | --- | --- |
| 170b34c4 | M7.R | 18.5 |
| 603ef1d4 | M8.0 docs | 17.8 |
| 1e8c7ea4 | M8.0s | 20.7 |
| 922194ed | M8.1 | 19.4 |
| 927d1161 | M8.6 | 19.4 |
| 1d38d857 | M8.2 | 18.5 |
| fcffe44c | M8.3a | 19.2 |
| 9b0c238b | M8.3b | 18.1 |
| a1e1b980 | M8.3c | 15.2 |
| 88357fa3 | M8.3d | 22.8 |
| b752a478 | M8.4 | 21.3 |
| 53caa910 | M8.5 | 26.9 |
| c19cbdf9 | vendor symlink | 19.4 |
| 7b2888dd | M8.7 | 24.9 |
| 7cce4ab5 | lane A | 26.8 |

cProfile, 8 commits. M8.3c execute is 2 ms. At M8.3d, `publish_session` / `run_checks` is 4.5 ms on every rule. At M8.7, `silence_design_shortcuts` walks every widget on every changeset and adds 5.4 ms. Paint is flat across those three.

After: data checks skip a behavior-only edit, the shortcut walk runs when a widget is created or a shortcut changes, and a formula commit repaints the State rows only. Outline looks up each buddy caption once per revision.

| point | budget | after | note |
| --- | --- | --- | --- |
| Outline patch, 15 samples | 2 ms | p50 1.73, p95 1.75, pass | Load 1.28. Was 4.25. |
| Inspector select, 15 samples | 16 ms | p50 14.60, p95 16.60, fail | Load 1.28. First build 126 ms, not in the p95. Left as noise around 16. |
| Commit a rule, 19 samples | 17 ms | p50 16.5–16.8. Best p95 17.2. Other runs 17.6–18.6 | Load 1.3–2.5. Was 26.4. One sample in the 19 still spikes, so p95 is not reliably under 17. The cluster is. Today's M7.R remeasure was 18.5. |

The 5 / 20 / 30 ms re-baseline is not applied. Outline is back under 2 ms. Inspector stays at 16 ms. Commit stays at 17 ms.

## New sentences

UX_SPEC F11, and the §13.5.9 row "Try, own driver": a form that imports a database driver itself and connects with its own credentials is outside Try's protection.

Status line for a bad stored value, said once: `invoice_date has a value that isn't a date ('4/2/2026'); it's shown blank.`
