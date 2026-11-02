# Team Sync shop day (esm4)

Drove one day on cbfarm shop `esm4`. net1 was Sam, net2 was Ana, net15 was the FaxMail twin. Both stations used `rocksolid@upwardmail.com`. Disposable homes were `/home/default/cbcs-team-net1` and `/home/default/cbcs-team-net2`. Project id `p_5fc9ae42e8d4facc`. Screenshots are in `docs/team_sync/screens/shopday/`.

The twin account folder did not already contain `account_settings_v2.conf`. A real terminal always has that file, and the address and size cap live in it, so discovery still requires it. The day created a realistic conf on the twin as test setup (`EmailAddress}{rocksolid@upwardmail.com`, `UserName}{RockSolid`, `CompanyName}{Cedar Hollow`, `MaxMsgSize}{30000000`).

## Steps

| Step | Result | Evidence |
| --- | --- | --- |
| 1. Sam opens Invoice App. Team view shows Not shared. | Pass | `01_net1.png`, `01_net1_project.png` |
| 2. Share and invite. `out/<id>/` then `sent/<id>/message.mail` with subject `CBCS-SYNC/1 invite`. | Fail, then fixed | `02_net1_dialog.png`, `02_net1_error.png`, `02_net1.png` |
| 3. Ana sees a verified invite and opens the project. | Pass, with history differences below | `03_net2.png`, `03_net2_project.png` |
| 4. Sam edits two files, adds one, and sends. Queued, then sent, then delivered. Dark theme. | Pass | `04_net1_dark.png`, `04_net1.png`, `04_net1_sent.png`, `04_net1_delivered.png` |
| 5. Ana reviews and accepts. Files stay hers until Accept. | Pass | `05_net2_toast.png`, `05_net2.png`, `05_net2_side_by_side.png`, `05_net2_form.png` |
| 6. Clash, Both, Cancel leaves files unchanged, Finish, Sam receives the merge. Dark theme. | Fail, then fixed | `06_net2.png`, `06_net2_both.png`, `06_net2_finished.png`, `06_net1.png` |
| 7. History, restore, undo, who-changed, set aside, bring back, package milestone. Dark theme. | Pass | `07_net1.png`, `07_net1_undo.png`, `07_net1_hover.png`, `07_net1_aside.png`, `07_net1_milestone.png`, `07_net1_packaged.png` |
| 8. Terminal offline, then the message goes out. | Pass | `08_net1.png`, `08_net1_sent.png` |
| 9. Forged `CBCS-SYNC/1` is ignored. FaxMail's own mail stays put. | Pass | `09_net1.png`, `09_net2.png` |

## What failed

Send Invite failed the first time. The status poll opened the ledger on one background-pool thread and Share ran on another. SQLite refused the second thread. `02_net1_error.png` is that dialog. The ledger now uses one connection with `check_same_thread=False` and a lock around every public method. The next Send Invite wrote `sent/20261102214558698/message.mail`.

Ana's first accept omitted `.gitignore`. dulwich 0.24 `update_working_tree` skips every path that starts with `.git`, so `.gitignore` never landed in the worktree and the next commit dropped it. Checkout now writes those skipped regular files itself, and a later accept on the fixed build restored the file. Hidden files can be created in the project folder. The skip was dulwich, not the ChoreBoy hidden-path rule.

Finish recorded the merge on Ana and sent a `have`. It did not send the merged tree, so Sam had nothing to accept. The live session published that one merge by calling the push directly. `finish_combine` now pushes when the kind is `merge`. A resolution that already matches the worktree also skipped the merge commit, so history kept a single parent. Finish now still records the merge parent in that case. `test_finish_writes_the_resolution_and_a_merge_commit` is the test that caught the skipped parent. The end-to-end test now accepts the merge on the other station.

## Timings

Clocks are the guest `time.time()` against the mailbox folder id.

