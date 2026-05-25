# TN-SHELL-MW-14 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-14  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 4912–5368 — markdown preview menu/tab orchestration, editor tab lifecycle hooks that touch markdown state, and adjacent editor/completion/indent blocks in the same line range. Cross-read: `app/shell/plugin_activation_workflow.py`, `app/shell/plugins_panel.py`, plugin handlers at `main_window.py:3493–3589` (outside slice; included because slice title covers plugin panels/commands), `app/shell/editor_tab_factory.py` (markdown pane materialization), `app/editors/markdown_editor_pane.py`.

---

## Executive verdict

**Not thermo-clean.** `PluginActivationWorkflow` is a strong extraction — typed snapshots, protocol ports, pure `build_effective_enabled_map` — but **plugin UI and failure UX still live on `MainWindow`**, and markdown mode control is **triplicated** across View menu handlers, tab context menu branches, and the pane’s own toolbar with **no shared workflow**. The assigned line range also embeds ~350 lines of generic editor/completion/indent orchestration (4943–5367) that belong to other slices, confirming the 5,549-line god-object problem. Dominant risks: (1) the next markdown or plugin surface will add another handler/branch on `MainWindow` instead of extending a workflow; (2) `_markdown_panes_by_path` lifecycle is split across factory + shell with defensive `getattr` in release paths; (3) dead `_execute_plugin_runtime_command` pass-through beside the live broker lambda wired at init. Four-theme impact: markdown preview rendering and pane chrome use `ShellThemeTokens` via `MarkdownEditorPane.apply_theme`; plugin manager dialog and `QMessageBox` failure toasts inherit shell stylesheet — any workflow extraction must re-validate Light, Dark, HC Light, and HC Dark for those surfaces.

---

### TN-SHELL-MW-14-1 — Markdown mode switching has three divergent control paths

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** View menu routes through `_set_active_markdown_mode` (`main_window.py:4905-4919`, wired in `menu_wiring.py:77-80`). Tab context menu calls `markdown_pane.set_mode(...)` directly and separately refreshes menu enablement (`main_window.py:5209-5217`). `MarkdownEditorPane` exposes its own mode toolbar buttons that call `set_mode` internally (`markdown_editor_pane.py:76-78`, `184`). Menu path and context-menu path duplicate the same three mode constants without sharing a dispatcher.
- **Code-judo alternative:** `MarkdownTabWorkflow` (or methods on `EditorTabsCoordinator`) with one entry point `set_mode_for_path(path, mode)` / `set_mode_for_active_tab(mode)` used by View menu, tab context menu, and optionally subscribed to `MarkdownEditorPane.mode_changed` to keep shell menu state in sync. Delete `_handle_markdown_show_*` triplet; wire menu callbacks to workflow with mode argument.
- **Suggested remediation:** R2 extraction colocated with editor-tab coordinator; hard cutover menu and context menu to workflow; consider listening to `mode_changed` so shell actions reflect pane toolbar changes without a second source of truth.
- **Tests that would prove fix:** Unit test: workflow `set_mode_for_active_tab` invoked from menu stub and context-menu stub; integration test confirms pane toolbar click updates workflow-visible mode (if shell sync is added).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-14-2 — Three one-line markdown menu handlers are delegator farm noise

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_markdown_show_source_action`, `_handle_markdown_show_preview_action`, and `_handle_markdown_show_split_action` are each a single call to `_set_active_markdown_mode` with a different constant (`main_window.py:4912-4919`). `_handle_markdown_toggle_preview_action` is the only handler with distinct logic (`4921-4926`).
- **Code-judo alternative:** One handler `_handle_markdown_set_mode_action(mode: str)` registered via partial/functor in `menu_wiring.py`, or menu callbacks bound directly to workflow methods — **net four methods down** on `MainWindow`.
- **Suggested remediation:** Fold into finding 1 workflow extraction; do not add a fifth markdown menu handler on `MainWindow`.
- **Tests that would prove fix:** Menu wiring test asserts four action IDs map to one workflow method with expected mode args; `rg "^    def _handle_markdown" app/shell/main_window.py` count drops.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-14-3 — `_markdown_panes_by_path` registry lifecycle split across factory and shell

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** Pane creation and dict insert in `EditorTabFactory._materialize_opened_editor_tab` (`editor_tab_factory.py:177-190`). Teardown/path remapping on `MainWindow`: `_release_editor_widget` scans dict with `getattr(self, "_markdown_panes_by_path", {})` (`main_window.py:4713-4718`), `_update_widget_language_for_path` rekeys entries (`4729-4736`), `_reset_editor_tabs` clears dict (`5278`). Active-pane lookup `_active_markdown_pane` (`4899-4903`) lives on shell while registration lives in factory.
- **Code-judo alternative:** `EditorWorkspaceController` (or `MarkdownTabWorkflow`) owns `_markdown_panes_by_path` exclusively: register on open, release on close, rekey on rename — factory calls controller ports instead of mutating `window._markdown_panes_by_path`. Remove defensive `getattr`; dict is always initialized at `main_window.py:434`.
- **Suggested remediation:** Move registry to workspace controller in same PR as markdown workflow; factory receives `register_markdown_pane(path, pane)` port.
- **Tests that would prove fix:** Unit test on controller: open markdown tab → register; close → pop + deleteLater scheduled; rename → rekey. Integration test `test_markdown_viewer_integration.py` still passes without touching `MainWindow` private dict.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-14-4 — Plugin manager dialog orchestration stranded on MainWindow despite clean activation workflow

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_open_plugin_manager_action` (`main_window.py:3493-3516`) owns lazy dialog construction, `finished` cleanup via `setattr`, repeated `project_root` ternary (four times in handler + snapshot lambda), safe-mode sync, show/raise/activate. `PluginActivationWorkflow` already exposes `snapshot()` and `reload()` with clean ports (`plugin_activation_workflow.py:126-196`). `PluginManagerDialog` consumes snapshot provider and change callbacks correctly (`plugins_panel.py:33-49`) but shell wiring remains in the god object.
- **Code-judo alternative:** `PluginManagerWorkflow` or thin `open_plugin_manager(parent, ports)` module: owns dialog singleton lifecycle, reads `project_root` once, delegates `on_plugins_changed` → `PluginActivationWorkflow.reload`. `MainWindow` menu callback becomes one line.
- **Suggested remediation:** R2 plugin wave — extract dialog lifecycle; keep `PluginActivationWorkflow` as activation source of truth; **method count down** on `MainWindow`.
- **Tests that would prove fix:** Unit test with fake snapshot provider: open twice reuses dialog; project root change triggers refresh; safe-mode toggle calls reload callback.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-14-5 — `_execute_plugin_runtime_command` is dead code; init already wires broker directly

