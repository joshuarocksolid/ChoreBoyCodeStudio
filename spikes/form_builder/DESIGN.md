# Form builder: interaction and visual design

The goal is a builder where a first-time user says "oh, this is easy" and a Qt Designer veteran does not want to go back. It is calm, dense but legible, and it never asks for a mode or a dialog when a gesture or a sentence will do. Every edit still goes through the command log; the canvas shows real widgets.

## 1. Principles

1. **The drop is already laid out.** Nothing is placed at a pixel. Every drop lands in a layout slot, and the slot is drawn before you let go.
2. **Words before property names.** Hug, Fill, Fixed and Gap are the vocabulary. The Qt name is shown underneath in small type for the veteran.
3. **Show the structure only where you are looking.** Layout frames are faint everywhere and become explicit (labels, margins, gaps, cell numbers) only for the hovered or selected container.
4. **No sticky modes.** Tab order and buddies are temporary overlays with a banner that says how to leave them (Esc). Connections live in the inspector.
5. **The keyboard is first-class.** Everything in the outline works without a mouse, and rename never steals focus.
6. **The canvas is the app.** Canvas widgets use the runtime style (Fusion, standard light palette) and never inherit the builder's theme or style sheet, so the builder's dark mode cannot lie about the app.

## 2. Visual language

**Type scale** (system UI font, px): 10.5 overline (uppercase, semibold, +0.6 tracking) · 12 secondary · 13 body · 15 panel title (semibold) · 22 screen heading · 30 hero. Numbers in the inspector use tabular figures where the font offers them.

**Spacing grid**: 4 px base. 4 / 8 / 12 / 16 / 24 / 32 / 48. Controls are 28 px tall, rows in lists 26 px. Radii: 6 controls, 8 popovers and chips, 12 cards and the page.

