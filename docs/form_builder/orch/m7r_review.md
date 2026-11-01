# M7 heuristic review

Mode is reference.

## Method

The walk set is `scratchpad/walk7r` (copied from `scratchpad/walk77`). The screenshot set is `scratchpad/shots7r`. Both were deleted and written again after the follow-up fixes. Themes opened are light, dark, high contrast light, and high contrast dark, at 100% and 200%. Inspector width 236 px is the files whose names end in `-236`. Logic and Uses at 184 px are the files whose names end in `-184`.

The walk was `4 passed in 49.81s`. The screenshot modules passed, including a second run of the What ran, Logic, and Checks shots after display names were wired through. `test_m7_4_k29.py` writes verb pages for light at 100% only, and that test passed.

The first follow-up commit is `485c949f`. This follow-up is `31a0a6b`. M7R-07 and M7R-10 are that commit. The other Fixed rows are `485c949f`.

## Findings

| id | screen | heuristic | what's wrong (quote the screen) | severity | fix |
| --- | --- | --- | --- | --- | --- |
| M7R-01 | Try, walk preview | 1 Visibility of system status | After the try key the window stays on Design. The What ran panel is absent. The status bar still says "Save · Push button · row 2 of the vertical layout". The launch failure is absent from this screen. The shot set's What ran panel does open and lists the run. | S2 | Fixed. A failed open shows the first line of the error. If `/opt/freecad/AppRun` is missing, the preview starts on the editor's interpreter. |
| M7R-02 | State, closed rows | 6 Recognition rather than recall | The closed Enabled when row shows "Discount is c now: no" on the walk, "Discount is check now: no" on the State shot at 100% and at 200%, and "Discol now: no" at 236 px. At 236 px Value shows "typed by the pe". The closed Visible when row shows "eeds a window value" where the row is "window.is_manager()" and "now: needs a window value". | S2 | Fixed. The sentence wraps, and "now:" sits on the line under it. `state-filled-light-100-236.png` reads "Discount is checked" and then "now: no". The same wrap is on the high contrast light 236 px shot. |
| M7R-03 | Checks | 6 Recognition rather than recall | The email row shows "Enter an email addres…". The full message is "Enter an email address like name@example.com". | S2 | Fixed. The check message wraps and keeps the full words. |
| M7R-04 | Events, step row | 6 Recognition rather than recall | The step shows "Check all fields (stops here if a…". The place link shows "invoic...:13". | S2 | Fixed. The step wraps. `scratchpad/walk7r/owner-24-check-all-first.png` shows "Check all fields (stops here if a field fails)" in full. A place link keeps the file name, or elides the middle and keeps `:line`. It does not cut the name and then append `:13`. |
| M7R-05 | Formula editor | 1 Visibility of system status | The completion list paints through the rows under it. The list shows "discountCheck", "rateLabel Dis...", and "discountEdit". Behind it, Read-only when, Value, and Format are broken into scraps such as "R" and "ed by the person". The same overlap is on the high contrast dark shot. | S2 | Fixed. The list is a child of the State section. It fills its own background and viewport in all four themes. The shot test samples pixels inside the list rect and accepts only the list fill, the text colour, and the selection blend. Letters still visible beside the list are the row ends the list does not cover. |
| M7R-06 | Formula editor | 5 Error prevention | While the list offers a match, the status says the prefix is wrong. "qty is not a field on this form." sits above "qtySpin Whole number". "disc is not a field on this form." sits above "discountCheck". The finished name "missingField" keeps "missingField is not a field on this form." and the list has no row for it. | S2 | Fixed. While the list has a match, the status keeps the type line and drops "is not a field on this form." A finished name with an empty list still shows the error. |
| M7R-07 | What ran | 2 Match between system and the real world | The form says "Discount", "Qty", "Price", and "$6.00". The trace says "lineTotalLabel · Value", "discountEdit · Enabled when", "emailEdit · Checks", and "saveButton · When clicked". The same names are on the high contrast light and high contrast dark shots. | S2 | Fixed. What ran uses the name the Logic panel row shows, from `widget_name`. `preview-what-ran-light-100.png`, `preview-what-ran-dark-100.png`, `preview-what-ran-high_contrast_light-100.png`, and `preview-what-ran-high_contrast_dark-100.png` show "Discount rate · Enabled when", "Line total · Value", "Note · Value", "Email · Checks", and "Save · When clicked". The form label on those shots says "Discount rate". Generated code still carries the object name. Consecutive identical "Rules ran (N)" rows collapse to one row with a count. The three "Rules ran (3)" rows in that shot are not consecutive, so they stay separate. |
| M7R-08 | Logic panel | 4 Consistency and standards | One state row says "Discount rate" and "Enabled when". The next says "lineTotalLabel" and "qtySpin * priceSpin". The closed State row for that value says "Qty × Price". | S2 | Fixed. `logic-filled-light-100.png` shows "Line total · Value · Qty × Price" and "Discount rate · Enabled when · Discount is checked". The raw formula is the tooltip. A formula the speaker cannot say keeps the code line under the row. |
| M7R-09 | Uses at 184 px | 8 Aesthetic and minimalist design | The call breaks mid-word. "self.ui.discountEdit.setEn" is on one line and "abled(True)" is on the next. The Logic panel at 184 px breaks the same call as "setEna" and "bled". | S3 | Fixed. Code lines gain a break opportunity before `.` and `(`. `logic-uses-light-100-184.png` breaks before `.setEnabled(True)`. The high contrast dark Logic panel at 200% and 184 px breaks before `.discountEdit.setEnabled`. |
| M7R-10 | Commit a rule | speed | A rule commit walked the form and rebuilt the canvas frame. Mac added p95 was 44.076 ms against 17 ms. VM added p95 was 79.905 ms against 50 ms. | S2 | Fixed. Mac added p95 is 16.414 ms (p50 15.232) against 17 ms. Load on that row was 3.71 3.83 3.90. Paired commit p95 22.424 ms, bare repaint p95 7.113 ms. VM added p95 is 33.075 ms (p50 26.988) against 50 ms, on ChoreBoyExp, Python 3.11.14, PySide6. The slot was released. A commit updates that rule's graph record, that State row's sentence and now value, and it does not call `setStyleSheet` on the row. |
| M7R-11 | Method rename | 6 Recognition rather than recall | Closed forms that name the method are not listed or rewritten. The preview sentence would be "Also used in {form}.ui (not open)". Apply needs the rename plan, the .ui writer, and undo. | S2 | Deferred to M8. |

