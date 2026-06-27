# ChoreBoy Code Studio User Manual — Complete Edition

This directory contains the source for the **comprehensive, end-to-end** user manual.
It documents **every user-facing feature in detail** and is supported by screenshots.

It is a separate deliverable from the shorter `docs/manual/` *Hobbyist Edition*, which
remains a quick-start oriented booklet. The Complete Edition is the canonical, in-depth
reference; the Hobbyist Edition is the lightweight on-ramp.

## Audience

Both newcomers and power users. The book uses **progressive disclosure**: a Quick Start
and tour up front, daily workflows next, advanced features and exhaustive reference
later, and plugin authoring + support at the end.

## Documentation model

Content follows the **Diátaxis** model, keeping the four modes distinct:

- **Tutorials** — learning-oriented (Part I).
- **How-to guides** — task-oriented (Parts II–III, V).
- **Reference** — information-oriented (Part IV, VI).
- **Explanation** — understanding-oriented ("How it works" sections).

Plus symptom-based troubleshooting, an FAQ, and a glossary.

## Layout

```text
docs/manual_complete/
  chapters/                 # Manual content, one file per chapter (NNN_ prefix orders them)
  screenshots/              # Captured PNGs + capture recipe + shot_list.json
    capture/README.md       # Reproducible screenshot capture guide
  templates/                # HTML template + print CSS
  dist/                     # Generated artifacts (HTML + PDF)
  outline.md                # Information architecture
  style_guide.md            # Writing + formatting rules
  feature_trace_matrix.md   # Every feature -> chapter coverage map
  MAINTENANCE.md            # How to keep the manual current
  manual_update_checklist.md
  build_manual.py           # Build/validate pipeline (HTML + PDF)
```

## Build commands

```bash
python3 docs/manual_complete/build_manual.py --check   # validate images, links, shot list
python3 docs/manual_complete/build_manual.py --html    # render searchable HTML
python3 docs/manual_complete/build_manual.py --pdf     # render HTML + print PDF (headless Chrome)
```

The build runs on the **system Python** (only Jinja2 + Chrome required); it does not
need the FreeCAD AppRun runtime. Capturing screenshots *does* need the runtime — see
`screenshots/capture/README.md`.

## Editing workflow

1. Update the affected chapter(s) in `chapters/`.
2. Update screenshots and `screenshots/shot_list.json` as needed.
3. Update `feature_trace_matrix.md` if coverage changes.
4. Run `--check`, fix any errors, then rebuild with `--pdf`.
5. Review output in `dist/`.
