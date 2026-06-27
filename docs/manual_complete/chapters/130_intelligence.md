# Code Intelligence

ChoreBoy Code Studio understands your Python code. It offers completion, hover
documentation, signature help, go-to-definition, find-references, and project-wide
rename — all based on real semantic analysis, not just text matching.

## A safety promise

> [!IMPORTANT] Code intelligence for files you are editing never executes your project
> code inside the editor. It analyzes your code statically. (The Python Console is the
> opposite: it inspects live objects, because that is its purpose — see "The Python
> Console".)

## Completion

As you type, ChoreBoy Code Studio suggests completions:

- Type normally, or press `Ctrl+Space` to trigger completion manually. (You can enable
  automatic completion in **Settings > Intelligence**.)
- Completions are project-aware: members of imported modules and your own classes are
  offered.
- Fast results (keywords, current-file symbols, trusted API entries) appear immediately;
  deeper semantic results refine the list a moment later.
- Documentation and signatures for the selected item load on demand, without changing
  what gets inserted.

Each completion shows useful metadata — its kind, where it came from, and a confidence
indicator. Approximate results are labeled as such, so you are never misled into thinking
a guess is a certainty.

> [!NOTE] FreeCAD and PySide2 are partly backed by C++ and are hard to analyze
> statically. ChoreBoy Code Studio ships a trusted API index for these so that import and
> attribute completion work for them.

## Hover and signature help

| Command | Shortcut | What it shows |
| --- | --- | --- |
| Show Hover Info | `Ctrl+Shift+I` | Documentation for the symbol under the cursor. |
| Signature Help | `Ctrl+Shift+Space` | The parameters of the function you are calling. |

You can also enable hover-on-mouse tooltips in **Settings > Editor > Hover tooltip
enabled**.

## Go to Definition and Find References

| Command | Shortcut | What it does |
| --- | --- | --- |
| Go To Definition | `F12` | Jump to where a symbol is defined, following imports across files. |
| Find References | `Shift+F12` | List every place a symbol is used. |

These respect binding identity, not just spelling: two different things that happen to
share a name are not confused. When a symbol has more than one valid definition, you are
asked to choose rather than being sent to the wrong one silently.

## Rename a symbol everywhere

Place the cursor on a symbol and press `F2` (**Rename Symbol**). ChoreBoy Code Studio
plans a project-wide rename:

1. A **preview** shows the changes grouped by file, in a patch-like form.
2. Only semantically related occurrences are renamed — unrelated same-name symbols are
   left alone.
3. Apply the rename, or cancel.

If a rename would be unsafe or ambiguous, it is blocked with an explanation rather than
risking incorrect edits. If applying fails partway, the change is rolled back so your
project is never left half-renamed.

## When analysis can't be certain

Some Python is too dynamic to analyze precisely. In those cases ChoreBoy Code Studio does
**not** pretend a text match is a definition. Instead it tells you the result is
approximate or unsupported, and offers a text-search fallback you can use deliberately.

## Source roots and imports

Code intelligence resolves your imports using your project's source roots. If your
packages live under a folder such as `src/`, mark it as a **Sources Root** (right-click
it in the Explorer). This makes both diagnostics and runs resolve `import yourpackage`
correctly, with no `sys.path` hacks. See "The project tree & file management".

## Keeping the index fresh

Code intelligence is accelerated by a symbol index that updates as you work. If results
ever seem stale, use **Tools > Rebuild Intelligence Cache**. Indexing is only an
accelerator — the editor keeps working even if the index is missing.

## Performance

Completion and navigation run off the UI thread, so they never freeze the editor. Results
are tied to the version of the buffer they were requested for, so a stale result can
never overwrite newer text you have typed.

## Where to go next

- Format and organize your code in "Python formatting & imports".
- See and fix problems in "Linting & the Problems panel".
