# Team Sync test fixtures

- `real_git_delta.bundle`: made with real git 2.x (`git gc --aggressive; git bundle create`).
  Ref `refs/heads/main` = `ddb62daf84c654ec20fdec234f47c6b03bb38314`, 6 commits, 6 blobs of
  `big_module.py` of which 5 are offset deltas against the 12,640-byte base. The final
  `big_module.py` contains the line `# rev 5`. dulwich must import it completely through
  `object_store.add_thin_pack`; `Bundle.store_objects` loses commits on it.
