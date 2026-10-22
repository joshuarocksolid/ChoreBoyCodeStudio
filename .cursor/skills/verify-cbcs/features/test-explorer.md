# Test Explorer

The Test Explorer activity discovers pytest nodes, runs all or a selection, reruns failures, and can debug a failed node. Outcomes stay in memory (`TestRunnerWorkflow._test_outcomes_by_node_id`) for the session.

Owns AT-96–101, AT-62, smoke M4.

<!-- dune-owners: platform.pytest -->

## Sub-features

- `tx-discover` populates `#shell.testExplorer.tree` after project-open collect.
- `tx-run-all` runs the suite from `#shell.testExplorer.runAllBtn`.
- `tx-run-node` runs a selected node from the tree context menu.
- `tx-rerun-failed` `#shell.testExplorer.runFailedBtn` only hits failures.
- `tx-debug-failed` `#shell.testExplorer.debugFailedBtn` / AT-62.
- `tx-filters` Passed / Failed / Skipped / Errors chips.
- `tx-persist` is not on disk. AT-100 / copy-project-metadata has nothing to copy.
- `tx-theme` panel stays readable in Light and Dark (AT-101); four themes preferred.

## How to get to it (user POV)

- Activity bar Test Explorer, or **View → Show Test Explorer** (Ctrl+Shift+X).
- **Run → Run Project Tests / Run Current File Tests / Run Test at Cursor / Debug Current Test / Debug Failed Test**.

## Driving it with control-cbcs

Preconditions:

- Project contains a pytest file that has at least one passing and one failing node (seed under the run tree).
- Doctor passed. Guest can spawn the in-app runner.

- **Open.** Prefer `control-cbcs ctl "$SID" click '#shell.activityBar.btn.test_explorer'`. `#shell.testExplorer` is visible. Do not treat `trigger shell.action.view.showTestExplorer` as equivalent: that action always calls `refresh_discovery()` and can raise a modal **Open a project first.** when no project is loaded.
- **Discover.** Opening a project already starts background `pytest --collect-only`. Open the pane, then poll — do not click Refresh unless collect already finished empty. `control-cbcs wait "$SID" shell.testExplorer.tree --min-rows 1 --timeout 45` when you expect nodes. Status becomes `N tests`, `Discovery error`, or a settled empty state (`No tests found in this project` / `#shell.testExplorer.emptyLabel`). `example_projects/crud_showcase` may have zero tests — an empty settled collect is fixture emptiness, not a failed wait. Shot `tx-discovered`.
- **Run all.** `control-cbcs ctl "$SID" click '#shell.testExplorer.runAllBtn'`. Counts on `#shell.testExplorer.countPassed` / `countFailed` update. Failures also appear in Problems.
- **Rerun failed.** After a failure, `#shell.testExplorer.runFailedBtn`. Only failed nodes re-run.
- **Navigate.** Activate a failed node. The editor opens at the `def` line. Assertion-line jump is Problems, not this tree.
- **Proof.** Shot of the tree with pass/fail icons and the count chips (`✓ N` / `✗ N`), or of the settled empty state when the fixture has no tests.

## Gotchas

- Discovery is a background `pytest --collect-only` (up to 30s). `#shell.testExplorer.statusText` stays `No tests discovered` until it finishes — `set_discovering` is unused. Poll tree rows or a `N tests` / `Discovery error` status, not a fixed sleep.
- Clicking Refresh restarts collect. If one is already running from project open, wait for it.
- AppRun `-c` runs one physical line. Do not `raise SystemExit(...)` / `sys.exit(pytest.main(...))` in that payload — AppRun swallows it and collect looks empty. Call `pytest.main(...)` and stop.
- Empty tree on a project with no tests is a valid empty state (`#shell.testExplorer.emptyLabel` / **No tests found in this project**), not a failure. Do not fail a `--min-rows 1` wait when status has already settled empty (e.g. `crud_showcase`).
- There is no persisted results file to copy before `stop`.
- `shell.action.view.showTestExplorer` refreshes discovery; prefer the activity-bar click unless you intentionally want that refresh.