**Colour tokens** (`theme.py`). The chrome follows the OS through `QStyleHints.colorScheme()` and updates live when it changes; View > Appearance overrides it.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `bg` | `#F5F6F8` | `#141619` | window chrome behind panels |
| `surface` | `#FFFFFF` | `#1C1F24` | panels, cards |
| `surface_alt` | `#F0F2F5` | `#252930` | hover rows, input fills, segmented track |
| `canvas` / `dots` | `#E9EBEF` / `#D3D8DF` | `#101215` / `#24282F` | canvas backdrop with a 16 px dot grid |
| `border` / `border_strong` | `#E2E5EA` / `#CBD1D9` | `#2A2E36` / `#3A3F49` | hairlines |
| `text` / `muted` / `faint` | `#16181D` / `#5C6370` / `#8C93A0` | `#ECEEF2` / `#A2A9B6` / `#6C7380` | |
| `accent` / `accent_soft` / `on_accent` | `#3D6BF0` / `#E7EDFE` / `#FFFFFF` | `#6F96FF` / `#1F2C4A` / `#0B1020` | selection, insertion line, primary button |
| `layout` | `#8B5CF6` | `#A78BFA` | layout frames and their chips |
| `gap` | `#E0418F` | `#F472B6` | gaps, margins, stretch numbers (Figma's spacing pink) |
| `tab` | `#F59E0B` | `#FBBF24` | tab-order badges and flow line |
| `buddy` | `#0E9F77` | `#34D399` | buddy links |
| `warn` / `danger` / `ok` | `#B86E00` / `#D23B3B` / `#16884A` | `#F0B44C` / `#FF7A7A` / `#4ADE80` | problems, save state |

High-contrast light and dark keep the same roles with 2 px focus rings.

**Iconography**: no asset files. `icons.py` paints 16 px glyphs with `QPainter` from 1.5 px strokes in the current text colour: one glyph per widget class (a button is a pill, a line edit a box with a caret, a grid layout four squares, a spacer a spring) plus a small UI set (chevrons, plus, undo, play, database). Glyphs are cached per colour and device pixel ratio. QSS arrows and check marks are rendered by the same painter into a per-theme cache folder.

**Elevation**: one level only. Cards and the page get a soft painted shadow; popovers get a 1 px border and the same shadow. Nothing else floats.

## 3. Screens

### Start screen
A centred column, max 1080 px. Hero line "What are you building?" and one sentence. Three groups of cards with painted wireframe thumbnails:

- **Templates**: Data-entry form, List and detail, Table with search, Dialog with buttons.
- **Start blank**: Widget, Main window, Dialog. Each already has a layout.
- **From your data**: Build a form from a table (database glyph → form wireframe), and Open a .ui file.

A whole card is the click target (no "Use this" buttons). Hover lifts the border to `accent`. A right rail lists recent files (from `QSettings`) with an empty state when there are none, and a short "keys worth knowing" card.

### Build from a table
One dialog, three columns: database and table list on the left, a mapping table in the middle (Include, Column, Type, Widget as a drop-down, Label as editable text), and a live preview of the resulting form on the right, rebuilt with the same realizer as the canvas. The primary button says what it will do: "Create form with 6 fields".

### Workbench
```
+--------------------------------------------------------------------------------+
| < Start  invoice.ui *     [Design|Tab order|Buddies]   - 100% +  Aa  W  Preview |
+--------------+--------------------------------------------------+--------------+
| OUTLINE    / |  . . . . . . . . . . . . . . . . . . . . . . . . | [] name  ... |
| > Form       |  .   +-- Invoice ------------------------------+  | Properties   |
|   = form     |  .   | Name *   [_________________________]   |  | Behavior Data|
|     Aa label |  .   | Email    [_________________________]   |> | CONTENT      |
|     [] name  |  .   | Notes    [                         ]   |  | SIZE         |
|   ...        |  .   |                       [OK] [Cancel]    |  |  W Hug|Fill|Fx|
| INSERT       |  .   +----------------------------------------+  |  H Hug|Fill|Fx|
| [filter    ] |  .              640 x 480                        |  why: ...    |
| tiles...     |                                                   | LAYOUT ...   |
+--------------+--------------------------------------------------+--------------+
| Drop into formLayout, row 3 | 0 problems | Saved, ui_invoice.py written | 0.8ms|
+--------------------------------------------------------------------------------+
```
- **Top bar** (custom, 44 px): back to Start, file name with a dirty dot, a segmented control for Design / Tab order / Buddies, zoom (− % +, Ctrl+wheel), preview text size (S M L, pain 12), width (two-widths toggle), Preview (primary) and Save.
- **Left pane**: the Outline (top) and the Insert palette (bottom) in a vertical splitter. Insert is a filterable grid of icon tiles grouped by category; drag a tile to the canvas, or double-click to insert after the selection.
- **Canvas**: dot-grid backdrop; the form sits on a page card with a mini title bar carrying `windowTitle`, and a size readout under it. The page's right and bottom edges are drag handles that resize the form (writes root geometry, one undo step).
- **Inspector**: header with class glyph, inline object-name field and breadcrumb path; tabs Properties · Behavior · Data. With nothing selected the inspector shows the form itself (title, size, tab order list, problems, files), so it is never empty.
- **Status bar**: left is a live sentence about what the pointer will do ("Drop into formLayout, row 3, field column" / "Tab nests, Shift+Tab un-nests"); then a problems chip; then save state ("Saved. ui_invoice.py written"); then the last edit time in faint type.

## 4. Direct manipulation

**Hover**: 1 px accent outline plus a name chip. **Selection**: 1.5 px accent outline, a name chip above (name · class), and a size badge below in plain words: "Fill × Hug · 320 × 24". Click selects the deepest widget, Alt-click the parent layout, Esc walks up, Enter walks down, Shift/Cmd-click toggles multi-select.

**Layout frames**: every layout gets a faint dashed violet frame. The hovered or selected container's layout gets a solid frame and a chip ("VBox", "Grid 3×2", "Form"). An empty layout is drawn at least 32 px high with a dashed fill and "Drop widgets here" (pain 4).

**Selected container details**: margins draw as translucent pink bands with their numbers; gaps draw as pink bars between items with the spacing number. Dragging a gap bar changes `spacing` live (4 px steps; Alt = 1 px, Shift = 8 px) and commits one command on release (delighters 3 and 8). Grid columns show stretch numbers above the columns (delighter 7).

**Resize handles**: only right, bottom and corner, because left and top are owned by the layout. Dragging writes Fixed width or height (policy Fixed, min = max = N). Double-click a handle to go back to Hug. This keeps the Designer muscle memory without pixel geometry (pains 1, 2).

**Drop indicators** (palette drag, canvas move, Alt-drag duplicate):

| Target | Indicator |
| --- | --- |
| Box layout | the container tints, a 3 px accent line with round end caps sits between items, chip "Into verticalLayout · position 3" |
| Grid | the hovered cell (or an empty one past the edge) is a dashed accent rectangle, chip "Row 2 · column 1". Other items do not move until the drop (pain 21). |
| Form | label or field half of a row tints, or a line between rows to insert a new row |
| Splitter / tab / stack | a line between panes; a tab page drops into the current page's layout |
| Container without layout | the whole container tints, chip "Creates a vertical layout" (pain 1) |

**Wrap** (Ctrl+G) opens a small popover of icon tiles at the selection: Vertical, Horizontal, Grid, Form, Group box, Frame. **Unwrap** (Ctrl+Shift+G) puts the children back in place; a toast offers Undo. Neither rebuilds the canvas: the realizer moves the existing widgets.

**Paste and duplicate** insert after the selected widget inside its layout, or at the end of a selected layout, and select the new widget (pain 3). No "break layout" step exists in the normal path; "Remove layout" is in the menu behind a confirm (pain 5).

**Next drop fills the next cell** (delighter 11): inserting into a form layout fills the empty field column of the last row before adding a row; inserting into a grid fills the first empty cell in reading order.

## 5. Modes as overlays

- **Tab order**: amber numbered badges on every focusable widget and a faint flow line between them. Click widgets in the order Tab should visit them; Shift-click starts from that widget. A banner says "Click fields in order. Esc when done. Reset to reading order." The inspector shows the same order as a list (pain 20). New inputs are spliced into the saved order by reading position, not appended.
- **Buddies**: green links from each label to its field; labels without a buddy show a hollow ring. Drag (or click, then click) from a label to a field. "Pair labels automatically" pairs each form-layout label with the field in its row.

## 6. Keyboard map

| Key | Action |
| --- | --- |
| Up / Down | Move in the outline |
| Enter / Esc | Select first child / parent |
| Tab / Shift+Tab | Nest into the previous container / un-nest |
| Alt+Up / Alt+Down | Move within the layout (also on the canvas) |
| F2 | Rename in place (outline or inspector); Enter commits, Esc cancels |
| / | Quick insert after the selection |
| Delete / Backspace | Delete |
| Cmd+C / Cmd+V / Cmd+D | Copy / paste into the layout / duplicate |
| Ctrl+G / Ctrl+Shift+G | Wrap / unwrap |
| Cmd+Z / Cmd+Shift+Z | Undo / redo |
| Cmd+S / Cmd+R | Save .ui and ui_<name>.py / Preview |
| Cmd+1 / Cmd+2 / Cmd+3 | Design / Tab order / Buddies |
| Cmd+= / Cmd+- / Cmd+0 | Zoom in / out / 100% |

## 7. Empty states

Every empty surface says what to do next: an empty form shows "Drop a widget here, or press / to insert one"; an empty layout says "Drop widgets here"; the Behavior and Data tabs say what is coming in the logic phase and what works today (connections).

## 8. Pain points and how this design answers them

| Pain | Answer |
| --- | --- |
| 1 Widgets sit still until a layout command | Every drop is into a layout; dropping into a bare container creates one |
| 2 Size policy is three mysteries | Hug / Fill / Fixed per axis, stretch next to it, and a "why is this size?" sentence |
| 3 Paste refused in a layout | Paste inserts after the selection and selects the result |
| 4 Nested layouts shrink to a line | Empty layouts draw 32 px with "Drop widgets here"; the outline accepts drops and reparents |
| 5 Break layout resizes siblings | Not needed: insert, move, wrap and unwrap work on live layouts; Remove layout asks first |
| 12 Raw pixel sizes | Laid-out children store no geometry; a text-size switch reflows the preview |
| 13 Modes and a dated canvas | Overlays instead of modes, connections in the inspector, a modern theme |
| 14 Spacers stick | Gaps are numbers you drag; stretch is a field on the child |
| 19 Splitter | Splitters take drops between panes and stretch uses the same field |
| 20 Tab order sticks, new widgets append | Esc leaves the overlay; new inputs splice in by reading order |
| 21 Grid drag moves other cells | Only the target cell is shown and only the dragged item changes row and column |
| 25 Rename steals focus | Rename edits in place; status messages never take focus |
| Reset that deletes the line | Every Reset removes the property from the file instead of writing a value |

## 9. Room for the logic phase

The inspector is a tab host. Properties is today's work. Behavior already holds the working Level 1 connection list (signal → receiver.slot pickers filtered by the selected widget's meta-object) above a quiet "Events, rules and checks arrive in the logic phase" block; the State / Checks / Events sections from `LOGIC_DESIGN.md` §2.1 drop in above it. Data shows the "Connect this form to a table" empty state from §2.6. The canvas overlay already has the layering for logic badges (§2.7).
