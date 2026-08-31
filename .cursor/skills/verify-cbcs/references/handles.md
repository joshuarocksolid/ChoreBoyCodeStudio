# Handles

Selectors for `control-cbcs ctl` / `cbapp`: `#objectName`, `text:Label`, `class:QClass[n]`.

Prefer `#shell.*`. Action ids are QAction objectNames; trigger them with `control-cbcs trigger "$SID" <id>`.

Duplicate names exist (`shell.welcome.onboardingActionBtn` on several welcome buttons). Prefer the unique name, else `text:`.

`CodeEditorWidget` itself is unnamed. The factory sets `shell.editorTabs.textEditor` on every tab — use `class:` + index or in-app Python if you need a specific buffer.

The installer wizard (`packaging/install.py`) has no `shell.*` names. Use `#__qt__passive_wizardbutton1` and `#qt_wizard_commit`.

Recovery Center has no object names. Arm `shell.action.file.recoveryCenter` and click `text:Open Timeline` / `text:Restore Latest to Buffer`.

Explorer header buttons share `#shell.explorerAction`. They are icon-only. Select by tooltip **New File** / **New Folder** / **Refresh Explorer**.

Paste overlay: `#PasteHintOverlay`, `#PasteHintOverlayReindentButton`, `#PasteHintOverlayAlwaysButton`, `#PasteHintOverlayDismissButton` (**×**). Only after `insertFromMimeData`.

`#shell.quickOpen.input` is the Quick Open field (`show()`, not `exec_()`).

Dependency Inspector title is **Project Dependencies**. No `#shell.dependency*` handle.

## Chrome

| Handle | What |
|--------|------|
| `#shell.mainWindow` | Main window |
| `#shell.activityBar` | Left activity bar |
| `#shell.activityBar.btn.explorer` | Explorer view |
| `#shell.activityBar.btn.search` | Search view |
| `#shell.activityBar.btn.test_explorer` | Test Explorer view |
| `#shell.leftRegion` | Sidebar host |
| `#shell.sidebarStack` | 0 Explorer, 1 Search, 2 Test Explorer |
| `#shell.projectTree` | Project tree |
| `#shell.explorerSplitter` | Tree + outline |
| `#shell.centerStack` | 0 welcome, 1 editor |
| `#shell.welcome` | Welcome pane |
| `#shell.editorTabs` | Editor tabs |
| `#shell.editorTabs.textEditor` | Text editor (shared name) |
| `#shell.bottomRegion.tabs` | Console / Debug / Problems / Run Log |
| `#shell.statusBar` | Status bar |

## Welcome

| Handle | What |
|--------|------|
| `#shell.welcome.newProjectBtn` | New Project |
| `#shell.welcome.openProjectBtn` | Open Project |
| `#shell.welcome.searchInput` | Filter recents |
| `#shell.welcome.projectList` | Recent projects |
| `#shell.welcome.onboardingCard` | First-run card |
| `#shell.welcome.onboardingPrimaryBtn` | Complete onboarding |
| `#shell.welcome.onboardingSecondaryBtn` | Dismiss onboarding |

Onboarding action buttons share `#shell.welcome.onboardingActionBtn`. Use `text:Runtime Center`, `text:Getting Started`, `text:Project Health`, `text:Load Example Project`, `text:Headless Notes`.

## Toolbar

`#shell.toolbar.runDebug` hosts:

`#shell.toolbar.btn.run` · `debug` · `runProject` · `debugProject` · `stop` · `restart` · `continue` · `pause` · `stepOver` · `stepInto` · `stepOut` · `removeAllBp` · `package`

## Status bar

| Handle | What |
|--------|------|
| `#shell.startupStatusLabel` | `Startup: Runtime ready (N/N checks)`. Click runs `exec_()` and blocks the Qt bridge. Use `arm` `shell.action.tools.runtimeCenter` instead. Widget class is `_ClickableLabel`; use `control-cbcs read`, not bridge `find('#…')`. |
| `#shell.diagnosticsStatusLabel` | Error / warning counts |
| `#shell.pythonToolingStatusLabel` | Black / isort readiness |
| `#shell.runStatusLabel` | `Run: idle` / `Run: running` / `Run: success (code=0)` / `Run: failed (code=N)` / `Run: terminated` |
| `#shell.projectStatusLabel` | Project name + `(project overrides)` |
| `#shell.indentStatusLabel` | Spaces / Tabs |
| `#shell.editorStatusLabel` | file, line, col, modified/saved |
| `#shell.statusBar.activeRunConfig` | Default or named config |

## Find, search, markdown

| Handle | What |
|--------|------|
| `#shell.findBar` | In-file find |
| `#shell.findBar.findInput` | Find field |
| `#shell.findBar.replaceInput` | Replace field |
| `#shell.findBar.nextBtn` / `prevBtn` / `replaceBtn` / `replaceAllBtn` | Nav |
| `#shell.searchSidebar` | Find in Files |
| `#shell.searchSidebar.searchInput` | Query |
| `#shell.searchSidebar.results` | Result tree |
| `#shell.markdownEditorPane` | Markdown host |
| `#shell.markdownEditorPane.modeButton.*` | Source / Preview / Split |
| `#shell.markdownPreview.browser` | Preview |

