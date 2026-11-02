# Team Sync shop day 2 (euf8)

Drove the same nine steps on cbfarm shop `euf8` after the L3c fixes. net1 was Sam Brenneman (Maple Ridge). net2 was Ana Kurtz (Cedar Hollow). Both used the twin account `rocksolid@upwardmail.com`. net15 was the FaxMail twin. Disposable homes were `/home/default/cbcs-team-net1` and `/home/default/cbcs-team-net2`. CBCS ran from source at `/mnt/cbprobe/incoming/cbcs/team-sync-final` with the cp39 vendor bundle. `CBCS_FAULT_LOG` was `/home/default/cbcs-team-net1/fault.log` and `/home/default/cbcs-team-net2/fault.log`. Both files were 0 bytes at the end. Project id `p_2c6975cbba117673`. Screenshots are in `docs/team_sync/screens/final/`.

The twin account folder did not already contain `account_settings_v2.conf`. Setup wrote `EmailAddress}{rocksolid@upwardmail.com`, `UserName}{Sam Brenneman`, `CompanyName}{Maple Ridge`, `MaxMsgSize}{30000000` under `/home/default/share/PDF/.Mails/default/`.

## Steps

| Step | Result | Evidence |
| --- | --- | --- |
| 1. Sam opens Invoice App. Team view shows Not shared. | Pass | `01_net1.png`, `01_net1_project.png` |
| 2. Share and invite. Names come from the account file. `out/<id>/` then `sent/<id>/message.mail` with subject `CBCS-SYNC/1 invite`. | Pass | `02_net1_dialog.png`, `02_net1.png` |
| 3. Ana sees a verified invite with her name and shop, opens the project, and both `main` SHAs match. No Review item. | Pass | `03_net2_invite.png`, `03_net2.png`, `03_net2_project.png`, `03_net1_joined.png` |
| 4. Sam edits two files, adds one, and sends. Queued, then sent, then delivered. Dark theme. | Pass | `04_net1_dark.png`, `04_net1_sheet.png`, `04_net1.png`, `04_net1_delivered.png` |
| 5. Ana reviews and accepts. The BEFORE pane shows the old `invoice.py`. Files stay hers until Accept. | Pass | `05_net2_toast.png`, `05_net2.png`, `05_net2_side_by_side.png` |
| 6. Clash, Both, Cancel leaves files unchanged, Finish, Sam receives the merge. Dark theme. | Pass | `06_net2.png`, `06_net2_both.png`, `06_net2_finished.png` |
| 7. History, restore, undo, who-changed, set aside, bring back, package milestone. Dark theme. History did not kill the editor. | Pass | `07_net1.png`, `07_net1_undo.png`, `07_net1_hover.png`, `07_net1_aside.png`, `07_net1_milestone.png`, `07_net1_packaged.png`, `07_net1_status.png` |
| 8. Terminal offline. The feed mark says Waiting. Then the message goes out. | Pass | `08_net1.png`, `08_net1_sent.png` |
| 9. Forged `CBCS-SYNC/1` is ignored. FaxMail's own mail stays put. | Pass | `09_net1.png`, `09_net1_dark.png`, `09_net2.png`, `09_net2_dark.png` |

## SHAs

Both stations, `refs/heads/main`.

| When | SHA |
| --- | --- |
| After Ana joined and Sam applied the join | `33549cc61c251586bf40694a7942acecf23ebad5` |
| After Sam accepted Ana's merge | `a17257036cc4a1c1ba3756733a64fb4f27555b01` |
| End of the day, after Ana accepted Sam's later pushes | `c47f9e4e8259a1de53af64f66d50952c0972d96d` |

The four project files (`invoice.py`, `customer.py`, `tax.py`, `invoice.ui`) had the same SHA-256 on both disks at the end.

## Timings

Clocks are guest `time.time()` against the mailbox folder id, measured inside the editor process.

- Send click to `out/` written. The tax send at `1793661867.217` wrote `out/20261102232427289` in 102 ms. The offline send wrote `out/20261102234213046` in 103 ms. The invite folder is `sent/20261102231454462`.
- `run-now` to the recipient. The tax push was in `sent/` by `23:24:51Z`. Ana's toast was visible at `23:25:16Z`.
- Review tab. The Review click made `#shell.teamSync.reviewTab` visible in 12 ms. The side-by-side text was filled on the next read.
- Typing during a poll. With `refresh_status` and a poll already scheduled, inserting a character and deleting it took 17 ms. The editor did not stall.

## Step notes

