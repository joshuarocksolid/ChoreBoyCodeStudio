# Manual Maintenance Policy

This document explains how to keep the user manual current as the app evolves.

## When manual updates are required

Update the manual when any user-facing behavior changes, including:

- menu labels or menu structure,
- toolbar actions,
- project/file workflows,
- run/debug behavior,
- settings or defaults,
- error dialogs or troubleshooting steps,
- plugin manager UX,
- keyboard shortcuts,
- packaging/export/share workflows.

## Required update steps

1. Update affected chapter(s) in `docs/manual/chapters/`.
2. Update screenshot references and replace outdated screenshots.
3. Update `feature_trace_matrix.md` if coverage mapping changes.
4. Run:
   - `python3 docs/manual/build_manual.py --check`
   - `python3 docs/manual/build_manual.py --pdf`
5. Review generated PDF in `docs/manual/dist/`.
6. Note manual revision date and changed chapters in your change notes.

## Screenshot refresh rule

If UI layout/labels change, replace related screenshots in the same change.

Do not leave stale screenshots in a "temporary" state.

## Accuracy rule

Never document TODO/unshipped features as available behavior.

Cross-check with:

- `docs/ACCEPTANCE_TESTS.md`
- `docs/USER_REQUESTS_TODO.md`
- current app behavior in runtime.

