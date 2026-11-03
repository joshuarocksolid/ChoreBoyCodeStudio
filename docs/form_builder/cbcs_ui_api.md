# Window methods after Eject to code

Eject copies the form's data methods onto the window class. Widgets are `self.ui.<objectName>`. A method you write in the window file calls the same names the eject dialog lists.

The public names are:

| Method | What it does |
| --- | --- |
| `load_record(key=None)` | Load the key list and show one record, or start a new one |
| `save_record()` | Save the open record. Returns True when the row is written |
| `delete_record()` | Ask, then delete the open record |
| `new_record()` | Start a blank record |
| `revert_record()` | Put the widgets back to the last loaded row |
| `reload_record()` | Revert, then show the same record again |
| `first_record()` `previous_record()` `next_record()` `last_record()` | Move through the loaded keys |
| `find_record()` | Ask for text and narrow the key list |
| `show_all_records()` | Drop the find filter |
| `load_lookups(fields=None)` | Fill lookup combos |
| `read_fields()` | The bound widget values, keyed by column |
| `write_fields(row)` | Put a loaded row into the widgets |
| `is_dirty()` | True when the widgets differ from the last load or save |
| `confirm_leave()` | The unsaved-changes question |
| `current_key()` | The open record's key |
| `read_lines()` | The lines grid, when the form has one |
| `add_line()` `delete_line()` | Add or remove a line |
| `refresh_list()` | Run the list query again |
| `open_record(which)` | Open the record form for `"new"` or `"selected"` |

Helpers on the same class start with `_` and have no `_cbcs_` prefix. They can change when the generator changes.

Database access inside these methods is only:

```python
import cbcs_connections
with cbcs_connections.work("shop") as connection:
    ...
```

Import `cbcs_connections` at the call, not with `from cbcs_connections import ...`. Try replaces that module in `sys.modules` before the method runs. A name captured at import time would skip the rollback.
