# Sync feat/form-builder with main v0.4.13

Merge of `origin/main` (`7e3b8ad`, Release v0.4.13) into `origin/feat/form-builder` (`faac8ad`). Both sides stay. Main commits below are the ones that touched the file after the merge base. Seam behaviour is the M2.0 tab-content provider seam in `docs/form_builder/CONTRACTS.md` §11 and `docs/form_builder/M2.0_AUDIT.md`.

- `app/editors/editor_tab.py` keeps `buffer_id` and `DiskConflict` from `0c79f86` and keeps `content_source` as the `current_content` / `is_dirty` delegate. `mark_saved(saved_text=...)` clears `disk_conflict`.
- `app/editors/editor_manager.py` keeps the buffer-id maps from `0c79f86` and `bc7c4ae`. `close_file` and preview close call `drop_content_source_subscription` before `_remove_tab`. `save_tab` passes `saved_text`.
- `app/features/spec.py` keeps `FeatureSpec.enabled` and lazy `_install_markdown`. `_install_editor_groups` from `5583428` imports inside the function so `feature-install-imports` still holds.
- `dune.yaml` keeps the `form-builder` owner and adds the `editor-groups` owner from `5583428`.
- `app/shell/draft_autosave_workflow.py` keys pending payloads by buffer id (`051d533`) and keeps path-keyed source revisions. `flush_pending_autosaves` still filters sourced paths with `selected_paths`. `migrate_draft_for_move` stays. `forget_source` does not unsubscribe.
- `app/shell/editor_sync_workflow.py` restores a surface when one is bound. A text tab calls `mark_saved(saved_text=text)` and refreshes whenever the tab widget exists (`5583428` dropped the single-bar index check).
- `app/shell/editor_tab_buffer_workflow.py` keeps disk-conflict status from `f6694f1` and imports `EditorTabState` for the seam. Group-aware status from `5583428` and `4d26468` stays.
- `app/shell/editor_tab_factory.py` asks the provider registry first, wraps every tab in `EditorTabPage` (`1739a5e`), registers editors by buffer id (`0c79f86`), and uses `completion_mode` (`8e28af7`, `3e48ec7`). It calls `present_tab_at` and then `refresh_tab_presentation`. A declined provider still opens text with its notice.
- `app/shell/editor_tab_host_protocols.py` keeps main's host methods (`5583428`, `779787a`, `8e28af7`) and types markdown panes as `dict[str, Any]` so the shell does not import `app.features.markdown`.
- `app/shell/editor_tab_lifecycle_workflow.py` keeps group close, split, and context menu from `5583428` and `779787a`. `release_tab_content` pops by buffer id and releases the surface. Close blockers run only when the buffer itself is closing, after `close_view_if_shared`. Reset walks `open_paths`.
- `app/shell/editor_tab_markdown_workflow.py` keeps second-group preview behaviour from `779787a` by duck-typing panes. It does not import the markdown feature. `clear_registry` calls `forget_all`.
- `app/shell/editor_tab_workflow_mixins.py` does not restore `wrap_tab_content_if_markdown`. Group, disk-bar, and completion mixin methods from `1739a5e`, `051d533`, `779787a`, and `3e48ec7` stay, and they delegate to the lifecycle workflow.
- `app/shell/main_window_composition_phases.py` wires the tree coordinator through `open_paths`, `widget_for_path`, `release_tab_content`, `rekey_tab_content`, and `remove_tabs_for_last_path` (`5583428`, `051d533`, `1739a5e`). It does not pass the raw widget dict.
- `app/shell/main_window_lifecycle.py` asks about a running program first (`8510f17`, `e4caf5d`), then `confirm_tab_close_blockers` for every open path, then the unsaved-changes decision.
- `app/shell/problems_controller.py` calls `surface.set_diagnostics` and returns. Otherwise it uses `widget_for_path`, because the widget map is buffer-id keyed (`5583428`, `051d533`).
- `app/shell/project_tree_action_coordinator.py` takes `open_tab_paths` as a callable and `widget_for_path` (`051d533`). Delete passes the callable through so lazy tabs are included.
- `app/shell/project_tree_controller.py` closes via `open_tab_paths()` and always calls `release_tab_content`. Move keeps buffer identity (`051d533`), calls `migrate_buffer_state`, and calls `rekey_tab_content` even when no widget exists.
- `tests/unit/shell/test_draft_autosave_workflow.py` keeps main's buffer-id flush and `migrate_draft_for_move` tests (`051d533`) and the seam's sourced-revision tests.
- `tests/unit/shell/test_external_file_change_workflow.py` keeps main's disk-changed, missing-file, and stale-save tests (`1739a5e`, `d9514d8`, `fdd0fe7`, `051d533`) and the seam's lazy-surface tests.
- `tests/unit/shell/test_project_tree_action_coordinator.py` constructs the coordinator with `open_tab_paths` and `widget_for_path` (`051d533`).
- `tests/unit/shell/test_project_tree_controller.py` keeps main's buffer-identity move tests (`051d533`). Close passes `manager.open_paths` and releases lazy tabs.

Files that merged clean and then needed a seam route:

- `app/features/editor_groups/controller.py` builds the second markdown pane inside the feature (`779787a`). `_register_remaining_markdown_pane` binds that pane back into the registry. `split_right` returns false when the page has no source editor.
- `app/features/editor_groups/install.py` imports `ShellCompositionContext` under `TYPE_CHECKING` and imports `bind_private_attrs` inside the function.
- `app/shell/editor_tabs_coordinator.py` themes a second-group surface through `source_editor` and `apply_theme`. It does not import `MarkdownEditorPane`.
- `app/shell/external_file_change_workflow.py` keeps the disk-changed dialog for text buffers (`fdd0fe7`, `1739a5e`). A dirty sourced tab with no source editor still uses the three-way unsaved-changes prompt.
- `tests/unit/shell/test_lazy_tab_surface_lifecycle.py` calls the post-merge close and move signatures and still expects `release_tab_content` and `rekey_tab_content` for a tab with no widget.
- `tests/unit/shell/test_tab_open_focus.py` and `tests/unit/shell/test_tab_provider_open_failure.py` stub `EditorTabsCoordinator` and the info-bar host. The notice assertion reads the page content, not the info-bar labels. Opening a markdown surface still does not call `focus_primary`.

## Round 2

The O-logic gate's closed list. Each item has a regression test that failed on this branch before the fix.

- Tree delete after a project switch reads `open_paths` from the live editor manager. `tests/integration/shell/test_project_switch_tree_delete_integration.py`.
- Replacing a preview passes the closed preview's path into `remove_tab_widget_for_buffer_id`, and `release_tab_content` pops that buffer id when the manager has already dropped the tab. `tests/unit/shell/test_preview_lazy_surface_rebind.py`.
- Cancelling a sourced dirty reload marks `disk_conflict` changed and returns declined, so the next save prompts. `test_sourced_dirty_cancel_marks_the_conflict_and_the_next_save_prompts`.
- `close_group` asks close blockers once before the unsaved-changes prompt, then closes with `skip_close_blockers`. `test_close_group_asks_blockers_before_unsaved_changes` and `test_close_group_asks_blockers_once_for_buffers_only_in_that_group`.
- The second group's markdown pane is built by `build_secondary_pane` and adopted by `adopt_secondary_pane`. The existing second-group preview tests still cover that.
- A declined provider's text tab is a `_DeclinedTextTab` with `source_editor()` and without markdown pane methods, so split works. `tests/integration/shell/test_declined_provider_split_integration.py`.