- Send click to `out/` written. Invite click `1793655958.493` (`2026-11-02T21:45:58.493Z`) to folder `20261102214558698`, about 205 ms. The tax send click `1793656879.636` to folder `20261102220119715`, about 80 ms. The offline send click `1793658172.994` to folder `20261102222253070`, about 76 ms.
- `run-now` to the recipient toast. The tax zip `20261102220143164` was visible at `1793656908.43`. Ana's toast "rocksolid sent a change" was at `1793656925.057`, about 17 s after the zip was seen and about 22 s after the zip folder timestamp.
- Review tab. The open that reached the tax review went from `1793656945.458` to `1793656945.758`, about 300 ms.
- Typing during a poll. A click, a typed character, and the read-back on Sam ran from `1793656926.743` to `1793656927.377`, about 0.63 s. The editor did not stall. The extra character was removed.

## Step notes

The `.lock` inside `out/<id>/` lives only while the copy runs. The poll never saw it. Do not treat any screenshot as a lock sighting.

The share dialog has no person-name field. The invitee name is the mailbox local part, so the invite was `rocksolid`, shop field `Cedar Hollow`. Sam's own shop fell back to the account folder name `default`. Ana's join used the same fallback. The feed says `rocksolid`, not Ana Kurtz.

Each station writes its own "joined" commit, and the join message carries no pack. The shared commit `e5bd6e49` matches. The join commits do not (`359a1ea8` on Ana, `3e5e94df` on Sam). File contents matched after the checkout fix, including `.gitignore` (`7c7bd53df2fc`).

The first accept was a merge, so the tips still differed after the trees matched. The form compare showed the window title change from Invoice to Cedar Hollow. The visible label on the form still said Invoice, because the edit hit the window title.

Cancel on the clash left `invoice.py` on Ana's line and the form without Cedar Hollow. Finish was disabled until the clash was settled again. After Finish and Sam's accept, both disks had both line-total lines and the Cedar Hollow title.

History search for `tax` listed the tax change. Restore of that change dropped the combined lines. Undo This Change put both lines back. The who-changed card on line 1 read `rocksolid`, note `Shared Invoice App`, meta `default · Nov 2`. Set Aside removed `# set aside` from `customer.py` and named the pile "Hold the customer note". Bring Back restored the line and cleared the pile. Package Project showed "Mark this version in history" checked. Packaging wrote `/home/default/cbcs-team-net1/invoice_app_installer_v0.1.0` and set milestone `0.1.0` on the undo commit. The package report warned about hidden files, a generic description, and no custom icon.

The first `open_history()` ended Sam's editor session and left no Python traceback. After a relaunch, history opened and the rest of step 7 ran.

`watchdog-pause` stops `startup.sh`, so `.faxmail15-watchdog` stops advancing. The file read `2026-11-02 22:16:56`. Team Sync treats the terminal as offline after 5 minutes. Status was `offline` at `22:22:27Z`. The send stored delivery `waiting_terminal` in `out/20261102222253070` and the status bar read `Team: Terminal offline`. After `watchdog-pause off` and `run-now`, the folder was under `sent/`, delivery was `sent`, the watchdog read `2026-11-02 22:23:23`, and the status bar read `Team: Sent` by `22:23:52Z`.

The forged message was injected as a `.eml` (`mail inject @share:incoming/shopday/cbcs-forged-push.eml`), not with `--attach`. An attachment would keep FaxMail's own subject, and Team Sync only reads a subject that starts with `CBCS-SYNC/1`. The zip `20261102222424583!.zip` arrived with that subject and a signature of sixty-four `1`s. Sam's ledger marked `p_5fc9ae42e8d4facc|5b3718cc|b_deadbeefdeadbeef|1/1` unverified and imported nothing. Ana's ledger recorded the same unverified row. Both status popovers showed `1 message couldn't be verified`. Ana's incoming item was Sam's real due-date push (`b_e266721580c6ea96` from `ce4873e7`), not the forged bundle. `inbox/` was empty before and after. The day did not delete or move any other mailbox folder.

## Differences from the spec

- Invitee display name is the mailbox local part. Sam's shop label is the account folder name.
- Join history SHAs differ after the shared commit. The trees matched.
- The sender sees their own invite again on the next launch, because invite watch has no identity and the seen set is memory only. Sam cancelled it. `03_net1.png`.
- The composer note is not cleared after Send, so a later type appends.
- The feed mark for a waiting terminal still says Queued. The tooltip and the ledger state are Waiting. The status bar says `Team: Terminal offline`.
- Choosing lines that already match the worktree used to skip the merge commit. That is fixed.
- Finish used to leave the merge on the station that combined it. That is fixed.
