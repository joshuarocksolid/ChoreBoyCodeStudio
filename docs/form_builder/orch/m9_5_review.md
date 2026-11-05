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
