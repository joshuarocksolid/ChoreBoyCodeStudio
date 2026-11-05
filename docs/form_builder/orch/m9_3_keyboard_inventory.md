# M9.3 keyboard inventory

Every user-facing form builder feature, the key that reaches it, and the test that drives it. A row is covered only when that test sends key events and fails if a mouse button arrives. Setup may open the project. On macOS, File > New Form is `action.trigger()` because Qt has no menu mnemonics there. That exception is the same one K1 already records.

Ctrl+R and Ctrl+Shift+R were already bound. This pass did not add a second shortcut for either.

## Commands, menus, toolbar

| Feature | Keyboard path | Test |
| --- | --- | --- |
| Quick Open | Ctrl+P, type, Return | `test_m5_keyboard_scripts.py::test_k17_pictures` |
| File > New Form | Alt+F, Down, Return (macOS triggers the action) | `test_m3_keyboard_scripts.py::test_k1_create_and_fill` |
| Save, undo, redo | Ctrl+S, Ctrl+Z, Ctrl+Shift+Z | K2, K9–K15, and the later together-sessions |
| Context menu | Shift+F10, then arrows and Return | `test_m5_keyboard_scripts.py::test_k16_main_window` |
| Zoom | Ctrl+=, Ctrl+-, Ctrl+0, Ctrl+9 on the canvas | `test_m3_keyboard_scripts.py::test_k8_views` |
| Designed toolbar | Shift+F10, Main window, Add toolbar | `test_m5_keyboard_scripts.py::test_k16_main_window` |
| Record toolbar | Space on Add toolbar in the Data pane | `test_m8_keyboard_scripts.py::test_k31_k32_k33_k34_together` |

There is no form-builder command palette. Ctrl+P stays the shell Quick Open.

## Canvas, outline, insert, inspector

| Feature | Keyboard path | Test |
| --- | --- | --- |
| Outline | Alt+1, arrows, F2 rename | `test_m3_keyboard_scripts.py::test_k4_rename_ten` |
| Move a page | Alt+1, Alt+Up | `test_m4_keyboard_scripts.py::test_k9_to_k15_in_one_session_keys_only` |
| Insert / widget box | Alt+2, type, Return, or `/` | same K9 session, and K1 |
| Canvas focus | Alt+3 | K1 and K2 |
| Layouts | Ctrl+1 wrap, Ctrl+Shift+B unwrap, Ctrl+Shift+G group | `test_m3_keyboard_scripts.py::test_k2_structure` |
| Inspector | Alt+4, Ctrl+F property search | `test_m3_keyboard_scripts.py::test_k5_sizing` and K11–K15 |
| Size | Hug, Fill, Fixed from the Size section | `test_k5_sizing` |
| Style sheet | Alt+4, Ctrl+F, type the sheet | `test_m5_keyboard_scripts.py::test_k18_style` |
| Pictures and resources | Icon row, then Ctrl+P on `resources.qrc` | K15 and `test_k17_pictures` |
| Promoted class | Shift+F10, Use my own class | `test_k19_your_own_class` |
| Tab order | F8, Enter, Shift+Enter, Backspace, Esc | `test_k23_tab_order_and_buddies` |
| Buddies | F7, Enter, Tab, type the field, Return | same K23 test |
| Go to widget | Ctrl+R, type, Enter. Esc closes | `test_m4_keyboard_scripts.py::test_k9_to_k15_in_one_session_keys_only` (`_k10`) |
| Rename | F2 in the outline | `test_k4_rename_ten` |
| In-place text | Enter on the canvas | K1 |

Ctrl+2 through Ctrl+6 (the other layout kinds) are bound. K2 presses Ctrl+1 only. The keys page lists the rest.

## Behavior, logic, signals

| Feature | Keyboard path | Test |
| --- | --- | --- |
| Behavior tab | Alt+B | `script_k24` in `test_m6_keyboard_scripts.py::test_k24_k25_k26_together` |
| Add an event and steps | Ctrl+Shift+E, type, Enter, Alt+Up, Ctrl+D, Delete | `script_k24` |
| Signals and slots | The Behavior list writes the connection. F4 opens the connections overlay | `script_k24`, `script_k25` |
| Write the method | Shift+F10, Write code for clicked, F12 | `script_k26` |
| Checks and formulas | K28–K30 | `test_m7_keyboard_scripts.py::test_k27_k28_k29_k30_together` |
| Logic panel | Alt+L focuses Filter logic. Down moves to the first matching row. Enter opens it. Up returns to the filter | `test_m9_3_keyboard.py::test_logic_filter_down_opens_the_row` |
| Uses | Shift+F12 | `test_m7_8a_keys.py::test_alt_l_focuses_the_filter_and_shift_f12_opens_uses` |

`L-logic-keyboard` is marked on `test_logic_filter_down_opens_the_row`. That test types a filter, moves with Down, and opens the formula. It does not call `setFocus`.

## Data, preview, start screen

| Feature | Keyboard path | Test |
| --- | --- | --- |
| Data pane, empty form | Ctrl+Shift+D lands on Connect to a table | `test_m9_3_keyboard.py::test_ctrl_shift_d_lands_on_connect` |
| Data pane, bound form | Ctrl+Shift+D, then the column rows | `script_k32` |
| Connections | Alt+F, Settings, Connections, Space through Add PostgreSQL | `script_k31` |
| Preview / Try | Ctrl+Shift+R. K34 reads the Try banner | `test_k20_preview_options_and_code`, `script_k34` |
| Form from a table | On the Start screen, Tab to a card, Ctrl+Down until "Build a form from a table", Return. Esc closes the dialog and focus returns to that card | `test_m9_3_keyboard.py::test_start_screen_from_table_escape_returns_to_the_card` |

## Names and contrast

`test_m9_3_names.py::test_open_surfaces_name_every_interactive_widget` walks the open form, the Go to widget popup, the Data pane, and the Form from a table dialog. A focusable widget passes when it has an accessible name, button text, a window title, or a label buddy. Containers (`QWidget`, `QFrame`, scroll areas, splitters, stacks, tab widgets, group boxes) may be unnamed.

Focus, selection, disabled text, error, and warning pairs are checked with `app.shell.contrast.contrast_ratio` in `test_chrome_contrast.py::test_focus_selection_disabled_and_error_clear_the_helper`.

High contrast grabs at 100% and 200% are `test_m9_3_shots.py`, written under `docs/form_builder/orch/shots_m9_3/` when `CBCS_FB_SCREENSHOT_DIR` points there.
