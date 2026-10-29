# Form builder architecture contracts (M1.0)

Status: binding for every M1–M3 work package, and for later WPs where a section names them. Revision 1, 2026-10-21. Author: Opus (architect). Inputs: `PLAN.md` rev 1, `LOGIC_DESIGN.md`, research R1, R3, C, and the spike on `feat/form-builder-spike`.

This document and the typed stubs under `stubs/app/...` are one contract. The stubs hold the exact names, signatures and field lists. This document holds the rules, the reasons, and the tests that prove the rules. When the two disagree, raise it in the PR. Don't pick one quietly.

**Words.** MUST and MUST NOT are absolute. SHOULD means "do this unless the PR explains why not". "Op" means one of the six primitive ops in §3.3. "Entry" means one undo step. "Session" means one `FormSession`, which is one open form tab.

**Changing this contract.** A WP that needs a contract change opens a separate contract PR (this file plus the stubs). It goes through the O-logic gate before any code that depends on it merges. Additions are cheap. You can add a command module, a diagnostic code, a participant or an expander through registration files without touching shared ones (§1.4). Changing an existing signature or rule costs more.

---

## 0. Decisions on one page

| # | Decision | Replaces |
| --- | --- | --- |
| D1 | Node ids are session-local positive ints. They are never reused and never persisted. The object name is the only persistent identity. | Spike `"id12"` strings, looked up by an O(n) tree walk |
| D2 | One typed node tree that is driven by a schema table (`ui4/schema.py`). It has an O(1) id index, parent map and name index. The XML write order is the ui4.xsd sequence, which is also Designer's output order. | Spike's untyped `body` lists of mixed parts |
| D3 | Undo records ops, it doesn't take snapshots. Commands run `apply` against the live document and emit **six primitive ops**, each with an exact inverse. Redo re-applies the recorded ops. Replay re-runs `apply` and must reproduce the same ops. Only `ReplaceDocument` stores a snapshot. | Spike stateful commands that captured their own old state; the prior branch's whole-XML snapshot stack |
| D4 | Ops and the subtrees they carry are frozen `NodeSpec` values. Undo history never shares a live node object with the document. | Spike `copy.deepcopy` of live nodes |
| D5 | Change events come straight from ops, one change per op, one `ChangeSet` per entry. Realize patches **only** the containers named in `structure_dirty`. | Spike `units(doc)` signature scan over the whole form on every structural edit |
| D6 | Rapid edits merge only by an explicit UI gesture token. The engine never merges by time. | (new) |
| D7 | Values are frozen dataclasses for all 33 ui4 value kinds. Anything that doesn't round-trip without loss becomes `OpaqueValue`. Nothing is ever dropped. | Spike's raw `XmlNode` bodies, and its `_norm_text`, which turned `" "` into `""` |
| D8 | The writer never drops a property that is in the model. The class table (defaults) is used for inspector display, Reset, rank insertion and realize resets, never to decide what gets written. | Spike `defaults.py` omitted "default-valued" properties on write, which caused silent file changes |
| D9 | The hit index refreshes lazily. Any invalidation is O(1) (an epoch bump), and it refreshes on the next pointer event or paint. Queries walk the hit tree; they don't scan a list. | Spike kept a deferred `index_dirty` flag but did linear hit lists and a 22 ms walk |
| D10 | The canvas never runs user code, generated code, `*_rc.py` or Designer plugins. Promoted widgets show as stand-ins of their `extends` class. Resources come from an in-memory compiled tree. | Spike ran preview in-process |
| D11 | The preview child reuses `ProcessSupervisor` (argv list, no shell) and the rpc_protocol JSON-lines encoding. Frames carry a sentinel prefix, and the child moves fd 1 to stderr so its frame stream stays clean. | Plan's "QProcess" wording (see Appendix B) |
| D12 | The shell seam is a provider registry plus an `EditorTabState.content_source`. Reading `current_content` is the lazy-serialization trigger. | Hard-wired Markdown wrap; `current_content` copied on every keystroke |

---

## 1. Package layout and import rules

### 1.1 Layout

```
app/features/form_builder/
  __init__.py        docstring only, imports nothing
  install.py         form_builder_enabled(), install_form_builder(ctx); light module level
  engine/            Qt-free
    ids.py  events.py  diagnostics.py  session.py
    ui4/             schema, values, opaque, spec, nodes, document, mutate (private),
                     reader, writer, numfmt, defaults (+ data/qt_classes.json)
    commands/        ops, base, log, context, placement, catalog, catalog_ext/,
                     participants/
    query/           tree helpers, selection model, hit index
    codegen/         api, logic_hooks, expanders/, resources, window_template
    logic/           storage codec (M6.0b); language, rules, data (M7, M8)
    project/         form scope, generated-file policy, connections model
    ipc/             preview protocol schema and codec
    diagnostic_codes/  one module per FB range, each one calls diagnostics.declare
  qtside/            PySide6, imported only through app.qt
    realize/  canvas/  inspector/  outline/  insert/  start/  dialogs/  theme/  icons/
    preview/         pool.py (editor side), child/ (child side)
  integration/       provider, content_source, problems_bridge, settings, theme hook,
                     run/packaging hooks
run_form_preview.py  repo root: three-line runpy shim into qtside/preview/child/main.py
tools/form_builder/dump_qt_classes.py   Qt-side dump script for the class table
```

### 1.2 Import rules (MUST)

| From \ may import | stdlib | `engine.*` | `qtside.*` | `integration.*` | `app.qt` | `app.shell`, `app.editors` | `app.run`, `app.plugins.rpc_protocol` | `app.bootstrap.qt_binding_choice` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `engine/**` | yes | yes | **no** | **no** | **no** | **no** | rpc_protocol only | **no** |
| `qtside/**` (not child) | yes | yes | yes | **no** | yes | **no** | `app.run.process_supervisor`, `app.run.runtime_launch`, rpc_protocol | no |
| `qtside/preview/child/**` | yes | yes | realize values + theme only | **no** | yes | **no** | rpc_protocol | no |
| `integration/**` | yes | yes | yes | yes | yes | yes | yes | yes |
| `install.py` (module level) | yes | yes | **no** | **no** | **no** | **no** (TYPE_CHECKING only) | no | yes |
| `app/shell/**`, `app/editors/**` | — | **no** | **no** | **no** | — | — | — | — |

Other rules:

- Nothing outside `app/qt/` imports `PySide6`, `PySide2` or `shiboken*` directly. This is the existing dune qt-portability rule, and the feature gets no exemption. The Qt side is PySide6-only at runtime, so it may use Qt 6 APIs freely through `app.qt`.
- Only `engine/commands/log.py`, `engine/commands/context.py` and `engine/ui4/reader.py` import `engine/ui4/mutate.py`.
- Engine code stays inside the Python 3.9 grammar and stdlib. That means no `X | Y` unions, `match`, `dataclass(slots=..., kw_only=...)` or `zip(strict=...)`. It also means no third-party packages. `hypothesis` is not vendored, so property tests use seeded `random`.

### 1.3 Mapping to dune (added by M2.1, except where noted)

| Dune artefact | Entry |
| --- | --- |
| `dune.yaml` owners | `form-builder: [app/features/form_builder/**]`. Repo-root `run_form_preview.py` is listed under `form-builder` too |
| `app/features/spec.py` | `FeatureSpec(key="form-builder", ownership_globs=("app/features/form_builder/**",), install=install_form_builder, enabled=form_builder_enabled)`. The key uses a hyphen and the directory an underscore (it has to be importable) |
| verify-cbcs feature doc | `.cursor/skills/verify-cbcs/features/form-builder.md` with `<!-- dune-owners: form-builder -->` and the form builder AT ids |
| handles | Widget object names use the prefix `formBuilder.<area>.<name>` and are listed in `handles.md`. The XML view reuses `shell.editorTabs.textEditor` only through `create_source_editor`, so it is still assigned in exactly one place |
| file role `form_builder.engine` | `app/features/form_builder/engine/**`: denied `("app", "PySide2", "PySide6", "shiboken2", "shiboken6")`, allowed `("app.features.form_builder.engine", "app.plugins.rpc_protocol")` |
| file role `form_builder.qtside` | `app/features/form_builder/qtside/**`: denied `("app.shell", "app.editors", "app.features.form_builder.integration", "app.runner", "app.packaging")` |
| file role `form_builder.child` | `app/features/form_builder/qtside/preview/child/**`: additionally denied `app.features.form_builder.qtside.canvas`, `.inspector`, `.outline` |
| file role `form_builder.mutate_guard` | `app/features/form_builder/**`: denied `app.features.form_builder.engine.ui4.mutate`, allowed_files = the three files in §1.2 |
| `app.shell` / `app.editors` roles | add `app.features.form_builder` to their denied imports (M2.0 does the same for `app.features.markdown`) |
| new rule `feature-install-imports` (M2.0) | see §11.5 |
| composition | install count stays 7. Window fields the install binds are owned through the FeatureSpec globs |
| reaper | `testing/runtime_child_reaper.py` markers gain `run_form_preview.py` (M2.5) |

### 1.4 Registries without shared-file edits

Registries discover modules in a package in sorted module-name order. Each module exposes `register(registry)`. A WP adds its own module and never edits another WP's module or the package `__init__`.

