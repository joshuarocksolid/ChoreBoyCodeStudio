# Caption Map (Complete Edition)

Maps each screenshot id to the caption used in the manual and any callout notes. This
supports deterministic re-capture (see `capture/README.md`) and the maintenance rule:
when the UI changes, re-capture the shot and keep the caption accurate.

Captions are the image `alt` text in the referencing chapter. The full shot inventory
(file, chapter, purpose, capture state) lives in `shot_list.json`.

| Shot id | Caption | Notes |
| --- | --- | --- |
| 020_getting_started | The in-app Getting Started onboarding dialog | Help > Getting Started |
| 030_demo_app | The example task-manager app running | crud_showcase launched |
| 040_window_tour | The main window with a project loaded | Used in the overview |
| 040_window_tour_annotated | Annotated tour of the main window | Numbered callouts per region |
| 050_new_project_dialog | The New Project dialog | |
| 060_tree_context_menu | The project tree right-click menu | File management actions |
| 070_editor_code | A Python file open in the editor, with syntax highlighting and the Outline panel populated | crud_showcase/main.py |
| 080_find_in_files | Find in Files results | |
| 080_quick_open | Quick Open (Ctrl+P) | |
| 090_run_configurations | The Run Configurations dialog | |
| 090_run_running | A run in progress with Run Log output | |
| 090_run_stopped | A finished run | |
| 090_run_with_args | The Run With Arguments dialog | |
| 100_markdown_split | Markdown split view (source + preview) | |
| 110_breakpoint | A breakpoint set in the gutter | |
| 150_problems_panel | The Problems panel with diagnostics | |
| 160_test_explorer | The Test Explorer with discovered pytest tests, before running | Seeded demo suite |
| 160_test_results | After running, the Test Explorer shows pass/fail counts and per-test status, with full pytest output in the Run Log | |
| 170_global_history | The Global History dialog | |
| 170_recovery_center | The Recovery Center dialog | |
| 180_add_dependency | The Add Dependency wizard | |
| 180_dependency_inspector | The Dependency Inspector | |
| 190_plugin_manager | The Plugin Manager | |
| 200_package_wizard | The Package Project wizard | |
| 230_settings_general | The General settings tab | Appearance/Output/Editor/Intelligence groups |
| 230_settings_keybindings | The Keybindings settings tab, with a searchable command/shortcut table | |
| 230_settings_syntax_colors | The Syntax Colors settings tab, showing the per-theme token color table | |
| 230_settings_linter | The Linter settings tab, with provider selection and the per-rule override table | |
| 230_settings_files | The Files settings tab, with the File Exclusions and Local History groups | |
| 240_theme_dark | The Dark theme | |
| 240_theme_menu | The View > Theme submenu | |
| 250_keyboard_shortcuts | The in-app Keyboard Shortcuts reference | |
| 260_menu_file | The File menu | |
| 260_menu_edit | The Edit menu | |
| 260_menu_run | The Run menu | |
| 260_menu_view | The View menu | |
| 260_menu_tools | The Tools menu | |
| 260_menu_help | The Help menu | |
| 340_runtime_center | The Runtime Center | |
