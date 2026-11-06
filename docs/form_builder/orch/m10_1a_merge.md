# M10.1a merge

`fb/m10.1` merged `origin/main` at `9a570d70`. The form builder stays as it was on `feat/form-builder`. Team Sync, shop sharing, and the buffer warm-up fix stay as they were on `main`.

`scripts/new_feature.py` refuses an id that already exists, so it was not run. `form-builder` was already in `FEATURE_SPECS`, `dune.yaml`, and `.cursor/skills/verify-cbcs/features/form-builder.md`. The merged registry keeps that entry and adds `shop-sharing` and `team-sync`. Install callables import their packages inside the function. A module-level import would load Qt during `import app.features`, which the isolation test forbids, and `feature-install-imports` rejects it in `spec.py`.

## Conflicts

| File | Form builder side | Main side | Combined |
| --- | --- | --- | --- |
| `app/features/__init__.py` | Re-exports `FEATURE_SPECS`, `feature_is_enabled`, and the types. | Empty file. Callers import `app.features.spec`. | Kept the re-export. `app.features.spec` is an allowed import, and outline code still imports from `app.features`. |
| `app/features/spec.py` | Lazy install wrappers, `enabled`, and `form-builder`. | Module-level imports of markdown, editor groups, shop sharing, and Team Sync. | One literal `FEATURE_SPECS` tuple. Every install wrapper imports inside the function. `form-builder` keeps `enabled`. `shop-sharing` and `team-sync` are always installed. |
| `app/shell/main_window_composition.py` | Imports `feature_is_enabled` and skips a disabled feature. | Imports `FEATURE_SPECS` from `app.features.spec` and installs every spec. | Imports both from `app.features.spec` and still skips a feature whose `enabled` predicate is false. |
| `app/shell/editor_tab_page.py` | Generated-file banner. | Notice host for feature bars (`add_notice_bar`). | Both. The generated banner stays under the disk-conflict bar. Notices sit under that. |
| `app/shell/editor_tab_factory.py` | Attaches the generated banner when a tab opens. | Runs `editor_page_hooks`. | Both, banner first, then the hooks. |
| `app/shell/settings_dialog.py` | `global_settings_payload`, `project_root`, `initial_page_key`, and feature pages. | `shop_sharing_group` and `commit()` on accept. | The constructor takes both. Accept writes feature pages first. A page refusal leaves sharing unchanged. Sharing `commit()` runs after that. A sharing refusal leaves the dialog open. |
| `app/shell/file_project_commands_workflow.py` | `_open_settings_dialog(page_key=, focus_completion_mode=)`. Connections uses `page_key="connections"`. | `focus` of `completion_mode` or `shop_sharing`, and `shop_sharing_settings_group()`. | One method. `focus` is `completion_mode` or `shop_sharing`. `page_key` remains. Project scope opens for Connections, or for completion when the project value differs. |
| `.cursor/skills/verify-cbcs/references/handles.md` | Form builder object names. | Team Sync handles and `#shell.editorTabPage.notices`. | Both sections. |
| `scripts/cloud_setup_screenshot_runtime.sh` | `ensure_vendor` for `py39` and `py311`, logged with `cloud_log`. | Skip `vendor_py39` only when `tree_sitter`, `jedi`, and `dulwich` are present. The skip used `log`, which this script does not define. | The two-profile function stays. A profile is skipped only when `dulwich` is present too, so Team Sync's dependency is installed. |

`app/features/shop_sharing/install.py` and `app/features/team_sync/install.py` did not conflict. Their module-level imports of `app.shell` and `app.qt` fail `feature-install-imports`. Those imports now sit inside the functions that use them. The widgets and the install order are unchanged.

`dune.yaml` merged clean. Owners are `form-builder`, `shop-sharing`, and `team-sync`.

## M10.1a

| Item | Shot | What was wrong | What changed |
| --- | --- | --- | --- |
| Start cards | 02, 64 | | |
| From-table combos | 05, 06 | | |
| Record bar | 05, 06 | | |
| Connect combos | 41 | | |
| Max length | 27, 63 | | |
| Why this size | 63 | | |
| Required row | 28 | | |
| Form inspector sentences | | | |
| Insert pitch | 20 | | |
| Tab-order chip | 15 | | |
| Tab-order badge | 15-dark | | |
| Run behavior | 48 | | |
| Form centre | 48 | | |
| What ran colour | | | |
