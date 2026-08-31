---
name: release-cbcs
description: Package a ChoreBoy-compatible product zip and prove it on the live VM before mailing, tagging, or handing a shop installer. Use when releasing, mailing LibrePy, tagging v*, running package.py for a product zip, or verifying an installer.
---

# Release ChoreBoy Code Studio

Do not mail or tag a product zip until this list is green on the real ChoreBoy VM.

## Vendor

Product source is a Linux manylinux `vendor_py39`. Do not package the Darwin tree Mac tests use.

```bash
CBCS_ARTIFACTS_DIR=/path/to/linux_artifacts ./scripts/setup_vendor_py39.sh
python3 package.py
```

`file` every `payload/vendor/**/_binding*.so`. Each must be `ELF 64-bit LSB shared object, x86-64`. Mach-O fails the release.

`validate_choreboy_tree_sitter_bundle` rejects non-ELF at staging. A passing package command is still not a ChoreBoy proof.

## Live proof

Follow [../verify-cbcs/SKILL.md](../verify-cbcs/SKILL.md). Drive the zip that will be mailed, not a source checkout.

```bash
CONTROL=".cursor/skills/verify-cbcs/scripts/control-cbcs"
$CONTROL launch --install --zip /path/to/choreboy_code_studio_installer_v*.zip
$CONTROL doctor "$SID"
```

Pass only if all of these hold:

1. `#shell.startupStatusLabel` contains `Runtime ready`
2. That chip does not contain `Syntax highlighting off`
3. Runtime Center has no tree-sitter issue
4. A project `.py` file opens without falling back to plain text

Keep shots under `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/`. Then `$CONTROL stop "$SID"`.

If another `cbapp` session is live, wait or refuse. Do not stop a session this run did not start.
