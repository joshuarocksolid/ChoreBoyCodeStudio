"""In-test FaxMail terminal. Moves unlocked out folders to sent and drops zip_in archives."""

from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path

from app.features.team_sync.core.mailbox import (
    ACCOUNT_CONF,
    header_value,
    address_of,
    read_account_settings,
    split_message,
)


class FaxMailSim:
    def __init__(self, mails_root: Path) -> None:
        self.mails = Path(mails_root)

    def tick(self) -> int:
        delivered = 0
        accounts = [
            path
            for path in self.mails.iterdir()
            if path.is_dir() and (path / ACCOUNT_CONF).is_file()
        ]
        by_email = {}
        for account in accounts:
            email_address, _size = read_account_settings(account / ACCOUNT_CONF)
            by_email[email_address.lower()] = account
        for account in accounts:
            out = account / "out"
            if not out.is_dir():
                continue
            for folder in list(out.iterdir()):
                if not folder.is_dir() or (folder / ".lock").exists():
                    continue
                message = folder / "message.mail"
                if not message.is_file():
                    continue
                raw = message.read_bytes()
                sent = account / "sent" / folder.name
                sent.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(folder), str(sent))
                if self._deliver(by_email, sent, raw):
                    delivered += 1
        return delivered

    def _deliver(self, by_email: dict, sent: Path, raw: bytes) -> bool:
        headers, body = split_message(raw)
        recipient = by_email.get(address_of(header_value(headers, "To")))
        if recipient is None:
            return False
        folder_id = sent.name
        prefix = f"{folder_id}!"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(prefix + "/", b"")
            archive.writestr(prefix + "/_headers_", headers.encode("utf-8"))
            archive.writestr(prefix + "/textfile0", body.encode("utf-8"))
            att = sent / "att"
            if att.is_dir():
                for path in sorted(att.iterdir()):
                    if path.is_file():
                        archive.writestr(prefix + "/" + path.name, path.read_bytes())
        zip_in = recipient / "zip_in"
        zip_in.mkdir(parents=True, exist_ok=True)
        (zip_in / f"{folder_id}!.zip").write_bytes(buffer.getvalue())
        return True