The share dialog prefilled Your name `Sam Brenneman` and Your shop `Maple Ridge` from `account_settings_v2.conf`. The invite row was Ana Kurtz, Cedar Hollow, `rocksolid@upwardmail.com`. The sent invite is `From: Sam Brenneman`, `To: Ana Kurtz`, subject `CBCS-SYNC/1 invite p_2c6975cbba117673 Invoice App`, with `member-name: Ana Kurtz`. The feed says Sam Brenneman, not the mailbox local part.

Ana's invite dialog prefilled Your name `Ana Kurtz` and Shop `Cedar Hollow` from that invite. She opened `/home/default/cbcs-team-net2/Projects/Invoice App`. Her feed line is `Ana Kurtz joined from Cedar Hollow`. Sam's feed shows the same words on a system line (`shell.teamSync.feedSystem`). There was no Review control for the join. The join message is `sent/20261102231726797`, subject `CBCS-SYNC/1 join`.

Sam's first editor session was ended by the app-run timeout of 240 seconds (`cbapp` log: `timeout; terminating`, `rc=-15`). The fault log stayed empty. That was the harness lifetime, not a native crash. Both stations were relaunched with `--timeout 3600`. The relaunch did not offer Sam his own invite. `machine.json` still held member `00543597` and bundle `b_4f1722e56b488b69`. History opened from the status popover and listed every note, including a search for `tax`. The fault logs were still empty afterward.

The tax send sheet listed `M customer.py`, `M invoice.py`, and `A tax.py`, note `Add the tax line`, button `Send to Cedar Hollow`. The composer note was empty after the send completed. The feed mark was `Queued`, then a check, then two checks, and the status bar read `Team: Delivered`.

Ana's side-by-side BEFORE pane for `invoice.py` (M) showed `def total(x):` / `return x`. AFTER showed `return round(x * 1.06, 2)` and `def tax`. Her disk file was still `return x` until Accept.

The clash was line 2 of `invoice.py`. Ana's side was `return round(x * 1.05, 2)`. Sam's side was `return round(x + x * 0.06, 2)`. Both produced both lines. Cancel left her file on the 1.05 line only, and the form title stayed `Cedar Hollow`. Finish wrote both lines and pushed. Sam's accept moved him to the same SHA. The feed says `You accepted Ana Kurtz's change`.

History search for `tax` showed `Add the tax line` by Sam. Restore of that change dropped the combined lines. Undo This Change put both lines back (`Undid Restored Add the tax line`). The who-changed card read `Sam Brenneman`, `Maple Ridge · Nov 2`, note `Shared Invoice App`. Set Aside of `# set aside` in `customer.py` named the pile `Hold the customer note` and removed the line. Bring Back restored the line. Package Project had `Mark this version in history` checked, wrote `/home/default/cbcs-team-net1/invoice_app_installer_v0.1.0`, and tagged `v0.1.0`. The package report warned about hidden files, a generic description, and no custom icon. The history row shows the `0.1.0` chip.

`watchdog-pause` froze `.faxmail15-watchdog` at `2026-11-02 23:36:06`. The status bar read `Team: Terminal offline` at `23:42:03Z`. The send stored `out/20261102234213046` and the feed mark was `Waiting` with delivery property `waiting`, not `Queued`. After `watchdog-pause off` and `run-now`, the folder was under `sent/`, the mark was a single check, the watchdog read `2026-11-02 23:42:38`, and the status bar read `Team: Sent`.

The forged message was injected as `mail inject @share:incoming/shopday/cbcs-forged-push.eml`, not with `--attach`. The zip `20261102234337965!.zip` arrived with subject `CBCS-SYNC/1 push` and a signature of sixty-four `1`s. Both ledgers marked `p_2c6975cbba117673|00543597|b_deadbeefdeadbeef|1/1` unverified. Neither station imported it. Both popovers, light and dark, showed `1 message couldn't be verified` on an opaque panel. Ana's review item was Sam's real restore (`Restored Add the tax line`), not the forged bundle. `inbox/` was empty before and after. The day did not delete or move any other mailbox folder.

The status popover in `07_net1_status.png`, `09_net1.png`, and `09_net1_dark.png` is an opaque bordered panel. On the dark theme it does not sit as bare text on the status bar. The light shots are `09_net1.png` and `09_net2.png`. Steps 8 and 9's first captures stayed in the dark theme left on from step 7. Step 9 was shot again in light.

## Open issues

None of the nine shop-day blockers remain.

Two follow-ups showed up during the day and are not release blockers for those nine:

- Cancel on Combine clears the session and leaves the files unchanged, and the Combine tab stays open on `0 of 0 settled` until it is closed.
- The who-changed card is filled when the editor page opens. It is not refreshed after a later commit, so a line can still show the author from open time. The card in this day named Sam Brenneman of Maple Ridge, not the mailbox.
