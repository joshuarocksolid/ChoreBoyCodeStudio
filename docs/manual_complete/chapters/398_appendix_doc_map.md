# Appendix E — Where to Learn More

This manual is the comprehensive user guide. For deeper or developer-facing material, the
project ships several canonical documents. This appendix maps where to look.

## This manual vs the Hobbyist Edition

- **Complete Edition** (this book) — comprehensive, every feature in detail.
- **Hobbyist Edition** (`docs/manual/`) — a short, quick-start booklet for getting going
  fast. Start there if you want the essentials in a few pages.

## In-application help

You rarely need to leave the application:

- **Help > Getting Started** — first-steps onboarding.
- **Help > Keyboard Shortcuts** — the live shortcut reference.
- **Tools > Runtime Center** — runtime and project health, explained in plain language.
- **Tools > FreeCAD Headless Notes** — guidance on headless limits.

## Canonical project documents

For background, design rationale, and developer-facing detail, the repository includes:

| Document | What it covers |
| --- | --- |
| `docs/PRD.md` | Product goals, scope, and intended workflows. |
| `docs/DISCOVERY.md` | Runtime facts and platform constraints (the "why" behind limits). |
| `docs/ARCHITECTURE.md` | System design: processes, modules, contracts, decisions. |
| `docs/ACCEPTANCE_TESTS.md` | Human-verifiable success criteria for each feature. |
| `docs/plugins/` | Plugin platform: PRD, SDK, authoring guide, API reference, compatibility policy. |

> [!NOTE] Those documents are developer-oriented. This manual translates the user-facing
> parts into task-focused guidance; the canonical docs are the source of truth if you need
> the underlying detail.

## How this manual is maintained

The manual is **docs-as-code**: its chapters are Markdown, built into HTML and a print PDF
by `docs/manual_complete/build_manual.py`. Governance lives alongside it:

- `style_guide.md` — writing and formatting rules.
- `outline.md` — the information architecture.
- `feature_trace_matrix.md` — maps each feature to the chapter that documents it.
- `MAINTENANCE.md` and `manual_update_checklist.md` — how to keep it current when the app
  changes.
- `screenshots/capture/README.md` — a reproducible recipe for re-capturing screenshots.

When a feature changes, the maintainer updates the affected chapter and screenshots in the
same change, then rebuilds and validates with `build_manual.py --check` and `--pdf`.

## Building this manual yourself

```bash
python3 docs/manual_complete/build_manual.py --check   # validate images, links, manifest
python3 docs/manual_complete/build_manual.py --html    # searchable HTML
python3 docs/manual_complete/build_manual.py --pdf     # print-ready PDF
```

The build runs on an ordinary Python install (only Jinja2 and a Chrome/Chromium browser
are needed). Output lands in `docs/manual_complete/dist/`.

## A final word

ChoreBoy Code Studio packs a full development experience into a constrained appliance.
Almost everything you need is one menu or shortcut away, and the application explains
itself through the status bar, the Runtime Center, and built-in help. When in doubt, open
the Runtime Center, read the Run Log, and remember that your projects are plain folders —
safe to copy, back up, and inspect.
