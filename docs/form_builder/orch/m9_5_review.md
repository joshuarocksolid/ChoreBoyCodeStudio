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

## Follow-up 2

One row per item in `followup2_M9.5_polish.md`. Shots are the tour names.

| Item | Shots | Result |
| --- | --- | --- |
| 1 Spacing scale | every chrome shot | Margins, gaps, and control heights in the builder chrome read `qtside/theme/metrics.py`. |
| 2 Section headers | 20, 23, 27, 28, 02 | One 28 px header. Title is the host outline title style. |
| 3 Inspector rows | 27, 60 | Label beside the editor. Behavior values are 24 px buttons. |
| 4 Builder tabs | 23, 27 | Outline, Insert, Logic and Properties, Behavior, Data share one tab bar. Design and XML stay two tool buttons. |
| 5 List selection | 23, 36 | Tree and list views share one hover and selected style. |
| 6 Popovers | 13, 22, 31, 39, 59 | Layout, event picker, Go to widget, quick insert, and row popovers share width, padding, and shadow. They rise 4 px and fade in over 120 ms. An offscreen grab sees the settled frame. |
| 7 Mode banner and info bar | 14, 15, 16, 54, 66 | The mode pill floats. The generated-file bar is one line. |
| 8 Host controls | 27, 41 | Builder chrome no longer paints its own combo and line-edit rules. The canvas form keeps the runtime palette. |
| 9 Outline rows | 23, 65 | Class glyphs, 24 px rows, name and object name on one line. |
| 10 Left pane header | 23, 20 | One header per pane. In the short window the tab is the header and the actions sit in the tab corner. |
| 11 Host outline | full window | An active form tab collapses the host outline to its header and does not save that collapse. |
| 12 Inspector header | 27 | Search, the selected widget, and the class sit in one header. |
| 13 Translation | 27 | The translation control sits inside the field. |
| 14 Search field | 27 | One search field. Placeholder only. |
| 15 Segmented choices | 27, 63 | Alignment and size choices are one segmented control. |
| 16 Tab toolbar | 08, 51 | Groups are Design/XML, overlays, undo, zoom, menus, Preview and Run behavior. Preview reads Preview. Aa and Widths paint an 8 px chevron with a 4 px gap. The style menu arrow stays hidden. |
| 17 Chips | 18 | Page and selection chips use the overlay ink. |
| 18 Margin and gap | 18 | Numbers sit in the gutter. |
| 19 Logic badges | 15 | Badges use the logic ink. |
| 20 Empty form | 07 | Two lines. Amended UX-EMPTY-001. |
| 21 Insert tiles | 20 | Tiles use the spacing scale. |
| 22 Logic segments | 35, 36 | All, Rules, Checks, and Events. Problem counts stay on the section that has the problem rows. |
| 23 Behavior and Data rows | 28, 32 | Same row grammar as Properties. |
| 24 Start | 02, 64 | Cards and the recent rail use the spacing scale. Amended UX-START-003. UX-START-005 already matched the 200 by 156 card. |
| 25 From table | 04 | Host dialog chrome and a row grid. |
| 26 Connections | 44 | The page uses the same row grid. |
| 27 Try chrome | 48, 51 | The preview bar matches the form toolbar. |
| 28 Dark and high contrast | dark and high_contrast_dark shots | Backdrop dots blend the border token. High contrast keeps its own ink. |
| 29 Status | 08 | Form sentence and selection sentence. The label keeps the whole sentence, because screen readers read it. |
| 30 Tour | 12, 15, 08, 09, 56, 62, 62-window-short-console, 63, 64, 65, 66, 67 | The tour collapses the Python Console for the full-window shots and opens it for `62-window-short-console`. Shot 15 is tab-order mode. Shot 12 holds the insertion line and chip for a Push button drop. Shots 63 through 67 are in the set. |

## Follow-up 3

One row per item in `followup3_M9.5.md`. Shots are the tour names.

