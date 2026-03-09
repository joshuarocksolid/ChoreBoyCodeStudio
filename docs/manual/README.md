# ChoreBoy Code Studio User Manual

This directory contains the source for the printed user manual.

The manual is designed for hobbyist users:

- simple language,
- clear step-by-step workflows,
- screenshot-supported guidance,
- concise troubleshooting.

## Target output

- Printable PDF
- Letter page size
- Full color
- 20–30 pages

## Directory layout

```text
docs/manual/
  chapters/                     # Manual content, split by chapter
  screenshots/                  # Captured screenshots + shot list
  templates/                    # HTML template + print CSS
  dist/                         # Generated artifacts (HTML + PDF)
  outline.md                    # Information architecture
  style_guide.md                # Writing style rules
  feature_trace_matrix.md       # Feature -> chapter mapping
  MAINTENANCE.md                # How to keep manual up to date
  manual_update_checklist.md    # Manual update checklist
  build_manual.py               # Build/check pipeline
```

## Build commands

```bash
python3 docs/manual/build_manual.py --check
python3 docs/manual/build_manual.py --html
python3 docs/manual/build_manual.py --pdf
```

## Editing workflow

1. Update affected chapter(s) in `chapters/`.
2. Update screenshot references and assets in `screenshots/`.
3. Run `--check` and fix any validation errors.
4. Rebuild PDF with `--pdf`.
5. Review output in `docs/manual/dist/`.

