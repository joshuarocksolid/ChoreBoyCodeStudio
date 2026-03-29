# Smoke test workflow (post–v0.2 + recent shell work)

Quick validation before a release candidate or after large shell/runner changes. Combines **automated pytest gates** with a **short manual GUI checklist**.

## Baseline

- **Last tagged release:** [CHANGELOG.md](CHANGELOG.md) — **0.2** (2026-03-09); git tag `v0.2`.
- **Scope:** Post–v0.2 changed a large surface area; this workflow uses automation for regression coverage and a **narrow manual path** for high-touch UI (run summary, test explorer, welcome/onboarding, themes).
- **Deeper coverage:** Full MVP-style checks live in [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md). Example phased run logs: [smoke_test_results.md](../smoke_test_results.md) (repo root).

---

## Layer 1 — Automated (run first)

Use [run_tests.py](../run_tests.py) so tests execute inside **FreeCAD AppRun**, matching [AGENTS.md](../AGENTS.md). Always pass `--import-mode=importlib`.

### A. Fast unit slice (shell + run-target + test explorer)

```bash
python3 run_tests.py -v --import-mode=importlib \
  tests/unit/shell/test_toolbar.py \
  tests/unit/shell/test_run_target_summary.py \
  tests/unit/shell/test_run_target_shortcuts.py \
  tests/unit/shell/test_welcome_widget.py \
  tests/unit/shell/test_test_explorer_panel.py \
  tests/unit/shell/test_run_session_controller.py
```

### B. Targeted integration (Qt offscreen)

```bash
python3 run_tests.py -v --import-mode=importlib \
  tests/integration/shell/test_run_preflight_integration.py \
  tests/integration/shell/test_welcome_runtime_onboarding.py \
  tests/integration/shell/test_runtime_explanation_theme_integration.py
```

**Coverage:** run toolbar target summary / named `run_configs`, runtime preflight vs **Runtime Center**, **Help → runtime onboarding** after autoload, runtime/onboarding dialogs under **light and dark** themes.

### C. Optional — AppRun subprocess parity

```bash
python3 run_tests.py -v --import-mode=importlib tests/runtime_parity/test_apprun_smoke.py
```

Tests self-skip if AppRun is missing.

### D. Broader gate (when time allows)

- `python3 run_tests.py -q --import-mode=importlib tests/unit/`
- If the full **integration** suite stalls or hangs, run `tests/integration/` in smaller batches (see [AGENTS.md](../AGENTS.md)).

### Note on exit codes

PySide2 teardown on `QT_QPA_PLATFORM=offscreen` may **segfault after all tests passed**, yielding a non-zero process exit even when pytest reported green. Treat the **pytest result lines** as authoritative; re-run a single file if you need a clean exit code.

---

## Layer 2 — Manual smoke (15–25 minutes)

Run on a **real DISPLAY** (not only offscreen). Use sample projects from [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md) §5 if you need fixtures.

| Step | What to verify |
|------|----------------|
| **M1 — Launch** | Editor starts; status bar shows runtime readiness; **Runtime Center** and **Help → runtime** flows still work. |
| **M2 — Welcome / onboarding** | Without autoload (or after clearing last project): welcome is usable; **Help → runtime onboarding** opens and text is readable. With autoload: onboarding does not auto-open; still reachable from **Help** (see integration test above). |
| **M3 — Run toolbar target summary** | With a project open: **two-line run summary** beside run controls; **tooltip** shows shortcuts and project/named-setup hints. Switch active file (Python vs non-Python); summary updates. If the project defines **`run_configs`**, use **Run With Configuration…** and confirm the summary matches the selection. |
| **M4 — Run / preflight** | **F5** (active file) and **Shift+F5** (project) launch; stdout/stderr in run log; failures show traceback; **Stop** works on a long-running script. **Preflight / missing entry** dialogs should be actionable (no hang). |
| **M5 — Test explorer** | Open the **Test** activity / sidebar; discovery populates; **run one test**, **run all**, **rerun failed** (after a failure) if available; **navigate to test** opens the editor at the right line. |
| **M6 — Themes** | Toggle **light / dark**; **welcome**, **test explorer**, **run summary panel**, and **runtime/onboarding** dialogs stay readable (contrast, icons). |
| **M7 — Spot-checks** | Edit `main.py`: dirty marker and save; optional: project tree **file type icons** look correct. |

**Recording:** Use PASS / FAIL / WARN per step and optional screenshots; [smoke_test_results.md](../smoke_test_results.md) is an example log format.

---

## Quick flow

```mermaid
flowchart LR
  L1[Layer1_pytest]
  L2[Layer2_manual_GUI]
  L1 --> L2
```
