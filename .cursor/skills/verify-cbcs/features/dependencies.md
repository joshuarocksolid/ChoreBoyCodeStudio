# Dependencies

The user adds a local wheel, zip, or folder to `vendor/` without a terminal, inspects the manifest, removes a dependency, and sees native-extension warnings.

Owns AT-90–95.

<!-- dune-owners: platform.project -->

## Sub-features

- `dep-add` **Tools → Add Dependency...** ingests a local package into `vendor/` and `cbcs/dependencies.json`.
- `dep-native-warn` warns on native extensions (AT-92).
- `dep-inspect` **Tools → Dependency Inspector...** lists metadata (AT-93).
- `dep-remove` updates the manifest and optionally cleans vendor (AT-94).
- `dep-package-gate` packaging preflight requires a complete manifest (AT-95).

## How to get to it (user POV)

- **Tools → Add Dependency...** / **Dependency Inspector...**.
- Package Project preflight (see [packaging-installer.md](./packaging-installer.md)).

## Driving it with control-cbcs

Preconditions:

- Project open; disposable HOME.
- A pure-Python wheel or folder staged on the share.
- Doctor passed.

- **Add.** `control-cbcs arm "$SID" shell.action.tools.addDependency` (modal wizard). Complete it with the staged package. Guest `vendor/` contains the package. `cbcs/dependencies.json` has an entry. Shot `dep-added`.
- **Native warning.** If you have a native wheel fixture, add it. The wizard shows a warning before finish. Cancel leaves the manifest unchanged.
- **Inspect.** `control-cbcs trigger "$SID" shell.action.tools.dependencyInspector` (`show()`, not `exec_()`). Window title is **Project Dependencies**. There is no `#shell.dependency*` handle. The row shows name / version / source.
- **Remove.** Remove the entry. The row stays with `status=removed`. Manifest updates.
- **Proof.** Copied `cbcs/dependencies.json` plus a listing of `vendor/` in artifacts, and the inspector shot.

## Gotchas

- Only local artifacts. There is no pip-from-internet path.
- Native wheels may be uninstallable on the guest ABI — the warning is the proof, not a successful import.
- Packaging (AT-95) fails closed if the manifest is incomplete. That failure is success for this sub-feature.
