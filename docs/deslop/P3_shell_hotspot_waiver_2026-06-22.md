# P3-3 Shell Hotspot Waiver — Deslop R3 Closeout

**Date:** 2026-06-22  
**Program item:** P3-3 (Remaining shell hotspots <700 LOC or documented)  
**Verdict:** **ACCEPT (documented waivers)**

---

## Metric sweep @ HEAD

| File | LOC | Wave owner | Notes |
|------|-----|------------|-------|
| `app/shell/python_console_widget.py` | 782 | shell-wave-2 CC-SHELL2 P2 | Console UX monolith; split when touched |
| `app/shell/local_history_workflow.py` | 773 | shell-wave-2 | Workflow cohesion; no MainWindow growth |
| `app/shell/settings_models.py` | 736 | shell-wave-2 CC-SHELL2-20 | Settings domain models; handlers already split |
| `app/shell/style_sheet_sections_workspace.py` | 735 | deslop R3 | Stylesheet section already partial-split from `style_sheet_sections.py` |
| `app/persistence/local_history_repository.py` | 725 | persistence-wave-1 CC-PERSIST-01 | Persistence package smell; facade modules exist |

**Blocker gate:** zero files ≥1000 LOC in `app/`.

## Decision

Splits deferred to post-program deslop briefs (R3 in `AUDIT_app_remaining_handoff.md`). Each file has clear ownership and wave closure references. No new monolith growth during thermo program.

## Validation

- `find app/shell -name '*.py' -exec wc -l {} + | awk '$1>=1000'` → empty  
- shell-wave-2 ACCEPT @ `a015e0a`  
- persistence-wave-1 ACCEPT with CC-PERSIST-01 deferred  
