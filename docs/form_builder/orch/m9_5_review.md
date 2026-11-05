# M9.5 review

The tour is `tests/form_builder/qtside/test_m9_5_shots.py`. The re-run command is the docstring at the top of that file. Shots are `docs/form_builder/orch/shots_m9_5/`. Open `index.html` and each row is one state, with light, dark, and high-contrast dark side by side. Dense states add light at 200%. `before/` keeps only the shots whose pixels changed.

Wording used everywhere for Try. Press Ctrl+Shift+R to open Preview. Run behavior starts checked. When the form has checks, steps, or rules, Preview runs them and undoes database changes. Uncheck Run behavior to see the layout only. Try is that checked state, not a second command. The other choice would be to rename the checkbox to Try. The checkbox name stayed Run behavior, because that is what the box does.

## Findings

| Shot | What was wrong | Result |
| --- | --- | --- |
| 01-start-welcome | "No projects yet…" wrapped so "above." sat on its own line. "Recent Projects" was title case. | The empty line no longer wraps. The heading is "Recent projects". "New Project" and "Open Project" stay. They are the host window's buttons, and changing them would retitle the whole app. |
| 02-start-templates | The sentence under the title repeated what the cards already show. | Removed "Every starting point is already laid out, so it resizes with the window." |
| 04-start-from-table-empty | "Choose a connection" sat in the middle of the main.py note, and the dialog opened at 960×560. | The reason is its own line under the note. The dialog opens at 1100×680. |
| 07-form-empty | The empty page listed a third line of shortcuts. | Removed "/ insert · Ctrl+Shift+G wrap · F2 rename". The first two lines are the next action. The keys page has the shortcuts. |
| 12-canvas-insertion-line | The grab is the selection chip, not a drop line. | Left. Offscreen has no pointer path that holds a drop target open through the grab. |
| 18-canvas-zoom-75 and the Fit command | Fit floored at 75% while the zoom menu offers 50%. | Fit now floors at 50%, the same as the menu and UX-RESP-007. A 620 px page in a 440 px view is centered, and its left edge stays in view. Two widths keeps that scale. The 75% floor had been hiding a refit when the wide copy opened. |
| 31-inspector-step-picker | The first runs deleted the popup before the grab. | The picker opens after the theme is on. The shot is the Then… list. |
| 51-preview-options | `showMenu` runs its own loop and the tour never returned. | The menu is shown without that loop. The shot is Text size, Screen scale, and Preview. |
| 56-form-fb510 | A new form with a missing connection withheld the generated files and said nothing on the tab. | The tab says "Generated files appear once the connection works." and has a Connections button. The bar shows only when both FB510 and FB301 are present, so a bad column name does not grow a Connections button. |
| 61-outline-rename-refusal | The sentence was not on the tour. | The toast shows the real sentence: a widget used by behavior from a newer version cannot be renamed here. |
| Preview, the manual, and UX-KEY-005 | Ctrl+Shift+R was called Try in the spec and Run behavior in the toolbar. | UI, `docs/form_builder/UX_SPEC.md`, `docs/manual/form_builder/preview.md`, `docs/manual/form_builder/keyboard.md`, and `docs/form_builder/manual/try.md` use the sentence above. |
| Keys page, DESIGNER_MOVES | The F4 row still said the connections overlay was not ready. | The row says F4 opens the Connections overlay. |
| Add lines | A second lines grid could be inserted. The FB320 sentence appeared only later, as a report. | `add_lines` refuses with that same sentence. Editing the one grid still works. |
| Record show | A failed line load painted the new header and left the previous lines on screen. | Lines are collected in the same transaction as the header fetch, and the header is written only after that succeeds. |
| F1 Read more | The button is never created. `manual_page()` returns None. | Left. In-app help can show markdown, but no `docs/manual/form_builder` page matches a widget class. Pointing every widget at one task page would open the wrong page. |
| `#D97706` and `#c62828` | M9.3 named a hard-coded amber. | Left. `#D97706` is the shell's pre-theme warning color, replaced when the theme applies. It is not in the form builder. `#c62828` is the invalid-check border, already allowlisted. |

## Helper lines

Removed:

- New form, "Every starting point is already laid out, so it resizes with the window." The cards show that.
- Empty canvas, "/ insert · Ctrl+Shift+G wrap · F2 rename". The keys page owns those shortcuts.

Kept:

- New form caption that names the three generated files. The name field does not say that.
- Template card subtitles. They are how the cards differ.
- From-table note about main.py. A shop owner cannot tell why the start checkbox is off.
- "Choose a connection", now on its own line. It is the next action.
- Logic empty, "This form has no rules, checks, or events yet. Select a widget and open Behavior to add one."
- Data empty, "This form isn't connected to a database." plus Connect to a table and Add a connection. Those are two different next steps.
- Run behavior tooltip. A checked box does not say that it runs checks and undoes database changes.
- Inspector property hints (tab order, layout, pictures). The property name does not say what the control does.
- FB510 sentence, the generated-file banner, and the damaged-file sentence.

## States

