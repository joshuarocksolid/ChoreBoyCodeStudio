# Complete Edition — Maintenance Policy

Keep this manual current as the application evolves. The manual is a maintained
artifact, not a one-time document.

## Ownership

Treat the manual as part of the "definition of done" for user-facing changes. When a
change alters user-facing behavior, update the manual in the **same change**.

## When updates are required

Update the manual when any of these change:

- menu labels or menu structure, toolbar actions, keyboard shortcuts;
- project/file workflows; run/debug behavior;
- settings, defaults, or settings layout;
- error dialogs, troubleshooting steps, or runtime explanations;
- plugin manager UX or plugin authoring contracts;
- dependency, packaging, export, or install workflows;
- code intelligence, formatting, linting, or testing behavior.

## Required steps

1. Update the affected chapter(s) in `chapters/`.
2. Replace affected screenshots (see `screenshots/capture/README.md`) and update
   `screenshots/shot_list.json`. Do not leave stale screenshots.
3. Update `feature_trace_matrix.md` if coverage mapping changes.
4. Run `python3 docs/manual_complete/build_manual.py --check` and fix all errors.
5. Run `python3 docs/manual_complete/build_manual.py --pdf` and review `dist/`.
6. Bump `PRODUCT_VERSION` in `build_manual.py` if documenting a new app version.

## Accuracy rule

Never document TODO/unshipped features as available. Cross-check against:

- `docs/ACCEPTANCE_TESTS.md` (behavior canon),
- the source code,
- the running application.

The Designer (.ui builder) subsystem stays out of scope until released.

## Screenshot freshness rule

If UI layout or labels change, replace the related screenshots in the same change.
The capture recipe makes re-capture deterministic.
