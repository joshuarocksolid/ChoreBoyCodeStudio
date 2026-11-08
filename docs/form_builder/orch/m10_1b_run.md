# M10.1b run

Clean pass: job `m10vm23-20261108T070647Z-d0f35a` on ChoreBoyExp (FreeCAD 1.1.1, AppRun Python 3.11.14, display 1680x1050). Probe return code 0. `results/steps.md` has 44 steps and no failures. Screenshots, `steps.md`, `timings.json`, and `facts.json` are in `probe_m10_vm/results/`.

The editor status on that boot was `Startup: Capability data unavailable | Syntax highlighting off`. The payload does not include `vendor/`. The form builder still ran.

## Apps

| App | Built | Packaged and installed | Launched from the installer |
| --- | --- | --- | --- |
| Customer card | Record form from `customers` (name, phone, email, credit limit, active). Email check, credit limit at least 0, Enabled when `active` (the panel reads "Active is checked"). Save writes `ui_customer_card.py`. Save button calls a method in the window file. | `/home/default/FreeCAD/Apps/customer_card` | Desktop Exec stayed up. `use_app` rc=0 |
| Products | List and record, stock-move lines, filter rule `form.count > 0` on `searchEdit`, record bar. Both `ui_products.py` and `ui_products_list.py`. | `/home/default/FreeCAD/Apps/products` | Desktop Exec stayed up. `use_app` rc=0 |
| Shop desk | Main window. File, Edit, and Help are in `shop_desk.ui`. Toolbar action ran. Tab widget insert closed. F7 and F8 ran. `ui_shop_desk.py` written. | `/home/default/FreeCAD/Apps/shop_desk` | Desktop Exec stayed up. `use_app` rc=0 |

Projects 2 and 3 were created with `create_blank_project` and `open_project_by_path`. The File > New Project dialog did not return once a project was already open (jobs m10vm3–m10vm7). The step log says so. The start checkbox stays off because `main.py` is already the project's file, so the probe writes the launch the manual describes.

Packaging: the wizard was opened, then `package_project` (the same call the Package button ends on) produced the installer. Install used `perform_install`, the wizard worker's call. No root.

## Defects

| App | Step | What was wrong | Fix | Rerun |
| --- | --- | --- | --- | --- |
| Customer card | Start card, Build a form from a table | `StartCard.mouseReleaseEvent` emitted `activated` and then called `super()`. Opening the form deleted the card. `super()` raised "Internal C++ object already deleted." | Call `super()` first, then emit on the next turn (`qtside/start/cards.py`). Test: `test_clicking_a_card_that_closes_its_page_does_not_crash`. | From-table passes on m10vm23. |
| All | View > Theme | `TeamInfoBar.apply_theme` called `setPixmap` on a deleted warning label. | Return when `wrapper_is_valid` is false (`team_sync/ui/info_bar.py`). No new test: it would poke a private label. | Theme steps pass on m10vm23. The earlier traceback is gone from the step path. |
| All | Package | With no runtime inventory, `import __future__` and `PySide6` were classified missing, so packaging stopped. | `__future__` is always stdlib. `PySide6` is runtime (`dependency_classifier.py`). Tests in `test_dependency_classifier.py`. | All three `package_project` calls succeed on m10vm23. |
| Products | Installed launcher | Generated list forms had no `_cbcs_form_count`. `form.count` raised `AttributeError`. | `listing.py` emits `_cbcs_form_count` from the list model's `rowCount`. Test: `test_a_list_form_count_is_the_rows_on_screen`. | Products launcher stays up on m10vm23. |
| Products | Build a form from a table, both files | Creating the list scheduled the start tab to close. `processEvents` ran that close while the from-table dialog was still up, so the record file was never written. | `_close_start_tab` waits while `formBuilder.fromTable` is visible (`new_form.py`). Test: `test_the_start_tab_stays_open_while_the_from_table_dialog_is_up`. | `ui_products.py exists=True` on m10vm23. |

Focused tests ran on this host with system Python 3.14.1 and its PySide6, not PySide6 6.8. The VM proof is the clean probe, which runs under FreeCAD 1.1 AppRun.

## Timings against the budgets

From `facts.json` on the clean pass. `os.getloadavg()` raises under AppArmor, so the idle-load column is empty.

| Row | Budget | Measured | Note |
| --- | --- | --- | --- |
| Editor start to window shown | none in the UX rows | 1955 ms | Status was not "Runtime ready". |
| Open a bound form (UX-M8-003) | ≤ 800 ms VM | customer 3738 ms, products 5691 ms | This timer wraps the from-table dialog, not a later open of a saved form. |
| Save (PLAN speed row) | ≤ 50 ms | customer 140 ms, products 174 ms, shop 6 ms | Over the plain 50 ms row for the two forms that generate code. |
| Save with rules (UX-M7-003) | ≤ 250 ms VM | 140 ms and 174 ms | Under that row. |
| Preview cold on the display | 3.9 s fact, not a budget | 6597 ms | Includes a fixed 6 s wait so the child window is on screen. |
| Package | no time budget | about 91–99 s | The probe waits up to 90 s for a wizard artifact, then calls `package_project`. |
| Install | none | 6–18 ms | `perform_install`. |
| Installed app start | none | 4000 ms | The probe's sleep before the grab, not time-to-window. |

## Preview on X11

Four grabs at 1680x1050: light, dark, high-contrast light, high-contrast dark. `popup black=None` means the parent process had no popup widget. The probe does not click combos or menus inside the preview child (that window is another AppRun). The child did not switch theme when the editor theme changed; it stayed on the theme it opened with. The preview window can sit over the lower right of the editor.

## Driver notes that are not product fixes

- `find` now walks every child with that name and prefers a visible one. Two open forms each have an outline.
- The outline paints the object name in a caption role. The products filter click matches that caption. Customer Enabled when ran against the widget the credit check had already selected, because the Logic tab had hidden the outline. The panel shows "Active is checked".
- Shop's tab pages do not launch the other two installed apps. There is no cross-project open verb. `use_app` opens the shop window's menus and sends Ctrl+N.