- **Persona:** TN-SHELL-MW-14
- **Severity:** NICE-TO-HAVE
- **Evidence:** `MainWindow.__init__` passes `execute_plugin_runtime_command=lambda ...: self._plugin_api_broker.invoke_runtime_command_for_event(...)` into `DeclarativeContributionManager` (`main_window.py:398-402`). `_execute_plugin_runtime_command` at `3559-3561` duplicates broker invoke + coerce but has **zero call sites** (grep: definition only). `contributions.py:151` calls the injected lambda, not the private method.
- **Code-judo alternative:** Delete `_execute_plugin_runtime_command`. If coerce is required at the shell boundary, make the init lambda the single named private helper `_invoke_plugin_runtime_command_for_event` used by both contributions and any future callers.
- **Suggested remediation:** Hard cutover delete in hygiene PR; no compatibility shim.
- **Tests that would prove fix:** Grep gate: no `_execute_plugin_runtime_command`; existing plugin contribution tests unchanged.
- **Handoff overlap:** none

---

### TN-SHELL-MW-14-6 — Plugin runtime failure UX and registry quarantine callbacks on MainWindow

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** `_record_plugin_runtime_failure` (`main_window.py:3563-3582`) performs registry mutation, scans entries for disable, shows `QMessageBox.warning`, and calls `_plugin_activation_workflow.reload()`. `_clear_plugin_runtime_failure` (`3584-3589`) clears registry failures. Wired as contribution manager callbacks at init (`403-404`). Quarantine logic correctly lives in `DeclarativeContributionManager._execute_runtime_command_with_quarantine` (`contributions.py:141-156`), but **UI + reload policy** leaked to shell.
- **Code-judo alternative:** `PluginRuntimeFailurePolicy` (or methods on `PluginActivationWorkflow` with a `notify_user: Callable[[str], None]` port): owns failure counting side effects, disable decision, user message text, and reload trigger. MainWindow passes `parent` and a toast/dialog port once at init.
- **Suggested remediation:** Extract with plugin manager workflow (finding 4); keep contributions manager transport-only.
- **Tests that would prove fix:** Unit test: N failures → disable + notify port invoked + reload called; success clears failure count without dialog.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-14-7 — Assigned slice range is mostly non-markdown editor orchestration (god-file boundary noise)

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** Of 457 lines in scope, ~30 lines are markdown-specific (`4912-4941`, markdown branches in `5184-5217`, refresh hooks at `5159`, `5254`, `5283`). The remainder is generic editor plumbing: `_handle_editor_text_changed` (`4943-4970`), cursor/status (`4972-4999`), completion async with nested closures (`5009-5147`), tab change/close/reset (`5149-5286`), font/indent preferences (`5288-5367`). `main_window.py` is **5,549 lines** (~5.5× the 1k guideline).
- **Code-judo alternative:** INTEG handoff should treat this slice as **two extraction targets**: markdown tab workflow (findings 1–3) and editor-tab/completion workflow (overlap TN-SHELL-MW-06 completion patterns). Do not add features by extending this line range on `MainWindow`.
- **Suggested remediation:** Document in wave-1 INTEG rollup; prioritize R2 extractions that **reduce** line count in 4943–5367 block, not redistribute it.
- **Tests that would prove fix:** `wc -l app/shell/main_window.py` decreases after extractions; method count grep baseline established.
- **Handoff overlap:** R2, INTEG

