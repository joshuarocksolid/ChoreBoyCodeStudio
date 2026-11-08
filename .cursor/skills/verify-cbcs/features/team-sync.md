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
- A cbfarm `shop` lease. net1 and net2 each have a FaxMail account, and the terminal moves `out/<id>` to `sent` and drops the zip in the other shop's `zip_in`.
- Open a project on net1 that is not shared yet.

- **Not shared.** `control-cbcs ctl "$SID" click '#shell.activityBar.btn.team'`. `#shell.teamSync.teamView` shows **Not shared** and `#shell.teamSync.shareButton`.
- **Share.** Click `#shell.teamSync.shareButton`. `#shell.teamSync.shareDialog` is titled `Share <project>`. Fill `#shell.teamSync.shareEmail` and `#shell.teamSync.shareShop`. Click `#shell.dialogChrome.button.primary` (**Send Invite**). The thread replaces Not shared without a restart. `cbcs/team.json` exists. An `out/<id>/message.mail` subject starts with `CBCS-SYNC/1`.
- **Invite on net2.** With no team project open, a toast `#shell.teamSync.toast` names the project and `#shell.teamSync.inviteDialog` opens. `#shell.teamSync.inviteLocation` defaults to `~/Projects/<project name>`. `#shell.teamSync.inviteBrowse` refuses a folder that already has files. **Open Project** is `#shell.dialogChrome.button.primary`.
- **Send.** `#shell.teamSync.toolbar.send` shows the paper-plane icon and a count badge when files are pending. The composer `#shell.teamSync.composerSend` is one 28 px control. Its arrow menu `#shell.teamSync.composerMenu` lists Send, Save Only, and Set Aside. A long press opens that menu too.
- **Review and combine.** `#shell.teamSync.feedReview` (also `#shell.teamSync.infoBarReview` and the toast action) opens `#shell.teamSync.reviewTab`. **Accept** is `#shell.teamSync.reviewAccept`. A clash opens `#shell.teamSync.combineTab`. While it is open, Send, Save Only, Set Aside, Bring Back, and Accept stay disabled. Finish is `#shell.teamSync.combineFinish`, disabled until every clash is settled. A deleted clash opens `#shell.teamSync.deletedClashDialog`. The title is the file name. The chip names who deleted it and who edited it. **Keep your version** and **Delete it** are the footer buttons.
- **Status.** `#shell.teamSync.statusSegment` sits before the Python, Completion, and Spaces segments so it stays visible at 1400 px. Click it for `#shell.teamSync.statusPopover`.
- **History.** `#shell.teamSync.historyTab` lists notes. The file list fills after the row is selected.
- **Proof.** `cbcs/team.json` in both projects, `.Mails/<account>/sent/<id>/message.mail` with a `CBCS-SYNC/1` subject, and matching `git log` on both stations.

## Gotchas

- Never move or delete anything under `.Mails` except our own `out/<id>/` while it holds `.lock`.
- Use `object_store.add_thin_pack` for bundle imports; dulwich's `Bundle.store_objects` loses commits on offset deltas.
