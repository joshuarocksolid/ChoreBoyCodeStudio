# Packaging and installer

The user exports an installable project artifact from **Package Project**, and the product itself is installed with the QWizard installer. Portable profile is retired.

Owns AT-78, AT-81, AT-82, AT-84, AT-95, AT-104, AT-105.

<!-- dune-owners: platform.packaging -->

## Sub-features

- `pkg-preflight` explains blockers before export (AT-78).
- `pkg-wizard` **Run → Package Project...** / `#shell.toolbar.btn.package` writes installer + payload + manifests (AT-81).
- `pkg-theme` wizard readable in all four themes (AT-84).
- `pkg-deps` export checks dependency manifest completeness (AT-95).
- `pkg-skip-missing` `#shell.packageWizard.skipMissingDependencyBlockers` (**Allow export with missing imports**) is AT-104. Native extensions and subprocess rules still block.
- `pkg-ask-folder` `#shell.packageWizard.askInstallLocation` (**Ask the installer for an install folder**) is off by default. Off means AT-105 silent install into `~/.local/share/FreeCAD/Macro/Apps`. On asks for a folder.
- `shop-install` AT-82 is the shop **project** installer (launcher publish / upgrade), not the Code Studio product zip.
- `product-install` `control-cbcs launch --install --zip <product zip>` walks the Code Studio installer (`PACKAGE_KIND_PRODUCT`, `ask_install_location=True`). That is not AT-82.

## How to get to it (user POV)

- **Run → Package Project...** or toolbar Package.
- On the appliance: extract the product zip, run `install_*.desktop`, finish the wizard, use the published launcher.

## Driving it with control-cbcs

Preconditions:

- For in-app export: project open, doctor passed, destination on the disposable tree.
- For product install: a `choreboy_code_studio_installer_v*.zip` (password `rsd`) built by `python3 package.py`.

- **In-app wizard.** `control-cbcs arm "$SID" shell.action.build.package` (modal `exec_()`). `#shell.packageWizardDialog` opens. Confirm `#shell.packageWizard.askInstallLocation` and `#shell.packageWizard.skipMissingDependencyBlockers`. Leave ask-folder unchecked unless you are proving a folder picker. Choose a destination under the run tree. Finish. Destination contains `installer/`, payload, `package_manifest.json`, `package_report.json`. Shot `package-done`. A first-page shot of the two checkboxes is enough if you only need the AT-104 / AT-105 handles.
- **Preflight block.** Remove the project entry or break a required path; open the wizard. An actionable blocker appears; no silent export.
- **Product install.** `control-cbcs launch --install --zip <zip>`. Click `#__qt__passive_wizardbutton1` until Install, then `#qt_wizard_commit`. Installed app launches. `#shell.startupStatusLabel` contains `Runtime ready`. Shot `product-installed`.
- **Proof.** Listing of the export dir in artifacts, or the install-lane launch shot + doctor output.

## Gotchas

- Do not `invoke` QWizard `next`. Click the visible buttons.
- Installer widgets have no `shell.*` names.
- Portable packaging is retired (AT-83). Do not look for that profile.
- Relocatable install is not a product feature.
- `install-test` is a second session. Stop the source session first so you do not double-drive the desktop.
