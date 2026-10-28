# Form builder: UX specification

Version 1 (work package M0.9). Author: Opus, lead UX designer. Date: 2026-10-21.
Status: draft for approval. Binding for M2 (shell integration) and M3 (canvas and layout editing). Section 13.2 (M5) gives the structure and the key decisions only, and will be deepened before that milestone starts.

Version 2 (work package M4.0, 2026-10-28, Opus). Section 13.1 is now the full M4 specification (areas CAT, CONT, PED, ITEM, plus UX-TOK-005 and UX-ICON-005), binding for M4. Section 12 gains the M4 screenshot states, keyboard scripts K9–K15, checks and the M4 persona walkthrough.

Inputs: `PLAN.md` (§1 fixed decisions, §2a O-UX gate, M2–M5), `SPIKE_DESIGN.md`, `research/P_user_pain_points.md`, `research/R3_designer_parity_checklist.md` ("Where Designer's UX is weak"), `research/A_market_survey.md` ("Patterns the best builders share"), `LOGIC_DESIGN.md` §2, the spike on `feat/form-builder-spike` (README, DESIGN, decisions.tsv, the 22 screenshots, plus five extra offscreen captures of the spike at 1100×640 and 1366×768), and the CBCS shell on `feat/form-builder` (`app/shell/theme_tokens.py`, `theme_dark_chrome_presets.py`, `style_sheet_sections_*.py`, `shortcut_preferences.py`, the menu builders, `status_bar.py`, `features/markdown/markdown_editor_pane.py`).

---

## 0. How to use this document

### 0.1 Clause ids

Every binding rule is a clause with a stable id: `UX-<AREA>-<NNN>`. Ids are never renumbered or reused. A removed clause keeps its id with the text "Withdrawn in vN". New clauses take the next free number in their area.

Each clause line carries three things after the id:

- the work package that implements it (for example `M3.1`), and
- the evidence codes a gate uses to verify it (section 12.1), and
- the rule itself, in the imperative ("must" is implied; "should" marks a strong default that a PR may deviate from with a written reason).

Example (see section 5.1 for the real clause): `UX-SEL-004` `M3.1` `[K]` Esc … selects the parent.

PRs list the clause ids they implement. The O-UX gate checks those clauses one by one and cites ids in a CHANGES list. A finding that cannot cite a clause or a failing test is not a blocking finding (PLAN §2 bounded fix loop).

### 0.2 Areas

| Prefix | Area | Section |
| --- | --- | --- |
| PRIN | Design principles | 1 |
| TOK, TYPE, GRID, ELEV, ICON, MOTION, ISO | Visual language | 2 |
| SHELL, XML, GEN, PROB, RUN, KEY, PS2 | CBCS integration | 3 |
| START, TABLE, WB, EMPTY, RESP | Screens and regions | 4 |
| SEL, HOV, FRAME, CHIP, DND, BOX, GRIDL, FORML, SPLIT, PAGES, BARE, AUTO, MOVE, GAP, RESIZE, TEXT, WRAP, CLIP, NUDGE, ZOOM, WIDTHS, SCALE | Canvas | 5 |
| OUT | Outline | 6 |
| INSP, SIZE | Inspector | 7 |
| OVL | Overlays (tab order, buddies, connections) | 8 |
| FEED, COPY | Feedback, errors, copy | 9 |
| A11Y | Accessibility | 10 |
| CAT | Insert catalog and search | 13.1.2 |
| CONT | Containers and pages | 13.1.3 |
| PED | Property editors | 13.1.4 |
| ITEM | Item editors | 13.1.5 |
| M4 | M4 shared rules (M4-005 … 007; M4-001 … 004 withdrawn in v2) | 13.1.1 |
| M5 | Later milestones (structure) | 13.2 |

### 0.3 Words used in this spec

These are also the words the product uses on screen, unless a clause says otherwise.

| Word | Meaning |
| --- | --- |
| Form | The `.ui` document and its top-level widget |
| Page | The drawn card on the canvas that shows the form at its design size |
| Backdrop | The canvas area around the page (dot grid). It follows the shell theme |
| Gutter | The backdrop band that is always kept free around the page (UX-ZOOM-004). Labels that would cover content go here |
| Layout | A `QVBoxLayout`, `QHBoxLayout`, `QGridLayout` or `QFormLayout`. On screen: "Vertical", "Horizontal", "Grid", "Form" (layout kinds); "vertical layout" in sentences |
| Slot (layout) | A place in a layout: an index in a box, a cell in a grid, a label or field cell in a form row. Never shown as the word "slot" to the user (Qt uses "slot" for methods) |
| Gap | Layout spacing between neighbours |
| Margin | Layout contents margins |
| Hug, Fill, Fixed | Sizing words (section 7.3) |
| Share | Stretch factor (box stretch, grid row/column stretch, splitter stretch) |
| Chip | A small filled label painted by the overlay (name, layout kind, drop target, number) |
| Overlay | A temporary canvas layer with its own clicks: Tab order, Buddies, and (M6) Connections |
| Content | Any non-ancestor widget's rectangle, and the selected widget's own rectangle. Ancestors' backgrounds and frames are not content |

---

## 1. Design principles

Each principle names the evidence it rests on. When two clauses conflict, the lower-numbered principle wins.

**UX-PRIN-001 · Truth first: the canvas is the app.** What the canvas shows is what `setupUi` builds at run time on ChoreBoy: same style, same palette, same font, same layout math, real widgets. The builder's own theme never leaks onto the form, and no overlay ever hides a pixel of the form that the user needs to read. *Evidence:* market survey failure mode "a preview that lies or dies"; pain 8 (style sheet differs), pain 12; the spike's `workbench-dark.png` proves the isolation works and its chips prove the overlay half does not yet (they cover fields).

**UX-PRIN-002 · Every drop is already laid out.** Nothing is placed at a pixel in normal work. A drop lands in a layout slot that is drawn before release. Layout commands become optional refinements, never a precondition. *Evidence:* pains 1, 4, 5, 21; delighters 1, 11, 15; survey pattern 4 and 5.

**UX-PRIN-003 · Plain words, Qt underneath.** On-screen vocabulary is Hug, Fill, Fixed, Gap, Margin, Share, "Vertical layout", "Line edit". Every friendly name has its Qt name one hover or one toggle away, and the file stays standard Qt. Veterans are never blocked by the friendly layer: the full Qt property list, Qt class names and Designer shortcuts are always reachable. *Evidence:* pain 2 (three mysteries), survey pattern 7 (names in the inspector are names in Python), owner goal "a Qt Designer veteran never goes back".

**UX-PRIN-004 · Structure appears where you look.** Layout frames, gaps, margins, numbers and badges are faint or hidden everywhere except the hovered or selected container. A calm canvas with one focus beats a dense diagram. *Evidence:* LOGIC_DESIGN §2.7 ("showing every relationship by default is what makes graphs unreadable"), spike `layout-selected.png` (works) vs `drag-box.png` (whole-form tint washes out every field).

**UX-PRIN-005 · No sticky modes; Esc always gets you out.** Tab order, Buddies and Connections are overlays with a visible exit. One Esc closes the innermost transient thing (inline editor, popover, drag, overlay), then walks selection up. Nothing changes the meaning of a click without a banner that says so. *Evidence:* pain 13, pain 20 ("unchecking does not work"), R3 items 1, 8, 10.

**UX-PRIN-006 · Keyboard and mouse are equal citizens; focus is never stolen.** Every canvas gesture has a keyboard path, every keyboard path has a visible focus, and no status message, toast, save or regeneration moves the keyboard. *Evidence:* pain 25, R3 weakness "Renaming steals focus", PLAN §2 quality gate 11.

**UX-PRIN-007 · Fast enough to feel like paper.** Feedback for a pointer move appears in the same frame (≤ 16 ms per edit, PLAN §1). Structure never animates. Expensive work (XML, generation, preview) is deferred and never blocks a gesture. *Evidence:* PLAN speed budgets; pain 23; VB6 and Glade complaints in the pains report ("hitches and lags", "freezes for a minute").

**UX-PRIN-008 · Native to Code Studio.** The builder is a CBCS editor tab, not a second application: same theme tokens, same density, same menus, same status bar, same Problems panel, same shortcuts with the same meanings. A builder-only concept earns its own chrome only when CBCS has no equivalent. *Evidence:* spike screenshots show a standalone window with its own menu bar, Start/back navigation, Save button and status bar (all `*.png`); CBCS controls are 12 px text, 4 px radius, 20–24 px tall (`style_sheet_sections_*.py`), while the spike uses 13 px, 6 px and 28 px.

---

## 2. Visual language

### 2.1 Colour tokens

The builder defines no free-floating colours. Its chrome tokens are aliases of `ShellThemeTokens` so a CBCS theme change (light, dark standard, dark neutral-gray, high contrast light, high contrast dark) restyles the builder with no builder code. Builder-only roles (backdrop, overlays) are new tokens defined in `qtside/theme/` and chosen to harmonize with the shell's values.

**UX-TOK-001** `M2.3` `[S A]` Chrome tokens alias shell tokens exactly as in this table. A builder file that writes a hex colour outside `qtside/theme/` fails review.

| Builder token | Shell source | Light | Dark (standard) | HC light | HC dark |
| --- | --- | --- | --- | --- | --- |
| `fb.window` | `window_bg` | `#F8F9FA` | `#1F2428` | `#FFFFFF` | `#000000` |
| `fb.panel` | `panel_bg` | `#FFFFFF` | `#262C33` | `#FFFFFF` | `#000000` |
| `fb.row_hover` | `tree_hover_bg` | `#E9ECEF` | `#2A3038` | `#E6E6E6` | `#1F1F1F` |
| `fb.row_selected` | `tree_selected_bg` | `#D0E2FF` | `#2D3A4A` | `#B8D7FF` | `#0A4D8C` |
| `fb.border` | `border` | `#DEE2E6` | `#3C434A` | `#000000` | `#FFFFFF` |
| `fb.text` | `text_primary` | `#212529` | `#E9ECEF` | `#000000` | `#FFFFFF` |
| `fb.muted` | `text_muted` | `#5A6168` | `#C2C9D1` | `#1F1F1F` | `#E0E0E0` |
| `fb.faint` | `gutter_text` | `#666F76` | `#8B949E` | `#2A2A2A` | `#D0D0D0` |
| `fb.accent` | `accent` | `#3366FF` | `#5B8CFF` | `#0000C0` | `#7CB7FF` |
| `fb.on_accent` | new | `#FFFFFF` | `#0B1020` | `#FFFFFF` | `#000000` |
| `fb.input` | `input_bg` | `#FFFFFF` | `#1B1F23` | `#FFFFFF` | `#000000` |
| `fb.popup` / `fb.popup_border` | `popup_bg` / `popup_border` | `#FFFFFF` / `#DEE2E6` | `#262C33` / `#3C434A` | `#FFFFFF` / `#000000` | `#000000` / `#FFFFFF` |
| `fb.error` / `fb.warning` / `fb.ok` | `diag_error_color` / `diag_warning_color` / `test_passed_color` | `#E03131` / `#D97706` / `#1A7F37` | `#FF6B6B` / `#E5A100` / `#3FB950` | `#9C0000` / `#7A4500` / `#005000` | `#FF8080` / `#FFD700` / `#7FCB66` |

The neutral-gray dark chrome palette substitutes its own surfaces through the same aliases.

**UX-TOK-002** `M2.3` `[S]` Backdrop tokens follow the shell theme (the backdrop is chrome):

| Token | Light | Dark | HC light | HC dark |
| --- | --- | --- | --- | --- |
| `fb.backdrop` | `#E9EBEF` | `#16191D` | `#FFFFFF` | `#000000` |
| `fb.dots` (16 px dot grid, 1 px dots) | `#D3D8DF` | `#262B31` | none | none |
| `fb.page_shadow` | `rgba(16,24,40,0.10)` | `rgba(0,0,0,0.45)` | none, 1 px `fb.text` border | none, 1 px `fb.text` border |

**UX-TOK-003** `M3.1` `[S A]` Form-surface tokens are the colours drawn *on top of the form* (selection, layout frames, gaps, drop targets, overlay badges). Because the form always renders in the runtime palette (light Fusion, window `#EFEFEF`, base `#FFFFFF`; UX-ISO-001), these tokens do **not** change between light and dark chrome. They change only for high contrast. The spike's practice of brightening the accent in dark mode lowered contrast on the light form (`#5B8CFF` on `#EFEFEF` is 2.6:1) and is withdrawn.

| Token | Normal | High contrast (both) | Contrast on `#EFEFEF` (normal / HC) | Use |
| --- | --- | --- | --- | --- |
| `ov.select` | `#2F5BEA` | `#0000C0` | 4.8:1 / 10.9:1 | selection outline, handles, drop line, drop cell |
| `ov.hover` | `#2F5BEA` at 55% alpha | `#0000C0` | n/a (transient) | hover outline |
| `ov.layout` | `#7C3AED` | `#5B21B6` | 5.0:1 / 7.8:1 | layout frames, layout chips |
| `ov.layout_faint` | `#7C3AED` at 28% alpha | `#5B21B6` at 60% | decorative | unselected layout frames |
| `ov.gap` | `#DB2777` | `#831843` | 4.0:1 / ≥ 7:1 | gap bars, margin bands, share numbers |
| `ov.gap_fill` | `#DB2777` at 12% alpha | `#831843` at 20% | decorative | margin bands |
| `ov.drop_fill` | `#2F5BEA` at 10% alpha | `#0000C0` at 15% | decorative | drop cell fill |
| `ov.tab` | `#B45309` | `#7A3E00` | 4.4:1 / 7.3:1 | tab-order badges and flow line |
| `ov.buddy` | `#047857` | `#00553A` | 4.8:1 / 7.7:1 | buddy links |
| `ov.problem` | `#C81E1E` | `#9C0000` | 5.0:1 / ≥ 7:1 | invalid drop, problem badge |
| `ov.chip_text` | `#FFFFFF` | `#FFFFFF` | ≥ 4.6:1 on every chip fill above | chip labels |

