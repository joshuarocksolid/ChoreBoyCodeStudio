# TN-SHELL-MW-04 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-04  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 1396–1557 — editor zoom handlers, settings snapshot loaders, plugin-safe-mode toggles, main-thread dispatch, runtime command registry, shell event bus passthroughs.

---

## Executive verdict

**Not thermo-clean.** This slice is a concentrated example of AD-015 composition-root drift: runtime preference loading fans out into six redundant disk reads and parses on every init and settings-apply path; six one-line tuple loaders add method count without owning behavior; zoom operates in raw `(base + delta)` space while rendering uses a clamped effective size, so bounds and UX can diverge; and the plugin runtime surface is duplicated as both public `MainWindow` methods and matching lambdas wired in `__init__`. None of this is catastrophic today, but it is exactly the kind of orchestration spaghetti that will multiply when the next shell feature touches preferences or plugin wiring. Dominant risk: **settings load amplification + delegator sprawl on a 5,549-line / 332-method class**.

---

### TN-SHELL-MW-04-1 — Startup and settings-apply paths re-read settings six times

- **Persona:** TN-SHELL-MW-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:444–484` — init unpacks six separate calls (`_load_editor_preferences`, `_load_completion_preferences`, `_load_diagnostics_preferences`, `_load_output_preferences`, `_load_intelligence_runtime_settings`, `_load_local_history_retention_policy`), each of which calls `_load_main_window_settings()`. Same pattern repeats at `app/shell/main_window.py:1781–1809` after settings dialog apply.
- **Code-judo alternative:** One `_reload_main_window_preferences() -> MainWindowSettingsSnapshot` (or inject a `MainWindowPreferencesLoader` collaborator) that loads global + project payloads once, parses once via `parse_effective_main_window_settings`, then unpacks all runtime fields in a single block. Call sites become one line, not six.
- **Suggested remediation:** Extract preference reload into `app/shell/main_window_preferences.py` (or extend `settings_models.py` with a loader that returns both `MainWindowSettingsSnapshot` and `EditorSettingsSnapshot` from one merged payload). Replace init and `_handle_settings_applied` fan-out with a single load. Delete the six one-liner accessors as part of the same R2 PR.
- **Tests that would prove fix:** Unit test with a spy/mocked `SettingsService` asserting exactly one `load_global` and at most one `load_project` per reload; characterization test that init field values match current behavior after consolidation.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-04-2 — Six one-line preference loaders violate MainWindow shrink rule

- **Persona:** TN-SHELL-MW-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1456–1474` —

  ```python
  def _load_editor_preferences(...) -> tuple[...]:
      return self._load_main_window_settings().editor_preferences
  def _load_completion_preferences(self) -> tuple[bool, bool, int]:
      return self._load_main_window_settings().completion_preferences
  # ... four more identical shapes ...
  ```

  Handoff explicitly forbids this: “If touching MainWindow, the method count must go down. Do not add new one-line delegator methods.” (`docs/deslop/AUDIT_app_remaining_handoff.md` §3, R2 §Implementation notes)
- **Code-judo alternative:** Callers read from a cached snapshot or a single reload helper; no intermediate `_load_*_preferences` methods on `MainWindow`.
- **Suggested remediation:** R2 thin pass-through cleanup — inline at the two call sites (init + settings apply) via snapshot unpack, or move accessors to the extracted preferences loader module as plain functions, not `MainWindow` methods.
- **Tests that would prove fix:** `rg "^    def " app/shell/main_window.py | wc -l` decreases in the PR; existing shell settings tests still pass without calling removed method names.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-04-3 — Parallel effective-settings loaders duplicate merge+parse work

- **Persona:** TN-SHELL-MW-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1434–1454` — `_load_effective_editor_settings_snapshot` and `_load_main_window_settings` both call `_current_project_root()`, `_settings_service.load_global()`, conditional `_settings_service.load_project()`, then `compute_effective_settings_payload` (inside `parse_effective_*` in `settings_models.py`). `parse_main_window_settings` already invokes `parse_editor_settings_snapshot` internally (`app/shell/settings_models.py:308–311`).
- **Code-judo alternative:** Single `load_effective_settings(state_root, project_root) -> EffectiveSettingsBundle` returning both snapshots (or the merged payload once). Settings dialog open path (`main_window.py:1710–1720`) and runtime reload path share it.
- **Suggested remediation:** Add `load_effective_settings_bundle(...)` to `settings_models.py` or a thin `settings_loader.py`; have MainWindow call it once per reload. Hard cutover importers in the same PR per repo cutover rule.
- **Tests that would prove fix:** Unit test on the loader module covering global-only, project override, and both snapshot shapes; mock-count test on combined reload paths.
- **Handoff overlap:** R2 (MainWindow), R3 (`settings_models.py` if snapshot API grows)

---

### TN-SHELL-MW-04-4 — Zoom handlers use raw base+delta; display uses clamped effective size

- **Persona:** TN-SHELL-MW-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1391–1404` — zoom in/out gates on `self._editor_font_size + self._zoom_delta < 72` and `> 8`. Effective rendering uses `max(8, min(72, self._editor_font_size + self._zoom_delta))` at `app/shell/main_window.py:5288–5289`. Font size parsing enforces minimum 8 but **no maximum** (`settings_models.py:142–146`), so persisted `font_size > 72` yields effective 72 while zoom-in stays blocked until delta is adjusted many times against an invisible base.
- **Code-judo alternative:** Small `EditorZoomController` (or methods on `EditorWorkspaceController`) owning `_zoom_delta`, with `effective_font_size(base) -> int`, `zoom_in/out/reset(base)`, and shared constants `UI_EDITOR_FONT_SIZE_MIN/MAX` used by handlers, parser, and `_apply_editor_preferences_to_open_editors`. Menu wiring (`menu_wiring.py:74–76`) targets the controller, not `MainWindow`.
- **Suggested remediation:** R2 extraction — move zoom state + handlers out of MainWindow; unify boundary checks on effective size, not raw sum; align parser max with zoom max (or clamp on read).
- **Tests that would prove fix:** Parametrized unit tests on the controller for base `{10, 72, 100}` × delta steps; assert effective size and handler no-ops match; four-theme N/A (font size only).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-04-5 — Plugin runtime façade is duplicated (methods + init lambdas)

