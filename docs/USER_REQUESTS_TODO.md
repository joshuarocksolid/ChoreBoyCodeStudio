# User-Requested Updates (TODO)

Backlog of feature requests from users. Tracked separately from the main `docs/TASKS.md` backlog.

---

## Status legend

- `DONE` — implemented and validated
- `IN PROGRESS` — currently being worked on
- `TODO` — not started

---

## Requests

### 1. Main window starts maximized

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Request** | Main window should maximize on startup (e.g. `window.showMaximized()` instead of `window.show()`). |
| **Location** | `run_editor.py` line 25 |
| **Notes** | Implemented: `window.showMaximized()` in `_start_editor()`. |

---

### 2. Syntax highlighting color customization

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Allow users to pick/customize the colors used by the syntax highlighter. |
| **Notes** | User would like control over editor color scheme. |

---

### 3. Keyboard shortcut customization

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Allow users to customize keyboard shortcuts. |
| **Key examples (LibrePy-like)** | |
| | Ctrl+D — duplicate line |
| | Ctrl+B — delete line |
| | Ctrl+/ — toggle comment |
| | Tab — indent (user could learn to use instead of Ctrl+I) |
| **Notes** | User finds Ctrl+/ for comments harder with one hand; prefers shortcuts that match LibrePy workflow. Customization would let users adapt to their preferences. |

---

### 4. Plugin / modular extension architecture

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Requested by** | Marcus Zimmerman |
| **Request** | Build the IDE with a modular plugin system so technically-inclined users can create and share their own extensions, rather than merging niche features into the core product. |
| **Rationale** | Keeps the core product focused on what benefits the majority (≥ 50%) of users. Minority-interest features ship as optional plugins instead of cluttering the mainline. User cites Classic Accounting as an example where a plugin model from the start would have let businesses build custom flows without bloating the base product. |
| **Trade-offs noted by requester** | Requires exposing stable internal APIs/hooks for plugin authors; maintaining backward compatibility with those APIs is ongoing work. |
| **Notes** | Large architectural decision — would need a formal design pass (plugin lifecycle, hook points, sandboxing, distribution mechanism) before implementation. Worth revisiting once the core MVP feature set is solid. |

---

## Cross-cutting

- UI changes must validate in both light and dark themes (see `.cursor/rules/ui_light_dark_mode.mdc`).
- Prefer settings persistence via `app/persistence/settings_store.py` where applicable.
