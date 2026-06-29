# Complete Edition — Writing & Formatting Style Guide

This manual serves both newcomers and power users. Write so a first-time user can
follow a procedure, and a power user can scan for exact facts.

## Voice and language

1. Write in the **second person** ("you"), **active voice**, **present tense**.
2. Prefer plain words. Define jargon the first time it appears; collect terms in the Glossary.
3. Keep sentences short (aim 8–20 words). Avoid walls of text.
4. Start procedure steps with a verb: "Click", "Type", "Press", "Open", "Select".
5. One action per numbered step. State the **expected result** when it aids confidence.

## Consistent terminology (use these exact terms)

- **Project** (not "workspace").
- **Run Log**, **Problems**, **Python Console**, **Debug** — exact bottom-panel labels.
- **Explorer** for the file tree sidebar; **Outline** for the symbol panel.
- **Run Configurations**, **Run With Arguments…** — exact command labels.
- **Project Health Check**, **Support Bundle**, **Runtime Center** — exact labels.
- **Plugin Manager**, **Dependency Inspector**, **Add Dependency** — exact labels.
- **Local History**, **Recovery Center**, **Global History** — exact labels.

## Formatting conventions

- Menus: `File > Open Project...` (use the `>` separator and the real label, including `...`).
- Shortcuts: `Ctrl+S`, `F5`, `Shift+F5`, `Ctrl+Shift+F`.
- Paths, filenames, code, JSON keys: inline code, e.g. `cbcs/project.json`, `default_entry`.
- UI control names in **bold** when first referenced in a step (e.g. click **New Project**).
- Use tables for reference material (fields, options, shortcuts, status values).

## Callouts (use the build pipeline's blockquote syntax)

```text
> [!TIP] A shortcut or efficiency suggestion.
> [!IMPORTANT] Something the user must not miss to avoid mistakes.
> [!NOTE] Helpful context or a cross-reference.
> [!LIMITATION] A ChoreBoy/runtime constraint or known boundary.
```

## Chapter structure

Each chapter opens with a 2–4 sentence intro stating what it covers and who it's for.
Each feature section follows this shape:

1. **What it is** (1–3 sentences).
2. **When to use it** (short).
3. **Before you begin** (preconditions, only if needed).
4. **Steps** (numbered; exact menu paths/shortcuts; expected results).
5. **Options / fields** (document every field or toggle, usually as a table).
6. **Screenshot(s)** with an explanatory caption.
7. **Notes / limitations** (cross-link troubleshooting where relevant).
8. **Related** (links to next logical chapters/sections).

## Screenshots

1. Every screenshot has a clear purpose and an explanatory caption (what to notice).
2. One concept per image. No unrelated windows or transient popups (unless the popup is the topic).
3. Text must be readable at print scale.
4. Use numbered callouts on overview images (window tour, debug panel).

## Accuracy rules (non-negotiable)

- Never document TODO/unshipped behavior as available. Cross-check against
  `docs/ACCEPTANCE_TESTS.md`, the source code, and the running app.
- The **Designer (.ui builder) subsystem is out of scope** (unreleased) — do not document it.
- When debug/runtime behavior depends on the environment, say so and give a fallback.

## Debug documentation rule

Debug instructions must be explicit and realistic: show setup in order, expected
behavior, and a fallback path (normal run + traceback) if pausing/stepping does not
behave as expected in a given environment.
