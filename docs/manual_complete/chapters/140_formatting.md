# Python Formatting & Imports

ChoreBoy Code Studio can format your Python code and organize its imports using
industry-standard tools, so your code looks consistent and professional.

## Format Current File

Choose **Tools > Format Current File** to reformat the active Python file. Formatting
uses **Black**, the widely used Python formatter, so the result matches what Python
developers expect — consistent spacing, line wrapping, and quote style.

- If the file is already formatted, formatting reports a no-op and does not change the
  buffer.
- Non-Python files use a generic whitespace cleanup instead of Black.

> [!NOTE] This is real Python formatting, not just trailing-whitespace trimming. The
> editor will not claim it formatted your code when nothing meaningful changed.

## Organize Imports

Choose **Tools > Organize Imports** to sort and group the imports in the active Python
file. Imports are ordered in a Black-compatible way, `__future__` imports stay first, and
surrounding comments are preserved.

> [!IMPORTANT] Organize Imports is a **style** action, not a refactor. It sorts and groups
> imports; it does not remove unused imports or rewrite import paths. Import rewriting for
> moved/renamed files is a separate feature (see "The project tree & file management").

## Doing both on save

You can run these automatically when you save, in **Settings > Editor**:

- **Format on save** — run Black on save.
- **Organize imports on save** — sort imports on save.
- **Trim trailing whitespace on save** and **Insert final newline on save** — generic
  hygiene, on by default.

> [!IMPORTANT] Saving your work always wins over style automation. If formatting or
> import-organizing fails (for example, the file has a syntax error), your current text is
> still written to disk and you get a clear warning. Save never silently loses your edits
> or pretends a failed format succeeded.

## Configuration comes from your project

Advanced formatting and import behavior is controlled by your project's `pyproject.toml`,
using the standard sections the Python ecosystem already uses:

- `[tool.black]`
- `[tool.isort]`
- `[project.requires-python]`

ChoreBoy Code Studio honors these so that your formatting matches your project's declared
style and target Python version. The status bar shows when project configuration was
detected (for example, `pyproject`).

> [!NOTE] Code Studio settings control the *workflow* (whether to format on save, and so
> on). They do not become a second, competing style-configuration system — your
> `pyproject.toml` is the source of truth for tool behavior.

## How it runs

Formatting and import-organizing run **in-process** in the editor's runtime using
vendored, pure-Python tools. They do not spawn external command-line programs and do not
create hidden cache folders, which keeps them reliable on the ChoreBoy appliance.

## Editor state is preserved

After formatting, your cursor, selection, scroll position, and undo history remain
practical — the editor does not feel like it threw away your working context. A single
undo reverts a format.

## Where to go next

- Catch problems with linting in "Linting & the Problems panel".
- Understand import resolution in "Code intelligence".
