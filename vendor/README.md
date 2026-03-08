# Vendored Dependencies

This folder holds Python packages that ship with ChoreBoy Code Studio instead
of being installed via pip on the target system. The contents are **not tracked
in git** -- each developer (or the packaging script) must populate the folder
using the instructions below.

## Required packages

| Package               | Version | Type                  | Notes                                                  |
|-----------------------|---------|-----------------------|--------------------------------------------------------|
| pyflakes              | 3.4.0   | Pure Python           | Linter backend for diagnostics                         |
| tree-sitter           | 0.21.3  | Python + native `.so` | Parsing library bindings                               |
| tree-sitter-languages | 1.10.2  | Python + native `.so` | Pre-compiled grammar bundle (~81 MB `languages.so`)    |

## Setup

Install all three packages into this directory with pip:

```bash
pip install \
  pyflakes==3.4.0 \
  tree-sitter==0.21.3 \
  tree-sitter-languages==1.10.2 \
  --target=vendor/
```

Run this from the repository root so the `--target=vendor/` path resolves
correctly.

### Platform-specific binaries

`tree-sitter` and `tree-sitter-languages` include compiled `.so` files that are
specific to the CPU architecture and CPython version. The wheels you download
must match the runtime that will load them:

- **ChoreBoy production**: CPython 3.9, x86_64 Linux (FreeCAD AppRun)
- **Cloud dev environment**: CPython 3.11, x86_64 Linux (FreeCAD AppRun)

If you need wheels for a CPython version that pip does not select automatically,
download them explicitly from PyPI and extract into this folder.

## How the app loads vendor packages

`app/treesitter/loader.py` inserts `vendor/` into `sys.path` at runtime so that
`import tree_sitter` and `import tree_sitter_languages` resolve here. The
pyflakes package is imported the same way by the diagnostics service.

## Packaging

`package.py` copies the entire `vendor/` folder into the distribution archive,
so end-user installs receive these dependencies without needing pip.
