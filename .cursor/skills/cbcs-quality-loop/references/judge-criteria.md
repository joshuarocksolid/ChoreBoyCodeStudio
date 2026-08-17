# Judge-only rubric

The judge sees sanitized arm labels and this list. Never a model name. Score every arm in one pass.

1. **Isolated launch.** Started a new editor on the ChoreBoy VM with a disposable HOME. Did not attach to a window that was already open for a human.
2. **Doctor first.** Ran a health check (process up, session ready, startup chip contains `Runtime ready`, HOME is disposable) before driving. Re-checked after a failed drive.
3. **Real Qt path.** Clicked / typed / triggered the live window. Offscreen automated suite output is not accepted as the proof.
4. **Action plus result.** Evidence includes the action and the resulting state (screenshot of the app identity plus a read of the proving widget), not only a final frame.
5. **Side effects when it mutates.** If the task writes a file, runs code, or changes settings, a second read of disk or the run log is present.
6. **Cleanup contract.** Stopped only the session it started. Proof files remain at `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/` after teardown.

Each criterion: pass / fail / unclear, with a one-line cite (artifact path or transcript moment). Recommend a base only from these six.
