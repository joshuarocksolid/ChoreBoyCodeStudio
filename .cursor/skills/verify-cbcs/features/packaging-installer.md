# Packaging and installer

The user exports an installable project artifact from **Package Project**, and the product itself is installed with the QWizard installer. Portable profile is retired.

Owns AT-78, AT-81, AT-82, AT-84, AT-95.

## Sub-features

- `pkg-preflight` explains blockers before export (AT-78).
- `pkg-wizard` **Run → Package Project...** / `#shell.toolbar.btn.package` writes installer + payload + manifests (AT-81).
- `pkg-theme` wizard readable in all four themes (AT-84).
- `pkg-deps` export checks dependency manifest completeness (AT-95).
- `pkg-skip-missing` `#shell.packageWizard.skipMissingDependencyBlockers` keeps missing imports as warnings so a working app can still export. Native extensions and subprocess rules still block.
- `product-install` `control-cbcs launch --install --zip <product zip>` walks the Code Studio installer (AT-82).

## How to get to it (user POV)

- **Run → Package Project...** or toolbar Package.
- On the appliance: extract the product zip, run `install_*.desktop`, finish the wizard, use the published launcher.

## Driving it with control-cbcs

Preconditions:

- For in-app export: project open, doctor passed, destination on the disposable tree.
- For product install: a `choreboy_code_studio_installer_v*.zip` (password `rsd`) built by `python3 package.py`.

- **In-app wizard.** `control-cbcs ctl "$SID" click '#shell.toolbar.btn.package'`. `#shell.packageWizardDialog` opens. Choose a destination under the run tree. Finish. Destination contains `installer/`, payload, `package_manifest.json`, `package_report.json`. Shot `package-done`.
- **Preflight block.** Remove the project entry or break a required path; open the wizard. An actionable blocker appears; no silent export.
- **Product install.** `control-cbcs launch --install --zip <zip>`. Click `#__qt__passive_wizardbutton1` until Install, then `#qt_wizard_commit`. Installed app launches. `#shell.startupStatusLabel` contains `Runtime ready`. Shot `product-installed`.
- **Proof.** Listing of the export dir in artifacts, or the install-lane launch shot + doctor output.

## Gotchas

- Do not `invoke` QWizard `next`. Click the visible buttons.
- Installer widgets have no `shell.*` names.
- Portable packaging is retired (AT-83). Do not look for that profile.
- Relocatable install is not a product feature.
- `install-test` is a second session. Stop the source session first so you do not double-drive the desktop.