## Debug, problems, console, tests

| Handle | What |
|--------|------|
| `#shell.debug.panel` | Debug pane |
| `#shell.debug.watchInput` | Watch expression |
| `#shell.debug.commandInput` | Debug command |
| `#shell.debug.variablesTree` | Locals / scopes |
| `#shell.debug.breakpointsTree` | Breakpoint list |
| `#shell.debug.stackTree` | Call stack |
| `#shell.debug.statusLabel` | `Paused at <file>:<line> in <func>` |
| `#shell.problemsPanel` | Problems |
| `#shell.bottom.pythonConsole` | REPL. Show the tab first (`#shell.bottomRegion.tabs` index 0). `text:Python Console` can miss. |
| `#shell.bottom.runLog` | Run Log host |
| `#shell.bottom.runLog.textArea` | Token / stdout text |
| `#shell.testExplorer` | Test Explorer |
| `#shell.testExplorer.runAllBtn` | Run All |
| `#shell.testExplorer.refreshBtn` | Refresh (restarts collect) |
| `#shell.testExplorer.tree` | Discovery tree |
| `#shell.testExplorer.statusText` | `N tests` / `Discovery error` / empty |
| `#shell.testExplorer.emptyLabel` | Empty or error copy |
| `#shell.testExplorer.countPassed` | `✓ N` |
| `#shell.testExplorer.countFailed` | `✗ N` |
| `#shell.testExplorer.runFailedBtn` | Rerun failures |

## Dialogs

| Handle | What |
|--------|------|
| `#shell.settingsDialog` | Settings. Modal. Use `arm` `shell.action.file.settings`. |
| `#shell.runtimeCenterDialog` | Runtime Center |
| `#shell.runtimeOnboardingDialog` | Onboarding |
| `#shell.packageWizardDialog` | Package Project. Modal. Use `arm` `shell.action.build.package`. |
| `#shell.packageWizard.skipMissingDependencyBlockers` | **Allow export with missing imports** (AT-104) |
| `#shell.packageWizard.askInstallLocation` | **Ask the installer for an install folder** (AT-105 when unchecked) |
| `#shell.pluginManagerDialog` | Plugin Manager |
| `#shell.runWithArgumentsDialog` | Run With Arguments |
| `#shell.runConfigurationsDialog` | Run Configurations |
| `#shell.quickSymbolDialog` | Go to Symbol |
| `#shell.helpDialog` | Built-in help |

## Menus

`#shell.menuBar` · `#shell.menu.file` · `#shell.menu.edit` · `#shell.menu.run` · `#shell.menu.view` · `#shell.menu.view.theme` · `#shell.menu.tools` · `#shell.menu.help` · `#shell.menu.file.openRecent`

## File actions

`shell.action.file.newProject` · `newWindow` · `newProjectFromTemplate` · `openProject` · `openFile` · `quickOpen` · `recoveryCenter` · `globalHistory` · `save` · `saveAs` · `saveAll` · `autoSave` · `settings` · `exit`

## Edit actions

`shell.action.edit.undo` · `redo` · `find` · `replace` · `goToLine` · `findInFiles` · `findReferences` · `renameSymbol` · `toggleComment` · `indent` · `outdent` · `pasteReindentedFlatPython` · `goToDefinition` · `signatureHelp` · `hoverInfo`

## Run actions

`shell.action.run.run` · `debug` · `runProject` · `debugProject` · `runWithArgs` · `runWithConfig` · `pytestProject` · `pytestCurrentFile` · `pytestAtCursor` · `debugPytestCurrentFile` · `debugPytestFailed` · `stop` · `restart` · `rerunLastDebugTarget` · `continue` · `pause` · `stepOver` · `stepInto` · `stepOut` · `toggleBreakpoint` · `removeAllBreakpoints` · `debugExceptionStops` · `pythonConsole` · `clearConsole` · `shell.action.build.package`

## View / Tools / Help actions

View: `resetLayout` · `showTestExplorer` · `theme.system|light|dark|high_contrast_light|high_contrast_dark` · `markdownTogglePreview` · `markdownShowSource` · `markdownShowPreview` · `markdownShowSplit` · `zoomIn` · `zoomOut` · `zoomReset`

Tools: `pluginManager` · `dependencyInspector` · `addDependency` · `formatCurrentFile` · `organizeImportsCurrentFile` · `lintCurrentFile` · `applySafeFixes` · `reindentFlatPythonSelection` · `rebuildIntelligenceCache` · `refreshRuntimeModules` · `analyzeImports` · `gotoSymbolInFile` · `setLanguageMode` · `clearLanguageOverride` · `inspectToken` · `runtimeCenter` · `projectHealthCheck` · `generateSupportBundle` · `headlessNotes`

Help: `loadExampleProject` · `openAppLog` · `openLogFolder` · `runtimeOnboarding` · `gettingStarted` · `shortcuts` · `about`

Prefix View/Tools/Help ids with `shell.action.view.`, `shell.action.tools.`, `shell.action.help.` as listed in the menu builders.
