# TN-EDIT-COMP — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-COMP  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/editors/completion_popup/` (8 modules, ~1,390 LOC total), cross-read `app/shell/python_console_widget.py` (781 LOC), `app/shell/editor_completion_workflow.py` (313 LOC), `app/intelligence/completion_merge_policy.py` (126 LOC), `app/editors/code_editor_semantics.py` completion trigger/paint paths (376 LOC). Gates: §17.4.2 tier presentation, AD-018 generation gating at paint boundary, four-theme `ShellThemeTokens`, gate 8 presentation-only imports in popup layer, hard-cutover reuse of canonical merge policy.

---

## Executive verdict

**REJECT — the `completion_popup/` package is a credible MVC extraction (controller / model / delegate / container under 1k each), and Intelligence Wave 1’s CC-02 merge-policy work now injects tier header rows at the shell boundary.** That is material progress over the prior flat ranked list. The popup **presentation boundary still fails §17.4.2**: tier headers render as ordinary selectable rows (kind chip, origin badge, highlight states), `reuse_items_for_prefix` destroys tier structure while the user types, and the Python Console forks a second, thinner completion host with its own prefix helper and no tier guards. TN-INT-SHELL-EDITORS-7 (prefix reuse fork) remains **open**; TN-INT-SHELL-EDITORS-9 / CC-02 are **partially closed** (data carries tiers, UI does not yet separate them). Dominant risk: users still perceive one homogeneous completion list during live prefix refinement, undermining the trust contract that approximate, runtime, and semantic tiers are visually distinct.

---

## Prior-wave re-validation

| ID | Intelligence Wave 1 claim | Status at baseline | Notes |
|----|---------------------------|-------------------|-------|
| **TN-INT-SHELL-EDITORS-7** | Popup `reuse_items_for_prefix` diverges from broker prefix semantics | **OPEN** | `completion_controller.py:117-130` still filters with `item.label.lower().startswith(prefix.lower())`; editor calls it from `code_editor_semantics.py:145-146`. |
| **TN-INT-SHELL-EDITORS-9** | Editor paints merged tiers with no tier awareness | **PARTIAL** | `completion_merge_policy.flatten_tiered_items` injects header rows; controller/list skip headers on accept/first-select. Delegate/docs panel treat headers like candidates. |
| **CC-02** | §17.4.2 flat merge mislabels tiers | **PARTIAL** | `merge_completion_display` + `envelope_confidence` fixed (`test_completion_merge_policy.py`); `editor_completion_workflow.py:113-116,208-212` routes through `merge_completion_for_display`. Popup still presents headers as homogeneous rows; reuse path drops headers entirely. |

---

### TN-EDIT-COMP-1 — `reuse_items_for_prefix` strips tier headers and collapses §17.4.2 structure

- **Persona:** TN-EDIT-COMP
- **Severity:** BLOCKER
- **Evidence:** `app/editors/completion_popup/completion_controller.py:117-130` — `reuse_items_for_prefix` filters with `item.label.lower().startswith(prefix.lower())`, then `set_items(items, prefix)`. Tier header rows (`"Indexed suggestions"`, etc. from `completion_merge_policy.py:94-95`) do not share the typed identifier prefix and are dropped. Section structure is not preserved; subsequent paints show a flat candidate list mid-keystroke.
- **Code-judo alternative:** Store the last delivered `CompletionEnvelope.tiers` (or row metadata with `{row_kind: header|item, tier_phase}`) on the controller; prefix lengthening re-slices tiers via `flatten_tiered_items` or a broker-side `filter_envelope_for_prefix` — no label heuristic in UI.
- **Suggested remediation:** Disable label-based reuse until tier-preserving filter exists, or pass tier tuple through `show_completion_items_for_request` and filter per tier item labels only. Never call `set_items` with a header-stripped flat list.
- **Tests that would prove fix:** Parametrize reuse with merged fast+semantic envelope: after typing one more char, row list still contains two tier headers in order; dotted-member prefix retains runtime tier rows.
- **Handoff overlap:** CC-02, TN-INT-SHELL-EDITORS-7, AD-016

---

### TN-EDIT-COMP-2 — Delegate paints tier headers as selectable completion rows (§17.4.2 presentation gap)

