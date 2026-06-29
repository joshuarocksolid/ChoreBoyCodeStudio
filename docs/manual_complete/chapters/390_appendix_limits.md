# Appendix B — Known Limitations & Behavior Notes

This appendix collects the boundaries and environment-specific behaviors referenced
throughout the manual, in one place.

## Environment constraints

- **No internet, no terminal, no system installation.** Everything runs on the appliance
  using FreeCAD's bundled Python. Dependencies and plugins are added from local files.
- **Restricted execution.** The appliance restricts running arbitrary programs. Features
  that would normally shell out are designed to run in-process or through the runner
  instead.
- **Restricted writable storage; visible folders only.** Hidden (dot-prefixed) folders are
  unreliable, so all metadata uses visible names (`cbcs/`,
  `choreboy_code_studio_state/`).

## FreeCAD / headless

- Runs and debugging execute **headless**: `FreeCAD.ActiveDocument` is `None`, and
  GUI-dependent operations fail with messages such as "Cannot load Gui module in console
  application."
- Some exporters work headless (for example, STL via the Part module); GUI-dependent ones
  do not.
- Recommended workflow: edit/save in Code Studio; run GUI/document macros inside FreeCAD.

## Debugging

- Breakpoint pausing and stepping depend on the runtime. On some setups the structured
  debug channel may not deliver pause events. When that happens, use a normal Run and read
  the traceback as a reliable fallback. This is an environment limitation, not a problem
  with your code.

## Code intelligence

- Editor intelligence is **static** and never executes your project code. Some highly
  dynamic Python cannot be analyzed precisely; in those cases results are clearly labeled
  as approximate or unsupported rather than presented as fact.
- FreeCAD and PySide2 are partly C++-backed; completion for them relies on a shipped
  trusted API index.
- The symbol index is an accelerator. If it is stale or missing the editor still works;
  rebuild it with **Tools > Rebuild Intelligence Cache**.

## Formatting and imports

- Formatting uses Black; import organizing is a style step that does **not** remove unused
  imports or rewrite import paths.
- Tool behavior is configured by project-local `pyproject.toml`, not a separate global
  config.
- Saving always wins: if formatting/organizing fails, your current text is still written
  and you get a warning.

## Plugins (phase 1)

- Pure Python only — no native extensions.
- No hidden metadata directories.
- No terminal or arbitrary-binary assumptions.
- Plugin runtime code runs in a separate host process and returns structured results; it
  does not mutate the editor process or write project files directly for editor-applied
  flows.

## Packaging

- Only the **installable** package profile is supported; the older portable profile is
  retired.
- Package to a folder **outside** the project being packaged.
- The installer launcher is keyed to the package folder path; installed-app launchers are
  fixed to the chosen install directory.

## Performance behaviors

- For very large files, syntax highlighting automatically reduces detail to stay
  responsive (thresholds configurable in **Settings > Intelligence**).
- Search, indexing, health checks, and support-bundle generation run in the background so
  the editor stays responsive.
- Console output is bounded; extremely long runs trim the oldest in-memory output while
  the full per-run log is preserved on disk.

## Editor interaction notes

- **Bottom-panel tabs** (Python Console, Debug, Problems, Run Log) are switched by
  clicking them or by the application's automatic switching (Run Log on output, Problems
  on failure). The application chooses the most relevant panel for you during runs.
- **Preview tabs** mean a single click opens a temporary tab; this is intentional and can
  be turned off in **Settings > Editor**.
- **External file changes** are detected and offered for reload rather than silently
  overwriting your buffer.

## Data and recovery notes

- Drafts and Local History restore into the editor **buffer** first; the file on disk is
  only changed when you save.
- Local History is bounded by retention settings (max checkpoints, retention days, max
  file size, exclude patterns). Very large or excluded files are intentionally not
  tracked, and the UI says so.
- Deleted files are recoverable from **Global History**; deleted items also go to a
  recoverable trash rather than being destroyed immediately.

## Networking notes

- The environment is LAN-only with no general internet access. Design apps to work
  offline; fetch data from local files or LAN services.
- A PostgreSQL server may be reachable on the LAN, but it is an old version with SQL
  feature limits (see "Appendix C — Runtime Capabilities"). SQLite is the recommended
  local database.

## About these notes

This manual documents shipped behavior only. For the underlying runtime facts that drive
these limitations, see the project's `docs/DISCOVERY.md`; for the design rationale, see
`docs/ARCHITECTURE.md`.