**UX-TOK-004** `M3.1` `[S]` Overlay strokes are drawn *outside* the widget rectangle they describe (a 2 px selection stroke sits 1 px outside the widget's edge), so the widget's own border and text stay visible. HC raises every overlay stroke to 2 px minimum.

### 2.2 Type scale

**UX-TYPE-001** `M2.3` `[S]` The builder uses the shell UI font family and weight setting (`ui_font_weight_css`). Sizes are defined relative to the shell base size B (12 px today); when the user changes the shell font size every builder size scales by B/12.

| Role | Size | Weight | Use |
| --- | --- | --- | --- |
| Overline | B − 2 (10 px), uppercase, +0.5 px letter spacing | 600 | section headers in panes ("OUTLINE", "SIZE") |
| Caption | B − 1 (11 px) | 400 | helper sentences, chips (chips use 600) |
| Body | B (12 px) | 400 | rows, fields, menus |
| Strong | B (12 px) | 600 | changed property labels, inspector name |
| Title | B + 1 (13 px) | 600 | inspector header name, dialog section titles |
| Screen | B + 6 (18 px) | 600 | Start and dialog headings |
| Hero | B + 10 (22 px) | 600 | Start "New form" only |

**UX-TYPE-002** `M3.1b` `[S]` Numbers in the inspector, chips and readouts use tabular figures when the font provides them, and always carry a unit when the unit is not obvious ("240 px", "2 columns").

**UX-TYPE-003** `M3.1` `[S]` Nothing in builder chrome is set smaller than 10 px at 100% DPI. Chips are 11 px semibold.

### 2.3 Spacing grid and sizes

**UX-GRID-001** `M2.3` `[S]` A 4 px grid. Allowed spacings: 4, 8, 12, 16, 24, 32. Pane padding is 12 (8 at the compact breakpoint, UX-RESP-002).

**UX-GRID-002** `M2.3` `[S]` Control heights match the shell: inputs, combos and segmented controls 24 px; buttons 24 px (primary 28 px only in dialogs and Start); outline rows 24 px; inspector rows 28 px (24 control + 4); pane section headers 28 px; tab toolbar 36 px.

**UX-GRID-003** `M2.3` `[S]` Radii: 4 px controls and chips (the shell's dominant radius), 6 px popovers, menus and the page card, 8 px Start cards. Nothing else is rounded.

**UX-GRID-004** `M3.1` `[A]` Hit targets: every canvas handle and every gap bar has a hit area of at least 12 × 12 screen px regardless of zoom; outline rows are 24 px tall; insertion targets in lists are at least 8 px tall (pain 20: "a drop marker wider than a few pixels").

### 2.4 Elevation

**UX-ELEV-001** `M2.3` `[S]` Three levels only. Level 0: panes, flat, separated by 1 px `fb.border`. Level 1: the page card (shadow `0 1 3` + `0 4 12` at `fb.page_shadow`). Level 2: popovers, menus, toasts, drawers (1 px `fb.popup_border` + shadow `0 8 24` at 16% black). High contrast: no shadows; level 1 and 2 use a 1 px (page) or 2 px (popover) `fb.text` border.

### 2.5 Iconography

**UX-ICON-001** `M3.1` `[S]` No icon files. All builder glyphs are painted by `qtside/icons/` with `QPainter`: 16 px design grid, 1.5 px stroke at 1× (scaled with device pixel ratio, never resampled bitmaps), round caps and joins, 2 px safe padding, single colour (`icon_primary`, or `fb.on_accent` on accent fills). Stroke weight and corner radius match `app/shell/toolbar_icons.py` so builder icons sit beside shell icons without looking foreign.

**UX-ICON-002** `M3.1` `[S]` Glyphs are drawn natively at 12 (chips), 16 (rows, toolbar) and 20 px (Insert tiles), not scaled from one size. Each is cached per (name, colour, size, device pixel ratio). A theme switch invalidates the cache.

**UX-ICON-003** `M4.1` `[S]` One glyph per widget class in the catalog, shaped like the widget (a push button is a pill, a line edit a box with a caret, a combo a box with a chevron, a grid layout four squares, a spacer a spring). Layout glyphs use `ov.layout`, spacer glyphs use `ov.gap`; every other glyph uses the text colour. Colour never carries meaning alone: the shape and the label do.

**UX-ICON-004** `M3.1` `[S]` The UI set covers at least: chevron (4 directions), plus, minus, close, reset (↺), undo, redo, play (preview), zoom, fit, two-widths, text-size ("Aa"), XML (`</>`), tab-order (1→2), buddy (link), connection (M6), warning, error, info, check, lock (generated file), database, search, drag grip, more (⋯).

### 2.6 Motion

**UX-MOTION-001** `M3.1` `[T]` Structure never animates. Inserts, moves, wraps, reflows and undo appear in the next frame. Insertion lines, drop cells and selection outlines move instantly with the pointer.

**UX-MOTION-002** `M3.1` `[S]` Only these animate: chips and handles fade in over 80 ms; popovers, menus and drawers fade and slide 4 px over 120 ms (ease-out); toasts slide 8 px and fade over 160 ms, and fade out over 120 ms; the page-resize readout fades out 600 ms after release.

**UX-MOTION-003** `M3.1` `[A]` When the platform disables UI effects (`QApplication.isEffectEnabled(Qt.UI_AnimateMenu)` is false) or the setting `form_builder.reduce_motion` is on, every duration is 0.

### 2.7 Runtime palette isolation of the canvas

**UX-ISO-001** `M2.3` `[S A]` Canvas widgets render with the runtime look the user's app gets on ChoreBoy: the Fusion style, Qt's standard light palette, and the runtime default application font (not the shell's UI font). The M0.7 probe result is the source of truth; if it shows a different default style on ChoreBoy, this clause follows the probe.

**UX-ISO-002** `M2.3` `[A]` No shell or builder style sheet rule reaches a canvas widget. The test renders a reference form (one of every catalog widget) on the canvas under all five shell themes and compares it pixel-for-pixel with the same form rendered in a clean `QApplication` with only Fusion and the standard palette. Any difference fails. This covers the spike's earlier bug where an app-level sheet squeezed a scroll bar into spin arrows (spike decisions.tsv, 2026-10-20T22:54).

**UX-ISO-003** `M2.3` `[S]` The page card's mini title bar (window title, three caption glyphs) is drawn by the builder in neutral runtime-like greys, identical in every chrome theme. It is not the ChoreBoy window manager's chrome and must not pretend to be: it is 22 px high, `#E4E4E4` fill, `#6B6B6B` glyphs, title in the runtime font at 11 px semibold.

**UX-ISO-004** `M5.3` `[S]` A form-level style sheet set by the user (`styleSheet` on the root or any widget) applies on the canvas exactly as at run time, because it is part of the truth (UX-PRIN-001).

---

## 3. Integration into CBCS

### 3.1 The `.ui` tab

**UX-SHELL-001** `M2.2` `[S]` Opening a `.ui` file (project tree, Quick Open, File > Open, a Problems row, a link) opens a normal CBCS editor tab whose content is the builder Workbench. The tab title is the file name with the form glyph; the dirty marker is the shell's standard one; close, close-others, reopen-closed and split behave as for any tab.

**UX-SHELL-002** `M2.2` `[S]` The builder has no menu bar, no window title, no "back to Start" link and no status bar of its own (all four exist in the spike). Its commands live in shell menus (UX-SHELL-004), its status text goes to the shell status bar (UX-SHELL-006), and its problems go to the shell Problems panel (section 3.4).

**UX-SHELL-003** `M2.2` `[S]` The tab content is: a 36 px tab toolbar, then the three-pane Workbench (section 4.3). The tab toolbar follows the Markdown pane's toolbar pattern (`shell.markdownEditorPane.toolbar`: 8 px side padding, mode group on the left, actions on the right) so the two editors look like siblings.

**UX-SHELL-004** `M2.3` `[S]` When a form tab is active, a **Form** menu appears in the shell menu bar between View and Tools, and disappears when another tab becomes active. It holds: Insert widget… (/), Go to widget… (Ctrl+R), Layout ▸ (Vertical, Horizontal, Grid, Form, Horizontal splitter, Vertical splitter, Wrap in…, Unwrap, Remove layout…, Adjust size, Simplify grid), Size ▸ (Hug, Fill, Fixed for width and height, Reset size), Overlays ▸ (Tab order, Buddies; Connections in M6), Preview (Ctrl+Shift+R), Preview options ▸ (text size, screen scale, two widths), View XML (Ctrl+Shift+V), Form settings… (M5.5b), Create window class… The shell's Edit menu items (Undo, Redo, Cut, Copy, Paste, Delete, Select all, Find) operate on the form when the form tab has focus.

**UX-SHELL-005** `M2.2` `[S]` Save is the shell's Save (Ctrl+S). There is no Save button in the tab. The right end of the tab toolbar shows a quiet save-state text in `fb.faint`: "Not saved yet" (new), "Unsaved changes", "Saved" (for 4 s after a save, then blank), "Saved · ui_invoice.py updated" when generation ran. Generation failure shows in `fb.error` "Saved invoice.ui · ui_invoice.py not written" and a Problems row.

**UX-SHELL-006** `M2.3` `[S]` The shell status bar's editor segment (the one that shows "Ln, Col" for code) shows the builder's context sentence: the selection summary when idle ("email · Line edit · row 2 of the form layout"), the gesture sentence during a gesture ("Insert between Shop name and Receipts"), the overlay instruction during an overlay. The sentence never contains internal ids. The shell's own segments (run state, Python tooling, problems count) are untouched.

**UX-SHELL-007** `M2.2` `[T]` Undo/redo history is per tab (PLAN §3). Closing and reopening the tab starts a new history. The shell's Edit > Undo label names the command: "Undo Wrap in group box".

### 3.2 View XML

**UX-XML-001** `M2.2` `[S T]` The tab toolbar's left end holds a two-segment control **Design | XML** (same component and style as the Markdown pane's mode group). Ctrl+Shift+V toggles it, reusing the shell's "toggle source view" key (today labelled "Markdown: Toggle Preview").

**UX-XML-002** `M2.2` `[S]` XML shows the current document serialized on demand (lazy, PLAN §3) in the CBCS code editor with XML highlighting, full editing, and the shell's find and replace. An info bar at its top reads: "Edits here apply to the design when you switch back."

**UX-XML-003** `M2.2` `[T]` Switching back to Design with valid XML applies one `ReplaceDocument` command (one undo step, named "Undo XML edits"), re-realizes the form and restores the selection by object name where the name still exists. Unchanged XML applies nothing.

**UX-XML-004** `M2.2` `[S T]` Switching back with invalid XML keeps the XML view, moves the caret to the error, and shows an error bar: "Line 42: the tag `<widget>` is not closed. Fix it, or [Discard XML edits]." Discard restores the last valid design. Neither version is ever lost.

**UX-XML-005** `M2.3` `[S]` If the file has nodes the builder does not understand, Design shows them untouched and the XML view marks them with a gutter note "Kept as is". Nothing is silently dropped (survey failure mode "serializer vandalism"). Moved out of M2.2 because the gutter mark needs the code editor's marker API, which this slice does not own. Design already keeps unknown nodes.

### 3.3 Generated files

**UX-GEN-001** `M2.3` `[S]` Opening `ui_<name>.py` (or `*_rc.py`, or the logic expansion) opens it read-only with an info bar: lock glyph, "Generated from invoice.ui. Code Studio rewrites this file every time the form is saved. Put your code in invoice_window.py." Buttons: [Open invoice.ui] [Open invoice_window.py] [Edit anyway].

**UX-GEN-002** `M2.3` `[T]` "Edit anyway" makes the buffer writable for this tab only. If the user saves a hand edit, the next save of the form detects it (M1.4 hash) and asks in an info bar on the form tab: "ui_invoice.py has edits made by hand. Saving the form will replace them. [Replace] [Open ui_invoice.py] [Cancel save]". It never overwrites silently (pain 6).

**UX-GEN-003** `M2.3` `[A]` Generated files are excluded from Problems linting and from format-on-save. The project tree shows them with the lock glyph and `fb.muted` text, nested under (or sorted next to) their `.ui` file. They still open and search normally.

### 3.4 Problems

**UX-PROB-001** `M2.3` `[S]` Form diagnostics appear in the shell Problems panel as ordinary rows: severity icon, message, source "Form", file `invoice.ui`, and a location that names the widget instead of a line ("saveButton"). FB codes appear at the row end in `fb.faint` ("FB201").

**UX-PROB-002** `M2.3` `[T]` Double-clicking a form problem focuses (or opens) the form tab, selects the widget, scrolls it into view and focuses the inspector field the problem is about (for example the Buddy field, the connection row, or the rule in M6+).

**UX-PROB-003** `M2.3` `[S]` The inspector's form view (nothing selected) shows a one-line problem summary with a link "Show in Problems". The builder never duplicates the Problems list inside itself.

**UX-PROB-004** `M3.1` `[S]` A widget with an error carries a 12 px `ov.problem` badge, placed by the chip solver (UX-CHIP-002). Hover shows the message; click opens it in Problems.

### 3.5 Run and Preview

**UX-RUN-001** `M2.4` `[T]` F5 (Run Active File) with a form tab active: if the form belongs to a project, save the form (which generates `ui_*.py`), then run the project entry point; the status bar says "Saved invoice.ui · Running main.py". If the project has no entry point, or the form is outside a project, F5 opens Preview instead and the status bar says why ("This form isn't part of a project, so F5 previews it."). A form inside the project that is not in `forms/` and is not adopted previews too, and the status bar says "This form isn't in forms/ or adopted, so F5 previews it." Shift+F5, Ctrl+F5 and Ctrl+Shift+F5 keep their shell meanings.

**UX-RUN-002** `M2.5` `[S T]` Preview (Ctrl+Shift+R, the Preview button) shows the form from the generated module in the separate preview process. The window title is "Preview · invoice.ui". While the child starts the button shows a spinner and the label "Starting…"; warm starts must not show it. Closing the preview window or pressing Esc in it closes it.

**UX-RUN-003** `M2.5` `[S T]` If the preview process crashes or raises, the editor stays usable, a Problems row is added ("Preview stopped: ImportError in myapp.widgets (line 12)"), and a toast says "Preview stopped. Your form is fine. [Show problem]". Preview is retried on the next request with the plan's crash-loop backoff; while backing off the button tooltip says "Preview is resting after 3 crashes. Try again in 20 s."

**UX-RUN-004** `M2.5` `[S]` Custom widgets that cannot be drawn in the editor show as sized stand-ins on the canvas (class name, dashed outline, at least 80 × 24 px; pain 7) and as the real class in Preview.

**UX-RUN-005** `M2.4` `[S]` The shell's packaging flow lists the project's forms with their generated files. A generated file older than its form, or missing, is a packaging problem with a fix button: "ui_invoice.py is older than invoice.ui. [Save the form now]" (pain 10).

### 3.6 Keyboard shortcuts

The shell table in `app/shell/shortcut_preferences.py` is authoritative. A form tab may reuse a shell shortcut only when its meaning in the form is the same idea (save, undo, find, rename, zoom, go to symbol). Every new form shortcut was checked against the shell table and against Linux window-manager defaults (MATE, Xfce, GNOME): `Ctrl+Alt+arrows`, `Alt+drag`, `Alt+F1…F10`, and `Ctrl+Shift+U` (IBus) are never used.

**UX-KEY-001** `M2.3` `[A]` A test loads the shell shortcut table plus the form table below and fails if any two commands active in the same focus context share a key, or if a form key is one of the window-manager keys listed above.

**UX-KEY-002** `M2.3` `[A]` Form shortcuts are registered with the shell's `ShortcutCommand` mechanism under category "Form designer", so Settings > Keyboard can rebind them and conflict detection covers them.

**UX-KEY-003** `M2.3` `[S]` All shortcuts use portable `QKeySequence` text: Ctrl means Command on macOS (developer machines). The spike's special case of physical Control for Ctrl+G is withdrawn.

**UX-KEY-004** `M2.3` `[K]` The complete form key table. "Shell" in the last column means the shell already binds the key and the form gives it the same meaning; "new" means a form-only key; "inert" means the shell key does nothing in a form tab and the status bar says what to use instead.

| Key | Context | Action | Status |
| --- | --- | --- | --- |
| Ctrl+S | form tab | Save `.ui` and generate `ui_*.py` | shell |
| Ctrl+Shift+S | any | Save all | shell |
| Ctrl+W | any | Close tab | shell |
| Ctrl+Z / Ctrl+Shift+Z | form tab | Undo / redo (form command log) | shell |
| Ctrl+X / Ctrl+C / Ctrl+V | canvas, outline | Cut / copy / paste into the layout (UX-CLIP) | shell |
| Delete, Backspace | canvas, outline | Delete selection (asks first if referenced, UX-OUT-012) | shell |
| Ctrl+A | canvas, outline | Select all siblings of the selection (or all children of the selected container) | new |
| Ctrl+D | canvas, outline | Duplicate after the selection | new |
| Ctrl+F | form tab | Find widget: focuses the outline filter. In the inspector: property search | shell (same idea) |
| Ctrl+R | form tab | Go to widget: a picker of object names, text and classes | shell (Go to Symbol) |
| F2 | canvas, outline, inspector | Rename (object name) in place | shell (Rename Symbol) |
| Enter | canvas | Edit the widget's text in place; on a container or layout, select its first child | new |
| Esc | everywhere | Close the innermost transient thing, else select the parent (UX-SEL-004) | new |
| Tab / Shift+Tab | canvas | Select next / previous widget in outline order (R3 22) | new |
| Tab / Shift+Tab | outline | Nest into the previous sibling container / un-nest | shell (Indent / Outdent idea) |
| Up, Down, Left, Right | canvas | Select the nearest widget in that direction | new |
| Up, Down | outline | Previous / next row | new |
| Left, Right | outline | Collapse or go to parent / expand or go to first child | new |
| Shift+arrow | canvas | Add the nearest widget in that direction to the selection | new |
| Alt+Up / Alt+Down | canvas, outline | Move within the layout (rows in forms and grids) | new |
| Alt+Left / Alt+Right | canvas | Move within a horizontal layout or across grid columns | new |
| Alt+arrow | canvas, bare container | Nudge by 8 px | new |
| Alt+Shift+arrow | canvas, bare container | Nudge by 1 px | new |
| Ctrl+Shift+arrow | canvas | Resize: width or height ± 8 px, writing Fixed (UX-RESIZE-006) | new |
| Ctrl+arrow | canvas | Resize: width or height ± 1 px, writing Fixed (UX-RESIZE-006) | new |
| / | canvas, outline | Quick insert after the selection | new |
| Ctrl+1 / Ctrl+2 | canvas, outline | Lay out horizontally / vertically (Designer parity) | new |
| Ctrl+3 / Ctrl+4 | canvas, outline | Lay out in a horizontal / vertical splitter | new |
| Ctrl+5 / Ctrl+6 | canvas, outline | Lay out in a grid / in a form | new |
| Ctrl+J | canvas, outline | Adjust size (Designer parity) | new |
| Ctrl+Shift+G | canvas, outline | Wrap in… (popover) | new |
| Ctrl+Shift+B | canvas, outline | Unwrap (remove the selected layout or plain container, keep its children in place) | new |
| (no key) | menu | Remove layout… (Designer's Break layout; Designer's Ctrl+0 is zoom here) | new |
| Ctrl+= / Ctrl+- / Ctrl+0 | form tab | Canvas zoom in / out / 100% | shell (Zoom) |
| Ctrl+9 | form tab | Zoom to fit | new |
| Ctrl+PgDown / Ctrl+PgUp | canvas, outline | Show the next / previous page of the innermost page container (canvas only, not saved; UX-CONT-007) | new (M4.2) |
| Ctrl+wheel | canvas | Zoom around the pointer | new |
| Ctrl+Shift+V | form tab | Design / XML | shell (toggle source view) |
| Ctrl+Shift+R | form tab | Preview | new |
| F5 | form tab | Run (UX-RUN-001) | shell |
| Shift+F5 / Ctrl+F5 / Ctrl+Shift+F5 | any | Run project / debug the active file / debug the project | shell |
| F3 | form tab | Leave overlay (same as Esc; Designer's "Edit widgets") | new |
| F7 | form tab | Buddies overlay (toggle) | new |
| F8 | form tab | Tab order overlay (toggle) | new |
| F4 | form tab | Connections overlay (M6; Designer parity) | new |
| Alt+1 / Alt+2 / Alt+3 / Alt+4 | form tab | Focus Outline / Insert / Canvas / Inspector | new |
| Shift+F10, Menu key | canvas, outline | Context menu for the selection | Qt standard |
| Ctrl+K, W | form tab | Two-widths view (toggle) | new (shell chord prefix) |
| Ctrl+H, Ctrl+G, Ctrl+/, Ctrl+Alt+V, Ctrl+Shift+Space, F9 | form tab | Nothing. Status: "Not used in the form designer. Ctrl+R goes to a widget." | inert |
| Shift+F2 | any | Stop (shell). Not used for rename in the form (the spike and LOGIC_DESIGN §2.12 used it) | shell |
| Ctrl+Shift+F | any | Find in Files (shell), which gains a "Forms" result group (M7.8) | shell |

**UX-KEY-005** `M6.0` `[A]` LOGIC_DESIGN §2.12 keys are adopted with three changes forced by the shell table: Try mode is Ctrl+Shift+R (not Ctrl+R); "search this form's logic" is Ctrl+F in the form tab (not Ctrl+Shift+F); rename is F2 (not Shift+F2). Ctrl+Shift+E, Ctrl+Shift+L, Ctrl+Space, Ctrl+., Ctrl+Enter, F12 and Shift+F12 are adopted unchanged (none collide). Alt+B (focus Behavior tab) is adopted only if no shell menu title uses the mnemonic B; otherwise it becomes Alt+4 then B.

**UX-KEY-006** `M3.1` `[S]` The canvas's first focus in a session shows a one-time status sentence: "Tab moves between widgets. Alt+4 goes to the inspector, Alt+1 to the outline."

### 3.7 PySide2 runtimes

**UX-PS2-001** `M2.1` `[S]` On a PySide2 runtime the builder is not loaded. A `.ui` file opens in the code editor as XML, with a dismissible info bar: "Visual form editing needs FreeCAD 1.1 or later. This form opens as text here; your changes are kept." The bar has no button and appears once per file per session.

**UX-PS2-002** `M2.1` `[S]` On PySide2, "New Form…" menu items, the Form menu and form templates are absent (not disabled). Projects that contain forms still open, build and run as before. Generated `ui_*.py` files keep their read-only banner (UX-GEN-001) because the banner is a shell feature that does not need PySide6.

---

## 4. Screens and regions

### 4.1 New form (Start)

**UX-START-001** `M2.2` `[S]` Start is not a home screen of the builder; it is the **New form** tab. It opens from File > New Form…, from the project tree context menu ("New Form…" on any folder, defaulting to `forms/`), and from the Welcome page. Opening an existing `.ui` never shows Start.

**UX-START-002** `M5.5c` `[S]` Layout: a centred column, max 960 px wide, 32 px top padding. Top: Hero "New form", then one sentence in `fb.muted`: "Every starting point is already laid out, so it resizes with the window." Then the name row (UX-START-003). Then three card groups. A right rail (240 px) with recent forms appears when the tab is at least 1180 px wide; below that, recent forms are a list under the cards.

**UX-START-003** `M2.2` `[S T]` The name row is first and focused on open: "Name [new_form] in [forms/ ▾]" and a live caption "Creates forms/new_form.ui, ui_new_form.py and new_form_window.py." The default name is unique in the folder. Invalid names show an inline message under the field and disable creation: "Use letters, digits and _, starting with a letter."

**UX-START-004** `M2.2` `[S K]` Card groups, each card a whole click target (no inner buttons):
- **Templates**: Data entry form; List and detail; Table with search; Dialog with OK and Cancel.
- **Start blank**: Widget; Main window; Dialog.
- **From what you have**: Build a form from a table; Adopt a form your code already loads (M2.4).

Clicking a card, or pressing Enter on a focused card, creates the files with the name row's values and replaces the tab content with the Workbench, with the first useful widget selected (the first input for templates, the root for blank forms). Arrow keys move between cards; the focused card has the focus ring (UX-A11Y-003). Templates name their widgets for what they hold (`nameLabel`, `nameEdit`, `emailEdit`, `buttonBox`), never `label_2`; forms built from a table use the column names.

**UX-START-005** `M2.2` `[S]` Cards are 200 × 156 px: a painted wireframe thumbnail (120 px tall, `fb.row_hover` fill, wireframe in `fb.faint` with one accent element), title in Strong, one-line description in Caption. Hover lifts the border to `fb.accent`; no shadow change.

**UX-START-006** `M2.2` `[S]` Recent forms lists up to 8 forms in this project opened most recently, with folder path in `fb.faint`. Empty: "Forms you open show up here."

**UX-START-007** `M5.5c` `[S]` Saved templates (save-as-template) appear as a fourth group "Your templates" only when at least one exists.

**UX-START-008** `M2.2` `[S]` The spike's "Keys worth knowing" card moves off Start into the empty-form state (UX-EMPTY-001) and Help > Form designer keys.

### 4.2 Build a form from a table

**UX-TABLE-001** `M2.2` `[S]` The spike's dialog structure is kept: table list (left), column mapping (middle: Include, Column, Type, Shows as, Label), live preview (right) rendered by the same realizer and runtime palette as the canvas. Fixes:
- the database path is shown relative to the project ("data/shop.sqlite"), with the full path in the tooltip (spike `from-table.png` shows a 90-character absolute path dominating the dialog);
- labels are derived from column names in title case with `_id` dropped ("customer_id" → "Customer"), editable;
- dates in the preview use the project locale with a four-digit year (spike shows "1/1/00");
- the primary button says what it does: "Create form with 6 fields"; disabled with the reason when 0 columns are included ("Include at least one column").

**UX-TABLE-002** `M8.3d` `[S]` From M8 the source is a named connection, and the created form is bound. Until then it lays out unbound fields from a SQLite file.

### 4.3 Workbench layout

```
+-- tab: invoice.ui ● ------------------------------------------------------------------------+
| [Design|XML]  [⇥ Tab order][🔗 Buddies]   ↶ ↷   [− 100% +]  [Aa ▾] [⇆]   [▶ Preview]  Saved  |  36 px tab toolbar
+----------------+--------------------------------------------------------+------------------+
| OUTLINE    + ⌕ |  · · · · · · · · · · · · · · · · · · · · · · · · · · · | ▭ email       ↺  |
| ▾ Invoice      |  ·   ┌ Invoice ───────────────────────── _ □ × ┐      · | Line edit        |
|   ▾ ≡ form     |  ·   │ Name *   [______________________________] │      · | Invoice › form › |
|      Aa nameL. |  ·   │ Email    [______________________________] │      · |[Properties|Behav]|
|      ▭ name    |  ·   │ Notes    [                              ] │      · | ⌕ Find property  |
|      ...       |  ·   │                         [ OK ] [Cancel ]  │      · | CONTENT          |
|----------------|  ·   └────────────────────────────────────────────┘      · | SIZE             |
| INSERT       ⌕ |  ·                     640 × 480 ═                     · |  Width  Hug|Fill|Fx
| [tiles...]     |  · · · · · · · · · · · · · · · · · · · · · · · · · · · |  ...             |
+----------------+--------------------------------------------------------+------------------+
  (shell status bar)  email · Line edit · row 2 of the form layout                 ✓ 0 problems
```

**UX-WB-001** `M2.2` `[S]` Three panes in a horizontal splitter: left pane (Outline over Insert), canvas, inspector. Default widths at a 1280 px wide tab: left 232, inspector 300, canvas the rest. Limits: left 184–360, inspector 264–420, canvas at least 360. The splitter handles are 1 px lines with a 6 px hit area, and they drag (the spike's handles do not). Widths persist per user, not per file.

**UX-WB-002** `M2.2` `[S]` The left pane is a vertical splitter, Outline above Insert (default 45 / 55), each with an Overline header, a header button row (Outline: + insert, ⌕ filter; Insert: ⌕ filter) and its own scroll. Either can be collapsed to its header by clicking the header; collapsed state persists.

**UX-WB-003** `M2.2` `[S]` Tab toolbar contents, left to right: **Design | XML** segments; a 1 px divider; overlay toggles **Tab order** and **Buddies** (toggle buttons, not a segmented "mode" control; text plus glyph; checked state uses `fb.row_selected` fill); Undo and Redo icon buttons (disabled state uses `fb.faint`, enabled `icon_primary`; the spike's always-faint arrows read as disabled); zoom group **− [100%] +** where the percentage is a menu button (Fit, 50, 75, 100, 150, 200 %); **Aa ▾** preview options (UX-SCALE); **⇆** two widths toggle (UX-WIDTHS); **Preview** button (secondary style with play glyph); the save-state text (UX-SHELL-005). Every icon-only button has a tooltip that includes its shortcut.

**UX-WB-004** `M2.2` `[S]` The canvas is a `QGraphicsView` over the backdrop: dot grid, the page card centred with at least the gutter (UX-ZOOM-004) around it, a page chip above the page's top-left outside corner ("Invoice · Form layout"), and the size readout under the page's bottom edge ("640 × 480"). The page's right and bottom edges carry pill grabbers (32 × 4 px, `fb.faint`, `fb.accent` on hover) that resize the form (UX-RESIZE-008).

**UX-WB-005** `M3.1b` `[S]` The inspector: header (UX-INSP-001), tab bar Properties · Behavior · Data (UX-INSP-002), a sticky property search field (Properties tab), then scrolling content. It is never empty: with nothing selected it shows the form (UX-INSP-010).

**UX-WB-006** `M2.2` `[S]` Toasts appear bottom-centre of the canvas viewport, 16 px above its bottom edge, over the backdrop. Banners (overlay instructions, info bars) appear at the top of the canvas viewport, also over the backdrop; the page is pushed down by the banner height rather than covered.

### 4.4 Empty states

Every empty surface says what it is and what to do next, in one or two sentences, with at most one button.

**UX-EMPTY-001** `M3.1` `[S]` Empty form (root layout with no items): the drop zone fills the root layout's whole interior (the spike's only fills a 160 px band at the top, `empty-form.png`). Centre text: "Drop a widget here" (Strong) and "or press / to search for one." (Caption), and under it three key hints in Caption: "/ insert · Ctrl+Shift+G wrap · F2 rename".

**UX-EMPTY-002** `M3.1` `[S]` Empty nested layout or empty container: drawn at least 32 px tall and 48 px wide with a dashed `ov.layout_faint` outline and centred Caption "Drop widgets here" when the area is at least 120 px wide, else a 12 px plus glyph. This minimum is a canvas-only size and is never saved (pain 4).

**UX-EMPTY-003** `M3.2` `[S]` Empty tab widget page, stacked page or toolbox item: the same as UX-EMPTY-002, with "Drop widgets on this page".

**UX-EMPTY-004** `M3.5` `[S]` Outline filter with no match: "No widget matches “xyz”." and a [Clear] link. Insert filter with no match: "Nothing called “xyz”. Try text, list or date." (suggestions are three real category words).

**UX-EMPTY-005** `M3.1b` `[S]` Behavior tab with no connections (M3–M5): "Nothing happens yet when this button is clicked." and [+ Add connection]. The sentence names the class's default event in words (LOGIC_DESIGN §2.2 table).

**UX-EMPTY-006** `M3.1b` `[S]` Data tab: hidden in user-facing builds until M8 lands. In development builds before M8 it shows "Connect this form to a table" as a disabled button with the caption "Not built yet (M8)". This stub text is the only place a milestone name may appear, and only behind the development flag. Behavior tab stubs follow the same rule: user builds never say "coming in the logic phase" (spike `inspector-behavior.png`).

**UX-EMPTY-007** `M5.6` `[S]` Tab-order list with no inputs: "No fields to visit yet. Inputs join the order as you add them."

**UX-EMPTY-008** `M2.2` `[S]` An unreadable file opens as a text tab with an info bar: "This form can't be opened in the form builder:" plus the reason (the CONTRACTS §8.5 wording). There is no centred panel and no [Open as text] button. This matches CONTRACTS §8.5: the provider declines and the shell opens the file as text.

**UX-EMPTY-009** `M2.2` `[S]` Recovered draft and external change are info bars at the top of the tab (not modal dialogs): "Recovered unsaved changes from 14:02. [Keep recovered] [Discard]"; "invoice.ui changed on disk. [Reload from disk] [Keep mine] [Compare…]". Compare opens the shell diff of the two XML texts.

### 4.5 Responsive behaviour

ChoreBoy screens may be 1366 × 768. Inside CBCS (project tree, menu, toolbar, tab bar, status bar) the form tab gets roughly 1080 × 600 px, and about 1080 × 420 with the Problems panel open. The spike at 1100 × 640 clips the page under a horizontal scroll bar and cannot collapse a pane (extra capture `small-1100x640.png`). Breakpoints use the tab content size W × H.

**UX-RESP-001** `M2.2` `[S]` W ≥ 1180: all panes at their remembered widths.

**UX-RESP-002** `M2.2` `[S]` 900 ≤ W < 1180 (the common ChoreBoy case): compact density. Left pane 200, inspector 272, pane padding 8, Insert tiles switch from a 3-column icon grid to a 2-column icon-and-label list.

**UX-RESP-003** `M2.2` `[S T]` 720 ≤ W < 900: the left pane collapses to a 36 px rail with two icon buttons, Outline and Insert. Clicking one (or Alt+1 / Alt+2) opens it as a 240 px drawer over the canvas edge (level 2), which closes on Esc, on a click on the canvas, or after a drop from Insert. A pin button in the drawer header restores the docked pane.

**UX-RESP-004** `M2.2` `[S T]` W < 720: the inspector also collapses to a right rail with its three tab icons; opening it shows a 288 px drawer. Selecting a widget does not auto-open it.

**UX-RESP-005** `M2.2` `[S]` H < 560: Outline and Insert stop splitting vertically and become two tabs in one left pane ("Outline | Insert"). The inspector header compresses to one line (glyph, name, class) and the breadcrumb moves into the name field's tooltip.

**UX-RESP-006** `M2.2` `[S]` The tab toolbar at W < 1000 hides the overlay toggle labels (glyph only, with tooltips) and folds Aa and ⇆ into a ⋯ menu. Nothing in the toolbar wraps or clips.

**UX-RESP-007** `M3.1` `[T]` Opening a form, and resizing panes while zoom is "Fit", sets the zoom to fit the page plus gutters, capped at 100% (never upscales on open), floored at 50% (below that it scrolls). Once the user picks a zoom, pane resizes keep it.

---
## 5. The canvas interaction model

### 5.1 Selection

**UX-SEL-001** `M3.1` `[T]` A click selects the deepest widget whose rectangle contains the pointer. A click in a layout's empty space (a gap, a margin, an empty grid cell, the area past the last item) selects that layout. A click on the backdrop selects the form. Press-and-drag beyond 4 px starts a move instead (UX-MOVE-001); the selection happens on press, so a drag always moves what you pressed.

**UX-SEL-002** `M3.1` `[T]` Shift+click and Ctrl+click both toggle a widget in or out of the selection. The last clicked widget is the *primary* selection: the inspector header shows it, and alignment-style commands (M4) use it as the anchor. Alt+click is not used (Linux window managers take Alt+drag and often Alt+click).

**UX-SEL-003** `M3.1` `[T]` Rubber band: a drag that starts on empty space inside a container (not on a child) draws a 1 px `ov.select` rectangle with `ov.drop_fill`, and selects the direct children of that container whose rectangles it touches. Shift held at the start adds to the selection. A rubber band never selects across containers (wrap and layout commands need siblings). A drag that starts on the backdrop selects among the root's children.

**UX-SEL-004** `M3.1` `[K]` Esc, in order of precedence: close the in-place editor (cancelling), close an open popover or menu, cancel a drag in progress (nothing changes), close the open overlay, close an open drawer; otherwise select the parent. Parents count layouts: line edit → its layout → the container → the container's parent layout → … → the form. Esc on the form does nothing (selection never becomes empty).

**UX-SEL-005** `M3.1` `[K]` Enter on a container or layout selects its first child. Enter on a widget with editable text opens the in-place editor (UX-TEXT-001).

**UX-SEL-006** `M3.1` `[K]` Tab and Shift+Tab select the next and previous widget in outline pre-order, skipping layouts and spacers, wrapping at the ends, and scrolling the canvas to keep the selection visible (R3 22).

**UX-SEL-007** `M3.1` `[K]` Arrow keys select the nearest widget in that direction (spatial navigation by centre point, ties broken by outline order). Shift+arrow adds that widget. Alt+arrows move (UX-NUDGE).

**UX-SEL-008** `M3.1` `[S]` The selection is drawn as a 2 px `ov.select` stroke 1 px outside each selected widget's rectangle, with resize handles on the primary selection only (UX-RESIZE-001). A selected layout is drawn as a 1.5 px solid `ov.layout` frame instead.

**UX-SEL-009** `M3.1` `[T]` Canvas selection, outline selection and inspector are one model: selecting in any of them updates the other two in the same frame, scrolls the outline row into view (without moving keyboard focus) and scrolls the canvas to reveal the widget when it is off-screen.

**UX-SEL-010** `M3.1` `[T]` Structural commands that need siblings (wrap, lay out, unwrap) are disabled when the selection spans different parents. Their tooltip and the status bar say why: "Select widgets in the same layout to wrap them."

### 5.2 Hover

**UX-HOV-001** `M3.1` `[S]` Hover draws a 1 px `ov.hover` outline 1 px outside the deepest widget under the pointer. No chip. The parent layout's faint frame strengthens to `ov.layout` at 60%. The outline row of the hovered widget gets `fb.row_hover`.

**UX-HOV-002** `M3.1` `[S]` The status bar shows "shopName · Line edit · click to select" (or "· double-click to edit text" when that is the double-click action). Hovering an outline row hovers the canvas widget, and the reverse.

**UX-HOV-003** `M3.1` `[S]` Hover never draws anything while a drag, an in-place editor or a popover is active.

### 5.3 Layout frames

**UX-FRAME-001** `M3.1` `[S]` Every layout draws a 1 px dashed `ov.layout_faint` frame around its rectangle, always (View option "Show layout frames", on by default, per user). The selected or hovered container's own layout draws solid `ov.layout`.

**UX-FRAME-002** `M3.1` `[S]` A spacer draws as a 1.5 px `ov.gap` spring (zigzag, 6 px amplitude) along its axis, centred in its rectangle; it is selectable like a widget and draws its sizing word under selection.

**UX-FRAME-003** `M3.1` `[S]` A container that has children but no layout (from older files) shows an amber "No layout" chip (via the chip solver) and a dashed `ov.tab` frame. Clicking the chip opens the Lay out popover (the wrap tiles applied to the container). This is the R3 34 "broken layout" marker.

### 5.4 Chips and badges: placement rules

The spike's name chip sits above the selected widget and covers the field above it (`workbench-light.png`, `workbench-dark.png`, `dark-layout.png`, `quick-insert.png`); its size badge covers the field below; chips pile up at a container's top-right corner (`empty-group.png`). The rules below replace that.

**UX-CHIP-001** `M3.1` `[S A]` Chips never cover content (section 0.3). This is checked automatically for every screenshot-tour state: no chip rectangle intersects a non-ancestor widget's rectangle or the selected widget's own rectangle. Handles are the only overlay elements allowed on the selected widget's edge.

**UX-CHIP-002** `M3.1` `[A]` The chip solver places each chip at the first candidate that is inside the viewport and free of non-ancestor content and of other chips, scanning: (1) outside the target, above its top-left corner, left-aligned; (2) below its bottom-left corner; (3) above its top-right corner, right-aligned; (4) below its bottom-right (a corner whose natural spot is off screen slides along the target's edge into view); (5) **beside** the target on its row, right then left, at 7 px, then further along the row with a horizontal 1 px leader in the chip colour that stops at the target's edge and crosses no other widget or chip (ancestor space is free); (6) the **gutter**: the backdrop band beside the page at the target's vertical centre with the same kind of leader. Leaders are horizontal; a leader that would cross content disqualifies the seat. The selection chip is never dropped: when (1)-(6) all fail it goes to (7) the **dock**, the page caption strip that sticks to the top of the canvas, at the target's x, painted as caption chrome (it covers no content); it gets a vertical leader only when nothing lies between the strip and the target. A "No layout" chip may also sit inside its own container's top-right or bottom-right corner, never on a child.

**UX-CHIP-003** `M3.1` `[S]` One label per selection, not three. The primary selection's chip reads "email · Fill × Hug". A selected container adds its layout kind: "receiptGroup · Horizontal". A selected layout reads "receiptRow · Horizontal layout · 2 items". Pixel sizes are shown only while resizing (UX-RESIZE-004) and in the inspector. Multiple selection: one chip on the primary, reading "email + 2 more".

**UX-CHIP-004** `M3.1` `[S]` Chip style: 18 px tall, 4 px radius, 6 px horizontal padding, 11 px semibold `ov.chip_text` on the role colour (selection `ov.select`, layouts `ov.layout`, numbers `ov.gap`, drop targets `ov.select`, tab order `ov.tab`, buddies `ov.buddy`, problems `ov.problem`). Chips keep their screen size at every zoom. Long object names elide in the middle at 24 characters.

**UX-CHIP-005** `M3.1` `[S]` Badges (problem badge, tab-order number, logic badges in M6) are 16 px circles placed by the same solver with corner candidates first (outside top-right, outside top-left), then the gutter.

**UX-CHIP-006** `M3.1` `[S]` The page chip above the page ("Invoice · Form layout") and the size readout under it live on the backdrop and are not counted as overlay chips; they use `fb.muted` text with no fill when idle and the role fill when the form is selected.

### 5.5 Drag and drop: common rules

**UX-DND-001** `M3.2` `[T]` Drag sources: an Insert tile, an Insert search result, an outline row, a canvas widget, and (M8) a Data column. Drop targets: the canvas and the outline. A drag from the outline can drop on the canvas and the reverse.

**UX-DND-002** `M3.2` `[S]` During a drag the dragged widget is shown as a 60% opacity snapshot under the pointer (offset so the pointer sits at the grab point). For a move, the original stays where it is at 35% opacity until release, so nothing else on the form moves before the drop (pain 21).

**UX-DND-003** `M3.2` `[S]` Exactly one drop target is shown at a time: the target layout's frame turns solid `ov.layout`, and the slot indicator for that layout kind is drawn (sections 5.6–5.11). The spike's whole-container tint is withdrawn: no fill washes over existing widgets.

**UX-DND-004** `M3.2` `[S]` The drop description is shown in two places: in the status bar as a sentence in plain words, and in a chip placed by the chip solver next to the indicator (normally in the gutter). Sentences name neighbours by their visible text when they have it, else by object name: "Insert between Shop name and Receipts", "Into row 2, column 3 of the grid", "New row after Email", "Into the Settings tab", "Into receiptGroup · makes a vertical layout". Internal names like "verticalLayout · position 3" are not used (spike `drag-box.png`).

**UX-DND-005** `M3.2` `[T]` Invalid targets (a widget into itself or its descendant, a spacer into a form's label column, a span that does not fit) show the indicator in `ov.problem`, the not-allowed cursor, and a status sentence that says why: "A widget can't go inside itself." Release over an invalid target does nothing.

**UX-DND-006** `M3.2` `[T]` Esc during a drag cancels it with no change. Leaving the canvas and outline cancels the target (no indicator) but keeps the drag alive until release.

**UX-DND-007** `M3.2` `[T]` Every drop is one undo step that also selects the dropped widget(s), and focuses the canvas (not the inspector).

**UX-DND-008** `M3.2` `[T]` Hit-testing is by slot geometry, not by widget under the pointer: inside a layout, the nearest slot boundary along the layout's axis wins; the pointer never has to hit a 6 px gap.

**UX-DND-009** `M3.2` `[T]` Spring-loading: hovering a drag over a collapsed outline row for 600 ms expands it; over a tab-widget tab title or toolbox item header for 600 ms switches to that page; over a stacked widget's page arrows (UX-PAGES-003) for 600 ms flips the page.

### 5.6 Box layouts

**UX-BOX-001** `M3.2` `[S T]` The indicator is a 2 px `ov.select` line with 6 px round end caps, centred in the gap between the two items it falls between (or 3 px inside the layout edge for first and last), spanning the layout's cross axis minus 4 px at each end.

**UX-BOX-002** `M3.2` `[T]` The insertion index is chosen by the pointer's position relative to each item's midpoint along the layout axis.

**UX-BOX-003** `M3.2` `[T]` Dropping near (within 8 px of) the edge of a widget along the *cross* axis of its layout is how nesting starts: dropping a widget to the right of a field in a vertical layout shows a vertical indicator at that field's right edge and the chip "Beside Email · makes a horizontal row". The drop wraps the field and the dropped widget in a new horizontal layout at the field's index (one undo step). This replaces the Designer workflow "drop, select both, lay out horizontally".

### 5.7 Grid layouts

**UX-GRIDL-001** `M3.2` `[S T]` Over an empty cell: the cell is drawn as a 1.5 px dashed `ov.select` rectangle with `ov.drop_fill`; chip "Row 2, column 3" (1-based, as in every user-facing count).

**UX-GRIDL-002** `M3.2` `[T]` Over an occupied cell: the indicator is a line on the cell edge nearest the pointer (left, right, top, bottom); the drop inserts a new column or row there and shifts later columns or rows by one; chip "New column before Medium". The occupied cell's centre (middle 50%) is not a target.

**UX-GRIDL-003** `M3.2` `[S T]` Past the last row or column (a 24 px band outside the grid, inside its container), a ghost cell with a dashed outline appears: "New row 3" or "New column 4".

**UX-GRIDL-004** `M3.2` `[T]` Moving an item that spans several cells keeps its span; if the span does not fit at the target the ghost is drawn in `ov.problem` and the status says "Needs 2 free columns here". Only the moved item's row, column and span change (pain 21); other items keep their cells.

**UX-GRIDL-005** `M3.3` `[T]` In a grid, dragging an item's right or bottom handle snaps to cell boundaries and changes its column or row span (readout "Spans 2 columns"); holding Shift while dragging writes a Fixed size instead (readout "Fixed 240 px"). The inspector's Placement group shows row, column and spans as numbers.

**UX-GRIDL-006** `M3.3` `[S T]` When the grid or its container is selected, share numbers (stretch) appear for each column and row as `ov.gap` chips via the solver, preferring the gutter band above the columns and left of the rows (delighter 7). Clicking one focuses that number in the inspector.

### 5.8 Form layouts

**UX-FORML-001** `M3.2` `[S T]` A form row has a label cell and a field cell. Over an empty cell of an existing row the cell is the target (dashed cell, chip "Field of row 3" or "Label of row 3"). Over an occupied cell the target is the line between rows nearest the pointer (chip "New row after Email").

**UX-FORML-002** `M3.2` `[T]` Dropping a non-label widget into a new row creates the row with a label "New field:" as the field's buddy, places the widget in the field cell, and opens the in-place editor on the label with its text selected. Typing and Enter names the row. All of this is one undo step, and Esc in the editor keeps the label text "New field:". Dropping a label into a new row puts it in the label cell and leaves the field cell empty, ready for the next drop (UX-AUTO-003). A push button, tool button, check box, radio button, command link, group box, or button box goes in the field cell with no label.

**UX-FORML-003** `M3.2` `[T]` A widget dropped on the label cell of a row whose label is empty becomes the row's label even if it is not a `QLabel` (Qt allows any widget). A spacer cannot go in a form cell (UX-DND-005).

**UX-FORML-004** `M3.2` `[T]` A row that spans both columns (`SpanningRole`) shows one cell across both columns; dropping on it targets the lines above and below only.

### 5.9 Splitters

**UX-SPLIT-001** `M3.2` `[S T]` A splitter's children are panes. The drop indicator is a 2 px line across the splitter at the pane boundary nearest the pointer, or at either end; chip "New pane after Customers list".

**UX-SPLIT-002** `M3.3` `[S T]` Splitter handles on the canvas are draggable (pain 19). The visual handle is the runtime one; the overlay adds an 8 px hit area centred on it and a grip glyph on hover. Dragging moves the boundary live in 1 px steps (Shift: 8 px), and the release is one undo step that writes the panes' stored sizes (mechanism per `CONTRACTS.md`). Double-click on a handle resets the panes to equal sizes.

**UX-SPLIT-003** `M3.3` `[S]` Selecting a pane shows its Share number on the splitter just like a box layout's stretch, and the inspector's Size group shows "Share of spare room" for it with the same control as a box item (R3 weakness "Splitter stretch is not in the property editor").

### 5.10 Tab, stacked and toolbox pages

**UX-PAGES-001** `M3.2` `[T]` Dropping onto a page container drops into the *current page's* layout, using that layout kind's indicator. A page with no layout follows UX-BARE-001.

**UX-PAGES-002** `M3.2` `[S T]` A tab widget on the canvas shows a "+" pseudo-tab after its last tab (overlay, `ov.select`, only while the tab widget is hovered or selected, or during a drag). Clicking it adds a page "Tab 3" with a vertical layout and opens the in-place editor on its title. Dropping a widget on it creates the page with the widget inside.

**UX-PAGES-003** `M3.2` `[S]` A stacked widget shows a page switcher chip via the chip solver: "◀ 2 / 3 ▶" with the current page's object name in the tooltip. Clicking the arrows changes the page shown on the canvas only (not `currentIndex`, which is a property in the inspector).

**UX-PAGES-004** `M3.5` `[T]` Pages reorder by dragging tab titles on the canvas (2 px vertical insertion line between titles, at least 8 px hit area), by dragging page rows in the outline, and with Alt+Left/Right on a selected tab title or Alt+Up/Down on a page row (pain 20; R3 127).

### 5.11 Bare containers (no layout)

**UX-BARE-001** `M3.2` `[S T]` Over an *empty* container that has no layout, the whole interior shows a dashed `ov.select` outline with chip "Into receiptGroup · makes a vertical layout". The drop creates a vertical layout with the widget in it: one undo step (pain 1).

**UX-BARE-002** `M3.2` `[S T]` Over a container with absolutely placed children and no layout (older files only), the drop places the widget at the pointer, snapped to an 8 px grid (Shift: no snap), shown as a ghost rectangle at its default size with a "x 120, y 48" readout chip. The container keeps its "No layout" marker (UX-FRAME-003).

### 5.12 Auto-layout and "next drop fills the next cell"

**UX-AUTO-001** `M3.2` `[T]` Every new form and every container created from Insert already has a vertical layout (blank forms and templates, UX-START-004; group boxes, frames, tab pages, scroll-area contents). A bare container without a layout appears only when the user removes a layout or opens an older file.

**UX-AUTO-002** `M3.2` `[T]` The first drop into an empty bare container creates a vertical layout (UX-BARE-001). The kind can be changed afterwards in one click (UX-WRAP-005), so the first drop never asks.

**UX-AUTO-003** `M3.2` `[T]` Inserting without a pointer position (Insert tile double-click, Enter on a tile, quick insert `/`, paste with a layout selected) fills the next free place: in a form layout, the empty field cell of the last row if any, else a new row; in a grid, the first empty cell in reading order, else a new row; in a box, after the selected item or at the end (delighter 11).

**UX-AUTO-004** `M3.2` `[S]` Before an insert without a pointer, the target is previewed: while the Insert tile has keyboard focus or the quick-insert popover is open, the canvas draws the indicator where Enter will put the widget, and the popover caption names it: "Goes right after shopName."

### 5.13 Move and copy

**UX-MOVE-001** `M3.2` `[T]` Dragging a selected widget moves it (and all selected siblings, keeping their order) to the drop target. Moving into another container reparents it. Dragging an unselected widget selects it first and moves only it.

**UX-MOVE-002** `M3.4` `[T]` Holding Ctrl at the moment of release copies instead of moving (Designer's Ctrl-drag clone). The pointer shows the copy cursor while Ctrl is held. Alt is also accepted when the window manager delivers it, but is never the documented key (Linux window managers take Alt+drag).

**UX-MOVE-003** `M3.2` `[T]` A move that would leave a layout empty leaves it empty (it stays a hittable 32 px drop zone); layouts are never deleted as a side effect.

### 5.14 Gaps and margins

**UX-GAP-001** `M3.3` `[S]` When a layout (or a container with a layout) is selected, its gaps are drawn as 2 px `ov.gap` bars centred in each gap, spanning the layout's cross axis; its margins are drawn as `ov.gap_fill` bands on the four inner edges. Nothing about gaps is drawn when the layout is not selected (UX-PRIN-004).

**UX-GAP-002** `M3.3` `[T]` Dragging any gap bar changes the layout's spacing for all gaps at once (Qt has one spacing value per layout axis; for grids and forms, horizontal and vertical spacing are separate bars). Steps are 1 px; Shift snaps to multiples of 4. The number is shown live in a chip via the solver and in the inspector. Release is one undo step (delighters 3, 8).

**UX-GAP-003** `M3.3` `[T]` Dragging a margin band's inner edge changes that side's margin. Double-click a margin band, or a gap bar, resets it to the default (the property is deleted from the file, delighter 14).

**UX-GAP-004** `M3.3` `[S]` When the root layout is selected, the page edges show anchor ticks: small `ov.layout` ticks on all four page edges at the layout's attachment points, with the margin numbers in the gutter. Caption in the inspector: "Everything in this layout follows the window's edges." (delighter 4).

**UX-GAP-005** `M3.3` `[T]` Gap bars and margin bands have 12 px hit areas (UX-GRID-004). When they overlap a child's edge, the child's resize handle wins only if the child is the selection; otherwise the gap wins.

### 5.15 Resize handles and Fixed sizes

**UX-RESIZE-001** `M3.1` `[S]` A selected widget inside a layout has three handles: right edge midpoint, bottom edge midpoint, bottom-right corner. Handles are 7 × 7 px squares, white fill, 1.5 px `ov.select` border, centred on the selection stroke, with 12 px hit areas. Left and top handles do not exist, because the layout owns position.

**UX-RESIZE-002** `M3.3` `[T]` Dragging a handle writes Fixed on that axis (size policy Fixed plus minimum = maximum = N; PLAN and the spike's sizing model). The layout reflows live; release is one undo step.

**UX-RESIZE-003** `M3.3` `[T]` Double-click a handle resets that axis (the corner resets both) to the class default: the lines are deleted from the file.

**UX-RESIZE-004** `M3.3` `[S]` While resizing, the selection chip reads "Fixed 240 × Hug". The readout stays for 600 ms after release.

**UX-RESIZE-005** `M3.3` `[T]` A widget in a bare container (absolute geometry) has eight handles and moves freely; its handles write `geometry`. Snap 8 px; Shift disables snap.

**UX-RESIZE-006** `M3.3` `[K]` Ctrl+Shift+Right/Left changes the width by ±8 px, Ctrl+Shift+Down/Up the height, with the same effect as a handle drag. Ctrl+arrow without Shift changes it by ±1 px. Alt is not used, because ChoreBoy's window manager takes Ctrl+Alt+arrow (`_WM_FORBIDDEN` in `engine/shell_commands.py`).

**UX-RESIZE-007** `M3.3` `[T]` Every drag gesture that edits a number (gap, margin, resize, splitter, page edge) moves in 1 px steps by default and snaps to multiples of 8 with Shift (gaps snap to 4; UX-GAP-002). The spike mixed 4 px default steps with Alt for 1 px; Alt is withdrawn.

**UX-RESIZE-008** `M3.1` `[T]` The page's right and bottom grabbers resize the form's design size (root `geometry`), not a Fixed size; the layout follows live; the readout under the page shows the new size; release is one undo step.

### 5.16 In-place text editing

**UX-TEXT-001** `M3.1` `[T K]` F2 is rename, never text editing (UX-KEY-004). Enter on a selected widget whose visible text is a property (label, push/tool/radio button, check box, group box title, tab title, menu title or action, line edit placeholder when the text is empty) opens an in-place editor over that text. Double-click opens it too (until M6.2, after which double-click on buttons, check boxes, radio buttons and actions goes to the handler per LOGIC_DESIGN §2.12, and Enter remains the text gesture).

**UX-TEXT-002** `M3.1` `[S]` The in-place editor uses the runtime font at the canvas zoom, the widget's text alignment, a 1 px `ov.select` border and a white background, and selects all text. It grows with the text and never changes the form's layout while typing.

**UX-TEXT-003** `M3.1` `[T]` Enter commits; Esc cancels; clicking elsewhere commits; Tab commits and opens the editor on the next text widget in outline order (so a row of labels can be typed in one go). Shift+Enter inserts a newline only where the property allows it (word-wrapped labels, plain text). One undo step per commit.

**UX-TEXT-004** `M3.1` `[T]` For widgets whose text is a list (combo box items, list widget items), Enter opens the item editor (M4.4) instead. From M4 this covers tree and table widgets too (UX-ITEM-001).

### 5.17 Wrap, unwrap, morph, remove layout

**UX-WRAP-001** `M3.3` `[S K]` Ctrl+Shift+G opens the Wrap popover anchored below the selection (or in the gutter if it would cover the selection): a 3 × 3 grid of tiles — Vertical, Horizontal, Grid, Form, Horizontal splitter, Vertical splitter, Group box, Frame, Tab widget — with digits 1–9, arrows and Enter, and Esc to cancel. Header: "Wrap 2 widgets in…". Tiles that cannot apply are disabled with a tooltip reason.

**UX-WRAP-002** `M3.3` `[T]` Ctrl+1 … Ctrl+6 apply directly, as in Designer: on several siblings, wrap them in that layout kind; on a container without a layout, give it that layout; on a container or layout that already has a layout, change its kind (morph).

**UX-WRAP-003** `M3.3` `[T]` After a wrap the new container or layout is selected, the toast says "Wrapped 2 widgets in a group box · Undo", and the canvas does not rebuild (the realizer moves the existing widgets; spike decisions.tsv).

**UX-WRAP-004** `M3.3` `[T]` Unwrap (Ctrl+Shift+B) on a layout or a plain container (group box, frame, plain widget) puts its children into the parent layout at the container's index, in reading order, and deletes the container. Toast "Unwrapped receiptGroup · Undo". Unwrap is disabled on containers whose loss would drop data (tab widget with several pages, scroll area with a set widget) with the reason.

**UX-WRAP-005** `M3.3` `[T]` Morph layout: the inspector's Layout group shows "Kind" as a four-segment glyph control (Vertical, Horizontal, Grid, Form) that morphs in place, keeping children in reading order. A lossy morph (grid with spans to a box, a form with spanning rows) first shows a confirm popover listing what changes: "Spans will be removed from 2 widgets." [Change layout] [Cancel].

**UX-WRAP-006** `M3.3` `[T]` Morph widget: the context menu's "Change to ▸" lists compatible classes (Designer's "Morph into"; for example Line edit → Plain text, Spin box → Double spin box, Push button → Tool button). It keeps the object name, layout position and every property the new class has; a toast lists dropped properties: "Changed to a plain text box. 1 property didn't apply: echoMode · Undo".

**UX-WRAP-007** `M3.3` `[T]` Remove layout (Designer's Break layout) is in the Form > Layout menu and the context menu only. It confirms in a popover: "Remove the layout from receiptGroup? Its 2 widgets keep their current position and size, but they won't follow the window any more." [Remove layout] [Cancel]. The children get geometry equal to their current rectangles; no other layout on the form changes size; one undo step restores it (pain 5).

**UX-WRAP-008** `M3.3` `[T]` Adjust size (Ctrl+J) sets the selected container's or form's design size to its size hint (one undo step). Simplify grid removes empty rows and columns (one undo step; disabled with a reason when there are none).

**UX-WRAP-009** `M3.3` `[T]` "Keep at content size" (Form > Layout, context menu on a container) sets the container's share to 0 and its vertical sizing to Hug, so a login-style group stops growing with the window, without a spacer (pain 14). One undo step; the toast names what changed: "receiptGroup now keeps its content height · Undo".

### 5.18 Clipboard and paste into a layout

**UX-CLIP-001** `M3.4` `[T]` Copy puts a `.ui` fragment (and the object names as plain text) on the system clipboard, including the copied widgets' layouts, buddies among themselves, connections among themselves, and (M6+) their logic.

**UX-CLIP-002** `M3.4` `[T]` Paste target, by what is selected:

| Selection | Paste goes |
| --- | --- |
| A widget inside a box layout | After it, in the same layout |
| A widget in a grid | The next empty cell after it in reading order, else a new row under it |
| A widget in a form row | A new row after that row. A copied label and field pair stays a pair |
| A layout, or a container with a layout | At its end (form and grid: UX-AUTO-003) |
| An empty container without a layout | Into a new vertical layout (UX-BARE-001) |
| A widget in a bare container | Into the same container, offset by 16, 16 px |
| The form | At the end of the root layout |

Paste never shows "cannot paste" errors (pain 3, R3 weakness "Paste into a layout is refused").

**UX-CLIP-003** `M3.4` `[T]` Pasted widgets are selected; the outline scrolls to them; focus stays where it was. Name collisions are renamed with the next free number (email → email2), and references *within* the pasted set are rewritten to the new names (LOGIC_DESIGN §2.13). The status bar says "Pasted 2 widgets after shopName".

**UX-CLIP-004** `M3.4` `[T]` Duplicate (Ctrl+D) is copy and paste after itself without touching the clipboard. Cut is copy then delete (one undo step for the delete; the clipboard is not part of undo).

**UX-CLIP-005** `M3.4` `[T]` Paste across forms works; if pasted connections or (M6+) formulas refer to names that do not exist in the target, they are kept and flagged in Problems, and a toast says "Pasted 3 widgets. 1 connection points at a widget that isn't on this form. [Show]".

**UX-CLIP-006** `M3.4` `[S T]` The scratch pad (R3 27) is a section at the bottom of the Insert pane, "Saved pieces", collapsed when empty. Drag a selection onto it, or use "Save to pieces" in the context menu, to keep a reusable copy (per user, across projects). Pieces drag back like any Insert tile and can be renamed and deleted.

### 5.19 Keyboard nudges and keyboard moves

**UX-NUDGE-001** `M3.2` `[K]` Alt+Up/Down (and Alt+Left/Right in horizontal layouts and grids) move the selection one slot within its layout; in a form layout Alt+Up/Down swaps rows; at the layout's end the move stops (it does not leave the layout). One undo step per press; repeated presses within 1 s merge into one step.

**UX-NUDGE-002** `M3.2` `[K]` To move into or out of containers by keyboard use the outline's Tab / Shift+Tab (UX-OUT-004), or cut and paste.

**UX-NUDGE-003** `M3.3` `[K]` In a bare container Alt+arrow nudges by 8 px and Alt+Shift+arrow by 1 px, writing geometry.

### 5.20 Zoom

**UX-ZOOM-001** `M3.1` `[T]` Zoom levels: 25, 33, 50, 67, 75, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400%. Ctrl+= and Ctrl+- step through them; Ctrl+wheel zooms around the pointer; Ctrl+0 is 100%; Ctrl+9 fits. The zoom menu offers Fit, 50, 75, 100, 150, 200%.

**UX-ZOOM-002** `M3.1` `[S]` Overlay strokes, chips, handles and hit areas keep their screen size at every zoom. Only the form scales.

**UX-ZOOM-003** `M3.1` `[T]` Zoom is per tab and is not saved in the file. Middle-drag or Space+drag pans; the scroll wheel scrolls; Shift+wheel scrolls horizontally.

**UX-ZOOM-004** `M3.1` `[A]` The scene always keeps a **gutter** of 64 screen px of backdrop above and below the page and 96 px on each side. Fit zoom accounts for it. When the page and its side gutters are wider than the view, the tab opens scrolled so the page's left edge sits 20 px inside the view (centred when the page alone fits with 20 px each side); the top gutter stays in view. The view keeps that home scroll across resizes until the user or a reveal scrolls it; Fit (Ctrl+9) returns to it.

### 5.21 Two widths

**UX-WIDTHS-001** `M3.6` `[S]` The two-widths view (⇆, Ctrl+K W) shows the form twice, live, at the **same zoom**: "Narrowest · 420 px" (the form's minimum size hint width) and "Wide · 1366 px" (the ChoreBoy screen width, editable in the menu). The spike scaled the wide copy down so it looked smaller than the narrow one (`two-widths.png`); withdrawn.

**UX-WIDTHS-002** `M3.6` `[S]` If both copies do not fit side by side at the current zoom, they stack vertically (narrow above wide) and the view scrolls. Each copy has a label chip above its top-left corner.

**UX-WIDTHS-003** `M3` `[T]` Both copies share one selection frame (M3, built with the canvas). Selecting in either draws the selection in both. Neither copy changes the form's design size. Drops, moves and resizes inside the wide copy are `M9.5`.

### 5.22 Text-size and screen-scale preview

**UX-SCALE-001** `M3.6` `[S]` The **Aa ▾** popover has two choices that change the canvas only, never the file: Text size — Smaller (−15%), Normal, Larger (+25%), Largest (+50%) — and Screen scale — 100, 125, 150, 200%. The spike's unlabeled "S M L" segments are withdrawn.

**UX-SCALE-002** `M3.6` `[S]` While any preview choice is not Normal / 100%, a pill on the backdrop above the page's top-right corner reads "Previewing larger text · Reset", so a user never mistakes the preview for their saved form.

**UX-SCALE-003** `M3.6` `[S A]` While previewing, every widget whose text no longer fits (its size hint is larger than its rectangle on an axis it cannot grow) gets a dashed `ov.tab` outline, and the pill adds "· 2 widgets cut off text". Clicking the pill's count selects them (pain 12).

**UX-SCALE-004** `M3.6` `[T]` Laid-out children carry no geometry in the file at any preview setting (pain 12 test).

---

## 6. The outline

**UX-OUT-001** `M3.5` `[S]` Each row (24 px): disclosure triangle, 16 px class glyph, object name (Body), then in `fb.faint` Caption the friendly class and the visible text in quotes ("Line edit “Full name”"). Layout rows use `ov.layout` for glyph and name, spacer rows `ov.gap`. A row whose widget has a problem shows the problem glyph at its right end. Hidden widgets (`visible` false) show their name in `fb.faint`.

**UX-OUT-002** `M3.5` `[S]` The friendly class and text column hides first when the pane is narrow. Each nested level indents 12 px. A name elides at the end, and only when the name alone cannot fit, so the start of the name stays readable. Hovering an elided row shows the full row as a tooltip.

**UX-OUT-003** `M3.5` `[K]` Keyboard grammar (focus in the outline):

| Key | Action |
| --- | --- |
| Up / Down | Previous / next visible row (selects it) |
| Left / Right | Collapse, else go to parent / expand, else go to first child |
| Shift+Up / Shift+Down | Extend the selection among siblings |
| Home / End | First / last row |
| Enter | Select first child (same as the canvas) |
| Esc | Select parent |
| F2 | Rename (UX-OUT-008) |
| Tab / Shift+Tab | Nest into the previous sibling container / move out to after the parent (UX-OUT-004) |
| Alt+Up / Alt+Down | Move up / down among siblings |
| / | Quick insert after the selected row |
| Ctrl+X / C / V / D, Delete | Clipboard and delete, as on the canvas |
| Ctrl+1 … Ctrl+6, Ctrl+Shift+G, Ctrl+Shift+B | Layout commands, as on the canvas |
| Type a letter | Jump to the next row whose name starts with it (Qt default type-ahead) |

**UX-OUT-004** `M3.5` `[K T]` Tab nests the selection into the previous sibling if it is a container or layout (at its end; into a new vertical layout if the container has none); Shift+Tab moves the selection out to the position after its parent container. Both are one undo step and keep focus and selection on the moved row. When Tab has no valid target the row flashes `ov.problem` once (120 ms) and the status says why ("Nothing above to nest into").

**UX-OUT-005** `M3.5` `[S T]` Drag reparenting: dropping on the middle 50% of a container or layout row puts the item at its end (row highlighted with a 1.5 px `ov.select` outline); on the top or bottom 25% inserts before or after (2 px insertion line, 8 px hit band). While between rows, moving the pointer left or right changes the target depth, shown by the insertion line's indent (outliner convention) and the status sentence ("Into receiptRow, after printCopy").

**UX-OUT-006** `M3.5` `[T]` Grid and form items in the outline are ordered row by row; dragging a row in the outline into a grid or form uses the same next-free-cell rule as UX-AUTO-003 unless it is dropped between two rows of the same layout, in which case it takes the position between them in reading order.

**UX-OUT-007** `M3.5` `[S T]` Pages of tab widgets, stacked widgets and toolbox items appear as page rows ("Page 2 · Settings", with the page title) that reorder by drag and by Alt+Up/Down (pain 20, R3 127).

**UX-OUT-008** `M3.5` `[K T]` Rename: F2 or a double-click on the name opens an inline editor on the row with the name selected. Enter commits and keeps focus on the same row; Esc cancels; Tab commits and opens rename on the next row, Shift+Tab on the previous (so renaming ten widgets is ten names and ten Tabs). Nothing else — status messages, regeneration, the inspector, Problems updates — takes focus while renaming (pain 25).

**UX-OUT-009** `M3.5` `[S T]` Name validation is inline under the editor, in `fb.error` Caption, and Enter is refused while it shows: "Names use letters, digits and _, and can't start with a digit." / "Another widget is already called email." / "“close” would replace a method of the window. Try closeButton." Python keywords and attribute names of the form's base class are refused (LOGIC_DESIGN FB204 spirit).

**UX-OUT-010** `M3.5` `[T]` A rename updates every reference in the form (buddies, tab stops, connections, M6+ formulas) in the same undo step. From M1.4 it also offers to update `self.ui.oldName` in the window class through the shell's rename-refactor preview (LOGIC_DESIGN §2.13).

**UX-OUT-011** `M3.5` `[S]` The outline filter (Ctrl+F, ⌕) matches object names, friendly class, Qt class and visible text; ancestors of matches stay visible in `fb.faint`; Enter in the filter selects the first match; Esc clears the filter and returns focus to the tree.

**UX-OUT-012** `M3.5` `[S T]` References shown before delete: deleting a widget that something else points to (a buddy label, a connection, a promoted-class page reference, M6+ rules) opens a confirm popover anchored to the row or the canvas selection, listing each reference in words: "email is used by: the buddy of “Email:”, 1 connection (email · returnPressed → Invoice · accept)". [Delete] [Cancel]. Deleting something unreferenced happens at once, with a toast "Deleted email · Undo". Tab order membership is not a reference worth asking about.

**UX-OUT-013** `M3.5` `[S]` The outline header's + button opens the quick-insert popover, the same as `/`.

---

## 7. The inspector

### 7.1 Structure

**UX-INSP-001** `M3.1b` `[S]` Header (fixed, not scrolling): the class glyph; the object name as an inline-editable field styled as Title text (F2 or click edits; same validation as UX-OUT-009; Enter keeps focus in the field); under it, the friendly class and, in `fb.faint`, the Qt class ("Line edit · QLineEdit"); under that, a breadcrumb of ancestors ("Invoice › form layout › email") whose segments select that ancestor. The breadcrumb elides from the left with "…"; the full path is the tooltip (the spike truncates the middle segment, `empty-group.png`).

**UX-INSP-002** `M3.1b` `[S]` Tabs: **Properties**, **Behavior**, **Data**. Behavior shows a count badge when the widget has connections (M3) or logic (M6+). Data is hidden in user builds until M8 (UX-EMPTY-006). The last used tab is kept as the user changes selection.

**UX-INSP-003** `M3.1b` `[S]` Properties is a list of collapsible groups. Each group has an Overline header with a chevron; collapsed state is remembered per group across selections. Row layout: label column 104 px (96 compact), editor column the rest, 8 px between, labels in Body `fb.muted`, right-aligned editors never clip their text (no "All non fixed fields grov", `window-selected.png`).

**UX-INSP-004** `M3.1b` `[S]` Curated groups, in this order, each shown only when it has rows for the selection:

| Group | Holds (examples) |
| --- | --- |
| Content | text, placeholder, title, items, current value, check state, icon (M4.3c), tooltip |
| Input | echo mode, max length, input mask, read-only, range and step, date range, accepted characters |
| Appearance | font (M4.3b), alignment, word wrap, frame, flat, text format |
| Size | sizing words, share, min and max (section 7.3) |
| Placement | where it sits in its parent layout: row, column, spans, cell alignment, form role (label, field, spanning) |
| Layout | for a container or layout: kind, gaps, margins, column and row shares and minimums, form options |
| Accessibility | accessible name, accessible description, status tip, What's This |
| All properties | every Qt property (UX-INSP-008) |

The curated rows per class come from a registry (M3.1b) so M4 adds rows without editing shared files.

**UX-INSP-005** `M3.1b` `[S]` Every curated row shows the friendly label; its tooltip gives the Qt property name and one sentence of help. The "Qt names" toggle in the tab's ⋯ menu shows Qt names as a second line under each label for veterans; it is remembered per user.

**UX-INSP-016** `M3.1b` `[S]` A widget whose parent has a layout shows no position or geometry rows anywhere in the curated groups (the layout owns them; survey pattern 4, pain 1). All properties shows `geometry` read-only with the Caption "Set by the layout." Widgets in bare containers show X, Y, width and height in Placement.

### 7.2 Changed values and reset

**UX-INSP-006** `M3.1b` `[S T]` A property that is written in the file ("changed") has its label in Strong weight (Designer's bold, which veterans read instantly) and a 2 px `fb.accent` bar at the row's left edge. A reset button (↺, 16 px) appears on hover and on keyboard focus of the row. Reset deletes the property from the file (one undo step) and the row returns to normal weight (delighter 14, pain 2).

**UX-INSP-007** `M3.1b` `[S]` A property that is not written shows the class default in `fb.faint` as the editor's placeholder or value: numbers show the default number with no "0 means unset" trap; optional limits that have no default show "—" ("not set"). The spike's "Minimum 0 × 0" placeholders (`inspector-size.png`) read as values and recreate pain 2; withdrawn.

**UX-INSP-008** `M3.1b` `[S]` **All properties** is collapsed by default. Expanded, it lists every property grouped by declaring class (QObject, QWidget, QLineEdit…, as Designer does), with Qt names, the same editors and the same changed/reset model. Its values come from the real canvas widget (the spike shows `focusPolicy` "No focus" and `mouseTracking` checked for a line edit, `inspector-size.png`, which does not match the widget; the gate checks every row against the live widget).

**UX-INSP-009** `M4.3a` `[S]` A property whose type has no editor is shown read-only with its raw value and "Kept as is" (pain 18). Enum and flag editors commit on choice (pain 18): enums as a drop-down of friendly names with the Qt name in each item's tooltip; flags as a popover of check boxes whose collapsed text lists the chosen names ("Left, vertically centred"), never middle-elided raw strings (`top-row-selected.png` shows "Left, Leading...rtical centre").

### 7.3 Size panel

**UX-SIZE-001** `M3.6` `[S]` The Size group has, per axis, a row "Width" / "Height" with a three-segment control **Hug | Fill | Fixed** and, when Fixed is chosen, a "[ 240 ] px" field beside it. Meanings, shown as each segment's tooltip:
- **Hug**: "As big as its content needs, and no bigger." (stored as size policy Fixed on that axis)
- **Fill**: "Takes the spare room the layout gives it." (Expanding)
- **Fixed**: "Exactly this many pixels." (Fixed plus minimum = maximum = N)

**UX-SIZE-002** `M3.6` `[S T]` Default state: when the axis has no stored policy, the segment matching the class default's behaviour is drawn *outlined*, not filled, and a Caption under the control says "Default for a line edit". Clicking a segment stores it (filled segment, changed marker). Reset returns to the outlined default and deletes the lines. This replaces the spike's "nothing selected" state and the badge word "Auto" (`dark-layout.png`), so one vocabulary of three words is used everywhere.

**UX-SIZE-003** `M3.6` `[S]` Mapping of class-default policies to the outlined word: Fixed → Hug; Expanding, MinimumExpanding, Ignored → Fill; Preferred, Minimum, Maximum → Hug, with the Caption explaining the softer behaviour: "Default for a group box: hugs its content, and grows when nothing else wants the room."

**UX-SIZE-004** `M3.6` `[S]` A stored policy that is none of Hug, Fill or Fixed (for example Minimum written by Designer) shows no filled segment and the Caption "Custom: Minimum — grows, never smaller than its content. Change it in All properties, or pick a word to replace it."

**UX-SIZE-005** `M3.6` `[S]` "Share of spare room" (stretch) appears under the axis that runs along the parent layout's direction (and for grid rows/columns and splitter panes): a number field with the Caption "0 means no share. Two widgets with 1 and 2 split the spare room 1 : 2." Shown only when the parent is a box layout, grid or splitter.

**UX-SIZE-006** `M3.6` `[S]` "At least" and "At most" rows each hold "[ — ] × [ — ] px" (minimum and maximum). Empty means not set; the placeholder is "—"; typing a number writes it; clearing the field deletes the line. Fixed hides these rows for that axis.

**UX-SIZE-007** `M3.6` `[S A]` "Why is it this size?" is an always-visible paragraph at the bottom of the group in Caption on `fb.row_hover`, built from these templates. Every number comes from the live canvas widget (geometry, size hint, minimum size hint, constraints) at the current preview scale, and a test checks each number against the widget (PLAN M3.6).

| Case | Template |
| --- | --- |
| Opening line | "{w} × {h} px." |
| Fill, got room | "Width fills the room the {parent} gives it." |
| Fill, stopped by At most | "Width would fill, but stops at its maximum of {max} px." |
| Fill with share | "It gets {k} of every {total} px of spare room (share {k} of {total})." |
| Hug | "Height is what a {class} needs for its content: {hint} px." |
| Default soft, grew | "Width grew past the {hint} px it asks for, because nothing else wanted the room." |
| Squeezed | "Width is squeezed below the {hint} px it asks for, because the window is too narrow. It can't go below {min} px." |
| Fixed | "Width is fixed at {n} px." |
| Held by At least | "Height can't go below its minimum of {min} px." |
| Form label column | "This label is {label} px wide. The label column is {column} px, the width of the longest label." |
| Not in a layout | "{w} × {h} px, as stored. A layout would size it." The Hug, Fill, and Fixed segments stay disabled, with the caption "Not in a layout: its size is the rectangle in Placement." |
| Splitter pane | "When the splitter grows, this pane takes {taken} of every {total} extra px." |
| Splitter pane, no share | "When the splitter grows, this pane keeps its size." |
| Splitter pane, no share, and it still grows | "When the splitter grows, this pane takes {taken} extra px." |
| Canvas-only minimum | "The canvas shows empty layouts bigger so you can drop into them; that size isn't saved." |

`{parent}` is in words ("vertical layout", "group box Receipts"), `{class}` is the friendly class. With "Qt names" on, the Qt policy name follows in `fb.faint` parentheses.

**UX-SIZE-008** `M3.6` `[S]` The selection chip's sizing words and the Size group always agree (UX-CHIP-003): same words, same effective value.

### 7.4 Multi-select

**UX-INSP-010** `M3.1b` `[S]` Nothing selected never happens; the form selected shows the form inspector: Window (title, design size with the Caption "Drag the page's right or bottom edge to try other sizes."), Layout of the root, Tab order list (UX-OVL-006), a one-line Problems summary (UX-PROB-003) and Files ("Saves invoice.ui and ui_invoice.py in forms/").

**UX-INSP-011** `M3.1b` `[S T]` With several widgets selected the header reads "3 selected" and the Caption lists kinds ("2 line edits, 1 combo box"). Groups show only properties all of them have. A row whose values differ shows "Mixed" in italic `fb.faint`. An edit applies to all as one undo step. The Size group is complete (Hug, Fill, Fixed; the spike's multi-select offered only Hug and Fill, `wrap-menu.png`). Reset resets the property on all of them.

### 7.5 Property search

**UX-INSP-012** `M3.1b` `[S K]` A search field sits under the tab bar ("Find a property", Ctrl+F when the inspector has focus). Typing filters curated groups and All properties together, matching friendly labels, Qt names and current values; group headers of matching rows stay; matched text is highlighted with the shell's `search_match_bg`. Esc clears it. The filter persists across selection changes until cleared, with a "Filtered: echo · Clear" pill so it is never forgotten.

### 7.6 Behavior and Data tabs

**UX-INSP-013** `M3.1b` `[S T]` The Behavior tab holds a working Connections list (R3 2–7 basics): each connection is a row "When **clicked** → **Invoice** · **accept()**" in words with the Qt signature in `fb.faint`. Each row has a delete button and a context menu. The signal and slot pickers ("When", the receiver, and "More") are `M6.1`. "+ Add connection" inserts a new row at the top of the list, already selected. Pain 16: a new row is never added off-screen.

**UX-INSP-014** `M6.0` `[S]` From M6 the Behavior tab follows LOGIC_DESIGN §2.1: sections State, Checks, Events in that fixed order, with the Connections list becoming the Events list. The layout reserves this order already: the M3 Connections list sits where Events will go (bottom), so muscle memory carries over.

**UX-INSP-015** `M8.0` `[S]` From M8 the Data tab follows LOGIC_DESIGN §2.6.

---

## 8. Modes as overlays

**UX-OVL-001** `M5.6` `[S]` Tab order (F8) and Buddies (F7) are overlays: toggle buttons in the tab toolbar, not segments of a mode control (the spike's "Design | Tab order | Buddies" segmented control reads as a sticky mode). Only one overlay is open at a time; opening another closes the first. (The basic overlays ship in M3 from the spike and are refined in M5.6.)

**UX-OVL-002** `M5.6` `[S]` An open overlay shows a banner at the top of the canvas viewport over the backdrop (UX-WB-006) with its glyph, name, one instruction sentence and a [Done · Esc] button. Esc, F3, Done, or clicking the toggle again closes it. Switching tabs closes it.

**UX-OVL-003** `M5.6` `[S]` While an overlay is open, the canvas dims layout frames and hover outlines, and the overlay's own marks use their role colour. Outline and inspector stay fully usable. Structural commands (insert, delete, wrap, move) close the overlay first, then run.

**UX-OVL-004** `M5.6` `[S A]` Tab order overlay: a 16 px `ov.tab` number badge for every widget in the focus chain, placed by the chip solver (outside top-left first), never inside the widget (the spike puts badges inside fields over their content, `tab-order.png`); a 1.5 px dashed `ov.tab` flow line joining badge centres in order. A `QDialogButtonBox` is one stop with one badge (its buttons' order belongs to the box).

**UX-OVL-005** `M5.6` `[T]` Clicking widgets in the overlay assigns 1, 2, 3… from the first click; Shift+click a widget to continue numbering from it; a hover hint chip says "Click to make it 4". The banner offers "Reset to reading order", which deletes `<tabstops>`. Each click is one undo step, merged while the overlay stays open.

**UX-OVL-006** `M5.6` `[S K]` The form inspector's Tab order list mirrors the overlay: numbered rows, drag and Alt+Up/Down to reorder, "Use reading order" to reset, and the Caption "Follows reading order: top to bottom, left to right." or "Custom order. New fields join it where they sit on the form." New inputs are spliced into a custom order by reading position, never appended (pain 20).

**UX-OVL-007** `M5.6` `[S A]` Buddies overlay: each label with a buddy gets a 1.5 px `ov.buddy` link from 2 px right of the label's text box to 2 px left of the field's rectangle, with 4 px end dots. Lines never cross text (the spike's dots sit on the last letter, "Emai", "Note", `buddy.png`), and fields are not tinted. Labels without a buddy show a hollow 8 px ring in the gutter-side margin, outside the label.

**UX-OVL-008** `M5.6` `[T]` Drag from a label (or its ring) to a field to set the buddy; click a label then a field also works; drag a link's field end to empty space to clear it. "Pair labels automatically" in the banner pairs every form-layout label with the field in its row (one undo step) and reports "Paired 3 labels".

**UX-OVL-009** `M6.1` `[S]` Connections overlay (F4, Designer parity, LOGIC_DESIGN §2.7): draws connections of the selected widget only; dragging from a widget to another opens the event picker. Structure only in v1; specified in M6.0.

---

## 9. Feedback, errors and copy

### 9.1 Toasts

**UX-FEED-001** `M3.1` `[S T]` Toasts confirm actions whose result might be missed or regretted: delete, cut, wrap, unwrap, morph, remove layout, cross-form paste with broken references, form created from a table, reset of several properties. They do not appear for actions whose result is plainly visible (drop, move, rename, ordinary property edits, paste in place).

**UX-FEED-002** `M3.1` `[S]` A toast is level 2, max 480 px wide, Body text, at most one action button ("Undo", "Show") plus a close ×. One toast at a time; a new one replaces the old. It stays 6 s (8 s with an action), pauses while hovered, and never takes keyboard focus. Ctrl+Z works whether or not the toast is showing.

**UX-FEED-003** `M3.1` `[T]` A toast's Undo undoes exactly the command it announced. The toast is dismissed as soon as any later command runs, so its Undo never reaches past newer work.

### 9.2 Status bar context

**UX-FEED-004** `M3.1` `[S]` The shell status bar's editor segment (UX-SHELL-006) is the builder's narrator. Priority: gesture sentence (during a drag or resize) > overlay instruction > hover sentence > selection summary. Messages never take focus and never pop up.

**UX-FEED-005** `M3.1` `[S]` Selection summary formats: "email · Line edit · row 2 of the form layout", "receiptGroup · Group box · 2 widgets in a horizontal layout", "3 selected", "Invoice · the form · 640 × 480".

### 9.3 Timings

**UX-FEED-006** `M3.1` `[S]` The spike's perf meter ("open 118.6 ms", "edit 62.0 ms") is a development tool. It is hidden in user builds. It shows in the shell status bar's right end when the setting `form_builder.dev.show_timings` is on or `CBCS_FB_TIMINGS=1` is set, in `fb.faint`, turning `fb.warning` over the PLAN budget. Timings are always logged for the speed harness.

### 9.4 Errors in place

**UX-FEED-007** `M3.1b` `[S]` Validation errors appear next to the field that caused them (Caption, `fb.error`, under the field) and the field keeps its invalid text until fixed or Esc. No modal error dialogs in the builder, except a failed save to disk (shell standard).

**UX-FEED-008** `M3.2` `[S]` Refused gestures explain themselves in the status bar and, if the user tries the same refused gesture twice within 5 s, in a toast without actions.

### 9.5 Copy guidelines

**UX-COPY-001** `all` `[C]` US English, sentence case everywhere (menus, buttons, headers in Overline excepted). Buttons are verbs that say what happens ("Create form with 6 fields", "Remove layout", "Delete"), never "OK" for a destructive or creating action.

**UX-COPY-002** `all` `[C]` Plain words first; Qt words only where a veteran needs them (tooltips, "Qt names" lines, All properties, the XML view). No internal words on screen: no milestone or phase names, no command or node ids, no "realize", "slot" (for layouts), "item", "ui_ module" fragments, no "position 3" without saying what is there.

**UX-COPY-003** `all` `[C]` Say what happened and what to do next, in that order, in at most two sentences. Name things by what the user sees (their text), then by object name.

**UX-COPY-004** `all` `[C]` Numbers carry units; counts are 1-based; plurals are correct ("1 widget", "2 widgets").

**UX-COPY-005** `all` `[C]` No blame, no exclamation marks, no "please", no "simply" or "just". Errors say "can't", not "invalid" or "illegal".

**UX-COPY-006** `all` `[C]` Examples (spike text → required text):

| Where | Spike | Required |
| --- | --- | --- |
| Drop chip | "+ Into verticalLayout · position 3" | "Insert between Shop name and Receipts" |
| Drop chip | "New row 3" | "New row after Email" |
| Size badge | "Auto × Auto · 622 × 69" | "receiptGroup · Hug × Hug" |
| Behavior tab | "Coming in the logic phase" | (no stub in user builds; see UX-EMPTY-005) |
| Data tab | "In the logic phase this tab binds fields…" | (hidden until M8) |
| Why sentence | "Width fills the room the form layout formLayout gives it (Expanding)." | "Width fills the room the form layout gives it." (Qt name only with "Qt names" on) |
| Problems in inspector | "No problems. Save writes a clean .ui and ui_ module." | "No problems." |
| Status hint | "Drag from Insert, or press / . Click to select, Esc for the parent." | "Drag a widget from Insert, or press / to search. Esc selects the parent." |
| Files | "Not saved yet. Save writes name.ui and ui_name.py side by side." | "Saves invoice.ui and ui_invoice.py in forms/." |
| Shortcut field | placeholder "Ctrl+O" on an empty shortcut | placeholder "None" and a "Record" button |
| Remove layout | "Remove layout…" (plain text link) | a secondary button "Remove layout…" |

---

## 10. Accessibility

**UX-A11Y-001** `M3.7` `[K]` Keyboard-only paths exist for every task in the M2–M3 scope, and the keyboard script (section 12.3) completes each without the mouse: create a form from a template; insert, move, nest, wrap, unwrap, morph, delete, copy, paste and duplicate widgets; rename; edit text; set Hug/Fill/Fixed, share, minimum and maximum; change gaps and margins (inspector); change splitter sizes (inspector); zoom; preview; switch to XML and back. Reorder tab order and set buddies are `M5.6`, because those overlays are built there.

**UX-A11Y-002** `M3.1` `[S]` Focus is always visible and always distinct from selection: a 2 px `fb.accent` focus ring (HC: `focus_border_width`, 2 px) on the focused control; the focused pane shows a 2 px `fb.accent` line along its top edge; on the canvas the focused-and-selected widget gets an extra 1 px dotted `ov.select` ring outside the selection stroke. In the outline, the focused row has the focus ring in addition to the selected-row fill (the spike shows no difference between a focused and an unfocused selected row, extra capture `focus-outline.png`).

**UX-A11Y-003** `M2.2` `[S]` Start cards, Insert tiles, segmented controls, the zoom menu and chips that act as buttons are focusable with the same ring.

**UX-A11Y-004** `M3.1` `[A]` Every interactive builder control has an accessible name (the spike sets none: `setAccessibleName` appears 0 times). Icon buttons use their tooltip text without the shortcut; Insert tiles "Insert line edit"; segmented segments "Width: Hug"; the canvas view "Form canvas"; outline rows "email, line edit, Full name". A test walks the builder widget tree and fails on any focusable widget with an empty accessible name.

**UX-A11Y-005** `M3.1` `[A]` The canvas exposes the current selection to assistive technology through its accessible description ("Selected: email, line edit, row 2 of the form layout") and updates it on every selection change. Canvas widgets themselves are not exposed as live controls (they are a picture of the user's form).

**UX-A11Y-006** `M2.3` `[A]` Contrast targets: text 4.5 : 1 against its background (7 : 1 in high contrast); non-text UI (icons, control borders, focus rings, overlay strokes, chips) 3 : 1 against what they sit on. The token tables in section 2.1 meet these; a test computes every token pair used and fails below target.

**UX-A11Y-007** `M3.1` `[S]` Colour is never the only signal: layout frames carry a kind chip when selected, changed properties use weight and a bar, invalid drops use the not-allowed cursor and a sentence, problems use a glyph and text.

**UX-A11Y-008** `M3.1` `[S]` At 200% device pixel ratio every glyph, stroke and chip is crisp (painted, not scaled bitmaps), and hit areas scale with the logical pixel.

**UX-A11Y-009** `M2.2` `[K]` Tab order of the builder chrome is: tab toolbar (left to right) → outline → Insert → canvas → inspector header → inspector tabs → search → rows. Inside the canvas and outline, Tab has its builder meaning (UX-KEY-004); Alt+1…4 and the toolbar's focus jump keys let a keyboard user leave them (UX-KEY-006).

---

## 11. Pains and delighters mapped to clauses

### 11.1 The 25 ranked pains

In the tables of this section the `UX-` prefix is omitted.

Every pain is a requirement (PLAN §1). Pains whose fix is mostly engine, generator or project work still have the UX clauses listed that make the fix visible. The pain's own test from `P_user_pain_points.md` remains the acceptance test; the clauses add how it looks and feels.

| Rank | Pain | Clauses that solve it | Milestone |
| --- | --- | --- | --- |
| 1 | Widgets sit still until a layout command | PRIN-002, AUTO-001, AUTO-002, BARE-001, START-004, INSP-016, RESIZE-008, SCALE-004 | M3.2 |
| 2 | Size policy, minimum and stretch are three mysteries | SIZE-001 … SIZE-008, INSP-006, INSP-007, CHIP-003, RESIZE-002, RESIZE-003 | M3.6 |
| 3 | Paste refused inside a layout | CLIP-002, CLIP-003, CLIP-004, MOVE-002 | M3.4 |
| 4 | Nested layouts shrink to a line | EMPTY-002, EMPTY-003, DND-008, BOX-003, FRAME-001, OUT-005 | M3.2, M3.5 |
| 5 | Break layout is required and resizes siblings | WRAP-002, WRAP-003, WRAP-004, WRAP-007 | M3.3 |
| 6 | Edits in `ui_*.py` disappear | GEN-001, GEN-002, GEN-003 | M2.3 |
| 7 | Promotion stores a C++ header, draws the base class | RUN-004, M5-004 | M5.4 |
| 8 | Style sheet on the canvas differs from the app | ISO-001, ISO-002, ISO-004, M5-003 | M2.3, M5.3 |
| 9 | Icon shows in the designer, gone at run time | M5-002 | M5.2 |
| 10 | Packaged app can't find the form | RUN-005 | M2.4 |
| 11 | A plugin aborts the designer | RUN-002, RUN-003, RUN-004 | M2.5 |
| 12 | Raw pixel sizes break on font or scale change | SCALE-001 … SCALE-004, WIDTHS-001 … WIDTHS-003, INSP-016 | M3.6 |
| 13 | Modes and a dated canvas | PRIN-005, OVL-001 … OVL-003, INSP-013, section 2 | M3, M5.6 |
| 14 | Spacers stick, disagree with preview | GAP-001 … GAP-005, FRAME-002, SIZE-005, WRAP-009 | M3.3 |
| 15 | No completion of widget names | OUT-010 (rename carries to code); completion itself is M1.4 | M1.4, M3.5 |
| 16 | Signal mode hides new connections | INSP-013, EMPTY-005, OVL-009 | M3.1b, M6.1 |
| 17 | Menus and toolbars refuse dragged controls | M5-001 | M5.1 |
| 18 | Enum properties don't commit | INSP-009, FEED-007, PED-001, PED-009, PED-022 | M4.3a |
| 19 | Splitter can't nest, handle doesn't move | SPLIT-001, SPLIT-002, SPLIT-003 | M3.2, M3.3 |
| 20 | Tab order sticks; new widgets append; page reorder is a thin target | OVL-002, OVL-004 … OVL-006, PAGES-004, OUT-007, GRID-004 | M3.5, M5.6 |
| 21 | One grid drag moves untouched cells | GRIDL-001 … GRIDL-004, DND-002 | M3.2 |
| 22 | `connectSlotsByName` misses a slot | PROB-001, PROB-002 (FB codes from M6.2) | M6.2 |
| 23 | Huge forms freeze | PRIN-007, MOTION-001, FEED-006, DND-008 (cached slot geometry), section 12.5 speed evidence | M3.1, M9.4 |
| 24 | Undo writes a non-widget z-order | OUT-006 (outline order is the real child order); engine fix in M1.2 | M1.2 |
| 25 | Rename steals the keyboard | PRIN-006, OUT-008, OUT-009, INSP-001, FEED-002, FEED-004 | M3.5 |

### 11.2 Adopted delighters (the report's fifteen)

| # | Delighter | Clauses |
| --- | --- | --- |
| 1 | Drop, and it is placed | AUTO-001 … AUTO-004, DND-003, DND-004 |
| 2 | Hug, fill and fixed | SIZE-001 … SIZE-004 |
| 3 | A gap you can select | GAP-001, GAP-002 |
| 4 | Anchors drawn on the window | GAP-004 |
| 5 | Double-click opens the handler; undo removes an empty one | TEXT-001 (switch at M6.2), LOGIC_DESIGN §2.13 |
| 6 | The hierarchy can reparent | OUT-004, OUT-005 |
| 7 | Column sizes are numbers | GRIDL-006, INSP-004 (Layout group) |
| 8 | A modifier key for small steps | RESIZE-007, GAP-002, SPLIT-002 |
| 9 | Preview in another process | RUN-002, RUN-003 |
| 10 | Live canvas, same file | XML-001 … XML-005, ISO-001 |
| 11 | Rows and columns receive the next control | AUTO-003, AUTO-004 |
| 12 | A theme object for common shapes | M5-003 |
| 13 | A custom component with a real size | RUN-004, M5-004 |
| 14 | Reset that deletes the line | INSP-006, RESIZE-003, GAP-003 |
| 15 | Auto layout by default, with an escape | AUTO-001, WRAP-007 |

### 11.3 Delighters added by this spec

| Delighter | Clause | Why |
| --- | --- | --- |
| Drop beside a field to make a row | BOX-003 | Removes "drop, select both, lay out horizontally", the most common nesting chore |
| Drop into a new form row, type its label | FORML-002 | A data-entry form becomes drop → type → Enter per field, buddies set |
| Tab through renames and text edits | OUT-008, TEXT-003 | Renaming ten widgets is ten names and ten Tabs (pain 25 test, made pleasant) |
| Cut-off text warning in the text-size preview | SCALE-003 | Turns pain 12 from "looks wrong at run time" into a count you can click |
| One plain sentence for every drop | DND-004 | Non-programmers know where a widget goes before releasing it |
| Designer layout keys | WRAP-002, KEY-004 | Ctrl+1 … Ctrl+6 and Ctrl+J are a veteran's muscle memory |

### 11.4 Praised elsewhere, not adopted

| Pattern | Decision |
| --- | --- |
| Pixel placement as the saved form | Only in bare containers from older files (BARE-002), never the default path |
| A drag that writes widget margins (WPF) | Not done. Margin drags edit the *layout's* contents margins (GAP-003), which Qt stores and every layout respects |
| Absolute position inside a layout frame (Figma) | Not offered. Layout children have no position rows (INSP-016) |
| Snaplines | Not added. Layouts align by construction; bare containers snap to an 8 px grid |
| In-process live previews | Not used for user code (RUN-002). The canvas is the realizer's real widgets without user code |

---

## 12. Acceptance evidence

### 12.1 Evidence codes

| Code | What the PR provides | How the gate verifies |
| --- | --- | --- |
| `S` | Screenshots of the named state (section 12.2), in light, dark, high contrast light and high contrast dark, at 100% and 200% device pixel ratio, at the tab sizes listed | The reviewer compares against the clause text; overlays are composited as in the spike's `grab()` |
| `T` | An interaction trace: a JSON-lines event log of real mouse and key events (drag state injected through the controller seam, PLAN §2 gate 10), the selection and focus widget after each step, the command names pushed, and the final `.ui` diff; then undo of every step back to the original bytes | The trace replays in CI; the reviewer reads the XML diff and the command names |
| `K` | A keyboard-only script (section 12.3): key sequence plus assertions, with no mouse events at all | CI runs it; a mouse event in the log fails it |
| `A` | An automated assertion in the test suite | CI result plus the test name in the PR |
| `C` | The copy strings touched, listed in the PR | The reviewer checks them against section 9.5 |
| `P` | A persona walkthrough record (section 12.6) | The reviewer reads step counts and confusion points |

The O-UX gate also needs a launched-build screenshot sequence from the lab Linux host (PLAN §2a) for any clause marked `S` that involves drag and drop, because offscreen grabs composite overlays differently from a real compositor.

### 12.2 Screenshot tour (state names)

Tab sizes: **L** = 1440 × 860 tab, **C** = 1080 × 600 tab inside the CBCS shell at 1366 × 768 (the ChoreBoy case), **N** = 840 × 560 tab. Unless marked, a state is required at L and C.

| State | Shows | Clauses |
| --- | --- | --- |
| `shell-form-tab` | A form tab inside CBCS with the project tree and Problems panel | SHELL-001 … 006, WB-001, WB-003 |
| `shell-form-menu` | The Form menu open | SHELL-004 |
| `xml-view`, `xml-error` | XML view; invalid XML on switching back | XML-001 … 004 |
| `generated-banner` | `ui_invoice.py` open | GEN-001 |
| `problems-row` | A form problem in Problems, and the widget badge | PROB-001, PROB-004 |
| `pyside2-ui` | `.ui` as text on PySide2 | PS2-001 |
| `start`, `start-invalid-name`, `start-narrow` (N) | New form tab | START-001 … 006 |
| `from-table` | Build from a table | TABLE-001 |
| `empty-form` | New blank form | EMPTY-001 |
| `empty-group` | An empty group box nested in a row | EMPTY-002, CHIP-001 |
| `select-top-row` | The first field of a form selected (the spike's chip overlap case) | SEL-008, CHIP-001 … 004 |
| `select-container` | A group box with a layout selected | CHIP-003, GAP-001, FRAME-001 |
| `select-layout-root` | The root layout selected: margins, anchors | GAP-001, GAP-004 |
| `select-multi` | Three widgets selected, inspector in multi mode | SEL-002, INSP-011 |
| `hover` | Hover over a nested widget | HOV-001, HOV-002 |
| `drag-box`, `drag-box-beside` | Insertion line; cross-axis drop making a row | BOX-001, BOX-003, DND-003, DND-004 |
| `drag-grid-empty`, `drag-grid-edge`, `drag-grid-newrow`, `drag-grid-span-refused` | Grid targets | GRIDL-001 … 004, DND-005 |
| `drag-form-field`, `drag-form-newrow`, `form-new-row-label-edit` | Form targets and the label editor after a drop | FORML-001, FORML-002 |
| `drag-splitter`, `splitter-handle-drag` | Splitter target and handle drag | SPLIT-001, SPLIT-002 |
| `drag-tab-plus`, `stack-switcher` | Page containers | PAGES-001 … 003 |
| `drag-bare-empty`, `bare-legacy` | Bare containers; No layout marker | BARE-001, BARE-002, FRAME-003 |
| `outline-drag-depth` | Outline drag between rows with indent | OUT-005 |
| `outline-rename`, `outline-rename-error` | Rename in place; invalid name | OUT-008, OUT-009 |
| `delete-references` | Delete confirm listing references | OUT-012 |
| `gap-drag` | Gap bar dragged with live number | GAP-002 |
| `resize-fixed` | Handle drag readout | RESIZE-001, RESIZE-004 |
| `text-edit-inplace` | In-place editor on a button | TEXT-002 |
| `wrap-popover`, `wrap-toast` | Wrap popover; toast after wrap | WRAP-001, WRAP-003, FEED-002 |
| `remove-layout-confirm` | Confirm popover | WRAP-007 |
| `inspector-size-default`, `inspector-size-fixed`, `inspector-size-custom` | Size group states with the why paragraph | SIZE-001 … 007 |
| `inspector-changed` | Changed rows, reset button on focus | INSP-006, INSP-007 |
| `inspector-all-props`, `inspector-search` | All properties expanded; search filtering | INSP-008, INSP-012 |
| `inspector-form` | Form selected | INSP-010 |
| `inspector-behavior` | Connections list with a new row in edit state | INSP-013, EMPTY-005 |
| `overlay-tab-order`, `overlay-buddies` | Overlays | OVL-001 … 008 |
| `two-widths` (L only) | Two widths side by side and stacked | WIDTHS-001, WIDTHS-002 |
| `preview-larger-text` | Text-size preview with cut-off warnings | SCALE-001 … 003 |
| `zoom-50`, `zoom-200` | Overlay sizes constant | ZOOM-002, ZOOM-004 |
| `responsive-rail` (N), `responsive-drawer` (N), `responsive-short` (1080 × 420) | Collapsed panes and drawers | RESP-001 … 006 |
| `focus-outline`, `focus-canvas`, `focus-inspector` | Focus rings | A11Y-002, A11Y-003 |
| `preview-crash` | Preview stopped toast and Problems row | RUN-003 |

**M4 states** (added in v2). Each is required at L and C, in light, dark and both high contrast themes, and the inspector states also at the minimum inspector width (236 px content).

| State | Shows | Clauses |
| --- | --- | --- |
| `insert-icons`, `insert-list` (C) | Insert pane with Recently used and all categories, each view | CAT-003 … 006, ICON-005 |
| `insert-search-synonym` | "dropdown" typed, Combo box first with “dropdown” caption | CAT-007, CAT-008 |
| `insert-search-empty` | No match | CAT-009 |
| `insert-window-kinds` | "wizard" typed: widget results then "Wizard · new form" | CAT-015 |
| `quick-insert-recent` | `/` with an empty query, Recently used first | CAT-013 |
| `insert-refused-wizard-page` | Wizard page dragged over a group box | CAT-014 |
| `pages-menu` | Context menu with Pages ▸ open on a tab page | CONT-002 |
| `page-delete-confirm` | Delete page popover listing widgets | CONT-004 |
| `page-shown-vs-start` | Tab widget showing page 2, starting on page 1, status sentence | CONT-006, CONT-007 |
| `pages-empty` | Tab widget with no pages | CONT-009 |
| `scroll-area-scrolled` | Scroll area scrolled to a selected widget at the bottom | CONT-010 |
| `mdi-windows` | MDI area with two windows and its switcher | CONT-011 |
| `dock-bands` (main window) | Dock widget dragged: four side bands, Left hot | CONT-012 |
| `wizard-canvas` | Wizard with step switcher; inspector step title rows | CONT-013 |
| `stand-ins` | OpenGL widget and Qt Quick view stand-ins | CONT-017 |
| `inspector-pages` (236 px) | Pages group of a tab widget | CONT-019, PED-044 |
| `inspector-min-width-all` (236 px) | A line edit, a label, a spin box and a date edit selected in turn: every row unclipped, stacked rows where required | PED-002 |
| `popover-flags`, `popover-size-policy`, `popover-date`, `popover-locale` | Each popover open from its row | PED-003, PED-023, PED-026, PED-028, PED-029 |
| `enum-unknown` | An enum value from a newer Qt shown as kept | PED-022 |
| `keyseq-recording`, `keyseq-clash` | Recorder active; clash warning | PED-027 |
| `text-translation` | Translation disclosure open, "Not translated" tag on another row | PED-041 |
| `rich-text`, `rich-text-source` | Rich text popover, both segments | PED-042 |
| `stringlist-popover` | List editor with 5 rows, one being dragged | PED-043, PED-044 |
| `custom-props`, `custom-prop-add-error` | Custom properties block; a refused name | PED-060, PED-061 |
| `all-props-sorted` | Sort A–Z on | PED-064 |
| `font-popover` (236 px) | Font popover with More open | PED-080 |
| `colour-popover`, `gradient-popover`, `palette-popover`, `palette-role-brush` | The visual editors | PED-081 … 085 |
| `picture-picker`, `icon-states`, `picture-missing` | Picker with a resource grid; icon states; a missing file | PED-100 … 104 |
| `items-combo`, `items-list-details`, `items-tree`, `items-table`, `items-model-view` | Item editors; the model-view status sentence | ITEM-001 … 008 |

### 12.3 Keyboard scripts

Each script starts with focus in the form tab and uses only keys. The PR runs the scripts that touch its clauses.

- **K1 Create and fill a data-entry form.** File > New Form… (menu by keyboard), type a name, arrow to "Data entry form", Enter. Assert: Workbench open, first input selected, canvas focused. Then `/`, type "date", Enter: a date field is inserted as a new form row with its label editor open; type "Issued", Enter. Assert the row, the buddy and that focus is on the canvas.
- **K2 Structure.** Select two sibling fields (Down, Shift+Down), Ctrl+1: wrapped in a horizontal layout; Ctrl+Shift+B: unwrapped; Ctrl+Shift+G, 7: wrapped in a group box; Esc: the group's layout is selected; Esc: the group; Alt+Up: moved up one place. Undo all: original bytes.
- **K3 Clipboard.** Select a field, Ctrl+C, Ctrl+V: pasted after it and selected; Ctrl+D: duplicated; Delete on a referenced field: the confirm opens; Esc: nothing deleted; Delete again, Enter on [Delete]: deleted, toast shown, focus unchanged.
- **K4 Rename ten.** Alt+1, F2, type a name, Tab, … ten times. Assert after each step: the focus widget is the rename editor or the outline, never anything else (pain 25).
- **K5 Sizing.** Alt+4, move to Size, set Width Fill, Share 1, Height Fixed 120, At least width 200; Reset each; assert the file has none of those lines after the resets. Ctrl+Shift+Right twice: Fixed width +16.
- **K6 Overlays.** F8: tab-order overlay; Esc: closed. In the form inspector, reorder the tab list with Alt+Down; "Use reading order". F7, then use the inspector Buddy field to pair a label; Esc.
- **K7 Text.** Select a button, Enter, type, Tab (next text widget's editor opens), type, Enter. Undo twice: both texts restored.
- **K8 Views.** Ctrl+9 fit, Ctrl+= twice, Ctrl+0; Ctrl+Shift+V to XML, edit a title, Ctrl+Shift+V back: the title changed in one undo step; Ctrl+Shift+R: preview opens; Esc closes it; F5: runs the project.

**M4 scripts** (added in v2). Same rules as K1–K8: keys only, start with focus in the form tab, and every script ends with Undo back to the original bytes unless it says otherwise. The lane named after each script owns its test; M4.5 runs them all together.

- **K9 Insert by words** (`M4.1`). Open a form-layout form, select its last field. Alt+2; type "dropdown": focus moves to the filter and Combo box is the first result with “dropdown” beside it. Enter: a combo box is inserted as a new form row and the label editor opens; type "Size", Enter: focus is back on the Insert result list. Esc: the filter clears and focus stays in Insert; Recently used shows Combo box first. Ctrl+Down twice, Enter: the first entry of that category is inserted after the combo. Esc (filter empty): focus returns to the canvas. Press `/`: the quick-insert list starts with Recently used; type "tabs", Enter: a tab widget with two pages is inserted and focus returns to the canvas. Assert after each insert: one undo step, named "Insert …". Undo four times: original bytes.
- **K10 Pages** (`M4.2`). Ctrl+R, "tabWidget", Enter. Shift+F10, open Pages, "Insert page after": a third page is shown and selected, its title editor open; type "Printing", Enter. Ctrl+PgUp: page 2 shown; the status bar says it still starts on page 1; the file has not changed (dirty state unchanged). Shift+F10, Pages, "Start on this page": `currentIndex` is 1 in the XML. Alt+1, Down to the "Printing" page row, Alt+Up: it moves before page 2. Delete on a page that has a widget: the confirm opens; Esc: nothing deleted; Delete, Enter on [Delete page]: deleted, toast shown, focus still in the outline. Undo five times: original bytes.
- **K11 Choices and numbers** (`M4.3a`). Select a line edit. Alt+4, Ctrl+F, type "echo": Echo mode is the only curated row; Tab to it, Alt+Down, choose "Password", Enter. Esc clears the search. Ctrl+S, close the tab, reopen the form, select the same line edit: Echo mode reads "Password" in Strong (pain 18). Tab to Maximum length, type 40, Enter, Up three times: 43, and Undo once restores the value from before the visit (one visit is one step); Redo. Tab away and back, Up once: 44; Undo once: 43 (a second visit is its own step). Select a label, open All properties, reach Text interaction, Enter: the flags popover opens; Space on "Select with mouse", Esc: nothing changed; Enter, Space, Enter: changed, one step. Select a date edit: Date row, type "12/31/2026", Enter; Alt+Down, PageDown, Enter: January 31, 2027 written. Select a key sequence edit: Record, press Ctrl+Shift+P: "Ctrl+Shift+P" written; Record, Esc: unchanged. Undo all: original bytes.
- **K12 Text, translations and custom properties** (`M4.3d`). Select a label; Alt+4; in Text type "Total:", Enter. Tab to "Translation ▸", Enter: it opens; Space on "Translate this text": the XML gains `notr="true"` and the row's caption says "Not translated"; Tab to "Note for the translator", type "Shown on receipts", Enter. End of All properties: Tab to "+ Add custom property", Enter, type "requiredRole", Tab, choose "Text", Enter: the row appears and its editor has focus; type "manager", Enter: the XML has `<property name="requiredRole" stdset="0">`. Type an invalid name in a second add ("2nd"): the refusal shows and Enter does nothing; Esc. Open the Text popover of a rich label, Formatted, select a word, Ctrl+B, Done: the HTML has bold; run the same steps twice and compare bytes. Undo all: original bytes.
- **K13 Font, colour and palette** (`M4.3b`). Select a label; Font row, Enter: the popover opens with focus on Family; type "Sans", Enter on the first match; Tab to Size, Up twice; Tab to Bold, Space; Done: one undo step "Change font of …", the summary lists only the parts set. Palette row, Enter; Down to "Window text", Enter: the brush editor opens; Tab to Hex, type "#1A7F37", Enter; Esc: back to the palette list; Esc: closed and reverted; repeat and press Done: kept, one step. Undo all: original bytes.
- **K14 Items** (`M4.4`). Select a combo box; Enter: the item editor opens with focus in its first row; type "Small", Enter, "Medium", Enter, "Large", Enter, Enter: closed, three items, one undo step "Edit items of …", focus back on the canvas. Enter; Down; Alt+Up: "Medium" first; Esc: the order is back to Small, Medium, Large and no step was added. Select a tree widget; Enter; type "Fruit", Enter, "Apple", Tab: Apple is under Fruit; Done. Select a list view; Enter: no popover, the status sentence of UX-ITEM-008. Undo all: original bytes.
- **K15 Pictures** (`M4.3c`). In a form that includes a `.qrc`, select a push button; Icon row, Enter; type "save" in the search; arrows to the first match, Enter: icon written as a resource path, one step. Open again, "Other states ▸", pick a Disabled picture; Esc: reverted. Undo all: original bytes.

### 12.4 Interaction traces

A trace is a JSON-lines file with one object per step: `{"t": ms, "event": "press|move|release|key|wheel", "pos": [x, y] or null, "key": "Ctrl+Shift+G" or null, "selection": [object names], "focus": "<objectName of focus widget>", "commands": ["Wrap in group box"], "status": "<status sentence>"}`, followed by the final XML diff and an undo-all check that compares bytes with the original. Traces are produced by the interaction-test harness, not by hand.

### 12.5 Automated checks the gate expects

| Check | Clauses |
| --- | --- |
| Chip and badge rectangles never intersect content, in every tour state | CHIP-001, CHIP-002, OVL-004, OVL-007, A11Y-007 |
| Every handle, gap bar and list insertion target meets the minimum hit area at 50%, 100% and 200% zoom | GRID-004, GAP-005, ZOOM-002 |
| Canvas pixel isolation under all five shell themes | ISO-001, ISO-002 |
| Token contrast pairs | TOK-003, A11Y-006 |
| Every focusable builder widget has an accessible name | A11Y-004 |
| Shortcut table has no collisions with the shell or window-manager keys | KEY-001, KEY-002 |
| "Why is it this size?" numbers equal the live widget's geometry and hints | SIZE-007 |
| The focus widget does not change during save, generation, toasts, Problems updates and renames | PRIN-006, OUT-008, FEED-002 |
| Edit-path speed within PLAN budgets, recorded with machine load | PRIN-007 |
| No hex colour literals outside `qtside/theme/` | TOK-001 |
| No user-visible string contains a milestone name, "phase", or an internal id (string table scan, development stubs excepted) | COPY-002, EMPTY-006 |
| Every catalog entry inserts a fragment that `QUiLoader` loads, that our generator and `uic` build into the same tree, and that saves twice to the same bytes | CAT-001, CAT-002 |
| Insert search returns the expected first result for every pair in the UX-CAT-007 table | CAT-007 |
| Every catalog glyph is non-blank and differs from every other entry's glyph | ICON-005 |
| No inspector row clips or scrolls sideways at 236, 264 and 420 px content width, for every editor of the reference form | PED-002 |
| Every ui4 value class has a registered editor other than the raw one, except the two deferred or kept rows of UX-PED-001 | PED-001 |
| A popover session is one undo step; Esc leaves the document bytes and the undo stack exactly as before it opened; focus returns to the row | PED-003, PED-004, ITEM-007 |
| The wheel over an unfocused field changes nothing | PED-005 |
| Rich text and gradients written on macOS and on Linux, under `C` and `de_DE`, are the same bytes | PED-042, PED-084 |
| Echo mode set, saved, reopened: still Password; an uneditable property is byte-identical after save (P-18) | PED-009 |
| After realizing a form with an OpenGL widget and a Qt Quick view, no GL context or QML engine exists | CONT-017 |
| Each page container writes its title where its loader reads it; a toolbox insert never writes `title` | CONT-001 |

### 12.6 Persona walkthroughs

M3.7 runs two walkthroughs on a launched build and records step counts and every hesitation:

- **Shop owner, never used a form builder.** Make a "Customer" form with name, phone, email and notes, and Save and Cancel buttons; make Notes grow with the window; put phone and email side by side; preview with larger text; save and run. Pass: finished without the manual, no dialog dismissed by guessing, no step that needed Undo to escape.
- **Qt Designer veteran.** Open a FreeCAD corpus form, select a nested layout, morph it to a grid with Ctrl+5, fix a buddy, reorder tab order, set a splitter's sizes, check XML. Pass: no Designer habit is blocked without an on-screen alternative named at that moment.

M4.5 runs one walkthrough on a launched build, after every M4 lane has merged, and records step counts and every hesitation:

- **Shop owner, M4 tasks.** Starting from a blank dialog, build a "Shop settings" form: a tab widget with the tabs "General" and "Printing" (rename the two default tabs; add a third "Extras" and then delete it); on General, a shop name field, a currency drop-down with USD, CAD and EUR, an opening date, an "Open on Sundays" tick box and a number of tills (1 to 9); on Printing, a receipt note with several lines, a bigger bold font for the receipt header label, a dark green header colour, a logo picture from the project's resources, and copies (1 to 5); make the currency drop-down start on CAD; set Echo mode of a PIN field to Password; save, reopen and preview. The owner searches with their own words ("dropdown", "tick box", "number", "date", "picture", "tabs"). **Pass:** every widget found by the first or second word tried; no "Kept as is" row met on any property touched; no popover closed by guessing; no step that needed Undo to escape; reopen shows every value set. **Record:** steps per task, every search word tried and its first result, every time Esc or Undo was used, and every sentence that confused.

The veteran's M4 checks are K9–K15 plus three spot checks the reviewer does by hand on a FreeCAD corpus form: add a dynamic property and see `setProperty` in `ui_*.py`; edit a palette role and compare with Designer's resave; reorder tree widget columns.

---

## 13. Later milestones: structure and key decisions

Section 13.1 is the full M4 specification (version 2). Section 13.2 fixes the decisions M2–M4 must leave room for; it will be expanded into full clauses before M5's first brief.

### 13.1 M4: widgets, containers and properties

Version 2 (work package M4.0, 2026-10-28). Binding for M4. It replaces the four short decisions that stood here in version 1:

- **UX-M4-001** Withdrawn in v2. Replaced by the CAT clauses (13.1.2) and UX-ICON-005.
- **UX-M4-002** Withdrawn in v2. Replaced by the CONT clauses (13.1.3). One change: a scroll area is drawn at its real size and scrolls on the canvas; its content is not expanded (UX-CONT-010, UX-PRIN-001).
- **UX-M4-003** Withdrawn in v2. Replaced by the PED clauses (13.1.4).
- **UX-M4-004** Withdrawn in v2. Replaced by the ITEM clauses (13.1.5).

The lane split, owned files and parity rows are in `PLAN.md` (M4 table and "M4 lanes"). Every clause names the lane that builds it. Copy in quotes is the exact on-screen text; `{name}` marks a value filled in at run time.

#### 13.1.1 Rules every M4 clause shares

**UX-TOK-005** `M4.0s, M4.2` `[S A]` New builder tokens for M4. They live in `qtside/theme/` like every builder colour (UX-TOK-001). M4.0s adds the `fb.*` chrome tokens; M4.2 adds the `ov.*` form-surface tokens it draws. Form-surface tokens (drawn on the canvas) are the same in light and dark chrome, like UX-TOK-003.

| Token | Source or light | Dark | HC light | HC dark | Use |
| --- | --- | --- | --- | --- | --- |
| `fb.tile_hover` | alias `fb.row_hover` | alias | alias | alias | Insert tile and list-row hover |
| `fb.tile_current` | alias `fb.row_selected` | alias | alias | alias | Current Insert tile, current list-editor row |
| `fb.glyph` | shell `icon_primary` | shell | shell | shell | Catalog glyphs (UX-ICON-005) |
| `fb.match` | shell `search_match_bg` | shell | shell | shell | Matched letters in Insert search, property search, item filter |
| `fb.swatch_border` | alias `fb.border` | alias `fb.border` | `#000000` | `#FFFFFF` | 1 px border of every colour swatch and thumbnail |
| `fb.checker_a` / `fb.checker_b` | `#FFFFFF` / `#D3D8DF` | `#3C434A` / `#262C33` | `#FFFFFF` / `#000000` | `#000000` / `#FFFFFF` | 4 px checkerboard under transparent colours and images |
| `fb.handle` | `fb.panel` fill, 1.5 px `fb.text` border | same | `#FFFFFF`, 2 px `#000000` | `#000000`, 2 px `#FFFFFF` | Gradient stops, colour-square cursor |
| `fb.handle_current` | 2 px `fb.accent` border | same | 2 px `#0000C0` | 2 px `#7CB7FF` | Selected gradient stop |
| `ov.stand_in_fill` / `ov.stand_in_line` / `ov.stand_in_text` | `#F4F4F4` / `#8A8A8A` dashed 1 px / `#3C3C3C` | same | `#FFFFFF` / `#000000` solid 2 px / `#000000` | same as HC light | Canvas stand-ins (UX-CONT-017). Form surface, so not chrome-dependent |
| `ov.dock_band` | `ov.drop_fill` with a 1 px dashed `ov.select` edge | same | `#0000C0` at 15% with a 2 px edge | same | Dock-side drop bands (UX-CONT-012) |

**UX-M4-005** `all M4` `[C]` Copy for M4 follows section 9.5. In addition: on-screen text never contains a lane or milestone id, an engine command name, `stdset`, `notr`, `iconset`, `cstring` or any other ui4 element name. Those words may appear only in the Qt-name line (UX-INSP-005), in All properties with "Qt names" on, and in the XML view.

**UX-M4-006** `all M4` `[T]` Undo names. Every M4 command and session has a plain name, used by Edit > Undo ("Undo Insert combo box") and by the toast's Undo. The table in 13.1.6 lists them. A popover session or an item-editor session is one undo step (UX-PED-004, UX-ITEM-007).

**UX-M4-007** `all M4` `[A]` Speed. Every M4 edit path stays inside the PLAN budgets: one keystroke in Insert search ≤ 16 ms with the whole catalog; opening any popover ≤ 50 ms; each live change from a popover (drag in a colour square, a gradient stop, a font size step) ≤ 16 ms on the 300-widget reference form; opening the item editor on a 500-item list ≤ 50 ms and each keystroke in it ≤ 16 ms. The speed rows are added to the harness by M4.5; each lane measures its own path with a local script and reports CPU p50 and p95.

#### 13.1.2 The Insert catalog (CAT)

**UX-CAT-001** `M4.1` `[A]` One catalog. Every insertable class has exactly one catalog entry with: friendly name, Qt class, category, default object name, default content, one-sentence description, synonyms and glyph. The Insert pane, quick insert (`/`), the outline's friendly-class column, canvas chips and status sentences, the inspector header and the "Change to" menu read friendly names from the catalog. No other table of friendly class names remains (today there are three: `qtside/inspector/words.py`, `qtside/canvas/core/words.py`, `qtside/canvas/core/palette.py`, and they disagree: "List" against "List widget"). A class that is not in the catalog (a custom or unknown class) gets a friendly name derived from its class name, as `class_words` does today. Catalog modules import no Qt, so the canvas core can build a fragment without Qt (dune file role, not a test).

**UX-CAT-002** `M4.1` `[S A]` Categories, in this order, and their entries in this order. "Content" is what one insert writes beyond the class and the object name. Every container gets a vertical layout (UX-AUTO-001). Default object names follow Designer (`lineEdit`, `pushButton`, `tabWidget`), with the suffix rule for repeats (`lineEdit_2`). Default texts are plain words, not Designer's (`Button`, not `PushButton`).

| Category | Friendly name | Qt class | Content | Description (tooltip sentence) |
| --- | --- | --- | --- | --- |
| Layouts and spacers | Vertical layout | `QWidget` + `QVBoxLayout` | name `verticalLayoutWidget` | Stacks widgets from top to bottom. |
| | Horizontal layout | `QWidget` + `QHBoxLayout` | `horizontalLayoutWidget` | Puts widgets side by side. |
| | Grid layout | `QWidget` + `QGridLayout` | `gridLayoutWidget` | Rows and columns, like a table. |
| | Form layout | `QWidget` + `QFormLayout` | `formLayoutWidget` | Labels on the left, fields on the right. |
| | Horizontal splitter | `QSplitter` | orientation Horizontal, no panes | Side-by-side panes the user can resize. |
| | Vertical splitter | `QSplitter` | orientation Vertical, no panes | Stacked panes the user can resize. |
| | Horizontal spacer | spacer | Horizontal, Expanding, 40 × 20 | Empty space that pushes its neighbours apart. |
| | Vertical spacer | spacer | Vertical, Expanding, 20 × 40 | Empty space that pushes its neighbours up or down. |
| Text and numbers | Line edit | `QLineEdit` | — | One line of text the user can type. |
| | Text edit | `QTextEdit` | — | Several lines of text, with formatting. |
| | Plain text edit | `QPlainTextEdit` | — | Several lines of plain text, such as notes. |
| | Spin box | `QSpinBox` | — | A whole number with up and down arrows. |
| | Double spin box | `QDoubleSpinBox` | — | A number with decimals, such as a price. |
| | Horizontal slider | `QSlider` | orientation Horizontal | Pick a number by dragging a handle. |
| | Vertical slider | `QSlider` | orientation Vertical | Pick a number by dragging a handle up or down. |
| | Dial | `QDial` | — | Pick a number by turning a knob. |
| | Horizontal scroll bar | `QScrollBar` | orientation Horizontal | Scrolls something your code draws. |
| | Vertical scroll bar | `QScrollBar` | orientation Vertical | Scrolls something your code draws. |
| | Key sequence edit | `QKeySequenceEdit` | — | Records a keyboard shortcut the user presses. |
| Choices | Combo box | `QComboBox` | — | Pick one item from a drop-down list. |
| | Font combo box | `QFontComboBox` | — | Pick one of the fonts on the computer. |
| | Check box | `QCheckBox` | text "Check box" | On or off, with a label. |
| | Radio button | `QRadioButton` | text "Radio button" | Pick one of several options. |
| Buttons | Push button | `QPushButton` | text "Button" | Runs an action when clicked. |
| | Tool button | `QToolButton` | text "…" | A small button, often with only an icon. |
| | Command link | `QCommandLinkButton` | text "Command link" | A large button with a title and a description. |
| | Button box | `QDialogButtonBox` | standard buttons OK and Cancel | OK, Cancel and other standard buttons, in the order the desktop expects. |
| Dates and times | Date edit | `QDateEdit` | — | A date the user types or picks. |
| | Time edit | `QTimeEdit` | — | A time of day. |
| | Date and time edit | `QDateTimeEdit` | — | A date with a time. |
| | Calendar | `QCalendarWidget` | — | A month grid to pick a day. |
| Lists and tables | List widget | `QListWidget` | — | A list of rows you type here. |
| | Tree widget | `QTreeWidget` | one column, header "Name" | Rows that fold open, typed here. |
| | Table widget | `QTableWidget` | — | A grid of cells you type here. |
| | List view | `QListView` | — | A list your code fills from a model. |
| | Tree view | `QTreeView` | — | A tree your code fills from a model. |
| | Table view | `QTableView` | — | A table your code fills from a model. |
| | Column view | `QColumnView` | — | Columns that drill down, filled by your code. |
| | Undo view | `QUndoView` | — | Shows the steps of an undo stack from your code. |
| Containers | Group box | `QGroupBox` | title "Group box", vertical layout | A titled frame around related widgets. |
| | Frame | `QFrame` | Styled panel, Raised, vertical layout | A plain border around a group of widgets. |
| | Widget | `QWidget` | vertical layout | An empty area that holds a layout. |
| | Tab widget | `QTabWidget` | pages `tab`, `tab_2`, titles "Tab 1", "Tab 2", each with a vertical layout | Pages the user switches with tabs. |
| | Toolbox | `QToolBox` | pages `page`, `page_2`, labels "Page 1", "Page 2", vertical layouts | Pages stacked like drawers; one is open at a time. |
| | Stacked widget | `QStackedWidget` | pages `page`, `page_2`, vertical layouts | Pages your code switches; one shows at a time. |
| | Scroll area | `QScrollArea` | content follows the area's size; contents `scrollAreaWidgetContents` with a vertical layout | Scrolls content that is bigger than the space. |
| | Wizard | `QWizard` | pages `wizardPage`, `wizardPage_2`, titles "Step 1", "Step 2", vertical layouts | Steps with Back and Next buttons. |
| | Wizard page | `QWizardPage` | title "Step {n}", vertical layout | One step of a wizard. Goes only into a wizard. |
| | MDI area | `QMdiArea` | no windows | Several small windows inside one area. |
| | Dock widget | `QDockWidget` | contents `dockWidgetContents` with a vertical layout | A panel that docks to a side of a main window. |
| Display | Label | `QLabel` | text "Label" | Text or a picture. |
| | Text browser | `QTextBrowser` | — | Formatted text with links, read only. |
| | Horizontal line | `Line` | orientation Horizontal | A thin line that separates groups. |
| | Vertical line | `Line` | orientation Vertical | A thin upright line that separates groups. |
| | Progress bar | `QProgressBar` | value 24 | Shows how far a task has got. |
| | LCD number | `QLCDNumber` | — | Digits in a calculator-style display. |
| | Graphics view | `QGraphicsView` | — | A drawing surface your code fills. |
| | OpenGL widget | `QOpenGLWidget` | — | 3D drawing from your code. The canvas shows a placeholder. |
| | Qt Quick view | `QQuickWidget` | — | A Qt Quick scene from your code. The canvas shows a placeholder. |
| FreeCAD | Quantity spin box, Input field, File chooser, Color button, URL label, Integer spin box, Double spin box (FreeCAD) | `Gui::QuantitySpinBox`, `Gui::InputField`, `Gui::FileChooser`, `Gui::ColorButton`, `Gui::UrlLabel`, `Gui::IntSpinBox`, `Gui::DoubleSpinBox` | a `customwidget` declaration with the base class and header FreeCAD's own forms use | One sentence each, ending "Needs FreeCAD's window at run time." |
| Your widgets | one tile per class in this form's custom widget declarations | the declared class | the declaration | "Your class {class}, based on {base}." |

The FreeCAD entries' base classes and headers are taken from FreeCAD's own `.ui` files on the development machine (the classes FreeCAD forms use most: Quantity spin box 75 uses, Input field 27). Preference variants (`Gui::Pref*`) are not listed; they still open, round-trip and draw as their base class.

**UX-CAT-003** `M4.1` `[S]` The Insert pane, top to bottom: the header ("INSERT", ⌕ search, ⋯ menu), the filter field (placeholder "Search widgets"), "RECENTLY USED" (UX-CAT-006), then the categories, then "Saved pieces" (UX-CLIP-006). The ⋯ menu holds "Show as icons", "Show as list" (a radio pair), "Expand all", "Collapse all" and "Clear recently used". Nothing else is in the header.

**UX-CAT-004** `M4.1` `[S]` Two views (R3 133). **Icons**: a grid of 64 × 60 px tiles, the 20 px glyph centred 8 px from the top, the friendly name under it in Caption, centred, at most two lines, elided at the end, with the full name in the tooltip. **List**: 24 px rows, a 16 px glyph, the friendly name in Body, the description in Caption `fb.faint` after it when the row has room for at least 12 more characters. The default is Icons when the left pane is at least 216 px wide and List below that (UX-RESP-002), as many columns as fit. "Show as icons" or "Show as list" overrides the default, per user. Search results always use List (UX-CAT-008). Tiles and rows: hover `fb.tile_hover`, current `fb.tile_current`, keyboard focus a 2 px `fb.accent` ring (UX-A11Y-002). A tile never shows a scroll bar inside itself; the pane scrolls.

**UX-CAT-005** `M4.1` `[S]` Each category has a 24 px header: chevron, the category name in Overline (`fb.muted`), and the entry count in `fb.faint` ("CONTAINERS 11"). Click or Enter toggles it; Left collapses and Right expands when the header has focus. Collapsed state is kept per user. FreeCAD starts collapsed. While the filter has text, every category is shown expanded and the remembered state is untouched. "Your widgets" is absent when the form declares no custom widget.

**UX-CAT-006** `M4.1` `[S T]` "RECENTLY USED" shows up to 6 entries, most recent first, as tiles or rows in the current view. An entry joins when it is inserted from Insert (click, Enter, drag) or from quick insert, and moves to the front when used again. The list is per user, across forms and projects, stored in the settings under `form_builder.insert.recent` (catalog keys, never object names). It is hidden while it is empty and while the filter has text. "Clear recently used" empties it at once with no confirm (it is a convenience, not work).

**UX-CAT-007** `M4.1` `[A]` Matching ignores case, spaces, hyphens and a leading Q. Each entry gets its best rank: (1) the friendly name equals the query; (2) a synonym equals the query; (3) a whole word of the friendly name equals the query ("tab" finds Tab widget); (4) the friendly name starts with the query; (5) a word of the friendly name starts with the query; (6) a synonym starts with the query; (7) the Qt class starts with the query; (8) the friendly name or Qt class contains the query; (9) a word of the description starts with the query. Ties go to category order, then catalog order, so a Qt widget always beats a FreeCAD widget at the same rank ("integer" finds Spin box). A word gets a synonym only on its lead entry and on siblings listed after it in the same category. Synonyms (catalog data; the lane may add):

| Query words | Lead result (and others it also finds) |
| --- | --- |
| textbox, text box, textfield, input, entry, field | Line edit |
| textarea, memo, multiline, notes, paragraph | Plain text edit (Text edit) |
| dropdown, drop down, select, picklist, choice, combo | Combo box |
| checkbox, tick, tickbox, toggle, yes no | Check box |
| radio, option | Radio button |
| button, btn, command | Push button (Tool button, Command link, Button box) |
| ok cancel, dialog buttons, buttons | Button box |
| number, integer, whole number, counter, numeric | Spin box |
| decimal, float, money, currency, price, amount | Double spin box |
| date, datepicker, day | Date edit (Calendar, Date and time edit) |
| time, clock | Time edit |
| datetime, timestamp | Date and time edit |
| calendar, month | Calendar |
| slider, range, track bar | Horizontal slider (Vertical slider) |
| knob | Dial |
| progress, loading, percent | Progress bar |
| table, spreadsheet, cells | Table widget (Table view) |
| grid | Grid layout (Table widget) |
| list, listbox | List widget (List view) |
| tree, hierarchy, folders | Tree widget (Tree view) |
| tabs, tab, notebook, pages | Tab widget (Toolbox, Stacked widget) |
| wizard, steps, assistant | Wizard (Wizard page) |
| panel, box, group, fieldset, container | Group box (Frame, Widget) |
| scroll | Scroll area (scroll bars) |
| label, caption, static text, title | Label |
| image, picture, photo, logo, icon | Label (a picture is a label's Picture property) |
| line, separator, divider, rule | Horizontal line (Vertical line) |
| space, gap, stretch, spring, spacer | Horizontal spacer (Vertical spacer) |
| shortcut, hotkey | Key sequence edit |
| html, browser, link, help text | Text browser |
| lcd, digits, display | LCD number |
| font | Font combo box |
| split, splitter, resizable panes | Horizontal splitter (Vertical splitter) |
| dock, side panel | Dock widget |
| mdi, windows | MDI area |
| quantity, unit, length | Quantity spin box |

The test is a table of (query, expected first result) pairs taken from this table plus "lin" → Line edit, "QComboBox" → Combo box, "push" → Push button, "tab" → Tab widget, "date" → Date edit.

**UX-CAT-008** `M4.1` `[S]` While the filter has text, the pane shows one flat result list in List view: glyph, friendly name with the matched letters on `fb.match`, and on the right in `fb.faint` Caption the category, or the synonym that matched in quotes ("“dropdown”") when the match came from a synonym. The first result is current, so Enter inserts it at once. The caption above the list (UX-AUTO-004) says where it will go: "Goes right after shopName."

**UX-CAT-009** `M4.1` `[S]` No match: the list area shows "Nothing called “{query}”. Try text, list or date." (UX-EMPTY-004) and a [Clear] link. Enter does nothing; the status bar says "Nothing to insert. Change the search or press Esc."

**UX-CAT-010** `M4.1` `[K]` Keyboard in the Insert pane (focus on a tile or row):

| Key | Action |
| --- | --- |
| Arrow keys | Move between tiles (Icons: in two dimensions; List: Up and Down). Left and Right on a category header collapse and expand it |
| Ctrl+Down / Ctrl+Up | First tile of the next / previous category |
| Home / End | First / last tile |
| Enter | Insert the current entry where the preview shows (UX-AUTO-003, UX-AUTO-004) |
| A printable character | Moves focus to the filter and types the character there |
| Esc | In the filter: clear it (focus stays). In the list with an empty filter: focus returns to the canvas |
| Down in the filter | Focus moves to the first result or tile |
| Alt+2 | Focus Insert (already in UX-KEY-004) |

To insert somewhere else, select the target first (Alt+1 and the outline, or the canvas), then Alt+2: the preview line shows the new place (UX-AUTO-004).

**UX-CAT-011** `M4.1` `[T K]` Inserting: click-and-drag places by pointer (UX-DND); double-click or Enter inserts without a pointer (UX-AUTO-003). After a keyboard insert, focus stays in the Insert pane so several widgets can be inserted in a row, each after the one before it (the selection follows the new widget). When the insert opens the form-row label editor (UX-FORML-002), focus goes to that editor and comes back to the same Insert tile after Enter or Esc in it. After a drag, focus goes to the canvas (UX-DND-007). Each insert is one undo step named "Insert {friendly name in lower case}" ("Undo Insert combo box").

**UX-CAT-012** `M4.1` `[S A]` A tile's tooltip has three lines: the friendly name (Strong), the Qt class in `fb.faint`, the description. Accessible names: tiles "Insert {friendly name in lower case}" ("Insert combo box"); category headers "{Category}, {n} widgets, collapsed" or "expanded"; the filter "Search widgets"; results "Insert combo box, Choices".

**UX-CAT-013** `M4.1` `[S K]` Quick insert (`/`, the outline's +, and the canvas `/`) uses the same search, ranking and synonyms. With an empty query it lists Recently used first, under a faint "Recently used" caption, then every entry by category. It shows at most 8 rows before scrolling. Rows: glyph, friendly name, category on the right. Enter inserts and closes it, Esc closes it, and focus returns to where `/` was pressed (UX-OUT-013).

**UX-CAT-014** `M4.1` `[T]` Context-limited entries are never hidden or greyed. They are refused at the target, with the indicator in `ov.problem` (UX-DND-005) and these sentences:

| Entry | Refused where | Sentence |
| --- | --- | --- |
| Wizard page | anywhere but a wizard | "A wizard page can only go into a wizard." |
| Dock widget | a main window's central area | "In a main window, a dock widget goes on one of its sides." |
| Spacer | a form layout cell | "A spacer can't go in a form row. Use a gap instead." (existing UX-DND-005 case) |
| Any container | inside itself | "A widget can't go inside itself." (existing) |

A keyboard insert of a refused entry inserts nothing, and the status bar shows the sentence.

**UX-CAT-015** `M4.1` `[S T]` Window kinds. Searching "main window", "dialog", "widget form" or "wizard" also lists, after the widget results, rows for the four window kinds: "Main window · new form", "Dialog · new form", "Widget · new form", "Wizard · new form", with the glyph of the kind. Enter opens the New form tab with that card focused and the name row filled with a free name. A window cannot go inside a form, so these rows never insert. The New form tab gains a fourth blank card, **Wizard**, which creates a `QWizard` root with two pages ("Step 1", "Step 2"), each with a vertical layout (R3 121).

**UX-CAT-016** `M4.1` `[S]` FreeCAD widgets draw on the canvas as their Qt base class (the realizer already uses the declared base). The FreeCAD category header has the tooltip "These widgets come from FreeCAD. In an app that runs without FreeCAD's window, each one is the plain Qt widget it is based on." Inserting one adds its `customwidget` declaration once per form.

**UX-ICON-005** `M4.1` `[S A]` Every catalog entry has its own glyph, painted on the 16 px grid at 16 and 20 px (UX-ICON-001, UX-ICON-002), in `fb.glyph`, with layouts in `ov.layout` and spacers in `ov.gap` (UX-ICON-003). Each glyph looks like a miniature of the widget: a button is a pill, a line edit a box with a caret, a combo a box with a chevron, a check box a ticked square, a radio a dotted circle, a slider a line with a knob, a dial a circle with a pointer, a spin box a box with up and down ticks, a date a calendar page, a time a clock, a list three lines with bullets, a tree indented lines, a table a 3 × 3 grid, a tab widget a folder tab, a toolbox stacked bars, a stacked widget two offset cards, a scroll area a box with a scroll thumb, a wizard a box with "<  >", an MDI area two overlapping windows, a dock a window with a side panel, a group box a box with a gap in its top edge for a title, a label "Aa", a line a single rule, a progress bar a half-filled bar, an LCD "88", OpenGL and Qt Quick a cube and a ring. Each window kind reuses the page-card glyph with a mark. Two entries share a glyph only when they differ only by orientation and the glyph is rotated. A test paints every glyph and fails when two different entries paint the same pixels, or a glyph is blank.

#### 13.1.3 Containers and pages (CONT)

**UX-CONT-001** `M4.2` `[A]` Page containers and where a page's title lives. The builder writes each page the way the container's loader reads it:

| Container | A page is | Title stored as | Shown in the outline as |
| --- | --- | --- | --- |
| Tab widget | a child widget | attribute `title` (also `toolTip`, `whatsThis`, `icon`) | "Tab 2 · Settings" |
| Toolbox | a child widget | attribute `label` (also `toolTip`, `icon`) | "Page 2 · Settings" |
| Stacked widget | a child widget | no title | "Page 2 · {object name}" |
| Wizard | a `QWizardPage` child | properties `title` and `subTitle` | "Step 2 · Payment" |
| MDI area | a child widget, shown in a subwindow | property `windowTitle` | "Window 2 · Notes" |

An insert never writes a tab title as a toolbox label, or the reverse (R3 128). Today's `InsertPage` writes `title` and "Tab {n}" for every container; M4.2 fixes it.

**UX-CONT-002** `M4.2` `[S K]` Page commands. On the canvas and in the outline, the context menu of a page container, of one of its pages, or of any widget inside a page has a **Pages** submenu (contributed through the context-menu seam, UX-CONT-020). It acts on the innermost page container and its shown page:

| Item | Shown for | Copy |
| --- | --- | --- |
| Insert page before | all but MDI | "Insert page before “{title}”" ("Insert tab before…", "Insert step before…" for tab widgets and wizards) |
| Insert page after | all but MDI | "Insert page after “{title}”" |
| Add window | MDI area | "Add window" |
| Delete page | all | "Delete page “{title}”…" (with "…" only when it will ask, UX-CONT-004) |
| Move left / Move right | tab widget | "Move tab left", "Move tab right" |
| Move up / Move down | toolbox, stacked, wizard, MDI | "Move page up", "Move page down" |
| Show previous / Show next | all | "Show previous page   Ctrl+PgUp", "Show next page   Ctrl+PgDown" |
| Start on this page | tab widget, toolbox, stacked, wizard | "Start on this page" (checked when it is the start page) |
| Tile windows / Cascade windows | MDI area | canvas only, not saved |

For a stacked widget, `{title}` is the page's object name. Items that cannot act stay visible and disabled with the reason as tooltip ("This is already the first page."). Shift+F10 opens the same menu by keyboard. The Pages submenu is the first item group, above the clipboard rows, when the clicked widget is a page or a page container.

**UX-CONT-003** `M4.2` `[T]` Insert page before or after the shown page: the new page gets the container's next free name (`tab_3`, `page_3`, `wizardPage_3`, `subwindow_2`), the title "Tab {n}", "Page {n}", "Step {n}" or "Window {n}" (n is its 1-based position), and a vertical layout. It becomes the shown page and the selection. For a tab widget, toolbox or wizard, the in-place title editor opens with the title selected (UX-TEXT-002); Enter keeps the typed title, Esc keeps the default. Insert and title are one undo step "Insert page". The canvas "+" pseudo-tab (UX-PAGES-002) is "Insert page after" the last page. Focus stays where it was (canvas or outline), except while the title editor is open.

**UX-CONT-004** `M4.2` `[T]` Delete page. A page with no widgets is deleted at once; toast "Deleted page “Tab 3” · Undo". A page with widgets asks first, in a popover anchored to the page's tab (canvas) or row (outline): "Delete page “Settings” and the 4 widgets on it?" [Delete page] [Cancel], Enter on the focused button, Esc cancels. References to widgets on the page are listed as in UX-OUT-012. After delete, the next page (else the previous one) is shown and selected. One undo step "Delete page". Deleting the last page is allowed; the container then shows UX-CONT-009.

**UX-CONT-005** `M4.2` `[T K]` Move page. Besides the existing drag and Alt+arrow gestures (UX-PAGES-004, UX-OUT-007), the Pages menu items move the shown page one place. Each move is one undo step "Move page"; presses within 1 s merge (UX-NUDGE-001). The start page stays the same page (CONTRACTS `MovePage`).

**UX-CONT-006** `M4.2` `[S T]` Shown page and start page are different things. The **shown** page is the one the canvas displays; it is never saved. Clicking a tab title, a toolbox header, the stacked switcher arrows (UX-PAGES-003), a wizard or MDI switcher chip, selecting a widget on a hidden page, Ctrl+PgUp or Ctrl+PgDown all change the shown page only. The **start** page is `currentIndex`, saved in the file, changed only by "Start on this page" or the inspector row "Starts on" (a drop-down of page titles, Content group). The page chip of a container whose shown page is not its start page reads "Shows {title} · starts on {title}" in its tooltip. This differs from Designer, which saves whatever page was showing; it keeps an accidental click from changing the file.

**UX-CONT-007** `M4.2` `[K]` Ctrl+PgDown and Ctrl+PgUp, with focus in the canvas or the outline and the selection inside or on a page container, show the next or previous page of the innermost one (they wrap). The status bar says "Showing page 2 of 3: Settings · the file still starts on page 1" when the shown page differs from the start page, else "Showing page 2 of 3: Settings". Add both keys to UX-KEY-004 (context canvas, outline; status new; checked against the shell table: free).

**UX-CONT-008** `M4.2` `[T K]` Page titles. Enter on a selected page row in the outline, on a selected tab title or toolbox header on the canvas, or on a wizard page opens the title editor (UX-TEXT-001; a wizard page edits its `title`). F2 still renames the page's object name. A stacked page has no title: Enter on it selects its first child (UX-SEL-005).

**UX-CONT-009** `M4.2` `[S]` A page container with no pages draws, inside its own rectangle, a dashed `ov.layout_faint` outline and the Caption "No pages. Use + or Pages > Insert page." (wizard: "No steps…"; MDI: "No windows. Use Pages > Add window."). A drop on it creates the first page with the widget inside (UX-PAGES-002 rule).

**UX-CONT-010** `M4.2` `[S T]` Scroll area. The canvas draws it at its real size with its real scroll bars (truth first, UX-PRIN-001). The wheel over a scroll area on the canvas scrolls its content (Shift+wheel horizontally) without moving the canvas; Ctrl+wheel still zooms. Selecting a widget inside it, by any means, scrolls the area so the widget is visible (canvas only, never saved). A drag held over the area's top or bottom 16 px for 400 ms scrolls it by one step per 100 ms, so a drop can reach any place. Drops go into the content widget's layout. A scroll area without a content widget (older files) gets `scrollAreaWidgetContents` with a vertical layout on the first drop, one undo step. Curated rows: "Content follows the area's size" (`widgetResizable`, help: "On: the content stretches to fill the area and scrolls only when it can't shrink further. Off: the content keeps its own size."), "Scroll bars" with "Horizontal" and "Vertical" drop-downs (As needed, Always, Never).

**UX-CONT-011** `M4.2` `[S T]` MDI area. Each child widget is a window and is drawn in a real subwindow on the canvas. "Add window" adds `subwindow` with the title "Window {n}" and a vertical layout, shown, selected, with the title editor open. Show previous and Show next bring a window to the front (canvas only); a switcher chip "◀ 2 / 3 ▶" sits by the area like the stacked one. Tile and Cascade arrange the windows on the canvas only and are not saved. The subwindow frames' buttons do nothing on the canvas. Delete removes the window and its content (UX-CONT-004 rules).

**UX-CONT-012** `M4.2` `[S T K]` Dock widget. In a main window, a dock widget belongs on a side. While a dock widget is dragged over a main-window form (from Insert or a move), four 32 px `ov.dock_band` bands appear along the inside edges of the page: "Left side", "Right side", "Top", "Bottom" (chips placed by the solver). The pointer picks the nearest band; the drop writes the dock's side (attribute `dockWidgetArea`, the number Qt uses) and the canvas shows it docked. The central area is a refused target (UX-CAT-014). The inspector shows "Dock side" as a four-segment control (Left, Right, Top, Bottom) in Placement, and "Can close", "Can float", "Can move" check boxes (`features`) and "Allowed sides" (flags popover) in Content. Outside a main window, a dock widget sits in the layout like any container, and its inspector Placement caption says "Docks only in a main window. In this form it shows as a panel." Keyboard: the Dock side control, and Alt+arrows do not move docks between sides.

**UX-CONT-013** `M4.2` `[S T]` Wizard. A wizard's pages are `QWizardPage` widgets. The canvas draws the real wizard with its Back, Next and Cancel buttons, which do nothing on the canvas; a switcher chip "◀ Step 2 of 3 ▶" changes the shown page. Insert step before and after, delete, move and "Start on this page" follow CONT-002 to CONT-006. A wizard page's Content group shows "Step title" (`title`, translatable) and "Step subtitle" (`subTitle`, translatable). The form can be a wizard (the New form card, UX-CAT-015) or contain one. Generated code builds the same pages in the same order; the uic oracle covers a root wizard and a nested one.

**UX-CONT-014** `M4.2` `[S]` Group box rows (Content and Appearance): "Title" (exists), "Can be switched off" (`checkable`, help: "Adds a check box to the title. Unchecking it turns off everything inside."), "Starts switched on" (`checked`, shown only when Can be switched off is on), "Flat" (exists), "Title alignment" (Left, Centre, Right).

**UX-CONT-015** `M4.2` `[S]` Frame rows (Appearance): "Frame" (`frameShape`: No frame, Box, Panel, Styled panel, Horizontal line, Vertical line, Windows panel), "Shadow" (`frameShadow`: Plain, Raised, Sunken), "Line width", "Middle line width". A `Line` widget shows only "Orientation" and "Shadow"; its shape follows its orientation, as Designer writes it.

**UX-CONT-016** `M4.2` `[T]` A page is a container (R3 132). Selecting a page (its outline row, or its empty area on the canvas) and pressing Ctrl+1 … Ctrl+6 lays out that page; a page without a layout shows the "No layout" marker (UX-FRAME-003). The same holds for a scroll area's content widget, a dock's content widget and an MDI window.

**UX-CONT-017** `M4.2` `[S A]` Stand-ins. An OpenGL widget, a Qt Quick view, and any class the realizer can't build safely in the editor (it would need a GL context, a QML engine, or user code) is drawn as a stand-in: an `ov.stand_in_fill` rectangle with a dashed `ov.stand_in_line` border, at least 80 × 24 px (UX-RUN-004), and centred 11 px `ov.stand_in_text`: "{friendly name} · drawn by your code" (two lines when narrower than the text). The stand-in has the widget's size policy and size hint, so the layout is the same as at run time. The editor never creates an OpenGL context or a QML engine (test: no `QOpenGLContext` or `QQmlEngine` exists after realizing a form that has both).

**UX-CONT-018** `M4.2` `[S]` Page attributes are curated rows on the page widget, in Content: tab widget pages "Tab title", "Tab tooltip", "Tab help" (`whatsThis`), "Tab icon" (shown from M4.3c); toolbox pages "Page label", "Page tooltip", "Page icon"; each written as an attribute (UX-PED-063). They are registered from a new rows module; the shared rows file is not edited.

**UX-CONT-019** `M4.4` `[S K T]` Inspector **Pages** group, for a tab widget, toolbox, stacked widget, wizard and MDI area, directly after Content. It is the list editor (UX-PED-044) over the pages: one row per page showing its title (stacked: object name, read-only, with "Page {n}" before it), a "Starts on" marker (a filled dot) on the start page's row, and a + button "Add page". Keys as the list editor: Enter on the last row adds a page after it; Alt+Up and Alt+Down move; Ctrl+Delete deletes (asking per UX-CONT-004); typing edits the title. Moving the current row shows that page on the canvas. Space on a row makes it the start page. Each action is the same command as the Pages menu, with the same undo step. At 236 px the group is full width (UX-PED-002 stacked rows); titles elide at the end with the full title in the tooltip.

**UX-CONT-020** `M4.0s` `[A]` Context-menu seam. Lanes add context-menu rows without editing `integration/surface.py` or `integration/context_menu.py`: modules in `integration/menu_ext/` are discovered in sorted name order and each exposes `register(registry)`; a contributor receives the menu, the selection and the command dispatcher, and may add a submenu or rows in one of three groups: "first" (above the clipboard rows), "structure" (with Change to and Remove layout) and "last". M4.2 adds Pages; M4.4 adds "Edit items…".

#### 13.1.4 Property editors (PED)

##### Shared rules

**UX-PED-001** `M4.0s` `[A]` Every value type has an editor; none is left as raw XML except the style sheet until M5.3 (pain 18). Owner lanes:

| Value (ui4 element) | Editor | Inline or popover | Lane |
| --- | --- | --- | --- |
| `bool` | check box | inline | M4.3a |
| `number`, `uint`, `longlong`, `ulonglong`, `float`, `double` | spin field | inline | M4.3a |
| `enum` | drop-down of friendly names | inline | M4.3a |
| `set` (flags) | summary + check-box popover; alignment keeps its segments | popover | M4.3a |
| `char` | one-character field | inline | M4.3a |
| `size`, `sizef`, `point`, `pointf`, `rect`, `rectf` | one field per line | stacked inline | M4.3a |
| `sizepolicy` | summary + popover | popover | M4.3a |
| key sequence (`string` named `shortcut`, `keySequence`) | recorder | inline | M4.3a |
| `date`, `time`, `datetime` | typed field + calendar popover | inline + popover | M4.3a |
| `locale` | summary + popover | popover | M4.3a |
| `string` | text field; multi-line and rich text in a popover; Translation disclosure | inline + popover | M4.3d |
| `stringlist` | summary + list popover | popover | M4.3d |
| `cstring` | text field | inline | M4.3d |
| `url` | text field + Translation disclosure | inline | M4.3d |
| `font` | summary + popover | popover | M4.3b |
| `color` | swatch + popover | popover | M4.3b |
| `brush` (and gradients) | swatch + popover | popover | M4.3b |
| `palette` | summary + large popover | popover | M4.3b |
| `cursor`, `cursorShape` | drop-down | inline | M4.3b |
| `pixmap` | thumbnail + picker popover | popover | M4.3c |
| `iconset` | thumbnail + picker popover | popover | M4.3c |
| style sheet (`string` named `styleSheet`) | raw text, "Kept as is" editing as today | inline | M5.3 (deferred) |
| anything else (an element from a newer Qt) | read-only raw value with "Kept as is" (UX-INSP-009) | — | M4.3d keeps it |

A test walks every ui4 value class and fails when one has no registered editor other than the raw one, except the two rows marked deferred and kept.

**UX-PED-002** `M4.0s` `[S A]` Width budget. The narrowest inspector content width is **236 px** (the 264 px pane minimum, less padding and the scroll bar). There the row is label 96 px + gap 8 + editor column 132 px. Every inline editor shows its reference value unclipped in 132 px: "Password echo on edit", "Minimum expanding", "−2147483648", "12/31/2026 11:59 PM" and "Ctrl+Shift+Alt+F12" are the reference texts. An editor that cannot fit uses the **stacked row**: the label on its own line, the editor full width (236 px) under it. Size, point and rect fields and the date-and-time field are stacked below 300 px content width and side by side above it. Summary buttons (fonts, colours, flags, lists, pictures) stay in the editor column and elide their text at the end, with the full text in the tooltip. Nothing in the inspector scrolls sideways at any width (test at 236, 264 and 420 px).

**UX-PED-003** `M4.0s` `[S K T]` The row popover. A compound value opens in a popover anchored to its row:

- Level 2 (UX-ELEV-001), `fb.popup` fill, 1 px `fb.popup_border`, 6 px radius, 12 px padding. Width is the inspector content width, at least 236 and at most 320 px; the large editors (palette, gradient, item lists, tables) are 320–480 px wide and grow to the left over the canvas. It opens below the row, or above when there is no room below, and never covers its own row.
- Header: the row label in Title and the Qt name in `fb.faint` Caption. Footer, when the editor needs one: [Reset] at the left (only when the value is written), [Done] at the right (primary).
- Open: Enter, Space or Alt+Down on the row's summary button, or a click on it. Focus goes to the popover's first field.
- Tab and Shift+Tab cycle inside the popover; they do not leave it.
- Close and keep: Done, Enter in a one-line field, or a click outside the popover. Close and revert: Esc, which undoes everything this popover changed and leaves no undo step. Ctrl+Z in a field undoes the field's typing first; elsewhere in the popover, Ctrl+Z closes it and keeps the change, then undoes it as one step.
- On close, focus returns to the row's summary button. Nothing else (toasts, regeneration, Problems) takes focus while it is open (UX-PRIN-006).
- Changing the selection, switching tabs, or a structural command closes it and keeps the changes.
- Accessible name of the popover: "{Row label} editor"; the summary button: "{Row label}: {summary}".

**UX-PED-004** `M4.0s` `[T A]` Commit and undo. Inline fields commit on Enter, on focus out and on a choice; Esc reverts uncommitted text (existing `is_dirty`). A **session** is the time a field keeps focus, or a popover stays open. Every change in one session to one property merges into one undo step named for the property ("Undo Change maximum length", "Undo Change font of titleLabel"); spin-arrow steps, drags in a colour square and gradient stop moves merge the same way. A popover session that touches several properties (palette roles, a font's parts) is still one step. Each change applies to the canvas live, inside the edit budget (UX-M4-007). The seam gives editors `commit(value, session=...)` and a popover session object with `revert()`; the existing per-row merge token ends when the session ends, so two separate visits to one row are two undo steps.

**UX-PED-005** `M4.0s` `[T]` The mouse wheel never changes a value in a field that does not have keyboard focus; it scrolls the inspector. With focus, the wheel steps a number field by one step and a drop-down by one item, and the session rule merges the steps.

**UX-PED-006** `M4.3a, M4.3b, M4.3c, M4.3d` `[S]` Unwritten values. Every editor shows the class default in `fb.faint` (UX-INSP-007): a faint number, a faint drop-down text, a summary like "Default (9 pt)" for fonts, a hollow swatch with "Default" for colours, "None" for images and shortcuts, "—" for limits without a default. Writing a value makes the text `fb.text` and the label Strong with the accent bar (UX-INSP-006). Reset deletes the property, one undo step "Reset {label}".

**UX-PED-007** `M4.3a, M4.3b, M4.3c, M4.3d` `[S T]` Multi-select (UX-INSP-011). Every editor has a Mixed look: an empty field with the placeholder "Mixed" in italic `fb.faint`, a partly checked check box, a drop-down whose text is "Mixed", a swatch with a diagonal line, a summary "Mixed". A commit writes the new value to every owner that has the property, as one step; owners without it are skipped and the caption says "Not applied to {n} widgets that lack this property." (exists).

**UX-PED-008** `M4.3a, M4.3b, M4.3c, M4.3d` `[S]` Refusals appear under the field in `fb.error` Caption (UX-FEED-007), keep the typed text, and block Enter until fixed or Esc. The sentences are in 13.1.6.

**UX-PED-009** `M4.3a` `[S T]` Pain 18. A chosen value is written at once and stays written: the row is Strong, and save writes it. If Qt refuses the value on the canvas widget (the realizer reports it), the value stays in the file and the row's caption says, in `fb.warning`: "Saved in the file. The canvas can't show this value." Save never drops a value. P-18 test: set Echo mode to Password, save, close, reopen: the row shows Password and the XML has `QLineEdit::Password`; a property whose type has no editor is byte-identical after save.

**UX-PED-010** `M4.3a, M4.3b, M4.3c, M4.3d` `[A]` Accessible names of editor parts follow "Row: part" (as M3.7d2 did for segments): "Maximum size: width", "Font: bold", "Colour: hex", "Date: open calendar". A test walks every editor built for the reference form and fails on an empty accessible name.

##### Scalars (M4.3a)

**UX-PED-020** `M4.3a` `[S K]` Bool: a check box with no text, aligned to the editor column's left. Space toggles; the toggle commits at once.

**UX-PED-021** `M4.3a` `[S K T]` Numbers: a spin field, right-aligned, tabular figures, with the unit after it when there is one ("px", "pt", "%"). The range comes from the curated row (Maximum length 0–32767), else from the Qt type. Up and Down step by one step (Shift: ×10), PageUp and PageDown by ten steps. Decimals: for `double` and `float`, as many as the property needs, at most 6, with trailing zeros dropped on show; the decimal mark is the project locale's (en_US: "."). Typing a value out of range shows "Use a number from {min} to {max}." Typing a non-number shows "Type a number, like 12." Clearing the field resets the property (deletes it) when the property has a default; otherwise it shows "Type a number, like 12."

**UX-PED-022** `M4.3a` `[S K T]` Enum: a drop-down of friendly names, in Qt's enumerator order. Friendly names come from a table (Echo mode: "Normal", "No echo", "Password", "Password while typing"; Frame: as UX-CONT-015; others by splitting the enumerator into words: `MinimumExpanding` → "Minimum expanding"). Each item's tooltip is the Qt name. A value the table doesn't know (a newer Qt, a plugin enum) is shown as the first item in italic, "{Qt name} (kept as is)", and stays written until the user picks another. Choosing commits (pain 18). Keys: Alt+Down or Space opens; Up and Down on the closed drop-down change the value and commit, merged into one step (UX-PED-004); typing letters jumps to the next match.

**UX-PED-023** `M4.3a` `[S K T]` Flags: a summary button listing the set names, friendly, joined by ", " ("Left, Vertically centred"), "None" when empty, elided at the end with the full list in the tooltip. Its popover lists one check box per flag; flag groups that exclude each other (horizontal alignment, vertical alignment) are radio groups with a "None" choice. Each toggle applies live; the session is one step. Space toggles the focused flag. The alignment rows keep their segmented controls from M3.7d2.

**UX-PED-024** `M4.3a` `[S]` Char: a 32 px field that takes exactly one character. With "Qt names" on, the code point shows after it in `fb.faint` ("U+00B7"). More than one character shows "Type one character."

**UX-PED-025** `M4.3a` `[S]` Size, point and rect (and their float forms): one labelled field per line ("Width", "Height" / "X", "Y" / "X", "Y", "Width", "Height") with "px" after integer fields, stacked below 300 px content width (UX-PED-002) and in pairs above it. Each field commits on its own (one step per field). Float forms show 2 decimals.

**UX-PED-026** `M4.3a` `[S T]` Size policy (the raw row in All properties and the curated "Size policy" row): summary "{horizontal} × {vertical}" with shares when set ("Expanding × Fixed · share 1 : 0"). The popover: "Horizontal" and "Vertical" drop-downs of the seven policies with friendly names and one-line help each (Fixed: "Exactly its size hint." Minimum: "Can grow; never smaller than its size hint." Maximum: "Can shrink; never larger than its size hint." Preferred: "Its size hint, but can grow or shrink." Expanding: "Takes all the room it can." Minimum expanding: "Takes all the room it can; never smaller than its size hint." Ignored: "Ignores its size hint; takes the room it's given."), then "Horizontal share" and "Vertical share" (0–255). Changes are live and one step. The Size group's words (UX-SIZE) and the chip update in the same frame (UX-SIZE-008).

**UX-PED-027** `M4.3a` `[S K T]` Key sequence: a field showing the sequence in portable text ("Ctrl+Shift+P"), or the placeholder "None", and a [Record] button (UX-COPY-006). Record (or Enter on the field) shows "Press the keys…" with a 2 px `fb.accent` border; the next key combination is captured; a second combination within 1 s makes a two-step shortcut ("Ctrl+K, Ctrl+S"); then recording stops and the value commits. Esc while recording cancels and keeps the old value. Backspace alone while recording clears the shortcut ("None") and commits. If another action in this form already has the same shortcut, the caption warns, in `fb.warning`: "{actionName} already uses {keys}." The value is written anyway. The string's translation attributes are kept as they were.

**UX-PED-028** `M4.3a` `[S K T]` Date and time: a typed field in the project locale's short format with a four-digit year ("10/28/2026", "2:30:00 PM", "10/28/2026 2:30 PM") and a ▾ button that opens a popover: a calendar for dates (arrows move by day, PageUp and PageDown by month, Ctrl+PageUp and Ctrl+PageDown by year, Enter picks and closes) and Hour, Minute, Second fields for times. Typed text commits on Enter or focus out; an unreadable date shows "Use a date like 10/28/2026." and an unreadable time "Use a time like 2:30 PM." Date ranges (minimum and maximum dates) use the same editor.

**UX-PED-029** `M4.3a` `[S K]` Locale: a summary "{Language} ({Country})" ("English (United States)"); unwritten shows "Same as the app" in `fb.faint`. The popover has "Language" (a drop-down that filters as you type) and "Country or region" (only the territories Qt pairs with that language). Stored as the `language` and `country` names Qt writes.

##### Text, translations and lists (M4.3d)

**UX-PED-040** `M4.3d` `[S K T]` Text. One-line properties edit in the row's field. Properties that allow several lines (a word-wrapped label's text, `plainText`, tooltips, What's this, status tips longer than the field) show the first line with "↵" where a line break is, and a ▾ button that opens a text popover: a plain multi-line editor (Body, the runtime font family), where Enter adds a line and Ctrl+Enter or [Done] keeps it, Esc reverts. One step per session, named for the property.

**UX-PED-041** `M4.3d` `[S K T]` Translation. Every string that generated code puts in `retranslateUi` (the translatable properties and attributes: texts, titles, tooltips, status tips, What's this, accessible names and descriptions, placeholders, window titles, page titles and labels, item texts, URL strings) has a "Translation ▸" disclosure in Caption `fb.muted` on its caption line. Expanded, it shows: a "Translate this text" check box (off writes `notr="true"`); "Meaning" (`comment`, help: "Tells translators which meaning is meant when the same words mean different things, like “Open” a file or “Open” the shop."); "Note for the translator" (`extracomment`); and, when the file has one or Qt names are on, "Translation id" (`id`). Each field commits on its own (one step each). A string that will not be translated shows "Not translated" in `fb.faint` at the end of its caption line, so a veteran sees it without opening the disclosure. A string that is not translatable (style sheet, input mask, object references) has no disclosure. Editing the text keeps the attributes as they were. The disclosure state is per row and remembered for the session.

**UX-PED-042** `M4.3d` `[S K T A]` Rich text (R3 172). For a label whose text format is Rich, or Automatic with text that is already HTML, and for the `html` of a text edit or text browser, the text popover has a two-segment control **Formatted | Source**. Formatted is an editor with a bar: Bold (Ctrl+B), Italic (Ctrl+I), Underline (Ctrl+U), Link… (no key; it asks "Link address" in a field under the bar), Bulleted list, Numbered list, and Text size (Smaller, Normal, Larger). Source shows the HTML in the code editor style with XML highlighting. Plain mode turns into Formatted only when the user picks Formatted ("Make this text formatted? It is stored as HTML." [Make formatted] [Cancel]). The HTML written is generated against the runtime default font and a fixed document setup, never the editor's own font, so the same edit gives the same bytes on macOS and Linux (test runs the edit under both and under the `C` and `de_DE` locales, CONTRACTS §8.3).

**UX-PED-043** `M4.3d` `[S K T]` String list: a summary "{n} items: {first}, {second}…" ("3 items: Red, Green, Blue"), "No items" when empty, elided at the end. The popover is the list editor (UX-PED-044) with a Translation disclosure at its foot that applies to the whole list (the attributes live on the `stringlist`). One step per session.

**UX-PED-044** `M4.3d` `[S K T A]` The list editor, shared by string lists, the Pages group (UX-CONT-019) and the item editors (UX-ITEM). One row per entry, 24 px: a drag grip, the text field, and a × button (accessible "Delete row {n}") shown on hover and focus.

| Key | Action |
| --- | --- |
| Typing | Edits the focused row's text |
| Enter | Keeps the row and moves to the next row; on the last row, adds a new empty row and moves to it. Enter on an empty last row closes the editor and keeps the session |
| Up / Down | Previous / next row |
| Alt+Up / Alt+Down | Move the row up / down |
| Ctrl+Delete | Delete the row (the next row gets focus, else the previous) |
| Backspace in an empty row | Delete the row and move to the end of the previous row |
| Ctrl+V with several lines | Paste one row per line, after the focused row |
| Esc | Close and revert the session |
| Tab / Shift+Tab | Leave the list to the footer buttons and back |
| Alt+Right / Alt+Left | Open / close the row's details, where rows have them (items, UX-ITEM-003) |

Rows reorder by dragging the grip, with a 2 px insertion line and an 8 px hit band (UX-GRID-004). An empty list shows "No items yet. Type one and press Enter." in `fb.faint`. 500 rows open within 50 ms (UX-M4-007). Accessible name of each field: "{List name} row {n}".

**UX-PED-045** `M4.3d` `[S]` C string: a plain text field with no Translation disclosure. Rows that name another object (the buddy) are M5.6 pickers; until then they are text fields that refuse a name that isn't on the form: "No widget called “{name}” on this form."

**UX-PED-046** `M4.3d` `[S]` URL: a text field showing the address. An address with no scheme gets the caption, in `fb.warning`, "This doesn't look like a web or file address." and is written anyway. The Translation disclosure applies to the inner string (R3 170).

##### The Properties tab (M4.3d)

**UX-PED-060** `M4.3d` `[S]` Custom properties (R3 149). Under All properties, a block "Custom properties" lists the selection's dynamic properties (written with `stdset="0"`), each a normal row: its name as the label (no friendly name), the editor for its type, Reset, and a ⋯ row menu with "Rename…", "Change type ▸" and "Remove". Code Studio's own logic keys (names starting with `cbcs`) are not listed here (M6 shows them in Behavior). The block is shown even when empty, with only the add button, so the feature can be found.

**UX-PED-061** `M4.3d` `[S K T]` "+ Add custom property" is a text button at the end of the block. It opens an inline form in the block: "Name" field, "Type" drop-down (Text, Number, Decimal number, True or false, Date, Time, Date and time, Colour, Font, Size, Point, Rectangle, List of text, Address (URL), Shortcut), and [Add] [Cancel]. Enter in the Name field adds; Esc cancels. The new property gets its type's empty value (empty text, 0, false, today's date, black, the default font, 0 × 0…), is written, and focus moves into its editor. One step "Add custom property {name}". With several widgets selected it is added to all of them.

Name refusals: "Names use letters, digits and _, and can't start with a digit." / "{Class} already has a property called {name}. Pick another name." / "This widget already has a custom property called {name}." / "Names starting with cbcs are kept for Code Studio."

**UX-PED-062** `M4.3d` `[T]` Rename is a remove plus an add of the same value, one step "Rename custom property". Change type converts the value when it can (number to text, text to number when it reads as one) and otherwise asks: "{name} can't be turned into {type}. Its value will be cleared." [Change type] [Cancel]. Remove deletes it, one step, toast "Removed custom property {name} · Undo". Reset on a custom property is the same as Remove and says so in its tooltip.

**UX-PED-063** `M4.3d` `[S]` Properties and attributes (R3 150). All properties lists Qt properties grouped by declaring class, then "Stored by the parent" for attributes (page titles, labels, dock side, toolbar area, button group), then "In the file" for anything else written that the live widget doesn't have, then Custom properties. An attribute row edits the attribute, never a property of the same name. With Qt names on, attribute rows show "(attribute)" after the Qt name.

**UX-PED-064** `M4.3d` `[S]` The inspector ⋯ menu gains "Sort all properties A–Z" (a check item, per user, off by default). On, All properties is one alphabetical list by Qt name with each row's declaring class in `fb.faint` on its Qt-name line; group headers go away (R3 148). Curated groups are never re-sorted.

**UX-PED-065** `M4.3d` `[S]` Property search (UX-INSP-012) also matches custom property names, attribute names and the friendly words of enum and flag values ("password" finds Echo mode).

##### Font, colour, brush, palette, cursor (M4.3b)

**UX-PED-080** `M4.3b` `[S K T]` Font: a summary of only the written parts, in the order family, size, style ("Sans Serif, 12 pt, Bold"), or "Default ({size} pt)" in `fb.faint`. The summary is drawn in the plain inspector font, never in the chosen font. The popover:

- "Family": a drop-down that filters as you type, with "Default (the app's font)" first, then the families installed here. A family is shown in its own face only in the drop-down list. Caption: "The computer that runs your app needs this font too."
- "Size": a spin field in points (1–200) with presets in its drop-down (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48).
- Style toggles Bold, Italic, Underline, Strikeout as four 24 px toggle buttons with glyphs "B", "I", "U", "S" (accessible "Font: bold" …).
- "More ▸": "Weight" (Thin … Black), "Kerning", "Smoothing" (Default, Prefer smooth, No smoothing), "Hinting" (Default, None, Vertical, Full).

Each part is written only when set; each set part has its own ↺ in the popover that unsets that part. Changes are live; one step per session. This replaces today's 50 px family combo that clipped to "De…" (ticket I5b).

**UX-PED-081** `M4.3b` `[S K A]` The colour picker, used by the colour row, brushes, gradient stops and palette roles: a saturation-value square 200 × 140 px with an `fb.handle` ring, a hue strip 200 × 12 px, an alpha strip (shown only where alpha is stored) over the `fb.checker` pattern, a "Hex" field ("#1A7F37", or "#1A7F3780" with alpha), "More ▸" with Red, Green, Blue (0–255) and Alpha (0–100 %) fields, and a row of up to 12 recent colours (per user, most recent first). Keys: in the square, arrows move by 1 (Shift: 10); in the strips, Left and Right. Typing a hex value commits on Enter; a bad one shows "Use a colour like #1A7F37." Dragging is live within the edit budget and one step per session. At 236 px the square shrinks to 212 × 120.

**UX-PED-082** `M4.3b` `[S]` Colour row: a 16 × 16 swatch (1 px `fb.swatch_border`, the checkerboard under transparency) and the hex text, plus "{n} %" when alpha is below 100. Unwritten: a hollow swatch and "Default" in `fb.faint`.

**UX-PED-083** `M4.3b` `[S K T]` Brush: summary swatch (the brush painted 16 × 16) and "Solid #1A7F37", "Pattern: Dense 4, #000000", "Linear gradient, 3 colours", "No brush". The popover has a "Style" segmented control: **None | Solid | Pattern | Gradient** (and **Picture** from M4.3c, UX-PED-103). Solid embeds the colour picker. Pattern shows a drop-down of the Qt patterns, each drawn as a 32 × 16 preview, with friendly names ("Dense 1 (darkest)" … "Dense 7 (lightest)", "Horizontal lines", "Vertical lines", "Cross", "Diagonal lines /", "Diagonal lines \\", "Diagonal cross"), and a colour.

**UX-PED-084** `M4.3b` `[S K T A]` Gradient (inside the brush popover, 320–480 px wide): "Type" (Linear, Radial, Conical); a 24 px gradient bar with stop handles (`fb.handle`, current `fb.handle_current`); the colour picker for the current stop; "Spread" (Pad, Repeat, Reflect); "Fill" ("Stretch to the widget", "Use pixel positions", "Stretch to the screen" for the three coordinate modes; default the first); and "More ▸" with the geometry fields of the type (Linear: start X, Y, end X, Y; Radial: centre X, Y, radius, focal X, Y; Conical: centre X, Y, angle), as fractions 0–1 in "Stretch to the widget" mode. Bar keys: Left and Right pick the previous and next stop; Alt+Left and Alt+Right move the current stop by 1 % (Shift: 10 %); Insert adds a stop halfway to the next one; Delete removes the current stop (at least 2 stay: "A gradient needs at least two colours."). Click on the bar adds a stop with the colour under the pointer; drag moves; drag a stop off the bar by 24 px removes it. Every change is live, one step per session. The written gradient is the same bytes for the same stops on macOS and Linux (CONTRACTS §8.3).

**UX-PED-085** `M4.3b` `[S K T]` Palette: summary "Default" or "{n} colours changed". The popover (320 px, up to 480 px tall, scrolls) lists the roles in this order with friendly names: Window, Window text, Base (field background), Alternate base, Text, Placeholder text, Button, Button text, Bright text, Highlight, Highlighted text, Link, Visited link, Tooltip background, Tooltip text, Light, Midlight, Mid, Dark, Shadow. Each role row has one swatch "All states". "Show each state" (a check box at the top) splits each row into three swatches: Active, Inactive, Disabled. Enter or a click on a swatch opens the brush editor in place inside the popover with a "‹ Palette" back button (Esc goes back first, a second Esc closes). A written role has a Strong label and a ↺. "Start from a colour…" sets every role from one button colour the way Qt derives a palette, as one step, after a confirm when roles are already set: "Replace the {n} colours you set?" [Replace] [Cancel]. Only changed roles are written; the three state groups are written as Qt requires. One step per session, named "Change palette of {name}".

**UX-PED-086** `M4.3b` `[S K]` Cursor: a drop-down with friendly names in this order: Arrow, Pointing hand, Text (I-beam), Wait, Busy (arrow and wait), Cross, Up arrow, Resize left–right, Resize up–down, Resize diagonal ⟋, Resize diagonal ⟍, Move, Split horizontal, Split vertical, Not allowed, What's this, Open hand, Closed hand, Drag copy, Drag move, Drag link, Blank. Tooltips give the Qt names. A legacy integer `cursor` is shown by its name and kept until changed; a change writes `cursorShape`.

##### Pictures and icons (M4.3c)

**UX-PED-100** `M4.3c` `[S K T]` The picture picker, used by pixmap and icon rows and picture brushes. A popover (320 px) with a "Search pictures" field and a grid of 56 × 64 px cells (48 px thumbnail on the checkerboard, file name under it, elided in the middle). It lists every image file in the `.qrc` files this form includes (`<resources>`), grouped by `.qrc` file and prefix, with the resource path in each tooltip (":/icons/save.png"). Arrows move in the grid, Enter picks and closes, Esc reverts. Below the grid: "From a file…" (a file dialog) and, when the form includes no `.qrc`, the Caption "This form uses no resource file yet. Pictures from files may be missing when the app is packaged." Picking a file outside resources writes its path relative to the form and shows, in `fb.warning` on the row, "Loaded from a file path. A packaged app may not find it." Adding the file to a resource file is M5.2 (deferred, pain 9).

**UX-PED-101** `M4.3c` `[S]` Picture row (pixmap): a 16 × 16 thumbnail (1 px `fb.swatch_border`) and the file name; unwritten "None" in `fb.faint`; a missing file "{name} (missing)" in `fb.error` with the tooltip "Code Studio can't find {path}." The canvas shows the picture as the app would (the realizer reads resources from the `.qrc` on disk).

**UX-PED-102** `M4.3c` `[S K T]` Icon (icon set): summary thumbnail and name. The popover: "Picture" (the normal, off state; the picker), "Theme icon name" (field, help: "Uses the desktop's icon with this name when there is one; otherwise the picture."), and "Other states ▸": a 4 × 2 grid of small picker cells — Normal, Disabled, Active, Selected, each Off and On — with "Same as normal" shown faint where unset. A legacy `resource` attribute is kept as it was. One step per session.

**UX-PED-103** `M4.3c` `[S]` A brush's **Picture** style (texture) uses the picture picker inside the brush popover.

**UX-PED-104** `M4.3c` `[S]` Every image on the canvas that cannot be loaded is drawn as the class would draw an empty picture, never as a crash or a broken-image icon, and the row says why (UX-PED-101).

#### 13.1.5 Item editors (ITEM)

**UX-ITEM-001** `M4.4` `[K T]` The items of a combo box, list widget, tree widget and table widget are edited in the item editor. It opens with: Enter on the selected widget on the canvas (UX-TEXT-004; for a tree and a table too); "Edit items…" in the context menu; or the "Items" row in the Content group, whose summary reads "{n} items: {first}, {second}…" (tree: "{n} rows in {m} columns"; table: "{rows} × {columns}, {n} cells filled"). Double-click on these widgets on the canvas opens it as well (they have no text to edit in place).

**UX-ITEM-002** `M4.4` `[S]` From the canvas, the editor is a popover anchored beside the widget, placed like a chip (UX-CHIP-002 order, never covering the widget being edited), 360 × 320 px by default (tree and table 480 × 360), resizable from its bottom-right grip, size remembered per user. From the inspector row it anchors to the row (UX-PED-003). It is a level 2 surface with a header "Items of {name}" and [Done] at the foot.

**UX-ITEM-003** `M4.4` `[S K T]` Combo box and list widget: the list editor (UX-PED-044) over the items' texts. Each row has a ▸ disclosure that shows the item's details: "Icon" (the picture picker, UX-PED-102), and for list widget items "User can check it" with "Starts" (Unchecked, Checked, Partly), "Enabled", "Selectable", "Editable", "Tooltip", and "More properties ▸" (UX-ITEM-006). Alt+Right opens the focused row's details and Alt+Left closes them (Ctrl+Left and Ctrl+Right stay word moves in the field). The combo's "Starts on" (`currentIndex`) is an inspector row, not part of the editor.

**UX-ITEM-004** `M4.4` `[S K T]` Tree widget: two tabs, **Items | Columns**. Columns is a list editor of the header texts (at least one column: "A tree needs at least one column."). Items is a tree-shaped list editor: each row has one field per column (up to 3 visible; more scroll sideways inside the editor); Tab nests the row under the previous row and Shift+Tab moves it out one level (the outline's grammar, UX-OUT-004); Ctrl+Tab and Ctrl+Shift+Tab leave the list. Left at the start of a field moves to the previous column's field, Right at the end to the next. Enter on the last row adds a sibling. Alt+Up and Alt+Down move a row among its siblings, with its children.

**UX-ITEM-005** `M4.4` `[S K T]` Table widget: three tabs, **Cells | Rows | Columns**. Rows and Columns are list editors of the header texts; their count is the table's row and column count ("Rows" adding a row adds a table row). Cells is a grid: arrow keys move, typing replaces the cell's text, Enter or F2 edits the cell keeping its text, Delete clears the cell, Ctrl+V of tab-separated text fills from the current cell. A cell's details (the UX-ITEM-003 list) open with Alt+Right.

**UX-ITEM-006** `M4.4` `[S]` "More properties" of an item, row or column header shows a short property list using the same editors as the inspector (UX-PED): Text, Tooltip, Status tip, What's this, Font, Background, Foreground, Text alignment, Check state, Flags. It reuses the inspector's editor registry; no item-only editors exist.

**UX-ITEM-007** `M4.4` `[T A]` Every change is live on the canvas. One editor session is one undo step, "Edit items of {name}" (`SetItems` with a merge key per widget and session). Esc reverts the session and leaves no step. Closing keeps it. Selecting another widget or a structural command closes it and keeps.

**UX-ITEM-008** `M4.4` `[S]` Model-based views (List, Tree, Table and Column view, Undo view) have no items in the file. Enter or double-click on one says, in the status bar: "This view gets its rows from your code. To type rows here, change it to a list widget (Change to)." No popover opens.

**UX-ITEM-009** `M4.4` `[S]` The outline's text column shows the first items for item widgets ("Combo box “Small, Medium, …”"), and the canvas signature check covers tree item texts (ticket M4b), so a realize patch that drops a tree item is caught.

#### 13.1.6 Copy tables

**Undo names** (UX-M4-006):

| Action | Undo name |
| --- | --- |
| Insert from the catalog | "Insert {friendly name}" ("Insert combo box") |
| Insert page / step / window | "Insert page" |
| Delete page | "Delete page" |
| Move page | "Move page" |
| Start on this page | "Change start page" |
| Dock side | "Dock to the {side}" |
| A field or popover session on one property | "Change {label in lower case}" ("Change echo mode") |
| A popover session on a font, palette or icon | "Change font of {name}", "Change palette of {name}", "Change icon of {name}" |
| Translation fields | "Change translation of {label in lower case}" |
| Add / rename / remove custom property | "Add custom property {name}", "Rename custom property", "Remove custom property {name}" |
| Item editor session | "Edit items of {name}" |
| Reset | "Reset {label in lower case}" |

**Refusals and warnings** (every sentence a lane may show for M4; a new one needs a spec change):

| Where | Sentence | Colour |
| --- | --- | --- |
| Insert target | "A wizard page can only go into a wizard." / "In a main window, a dock widget goes on one of its sides." | status + `ov.problem` |
| Insert search, Enter with no result | "Nothing to insert. Change the search or press Esc." | status |
| Page commands | "This is already the first page." / "This is already the last page." | tooltip |
| Number | "Use a number from {min} to {max}." / "Type a number, like 12." | `fb.error` |
| Char | "Type one character." | `fb.error` |
| Date / time | "Use a date like 10/28/2026." / "Use a time like 2:30 PM." | `fb.error` |
| Colour | "Use a colour like #1A7F37." | `fb.error` |
| Gradient | "A gradient needs at least two colours." | `fb.error` |
| Tree columns | "A tree needs at least one column." | `fb.error` |
| Custom property names | the four sentences in UX-PED-061 | `fb.error` |
| Object reference | "No widget called “{name}” on this form." | `fb.error` |
| Shortcut clash | "{actionName} already uses {keys}." | `fb.warning` |
| URL | "This doesn't look like a web or file address." | `fb.warning` |
| Canvas can't show | "Saved in the file. The canvas can't show this value." | `fb.warning` |
| File path picture | "Loaded from a file path. A packaged app may not find it." | `fb.warning` |
| Model views | "This view gets its rows from your code. To type rows here, change it to a list widget (Change to)." | status |

#### 13.1.7 Deferred from M4, with owners

| Item | Owner |
| --- | --- |
| Main-window parts in the catalog (menu bar, toolbar, status bar), menus, actions, action groups, button groups (R3 113–119) | M5.1 |
| Promotion and a project-wide "Your widgets" registry (R3 123) | M5.4 |
| Adding a picture to a resource file, resource-only pictures, the Problems fix for file paths (pain 9) | M5.2 |
| Style sheet editor (the `styleSheet` row stays raw) | M5.3 |
| Buddy and tab-order pickers (object-reference rows stay text fields) | M5.6 |
| Speed harness rows for the M4 paths (UX-M4-007) | M4.5 |
| Drops and moves inside the wide copy of Two widths | M9.5 (unchanged) |
| Items for model-based views | Won't do: the model lives in user code (UX-ITEM-008) |

### 13.2 M5: main windows, resources, styling, custom widgets, templates

**UX-M5-001 Main windows (M5.1).** "Type here" on menu bars, menus and toolbars (toolbars too, unlike the spike). An **Actions** tab joins the left pane (Outline | Insert | Actions when the form is a main window); actions drag onto menus and toolbars, and the action inspector lists "Used in File menu, toolbar". A toolbar refuses a widget the `.ui` schema cannot store with a sentence, never silently (pain 17).

**UX-M5-002 Resources (M5.2).** Image properties accept only resources. The icon picker shows the project's resources with thumbnails and an "Add image…" button that copies the file into the project's resource folder and `.qrc`. A raw file path in an older file is a Problems row with the fix "[Add to resources]" (pain 9).

**UX-M5-003 Style (M5.3).** "Style sheet…" opens a bottom drawer under the canvas with the CBCS code editor (CSS highlighting, syntax check, resource and colour pickers). Every selector's matches are outlined live on the canvas in dashed `ov.select` with a match count per rule, and "no match" is marked (pain 8). Theme roles are a short list in form settings (accent, base font size, corner radius), not per-widget colours (delighter 12).

**UX-M5-004 Custom widgets (M5.4).** "Use my own class…" asks for class name, base class and Python module path, with validation that the module path looks importable. The canvas draws a sized stand-in (UX-RUN-004); the real class appears only in Preview; a short note explains that the class's code runs only in the preview process.

**UX-M5-005 Preview options, settings, templates (M5.5a–c).** The Aa menu gains Style (Fusion and the styles available on the runtime) and device profiles; Preview gets Save image and Print; "View code" shows the generated Python read-only in a split beside the canvas. Form settings is one dialog. Start v2 adds saved templates (UX-START-007).

**UX-M5-006 Shortcut parity and keyboard index (M5.6).** Help > Form designer keys opens a searchable page generated from the shortcut registry (so it can never drift from the real bindings). Designer keys that are remapped here (F3–F6, Ctrl+0, Ctrl+R) are listed with their Code Studio equivalent.

---

## 14. Heuristic review of the spike build

Method: the 22 spike screenshots, plus five offscreen captures of the spike made for this review at 1100 × 640 and 1366 × 768 (top row selected, outline focused, dark notes), judged against Nielsen's ten heuristics, Gestalt grouping, density and hierarchy, and consistency with CBCS. The spike is a strong start: the start screen, the overlay concept, the plain-words sizing and the realizer that moves live widgets are all kept. The issues below are what this spec fixes.

| # | Issue | Screenshots | Heuristic | Fixed by |
| --- | --- | --- | --- | --- |
| 1 | The name chip covers the field above the selection, and the size badge covers the field below | `workbench-light`, `workbench-dark`, `dark-layout`, `quick-insert`, `empty-group`; extra `top-row-selected` | Aesthetic and minimalist design; Gestalt figure–ground | CHIP-001 … 004 |
| 2 | Chips pile up at a container's top-right corner and cover its title | `empty-group`, `layout-selected` | Gestalt proximity (labels attach to the wrong thing) | CHIP-002, CHIP-003 |
| 3 | Drop feedback tints the whole container (washing out every field) and its chip covers the target field, in internal words ("Into verticalLayout · position 3", "New row 3") | `drag-box`, `drag-grid`, `drag-form` | Match with the real world; visibility | DND-003, DND-004, COPY-006 |
| 4 | Sizing vocabulary is inconsistent: the badge says "Auto × Auto" while the inspector offers Hug/Fill/Fixed with nothing chosen; "Minimum 0 × 0" placeholders read as values (pain 2 again); multi-select offers only Hug and Fill | `dark-layout`, `layout-selected`, `inspector-size`, `wrap-menu` | Consistency; error prevention | SIZE-001 … 006, INSP-007, INSP-011 |
| 5 | All properties lists irrelevant rows first with raw names, and some values don't match the widget (focusPolicy "No focus" and mouseTracking on a line edit) | `inspector-size` | Match with the real world; trust | INSP-008 |
| 6 | It is a separate application, not a CBCS tab: own menu bar, back-to-Start, Save button, status bar, 13 px / 28 px / 6 px metrics; and at ChoreBoy sizes the page clips under a scroll bar because no pane collapses and zoom never fits | all workbench shots; extra `small-1100x640` | Consistency and standards; flexibility | PRIN-008, SHELL-001 … 006, GRID-001 … 003, RESP-001 … 007 |
| 7 | Controls clip or elide their own values ("All non fixed fields grov", "Left, Leading…rtical centre"), the label-alignment combo has a different style, and breadcrumbs truncate in the middle | `window-selected`, `drag-form`, `empty-group`; extra `top-row-selected` | Aesthetic design; recognition | INSP-001, INSP-003, INSP-009 |
| 8 | Overlay marks sit on the content they annotate: buddy dots cover the last letter of labels and fields are tinted; tab-order badges sit inside fields; the button box gets no tab badge | `buddy`, `tab-order` | Visibility of what matters; accuracy | OVL-004, OVL-007 |
| 9 | Two widths draws the wide copy smaller than the narrow one | `two-widths` | Match with the real world | WIDTHS-001 … 003 |
| 10 | Developer and internal text reaches users: "edit 62.0 ms" (over the 16 ms edit budget), "open 118.6 ms", "Coming in the logic phase", "ui_ module", "(Expanding)" in the why sentence | `empty-group`, `workbench-dark`, `inspector-behavior`, `inspector-data`, `workbench-light` | Speak the user's language | FEED-006, COPY-002, COPY-006, EMPTY-006 |
| 11 | No accessible names anywhere; the focused outline row looks the same as an unfocused selected row; the Shortcut field's placeholder "Ctrl+O" looks like a value | extra `focus-outline`; `main-window-menu` | Visibility of system status; accessibility | A11Y-002, A11Y-004, COPY-006 |
| 12 | Templates create `label_2`, `label_3`; the Behavior tab is a three-combo form plus an "Add connection" button with no visible list; the "S M L" segments and the ⇆ icon are unlabeled | `workbench-light`, `inspector-behavior` | Recognition rather than recall | START-004 (templates name their widgets), INSP-013, SCALE-001 |
| 13 | The table dialog's absolute database path dominates; the preview date reads "1/1/00" | `from-table` | Aesthetic design; match with the real world | TABLE-001 |
| 14 | The empty-form drop zone fills only a band at the top of an empty window | `empty-form` | Affordance | EMPTY-001 |

What the spike gets right and this spec keeps: whole-card click targets on Start; painted wireframes; the dot-grid backdrop and page card; faint layout frames that strengthen on focus; springs drawn as springs; gap bars and margin bands; the "why is it this size?" paragraph; Reset that deletes the line; overlays with an Esc banner; Type here menus; "Used in menuFile, toolBar" on actions; the runtime-palette canvas in dark mode; the realizer reusing live widgets.

---

## 15. Changes to earlier design documents

| Earlier text | Change | Reason |
| --- | --- | --- |
| SPIKE_DESIGN §3 top bar: Back to Start, file name, Design / Tab order / Buddies segmented control, Save | Removed: the shell owns file name, save, navigation; overlays are toggles | PRIN-008, OVL-001 |
| SPIKE_DESIGN §4 hover chip, selection chip plus size badge | Hover has no chip; one selection label placed by the solver | CHIP-001 … 003 |
| SPIKE_DESIGN §4 drop indicator "the container tints" | No tint; frame plus one indicator | DND-003 |
| SPIKE_DESIGN §4 Alt-click selects the parent layout; Alt-drag duplicates; Alt 1 px gap steps | Esc for parent; Ctrl-drag copies; Shift snaps, default 1 px | Linux window managers take Alt+drag; SEL-002, MOVE-002, RESIZE-007 |
| SPIKE_DESIGN §2 type 13 px body, 28 px controls, 6 px control radius | 12 px body, 24 px controls, 4 px radius (shell metrics) | PRIN-008, TYPE-001, GRID-002, GRID-003 |
| SPIKE_DESIGN §2 accent brightens in dark mode on the form | Form-surface overlay colours are constant across chrome themes | TOK-003 |
| SPIKE_DESIGN §6 and LOGIC_DESIGN §2.12: Ctrl+G wrap, Ctrl+R preview/Try, Shift+F2 rename, Ctrl+Shift+F form logic search, Cmd+1/2/3 modes | Ctrl+Shift+G, Ctrl+Shift+R, F2, Ctrl+F, F7/F8 overlays; Ctrl+1 … 6 are Designer's layout keys | Shell collisions (Go to Line, Go to Symbol, Stop, Find in Files); KEY-004, KEY-005 |
| SPIKE_DESIGN §6 F2 edits text on the canvas | Enter edits text; F2 renames everywhere | Same meaning as the shell's Rename Symbol; TEXT-001 |
| SPIKE_DESIGN §7 Behavior/Data stubs say "arrives in the logic phase" | No milestone text in user builds; Data hidden until M8 | EMPTY-006 |
| SPIKE_DESIGN §2 sizing "Auto" state | Outlined default word with a caption; three words only | SIZE-002, SIZE-003 |

---

## 16. Open items

### 16.1 Question for the product owner

1. **Ctrl+R in a form tab.** Designer users press Ctrl+R to preview; in Code Studio Ctrl+R is "Go to Symbol in File". This spec keeps the shell meaning (Ctrl+R jumps to a widget by name) and puts Preview on Ctrl+Shift+R, so every CBCS tab treats Ctrl+R the same way. The alternative is to let Ctrl+R preview inside form tabs only, which helps Designer veterans and breaks shell consistency. Recommendation: keep the spec (shell meaning), and list Ctrl+Shift+R in the Designer key index. Decide only if you disagree.

### 16.2 Facts needed from the M0.7 probe (not owner decisions)

- The default `QStyle`, palette and application font that a CBCS-run app gets on ChoreBoy with FreeCAD 1.1 (UX-ISO-001 follows the probe).
- Whether the ChoreBoy window manager takes Alt+click, Alt+drag, Alt+F7/F8 and Ctrl+Alt+arrows (UX-KEY-001 already avoids all of them; the probe confirms nothing else is taken, such as F7 or F8).
- Screen size and device pixel ratio of ChoreBoy installs (the C tab size in 12.2 assumes 1366 × 768 at 1.0).
