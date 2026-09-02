# Handles

Selectors for `control-cbcs ctl` / `cbapp`: `#objectName`, `text:Label`, `class:QClass[n]`.

Prefer `#shell.*`. Action ids are QAction objectNames; trigger them with `control-cbcs trigger "$SID" <id>`.

Duplicate names exist (`shell.welcome.onboardingActionBtn` on several welcome buttons). Prefer the unique name, else `text:`.

`CodeEditorWidget` itself is unnamed. The factory sets `shell.editorTabs.textEditor` on every tab — use `class:` + index or in-app Python if you need a specific buffer.

The installer wizard (`packaging/install.py`) has no `shell.*` names. When driving it by hand, use `#__qt__passive_wizardbutton1` and `#qt_wizard_commit`. `control-cbcs launch --install` uses `cbapp install-test`, which auto-walks those pages — those handles are not reachable in that lane. When install-test finishes the SID is exited; do not doctor that SID. Proof is the `01_welcome`…`05_done` shots; Runtime-ready needs a later launch of the installed app.

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
| `#shell.packageWizardDialog` | Package Project. Modal. Use `arm` `shell.action.build.package`. Step 1 of 2 = **Choose Package Destination** (primary **Next**, Cancel); Step 2 of 2 = **Review Package Metadata** (primary **Package**). AT-104/105 checkboxes are `vis=False` on Step 1 and visible/unchecked on Step 2. |
| `#shell.packageWizard.skipMissingDependencyBlockers` | **Allow export with missing imports** (AT-104). Not on page 0 / Step 1. |
| `#shell.packageWizard.askInstallLocation` | **Ask the installer for an install folder** (AT-105 when unchecked). Not on page 0 / Step 1. |
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

## Additional required handles

The Dune checker requires each handle below to match a `setObjectName` call under `app/`:

