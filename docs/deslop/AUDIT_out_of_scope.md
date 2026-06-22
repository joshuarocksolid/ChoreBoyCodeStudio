# Deslop Audit — Out Of Scope (tests, scripts, plugins, templates, examples, launchers)

**Status:** complete v1 (2026-06-22)  
**Related:** [AUDIT_app.md](AUDIT_app.md) (historical `app/` audit — do **not** merge findings here), [TEST_TOOLING_AUDIT.md](TEST_TOOLING_AUDIT.md) (R6 shell brittleness closeout), [AUDIT_app_remaining_handoff.md](AUDIT_app_remaining_handoff.md) §R7

**Audience:** agents filing small PRs against non-`app/` trees without polluting the app slop narrative.

---

## 1. Purpose

The original app deslop pass ([AUDIT_app.md](AUDIT_app.md)) intentionally excluded everything outside `app/`. This catalog records **concrete findings** in those excluded areas using the same slop signatures (§2) and three release categories (§3). Each work brief in §6 is sized for a single agent PR.

---

## 2. Slop signatures (same taxonomy as app audit)

1. **Structural duplication** — parallel scripts or launch paths doing the same bootstrap.
2. **Silent fallback chains** — swallowed exceptions without logging in entrypoints.
3. **Complexity inflation** — fat launchers that duplicate `app/` logic.
4. **Test–implementation coupling** — private widget/layout assertions (see [TEST_TOOLING_AUDIT.md](TEST_TOOLING_AUDIT.md)).
5. **Architectural drift** — hidden metadata paths, stale template shapes, plugin manifest mismatch.
6. **Documentation lying** — comments claiming thin bootstrap when file owns real protocol logic.
7. **Cosmetic noise** — empty placeholder files, dev-only dot paths in scripts.

---

## 3. Finding categories

| Label | When to use |
| --- | --- |
| **Must fix before release** | Security, data loss, broken install, ChoreBoy platform violation, CI blocker. |
| **Refactor when touched** | Style, duplication, test brittleness, clarity — no standalone urgency. |
| **Do not touch unless product scope changes** | Stable contracts with high churn cost (packaging, plugin host IPC, dev launcher). |

---

## 4. Metric sweep (2026-06-22, repo at HEAD)

| Area | Files / LOC | Notable grep hits |
| --- | --- | --- |
| `tests/` | 359 `.py`, ~48,216 LOC | 723 private `._` hits in `tests/unit/shell/` (48 files); 166 in `tests/integration/shell/` |
| `scripts/` | 10 files, ~400 LOC shell+py | 3× `except Exception` in `generate_stdlib_api_index.py` |
| `bundled_plugins/` | 8 plugins, 8× `plugin.json`, ~417 LOC Python | 0 hidden-path tokens; 0 bare `except Exception` in runtime |
| `templates/` (repo root) | 3 templates, 3× `template.json`, 13 files | All JSON include `template_id`, `display_name`, `template_version` |
| `example_projects/` | 1 showcase, 18 files | **1 tracked hidden path:** `example_projects/crud_showcase/.cbcs/.gitkeep` |
| Root launchers | `run_editor.py` (173 LOC), `run_runner.py` (30), `run_plugin_host.py` (302) | `run_runner.py` thin; `run_plugin_host.py` owns full stdin/stdout RPC loop |
| Packaging / dev harness | `package.py`, `dev_launch_editor.py`, `run_tests.py`, `launcher.py`, `testing/` | `package.py` delegates to `app.packaging.product_builder`; `launcher.py` no-op shim |
| Stray root artifact | `test.py` | 0 bytes (empty) |

Commands used:

```bash
find tests bundled_plugins templates example_projects scripts -type f ...
rg '\._[a-zA-Z]' tests/unit/shell tests/integration/shell
rg '\.cbcs|/\.' templates example_projects bundled_plugins scripts
rg 'except Exception' run_*.py package.py dev_launch_editor.py scripts/
```

---

## 5. Findings overview by area

### 5.1 Tests (`tests/`)