| Item | Shots | What was wrong | What changed | Spec |
| --- | --- | --- | --- | --- |
| 1 Behavior headers | 28, 29, 30 | STATE, CHECKS and EVENTS were small raised buttons. STATE had no rows. A sentence and a link sat under Checks. | The three headers are the shared section header, flush left. STATE lists Enabled when, Visible when, Read-only when, Value and Default. The sentence is the FB038 info row in Problems, and its fix adds the outline style once. | |
| 2 Section headers | 27, 60, 63, 08, 07 | The title sat in the middle and the chevron sat at the far left. Window, Layout, Tab order, Problems and Files were small labels. Three helper sentences were on the form. | The shared header puts the chevron at the pane pad and the title 4 px after it. Those five labels are section headers. The size sentence is the size readout's tooltip. The reading-order sentence and the empty-pictures sentence are gone. | |
| 3 Left pane | 08, 07, 15, 62 | Outline, Insert, Saved pieces, Logic and Data were stacked. Insert was a clipped strip. | The left pane is always Outline, Insert and Logic, each full height. Actions sit in the tab corner. Insert is a list below 232 px and a 72 by 56 tile grid at or above it. Saved pieces shows only when a piece exists. Logic ends with Connect to a table, and a connected form keeps its column list on that tab. Add a connection is the last entry in the Connect dialog. | UX-WB-002 and UX-RESP-005 now say the pane is always those three tabs. |
| 4 Contrast | 08-dark, 62-high_contrast_dark, 07-dark | Titles and unselected segments were a disabled grey. The tab-order list was white in dark. Connect buttons were light native buttons. | Titles and unselected segment text use text_muted. Lists use the editor or panel background with primary text. Chrome buttons use the host button rule. | |
| 5 Canvas chips | 10, 12, 13, 15, 07, 08 | The page chip was pale cyan. The selection chip used the high-contrast blue in light. | The page chip is the layout purple with white text and the layout glyph. The selection chip is the normal blue, and the high-contrast blue with a white outline only in high contrast. It sits 2 px above the widget when that seat is clear. | |
| 6 Inspector labels | 27, 15, 60 | Labels elided at 80 px. Value buttons did not share a column. Tooltip was a lone chevron. Alignment clipped. | The label column is 38% of the inspector, clamped to 88–120 px. A label elides only when that column is at the 88 px floor. Value buttons fill the editor column. Tooltip is an empty line edit. Alignment is two stacked rows. | |
| 7 Toolbar | 62, 62-window-short-console | Design and Connections elided. Undo, redo and zoom were 4 px dots. | Design and XML keep the width of their words. Tab order, Buddies and Connections become 24 px glyphs when the words do not fit. Undo, redo and zoom are 16 px glyphs. | |
| 8 Margin overlay | 07, 08, 18 | Selecting the root tinted the whole form pink. | The faint gap colour fills only the margin bands. Gap bars are 2 px. The content area stays clear. | |
| 9 Outline names | 08, 23, 15, 65 | Object names elided to a few letters. The tree had an accent frame. | An object name that cannot show 8 characters is hidden. The tooltip keeps it. The display name elides on the right. Focus is a 2 px accent bar on the selected row. | |
| 10 Popovers | 31, 13, 59 | The step picker was native. The layout popover was a blank rectangle. Go to widget showed an empty list. | All three use the shared popover. The layout tiles sit beside the widget. An empty Go to widget hides the list. | |
| 11 Mode banner | 66, 14, 16 | The pill elided the sentence to nothing. | The pill sizes to the sentence, up to 560 px or the viewport minus 32, and elides only past that. | |
| 12 Build from a table | 04, 05, 06 | Include was clipped. The preview was tiny. The footer had helper lines. Create had no shape. There was no title. | Include is 64 px with the host checkbox. The preview stays at least 75% and scrolls. The helper lines are tooltips. The disabled Create button keeps its shape. The title is Build a form from a table. | |
| 13 Search field | 08, 20, 22, 27, 36 | Each surface painted its own field. | One 24 px search field, with the search glyph and a placeholder, is used by Find a property, Insert, Logic, Outline, quick insert, Go to widget and the step picker. | |
| 14 Tour fidelity | 15, 63, 64, 37, 65, 67 | Shot 15 was not in Tab order mode. Shot 63 matched shot 27. Shot 64 showed no hover or focus. Shots 37, 65 and 67 matched their neighbours. | Shot 15 opens tab order. Shot 63 scrolls to Size so Hug, Fill and Fixed are visible. Shot 64 hovers one card and focuses another. Shot 37 filters to the fighting row. Shot 65 hovers a row. Shot 67 shows the generated banner on the editor. The tour fails when two shot names share pixels. | |
| 15 Try, Logic, Connections | 48, 36, 30, 44, 47 | The try strip named the database. Clear used a refresh glyph. The logic note was clipped. A step wrapped. A one-row list scrolled sideways. | The data line is gone. Clear is an X. The logic note is inset and elides on the right, and the count uses the diagnostic colour. A step stays on one line. Those lists do not scroll sideways. | |

## Follow-up 4

One row per blocking item. Shots are the tour names.

