# Appendix C — Runtime Capabilities for Your Projects

This appendix summarizes what the ChoreBoy runtime can do for applications you build in
Code Studio: data storage, databases, reporting, and printing. It is reference material
for ambitious projects. These capabilities are **advanced** and optional — most projects
need none of them.

> [!NOTE] These facts come from validated runtime discovery on ChoreBoy. They describe
> what your *programs* can use at runtime; they are not editor features. For the
> authoritative, detailed findings, see the project's `docs/DISCOVERY.md`.

## The runtime in one paragraph

Your code runs inside FreeCAD's bundled Python (version 3.9) with the Qt toolkit
(PySide2) available. You can write files, use SQLite, spawn limited subprocesses, and
`import FreeCAD` for headless geometry. Several heavier capabilities are available through
in-process techniques because the appliance blocks running external binaries directly.

## Local data storage

| Need | Recommended approach |
| --- | --- |
| Settings, small structured data | A JSON file in your project. |
| Local relational data, indexes | **SQLite** (in the standard library) — fully supported and fast. |
| Large/critical data | SQLite with regular backups to USB. |

SQLite is the default, reliable choice for application data on ChoreBoy.

## PostgreSQL connectivity

If your project must talk to a PostgreSQL server on the network, it can — through
pure-Python or vendored drivers, not a system `psql`:

- **pg8000** — a pure-Python driver; zero setup, ideal for simple queries.
- **psycopg 3 (binary)** — C-accelerated, faster for parameterized queries and bulk work;
  it loads its compiled libraries in-process.
- **SQLAlchemy 2.0** — works as an ORM layer over psycopg for both sync and async.

> [!LIMITATION] The validated ChoreBoy PostgreSQL server is an old version (9.3-era). Some
> modern SQL features (`JSONB`, `ON CONFLICT` upserts, generated columns, multiranges) are
> unavailable. SQLite avoids these constraints for local data. Django's ORM is not usable
> against that PostgreSQL version on Python 3.9; use raw drivers or SQLAlchemy instead.

## Reporting (JasperReports)

Rich PDF/printed reports are possible. Java and JasperReports run **in-process** via the
JVM loaded as a shared library (the appliance blocks launching the `java` binary
directly). The validated pipeline compiles a JRXML template, fills it with data
(including from a database), and exports to PDF or PNG, which you can then display or
print.

This is an advanced integration; budget time for it and consult `docs/DISCOVERY.md` for
the exact loading recipe.

## Printing

Your app can print without a terminal:

- Submit print jobs **in-process through the CUPS library** (`libcups`), not by running
  `lpr`/`lp` (those are blocked).
- Qt's print-preview dialog works for on-screen preview.
- Select a printer explicitly, fall back to the system default, or list available
  destinations if none is set.

## Compiled Python packages

Pure-Python packages vendored into `vendor/` work directly. Some **compiled** packages can
also work because the runtime can load their shared libraries from memory, bypassing the
appliance's restriction on executing code from writable storage. This is how the editor
itself loads tree-sitter. Treat compiled dependencies as advanced: validate them on the
real device, and prefer pure-Python where possible. See "Managing dependencies".

## What is blocked

To set expectations, the appliance blocks:

- launching arbitrary external programs (only a minimal shell is permitted);
- a user terminal or command prompt;
- general internet access (the environment is LAN-only).

The capabilities above all work *around* these constraints by running in-process or
through allowed system libraries.

## Where to go next

- Add a database or report library as a dependency in "Managing dependencies".
- Understand why these constraints exist in "How it works".
- Read the full, authoritative findings in `docs/DISCOVERY.md`.
