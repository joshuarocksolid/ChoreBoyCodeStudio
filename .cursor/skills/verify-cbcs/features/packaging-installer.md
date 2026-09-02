# Packaging and installer

The user exports an installable project artifact from **Package Project**, and the product itself is installed with the QWizard installer. Portable profile is retired.

Owns AT-78, AT-81, AT-82, AT-84, AT-95, AT-104, AT-105.

<!-- dune-owners: platform.packaging -->

## Sub-features

- `pkg-preflight` explains blockers after finish when export fails (AT-78). They are not on wizard open.
- `pkg-wizard` **Run → Package Project...** / `#shell.toolbar.btn.package` writes installer + payload + manifests (AT-81).
- `pkg-theme` wizard readable in all four themes (AT-84).
- `pkg-deps` export checks dependency manifest completeness (AT-95).
- `pkg-skip-missing` `#shell.packageWizard.skipMissingDependencyBlockers` (**Allow export with missing imports**) is AT-104. Native extensions and subprocess rules still block. The checkbox is not on page 0.
- `pkg-ask-folder` `#shell.packageWizard.askInstallLocation` (**Ask the installer for an install folder**) is off by default. Off means AT-105 silent install into `~/.local/share/FreeCAD/Macro/Apps`. On asks for a folder. The checkbox is not on page 0.
- `shop-install` AT-82 is the shop **project** installer (launcher publish / upgrade), not the Code Studio product zip.
- `product-install` `control-cbcs launch --install --zip <product zip>` auto-walks the Code Studio installer (`PACKAGE_KIND_PRODUCT`, `ask_install_location=True`) via `cbapp install-test`. That is not AT-82.

## How to get to it (user POV)

- **Run → Package Project...** or toolbar Package.
- On the appliance: extract the product zip, run `install_*.desktop`, finish the wizard, use the published launcher.

## Driving it with control-cbcs

Preconditions:

- For in-app export: project open, doctor passed, destination on the disposable tree.
- For product install: a `choreboy_code_studio_installer_v*.zip` (password `rsd`) built by `python3 package.py`.

- **In-app wizard.** `control-cbcs arm "$SID" shell.action.build.package` (modal `exec_()`). `#shell.packageWizardDialog` opens on **page 0 (destination)**. Page-0 primary chrome is **Package**, not Next. `#shell.packageWizard.askInstallLocation` and `#shell.packageWizard.skipMissingDependencyBlockers` exist but `vis=False` until you advance past page 0. After advance both checkboxes are visible and unchecked by default. Leave ask-folder unchecked unless you are proving a folder picker. Choose a destination under the run tree. Finish. Destination contains `installer/`, payload, `package_manifest.json`, `package_report.json`. Shot `package-done`. For AT-104 / AT-105 handles, shot after advancing — not the destination page.
- **Preflight block.** Remove the project entry or break a required path; open the wizard and finish. Blockers surface after finish as `QMessageBox.critical` plus Runtime Center **Packaging Failed** — not on wizard open. No silent export.
- **Product install.** `control-cbcs launch --install --zip <zip>` runs `cbapp install-test`, which auto-walks the product installer wizard (`01_welcome` … `05_done`). Explicit `#__qt__passive_wizardbutton1` / `#qt_wizard_commit` clicks are not reachable in that lane; the session exits when install-test finishes. For a manual wizard drive, launch the installer outside `install-test`. After a successful install-test lane, the installed app is what you doctor: `#shell.startupStatusLabel` contains `Runtime ready`. Shot `product-installed`.
- **Proof.** Listing of the export dir in artifacts, or the install-lane launch shot + doctor output.

## Gotchas

- Do not `invoke` QWizard `next`. Click the visible buttons when driving the wizard by hand.
- Installer widgets have no `shell.*` names.
- AT-104 / AT-105 checkboxes are not on the destination (page 0) view.
- Portable packaging is retired (AT-83). Do not look for that profile.
- Relocatable install is not a product feature.
- `install-test` is a second session. Stop the source session first so you do not double-drive the desktop.