- **Persona:** TN-EDIT-COMP
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/completion_popup/completion_item_delegate.py:86-160` — no `is_tier_header_item` branch; tier header `CompletionItem` rows (`completion_merge_policy.py:117-126`, `kind=TEXT`, `source="tier_header"`) receive kind chip, hover/selected backgrounds, and `_origin_text` badge `"tier_header"` (`completion_item_delegate.py:268-276`). `completion_list_view.py:111-125` skips headers only for initial selection, not arrow navigation.
- **Code-judo alternative:** Early-return header paint path: muted full-width label, no chip/badge, reduced row height, `State_Enabled` off; or separate `QHeaderView` sections per `CompletionTierPhase`. Single `is_tier_header_item` check in delegate + list navigation skip.
- **Suggested remediation:** Import `is_tier_header_item` in delegate; paint headers as non-interactive section labels; list view `keyPressEvent` or selection model skips header indices on Up/Down.
- **Tests that would prove fix:** Manual four-theme acceptance: tier labels visually distinct from candidates; no `"tier_header"` origin badge. Unit test: header row `sizeHint` / paint path does not emit origin badge text.
- **Handoff overlap:** CC-02, §17.4.2

---

### TN-EDIT-COMP-3 — Tier header selection pollutes docs panel

- **Persona:** TN-EDIT-COMP
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/completion_popup/completion_popup_container.py:76` — `current_item_changed` feeds all rows to `CompletionDocsPanel.set_item`. `app/editors/completion_popup/completion_docs_panel.py:232-240` — `_has_visible_metadata` returns true when `item.source` is set; tier headers have `source="tier_header"` and `confidence="unsupported"`, so the panel renders signature/provenance for a non-candidate row when arrow-navigated onto a header.
- **Code-judo alternative:** `set_item` returns early on `is_tier_header_item(item)`; or container filters before connecting docs panel.
- **Suggested remediation:** Guard docs panel and `selection_changed` emitters against tier headers; keep last real item visible when selection lands on header.
- **Tests that would prove fix:** Select tier header row programmatically → docs panel stays empty or shows previous item; provenance never displays `"tier_header"`.
- **Handoff overlap:** CC-02

---

### TN-EDIT-COMP-4 — Three prefix semantics in one refresh cycle (TN-INT-SHELL-EDITORS-7 still open)

- **Persona:** TN-EDIT-COMP
- **Severity:** STRUCTURAL
- **Evidence:** (1) Broker/editor prefix from `build_completion_context` — dotted member, import, identifier (`completion_context.py:144-233`, wired in `code_editor_semantics.py:126-137`). (2) Reuse filter `label.startswith(prefix)` (`completion_controller.py:123-127`). (3) Highlight subsequence fuzzy match in `compute_match_ranges` (`completion_item_model.py:26-60`) — can bold characters that reuse filter would drop. Console adds a fourth: `_completion_prefix` identifier-only tail (`python_console_widget.py:769-774`).
- **Code-judo alternative:** Popup stores broker-issued prefix string at `set_items` time; reuse and match ranges both derive from that single contract. Console calls shared `build_completion_context` or a shell `CompletionHost` helper.
- **Suggested remediation:** Delete label-based reuse; pass `prefix` only from workflow deliver envelope; align `compute_match_ranges` with broker filter policy or move matching to intelligence layer.
- **Tests that would prove fix:** Dotted-member typing: reuse retains member candidates whose labels do not start with typed prefix; TN-INT-SHELL-EDITORS-7 closed.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-7, CC-05, TN-EDIT-SEM-9

---

### TN-EDIT-COMP-5 — Python Console forks parallel completion host without popup parity

