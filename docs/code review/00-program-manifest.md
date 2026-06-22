# Thermo Program — Master Manifest

Status: **active** (kickoff 2026-06-22)
Last verified commit: `48d9cfe`
Orchestrator: Composer 2.5 Fast (`/thermo-program-orchestrator`)

---

## Program goal

Complete thermo-nuclear code quality **review + remediation + closure** for all `app/` packages until `PROGRAM_STATUS.md` shows `overall: ACCEPT`.

---

## Wave inventory @ HEAD

| Wave | Review | Plans | Closure | Status |
|------|--------|-------|---------|--------|
| editors-wave-1 | 2026-06-17 | W1+W2 | **ACCEPT** (W1+W2 closure docs) | **done** — preserve grep gates |
| shell-wave-2 | 2026-06-17 @ `fccb611` | yes | none | **in_progress** — re-baselined @ HEAD; partial remediation landed |
| intelligence-wave-1 | 2026-06-16 | yes | none | open (23 CC themes) |
| project-ssot-wave-1 | 2026-06-16 | yes | none | open (P0 claimed closed in code; no formal closure) |
| run-wave-1 | 2026-05-25 | **missing** | none | open (20 CC themes; stale baseline) |
| shell-wave-1 | 2026-05-25 | handoff only | none | superseded by shell-wave-2 |

---

## HEAD metric snapshot (2026-06-22)

| Metric | Value | Gate |
|--------|------:|------|
| `app/` files ≥1000 LOC | **0** | pass |
| `main_window` methods | **28** | pass (≤40) |
| `window: Any` in `app/shell/` | **104** | fail (review baseline 79; CC-SHELL2-05 blocker) |
| `main_window_composition_phases` LOC | **453** | improved (was 639 pre-R-03) |
| `window._` in composition phases | **110** | improved (was 297 pre-R-03) |
| `app/` files ≥700 LOC | **5** | smell |
| Editors grep gates | clean | pass |
| pyright | 0 errors | pass |
| fast shard | PASS @ session 2 | pass |

Files ≥700 LOC: `python_console_widget.py` (782), `local_history_workflow.py` (773), `settings_models.py` (736), `style_sheet_sections_workspace.py` (735), `persistence/local_history_repository.py` (725).

---

## Phase roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| P0 | Program tracker + baseline | done (kickoff session 1) |
| P1 | Close open waves @ HEAD | in_progress |
| P2 | New reviews (persistence, plugins, treesitter, packaging, python_tools, core, pytest/templates) | pending |
| P3 | Deslop R0–R7 | pending |
| P4 | INTEGR + final closure | pending |

### P1 work queue

1. **P1-1** shell-wave-2 — Wave 1 hosts verified; SHELL-R-18 landed; **next: SHELL-R-04b extract host adapters, net-reduce `window: Any` ≤79**
2. **P1-2** intelligence-wave-1 — verify CC-01…23 → closure
3. **P1-3** project-ssot-wave-1 — formalize P0 closure → finish P1/P2
4. **P1-4** run-wave-1 — author plans → remediate → closure
5. **P1-5** shell-wave-1 — archive superseded status

---

## Verification gates (re-run @ HEAD before closure)

```bash
find app -name "*.py" -exec wc -l {} + | awk '$1>=1000 && $2 !~ /total$/ {print "BLOCKER:", $2}'
rg "^    def " app/shell/main_window.py | wc -l
rg "window: Any" app/shell --count-matches
rg 'hover_provider' app/ || true
rg 'build_completion_context' app/editors/ || true
rg 'from app\.intelligence' app/project/ || true
python3 testing/preflight_test_env.py
python3 testing/run_test_shard.py fast
npx pyright
```

---

## Canonical references

- [`THERMO_PROGRAM_ORCHESTRATOR.md`](THERMO_PROGRAM_ORCHESTRATOR.md)
- [`THERMO_PROGRAM_WORKFLOW.md`](THERMO_PROGRAM_WORKFLOW.md)
- [`PROGRAM_STATUS.md`](PROGRAM_STATUS.md)
- [`docs/deslop/AUDIT_app_remaining_handoff.md`](../deslop/AUDIT_app_remaining_handoff.md)
