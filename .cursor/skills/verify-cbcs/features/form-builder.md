# Form builder

A `.ui` file opens as a form tab on PySide6. Design shows the form name and structure. View XML is the same code editor used for other text, with the XML grammar, so AT-32 step 3 (open `.ui` and see XML highlighting) is done through View XML. On PySide2 the file stays a text tab.

<!-- dune-owners: form-builder -->

## Sub-features

- `form-open` opens `*.ui` on the form surface when the form builder is installed.
- `form-view-xml` toggles Design and XML from `#formBuilder.viewXml` or View → Markdown: Toggle Preview (Ctrl+Shift+V).
- `form-save` writes the opened bytes until the document changes, and writes typed XML while XML is showing.
- `form-discard-xml` leaves invalid XML with Discard XML edits and returns the last valid design.

## How to get to it (user POV)

- Open a `.ui` file from the project tree on FreeCAD 1.1 (PySide6).
- The tab shows `#formBuilder.surface`.
- View XML, or Ctrl+Shift+V, shows the file text in `#shell.editorTabs.textEditor`.

## Driving it with control-cbcs

Preconditions:

- PySide6 runtime. Doctor passed.
- A project `.ui` file, for example `invoice.ui`.

- **Open.** Open the `.ui` file from the tree. `#formBuilder.name` shows the form name. `#formBuilder.structure` lists the widgets.
- **View XML.** `control-cbcs trigger "$SID" shell.action.view.markdownTogglePreview`. `#formBuilder.viewXml` is checked. `#shell.editorTabs.textEditor` is visible and uses XML highlighting (AT-32 step 3).
- **Back to Design.** Trigger the same action again. The structure tree is visible.
- **Invalid XML.** Type broken XML, switch toward Design, and the banner `#formBuilder.xmlBanner` stays with Discard on `#formBuilder.discardXml`.

Handles already used by the driver:

| Handle | What |
|--------|------|
| `formBuilder.surface` | Form tab |
| `formBuilder.name` | Form name |
| `formBuilder.viewXml` | View XML toggle |
| `formBuilder.structure` | Structure tree |
| `formBuilder.xmlBanner` | View XML notice box (frame; Discard sits inside it on errors) |
| `formBuilder.xmlBannerText` | View XML notice text |
| `formBuilder.discardXml` | Discard XML edits |

## Gotchas

- Ctrl+Shift+V is the shell toggle-source action. The form does not add a second shortcut.
- Saving an unchanged form must not rewrite bytes the builder would normalize.
- Invalid XML has no Design view until the text parses or the user discards it.
- PySide2 opens `.ui` as text with `#shell.editorTabs.uiTextHint` and `#shell.editorTabs.uiTextHintDismiss`.
