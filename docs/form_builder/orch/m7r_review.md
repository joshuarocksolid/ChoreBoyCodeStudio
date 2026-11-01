# M7 heuristic review

Mode is reference.

## Method

I opened 55 screenshots. The walk set is `scratchpad/walk7r` (copied from `scratchpad/walk77` after the persona walk). The screenshot set is `scratchpad/shots7r`. Themes I opened are light, dark, high contrast light, and high contrast dark. Scales I opened are 100% and 200%. The 200% files are `state-filled-light-200.png`, `builder-value-dark-200.png`, `builder-if-high_contrast_light-200.png`, and `read-as-text-high_contrast_dark-200.png`. Inspector width 236 px is the files whose names end in `-236`. I opened those for State in light, dark, and high contrast dark, and for Checks in light. The walk uses the window's own inspector width. The 184 px files are the Logic panel and the Uses dialog. The walk outline pane is about 208 px wide. No shot sets the outline pane to 184 px.

The walk was `4 passed in 49.56s`. The screenshot run was `9 passed in 84.58s`. No file skipped. `test_m7_4_k29.py` writes verb pages for light at 100% only, and that test passed.

## Findings

| id | screen | heuristic | what's wrong (quote the screen) | severity | fix |
| --- | --- | --- | --- | --- | --- |
| M7R-01 | Try, walk preview | 1 Visibility of system status | After the try key the window stays on Design. The What ran panel is absent. The status bar still says "Save · Push button · row 2 of the vertical layout". The launch failure is absent from this screen. The shot set's What ran panel does open and lists the run. | S2 | Fixed. A failed open shows the first line of the error. If `/opt/freecad/AppRun` is missing, the preview starts on the editor's interpreter. The walk shot above is from before this fix. |
| M7R-02 | State, closed rows | 6 Recognition rather than recall | The closed Enabled when row shows "Discount is c now: no" on the walk, "Discount is check now: no" on the State shot at 100% and at 200%, and "Discol now: no" at 236 px. At 236 px Value shows "typed by the pe". The closed Visible when row shows "eeds a window value" where the row is "window.is_manager()" and "now: needs a window value". | S2 | Fixed. The sentence wraps, and "now:" sits on the line under it. The shots above are from before this fix. |
| M7R-03 | Checks | 6 Recognition rather than recall | The email row shows "Enter an email addres…". The full message is "Enter an email address like name@example.com". | S2 | Fixed. The check message wraps and keeps the full words. The shot above is from before this fix. |
| M7R-04 | Events, step row | 6 Recognition rather than recall | The step shows "Check all fields (stops here if a…". The place link shows "invoic...:13". | S2 | Deferred, owner M8. The step row is a custom layout. Wrapping it is larger than this lane. |
| M7R-05 | Formula editor | 1 Visibility of system status | The completion list paints through the rows under it. The list shows "discountCheck", "rateLabel Dis...", and "discountEdit". Behind it, Read-only when, Value, and Format are broken into scraps such as "R" and "ed by the person". The same overlap is on the high contrast dark shot. | S2 | Deferred, owner M8. The list already raises itself. The rows under it still paint through. |
| M7R-06 | Formula editor | 5 Error prevention | While the list offers a match, the status says the prefix is wrong. "qty is not a field on this form." sits above "qtySpin Whole number". "disc is not a field on this form." sits above "discountCheck". The finished name "missingField" keeps "missingField is not a field on this form." and the list has no row for it. | S2 | Fixed. While the list has a match, the status keeps the type line and drops "is not a field on this form." A finished name with an empty list still shows the error. |
| M7R-07 | What ran | 2 Match between system and the real world | The form says "Discount", "Qty", "Price", and "$6.00". The trace says "lineTotalLabel · Value", "discountEdit · Enabled when", "emailEdit · Checks", and "saveButton · When clicked". The same names are on the high contrast light and high contrast dark shots. | S2 | Deferred, owner M8. The trace lines come from the generated names. |
| M7R-08 | Logic panel | 4 Consistency and standards | One state row says "Discount rate" and "Enabled when". The next says "lineTotalLabel" and "qtySpin * priceSpin". The closed State row for that value says "Qty × Price". | S2 | Deferred, owner M8. The Logic panel still shows the stored formula. |
| M7R-09 | Uses at 184 px | 8 Aesthetic and minimalist design | The call breaks mid-word. "self.ui.discountEdit.setEn" is on one line and "abled(True)" is on the next. The Logic panel at 184 px breaks the same call as "setEna" and "bled". | S3 | Deferred, owner M8. The width stays 184 px. |

