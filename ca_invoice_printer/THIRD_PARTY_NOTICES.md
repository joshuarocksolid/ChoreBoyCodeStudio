# Third-Party Notices

This distribution bundles third-party dependencies under `vendor/` and also includes an embedded `jasper_bridge/` runtime.

The authoritative license terms are the license files shipped with each dependency and the upstream projects.

## Vendored Python dependencies

| Component | Bundled package path | Declared license | License file path |
|---|---|---|---|
| asn1crypto 1.5.1 | `vendor/asn1crypto/` | MIT | `vendor/asn1crypto-1.5.1.dist-info/LICENSE` |
| pg8000 1.31.5 | `vendor/pg8000/` | BSD 3-Clause | `vendor/pg8000-1.31.5.dist-info/licenses/LICENSE` |
| python-dateutil 2.9.0.post0 | `vendor/dateutil/` | Dual License (Apache-2.0 or BSD-3-Clause) | `vendor/python_dateutil-2.9.0.post0.dist-info/LICENSE` |
| scramp 1.4.8 | `vendor/scramp/` | MIT-0 | `vendor/scramp-1.4.8.dist-info/licenses/LICENSE` |
| six 1.17.0 | `vendor/six.py` | MIT | `vendor/six-1.17.0.dist-info/LICENSE` |

## Embedded jasper_bridge dependencies

`ca_invoice_printer` includes an embedded `jasper_bridge` copy under `ca_invoice_printer/jasper_bridge/`.

Its bundled Java dependency notices are listed in:

- `ca_invoice_printer/jasper_bridge/THIRD_PARTY_NOTICES.md`