- **Persona:** TN-SHELL-MW-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:387–396` wires `DeclarativeContributionManager` with lambdas that call `self.register_runtime_command`, `self.execute_runtime_command`, `self.subscribe_shell_event`, etc. The same class exposes near-identical public methods at `1500–1559` that forward to `_action_registry`, `_command_broker`, and `_event_bus`. `execute_runtime_command` adds a three-branch overload simulation (`1549–1553`) for optional payload/activation_event.
- **Code-judo alternative:** Introduce `ShellPluginHost` (or pass a frozen `PluginShellPorts` dataclass holding `CommandBroker`, `ShellEventBus`, and registry handles) constructed once in `MainWindow.__init__`; contribution manager and tests depend on the host, not five `MainWindow` methods.
- **Suggested remediation:** R2/R3 — extract host module under `app/shell/`; hard cutover `DeclarativeContributionManager` and plugin tests to the host; remove passthrough methods from MainWindow unless a documented external plugin API requires them on the window type.
- **Tests that would prove fix:** Existing `tests/unit/plugins/test_contributions.py` updated to inject host ports; no behavior change in command registration, invoke, subscribe/unsubscribe.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-04-6 — Python tooling status helpers are MainWindow noise

- **Persona:** TN-SHELL-MW-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:1417–1421` — `_current_python_tooling_status_context` and `_settings_dialog_python_tooling_copy` are one-line forwards to `_python_tooling_status_controller`. R2 candidate list includes “settings getter methods that only read service values” (`AUDIT_app_remaining_handoff.md` R2 §Candidate extractions §4).
- **Code-judo alternative:** Settings dialog and status refresh call `PythonToolingStatusController` directly (passed as collaborator to `SettingsDialog` / status wiring), keeping `_refresh_python_tooling_status` as the only shell-level orchestrator if it must push into `ShellStatusBarController`.
- **Suggested remediation:** Fold into the same R2 PR that touches settings open path (`_handle_open_settings_action`) or defer until preferences loader extraction lands.
- **Tests that would prove fix:** Settings dialog unit tests still receive tooling copy strings; status bar refresh test unchanged.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-04-7 — `MainWindowSettingsSnapshot` tuple unpack is a fragile contract

- **Persona:** TN-SHELL-MW-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/settings_models.py:85–93` — `editor_preferences` is a 15-element positional tuple; `main_window.py:444–459` and `1765–1780` unpack by position with no field names at the callsite.
- **Code-judo alternative:** Replace tuples with a `@dataclass(frozen=True) EditorRuntimePreferences` (named fields) inside `MainWindowSettingsSnapshot`; single unpack to named attributes.
- **Suggested remediation:** R3 settings model cleanup when touching `settings_models.py` for TN-SHELL-MW-04-3; avoid expanding tuple arity in MainWindow.
- **Tests that would prove fix:** Extend `test_parse_main_window_settings_builds_grouped_preferences` to assert named dataclass fields; pyright catches arity drift.
- **Handoff overlap:** R3

---

### TN-SHELL-MW-04-8 — Zoom clamp test duplicates formula, not production seam

- **Persona:** TN-SHELL-MW-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/shell/test_settings_models.py:452–470` — `test_effective_font_size_clamping` re-implements `max(8, min(72, base_size + delta))` inline instead of exercising `MainWindow._effective_font_size` or a extracted zoom helper.
- **Code-judo alternative:** After TN-SHELL-MW-04-4 extraction, test the controller/helper directly; delete duplicated formula test or repoint it to the canonical function.
- **Suggested remediation:** Pair with zoom extraction PR; keep parametrized cases, change import target.
- **Tests that would prove fix:** Same parametrization against `EditorZoomController.effective_font_size(base, delta)`.
- **Handoff overlap:** R2

---

## Cross-slice notes (for TN-SHELL-INTEG)

- **Settings SSOT:** This slice overlaps MW-05+ settings-apply fallout (`1781+`); integration should treat “single effective-settings load” as one P1 theme across MW-04 and settings dialog paths.
- **Method-count metric:** This slice alone contributes ~15 methods that are passthrough or amplifying; R2 acceptance criterion is method count **down** on every MainWindow-touching PR.
- **Four-theme impact:** Zoom and preference reload changes here are font/runtime only; no new hardcoded colors. HC/Light/Dark validation not required for loader consolidation unless UI copy changes.