Shot 42 and shot 57 are unused numbers. The state builder is inside 28-inspector-behavior. An events list with no events is 35-logic-empty. Hover, pressed, and disabled frames are not separate shots. Offscreen does not hold a hover across the theme pass. Focus rings and the high-contrast dark shots are in the contact sheet. High-contrast light was not part of this tour.

## Follow-up 1

Opus reviewed every light 100% shot. Each row is one of those findings. Dark and high-contrast dark were checked again for the black surfaces, the connection row, the left column, alignment, logic rows, the insert list, and the Behavior headers.

| Shot | What was wrong | Result |
| --- | --- | --- |
| 04-start-from-table-empty | With no table the button read "Create form form with 0 fields" and looked enabled. | The label is "Create form with 0 fields". The button stays disabled until a table has one included field, and the disabled style is grey. |
| 06, 39, 59 | Light theme showed solid black. The lines preview, the Uses popup, and Go to widget. | The lines preview was a real empty viewport. The dialog stylesheet rebuilds that viewport, so the fill is applied again after the sheet. Light and dark measure under 0.1% black, and the form fields are readable. High-contrast dark is black because that theme's background is black. The two popups are an offscreen grab. `grab()` on the native window is an opaque black store, and this Mac run has no live X11 to compare. Their children still paint, so the tour draws those children on the theme background. Light and dark of both popups measure 0% black. |
| 44, 46, 47 | The selected connection row painted its title twice. | The list item text is empty. The row widget paints the title once and the engine line once. Checked in dark as well. |
| 54-files-generated-banner | Two buttons had no text, and the banner sentence was missing. | The Open buttons stay hidden until the banner is shown. The shot has the generated-file sentence, "Open gone.ui", "Open gone_window.py", and "Edit anyway". |
| 41 | "Key" appeared twice. The first Order combo was blank while the others said "(none)". | One Key label, an empty key field, and all three Order combos say "(none)". |
| 33, 34 | The Column combo showed "Bind" instead of the bound column. A lines grid with a lines binding said "Not bound". | The bound name is added when the schema list does not already contain it. Column shows notes. A lines grid does not say "Not bound". |
| 09, 56, and new 62 | Logic chips overlapped the empty-rules sentence, Saved pieces overlapped the widget list, and the Data sentence was clipped. | Each left section has a minimum height, and the column scrolls instead of stacking those sections on top of each other. The scroller's minimum height is what the shell splitter honors, so a 1366×768 window stays in that column instead of dropping into tabs. The scrollbar's width is added to the pane, so outline names keep their room. Shot 62 is the full window at 1366×768. Dark shows the same stacked sections, with the rules sentence complete and a scrollbar rather than an overlap. |
| 60-inspector-narrow | Text alignment buttons were middle-elided ("Ce...er", "Ju...fy"). | The choices are one column of words. The tooltip is the word. High-contrast dark shows Left, Center, Right, and Justify in full. |
| 36-logic-filled | "Enabled when · Di" was clipped with no ellipsis. `save_invoice` used a serif fallback. "Save  · clicked" had a stray space. | The aside elides with an ellipsis and keeps the full text in the tooltip. The shot shows "Enabled …" and "Save · clicked". The code line uses the editor font family. |
| 56 | "Saved gone.ui · ui_g..." was red and clipped. | A saved form is not an error, including when the generated file was withheld. The label uses the muted gutter color, elides with an ellipsis, and the tooltip has the full sentence. That sentence says the file was not written. |
| 20, 22 | Category headers truncated, and each row carried a second line that also truncated. | Headers wrap onto two lines. The row description stays in the tooltip. High-contrast dark shows "LAYOUTS AND SPACERS" in full and rows with no second line. |
| 28, 29 | The Required message looked like an empty placeholder. STATE, CHECKS, and EVENTS did not match the Properties headers. | The message uses the normal text color. Those three headers are the same disclosure buttons as the Properties groups. High-contrast dark shows "Enter an email address" as body text and EVENTS with a disclosure arrow. |
| 30-inspector-events | "not checked" after "Call save_invoice()" did not say what failed. | It meant the window file could not be read. The button now says "Couldn't read the file". When the file is readable, the shot shows the file and line. |
| 48-preview-run-behavior | The form area was empty, and the bottom line repeated the rollback banner. | Preview shows the form. The strip is "Data: Shop database." The banner still says the changes are rolled back. |
| 47 | A failed test said only "Could not open that database." | The sentence includes the missing path. The shot reads "Could not open that database. data/missing.db is missing." |
| 18-canvas-zoom-75 | The selection chip sat outside the form frame at 75%. | The chip stays on the selected widget. At 75% it sits on the field's right edge. A layout chip stays in the gutter, so the margin numbers stay outside the page. |
| 13-canvas-layout-popover | A blurry upscaled crop. | The menu is grabbed at its own size and drawn beside the widget. The shot is 551×562. |
| 52, 53, 37 | The Problems panel was too small to read, and the logic Problems chip showed no problem. | The panel is 1396×320 and the FB207 sentence is readable. The logic shot lists "PROBLEMS · 1" and the discountEdit rule fight. |
| 58-pictures-none | The PNG was transparent. | Shots that still have a clear pixel are composited onto the theme background. This one measures 0% clear in light, dark, and high-contrast dark. |