- `#shell.action.file.autoSave`
- `#shell.bottom.pythonConsole.clearBtn`
- `#shell.bottom.pythonConsoleContainer`
- `#shell.bottom.runLog.clearBtn`
- `#shell.bottom.runLog.metaLabel`
- `#shell.bottom.runLog.openBtn`
- `#shell.bottom.runLog.statusDot`
- `#shell.bottom.runLog.toolbar`
- `#shell.centerPanel`
- `#shell.centralWidget`
- `#shell.debug.commandInputRow`
- `#shell.debug.leftSplitter`
- `#shell.debug.mainSplitter`
- `#shell.debug.output`
- `#shell.debug.rightSplitter`
- `#shell.debug.sectionBtn`
- `#shell.debug.sectionCount`
- `#shell.debug.sectionHeader`
- `#shell.debug.sectionTitle`
- `#shell.debug.statusDot`
- `#shell.debug.statusHeader`
- `#shell.debug.threadsTree`
- `#shell.debug.watchInputRow`
- `#shell.debug.watchTree`
- `#shell.dialogChrome.body`
- `#shell.dialogChrome.footer`
- `#shell.dialogChrome.header`
- `#shell.dialogChrome.icon`
- `#shell.dialogChrome.meta.chip`
- `#shell.dialogChrome.metaRow`
- `#shell.dialogChrome.subtitle`
- `#shell.dialogChrome.title`
- `#shell.diffView`
- `#shell.diffView.afterPane`
- `#shell.diffView.beforePane`
- `#shell.diffView.inline`
- `#shell.diffView.message`
- `#shell.diffView.modeButton.inline`
- `#shell.diffView.modeButton.sideBySide`
- `#shell.diffView.modeToolbar`
- `#shell.diffView.paneLabel`
- `#shell.diffView.splitter`
- `#shell.editorPage`
- `#shell.explorerHeader`
- `#shell.explorerPage`
- `#shell.fieldAction.button`
- `#shell.findBar.caseBtn`
- `#shell.findBar.chevronBtn`
- `#shell.findBar.closeBtn`
- `#shell.findBar.findRow`
- `#shell.findBar.matchCount`
- `#shell.findBar.navGroup`
- `#shell.findBar.prevBtn`
- `#shell.findBar.regexBtn`
- `#shell.findBar.replaceAllBtn`
- `#shell.findBar.replaceBtn`
- `#shell.findBar.replaceRow`
- `#shell.findBar.topRow`
- `#shell.findBar.wordBtn`
- `#shell.helpDialog.browser`
- `#shell.helpDialog.closeBtn`
- `#shell.helpDialog.footer`
- `#shell.helpDialog.header`
- `#shell.helpDialog.icon`
- `#shell.helpDialog.title`
- `#shell.leftRegion.body`
- `#shell.leftRegion.title`
- `#shell.localHistoryDialog.compareCurrent`
- `#shell.localHistoryDialog.compareLabel`
- `#shell.localHistoryDialog.comparePrevious`
- `#shell.localHistoryDialog.revisionTree`
- `#shell.localHistoryDialog.splitter`
- `#shell.localHistoryDialog.toolbar`
- `#shell.markdownEditorPane.modeGroup`
- `#shell.markdownEditorPane.refreshButton`
- `#shell.markdownEditorPane.splitter`
- `#shell.markdownEditorPane.status`
- `#shell.markdownEditorPane.title`
- `#shell.markdownEditorPane.toolbar`
- `#shell.outlinePanel`
- `#shell.outlinePanel.body`
- `#shell.outlinePanel.chevron`
- `#shell.outlinePanel.emptyLabel`
- `#shell.outlinePanel.fileLabel`
- `#shell.outlinePanel.filter`
- `#shell.outlinePanel.filterRow`
- `#shell.outlinePanel.header`
- `#shell.outlinePanel.title`
- `#shell.outlinePanel.tree`
- `#shell.problemsPanel.emptyLabel`
- `#shell.problemsPanel.filterErrors`
- `#shell.problemsPanel.filterInfo`
- `#shell.problemsPanel.filterWarnings`
- `#shell.problemsPanel.sourceLabel`
- `#shell.problemsPanel.toolbar`
- `#shell.problemsPanel.tree`
- `#shell.quickOpen`
- `#shell.quickOpen.count`
- `#shell.quickOpen.empty`
- `#shell.quickOpen.results`
- `#shell.quickOpen.resultsContainer`
- `#shell.quickSymbolDialog.count`
- `#shell.quickSymbolDialog.empty`
- `#shell.quickSymbolDialog.input`
- `#shell.quickSymbolDialog.list`
- `#shell.runConfigurationsDialog.addButton`
- `#shell.runConfigurationsDialog.configsDetailForm`
- `#shell.runConfigurationsDialog.configsDetailPanel`
- `#shell.runConfigurationsDialog.configsDetailScroll`
- `#shell.runConfigurationsDialog.configsGroup`
- `#shell.runConfigurationsDialog.defaultArgvGroup`
- `#shell.runConfigurationsDialog.defaultEntryLabel`
- `#shell.runConfigurationsDialog.deleteButton`
- `#shell.runConfigurationsDialog.duplicateButton`
- `#shell.runConfigurationsDialog.emptyState`
- `#shell.runConfigurationsDialog.entryField`
- `#shell.runConfigurationsDialog.error`
- `#shell.runConfigurationsDialog.list`
- `#shell.runConfigurationsDialog.nameField`
- `#shell.runConfigurationsDialog.workingDirField`
- `#shell.runEnvOverridesDialog`
- `#shell.runEnvOverridesDialog.table`
- `#shell.runFormSection`
- `#shell.runFormSection.title`
- `#shell.runWithArgumentsDialog.advancedGroup`
- `#shell.runWithArgumentsDialog.commandPreview`
- `#shell.runWithArgumentsDialog.entry`
- `#shell.runWithArgumentsDialog.error`
- `#shell.runWithArgumentsDialog.footerSeparator`
- `#shell.runWithArgumentsDialog.formScroll`
- `#shell.runWithArgumentsDialog.formScrollContent`
- `#shell.runWithArgumentsDialog.overridesSummary`
- `#shell.runWithArgumentsDialog.overridesTitle`
- `#shell.runWithArgumentsDialog.overridesToggle`
- `#shell.runWithArgumentsDialog.prefill`
- `#shell.runWithArgumentsDialog.wdHelper`
- `#shell.runWithArgumentsDialog.workingDir`
- `#shell.runtimeCenterDialog.closeButton`
- `#shell.runtimeCenterDialog.detailBrowser`
- `#shell.runtimeCenterDialog.footer`
- `#shell.runtimeCenterDialog.header`
- `#shell.runtimeCenterDialog.helpButton`
- `#shell.runtimeCenterDialog.issueList`
- `#shell.runtimeCenterDialog.summary`
- `#shell.runtimeCenterDialog.title`
- `#shell.searchSidebar.caseBtn`
- `#shell.searchSidebar.clearBtn`
- `#shell.searchSidebar.excludeInput`
- `#shell.searchSidebar.filterToggle`
- `#shell.searchSidebar.filtersContainer`
- `#shell.searchSidebar.header`
- `#shell.searchSidebar.headerRow`
- `#shell.searchSidebar.includeInput`
- `#shell.searchSidebar.noResults`
- `#shell.searchSidebar.regexBtn`
- `#shell.searchSidebar.replaceAllBtn`
- `#shell.searchSidebar.replaceInput`
- `#shell.searchSidebar.replaceToggle`
- `#shell.searchSidebar.summary`
- `#shell.searchSidebar.wordBtn`
- `#shell.settingsDialog.addExcludeBtn`
- `#shell.settingsDialog.addLocalHistoryExcludeBtn`
- `#shell.settingsDialog.appearanceGroup`
- `#shell.settingsDialog.buttonBox`
- `#shell.settingsDialog.cancelBtn`
- `#shell.settingsDialog.editorGroup`
- `#shell.settingsDialog.editorResetGlobal`
- `#shell.settingsDialog.fileExcludeInput`
- `#shell.settingsDialog.fileExcludesGroup`
- `#shell.settingsDialog.fileExcludesHelp`
- `#shell.settingsDialog.fileExcludesList`
- `#shell.settingsDialog.generalScroll`
- `#shell.settingsDialog.generalScrollContent`
- `#shell.settingsDialog.intelligenceGroup`
- `#shell.settingsDialog.intelligenceResetGlobal`
- `#shell.settingsDialog.linterProviderGroup`
- `#shell.settingsDialog.linterProviderScopeHint`
- `#shell.settingsDialog.linterResetGlobal`
- `#shell.settingsDialog.linterTable`
- `#shell.settingsDialog.localHistoryExcludeInput`
- `#shell.settingsDialog.localHistoryExcludesHelp`
- `#shell.settingsDialog.localHistoryExcludesList`
- `#shell.settingsDialog.localHistoryGroup`
- `#shell.settingsDialog.localHistoryHelp`
- `#shell.settingsDialog.okBtn`
- `#shell.settingsDialog.outputGroup`
- `#shell.settingsDialog.outputResetGlobal`
- `#shell.settingsDialog.removeExcludeBtn`
- `#shell.settingsDialog.removeLocalHistoryExcludeBtn`
- `#shell.settingsDialog.resetAllShortcuts`
- `#shell.settingsDialog.resetExcludesBtn`
- `#shell.settingsDialog.resetLocalHistoryBtn`
- `#shell.settingsDialog.scopeBanner`
- `#shell.settingsDialog.scopeHeader`
- `#shell.settingsDialog.scopeSegmented`
- `#shell.settingsDialog.shortcutConflict`
- `#shell.settingsDialog.shortcutSearch`
- `#shell.settingsDialog.shortcutTable`
- `#shell.settingsDialog.syntaxColorTable`
- `#shell.settingsDialog.syntaxThemeInput`
- `#shell.settingsDialog.syntaxValidation`
- `#shell.settingsDialog.tabs`
- `#shell.settingsDialog.validationBanner`
- `#shell.testExplorer.countSkipped`
- `#shell.testExplorer.debugFailedBtn`
- `#shell.testExplorer.filterBar`
- `#shell.testExplorer.statusBar`
- `#shell.testExplorer.statusDot`
- `#shell.testExplorer.title`
- `#shell.testExplorer.toolbar`
- `#shell.toolbar.separator`
- `#shell.topSplitter`
- `#shell.unsavedChangesDialog.fileList`
- `#shell.unsavedChangesDialog.row`
- `#shell.unsavedChangesDialog.row.name`
- `#shell.unsavedChangesDialog.row.path`
- `#shell.verticalSplitter`
- `#shell.welcome.btnRow`
- `#shell.welcome.container`
- `#shell.welcome.emptyLabel`
- `#shell.welcome.onboardingActionRow`
- `#shell.welcome.onboardingChecklist`
- `#shell.welcome.onboardingReminder`
- `#shell.welcome.onboardingRuntimeSummary`
- `#shell.welcome.onboardingStateRow`
- `#shell.welcome.onboardingTitle`
- `#shell.welcome.recentLabel`
- `#shell.welcome.subtitle`
- `#shell.welcome.title`