---

### TN-SHELL-MW-14-8 — Editor completion async block duplicates intelligence stale-guard pattern (MW-06 overlap)

- **Persona:** TN-SHELL-MW-14
- **Severity:** STRUCTURAL
- **Evidence:** `_request_editor_completions_async` and `_request_completion_item_resolve_async` (`main_window.py:5009-5147`) embed nested `on_success`/`on_error` closures with identical AD-018 guards: `active_widget is editor_widget`, `_editor_buffer_revision` match, telemetry logging. Same pattern flagged in TN-SHELL-MW-06-4 for hover/signature. Wired from `EditorTabFactory` completion closures (`editor_tab_factory.py:95-147`).
- **Code-judo alternative:** Move revision-gated async completion into `EditorIntelligenceController` or shared `RevisionGatedEditorCallback` helper; `MainWindow` deletes both methods; factory closures call controller/workflow ports.
- **Suggested remediation:** Coordinate with MW-06 R2 extraction — one generic stale-guard helper, not three copies.
- **Tests that would prove fix:** Unit test: stale revision drops callback; widget swap drops callback; shared helper covered once.
- **Handoff overlap:** R2 (TN-SHELL-MW-06)

---

### TN-SHELL-MW-14-9 — `_refresh_markdown_action_states` scatter-only enablement; no sync with pane toolbar mode

- **Persona:** TN-SHELL-MW-14
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_refresh_markdown_action_states` only sets `action.setEnabled(enabled)` for four View actions (`4928-4941`); called from seven sites (`740`, `4910`, `4926`, `5159`, `5211-5217`, `5254`, `5283`). View menu actions are not checkable (`view_menu_builder.py:40-76`). User can change mode via pane toolbar without any shell menu state update — acceptable today but prevents future “current mode” menu affordances.
- **Code-judo alternative:** If product wants menu/pane parity, workflow subscribes to `MarkdownEditorPane.mode_changed` and updates checkable actions or action text; otherwise collapse seven call sites to tab-change + project-reset hooks only.
- **Suggested remediation:** Defer until markdown workflow exists; include in finding 1 if checkable menu items are added.
- **Tests that would prove fix:** Optional: pane toolbar mode change fires workflow sync; or call-site count drops after workflow owns enablement policy.
- **Handoff overlap:** R2

---

## Positive signals (not findings)

- `PluginActivationWorkflow` is well-bounded: protocol-injected dependencies, immutable `PluginActivationSnapshot`, pure `build_effective_enabled_map` and `plugin_display_state` (`plugin_activation_workflow.py:96-321`).
- `MarkdownEditorPane` owns preview debounce, scroll sync, theme application, and mode UI — appropriate editor-layer responsibility (`markdown_editor_pane.py:31-200`).
- `EditorTabFactory` cleanly materializes markdown tabs when `is_markdown_path` and `qt_markdown_supported()` (`editor_tab_factory.py:177-190`).
- Integration coverage exists: `tests/integration/shell/test_markdown_viewer_integration.py`.
- Safe-mode path in `PluginActivationWorkflow.reload()` clears contributions, stops runtime, and publishes empty catalog atomically (`plugin_activation_workflow.py:127-133`).

---

## Approval bar (this slice)

**Would not approve** changes that add markdown handlers, plugin dialog plumbing, or `_markdown_panes_by_path` mutations on `MainWindow` without (1) a `MarkdownTabWorkflow` (or workspace-controller ownership) that collapses menu/context-menu/pane mode paths, and (2) plugin UI/failure policy extraction that keeps `PluginActivationWorkflow` as the activation source of truth while **net-reducing** `MainWindow` method count. Any dialog or markdown chrome move must note four-theme validation status for confirmation/toast surfaces.
