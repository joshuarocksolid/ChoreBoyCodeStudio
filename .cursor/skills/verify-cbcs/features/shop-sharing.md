# Shop sharing

Settings, recent projects, and Python Console history can live in a visible
`Code Studio Settings/` folder on the shop share. Each machine stores its own
absolute path to that folder in `<local state>/shop_sharing.json`. Product
behavior is in `docs/shop_sharing/SPEC.md`.

<!-- dune-owners: shop-sharing, platform.bootstrap -->

## Sub-features

- `share-merge` saves only the changed settings leaves into the shop's `settings.json`.
- `share-recents` keeps `shop_recent_projects.json` (v2) entries relative to the share root, so one entry opens on the server and on clients.
- `share-offline` keeps working on the last synced copy while the share is gone, and pushes the pending changes when it returns.
- `share-convert` turns a v0.4.13 pointer or legacy home link into a choice file once.

## How to get to it (user POV)

- Settings, General tab, Shop sharing group. The UI lane owns this entry point.

## Driving it with control-cbcs

Preconditions:

- Doctor passed.

- Not drivable until the Settings group lands.
- **Proof.** `shop_sharing.json` under local state names the folder, and the shop folder holds `shop.json`.

## Gotchas

- An offline shop folder never shows a startup dialog and never falls back to the local files.
