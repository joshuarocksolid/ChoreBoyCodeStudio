# Troubleshooting by Symptom

This chapter is organized by what you **see**, not by technical cause. Find your symptom,
check the likely causes, and apply the fix. If nothing here helps, generate a Support
Bundle (see "Diagnostics & support tools") so a supporter can help.

## The status bar shows "Runtime issues"

**Symptom:** The status bar reads "Runtime issues (N/8 checks)" instead of "Runtime ready
(8/8 checks)".

**Likely cause:** One of the startup capability checks failed (for example, a settings or
log folder is not writable, or a runtime component did not load).

**Fix:**

1. Open **Tools > Runtime Center** for a plain-language explanation of which check
   failed.
2. Follow the suggested next step shown there.
3. If a folder is not writable, the editor falls back to a temporary location and logs the
   active path — check the application log via **Help > Open Application Log**.

## A run does nothing, or fails immediately

**Symptom:** Pressing Run produces no output, or the run fails instantly.

**Likely causes & fixes:**

- **No active file** — "Run Active File" needs a file open. Open one, or use **Run
  Project** (`Shift+F5`).
- **Wrong entry file** — Run Project uses the project's entry file. Set the correct one
  by right-clicking it in the tree and choosing **Set as Entry Point**.
- **An error in your code** — open the **Problems** panel and the **Run Log**; the
  traceback names the file and line.

## "Cannot load Gui module in console application" (FreeCAD)

**Symptom:** A FreeCAD script fails with a message about not loading the Gui module, or
`FreeCAD.ActiveDocument` is `None`.

**Likely cause:** Runs execute **headless** — there is no FreeCAD GUI or active document.

**Fix:** Edit and save the macro in Code Studio, then run it **inside FreeCAD** where the
GUI and document exist. Use Code Studio's runs only for headless-safe code. See "FreeCAD
workflows & headless limits" and **Tools > FreeCAD Headless Notes**.

## Breakpoints do not pause

**Symptom:** You set breakpoints and start Debug, but execution does not stop.

**Likely causes & fixes:**

1. The breakpoint is on a non-executable line (blank or comment) — move it to a real
   statement.
2. The file was not saved before debugging — save and retry.
3. You started the wrong mode — confirm Active File vs Project.
4. **Environment limitation** — on some setups the debug channel may not deliver pause
   events. Fall back to a normal **Run** and read the traceback in the Run Log; this
   diagnoses most issues quickly. See "Debugging".

## An import is flagged as unresolved

**Symptom:** A `import yourpackage` line shows a problem (for example, `PY200`).

**Likely causes & fixes:**

- **`src/` layout** — mark your source folder as a **Sources Root** (right-click it in
  the Explorer). Imports beneath it then resolve.
- **Third-party package not vendored** — add it with **Tools > Add Dependency...**.
- **Module not available in the runtime** — use **Tools > Analyze Imports** for a
  classification of the cause, and **Refresh Runtime Modules** after vendoring.

## Completion or navigation seems wrong or stale

**Symptom:** Completions or go-to-definition results look outdated.

**Fix:** Use **Tools > Rebuild Intelligence Cache**. The index is only an accelerator;
rebuilding refreshes it. Results are tied to your current text, so newer edits always win.

## A file change on disk is not reflected

**Symptom:** A file changed outside the editor but the tab shows the old content.

**Fix:** The editor offers to reload externally-changed files and records a Local History
checkpoint when you do. Choose to reload, or use the Explorer's refresh control.

## Packaging fails or warns

**Symptom:** The packaging wizard reports a problem.

**Likely causes & fixes:**

- **Output overlaps the project** — choose an output folder **outside** the project.
- **Missing entry file** — set a valid entry file.
- **Missing vendored dependency** — a dependency is listed in `cbcs/dependencies.json`
  but its files are absent from `vendor/`; re-add it. See "Managing dependencies".

## A plugin misbehaves

**Symptom:** A plugin causes errors or instability.

**Fix:**

1. Open **Tools > Plugin Manager** and **Disable** the plugin, or tick **Safe mode** to
   start with all plugins off.
2. The application auto-quarantines plugins that fail repeatedly; re-enable explicitly
   after fixing.
3. Remember plugin code runs in a separate process — it cannot crash the editor itself.

## I lost unsaved work after a crash

**Symptom:** The application closed unexpectedly and you had unsaved edits.

**Fix:** Reopen the file and use **File > Open Recovery Center...** to compare and restore
your draft. For saved versions, use **Local History...**. See "Local History & recovery".

## The editor will not start

**Symptom:** Double-clicking the launcher does nothing, or the window never appears.

**Likely causes & fixes:**

- The runtime may be initializing — wait a few seconds.
- Check the application log at `~/choreboy_code_studio_state/logs/app.log` (or the
  fallback under the temp folder) for a startup error.
- If a previous instance is stuck, the single-instance guard may be blocking a new one;
  ensure the old window is fully closed.
- Start in **safe mode** (Plugin Manager) to rule out a misbehaving plugin.

## Completion or hover shows nothing

**Symptom:** Pressing `Ctrl+Space` or hovering produces no suggestions.

**Likely causes & fixes:**

- Confirm **Enable completion** is on in **Settings > Intelligence**.
- The symbol index may be building or stale — run **Tools > Rebuild Intelligence Cache**.
- For third-party or runtime modules, confirm they are importable (**Tools > Refresh
  Runtime Modules**) or vendored (**Add Dependency**).

## Find in Files returns nothing

**Symptom:** A search you expect to match returns no results.

**Likely causes & fixes:**

- Check the match toggles: **Aa** (case), **W** (whole word), **.\*** (regex). A stray
  whole-word or case toggle is the usual cause.
- The files may be excluded in **Settings > Files**. Remove the relevant exclude pattern
  to include them.

## Formatting did nothing

**Symptom:** **Format Current File** reports no change.

**Likely cause:** The file is already Black-formatted, so formatting is a no-op — that is
correct behavior, not a failure. If a Python file with obvious issues is not formatted,
confirm formatter dependencies are present (**Tools > Runtime Center**).

## The theme is hard to read

**Symptom:** Text or highlights are low-contrast.

**Fix:** Switch to a clearer theme in **View > Theme** — the two **High Contrast** modes
maximize legibility. If you previously customized syntax colors, clear the override for
the affected token in **Settings > Syntax Colors**. See "Themes in depth".

## A setting did not take effect

**Symptom:** Changing a setting had no visible effect.

**Likely causes & fixes:**

- Confirm you saved the Settings dialog.
- Check **scope**: a global value may be overridden by a **project** setting. The status
  bar shows **(project overrides)** when the project has its own settings. Reset the
  project override if needed. See "Settings overview".

## The editor is slow on a huge file

**Symptom:** Typing lags in a very large file.

**Fix:** This is expected — the editor automatically reduces highlighting detail past size
thresholds to stay responsive. You can tune the thresholds in **Settings > Intelligence**.
See "Editing files".

## Still stuck?

Generate a **Support Bundle** (**Tools > Generate Support Bundle**) and share it. It
contains logs, project metadata, the latest run log, and a runtime snapshot — enough for a
supporter to help without reproducing your exact session.