| Registry | Package | Seam WP |
| --- | --- | --- |
| Extra commands | `engine/commands/catalog_ext/` | M1.2 |
| Rename/delete participants | `engine/commands/participants/` | M1.2 |
| Diagnostic codes | `engine/diagnostic_codes/` | M1.0 seeds `fb0xx.py`, `fb5xx.py`, `fb6xx.py`, `fb9xx.py` |
| Codegen expanders | `engine/codegen/expanders/` | M1.3 |
| Property editors | `qtside/inspector/editors/` and `qtside/inspector/api.py` (`RowSpec.editor`, `Choice` / `ValueSpec.choices` / `RowSpec.choices`, `FlagBit` (bool row over one bit; multi-owner edit is one step, reset restores the bit and deletes the property when the set equals the default), `RowWrite.edit`/`reset` may return a tuple of commands run as one step, read-only `EditorHost.document` / `owner_ids` / `qt_names` / `form_shortcuts` (shortcut text → owning widget or action name, from the form document's `shortcut` and `keySequence` only, cached per revision), optional `Editor.caption_widget`) | M3.1b |
| Widget catalog entries | `qtside/insert/catalog/` (Qt-free data) | M4.1 |
| Context-menu contributors | `integration/menu_ext/` (groups "first", "structure", "last"; `MenuContext.at`, `source` `"canvas"` or `"outline"`, `live(node_id)`, `run(command)`; UX-CONT-020) | M4.0s |
| Tab-content providers | registered at install (shell registry) | M2.0 |

---

## 2. Node identity and the document model

### 2.1 Node identity

1. `NodeId` is a positive `int`. `DOCUMENT_ID = 0` is the `<ui>` node. The session's `IdAllocator` hands out ids from 1 upwards, in order.
2. The reader allocates ids in pre-order, in schema slot order. Reading the same text with a fresh allocator always gives the same ids. Replay depends on this.
3. Ids are **never reused** within a session. That holds across undo, redo and `ReplaceDocument`. An id that has left the document never names a different node later. This rules out ABA bugs in maps the Qt side keeps.
4. Ids never appear in the `.ui`, the generated module, the clipboard, the preview IPC, Problems rows or settings. Anything that persists or crosses a process uses **object names**, and diagnostics add a `key`.
5. An object name is an identity, but it isn't guaranteed unique. Files on disk can contain duplicates, and that shows up as FB010, not as an invariant failure. Commands never create a duplicate.
6. After `ReplaceDocument`, every id except 0 is fresh. Views carry selection across by object name (§3.10).

### 2.2 The typed ui4 tree

The kinds are `ui`, `widget`, `layout`, `layoutitem`, `spacer`, `action`, `actiongroup`, `actionref`, `item`, `header`, `buttongroup`, `connection`, `customwidget`, `include`, `resource` and `opaque` (`schema.NodeKind`). For each kind, `schema.SCHEMA` defines:

- the **fields**: immutable scalars, tuples, or frozen dataclasses such as `LayoutDefault`, `SlotsDecl`, `HeaderDecl` and `ConnectionHint`
- the **slots**: ordered child lists, each with the kinds it accepts and a maximum length
- whether the kind carries `<property>` and `<attribute>` lists
- the **write order** of its content groups, and the **attribute order**

The full field lists are in the stub. Elements that only hold values become fields: `<tabstops>`, `<zorder>`, `<slots>`, `<class>`, `<author>`, `<comment>`, `<exportmacro>`, `<layoutdefault>`, `<layoutfunction>` and `<pixmapfunction>`. `<designerdata>` and `<images>` are kept verbatim as `OpaqueElement` fields.

Wrapper elements that Designer writes even when they're empty (`<resources/>`, `<connections/>`) are tracked in the `ui` field `present_wrappers`. That way a document whose last connection was deleted still writes `<connections/>`, the way Designer does.

Write order follows the ui4.xsd `xs:sequence` of each element. That's the order Qt's generated `Dom*::write` emits, so it's also Designer's resave order. For a widget it's: properties, attributes, rows, columns, items, layout, child widgets, actions, action groups, addactions, zorder. The M0.4b Designer-resave corpus is the oracle. If it disagrees with this table, the table changes (with a test).

**The spike was right about** keeping the `.ui` itself as the model instead of a JSON layout file, keeping a single owner of the tree, and keeping unknown content in place. **The spike was wrong about** mixed untyped `body` lists, O(n) `find_node`/`locate`, and having no parent pointers. Production keeps a schema-typed tree with `UiDocument.node(id)`, `parent(id)` and `by_name(name)`, all O(1).

### 2.3 Unknown-content preservation (MUST)

| Input | Model | Output |
| --- | --- | --- |
| Unknown child element of a known element | `OpaqueNode` in that node's `opaque` slot, with `anchor = (group, n)`: `group` is the write-order group it sits in or follows in the input (`""` means before the first group), and `n` is the number of typed entries of that group that came before it | Written at that exact position: after the `n`-th typed entry of `group`. Among opaque siblings with the same anchor, input order is kept. If the group has fewer than `n` entries after edits, it's written at the end of the group |
| Unknown attribute on a known element | `extra_attrs`, in input order | Written after the known attributes, in input order |
| Known value tag whose text doesn't parse without loss (`<bool>1</bool>`, `<double>1e-400</double>`, a `<number>` out of range) | `OpaqueValue` + FB005 (Info) | Byte-identical content |
| Unknown value tag inside `<property>` | `OpaqueValue` + FB005 | Same |
| A second `<property>` with the same name on one node | The **last** copy is the typed entry, because Qt applies properties in order and the last one wins. Earlier copies go to `opaque` + FB007, anchored `("properties", n)` | Same positions: an earlier duplicate stays before the typed entry |
| Unknown `cbcs*` dynamic property, or unknown keys inside logic JSON | Kept as a normal `StringValue` entry. The logic codec keeps unknown keys verbatim | Same text |
| XML comments and PIs outside preserved subtrees | Dropped (Designer drops them too) | — |
| Comments, PIs and mixed text inside an opaque subtree | Kept | Kept |
| `<designerdata>`, `<images>`, deprecated `<script>`/`<widgetdata>`/custom-widget `<properties>` | Opaque | Kept |

The rule behind every row: **`write(read(x))` loads in Qt to the same widget tree as `x`.** Structure that Qt would see is never dropped. The QUiLoader oracle tests this.

### 2.4 Property values

`values.py` has one frozen dataclass for each of the 33 ui4 value elements (R3 283–315), plus `OpaqueValue`. Values are shared by reference across the document, ops, events and undo. Nobody copies them.

1. **Lossless parse rule.** The reader parses each value element into its class only if formatting it again gives the same value. In particular, `parse_real(format_real(v)) == v` must hold for every real. Otherwise the element becomes `OpaqueValue`. This is checked per value, so one odd value never makes a whole property opaque.
2. **Strings are exact.** No stripping and no newline changes inside `<string>`, `<cstring>`, `<enum>`, `<set>` and the like. The spike's `_norm_text` turned whitespace-only strings into empty strings. That was a bug, and it's banned.
3. **Enums and sets by name.** `EnumValue.text` and `SetValue.text` are stored exactly as written. Comparisons use `key()`/`keys()`, which normalise away the enum-type qualifier (`Qt::Horizontal` matches `Qt::Orientation::Horizontal`). New values that commands create use `UiDocument.enum_style()`: the spelling most of that document's enums use, or `DEFAULT_ENUM_STYLE` (set from what Designer 6.8 writes in the M0.4b corpus). Ints never stand in for enums anywhere in the engine.
4. **Translatable strings.** `notr`, `comment` (disambiguation), `extracomment` (translator comment) and `id` are all typed, and each is kept only when present.
5. **Logic properties** (LOGIC_DESIGN §6.1) are `PropertyEntry(kind="property", stdset="0", value=StringValue(text, notr=True))`. They're written after every standard property, in `logic.storage.LOGIC_PROPERTY_ORDER` (§2.5 rank group 2). The layout key `cbcsSplitterSizes` (§9.3) has the same storage shape and sorts first in group 2, but it isn't logic: it's set with `SetProperty`, never adds `cbcsLogic`, and FB402 doesn't make it read-only.
6. `semantic_equal` defines when an edit is a no-op. `value_to_json`/`value_from_json` is the one JSON form, used for IPC and traces.

### 2.5 The class table (defaults)

`engine/ui4/data/qt_classes.json` is committed. It's produced by `tools/form_builder/dump_qt_classes.py`, which runs under FreeCAD 1.1 PySide6 offscreen. Its shape is in `defaults.py`: per class, the super class, flags, properties in property-sheet order (kind, default, designable, stored, volatile, enum type), signals, slots and the default signal; plus an enum table. The engine reads the JSON lazily, once per process, and never imports Qt.

The table is used for exactly these things:

- inspector display of unset values
- Reset (which removes the entry)
- **rank insertion** of new property entries: `property_rank` gives a group (0 Qt, 1 other dynamic, 2 `cbcs*`), then a rank, then a name
- realize's "reset to default" for non-volatile properties
- multi-select applicability
- MorphWidget keep/drop decisions
- signal and slot pickers, and FB015/FB202 checks
- container flags

It's **never** used to decide whether a property gets written. "Changed" (bold in the inspector, R3 146) means "an entry exists". A property that's set to its default value is still written. That's Designer parity: Designer tracks changed-ness, not value equality.

Volatile defaults (font, palette, geometry, sizeHint and anything else that depends on style or platform) are never shown as "the default" and never compared.

Rules the dump and the loader follow, all checked against the Designer-resaved corpus:

- `rank` counts across the class chain (QObject first). A class that declares a property again (`QDialog.modal`, `QDockWidget.windowTitle`, `QGridLayout.spacing`) owns that property's position, because Designer writes it there.
- Designer's sheet has properties Qt's meta-object lacks: the legacy layout `margin` (uic still honours it), the four layout margins and `QLabel.buddy`. The dump lists them after the class's own properties with `"extra": true` and no default. A grid or form layout declares `spacing` again so it follows the margins; box layouts write it before them.
- A subclass that changes an inherited default lists it in `"defaults"` (for example `QLineEdit.cursor`). The committed table is dumped on Linux (the ChoreBoy platform) and records `platform`. The dump runs three passes (Fusion/en_US, Windows/de_DE with a bigger font, and every widget built with a parent). A default that differs between passes, depends on the clock, locale, installed fonts or platform is `volatile` and has none.
- A name the table knows ranks as a Qt property even when the entry says `stdset="0"`. Designer writes that for any property whose setter is not `set<Name>` (`isWrapping`).

A test re-runs the dump against the running Qt and fails on any difference, naming the class and property (§13). If FreeCAD moves to a new Qt minor version, the JSON is regenerated in its own PR.

### 2.6 Mutation

Only the command log changes a document (§3). Node accessors return immutable data: tuples, frozen values and nodes. The mutate guard file role (§1.3) enforces this. The O-logic gate checks it, and so does the property test that fingerprints the document before and after every read-only API call in a random session.

### 2.7 Integrity invariants (`UiDocument.validate`, MUST hold after every entry)

1. Every id in the index is unique. The index holds exactly the nodes reachable from `ui`.
2. `parent(child)` and `parent_slot` agree with the slot that holds the child. The `ui` node has no parent.
3. Every child's kind is accepted by its slot, and single-child slots hold at most one child.
4. There's exactly one root widget.
5. The name index equals a recomputation from the tree. So do the per-node property name maps.
6. Every field holds a value of its declared type. Required fields are set.
7. No `PropertyEntry` identity `(kind, name)` repeats on a node.
8. `revision` is never lower than any previously observed revision.

Semantic problems are **diagnostics**, never invariant failures. That covers duplicate names, dangling buddies, overlapping grid cells and missing connection endpoints. Files on disk contain them, and so may documents that are in the middle of an edit. `CBCS_FB_VALIDATE=1` runs `validate()` after every entry. It's always on in tests.

A QFormLayout cell is (row, role): colspan 2 is the spanning role and covers both cells; column 0 is the label role, any other column the field role; rowspan is ignored. Files may contain two items in one cell (FB023, a diagnostic). Commands never create one; the log checks this after every entry when `CBCS_FB_VALIDATE=1`.

### 2.8 Read-only query helpers

These are in `document.py` and `query/tree.py`: traversal, name lookups and `unique_name` (Designer's `_2`, `_3` suffix rule), grid occupancy, the next free cell, form rows, visual children, reading order, the effective tab order and tab-order splicing (the spike's rule, kept), the real child stacking order (pain 24), native references to a name, page children, container tests and form kind. Each one states its complexity. All are pure.

---

## 3. The command log

### 3.1 Strategy (decided)

**Record ops, don't take snapshots.** A command's `apply(doc, ctx)` reads the live document and calls `ctx.do(op)` for each primitive change. Each op is applied right away, so later reads inside `apply` see it. The mutation primitive returns the exact inverse. The log records `(ops, inverse_ops, allocated_ids)`.

- **Undo** applies `inverse_ops` in reverse order.
- **Redo** re-applies `ops` exactly. It never re-runs `apply`.
- **Replay** (tests and traces) re-runs every command's `apply`, with an allocator that hands back `allocated_ids` in order. It asserts that the produced op sequence equals the recorded `ops`. That proves planners are deterministic.

Why: every structural command, from wrap and morph to paste and rename, reduces to six ops whose inverses can be tested on their own. Entries cost O(changed) memory. Events fall out of the ops mechanically. Snapshotting is kept only for `ReplaceDocument`, where the whole document really is the change.

**The spike was right** that every mutation goes through one history and that structural edits should be patches. **The spike was wrong** to have commands capture state on their first `redo` and keep it in mutable fields. That made correctness depend on call order and needed deep copies. It's replaced by recorded frozen ops.

### 3.2 The Command protocol

A command is a `@dataclass(frozen=True)` with JSON-able fields and a stable `command_type`. `apply` MUST:

- be a pure function of `(document content, its parameters, the ids ctx.alloc() returns, the class table)`. No clock, no environment, no Qt, no set iteration order, and no randomness.
- get every Qt-measured quantity (rects, size hints, visual order) as a parameter.
- raise `CommandRejected` for illegal or stale requests. The log then rolls back whatever `apply` already did.
- report the selection it wants afterwards through `ctx.select`.

### 3.3 The six primitive ops

| Op | Meaning | Inverse | Precondition (`OpError` before any change) |
| --- | --- | --- | --- |
| `InsertNodeOp(parent, slot, index, spec)` | Insert a subtree | `RemoveNodeOp(spec.id)` | Slot exists and accepts `spec.kind`; `0 <= index <= len`; a single-child slot is empty; every id in `spec` is set and not present in the document |
| `RemoveNodeOp(node)` | Remove the subtree | `InsertNodeOp(old parent, old slot, old index, snapshot)` | Node exists and isn't `ui` or the root widget |
| `MoveNodeOp(node, parent, slot, index)` | Re-parent or reorder, keeping ids. `index` counts **after** the node has left its old list | `MoveNodeOp` back to the old position | Target accepts the kind; target isn't inside the node's own subtree; index in range |
| `SetPropertyOp(owner, kind, name, entry, index)` | `entry=None` removes. An existing entry is replaced in place (`index` must be None). A new entry is inserted at `index`, which the planner computes by rank insertion | Restore the old entry at its old index, or remove it | Kind is allowed on the owner; `index` is valid when inserting |
| `SetFieldOp(node, field, value)` | Set a scalar field | `SetFieldOp(old value)` | Field exists, type is valid, a required field isn't cleared |
| `ReplaceRootOp(spec)` | Replace the whole `ui` node | `ReplaceRootOp(old snapshot)` | `spec.kind == "ui"`, `spec.id == 0`, every other id in `spec` is set and not present in the document (except 0) |

Rules for entries: (a) an id removed inside an entry MUST NOT be inserted again in the same entry (use `MoveNodeOp`); `ctx.do` enforces this. (a2) **Freshness** (every id an `InsertNodeOp`/`ReplaceRootOp` inserts came from `ctx.alloc()` in this entry) is checked by `ctx.do` on forward application only. `mutate`, undo and redo never check it, because undo re-inserts old ids and redo re-applies ids allocated earlier. (b) Each op bumps `revision` by one. (c) `apply(op)` then `apply(inverse)` restores `fingerprint()` exactly (§13).

### 3.4 Placement

`commands/placement.py` defines the targets in visual terms: `InBoxLayout`, `InGridCell` (with `mode` cell, insert_row or insert_column), `InFormRow` (role label, field or spanning, with `insert_row`), `InContainer` (pages, panes, free children with optional geometry), `AsMainWindowPart` and `InActionList`. The planner converts these into op indexes. For a move inside one list, the placement index is the position the user saw before the drag. The planner adjusts it to the post-removal index. Putting this adjustment in one place removes the spike's scattered `if src_index < index: index -= 1`.

### 3.5 The command catalog

Owner WP in brackets. The stub `commands/catalog.py` has the fields and full semantics. Every command rejects stale ids.

| Command | Parameters | Key semantics | Selection after | Merge key |
| --- | --- | --- | --- | --- |
| `InsertFragment` [M1.2] | placement, fragment, auto_layout | Covers insert, paste, duplicate, Alt-drag clone, palette drop and templates. Names get the suffix rule. References inside the fragment follow renames; references to outside names stay (LOGIC 2.13). A connection whose both ends are in the fragment is kept and rewritten. A connection with one end outside the fragment is kept only when that end does not name a widget on the target, and then it is FB014. An outside end that already exists on the target is dropped. Custom-widget and resource declarations are merged. An empty container with no layout gets a QVBoxLayout first (pain 1). A container that already has free children keeps them and takes the paste as another free child | inserted top-level nodes | — |
| `DeleteNodes` [M1.2] | ids | Descendants of other deleted ids are ignored. Box layout items are removed; **grid and form cells are left empty**. The same entry removes native references: connections, tab stops, zorder, addaction refs, buddy cstrings, `buttonGroup` attributes. **Logic references are kept** and become FB101 | nearest surviving sibling, else parent | — |
| `MoveNodes` [M1.2] | ids, placement | Moves keep ids. A grid move changes only the moved items' cells (pain 21). Emptied layouts stay | moved | `("move", ids)` |
| `Wrap` [M1.2] | ids, container_class or None, layout_class, cells | Siblings only. The new container takes the first item's place. Order is kept. `cells` comes from the live geometry for grids | new container or layout | — |
| `Unwrap` [M1.2] | id | Children go back to the parent layout at the container's position, in visual order. Rejected for the root and for page containers | children | — |
| `ApplyLayout` [M1.2] | widget, layout_class, order, cells | Lay out a container that has no layout. Removes child `geometry` | layout | — |
| `BreakLayout` [M1.2] | layout, geometries | Keeps sizes (R3 41, pain 5), using geometries measured from Qt. A nested layout's items move up instead | owner | — |
| `MorphLayout` [M1.2] | layout, new_class | Designer morph rules (R3 54) | layout | — |
| `MorphWidget` [M1.2] | id, new_class | Keeps properties the new class has (class table) and reports the ones it drops | widget | — |
| `SimplifyGrid` [M1.2] | layout | Removes empty rows and columns | layout | — |
| `AdjustSize` [M1.2] | id, size | Size is measured as the sizeHint | — | — |
| `SetZOrder` [M1.2] | parent, order | `order` comes from `child_stack_order`, the real child list (pain 24). Document order clears the field | — | — |
| `SetProperty` [M1.2] | owner, name, value or None, kind, stdset, merge_token | None means Reset (removes the entry). A semantically equal value is a no-op. Rank insertion | — | `("set_property", owner, kind, name)` |
| `SetPropertyMany` [M1.2] | owners, … | R3 147. Owners without the property are skipped and reported | — | `("set_many", owners, kind, name)` |
| `Rename` [M1.2] | id, new_name | Rejects invalid names, keywords, names starting with `cbcs`, reserved formula names and names already used (FB011, FB106, FB010). Updates every native reference, and `<class>` when the old root name matched it. Participants add logic ops. User code isn't touched | — | — |
| `SetLayoutCell` [M1.2] | item, row, column, spans, alignment | Rejects grid overlaps and form cells that are taken. | — | — |
| `SetLayoutStretch` [M1.2] | layout, field, value | Comma-list text | — | `("layout_stretch", layout, field)` |
| `SetGeometry` [M1.2] | id, rect | Free widgets and resizing the root page edge | — | `("geometry", id)` |
| `MovePage` [M4.2] | container, from, to | Keeps the current page current | page | — |
| `InsertPage` [M3.2, M4.2] | container, index, fragment or existing | Writes the page title where the container's loader reads it: tab `title` attribute, toolbox `label` attribute, wizard `title` property on a `QWizardPage`, MDI `windowTitle` property, stacked none (UX-CONT-001). New page gets a vertical layout. Keeps `currentIndex` on the same page | new page | — |
| `DeletePage` [M4.2] | container, index | Deletes the page and its subtree with DeleteNodes reference rules; keeps `currentIndex` on the same page, else clamps | next page, else previous, else container | — |
| `SetItems` [M4.4] | widget, items, rows, columns, merge_token | Replaces the whole item list. One item-editor session merges into one entry (UX-ITEM-007) | — | `("set_items", widget)` with the session token |
| `CreateAction`, `AddActionRef`, `CreateMenu` [M5.1] | spec/placement/name/title | "Type here", dragging an action onto a toolbar (pain 17) | new node | — |
| `AddConnection`, `EditConnection`, `MoveConnection` [M6.1] | fields | Signatures are normalised the way Designer writes them | connection | — |
| `SetTabStops` [M5.6] | names or None | None removes the element | — | — |
| `SetBuddy` [M5.6] | label_widget, target | Sets the `buddy` cstring | — | — |
| `SetButtonGroup` [M5.1] | buttons, group or None | Creates the group, or removes it once it's empty | — | — |
| `SetFormSlots` [M6.2] | signals, slots | `<slots>` | — | — |
| `Promote`, `SetCustomWidget` [M5.4] | ids, class_name, declaration | Demoting removes declarations nobody uses | — | — |
| `SetResourceIncludes` [M5.2] | locations | — | — | — |
| `SetFormField` [M5.5b] | field, value | Form settings, includes | — | — |
| `ReplaceDocument` [M2.2] | text, reason | §3.10 | matched by name | — |
| `SetLogic` [M6.0b] | owner, key, text or None, merge_token | Uses the logic codec. Keeps `cbcsLogic` in step. Rejected with FB402 when the document's logic version is newer than supported | — | `("logic", owner, key)` |

Compound gestures are **transactions** of these commands, not new commands. Examples: "Pair labels with their fields", a double-click stub plus its connection (M6.2, where the user-file edit is a paired text edit outside the log; see §9.5), and a drop that also wraps.

### 3.6 Participants

`RenameParticipant.rename_ops(doc, renames, scope)` and `.references(doc, name)`, plus `DeleteParticipant.delete_ops`. These are discovered from `participants/` and sorted by `participant_id`. M6.0b adds the formula, step-target and error-label participants. Participants are pure and add ops to the same entry.

- `renames` is a tuple of `(old, new)` pairs applied **simultaneously** (one pass, so `x→x_2` and `x_2→x_3` in the same map never chain). `scope: Optional[FrozenSet[NodeId]]` limits the rewrite to owners inside the set; None means the whole document.
- `Rename` calls participants with a one-pair map and `scope=None`.
- `InsertFragment` computes its **whole** rename map before inserting, against `doc.names()` plus the names it has already chosen for this fragment. It rewrites native references inside the fragment specs before insertion, then calls participants with `scope` = the inserted subtree ids, so references to the original nodes outside the fragment stay unchanged.
- **Shared names (FB010).** When the old name is used by more than one node, references are ambiguous. `Rename` renames the node and rewrites **no** references; `DeleteNodes` removes **no** references to that name. Both add the existing FB010 to the result so the UI can say so.
- `Rename` also rewrites `buttonGroup` attribute values on buttons when a button group is renamed.

### 3.7 Ownership

One `FormSession` per tab owns: the `UiDocument`, the `IdAllocator`, the `CommandLog`, the `SelectionModel`, the `DiagnosticsStore` and the `SerializationCache`. Sessions never share any of these. The shell already de-duplicates tabs by path, so one file is never open in two sessions. The clipboard is process-wide and carries fragment XML (`writer.write_fragment`) plus the MIME type `application/x-cbcs-form-fragment`. It never carries node objects or ids. Cross-form paste is `read_fragment` followed by `InsertFragment`.

### 3.8 Execution rules

- **No-op.** A command or transaction that applies zero ops pushes nothing and emits nothing.
- **Failure.** Any exception rolls back every op of the entry (or the whole transaction), emits nothing and re-raises. Non-`CommandRejected` exceptions are logged and wrapped with FB999. The document is byte-identical to its state before.
- **Merge.** Merge into the top entry only when all of these hold: same non-None `merge_key()`, same non-None `merge_token`, not inside a transaction, the top entry isn't the save point, and the redo stack is empty. The merged entry is: `ops = top.ops + new.ops`, `inverse_ops = top.inverse_ops + new.inverse_ops` (undo still applies them in reverse), `commands = top.commands + (new,)`, `allocated = top.allocated + new allocated`, `selection_before` from the top entry and `selection_after` from the new command. **Net nil** means every touched `(owner, kind, name)` property and every touched `(node, field)` now equals the value its **first** inverse op restores, and the entry contains no insert, remove, move or replace op. A net-nil entry is popped, and the ChangeSet is still emitted.
- **Gesture continuation.** `log.execute(cmd, continue_gesture=True)` opens an entry that absorbs every later command carrying the same non-None `merge_token`, **whatever its `merge_key()`**, under the same other conditions (no transaction, not the save point, empty redo stack). That serves UX-FORML-002: the drop and the label text typed right after it are one undo step. The first command with a different or absent token closes the gesture.
- **Gesture tokens.** The Qt side sends one token per gesture: from an editor getting focus to its commit, a scrub drag, a handle drag, a page-edge drag, a drop that continues into in-place editing, and a **nudge burst**: repeated Alt+arrow moves (or arrow nudges) where each press comes within **1 s** of the previous press (UX-NUDGE-001's window; the **UI** owns that timer). The engine has no timers.
- **Transactions.** `with log.transaction(label):` joins nested transactions into the outermost one. Committing produces one entry and one ChangeSet. **Every Qt-measured parameter** (`Wrap.cells`, `BreakLayout.geometries`, `ApplyLayout.order`/`cells`, `AdjustSize.size` and any other) is measured **before the transaction opens**, because realize doesn't run until commit. A planner that needs measurements of nodes created or moved earlier in the same transaction raises `CommandRejected` instead of guessing.
- **Re-entrancy.** `execute`, `undo` and `redo` raise `ReentrantCommandError` when called from a ChangeSet listener. Listeners schedule follow-up work on the Qt event loop.
- **Save point.** `is_dirty()` is O(1). Undoing past the save point and then executing makes the save point unreachable. `mark_saved()` moves it. When the undo limit (2000) drops the save-point entry, the save point becomes unreachable.
- **Undo, redo and selection.** Undo restores `selection_before`; redo restores `selection_after`. Both are filtered to ids that are present.

### 3.9 Invariants (tested, §13)

1. **Single writer.** Every document mutation goes through `CommandLog`. Nothing else imports `mutate`.
2. **Replay equals live.** `replay(initial_text, log.entries())` reproduces the recorded ops exactly, and `fingerprint()` equals the live document's (ids included).
3. **Undo-all equals original.** Undoing every entry restores `fingerprint()` and `write_ui` bytes to the state after the read.
4. **Redo-all equals final.** Redoing everything afterwards restores the final fingerprint.
5. **Round trip per op.** For every op type and random preconditions, applying the op and then its inverse is the identity.
6. **Events are complete.** A `ShadowTree` listener that uses only ChangeSets to maintain parent/slot/children and property maps equals the document after every entry, undo and redo (§4.4).
7. **Atomicity.** A failed command or transaction leaves the bytes unchanged and emits zero ChangeSets.

### 3.10 ReplaceDocument

This covers View XML commit, draft restore, local-history restore, and external reload ("take theirs"). It parses with the reader. On a parse error it raises `CommandRejected` carrying `UiReadError` (code, line, column), and the caller keeps both texts. On success it applies one `ReplaceRootOp` with fresh ids, and the inverse holds the old snapshot. So undoing a View XML edit, a restore or a reload is one step. Selection is carried across by object name, with the root as fallback.

External reload of a clean tab is `ReplaceDocument(reason="reload")` followed by `mark_saved()`. Of a dirty tab it's the three-way choice: keep mine (no change), take theirs (the reload path), or compare (open a diff). This is M2.2's UI.

---

## 4. Change events

### 4.1 Schema

The shape is in `events.py`. Changes are `NodeInserted`, `NodeRemoved`, `NodeMoved`, `PropertyChanged`, `FieldChanged` and `DocumentReplaced`. `NodeInserted` and `DocumentReplaced` carry `spec: NodeSpec`, the subtree taken from the op (do, redo) or from its inverse (undo), shared by reference, so a listener can rebuild from ChangeSets alone. Each carries a `category`: `node`, `property`, `layout`, `item`, `page`, `action`, `connection`, `logic`, `form`, `name` or `document`. A `ChangeSet` adds the derived sets `removed`, `added`, `structure_dirty`, `property_dirty` (net), `renamed` and `categories`, plus `replaced`. They're computed once per set, in O(changes).

### 4.2 Category rules (deterministic, from the op and the document at apply time)

- `PropertyChanged` on a `cbcs*` name is `logic`, except the layout keys in `logic.storage.CBCS_LAYOUT_KEYS` (`cbcsSplitterSizes`), which are `property`. On an `item` or `header` owner it's `item`. Otherwise it's `property`.
- Insert, remove or move of `item`/`header` is `item`. Of a `widget` whose parent is a page container's `children` slot it's `page`. Of `action`/`actiongroup`/`actionref` it's `action`. Of `connection` it's `connection`. Of `customwidget`/`include`/`resource`/`buttongroup` it's `form`. Everything else is `node`.
- `FieldChanged`: `object_name`/`name` is `name`. Layout item cell and alignment fields, layout stretch fields, and a layout's `class_name` are `layout`. `ui` fields are `form`. Connection fields are `connection`. A widget's `class_name` (morph) is `node`. `zorder` is `node`.

### 4.3 Delivery and batching

- One ChangeSet per committed entry: a single command, a merged command or a transaction. One per undo and one per redo. Origin is `do`, `undo` or `redo`. A transaction never emits partial sets.
- It's delivered synchronously after the entry has been applied in full. The document is consistent and `validate()` passes.
- Order of delivery: ascending priority (`PRIORITY_MODEL_CACHES` 0, `SELECTION` 5, `DIAGNOSTICS` 8, `REALIZE` 10, `HIT_INDEX` 20, `VIEWS` 30, `SHELL` 40), then subscription order.
- Listeners MUST NOT mutate (they get `ReentrantCommandError`), MUST be O(changes) or schedule heavier work for later, and MUST treat `DocumentReplaced` as "rebuild everything". A listener exception is logged and doesn't stop the other listeners. The realizer recovers on its own (§5.2).
- Subscribe with `log.subscribe(fn, priority=...)`, which returns a `Subscription` with `close()`. `FormSession.dispose()` closes everything.

### 4.4 Consistency guarantee

Because changes come from ops one-to-one, replaying a ChangeSet stream on a mirror rebuilds the document's structure. That's the test in §3.9 item 6. It's also what lets realize, the outline and the hit index trust events without rescanning the form.

---

## 5. Realize patch protocol

### 5.1 Mapping events to patches

| Change | Patch |
| --- | --- |
| `PropertyChanged` on a widget, layout, spacer or action | Re-read the **current** entry from the document and apply it. Patching never uses the event's `new` value, so it's idempotent and safe in any order. A removed entry restores the class-table default. Volatile defaults come from a cached fresh instance of that class, created once per class per process |
| Insert, remove or move (any category except connection and form) | Add the parent to the dirty-container set |
| `FieldChanged` on a layout item cell or alignment, or a layout stretch field | Reconcile that layout |
| `FieldChanged` `class_name` (morph) | Rebuild that node's object and reuse its child widgets from the pool |
| `FieldChanged` `object_name`/`name` | `setObjectName`, then re-resolve buddies that name either the old or new name |
| Connections, tab stops, form slots, includes | Nothing (the canvas never wires connections and never sets focus order) |
| Custom widget `extends` changed | Rebuild the widgets of that class |
| `FieldChanged` `zorder` | Restack that parent's child widgets (`raise_()` in `child_stack_order`) |
| Attribute change on a page (`title`, `label`, `icon`, `toolTip`, `whatsThis` of a tab, toolbox or wizard page) | Patch the parent container's tab/item text, icon or tip for that page index |
| `PropertyChanged` `cbcsSplitterSizes` on a QSplitter | `setSizes(...)` after the splitter's panes are in place (§9.3) |
| `DocumentReplaced` | `build()` |

### 5.2 Reconcile and fallback

Reconcile runs in three phases per ChangeSet:

1. **Detach moves.** Every object named by a `NodeMoved` is detached into a pool keyed by node id, wherever it currently is. This matters when a node moves into a container that comes earlier in the top-down order than the one it left.
2. **Reconcile structure.** For each id in `structure_dirty`, top-down by depth: detach that container's remaining live children (layout, page container, menu, or layout-less widget) into the pool, then re-attach the model's children in model order, taking objects from the pool and constructing only ids that aren't in it.
3. **Destroy and purge.** Destroy pooled objects whose ids are in `changeset.removed`, then remove every id in each `NodeRemoved.subtree` from the id maps (descendants included, not only the subtree root).

That's the spike's approach of moving live widgets instead of rebuilding a subtree, which was **kept**. It's now driven by `structure_dirty` instead of a scan over the whole form. Main-window chrome (menubar, menus, toolbars, docks) is reconciled the same way, per container. The spike's "structural edits to a main window rebuild the whole canvas" is **replaced**.

Fallback: any exception inside a patch rebuilds the nearest ancestor widget subtree and increments `PatchStats.fallback_rebuilds`. If that rebuild also fails, it runs `build()`. Fallbacks are logged with the change that caused them (FB901 in debug). The standard command set MUST run with zero fallbacks (§13).

### 5.3 Identity mapping and lifecycle

- Every realized QObject carries the dynamic property `_cbcsNodeId`. The `Realizer` keeps id-to-object dicts, so `widget_for`, `layout_for` and `object_for` are O(1). `node_for(obj)` walks up to the nearest tagged ancestor, which covers internal children such as a spin box's line edit.
- `Realizer.refused(node_id, name) -> Optional[str]` (M4.2, for UX-PED-009) is O(1): the reason the canvas widget did not take the value of `name`, set when `setProperty` returns False for a real Qt property or the setter raises, cleared when the property is next applied or the node is removed. `problems()` stays the flat build log. A reset to a fresh widget's value passes enums and flags as their number, which PySide6's `setProperty` requires.
- Removed objects are destroyed **immediately** through an immediate-delete helper in `app/qt` (M2.1 adds it, wrapping shiboken's delete). Never `deleteLater`: the spike found deferred deletes never ran under nested `processEvents`, and memory grew by 30 MB.
- Realized widgets never receive input or focus. They get focus policy `NoFocus` and `WA_TransparentForMouseEvents`, and the overlay gets every event. There are no per-widget event filters (the spike measured about 20 ms per open for them).
- The realizer never connects `<connections>`. It never imports or runs user code, generated modules, `*_rc.py` or Designer plugins. Promoted widgets become their `extends` class, with a "custom" badge drawn by the overlay. `:/` paths resolve through `codegen.resources.compile_resource_tree` registered with `QResource.registerResourceData`.

### 5.4 Runtime palette isolation (MUST)

The canvas shows the shipped app's look, never the chrome theme (`qtside/theme/runtime.py`):

1. The form root lives in a `QGraphicsProxyWidget`. It's never a QWidget descendant of the main window, so `window.setStyleSheet(...)` doesn't cascade into it.
2. The scene gets `setStyle(Fusion)` and `setPalette(Fusion standard palette)`. No realized widget gets a chrome palette, font or style sheet. The form's own `styleSheet` property is applied as authored.
3. While the feature is enabled, the application-level style sheet may contain only `QToolTip` rules. Today that's `set_app_tooltip_style_sheet`. A test parses it.
4. A shell theme switch never touches the scene. A test compares the realized palette's window and text colors before and after a dark/high-contrast switch with a reference realized in a bare QApplication.

### 5.5 Hit-test index

The index is Qt-free logic in `engine/query/hit_index.py`, fed by the `qtside/canvas/geometry.py` `LiveGeometrySource`.

- **Invalidation is O(1)**: it bumps an epoch. Triggers are every ChangeSet (subscriber at `PRIORITY_HIT_INDEX`), zoom, root resize, page switch, scroll-area scroll, splitter move, text-size preview, style/palette/DPI change, realize rebuild, and showing or hiding a realized widget. Nothing else invalidates it.
- **Refresh is lazy.** It runs only in `ensure_fresh()` at the start of a pointer event, a keyboard navigation that needs rectangles, or the view's `UpdateRequest`/pre-paint hook. **`settle()` never runs inside `paintEvent`** (activating layouts there would schedule another paint); the overlay's `paintEvent` only reads an index that was made fresh before the paint. It never runs in a listener or on a timer. A refresh is `settle()` (synchronous root-layout activation) followed by one pre-order walk that adds up parent offsets (no per-widget `mapTo`). Budget: 4 ms at 300 widgets.
- **Query** goes O(depth × siblings) down the hit tree and returns the deepest visible entry plus its path. That replaces the spike's linear `hits` list.
- **Drag** state is set through the controller seam (plan gate 10). The index isn't invalidated mid-drag except by zoom or scroll.

---

## 6. Selection and focus

### 6.1 The model

There's one `SelectionModel` per session, shared by canvas, outline and inspector. No view keeps its own selection.

- `SelectionState(ids, current)`: ids are ordered and unique, all present in the document. `current` is None exactly when `ids` is empty, and otherwise is a member of `ids`. An empty selection means the inspector shows the form (spike DESIGN: never empty).
- Mixed kinds are allowed. The inspector shows the properties common to all selected nodes. Rubber band selects widgets only.
- Every change carries a `SelectionSource`: canvas, outline, inspector, command, undo, prune or program.

### 6.2 Rules

- Selection by itself isn't undoable. Each entry snapshots it, so undo and redo restore it (O-UX check 4).
- `apply_changeset` runs at `PRIORITY_SELECTION` (5): the **state** is updated there, so later listeners read the new selection. It restores a snapshot when one applies, otherwise it prunes removed ids. If `current` was removed, it moves to the nearest surviving ancestor.
- Selection **subscribers** are notified after the last log listener for that ChangeSet (`PRIORITY_SELECTION_NOTIFY`, 100), so realize (10), the hit index (20) and views (30) have already run. Changes made outside a ChangeSet (clicks) notify immediately.
- Unknown ids passed to `set` are dropped silently, since stale UI is normal.
- Hover is local to each view and isn't part of the model.

### 6.3 Focus contract

- Keyboard focus belongs to exactly one of: the canvas view, the outline tree, an inspector editor, the XML editor, or a popover.
- **A selection change never moves keyboard focus.** Only the user's own input in a view, or an explicit focus command, moves it: Shift+F2 goes to the inspector name field, Alt+B to Behavior, Esc from the inspector returns focus to the view that had it last.
- Renaming in the outline keeps focus in the outline (pain 25). Committing an inspector edit keeps focus in that editor. Undo and redo keep focus where it is.
- **Reveal:** on a change from source X, every other view reveals `current`. The outline expands and scrolls to it. The canvas scrolls it into view only for sources outline, program or undo. The inspector shows `current`. The view that made the change doesn't re-scroll itself.
- The inspector rebuilds at most once per event-loop turn (coalesced). The outline and canvas overlay update synchronously within budget (§12).

---

## 7. Diagnostics

### 7.1 Record

`FormDiagnostic(code, severity, message, location, source, fixes)` and `key`. `DiagnosticLocation(node_id, object_name, property, rule_path, span, line)` points at a node, a property or attribute, a path inside logic JSON (`("cbcsValidate", 1, "pattern")`) or a connection index, a span inside a formula, and the XML line. `QuickFix` holds either an engine `command` (run through the log; if planning rejects it the fix is shown disabled) or a Qt-side `action` id (`open-raw`, `go-to-code`, `refresh-schema`, `create-method`…). Messages use LOGIC_DESIGN §2.9's plain voice.

### 7.2 Codes

The ranges are in `diagnostics.py`. Codes 101–402 come from LOGIC_DESIGN §2.9 and keep its numbers and meanings. New codes:

| Code | Severity | Meaning |
| --- | --- | --- |
| FB001 | Error | Malformed XML (line, column). Blocks the visual editor; the file opens as text |
| FB002 | Error | Not a `<ui>` document, or no root widget. Blocks the visual editor |
| FB003 | Warning | `<ui version>` isn't 4.x |
| FB004 | Error | DOCTYPE or entity declaration refused. Blocks the visual editor |
| FB005 | Info | A value was kept exactly as written (shown read-only) |
| FB006 | Info | An unknown element was kept as written |
| FB007 | Warning | A property was given twice; the last one is used, the earlier one kept |
| FB008 | Error | File too large or too deeply nested. Blocks the visual editor |
| FB010 | Error | Two objects share a name |
| FB011 | Error | A name isn't a valid Python identifier |
| FB012 | Warning | A buddy names a missing widget |
| FB013 | Warning | A tab stop names a missing widget |
| FB014 | Error | A connection's sender or receiver is missing |
| FB015 | Warning | A connection's signal or slot isn't on that class (class table; user slots go to FB2xx) |
| FB020 | Warning | Grid items overlap |
| FB021 | Warning | A widget sits outside the layout of a laid-out container (the broken-layout marker, R3 34) |
| FB022 | Info | An empty layout |
| FB023 | Warning | Two items share a form cell |
| FB030 | Warning | A promoted class is used but not declared (Info when declared but unused) |
| FB106 | Error | A widget uses a name reserved for formulas (`form`, `record`, `window`, `cbcs…`, function names). LOGIC 4.5 said FB101; FB101 stays "unknown name in a formula" |
| FB501 | Warning | `ui_<name>.py` had been edited by hand; a copy was saved before regenerating |
| FB502 | Error | A construct can't be generated (the node is named) |
| FB503 | Error | A resource file is missing |
| FB504 | Warning | A promoted class's header isn't an importable Python module path |
| FB505 | Warning | A generated file is out of date with its form |
| FB506 | Info | The form isn't part of a project, so no Python is generated |
| FB507 | Error | The form's file name can't be a Python module name |
| FB508 | Warning | A `<connection>` names a signal the sender's class doesn't have. A plain Qt sender's line is left out; a `Gui::`, promoted or C++ `::` sender keeps uic's line (§9.3) |
| FB509 | Error | A generated file could not be written |
| FB601 | Error | The preview process stopped unexpectedly (stderr tail attached) |
| FB602 | Warning | A custom widget couldn't load in the preview; the base class was used |
| FB603 | Error | Preview protocol version mismatch |
| FB604 | Error | An exception happened in Try mode (traceback mapped to the rule) |
| FB605 | Warning | Preview is off after repeated crashes (Retry) |
| FB901 | Info | A realize fallback happened (debug builds only) |
| FB999 | Error | An internal error in a command (shown as a status message, logged) |

### 7.3 Rules

- **No diagnostic blocks saving** (test). Only FB001, FB002, FB004 and FB008 can block **opening the visual editor**, and the file then opens as text.
- A logic error generates no code for that rule. The rest of the form generates and runs (LOGIC 2.9).
- **Producers** publish per `source` into `DiagnosticsStore`, which replaces atomically. Cheap producers (names, references, layout sanity) run synchronously at `PRIORITY_DIAGNOSTICS` and are O(changed): they work from `added`, `removed`, `renamed` and `property_dirty`. Expensive producers (formula type-check, parsing handler files, schema checks) are coalesced to idle by the Qt side. Full revalidation happens only on open and on `DocumentReplaced`.
- Codes are declared once in `diagnostic_codes/`. Emitting an undeclared code fails a test.

### 7.4 Reaching the Problems panel

`integration/problems_bridge.py` maps each record to `CodeDiagnostic`:

- code: the FB code
- severity: the same value
- file_path: the `.ui` path
- line_number: `location.line` or 1. The line comes from the last serialization's line map, or the reader's
- message: `"<object>: <message>"`
- detail: `to_problem_detail`, which carries `fb_key`, `fb_object`, `fb_property`, `fb_rule_path` and `fb_source`, **never the node id**

The bridge pushes through `ProblemsController.apply_lint_diagnostics_result`, coalesced to one push per event-loop turn. `.ui` files aren't linted, so the form owns that path's slot. A double-click calls `TabSurface.reveal(line, detail)`, which selects the node by `fb_key` (falling back to the object name) and opens the property or rule.

---

## 8. Serialization

### 8.1 Reader

`read_ui(text, allocator=..., source_path=...)` returns `ReadResult(document, diagnostics, line_map)`, or raises `UiReadError(code, message, line, column)`.

- It uses `xml.parsers.expat` directly: positions for every element, faster than building an ElementTree first, and DOCTYPE and entity declarations refused (FB004). Inputs over 16 MB or nested deeper than 256 levels are refused (FB008). A leading BOM is ignored. CRLF and CR are accepted.
- Whitespace-only text between elements is ignored. Text in value leaves is exact (§2.4.2).
- It follows the preservation table in §2.3 and the lossless parse rule in §2.4.1.
- **Fuzz contract:** for any input string, `read_ui` returns or raises `UiReadError`. Nothing else, and no hang: it's linear in the input.

### 8.2 Writer byte rules (`write_ui`, MUST)

1. The first line is `<?xml version="1.0" encoding="UTF-8"?>`. Line endings follow the Appendix E "Line endings" row. The file ends with `</ui>\n`. There's no trailing whitespace on any line outside text content (text content is exact, §2.4.2).
2. Indentation is one space per level, Designer's QXmlStreamWriter auto-format.
3. Element order follows `schema.write_order`, with opaque children after their anchor (§2.3). Attribute order follows `schema.attr_order`, then unknown attributes in input order.
4. *(Provisional until M0.4b.)* An element with no content is written `<x/>`. Designer writes empty strings as `<string/>` and `<string notr="true"/>` (verified by the gate reviewer). Elements Designer writes through `writeTextElement` with empty text come out as `<x></x>`. The writer keeps one table, element by element, of which empty form to use; M0.4b fills it from the corpus (see the table below).
5. Escaping: in text and attributes, `&`→`&amp;`, `<`→`&lt;`, `>`→`&gt;`, `"`→`&quot;` (QXmlStreamWriter's set). In attributes, tab, LF and CR are also written as `&#9;`, `&#10;`, `&#13;`. A CR in **text** is written as `&#13;` so it survives the reader's newline normalisation; that's a deliberate deviation from Qt and goes on the M0.4b diff allowlist. Non-ASCII is written as raw UTF-8, never as character references. This **corrects LOGIC_DESIGN §6.3**, which said `>` is left unescaped. Designer files contain `&lt;html&gt;…`. `SetProperty`, `SetPropertyMany` and `SetLogic` reject (`CommandRejected`) any text containing characters outside the XML 1.0 `Char` range, so the writer never has to emit an unloadable file.
6. *(Provisional until M0.4b.)* Numbers go through `numfmt`. Ints are plain. `<double>` and double-valued children are `format(v, ".15f")` (Designer's `'f', 15`). `<float>` is likely 8 decimals, not 15, so `numfmt` has separate `format_double` and `format_float` functions. How `-0` is written is pinned by M0.4b (provisionally `0.000000000000000`). Booleans are `true`/`false`. No locale and no `str(float)` anywhere in the writer.
7. Logic JSON text is written exactly as the codec produced it (LOGIC 6.3 canonical form). The writer doesn't reformat it.

**M0.4b must pin** (rules 3, 4 and 6 and §2.4.3 stay provisional until each row has a corpus-backed answer and a writer test):

| Question | Provisional answer |
| --- | --- |
| Empty form for each element (`<x/>` or `<x></x>`), per element and per attribute set | `<string/>`, `<string notr="true"/>` verified; others per corpus |
| `<float>` precision | 8 decimals |
| `<double>` precision | 15 decimals |
| How `-0` is written | `0.000000000000000` |
| `DEFAULT_ENUM_STYLE` | `qualified` |
| Whether Designer writes empty `<resources/>` and `<connections/>` | yes (kept through `present_wrappers`) |
| Where Designer places `stdset="0"` `cbcs*` entries, and whether it keeps `notr` on them | after standard properties; `notr` kept |
| Attribute order on `<property>` (`name`, `stdset`) and on `<string>` (`notr`, `comment`, `extracomment`, `id`) | as listed |

### 8.3 Determinism (MUST; tested on macOS and Linux, under `C` and `de_DE`, with `PYTHONHASHSEED` 0, 1 and random)

- `write_ui` is a pure function of document content. Ids are excluded.
- No clock, no environment variables, no locale, no `hash()` and no set iteration in any output path. Sets are sorted before output.
- Dicts are iterated only where insertion order is itself deterministic.
- Double save gives identical bytes: `write(read(write(read(x)))) == write(read(x))`.
- The same holds for codegen output, `*_rc.py` and IPC frames.

### 8.4 Lazy serialization

XML exists only when someone reads it, through `SerializationCache.text(doc)`, memoized by `revision`. The triggers are:

| Trigger | How it reads |
| --- | --- |
| Save | `EditorTabState.current_content` → `FormContentSource.current_text()` |
| Local-history snapshot | Same |
| Draft autosave | The shell's lazy draft path: on debounce, if `content_source.revision()` changed since the last draft, read `current_text()` (§11.2) |
| View XML | `session.text()` once, on entering XML mode |
| Preview load of an external form | `session.text()` for `LoadForm.ui_xml` |

Codegen works from the in-memory document and never re-reads the XML. A test (§13) runs 200 edits and asserts `serialize_count == 0`.

### 8.5 Malformed input

When a file won't open, the provider declines (§11). The file opens as text with an info bar: "This form can't be opened in the form builder: <reason> (line N)." The Problems panel gets FB001, FB002, FB004 or FB008. Leaving View XML with text that doesn't parse keeps XML mode with the same banner and keeps both versions (§11.2). A newer `cbcsLogic` makes the logic read-only (FB402). The layout stays editable, and the logic is written back untouched.

---

## 9. Codegen

### 9.1 Entry points

| Function | Input | Output |
| --- | --- | --- |
| `generate_form_module(doc, scope, source_bytes, options)` | Document, `FormScope`, `source_bytes: Optional[bytes]` (the exact `.ui` bytes just written; None for preview, which writes no source hash line), `CodegenOptions` (the uic flags relevant to Python, R3 322–330) | `CodegenResult(text or None, diagnostics, attribute_names, resource_modules, uses_freecadgui, header)` |
| `render_header`, `read_header`, `is_hand_edited`, `is_stale` | — | Header handling (§9.2) |
| `read_qrc`, `compile_resource_tree`, `render_rc_module` | `.qrc` text, a file reader | `ResourceTree` (also used for in-editor resources), `*_rc.py` text |
| `render_window_class(doc, scope)` | — | The initial `<stem>_window.py` |
| `plan_stub(window_source, …)` | User file text (parsed with `ast`, never executed) | `StubPlan(TextEdit, stub_text, method_name)` |
| `LogicExpander.contribute(doc, ctx)` | — | `Contribution` (§9.4) |

### 9.2 Header and hash scheme

`render_header` gives the exact text. It's the LOGIC 7.1 banner plus three machine lines: `## cbcs-codegen: 1`, `## cbcs-source-sha256: <hex>` and `## cbcs-body-sha256: <hex>`. The body is every byte after the header. There are no timestamps and no Qt or host versions in the header, so it's deterministic across machines.

- **Hand-edit detection.** Before overwriting, if the existing file's header is missing or its body hash doesn't match, the file is copied to `<project>/cbcs/form_builder/hand_edits/<name>.<body8>.py.txt`. The `.txt` suffix keeps it from being imported, linted or collected as Python. M2.4 adds `cbcs/form_builder` to the pruned subtrees in `app/packaging/payload_policy.py`, next to `cbcs/runs`, `cbcs/logs` and `cbcs/cache`, so it never ships. M2.3 also excludes `cbcs/form_builder/**` from lint, project search, pytest collection and Jedi indexing. Then it's overwritten and FB501 is raised with "Open the saved copy". User work is never lost.
- **Staleness.** `is_stale(text, ui_bytes)` compares the source hash and the codegen version. Packaging (M2.4) flags FB505, and so does opening a form whose generated file is stale.

### 9.3 Body shape

- It's the shape `uic -g python` 6.8.3 writes: the same statement order and names, `retranslateUi`, `QMetaObject.connectSlotsByName` (unless `-a` or `connectslotsbyname="false"`), and form-slot connections written as `Form.method` exactly the way uic writes them (LOGIC 3.5).
- **Imports** are `from PySide6.QtCore import (...)` and so on, the same as uic. They're never the FreeCAD `PySide` shim.
- **FreeCAD `Gui::` classes** use the spike's guarded import, which was right and is kept: `try: import FreeCADGui as _cbcs_FreeCADGui` / `except ImportError: _cbcs_FreeCADGui = None`. A helper creates the widget through `FreeCADGui.UiLoader().createWidget(class, parent, name)` and falls back to the `extends` Qt class.
- **Promoted Python classes** are imported from their header's module path (`from <header module> import <Class>`).
- Resource modules are imported in uic style, subject to the import-style options.
- Output is Python 3.9-parseable (`ast.parse(..., feature_version=(3, 9))`). This **corrects LOGIC 7.1 rule 4**, which said "Python 3.11". The plan's fixed decision says 3.9.
- Node ids never appear in the output.
- **Names that can't be generated.** An object name on disk that isn't a valid identifier, is a Python keyword, or clashes with `setupUi`, `retranslateUi` or a `_cbcs_*`/`cbcs_*` name gives **FB502 Error naming the node**. `text` is None and the old file on disk stays.
- **String literals** use one deterministic rule that doesn't depend on the Python version's Unicode tables: `u"` + text + `"`, where `\` → `\\`, `"` → `\"`, LF → `\n`, CR → `\r`, tab → `\t`, other code points below U+0020 and U+007F → `\xNN`, surrogates U+D800–U+DFFF → `\uNNNN`, and every other character (all other non-ASCII included) written as raw UTF-8. Never `repr()`.
- **Splitter sizes.** A QSplitter with a `cbcsSplitterSizes` dynamic property (comma-separated ints, `stdset="0"`, written through plain `SetProperty`, not `SetLogic`; it doesn't add `cbcsLogic`) gets `self.<splitter>.setSizes([...])` at the end of `setupUi`, before `retranslateUi`, emitted by the core through a fixed helper. This is the stored-sizes mechanism UX-SPLIT-002 refers to: release of a handle drag is one `SetProperty`, and double-click writes equal sizes measured by the Qt side. The uic oracle ignores this one call.
- Every generated output is also `compile()`d under the real Python 3.9 AppRun in the gate runner (`testing/run_form_builder_checks.py`, lane `syntax-py39`), in addition to `ast.parse(feature_version=(3, 9))`.
- The oracle is tree equality with uic's module on every corpus file, plus a reported text diff (M1.3).

### 9.4 Logic expansion hooks

The core owns everything uic emits, which covers Level 1 and Level 2 native connections. Expanders, discovered from `codegen/expanders/` and ordered by `order` (built-ins: 100 step lists, 200 state rules and values, 300 checks, 400 data), contribute `imports`, `setup_lines`, `methods` and `helpers`. When any expander contributes setup lines, `setupUi` ends with `self._cbcs_setup(<form>)` after `connectSlotsByName`. Generated names start with `cbcs_` or `_cbcs_`. Each method begins with a comment that quotes its source rule (`source_ref`), so tracebacks map back to the rule. Helpers come from a fixed table, are emitted once each, in table order. A rule that errors contributes nothing and reports a diagnostic. Expanders never raise.

### 9.5 Scope, window class, stubs

- Generation runs only when `FormScope.generates` is true: the form is under `<project>/forms/` or adopted (`classify_form`). External forms are edited without writing anything beside them (FB506 Info).
- The window class file is created once (`render_window_class`) and never overwritten. It uses an absolute import from the project root, and `forms/__init__.py` is created when it's missing.
- Stub insertion (M6.2) is a `TextEdit` applied through the open code tab's document when there is one (so it lands in that tab's undo), or written to the file otherwise.
- The M6.2 compound "create handler" pairs a log transaction (the connection) with that text edit. Undo removes the stub only while its text still hashes to `stub_text` (LOGIC 2.13).

### 9.6 Save pipeline (integration, M2.2)

1. Get `current_text()` and atomically write the `.ui`.
2. `mark_saved`.
3. If the scope generates and the text parses: `generate_form_module(doc, source_bytes=<the bytes from step 1>)`, run the hand-edit check, and atomically write `ui_<name>.py`, plus `*_rc.py` for any changed `.qrc`.

A codegen failure never fails the save; it reports FB5xx. Steps 1–3 take ≤ 50 ms CPU at 300 widgets.

---

## 10. Preview and Try-mode IPC

### 10.1 Transport and framing

- The editor side (`qtside/preview/pool.py`) uses `app.run.process_supervisor.ProcessSupervisor`: an argv list, no shell, `start_new_session=True`, killpg on stop, and a sanitized AppRun environment. The command is `[AppRun, "-c", build_runpy_bootstrap_payload(script_path=<repo>/run_form_preview.py, ...)]` with `CBCS_QT_API=pyside6`. Supervisor events arrive on reader threads, and a queued Qt signal marshals them to the GUI thread before anything decodes or touches widgets.
- The child keeps both frame streams private. At startup it does `requests = os.fdopen(os.dup(0))` then `os.dup2(<devnull>, 0)`, so user code reading stdin gets EOF instead of eating frames; and `frames = os.fdopen(os.dup(1))` then `os.dup2(2, 1)`. User `print` becomes `Log` frames, and Qt messages become `Log(stream="qt")`.
- A frame is `FRAME_PREFIX` (`"\x1eCBFP1 "`) followed by the JSON and a newline. The JSON is `rpc_protocol.encode_message` semantics (`sort_keys=True`), and the line is pure ASCII. Lines without the prefix become `NoiseLine`s, which go to the debug log. Prefixed garbage is a `ProtocolViolation`; three in one session restart the child. Frames are limited to 32 MB.

### 10.2 Messages (version 1; schema in `engine/ipc/protocol.py`)

| Direction | Message | Purpose |
| --- | --- | --- |
| child→host | `ready` | QApplication is up: pid, Python, Qt and PySide versions, whether FreeCADGui is available |
| host→child | `hello` | Protocol name, version, session token, host pid. A mismatch gets `error="protocol_mismatch"`, the child exits 3, and the host raises FB603 and opens the circuit |
| host→child | `load_form` | Open or replace a view. Project forms send `module_source` (generated **in memory** from the current, possibly unsaved, document, with `source_bytes=None`); external forms send `ui_xml` (QUiLoader with plugin paths cleared, plus a `createWidget` override). Also `resource_modules` (name and in-memory `*_rc.py` source, registered first), `promoted` (class, header module, extends), `sys_path`, `appearance`, `keep_values`, `revision`. The child pre-imports each promoted class; on failure it installs a stub class of that name subclassing `extends` and reports FB602, so the form still loads. Before each `load_form` the child drops every `sys.modules` entry whose file lives under the previous project root, so edited user modules are re-imported |
| host→child | `update_form` | Property-only patches by object name since `base_revision`, only for nodes whose object name is unique in the document. Anything structural, a rename, a duplicate-named node, or an unpatchable property gets a full `load_form` instead. The child answers `stale` when it isn't at `base_revision`. At most one request per view is in flight; newer ones coalesce |
| host→child | `set_appearance` | Palette (default runtime), style, scale, font scale, device profile |
| host→child | `try_start` / `try_stop` | Run the generated module with a stand-in window class and window values (LOGIC 2.10). The data plan covers SQLite scratch copies and PostgreSQL `rollback` (SET LOCAL statement and lock timeouts) or `would_run` |
| child→host / host→child | `need_secret` / `provide_secret` | Passwords are only sent on request, per connection, and are never written to logs |
| host→child | `grab`, `close_view`, `ping`, `shutdown` | — |
| child→host | `response` | `rpc_protocol.build_response` shape. Errors use `ERROR_CODES` |
| child→host | `log`, `view_closed`, `error`, `crash` | Logs (including Try-log lines with a `SourceRef`), view closed, survived failures (FB602, FB604) with frames mapped to rules, and a best-effort crash report |

Versioning: a change that breaks compatibility bumps `PROTOCOL_VERSION` and `FRAME_PREFIX` together. Adding an optional field doesn't need a bump, and receivers ignore unknown fields.

### 10.3 Lifecycle

- There's **one warm child per editor process**, shared by every form tab. Each tab is a `view_id`. **Pre-warm is on by default**: the child is spawned when the first form opens (a setting can turn this off, and then it starts on the first request).
- The handshake times out after 30 s (a cold AppRun start is included). A request times out after 20 s. While views are open the host sends `ping` every 5 s; the child answers on its GUI thread, so a stuck event loop is noticed.
- **Hang.** A request timeout, or two missed pings in a row, means the child is hung. The host kills the process group and treats it exactly like a crash (FB601, backoff below).
- **Crash-loop backoff.** A crash happens when the child exits while views are open, when it hangs (above), or after three protocol violations. Every view's session gets FB601 with the last 40 stderr lines. Restarts wait 0, 1, 4 and 15 s for consecutive crashes within 120 s. After that the circuit opens (FB605), and the user's Retry closes it. Views reload after a restart.
- The child exits by itself on `shutdown`, on stdin EOF (the host died), or after 600 s with no views.
- When the editor exits it sends `shutdown`, then `supervisor.stop()` (SIGTERM to the process group, then SIGKILL). `tests/conftest.py` reaps by the `run_form_preview.py` marker.

### 10.4 Security rule (MUST)

User code runs **only** in the child. That includes window classes, promoted and custom widget classes, user modules, `window.method()`, generated `ui_*.py` and `*_rc.py`. The editor process may `ast.parse` user files but never imports or runs them. It also never loads Designer plugins and never calls `QUiLoader` on project files. The child never imports `app.shell`, `app.editors` or `integration` (file role `form_builder.child`). Secrets cross the pipe only in answer to `need_secret`.

---

## 11. Tab-content provider seam (M2.0)

### 11.1 Protocols (stubs `app/shell/tab_content_providers.py`, `app/editors/tab_content_source.py`)

- `TabContentProvider(provider_id, priority, matches(path, ctx), create_surface(request))`. `matches` is a pure path test. `create_surface` may raise `ProviderDeclined(reason)`, in which case the shell opens a text tab with an info bar.
- `TabSurfaceRequest` gives the provider the path, the initial text, the parent, the theme, `open_linked_file`, the project root, and `create_source_editor()`. That builds a **fully bound** `CodeEditorWidget` (the same code path as text tabs, including the `shell.editorTabs.textEditor` object name and workspace registration). It can be called at most once. Markdown calls it eagerly. The form builder calls it on the first View XML, which keeps a ~100 KB XML editor out of the 150 ms open budget.
- `TabSurface` has `widget()`, `content_source()`, `source_editor()`, `apply_theme`, `set_diagnostics`, `reveal(line, detail)`, `restore_text(text, reason)`, `close_blockers()`, `file_path_changed`, `focus_primary` and `release`.
- `TabContentProviderRegistry` has `register`, `provider_for`, `surface_for_path`, `surfaces` and `apply_all_themes`. It's a committed window field bound by the platform. Features call `register` from `install`.

### 11.2 Dirty source and lazy text

- `EditorTabState` gains `content_source: Optional[TabContentSource]`. `current_content` becomes a property that delegates when a source is attached. `is_dirty` delegates too. `update_content` on a sourced tab raises `ValueError`. `mark_saved` passes the exact saved text through.
- **Save transforms.** Sourced tabs skip every save transform (trailing-whitespace trim, final newline, format on save). Save writes `current_text()` encoded as UTF-8 with no BOM.
- **Registry field.** The committed window field `_tab_content_registry` becomes the `TabContentProviderRegistry`. It's bound in `install_editors`, before the `FEATURE_SPECS` loop, so feature installs can register into it. `_markdown_panes_by_path` moves under markdown's ownership globs.
- **Late services.** Feature install runs before `install_run_debug`, so the form builder's Run and packaging hooks look up their services lazily (at first use), never during install.
- The shell's draft autosave gains a lazy path for sourced tabs. The source's `subscribe_changed` schedules the debounce, and when it fires the shell reads `current_text()` only if `revision()` changed. Text widgets keep today's push path.
- `FormContentSource` (integration, Qt-free) has visual mode and XML mode, with exact rules in its stub. Saving in XML mode writes the typed text verbatim. Leaving XML mode commits one `ReplaceDocument`, or stays in XML mode with the error and both versions kept.

### 11.3 FeatureSpec.enabled

`FeatureSpec(..., enabled: Optional[Callable[[], bool]] = None)`. The composition loop calls `enabled()` once per process before `install`. The predicate must not import Qt and must not raise (an exception counts as False). The form builder's predicate is `CBCS_FORM_BUILDER != "0"` and `qt_binding_choice.select_binding() == "PySide6"`, the import-free equivalent of `IS_QT6`. Under PySide2, `.ui` files open as XML text exactly as they do today, plus the hint "The visual form builder needs FreeCAD 1.1" (M2.1).

### 11.4 Shell call sites M2.0 routes through `TabSurface` when a provider owns the tab

These are: `EditorTabFactory._materialize_opened_editor_tab` (asks the registry first); `wrap_tab_content_if_markdown`, which is deleted and replaced by the Markdown provider; `ProblemsController.push_diagnostics_to_editor` (`set_diagnostics`); the theme appliers (`apply_all_themes`); `LocalHistoryWorkflow.maybe_restore_draft` and history restore (`restore_text`); external file change (`restore_text("external_reload")` or the three-way prompt); close prompts (`close_blockers` in addition to the standard dirty prompt); rename and move (`file_path_changed`); Problems navigation (`reveal`); and release on close. M2.0 audits every `_editor_widgets_by_path` user. Each one either keeps working with the source editor or calls the surface, and the PR lists them.

AT-32: on PySide6, step 3 ("Open `.ui` … expected XML highlighting") is done through View XML, which is the same `CodeEditorWidget` with the XML grammar. M2.2 amends AT-32's wording to say so. On PySide2 nothing changes.

### 11.6 Round 2 seam corrections

These are the behaviours the v0.4.13 sync has to keep.

- The project-tree coordinator reads open tab paths from the live `EditorManager`. `reset_editor_tabs()` replaces that manager on project switch. A method bound at composition time is stale, and a delete in the new project would leave the tab open.
- Replacing a preview releases the closed preview's surface by path and buffer id. The editor manager has already dropped that tab. A lazy surface never registered a source editor, so popping by buffer id alone leaves the path bound.
- Cancelling the three-way reload prompt on a dirty sourced tab with no source editor marks the tab changed on disk and returns declined. The stale bar stays. The next save still prompts. Acknowledging the mtime and returning cancelled hides both.
- `close_group` asks `close_blockers` once, for the paths shown only in that group, before the unsaved-changes prompt. The closes that follow pass `skip_close_blockers`. A No leaves the group as it was.
- The second editor group's markdown pane is built and adopted by the markdown feature (`build_secondary_pane`, `adopt_secondary_pane`). That feature owns `_markdown_panes_by_path`.
- A tab whose provider declined is a text editor inside a notice container. The container's `source_editor()` returns that editor, so the tab can be split. It does not implement `apply_theme`, `set_mode`, or `toggle_preview`.

### 11.5 Dune rule `feature-install-imports` (M2.0)

For `app/features/spec.py`, every `app/features/*/install.py` and every `app/features/*/__init__.py`: module-level imports outside `if TYPE_CHECKING:` must come from the stdlib, `typing`, `app.bootstrap.qt_binding_choice`, `app.features.spec`, or the feature's own `engine` subpackage. Imports inside functions are unrestricted. Markdown's `install.py` moves its pane and registry imports into `install_markdown`. The proof is a runtime test, not the lint: a subprocess installs a `sys.meta_path` finder that only **records** import attempts (it never raises, so a lazy import elsewhere can't change behaviour), then imports `app.features.spec` and calls every `enabled()`. It asserts that no `PySide6`/`shiboken6` entry is in `sys.modules` and none was recorded. On a PySide6 machine it also asserts `form_builder_enabled()` is True. It runs on machines without PySide2 too. With `CBCS_QT_API=pyside2` where PySide2 exists, the editor starts and `PySide6` is not in `sys.modules`.

---

## 12. Performance contracts

These are measured as process CPU time, p95, n = 15 after warmup, on the Mac baseline, using the M1.5 harness. They're re-checked on the VM and on the CPU-capped profile (plan §1). "300w" means the 300-widget reference form.

| Contract point | Complexity | Budget |
| --- | --- | --- |
| `read_ui` | O(input) | 25 ms (300w) |
| Class table first load | once per process | 25 ms |
| `Realizer.build` | O(form) | 90 ms (300w) |
| Outline full build | O(form) | 15 ms |
| **Open total** (read + build + outline + inspector + first index) | — | **150 ms** (plan) |
| One command (apply + ops + ChangeSet derivation + engine listeners) | **O(changed)** | 2 ms at 300w, 3 ms at 1000w |
| Realize patch per ChangeSet | **O(changed widgets + reconciled children)** | 8 ms |
| Hit index invalidate | O(1) | — |
| Hit index refresh | O(visible nodes) | 4 ms (300w), 12 ms (1000w) |
| Hit query | O(depth × siblings) | 0.2 ms |
| Overlay paint | O(visible) | 4 ms |
| Outline patch per ChangeSet | **O(changed)** | 2 ms |
| **Edit total** (command → repainted canvas, outline, coalesced inspector) | — | **16 ms** (plan) |
| Selection change → canvas overlay + outline | O(selection) | 8 ms. Inspector repopulate ≤ 16 ms, may lag one frame |
| `is_dirty`, `revision` | O(1) | — |
| Cheap diagnostics producers | **O(changed)** | 2 ms |
| `write_ui` | O(form), lazy only | 10 ms (300w) |
| `generate_form_module` | O(form), on save | 30 ms (300w, no logic) |
| **Save total** | — | **50 ms** (plan) |
| Memory | — | ≤ 30 MB extra per open form, ≤ 60 MB with three forms. The undo log grows O(changed): 500 property edits ≤ 2 MB |
| Preview warm update (`update_form` → child repaint) | O(patches) | 100 ms wall |
| Preview cold start | — | Measured and reported against the M0.7 fact; no budget |

**O(form) is allowed only for:** read, build, `ReplaceDocument`, serialize, codegen, `validate`, fingerprints, hit-index refresh, full diagnostic revalidation (on open or replace only), reading-order and effective tab order (tab-order mode and codegen only), and `Rename`/`DeleteNodes` reference scans (3 ms at 1000w). Everything else on the edit path is O(changed). Adding an O(form) step to the edit path is a contract violation even when it fits the budget at 300w.

---

## 13. Test contracts (feed the O-logic gate)

Generators live in `tests/support/form_builder/gen.py`: random documents over every node kind and value kind, random valid command sequences generated against the live document, and byte-level mutators for fuzzing. They use seeded `random`. The seed and the case count are printed on failure, and `FB_SEED=<n>` reproduces a run. The fast lane runs 200 sequences × 30 commands. The gate run (O-logic evidence) runs 5,000 sequences × 50 commands plus 20,000 fuzz inputs. Tests assert behaviour, never constants (see `.cursor/rules/test_anti_patterns.mdc`).

| Module (WP) | Invariants and property tests a PR MUST include |
| --- | --- |
| `ui4.values`, `numfmt` (M1.1b) | Every value kind: `value_from_json(value_to_json(v)) == v`; read → write → read equality; the lossless rule sends non-round-trippable reals and bools to `OpaqueValue`; `semantic_equal` on enum spellings; real formatting is identical under `de_DE` and `C` |
| `ui4.reader`/`writer` (M1.1a–c) | Corpus round trip 100% (structure fingerprint plus QUiLoader tree equality); double save byte-identical across machines, locales and hash seeds; the Designer-resave zero-diff oracle (allowlist kept in the ledger); random unknown elements and attributes injected anywhere are preserved in place; fuzz contract (only `UiReadError`, linear time, no hang); DOCTYPE refused; line maps point at start tags |
| `ui4.document` (M1.1a) | `validate()` passes after every random op; name index equals recomputation; the API never mutates (fingerprint before and after every read call in random sessions) |
| `ui4.defaults` (M1.1b) | Dump-vs-runtime equality under the current Qt (fails naming the class and property); `property_rank` gives a total order; rank insertion keeps Designer-saved files' property order unchanged |
| `commands.ops` + `mutate` (M1.2) | Every op type: apply then inverse is the identity (fingerprint); each `OpError` precondition leaves the document untouched |
| `commands.log` (M1.2) | §3.9 invariants 1–7 over random sequences, including interleaved undo and redo; merge (one gesture's edits undo to the value before the gesture; returning to the original pops the entry and restores clean state); save point (dirty after undo past save then edit); transaction rollback (exception mid-transaction gives identical bytes and zero ChangeSets); `ReentrantCommandError` |
| `commands.catalog` (M1.2 and owners) | For each command: a semantics test for its documented rules (for example DeleteNodes removes native references but keeps logic references; a grid move changes only the moved cells; Rename updates every reference kind in `references_to`); random use inside the log-level property tests; planner determinism through replay |
| `events` (M1.2) | ShadowTree equality (§4.4); `property_dirty` is net (set then reset in one transaction is absent); category rules for every op and kind pair |
| `query.selection` (M3.1) | After any entry, `ids` ⊆ document and `current` ∈ `ids` or is None; undo and redo restore snapshots; no listener moves focus for a change from another source (Qt test) |
| `query.hit_index` (M3.1) | After random edits, zoom and page switches, `query` equals a brute-force oracle over live widgets (`childAt` plus layout geometry); refresh count is exactly one per invalidated paint; zero refreshes inside listeners |
| `qtside.realize` (M3.1) | **Patch equals rebuild:** after each random command, undo and redo, `Realizer.signature()` equals a fresh `build()` signature; `fallback_rebuilds == 0` for the standard set; destroyed-widget count equals removed widget ids; no user or generated code imported (an `import` hook records the modules loaded during a session over a project with promoted classes); runtime palette unchanged across theme switches |
| `codegen` (M1.3) | uic tree equality on every corpus file plus the text diff; `ast.parse(feature_version=(3, 9))` on every output; determinism (bytes identical across hash seeds); header round trip; `is_hand_edited` and `is_stale` truth tables; ids absent (generate from two documents with different ids and the same content, compare bytes); an expander that raises or errors leaves the core output plus the other rules intact; evaluator ≡ generated code (M7.1) |
| `codegen.resources` (M5.2) | Our `*_rc.py` and rcc's register identical path → bytes maps; bytes independent of mtimes and zlib |
| `project.forms` (M1.4) | Classification truth table; external scope never writes beside the form |
| `diagnostics` (M1.0 codes, all producers) | Unique codes; no undeclared code emitted; no diagnostic blocks save (save succeeds with every code present); incremental producers equal full revalidation after random sequences |
| `ipc.protocol` (M2.5) | `decode_line(encode_frame(m)) == m` for random messages; noise lines interleaved at random never break decoding; prefixed garbage gives `ProtocolViolation`; frames are ASCII-only |
| `preview.pool` (M2.5) | With a fake clock and fake supervisor: the backoff schedule, the circuit, coalescing (one in flight per view), handshake mismatch gives FB603; with a real child: kill -9 mid-session leaves the editor alive and the reaper clean; cold and warm timings recorded |
| Provider seam (M2.0, M2.2) | The Qt import-blocker test (§11.5); Markdown behaviour unchanged (existing tests); dirty comes from the log; `serialize_count == 0` over 200 edits; draft restore and history restore are each one undoable ReplaceDocument; malformed `.ui` opens as text with FB001; AT-32 still passes |

The PR body for any logic WP lists: the invariants touched, the seeds and case counts, the oracle results, double-save hashes from macOS and Linux, and the failure-mode table (malformed input, newer format version, missing method, missing driver, lost connection).

---

## Appendix A. Spike: kept, replaced, dropped

| Spike element | Verdict | Production |
| --- | --- | --- |
| `.ui` as the model, a single owner of the tree, unknown elements kept | **Keep** | §2 |
| `History` + command classes, every edit through history | **Keep the rule, replace the mechanism** | Recorded frozen ops with inverses; redo re-applies ops; replay verified (§3) |
| Commands that capture state on first `redo` and `deepcopy` nodes | **Replace** | Frozen `NodeSpec` ops (D4) |
| `find_node`/`locate` tree walks (O(n) per lookup) | **Replace** | O(1) indexes (§2.2) |
| Untyped `body` lists of mixed parts | **Replace** | Schema-typed slots, ui4.xsd write order (§2.2) |
| `_norm_text` stripping whitespace-only text | **Drop (bug)** | Exact value text (§2.4) |
| `defaults.py` omitting "default" properties on write | **Drop (lossy)** | The writer writes every entry; the class table drives Reset only (D8) |
| Deterministic writer, one-space indent, `\n` | **Keep** | Pinned byte rules (§8.2) |
| Realize moving live widgets instead of rebuilding | **Keep** | §5.2 |
| `units(doc)` signature scan on every structural edit | **Replace** | `structure_dirty` from events (D5) |
| Main-window structural edits rebuilding the whole canvas | **Replace** | Per-container reconcile |
| `_reset_property` constructing a fresh widget per reset | **Replace** | Class-table default; one cached instance per class for volatile defaults |
| Overlay as a child of the view, on top of the proxy | **Keep** | §5.3 |
| Deferred hit index | **Keep the laziness, replace the structure** | O(1) epoch invalidation, hit tree queries (§5.5) |
| Removing the per-widget event filter, freeing replaced forms at once | **Keep** | §5.3 |
| Chrome style sheet never on the app, explicit runtime palette | **Keep and strengthen** | Scene-level style and palette plus tests (§5.4) |
| Guarded FreeCADGui import for `Gui::` widgets | **Keep** | §9.3 |
| Preview inside the editor process | **Drop** | Child process only (§10.4) |
| Tab order splicing, next free cell, buddy pairing | **Keep as query helpers / transactions** | §2.8, §3.5 |
| Spike UI (canvas, inspector, outline) | **Redesign** | From the UX spec (M0.9), not from these contracts |

## Appendix B. Corrections to upstream documents (folded in, no decision needed)

1. **LOGIC_DESIGN §6.3** says `>` is written unescaped "as Qt does". QXmlStreamWriter escapes `>` as `&gt;` (Designer files show `&lt;html&gt;`). §8.2 rule 5 is the rule.
2. **LOGIC_DESIGN §7.1 rule 4** says "Python 3.11 and PySide6 only". The plan's fixed decision says generated code is Python 3.9-parseable. §9.3 follows the plan.
3. **LOGIC_DESIGN §4.5** gives reserved widget names code FB101. That's now **FB106**; FB101 keeps the meaning "unknown name in a formula".
4. **PLAN §3** says the preview child is "started with QProcess". CBCS's existing supervision code, which the plan also says to reuse, is `ProcessSupervisor` (`subprocess.Popen`, argv list, no shell, process group). It's already proven on ChoreBoy for the runner and the plugin host. §10.1 uses it. The M0.7 probe should confirm the AppRun cold start through the same path.
5. **PLAN §3 (`__init__.py` FeatureSpec)**: the predicate lives in `install.py` and uses `qt_binding_choice.select_binding()`, so importing `app.features` never imports a binding (§11.3).
6. **AT-32** step 3 on PySide6 is done through View XML. M2.2 amends the wording (§11.4).

## Appendix C. Open questions for the orchestrator

1. **Generation options storage.** The uic-flag equivalents (`CodegenOptions`) need a home. This contract puts them in project settings (`cbcs/project.json`, a per-project default with per-form overrides), not in the `.ui` file, because Designer has no place for them and uic takes them as command-line flags. M5.5b needs a yes or no before it writes settings keys. Nothing in M1–M3 depends on it.
1. **Generation options storage.** The uic-flag equivalents (`CodegenOptions`) need a home. This contract puts them in project settings (`cbcs/project.json`, a per-project default with per-form overrides), not in the `.ui` file, because Designer has no place for them and uic takes them as command-line flags. M5.5b needs a yes or no before it writes settings keys. Nothing in M1–M3 depends on it.

## Appendix D. Gate responses (O-logic review of M1.0, 18 items)

1. Done (§3.3, `ops.py`): presence is the op precondition; freshness is checked by `ctx.do` on forward application only.
2. Done (§3.8, `log.py`): concatenated ops and inverses, appended commands, new `selection_after`, net-nil defined against first inverses (and only for property/field-only entries).
3. Done (§3.5, §3.8, `catalog.py`, `log.py`): `MoveNodes` key `("move", ids)`; `execute(..., continue_gesture=True)`. Nudge window: **1 s between presses**, matching UX-NUDGE-001 as written, so **no UX_SPEC clause text changes**; the contract's old "500 ms after release" is removed. Extra: `cbcsSplitterSizes` added (§2.4, §4.2, §5.1, §9.3, `storage.py`); UX-SPLIT-002's "mechanism per CONTRACTS.md" now resolves to it.
4. Done (§3.8): measure before the transaction opens; planners needing in-transaction measurements reject.
5. Done (`events.py`, §4.1): `spec` on NodeInserted and DocumentReplaced.
6. Done (§5.1, §5.2, `realize/api.py`): three phases; zorder, page-attribute and splitter-size rows added.
7. Done (§6.2, `selection.py`, `events.py`): state at 5, notification at `PRIORITY_SELECTION_NOTIFY` = 100.
8. Done (§5.5, `hit_index.py`, `geometry.py`).
9. Done with one addition (§3.6, `participants/__init__.py`): besides `scope`, `rename_ops` takes the whole rename map applied simultaneously, because InsertFragment's map can contain chains (`x→x_2` while the fragment's own `x_2→x_3`), which sequential one-pair calls would double-rename.
10. Done (§2.3, `schema.py`, `nodes.py`): `anchor = (group, n)`.
11. Done (§8.2 rules 1 and 5, `catalog.py`).
12. Done (§8.2 rules 4 and 6 provisional, M0.4b table, `numfmt.py` split into `format_double`/`format_float`).
13. Done (§10.1, §10.2, §10.3, `protocol.py`, `pool.py`, `child/main.py`): (a)–(f) as written; ping is answered on the child GUI thread so hangs in user code are caught.
14. Done (§9.1, `codegen/api.py`).
15. Done (§11.2, `tab_content_source.py`, `tab_content_providers.py`).
16. Done (§11.5): recording-only finder plus the two assertions.
17. Done (§9.3, `codegen/api.py`): FB502 for unusable names; pinned string-literal rule (independent of Python's Unicode tables, so 3.9 and 3.11 give the same bytes); `syntax-py39` compile lane.
18. Done (§9.2, `codegen/api.py`): `.py.txt` backup name; M2.3 exclusions.

Nothing was rejected.

## Orchestrator resolution of open questions (2026-10-21)

- **Codegen options (uic-flag equivalents):** stored in project settings (`cbcs/project.json`), with a per-project default and per-form overrides, as proposed. They only affect M5.5b.
- **Stub location:** the typed stubs live in `docs/form_builder/contracts/stubs/` as the reference. Each work package copies the stubs it owns into `app/...` and implements them; it does not import from `docs/`.

## Appendix E. Writer pins from the Designer resave corpus (M0.4b, fixed 2026-10-21)

Source: `tests/form_builder/corpus/designer_resaved/FINDINGS.md` (Qt Designer 6.8.3 from the FreeCAD 1.1.4 AppImage re-saved 209 forms). These replace every "provisional" rule in §8.2.

**Policy.** The writer's target is Designer's bytes for every construct Designer keeps. Where Designer drops data, our writer stays lossless, and the difference goes on an allowlist. The oracle `test_designer_resave_diff.py` turns from xfail into a hard gate once only allowlisted differences remain (WP M1.1d).

| Rule | Fixed value |
| --- | --- |
| Empty elements | Self-closing `<x/>` when present and empty, `<string/>` and `<string notr="true"/>` included. Empty `<author>`, `<comment>` and `<exportmacro>` are omitted. |
| `<double>` | 15 fraction digits everywhere, including inside pointf, rectf, sizef and gradient stops. `-0` is written `0.000000000000000`. |
| `<float>` | Designer drops floats on save. We keep them, written with 8 fraction digits; `-0` is written `0.00000000`. Allowlisted. |
| Enums | Written qualified: `Qt::Orientation::Horizontal`, `QFrame::Shape::Box`. Single-token attribute enums such as `TopToolBarArea` stay as they are. Values read unqualified are written qualified, as Designer does. |
| Unknown dynamic enums and sets | Designer drops them. We keep them verbatim. Allowlisted. |
| `<resources/>` and `<connections/>` | Always written, self-closed when empty. The `name` attribute on `<resources>` is dropped, as Designer does. |
| Dynamic `cbcs*` properties | Written after the widget's standard properties, with `stdset="0"` and attribute order `name`, `stdset`. `notr` is kept when present and never added. |
| Attribute order | `<property name stdset>`; `<string notr comment extracomment id>`; the same for `<stringlist>`. |
| Tag spellings | `longLong`, `UInt`, `uLongLong`, `gradientstop`, `cursorShape` (named shape). Reading stays case-insensitive. |
| `<sizepolicy>` | Attribute form: `hsizetype="Preferred" vsizetype="Preferred"`, with `horstretch` and `verstretch` children. |
| `stdset` | `stdset="1"` is omitted; `stdset="0"` is written. Layout `margin` is stored with `stdset="0"`. |
| Redundant `objectName` | Omitted when it only repeats the widget or layout `name`. |
| `<iconset>` | One line: `<iconset [theme=…]><normaloff>a</normaloff>[<normalon>b</normalon>…]a</iconset>`. The normal path is written once as text after the last state. Designer drops `resource` and `alias`; we keep them (allowlisted). |
| `<script>`, `<widgetdata>`, `<propertyspecifications>`, `<images>`, `<addpagemethod>` | Designer drops them. We keep them (allowlisted, §2.2 MUST). |
| Comments | Comments inside opaque subtrees are kept. Comments outside them are dropped (§2.3). |
| Palette | Stored roles only. Legacy `<color>` lists are kept verbatim and never converted. No roles are added from the live palette. A `<color>` without `alpha` stays without `alpha` (Designer writes `alpha="0"`, which reloads as transparent). |
| Line endings | Preserved per file: LF stays LF, and a CRLF source is written CRLF on every line. |
| Indentation and declaration | One space per level, no trailing whitespace, final newline. `<?xml version="1.0" encoding="UTF-8"?>` is always written first. |
| Text escaping | `"` in text becomes `&quot;` (already §8.2.5). |
