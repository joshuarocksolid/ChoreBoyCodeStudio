# Team sync

Projects shared between shops through each shop's FaxMail terminal, with real git
history written by vendored dulwich. Product behavior is in `docs/team_sync/SPEC.md`;
AT-106–AT-113.

<!-- dune-owners: team-sync, platform.shell -->

## Sub-features

- `team-share` shares a project and opens it from an invite (AT-106).
- `team-send` saves and sends a change and tracks Queued, ✓, ✓✓ (AT-107).
- `team-review` reviews incoming work in a Review tab before Accept (AT-108).
- `team-combine` settles clashes in a Combine tab; files untouched until Finish (AT-109).
- `team-history` history, restore, undo, who changed this line (AT-110).
- `team-power` set aside, milestones from Package Project, experiments (AT-111).
- `team-offline` terminal offline and unverified mail (AT-112); budgets (AT-113).

## How to get to it (user POV)

- Activity bar Team icon (Thread view), toolbar Send, the Team status segment, editor info bars and toasts.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- A cbfarm `shop` lease: net1 and net2 share the twin's FaxMail account.

- Share from net1, open the invite on net2, then follow AT-107–AT-112.
- **Proof.** `cbcs/team.json` in both projects, `.Mails/<account>/sent/<id>/message.mail` with a `CBCS-SYNC/1` subject, and matching `git log` on both stations.

## Gotchas

- Never move or delete anything under `.Mails` except our own `out/<id>/` while it holds `.lock`.
- Use `object_store.add_thin_pack` for bundle imports; dulwich's `Bundle.store_objects` loses commits on offset deltas.
