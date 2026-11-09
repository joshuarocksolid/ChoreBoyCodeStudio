# Designer resave allowlist

`ALLOWLIST.json` is the list `test_designer_resave_diff.py` reads. Each entry names one file under this directory and a regular expression that must match a changed line. The test fails when a changed line has no entry, and it fails when an entry matches nothing.

The list is empty. `write(read(file))` matches Qt Designer 6.8.3 bytes for all 209 resaved forms (measured 2026-10-22).

Appendix E says we keep data Designer drops. Those constructs are not in this corpus, because Designer already removed them before the files were stored here. They are not entries.

| Appendix E row | Why it is not an entry |
| --- | --- |
| `<float>` | Designer drops the property. No resaved file still has a `<float>`. |
| Unknown dynamic enums and sets | Designer drops them. No resaved file still has one. |
| `<iconset>` `resource` and `alias` | Designer drops both attributes. No resaved iconset still has them. |
| Comments, `<script>`, `<widgetdata>`, `<propertyspecifications>`, `<images>`, `<addpagemethod>` | Designer drops them. No resaved file still has them. |

Add an entry only when a resaved file still differs because we kept one of those. The `file` path is relative to this directory. The `pattern` is a Python regular expression matched against one `+` or `-` diff line, and it must not match the empty string.
