# Smoke Test Report — Process and Evidence

## Purpose

This document defines how to record smoke-test evidence for release candidates and large shell/runner changes. It aligns with [`SMOKE_WORKFLOW.md`](SMOKE_WORKFLOW.md) and supports incremental status reporting referenced from [`USER_REQUESTS_TODO.md`](USER_REQUESTS_TODO.md).

## When to write a report

Run a smoke report when:

- preparing a release candidate after significant UI/runner changes,
- validating post–v0.2 shell work before tagging, or
- completing Layer 1 + Layer 2 of [`SMOKE_WORKFLOW.md`](SMOKE_WORKFLOW.md).

## How to record results

1. Run automated shards per [`TESTS.md` §5](TESTS.md#5-core-commands) (start with `fast`, then `runtime_parity`, optionally `integration` and `performance`).
2. Run manual steps M1–M6 on a real DISPLAY (four-theme check required for M5).
3. Copy the template from [`../smoke_test_results.md`](../smoke_test_results.md) into that file (or a dated copy `smoke_test_results_YYYY-MM-DD.md` at repo root).
4. Note PASS / FAIL / WARN per step with optional screenshots.

## Storage convention

| Artifact | Location |
|----------|----------|
| Latest smoke log | [`smoke_test_results.md`](../smoke_test_results.md) at repo root |
| Dated archives | `smoke_test_results_YYYY-MM-DD.md` (optional) |
| Release history | [`CHANGELOG.md`](../CHANGELOG.md) |
| Full MVP acceptance | [`ACCEPTANCE_TESTS.md`](ACCEPTANCE_TESTS.md) |

## Related docs

- [`SMOKE_WORKFLOW.md`](SMOKE_WORKFLOW.md) — automated + manual checklist
- [`docs/TEST_AUDIT.md`](TEST_AUDIT.md) — test shard reference and known failures
- [`AGENTS.md`](../AGENTS.md) — latest validation checkpoint counts
