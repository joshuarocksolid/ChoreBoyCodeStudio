# `self.ui` after Eject to code

Eject copies the form's data methods into the window file and binds them onto `self.ui`. The window methods (`load_record`, `save_record`, and the others listed in the eject dialog) call those `self.ui` methods. A method you write in the window file can call the same names.

The public names are:

| Method | What it does |
| --- | --- |
| `cbcs_open(key=None)` | Load the key list and show one record, or start a new one |
| `cbcs_save()` | Save the open record. Returns True when the row is written |
| `cbcs_delete()` | Ask, then delete the open record |
| `cbcs_new()` | Start a blank record |
| `cbcs_revert()` | Put the widgets back to the last loaded row |
| `cbcs_reload()` | Revert, then show the same record again |
| `cbcs_first()` `cbcs_previous()` `cbcs_next()` `cbcs_last()` | Move through the loaded keys |
| `cbcs_find()` | Ask for text and narrow the key list |
| `cbcs_show_all()` | Drop the find filter |
| `cbcs_load_lookups(fields=None)` | Fill lookup combos |
| `cbcs_read_fields()` | The bound widget values, keyed by column |
| `cbcs_write_fields(row)` | Put a loaded row into the widgets |
| `cbcs_is_dirty()` | True when the widgets differ from the last load or save |
| `cbcs_confirm_leave()` | The unsaved-changes question |
| `cbcs_current_key()` | The open record's key |
| `cbcs_read_lines()` | The lines grid, when the form has one |
| `cbcs_refresh_list()` | Run the list query again |
| `cbcs_open_record(which)` | Open the record form for `"new"` or `"selected"` |

Names that start with `_cbcs_` are private. They can change when the generator changes.

Database access inside these methods is only:

```python
import cbcs_connections
with cbcs_connections.work("shop") as connection:
    ...
```

Import `cbcs_connections` at the call, not with `from cbcs_connections import ...`. Try replaces that module in `sys.modules` before the method runs. A name captured at import time would skip the rollback.