## Known notes

M7R-02 is fixed in this lane. The shots still show the old elision. On the walk the closed row read "Discount is c now: no". On the State shot it read "Discount is check now: no", and at 236 px "Discol now: no". The row now wraps the full sentence, and "now:" is on the next line.

The outline object name still elides on nested rows. The walk outline shows "Discount discoun...", "discount edit disc...", and "Line total lineTota...". The pane width stays. The tooltip now carries the spoken name, the class, and the object name, for example "Discount rate · Line edit · discountEdit".

## Deferred

| id | screen | what's wrong | owner |
| --- | --- | --- | --- |
| M7R-04 | Events step | "Check all fields (stops here if a…" and "invoic...:13" | M8 |
| M7R-05 | Formula list | The completion list paints through the rows under it | M8 |
| M7R-07 | What ran | Trace uses object names such as "lineTotalLabel · Value" | M8 |
| M7R-08 | Logic panel | "lineTotalLabel" and "qtySpin * priceSpin" beside "Qty × Price" | M8 |
| M7R-09 | Uses at 184 px | "setEn" / "abled" | M8 |
| M7R-10 | Commit a rule | Mac added p95 44.076 ms against 17 ms. VM added p95 79.905 ms against 50 ms. Profiles are `docs/form_builder/orch/m7r_mac/results/profile_commit_added.txt` and `docs/form_builder/orch/probe_m7r_vm/results/profile_commit_rule_added.txt`. The hot path is a full document walk on commit. | M8 |
| M7R-11 | Method rename | Closed forms that name the method are not listed or rewritten. The preview sentence would be "Also used in {form}.ui (not open)". Apply needs the rename plan, the .ui writer, and undo. That is more than this lane. | M8 |

## Screens that held up

The value builder shows "Qty × Price" and "now: 0.00" in light and in dark at 200%. The if builder's sentence reads "If Discount is checked, then Qty × Price, otherwise 0" in light and in high contrast light at 200%. The field chip on that row says "Discount · Y..." and the sentence under it is complete. Repair says "1 rule points at a widget that was renamed outside Code Studio." and the dialog says "oldName → noteEdit · Line edit" in light and in high contrast dark. Read as text keeps the full sentences, including "stops here if a field fails", in the walk, at 500 px, and in high contrast dark at 200%. The Check all fields and Show a message verb pages are plain and complete. No shot in this set shows a step's only-if row. The if builder above is the value If / Then / Otherwise page.

## Ten shots

1. `scratchpad/walk7r/owner-05-commit-enabled.png`
2. `scratchpad/shots7r/state-filled-light-100-236.png`
3. `scratchpad/walk7r/developer-18-formula-is-manager.png`
4. `scratchpad/shots7r/fx-complete-light-100.png`
5. `scratchpad/shots7r/verb-formula-light-100.png`
6. `scratchpad/walk7r/owner-20-commit-email.png`
7. `scratchpad/walk7r/owner-23-add-check-all.png`
8. `scratchpad/walk7r/owner-26-preview.png`
9. `scratchpad/shots7r/preview-what-ran-high_contrast_dark-100.png`
10. `scratchpad/shots7r/logic-uses-light-100-184.png`
