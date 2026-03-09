# Manual Writing Style Guide

This manual is written for hobbyist users, not professional software engineers.

## Core style rules

1. Use plain words.
   - Prefer "open a project" over "initialize a workspace context."
2. Use short sentences.
   - Aim for 8–18 words per sentence.
3. Use step-by-step actions.
   - Start lines with verbs: "Click", "Type", "Press", "Open".
4. Keep each procedure focused.
   - One goal per procedure.
5. Explain why only when helpful.
   - If a user needs context to avoid mistakes, add one short note.

## Terms to use consistently

- "Project" (not workspace)
- "Run Log" (exact panel label)
- "Problems panel" (exact label)
- "Python Console" (exact label)
- "Project Health Check" (exact menu command)
- "Support Bundle" (exact command label)

## Command formatting

- Menus: `File > Open Project...`
- Shortcuts: `Ctrl+S`, `F5`, `Shift+F5`
- Paths: use inline code, for example `cbcs/project.json`

## Screenshot rules

1. Every screenshot needs a purpose.
2. Use captions that explain what to notice.
3. Keep screenshots clean:
   - no unrelated windows,
   - no transient popups unless the popup is the topic,
   - readable text at print scale.
4. Prefer one concept per screenshot.

## Debug flow documentation rule

Debug instructions must be explicit and realistic:

- show setup steps in order,
- show expected behavior,
- show fallback steps if pausing/stepping does not behave as expected,
- avoid promising behavior that is not consistently available in all environments.

## Concision limits

- Chapter intros: 2–5 sentences.
- Procedures: usually 3–8 numbered steps.
- Troubleshooting entries: 3-part structure:
  - symptom,
  - likely cause,
  - exact fix/check.