| Item | Shots | What was wrong | What changed | Spec |
| --- | --- | --- | --- | --- |
| 1 Dialogs and inputs | 41-high_contrast_dark, 05-high_contrast_dark, 44, 04, 02-dark, 08-dark, 62-high_contrast_dark | Labels were black on black. Lists and fields stayed white. Shot 44 matched its light twin because the connections page kept the light colours it painted at show time. Shot 04 matched its light twin because the tour built the empty dialog with light chrome and never reapplied the theme. The product opens that dialog with the theme that is current. Shots 05 and 06 already reapplied chrome, and they were not identical. | Dialog chrome paints labels, checkboxes, and fields from the host tokens. Fields use input_bg and text_primary. The connections page re-reads the host theme on show and on a style change. The Start name field and the inspector Title field use that same chrome input colour. The empty from-table grab reapplies the current theme before the shot. The tour fails when a dark or high-contrast shot matches its light twin. | |
| 2 Insert tiles | 20 | Glyphs and labels split across rows. Labels wrapped to three lines and clipped. | Each tile is a 72 by 56 face in a 76 by 60 cell. The 16 px glyph is centred 8 px from the top. The 11 px label stays under it, two lines at most, and the second line elides. A 232 px pane has two columns. A 260 px pane has three. Category headers still span the pane. List mode is unchanged. | |
| 3 From-table preview | 05, 06, 05-high_contrast_dark | The preview was a scaled picture with a clipped record bar, empty grey lines, and a horizontal scrollbar. Two checkbox labels disappeared in high contrast dark. | The form is laid out at the page card's inner width and shown at scale 1, with the 16 px inset and the page shadow. Only a vertical scrollbar can appear. The record bar wraps inside the page. Those checkbox labels take text_primary from the dialog chrome. Toggling a column rebuilds the preview. | |
| 4 Inspector labels | 27, 27-dark, 15 | "Maximum length" was cut to "Maximum leng" with no ellipsis. | The label column stays 38% of the inspector, clamped to 88–120 px. Any label wider than that box elides on the right, and the tooltip keeps the full text. | |
| 5 SIZE | 63 | Hug, Fill, and Fixed were loose text buttons. Each axis showed a "Default for a line edit" line. | Width and Height use the shared segmented control. Those default sentences are the control's tooltip. | |
| 6 Tab-order badges | 15 | Badges sat on the left edge and covered the field text. | Each badge sits inside the right edge, vertically centred, 4 px in. A widget under 48 px wide carries the badge just outside that edge. The flow line joins the badge centres. | |
| 7 Behavior | 28, 30 | The EVENTS title looked disabled. Kind and Format were native combos, and Format was empty. | The EVENTS title uses the same section-header colour as STATE and CHECKS. Kind and Format are value buttons. Format is hidden when its only choice is the default. | |

## Follow-up 5

One row per blocking item. Shots are the tour names.

| Item | Shots | What was wrong | What changed | Spec |
| --- | --- | --- | --- | --- |
| 1 SIZE state | 63, 63-dark, 63-high_contrast_dark | Width and Height read as plain Hug Fill Fixed. Nothing showed that one segment was the current choice. The class default is not a checked button. It is the outline flag, and the track stylesheet ignored that flag. | The shared segmented control paints that flag the same way it paints a checked segment. The track is tree_hover_bg, 24 px, with 2 px of inner padding. The chosen segment is panel_bg, a 1 px border, and text_primary at weight 600. The others are text_muted. High contrast uses a 2 px accent border on the chosen segment. | |
| 2 Alignment glyphs and Edit | 63-dark, 15-dark | The alignment marks were painted from the widget palette, which stayed dark grey on the dark track. Edit… on Style sheet was a native light button. | Idle marks use icon_primary. The chosen mark uses text_primary, because the chip is a panel fill and white-on-accent would disappear on the light blue chip. A theme change repaints the marks. Edit… uses the host secondary button. | |
| 3 Preview chrome | 48, 49, 50, 51, and the dark and high_contrast_dark copies | The live Preview child painted the Run behavior bar, the info bar, and What ran with the light fallback. The tour hid that by painting those widgets itself. | Appearance now carries the shell colour pairs the Preview chrome reads. The child applies them after the Qt style is set and before the window is shown. The form keeps the runtime palette. Shots 48–50 are grabbed from that child path. The tour no longer paints its own colours on those shots. | |

## Follow-up 6

One row per blocking item. Shots are the tour names.

| Item | Shots | What was wrong | What changed | Spec |
| --- | --- | --- | --- | --- |
| 1 Logic segments | 35-high_contrast_dark, 36-high_contrast_dark | Rules, Checks and Events were black on the black panel. The track stylesheet only matched a control still named formBuilder.segmented, and Logic renames that control. | The sheet matches the fbSegmented property, which the rename leaves in place. Unselected text is text_muted. The chosen segment stays the panel chip, with a 2 px accent edge in high contrast. Size and alignment use the same control. | |
| 2 Preview form size | 48, 49, 50 | The form was in a stretching layout, so it filled the pane. Customer sat mid-pane and the field sat on the bottom edge. | The form is hosted at the size setupUi set, or at its size hint when setupUi did not resize it. It sits at the top-left with a 16 px inset in a scroll area. Resizing the Preview window scrolls. It does not stretch the form. The form keeps the runtime palette. | |
