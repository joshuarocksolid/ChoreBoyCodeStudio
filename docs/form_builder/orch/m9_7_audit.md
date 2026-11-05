# M9.7 logic audit

| Finding | Status |
| --- | --- |
| S1. A failed commit left the new key and reloaded line keys on the form. | Fixed. `tests/form_builder/engine/test_m9_7_save_state.py::test_a_failed_commit_keeps_the_typed_line_for_the_next_save` |
| S3. Try save did not put back the key, line snapshot, deleted line keys, or line model. | Fixed. `tests/form_builder/qtside/test_m9_7_try_readonly.py::test_rolled_back_save_puts_back_the_key_snapshot_and_line_model` |
| S2. Record steps did not stop the list. | Fixed. `tests/form_builder/engine/test_m9_7_steps.py::test_save_returning_false_stops_the_list` |
| S2. Open-form called the window, guessed the class, read every key with `currentData`, skipped refresh and the window-mode prompt, and called `exec` on a main window. | Fixed. `tests/form_builder/engine/test_m9_7_steps.py::test_open_form_reads_a_spin_box_key_through_the_ui`, `test_open_form_imports_the_class_stored_in_the_ui`, `test_refresh_lookups_runs_after_the_dialog_closes`, `test_window_mode_asks_before_show`, `test_a_main_window_cannot_open_as_a_dialog` |
| S2. Find on pg8000 with two or more columns. | Fixed. `tests/form_builder/engine/test_m9_7_find_escape.py::test_pg8000_converts_every_placeholder_in_a_three_column_find` and `tests/form_builder/engine/test_m8_2_followup_pg93.py::test_postgres_find_escape_matches_two_columns` |
| S2. A missing connection overwrote the generated module. | Fixed. `tests/form_builder/engine/test_m9_7_keep_generated.py::test_a_missing_connection_keeps_the_previous_python_file` |
| S2/S3. Value rules showed scientific notation. | Fixed. `tests/form_builder/engine/test_m9_7_number_text.py::test_a_value_rule_shows_two_hundred_not_scientific_notation` |
| S3. Whitespace-only text was saved as typed. | Fixed. `tests/form_builder/engine/test_m9_7_save_state.py::test_nullable_text_saves_blank_as_null` |
| S3. `and` / `or` evaluated both sides. | Fixed. `tests/form_builder/engine/test_m9_7_short_circuit.py::test_blank_record_does_not_call_ok` |
| S3. Would-run `BEGIN READ ONLY` was not the first statement. | Fixed. `tests/form_builder/qtside/test_m9_7_try_readonly.py::test_begin_read_only_is_the_first_statement_after_the_driver_begin` |

## Deferred

| Finding | Why |
| --- | --- |
| A dead PostgreSQL connection stays in `_OPEN` and is never reopened. | Reconnecting changes the process-wide connection cache. This lane does not touch that lifetime. |
| A hand-written `{"check": "unique"}` is parsed and then dropped, with no diagnostic. | `plan` returns a field plan and has no diagnostic channel. A warning would have to be threaded through every caller. Not a one-line fix. |
| `datetime.fromisoformat` on Python 3.9 rejects a trailing `Z` and some fractional seconds. | The audit asked to record this, not to change the parser. |
| Renumbering line positions can collide with another clerk's rows. | The save fails cleanly. The audit asked to record that, not to change the lock. |
| `_cbcs_show` sets the header and key, then loads lines in a second transaction; if that lines query fails, the previous record's lines and line snapshot stay on screen under the new record. | Found by the M9.7 review, outside this lane's findings. Needs the show path to collect lines before applying the header, like the save path now does. |
| A new form that gets FB510 (missing connection) keeps its `.ui` but has no `ui_*.py` or window file until the connection is fixed. | The withhold choice is intended. Only the FB510 warning tells the author; a clearer first-run message is a polish item for M9.5. |

The M9.7 review also found that openForm in window mode called `_cbcs_confirm_leave` on forms with no record source (AttributeError). Fixed in 169e5957 with a test that runs the generated handler: `tests/form_builder/engine/test_m9_7_steps.py::test_window_mode_asks_before_show`.

Two-cart check on a real ChoreBoy floor: `docs/form_builder/orch/m9_7_floor/RESULT.md` (main repo, untracked evidence).
