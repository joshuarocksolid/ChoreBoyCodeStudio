The M6 shop project (UX_SPEC 12.3, K24 to K26). Lanes extend it in their own subfolders.

- `forms/sale.ui`: a dialog `Sale` with `nameEdit`, `phoneEdit`, `clearButton`, `printButton`, `saveButton`, `cancelButton` and a `QDialogButtonBox` connected to `accept()` and `reject()` (with `<hints>`).
- `forms/sale_window.py`: class `SaleWindow` with one method, `show_total`, and a trailing comment. The file uses CRLF line endings; keep them (a test asserts the bytes).
- `forms/designer_made.ui`: connections with `<hints>`, a layout connection (`wholeWords` to `verticalLayout.invalidate()`), and an event stored in two places (`goButton.clicked()` is a native connection and a `cbcsOnClicked` list).
