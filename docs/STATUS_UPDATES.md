# Incremental Status Updates (Email-Ready)

This document defines the standard format for small, forwardable progress updates.

## Purpose

Provide stakeholders with concise implementation updates that can be pasted directly into email without requiring full backlog/changelog context.

## Cadence

- Create one update packet per meaningful implementation batch (typically 1-3 related slices).
- Keep each packet focused and short.

## Packet requirements

Each packet must include all of the following sections:

1. **What shipped**
   - Completed work delivered in this batch.
2. **What changed**
   - Notable behavior, UX, docs, or test changes.
3. **What’s next**
   - The immediate next batch only (avoid long roadmap detail).
4. **Known risks/blockers**
   - Open issues, deferred items, or dependencies.
5. **Evidence links**
   - Concrete proof from tests, screenshots, logs, or report artifacts.

## Authoring rules

- Use the shared template in `docs/templates/STATUS_UPDATE_TEMPLATE.md`.
- Target one screen-length summary where possible.
- Prefer bullet points over paragraphs.
- Reference issue numbers where available.
- Do not duplicate long changelog entries; link to them instead.

## Storage convention

- Save packets in `docs/status_updates/`.
- Filename format: `YYYY-MM-DD-batch-XX.md`
  - Example: `2026-03-15-batch-01.md`

## Review checklist

Before sending an update packet:

- [ ] All five required sections are present.
- [ ] Statements match shipped code/docs.
- [ ] Evidence links resolve to real artifacts.
- [ ] Deferred/out-of-scope items are explicitly called out.