- **Persona:** TN-EDIT-COMP
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/completion_popup/__init__.py:1` — package documented as shared by editor and console. `python_console_widget.py:358-387` — local `_show_completion_items`, `_insert_completion_from_item`, `_completion_prefix`; no `reuse_items_for_prefix` while typing (`code_editor_semantics.py:145-146`); no `is_tier_header_item` guard on insert (`code_editor_semantics.py:350-351` vs console `:369-387`). Console `show_completion_items_for_request` omits explicit `prefix` param — recomputes locally each paint (`:129-142`).
- **Code-judo alternative:** Extract `CompletionHostMixin` (popup wiring, generation gate, prefix from broker deliver, accept/delete span) consumed by semantics mixin and console; single `_show_completion_items(items, prefix)` shape.
- **Suggested remediation:** Hard cutover console to broker-delivered prefix in `show_completion_items_for_request`; share reuse/tier-skip behavior; delete `_completion_prefix` or delegate to `build_completion_context` on prompt slice only.
- **Tests that would prove fix:** Console integration test: tier headers present after merge deliver; accept on header rejected; prefix on deliver matches editor path for same input line.
- **Handoff overlap:** CC-02, hard-cutover bias

---

### TN-EDIT-COMP-6 — Duplicate keyboard navigation orchestration in `CompletionController`

- **Persona:** TN-EDIT-COMP
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/completion_popup/completion_controller.py:199-219` — `handle_navigation_event` handles Escape/accept/nav keys. `:232-265` — `eventFilter` duplicates the same key sets and accept/hide logic before forwarding typed keys to host. Any future nav change requires two edits; drift risk is active debt.
- **Code-judo alternative:** Single `_dispatch_popup_key(key_event) -> bool` used by both entry points; eventFilter only forwards when dispatch returns false.
- **Suggested remediation:** Collapse duplicated branches; add unit test that both paths call the same helper for Escape/Enter/Up.
- **Tests that would prove fix:** Parametrized test invoking `handle_navigation_event` and `eventFilter` with same `QKeyEvent` → identical hide/accept side effects.
- **Handoff overlap:** none

---

### TN-EDIT-COMP-7 — CC-02 closed at merge policy, not at popup boundary

- **Persona:** TN-EDIT-COMP
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_merge_policy.py:23-98` — tier tuple, headers, dedupe, `envelope_confidence` never exact with approximate items. `app/shell/editor_completion_workflow.py:113-116` — shell uses session merge before paint. Popup model (`completion_item_model.py:96-102`) treats all rows uniformly; delegate has no tier awareness. Manifest gate 4 (`_findings/_README.md:87`): tiers must not present as one homogeneous list — data is tiered, presentation is not.
- **Code-judo alternative:** Model accepts `CompletionEnvelope` or tier metadata roles; delegate + list enforce section UX. Intelligence merge stays canonical; popup is a tier-aware view, not a flat `list[CompletionItem]` passthrough.
- **Suggested remediation:** Extend `CompletionItemModel.set_items` to accept envelope/tier boundaries; pair with TN-EDIT-COMP-2 header paint path. Update manual acceptance doc for four-theme tier visibility.
- **Tests that would prove fix:** Extend `test_completion_merge_policy.py` or add `test_completion_popup_tiers.py`: merged envelope → model row roles include `is_header`; delegate skips chip for header rows.
- **Handoff overlap:** CC-02, AD-016

---

### TN-EDIT-COMP-8 — Test gap: popup tier presentation untested despite manifest flag

- **Persona:** TN-EDIT-COMP
- **Severity:** NICE-TO-HAVE
- **Evidence:** `docs/code review/editors-wave-1/00-manifest.md:139` — lists `completion_popup/` tier headers as **High** gap. Existing tests cover merge policy (`tests/unit/intelligence/test_completion_merge_policy.py`) and model match ranges (`tests/unit/editors/completion_popup/test_completion_item_model.py`) but not header row roles, reuse preservation, delegate/header paint, or docs-panel guard.
- **Code-judo alternative:** One parametrized popup contract test file exercising model+controller with synthetic tiered envelope; defers widget paint to manual acceptance only if AppRun delegate tests are too heavy.
- **Suggested remediation:** Add tests alongside COMP-1/COMP-2 fixes; do not add snapshot-of-styles tests — assert selectable flag and row count invariants only.
- **Tests that would prove fix:** `test_completion_popup_tiers.py` passes after remediation; manifest row marked Medium/Low.
- **Handoff overlap:** CC-02, R6

---

### TN-EDIT-COMP-9 — Four-theme: hardcoded fallback palette before `apply_theme`

- **Persona:** TN-EDIT-COMP
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/completion_popup/completion_item_delegate.py:58-64` — constructor caches `#212529`, `#D0E2FF`, `#E9ECEF` light-theme literals before any `apply_theme` call. `completion_popup_container.py:85-86,72` — shadow `QColor(0,0,0,80)` and chrome fallbacks `#FFFFFF` / `#DEE2E6`. `completion_list_view.py:65-66` — same pattern. First popup show before theme propagation may flash wrong colors in HC Dark/Light.
- **Code-judo alternative:** Require `apply_theme` before first `complete()` (assert in controller) or initialize from `tokens_from_palette` default snapshot at construct time via shell wiring.
- **Suggested remediation:** Shell guarantees `apply_theme` on editor/console before first completion; remove literal defaults or source from neutral token snapshot.
- **Tests that would prove fix:** Manual four-theme: open completion in HC Light (`#FFFFFF` popup bg) and HC Dark (`#000000`); no light-blue selection flash on first paint.
- **Handoff overlap:** none

