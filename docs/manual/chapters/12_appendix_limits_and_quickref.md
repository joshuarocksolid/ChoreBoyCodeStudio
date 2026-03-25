# Appendix A — Known Limits and Notes

This appendix lists practical limits you may see in real use.

## Environment limits

- ChoreBoy users do not have direct terminal access.
- Some FreeCAD features require GUI modules and may fail in console/headless runs.
- Heavy projects may need extra care with organization and frequent saves.

## Debug behavior note

Debug controls are available, but runtime conditions can affect breakpoint/step behavior.

If debug flow does not pause as expected:

1. Save all changed files.
2. Confirm executable breakpoint line.
3. Confirm active file vs project debug mode.
4. Fall back to run + traceback workflow for diagnosis.

## Project portability note

Keep visible project metadata folders (`cbcs/`) intact when moving projects.

Do not remove:

- `cbcs/project.json`
- `cbcs/settings.json` (if used)
- `cbcs/logs/` when diagnostic history matters

---

# Appendix B — One-Page Quick Reference

## Daily workflow

1. Open project (`Ctrl+O`)
2. Open file
3. Edit
4. Save (`Ctrl+S`)
5. Run (`F5`)
6. Read Run Log
7. Fix issues from Problems panel

## If something fails

1. Check Run Log
2. Check Problems panel
3. Open Runtime Center
4. Run Project Health Check
5. Generate Support Bundle if needed

## Most used commands

- Run Active File: `F5`
- Run Project: `Shift+F5`
- Stop: `Shift+F2`
- Find in Files: `Ctrl+Shift+F`
- Quick Open: `Ctrl+P`
- Go To Definition: `F12`

