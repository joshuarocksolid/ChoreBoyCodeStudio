# Manual Update Checklist

Use this checklist whenever user-facing behavior changes.

## Content

- [ ] I identified all affected manual chapters.
- [ ] I updated all affected instructions and menu paths.
- [ ] I removed or reworded any outdated statements.
- [ ] I verified debug instructions still match current behavior.

## Screenshots

- [ ] I identified all affected screenshot IDs.
- [ ] I replaced outdated screenshots.
- [ ] New screenshots are clear and readable at print scale.
- [ ] Screenshot captions still match what users will see.

## Build + validation

- [ ] `python3 docs/manual/build_manual.py --check` passes.
- [ ] `python3 docs/manual/build_manual.py --pdf` succeeds.
- [ ] Final PDF opens and has clean pagination.

## Final review

- [ ] Manual still reads clearly for hobbyist users.
- [ ] No TODO/unreleased features are documented as shipped.
- [ ] Feature trace matrix remains up to date.