---

### TN-EDIT-COMP-10 — Docs panel risk pill bypasses semantic warning/error tokens in HC modes

- **Persona:** TN-EDIT-COMP
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/completion_popup/completion_docs_panel.py:215-219` — pill background uses `tokens.diag_warning_color` / `tokens.diag_error_color` with hex fallbacks; text always `#FFFFFF` for both `tokens.is_dark` branches (`:219`). HC themes may need thicker border or `tokens.text_on_accent` if added — current branch is a no-op ternary.
- **Code-judo alternative:** Use dedicated `tokens.badge_text` or `tokens.text_on_warning` from `ShellThemeTokens`; drop dead `is_dark` ternary.
- **Suggested remediation:** Align pill with tree/badge token pattern used elsewhere in shell; verify contrast ≥ 7:1 on HC Light popup surface.
- **Tests that would prove fix:** Manual four-theme: risk pill readable on HC Light white popup background.
- **Handoff overlap:** none

---

### TN-EDIT-COMP-11 — Positive structural note: MVC decomposition is thermo-directional

- **Persona:** TN-EDIT-COMP
- **Severity:** NICE-TO-HAVE
- **Evidence:** Eight focused modules (`completion_controller.py` 308 LOC, `completion_item_delegate.py` 280, largest file well under 1k); typed `CompletionItem` roles; theme via `ShellThemeTokens` throughout; `is_tier_header_item` centralized in intelligence merge policy and honored on accept (`completion_controller.py:225-226`). Contrasts favorably with pre-extraction `QCompleter` flat string list.
- **Code-judo alternative:** Keep package boundaries; invest next in tier-aware view model rather than moving logic back into `CodeEditorWidget` or console widget.
- **Suggested remediation:** Treat `completion_popup/` as the stable paint boundary; push remaining prefix/tier policy out of controller into shell/intelligence deliver contract.
- **Tests that would prove fix:** LOC budget test: no file in `completion_popup/` exceeds 400 LOC after tier view-model land.
- **Handoff overlap:** §12.4, CC-02

---

## Cross-cutting gate checklist

| Gate | Status in TN-EDIT-COMP slice |
|------|------------------------------|
| AD-016 session boundary | Popup is paint-only; accept routes through controller filter. Reuse/filter policy incorrectly re-implements broker semantics (COMP-1, COMP-4). |
| AD-018 revision gate | Generation gating lives in semantics/console callers, not popup — **OK**. Popup has no buffer revision (correct layer). |
| §17.4.2 tier separation | Merge injects headers — **partial**. Presentation + reuse fail explicit tier UI — **REJECT**. |
| Gate 8 intelligence imports | Popup imports `CompletionItem`, `is_tier_header_item`, `CompletionKind` — presentation/policy helper only; **OK**. |
| 1k-line rule | All scoped files under 1k; package total ~1,390 across 8 modules — **OK**. |
| Four-theme | Token-driven with literal fallbacks and first-paint risk (COMP-9, COMP-10). |
| Hard-cutover | Shared `CompletionController` for editor+console is good; console orchestration duplication violates cutover (COMP-5). |

**Approval bar:** **REJECT.** CC-02 and TN-INT-SHELL-EDITORS-9 are not closable until tier headers survive reuse and render as non-homogeneous section UI in all four themes. TN-INT-SHELL-EDITORS-7 remains open at the controller reuse site. The MVC split is worth keeping — fix tier view model and delete label-based reuse rather than reverting to `QCompleter`.
