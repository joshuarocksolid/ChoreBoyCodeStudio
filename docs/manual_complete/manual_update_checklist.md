# Complete Edition — Update Checklist

Use this checklist whenever user-facing behavior changes.

## Content

- [ ] Identified all affected chapters.
- [ ] Updated all affected instructions, menu paths, shortcuts, and field tables.
- [ ] Removed or reworded outdated statements.
- [ ] Verified debug/runtime instructions still match current behavior.
- [ ] Confirmed no unshipped/TODO behavior is documented as shipped.

## Screenshots

- [ ] Identified all affected screenshot ids in `shot_list.json`.
- [ ] Re-captured affected screenshots using the capture recipe.
- [ ] New screenshots are clear and readable at print scale.
- [ ] Captions still match what users will see.

## Reference & coverage

- [ ] Updated the menu/command reference for any new/changed command.
- [ ] Updated the shortcut table if defaults changed.
- [ ] Updated `feature_trace_matrix.md` coverage map.

## Build + validation

- [ ] `build_manual.py --check` passes (images, links, shot list).
- [ ] `build_manual.py --pdf` succeeds and the PDF paginates cleanly.

## Final review

- [ ] Reads clearly for both newcomers and power users.
- [ ] Terminology matches the style guide.