**Verdict:** Largest out-of-scope slop surface; dominated by shell UI brittleness (signature #4). Full metrics and rewrite briefs live in [TEST_TOOLING_AUDIT.md](TEST_TOOLING_AUDIT.md) §3–§7 — **not duplicated here**.

**Summary counts:**

- `tests/unit/`: 282 files, ~43,197 LOC
- `tests/integration/`: 32 files, ~3,500 LOC
- `tests/support/`: 5 files, ~565 LOC (`shell_host_stubs.py` is the good pattern)
- `testing/`: 559 LOC (shard runner, preflight, MainWindow helpers) — **stable CI contract**

**Category assignment:**

| Finding | Category |
| --- | --- |
| 723+166 private widget hits in shell tests | Refactor when touched (R6-T1…T5 briefs) |
| `MainWindow.__new__` in `test_main_window_background_teardown.py:92` | Refactor when touched |
| Icon `cacheKey()` assertion in `test_outline_panel.py:471` | Refactor when touched |
| `testing/run_test_shard.py` + `preflight_test_env.py` | Do not touch unless product scope changes |
| Risk-first unit/integration tests (runner, manifest, persistence) | Do not touch unless behavior changes |

### 5.2 Scripts (`scripts/`)

| Path | Finding | Category |
| --- | --- | --- |
| [`scripts/setup_venv_editor.sh`](../../scripts/setup_venv_editor.sh) | Creates `$ARTIFACTS_DIR/.venv-editor` (dot-prefixed **dev-only** path; not shipped) | Refactor when touched |
| [`scripts/generate_stdlib_api_index.py`](../../scripts/generate_stdlib_api_index.py) | 3× broad `except Exception` when introspecting stdlib modules (lines ~34, ~50+) | Refactor when touched |
| [`scripts/generate_icon_pngs.py`](../../scripts/generate_icon_pngs.py), [`overlay_cp39_tree_sitter_binding.py`](../../scripts/overlay_cp39_tree_sitter_binding.py) | One-off build helpers; no runtime coupling | Do not touch unless product scope changes |
| [`scripts/setup_vendor_py39.sh`](../../scripts/setup_vendor_py39.sh), [`setup_vendor_py311.sh`](../../scripts/setup_vendor_py311.sh), [`migrate_vendor_to_py311.sh`](../../scripts/migrate_vendor_to_py311.sh) | Documented dual-vendor workflow ([AGENTS.md](../../AGENTS.md)) | Do not touch unless vendor contract changes |
| [`scripts/resolve_pyright_extrapaths.sh`](../../scripts/resolve_pyright_extrapaths.sh) | Pyright helper only | Do not touch unless pyright layout changes |

### 5.3 Bundled plugins (`bundled_plugins/`)

Eight first-party plugins, each with `plugin.json` + thin `runtime.py` adapter delegating into `app/`:

| Plugin id | Runtime role |
| --- | --- |
| `cbcs.dependency_audit` | Dependency audit workflow |
| `cbcs.freecad_helpers` | FreeCAD helper commands |
| `cbcs.packaging_tools` | Packaging wizard hooks |
| `cbcs.pytest` | In-app Test Explorer pytest job provider |
| `cbcs.python_diagnostics` | Diagnostics provider |
| `cbcs.python_tools` | Black/isort query handlers ([`runtime.py`](../../bundled_plugins/cbcs.python_tools/runtime.py)) |
| `cbcs.runtime_explainers` | Runtime onboarding copy |
| `cbcs.templates.standard` | Template catalog provider |

**Findings:**

| Finding | Category |
| --- | --- |
| No forbidden hidden storage paths in plugin sources | ✅ clean |
| Manifest `api_version`, `permissions`, `contributes` blocks present | Do not touch unless plugin API version bumps |
| Local `__pycache__` under working tree (not git-tracked) | Refactor when touched (hygiene only) |
| Runtime files are thin serializers — good pattern | Do not touch unless product scope changes |

### 5.4 Templates (`templates/`)

| Template | `template.json` | Notes |
| --- | --- | --- |
| [`templates/qt_app/`](../../templates/qt_app/) | `default_entry: main.py` | GUI starter; matches project model |
| [`templates/headless_tool/`](../../templates/headless_tool/) | `default_entry: main.py` | Headless FreeCAD-safe layout |
| [`templates/utility_script/`](../../templates/utility_script/) | `default_entry: main.py` | Minimal script starter |

**Findings:**

| Finding | Category |
| --- | --- |
| JSON schema consistent (`template_id`, `display_name`, `description`, `template_version`) | Do not touch unless template product changes |
| README + `main.py` per template | Refactor when touched (copy/clarity only) |
| No dot-prefixed metadata dirs in templates | ✅ clean |

### 5.5 Example projects (`example_projects/`)

| Path | Finding | Category |
| --- | --- | --- |
| [`example_projects/crud_showcase/.cbcs/.gitkeep`](../../example_projects/crud_showcase/.cbcs/.gitkeep) | **Violates** [.cursor/rules/no_hidden_folders.mdc](../../.cursor/rules/no_hidden_folders.mdc) and [docs/DISCOVERY.md](../DISCOVERY.md) §4A — hidden metadata dir checked into git | **Must fix before release** |
| [`example_projects/crud_showcase/template.json`](../../example_projects/crud_showcase/template.json) | Valid example metadata (`crud_showcase`) | Do not touch unless example scope changes |
| [`example_projects/crud_showcase/tasks.sqlite3`](../../example_projects/crud_showcase/tasks.sqlite3) | Demo database artifact for CRUD walkthrough | Do not touch unless example scope changes |
| `__pycache__` under showcase (local only) | Hygiene | Refactor when touched |

### 5.6 Root launchers

| File | LOC | Role | Category |
| --- | ---: | --- | --- |
| [`run_runner.py`](../../run_runner.py) | 30 | argparse → `app.runner.runner_main.run_from_manifest_path` | Do not touch unless runner CLI changes |
| [`run_editor.py`](../../run_editor.py) | 173 | Logging, capability probe, tree-sitter init, Qt loop | Do not touch unless startup contract changes |
| [`run_plugin_host.py`](../../run_plugin_host.py) | 302 | Full plugin-host stdin/stdout RPC loop (not a thin bootstrap) | Do not touch unless plugin IPC changes |

**Refactor when touched (launchers):**

| Location | Finding |
| --- | --- |
| `run_editor.py:117–118` | Swallows `Exception` in previous `excepthook` chain |
| `run_editor.py:126–127` | Broad `except Exception` around `faulthandler.enable()` (logged — lower risk) |
| `run_plugin_host.py:51,110,149,238` | Broad `except Exception` returning RPC errors — intentional for host isolation; narrow only with protocol tests |

### 5.7 Packaging and test harness (outside `app/`)

| File | Finding | Category |
| --- | --- | --- |
| [`package.py`](../../package.py) | Version prompt + `build_product_artifact()` wrapper | Do not touch unless release pipeline changes |
| [`dev_launch_editor.py`](../../dev_launch_editor.py) | Dev AppRun launcher, vendor profile symlinks | Do not touch unless local dev contract changes |
| [`run_tests.py`](../../run_tests.py) | AppRun pytest injection (`importlib`, xdist, performance demotion) | Do not touch unless test runner contract changes |
| [`launcher.py`](../../launcher.py) | Explicit no-op compatibility shim (19 LOC) | Refactor when touched — delete when no packaging reference remains |
| [`test.py`](../../test.py) | Empty file at repo root | **Must fix before release** (delete or document; confuses discovery) |
| [`testing/run_test_shard.py`](../../testing/run_test_shard.py) | Fast/integration/performance shard orchestration | Do not touch unless CI budget changes |

---

## 6. Per-agent work briefs

Effort: **S** < 1 day, **M** 1–3 days, **L** 3–7 days (excluding review).

Cross-cutting rules: [.cursor/rules/no_hidden_folders.mdc](../../.cursor/rules/no_hidden_folders.mdc), [testing_when_to_write.mdc](../../.cursor/rules/testing_when_to_write.mdc), [AGENTS.md](../../AGENTS.md) test commands.

---

### OS-M1 — Example project visible metadata path (S) — **Must fix before release**

**Goal.** Remove tracked hidden `.cbcs/` from the CRUD showcase example; use visible `cbcs/` per platform rules.

**Files.**

- `example_projects/crud_showcase/.cbcs/.gitkeep` → migrate to `example_projects/crud_showcase/cbcs/.gitkeep` (or drop if unnecessary)
- Any docs referencing the example path

**Acceptance.**

- `rg '\.cbcs' example_projects/` shows no dot-prefixed directory names in tracked files
- Example still opens in Help / template flows if applicable

**Suggested PR title.** `deslop: move crud_showcase metadata to visible cbcs/ path`

---

### OS-M2 — Delete empty root `test.py` (S) — **Must fix before release**

**Goal.** Remove 0-byte [`test.py`](../../test.py) at repo root to avoid pytest/import confusion.

**Acceptance.** File deleted; no references in docs or packaging; fast shard green.

---

### OS-T1 — Shell test brittleness wave 1 (M) — **Refactor when touched**

**Goal.** Execute [TEST_TOOLING_AUDIT.md](TEST_TOOLING_AUDIT.md) brief **R6-T1** (search sidebar + settings dialog).

**Files.** `tests/unit/shell/test_search_sidebar_widget.py`, `tests/unit/shell/test_settings_dialog.py`

**Acceptance.** ≥80% reduction of private `._` probes in those files; behavior coverage preserved.

---

### OS-T2 — Shell host stub consolidation (M) — **Refactor when touched**

**Goal.** Execute **R6-T2**: format actions, reference rename, project tree refresh tests → `tests/support/shell_host_stubs.py`.

**Files.** `test_main_window_format_actions.py`, `test_main_window_reference_rename_actions.py`, `test_project_tree_refresh_state.py`, `test_main_window_background_teardown.py`

**Acceptance.** No new `MainWindow.__new__` harness blocks.

---

### OS-T3 — Integration shell de-privatization (L) — **Refactor when touched**

**Goal.** Execute **R6-T3** on top integration tests (quick-open, shutdown, session persistence).

**Acceptance.** Integration shard green; child-process reaper clean.

---

### OS-S1 — Stdlib index generator exception narrowing (S) — **Refactor when touched**

**Goal.** In [`scripts/generate_stdlib_api_index.py`](../../scripts/generate_stdlib_api_index.py), replace broad `except Exception` with `(AttributeError, ImportError, TypeError)` or log-and-continue for introspection misses.

**Acceptance.** Regenerated `app/intelligence/stdlib_api_index.json` unchanged or intentionally updated with diff explained.

---

### OS-S2 — Dev venv path comment (S) — **Refactor when touched**

**Goal.** Document in [`scripts/setup_venv_editor.sh`](../../scripts/setup_venv_editor.sh) header that `.venv-editor` is **editor-tooling-only** and never deployed to ChoreBoy.

**Acceptance.** Comment only unless product chooses a visible artifacts name.

---

### OS-P1 — Bundled plugin manifest validation (S) — **Do not touch unless product scope changes**

**Goal.** When adding/changing a bundled plugin, run existing manifest tests + confirm `permissions`/`api_version` match [docs/ARCHITECTURE.md](../ARCHITECTURE.md) plugin host contract.

**Files.** `bundled_plugins/*/plugin.json`, `tests/unit/plugins/` (if present)

**Acceptance.** No hidden paths; runtime stays thin adapter.

---

### OS-L1 — Launcher documentation accuracy (S) — **Refactor when touched**

**Goal.** Add module docstring note to [`run_plugin_host.py`](../../run_plugin_host.py): this file **is** the plugin host process, not a bootstrap shim (corrects signature #6 drift vs original handoff assumption).

**Acceptance.** Doc-only unless IPC exception narrowing is justified with integration tests.

---

### OS-PK1 — Retire `launcher.py` shim (S) — **Refactor when touched**

**Goal.** Grep for `launcher.py` imports/references; remove shim if nothing packages it.

**Files.** [`launcher.py`](../../launcher.py), packaging docs

**Acceptance.** No broken entrypoint references; pyright clean.

---

## 7. What this document is not

- Not a second `app/` slop catalog — never merge duplicate fixed/open status from [AUDIT_app.md](AUDIT_app.md).
- Not a mandate to delete tests by LOC — follow risk-first gate in [testing_when_to_write.mdc](../../.cursor/rules/testing_when_to_write.mdc).
- Not adding Ruff/Vulture/Radon — see [TEST_TOOLING_AUDIT.md](TEST_TOOLING_AUDIT.md) §6.

---

## 8. R7 acceptance (this pass)

| Criterion | Status |
| --- | --- |
| Audit document under `docs/deslop/` | ✅ this file |
| Findings cite concrete paths | ✅ §4–§5, §6 briefs |
| Three categories applied | ✅ §3, §5–§6 |
| Small agent briefs | ✅ OS-M1…OS-PK1 |
| Shell test detail in R6 doc, not duplicated | ✅ cross-link only |

**Validation reference:**

```bash
python3 testing/run_test_shard.py fast
npx pyright
```

End of out-of-scope deslop audit.