## Deferred

| id | screen | what's wrong | owner |
| --- | --- | --- | --- |
| M7R-11 | Method rename | Closed forms that name the method are not listed or rewritten. | M8 |

Section 12 outline patch, three runs each, same row. At `3000ecd8` the p95 values were 4.212, 4.134, and 4.180 ms. On `fb/m7.r` they were 4.196, 4.169, and 4.204 ms. Load was about 8.95 5.13 4.39. Both miss the 2 ms budget the same way, so the budget stays.

## Ten shots

All of these were taken after the fixes.

1. `scratchpad/shots7r/state-filled-light-100-236.png` wrapped closed Enabled when, "Discount is checked" then "now: no".
2. `scratchpad/shots7r/state-filled-high_contrast_light-100-236.png` the same wrap on high contrast light at 236 px.
3. `scratchpad/walk7r/owner-24-check-all-first.png` the Events step "Check all fields (stops here if a field fails)" wraps in full.
4. `scratchpad/shots7r/fx-complete-light-100-236.png` the completion list.
5. `scratchpad/shots7r/fx-complete-dark-100-236.png` the same list in dark.
6. `scratchpad/shots7r/preview-what-ran-light-100.png` What ran with "Discount rate · Enabled when", "Line total · Value", "Email · Checks", and "Save · When clicked".
7. `scratchpad/shots7r/preview-what-ran-high_contrast_light-100.png` the same names on high contrast light. The dark and high contrast dark 100% shots say "Discount rate" as well.
8. `scratchpad/shots7r/logic-filled-light-100.png` "Line total · Value · Qty × Price".
9. `scratchpad/shots7r/logic-filled-high_contrast_dark-200-184.png` that row at 200% on high contrast dark, 184 px wide.
10. `scratchpad/shots7r/logic-uses-light-100-184.png` the Uses call breaks before `.setEnabled`, not inside the name.
