"""FaxMail adapter. Writes only our out/<id>/ folders. Reads zip_in and inbox."""

from __future__ import annotations

import email
import email.utils
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.features.shop_sharing.model import Machine
from app.features.shop_sharing.storage import logical_path, share_roots, visible_child_dirs
from app.features.team_sync.api import TERMINAL_NONE, TERMINAL_OFFLINE, TERMINAL_OK, Mailbox
from app.features.team_sync.core import TeamSyncError

ACCOUNT_CONF = "account_settings_v2.conf"
WATCHDOG_STALE = timedelta(minutes=5)


@dataclass(frozen=True)
class InboundMail:
    source: str
    subject: str
    from_header: str
    body: str
    attachments: Dict[str, bytes]


@dataclass
class MailScan:
    """mtime short-circuit. A second pass with nothing new only stats directories."""

    roots: Tuple[str, ...]
    _stamp: Optional[Tuple[Tuple[str, Optional[int]], ...]] = None
    hits: List[InboundMail] = field(default_factory=list)

    def scan(self) -> List[InboundMail]:
        stamp = _tree_stamp(self.roots)
        if stamp == self._stamp:
            return []
        found: List[InboundMail] = []
        for root in self.roots:
            account = Path(root)
            found.extend(_scan_zip_in(account / "zip_in"))
            found.extend(_scan_inbox(account / "inbox"))
        self._stamp = stamp
        self.hits = found
        return found


def discover_mailboxes(
    machine: Optional[Machine],
    mail_roots: Optional[Sequence[str]] = None,
) -> List[Mailbox]:
    roots = _mails_directories(machine, mail_roots)
    found: List[Mailbox] = []
    seen = set()
    for root in roots:
        if not root.is_dir():
            continue
        direct = root / ACCOUNT_CONF
        children = [root] if direct.is_file() else visible_child_dirs(root)
        for child in children:
            conf = child / ACCOUNT_CONF
            if not conf.is_file():
                continue
            identity = str(logical_path(child))
            if identity in seen:
                continue
            seen.add(identity)
            email_address, _size = read_account_settings(conf)
            found.append(Mailbox(path=identity, email=email_address, label=child.name))
    return found


def read_account_settings(path: Path) -> Tuple[str, Optional[int]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TeamSyncError(f"Could not read the FaxMail account settings: {exc}") from exc
    email_address = ""
    max_size: Optional[int] = None
    for line in text.splitlines():
        if line.startswith("EmailAddress}{"):
            email_address = line.split("}{", 1)[1].strip()
        elif line.startswith("MaxMsgSize}{"):
            raw = line.split("}{", 1)[1].strip()
            if raw.isdigit():
                max_size = int(raw)
    return email_address, max_size


def terminal_state(
    mail_roots: Sequence[str],
    now: datetime,
    hostname: str,
) -> str:
    if not mail_roots:
        return TERMINAL_NONE
    newest: Optional[datetime] = None
    saw_file = False
    for root in mail_roots:
        account = Path(root)
        mails = account.parent
        candidates = [mails / f".{hostname}-watchdog"]
        try:
            candidates.extend(
                path for path in mails.iterdir() if path.name.startswith(".") and path.name.endswith("-watchdog")
            )
        except OSError:
            continue
        for path in candidates:
            if not path.is_file():
                continue
            saw_file = True
            stamped = _parse_watchdog(path)
            if stamped is not None and (newest is None or stamped > newest):
                newest = stamped
    if not saw_file or newest is None:
        return TERMINAL_OFFLINE
    current = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    stamped = newest if newest.tzinfo is not None else newest.replace(tzinfo=timezone.utc)
    if current - stamped > WATCHDOG_STALE:
        return TERMINAL_OFFLINE
    return TERMINAL_OK


def mails_root_for_accounts(accounts: Iterable[str]) -> List[str]:
    return list(accounts)


def publish_out(
    account_dir: Path,
    mail_id: str,
    message: bytes,
    attachments: Dict[str, bytes],
    trace: Optional[List[str]] = None,
) -> str:
    """Build on local disk. In out/<id>/, .lock is created before the bytes and removed last.

    The terminal skips a folder that still holds .lock, so a crash mid-copy cannot send a partial message.
    """

    import tempfile

    account_dir = Path(account_dir)
    out_root = account_dir / "out"
    _mkdir(out_root)
    folder_id = _unique_id(out_root, mail_id)
    staging = Path(tempfile.mkdtemp(prefix="cbcs-mail-"))
    dest = out_root / folder_id
    try:
        atomic_write_bytes(staging / "message.mail", message)
        if attachments:
            att = staging / "att"
            _mkdir(att)
            for name, payload in attachments.items():
                atomic_write_bytes(att / _attachment_file_name(name), payload)
        _mkdir(dest)
        lock_path = dest / ".lock"
        _note(trace, "lock")
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError as exc:
            _remove_tree(dest)
            raise TeamSyncError(f"Could not lock the outgoing mail folder: {exc}") from exc
        os.close(fd)
        _note(trace, "copy")
        _copy_verified(staging / "message.mail", dest / "message.mail")
        if attachments:
            _mkdir(dest / "att")
            for name in attachments:
                filename = _attachment_file_name(name)
                _copy_verified(staging / "att" / filename, dest / "att" / filename)
        _fsync_dir(dest)
        _fsync_dir(out_root)
        _note(trace, "unlock")
        try:
            os.unlink(str(lock_path))
        except OSError as exc:
            raise TeamSyncError(f"Could not release the outgoing mail folder: {exc}") from exc
        _fsync_dir(dest)
    except Exception:
        if dest.exists() and (dest / ".lock").exists() and not (dest / "message.mail").is_file():
            _remove_tree(dest)
        raise
    finally:
        _remove_tree(staging)
    return folder_id


def is_sent(account_dir: Path, folder_id: str) -> bool:
    out_folder = Path(account_dir) / "out" / folder_id
    sent_mail = Path(account_dir) / "sent" / folder_id / "message.mail"
    try:
        return sent_mail.is_file() and not out_folder.exists()
    except OSError:
        return False


def atomic_write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    """Temp file, fsync, replace. The temp name is visible, same rule as shop sharing."""

    path = Path(path)
    _mkdir(path.parent)
    last_error: Optional[BaseException] = None
    for attempt in range(4):
        tmp = path.parent / f"{path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
        try:
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
            try:
                view = memoryview(data)
                while view:
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.chmod(str(tmp), mode)
            os.replace(str(tmp), str(path))
            if mode != 0o644:
                os.chmod(str(path), mode)
            _fsync_dir(path.parent)
            return
        except OSError as exc:
            last_error = exc
            try:
                tmp.unlink()
            except OSError:
                pass
            time.sleep(0.02 * (attempt + 1))
    raise TeamSyncError(f"Could not write {path.name}: {last_error}")


def render_message(
    *,
    sender_name: str,
    sender_email: str,
    recipient_name: str,
    recipient_email: str,
    subject: str,
    body: str,
    when: datetime,
    message_id: str,
) -> bytes:
    moment = when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
    headers = [
        f"From: {_address(sender_name, sender_email)}",
        f"To: {_address(recipient_name, recipient_email)}",
        f"Subject: {subject}",
        f"Date: {email.utils.formatdate(moment.timestamp(), usegmt=True)}",
        f"Message-ID: <{message_id}>",
    ]
    head = "\r\n".join(headers) + "\r\n\r\n"
    text = body if body.endswith("\n") else body + "\n"
    return head.encode("utf-8") + text.replace("\r\n", "\n").encode("utf-8")


def split_message(raw: bytes) -> Tuple[str, str]:
    if b"\r\n\r\n" in raw:
        head, body = raw.split(b"\r\n\r\n", 1)
    elif b"\n\n" in raw:
        head, body = raw.split(b"\n\n", 1)
    else:
        head, body = raw, b""
    return head.decode("utf-8", "replace"), body.decode("utf-8", "replace")


def header_value(headers: str, name: str) -> str:
    message = email.message_from_string(headers if headers.endswith("\n") else headers + "\n")
    return str(message.get(name, "") or "")


def address_of(from_header: str) -> str:
    _name, addr = email.utils.parseaddr(from_header)
    return addr.strip().lower()


def _mails_directories(
    machine: Optional[Machine], mail_roots: Optional[Sequence[str]]
) -> List[Path]:
    if mail_roots is not None:
        return [Path(root) for root in mail_roots]
    found: List[Path] = []
    if machine is not None:
        for root in share_roots(machine):
            found.append(root / "PDF" / ".Mails")
    found.append(Path("/home/default/PDF/.Mails"))
    return found


def _scan_zip_in(directory: Path) -> List[InboundMail]:
    if not directory.is_dir():
        return []
    found: List[InboundMail] = []
    try:
        names = sorted(path.name for path in directory.iterdir() if path.suffix == ".zip")
    except OSError:
        return []
    for name in names:
        path = directory / name
        try:
            mail = _read_zip(path)
        except OSError:
            continue
        if mail is not None:
            found.append(mail)
    return found


def _read_zip(path: Path) -> Optional[InboundMail]:
    import zipfile

    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile):
        return None
    with archive:
        headers_name = ""
        for info in archive.infolist():
            if info.filename.endswith("/_headers_") or info.filename == "_headers_":
                headers_name = info.filename
                break
        if not headers_name:
            return None
        headers = archive.read(headers_name).decode("utf-8", "replace")
        subject = header_value(headers, "Subject")
        if not subject.startswith("CBCS-SYNC/1 "):
            return None
        prefix = headers_name[: -len("_headers_")]
        body_name = prefix + "textfile0"
        body = ""
        if body_name in archive.namelist():
            body = archive.read(body_name).decode("utf-8", "replace")
        attachments: Dict[str, bytes] = {}
        for info in archive.infolist():
            filename = info.filename
            if filename.endswith("/") or filename in {headers_name, body_name}:
                continue
            base = filename.rsplit("/", 1)[-1]
            if not base or base in {"_headers_", "textfile0"}:
                continue
            attachments[base] = archive.read(info)
        return InboundMail(
            source=str(path),
            subject=subject,
            from_header=header_value(headers, "From"),
            body=body,
            attachments=attachments,
        )


def _scan_inbox(directory: Path) -> List[InboundMail]:
    if not directory.is_dir():
        return []
    found: List[InboundMail] = []
    try:
        children = [path for path in directory.iterdir() if path.is_dir()]
    except OSError:
        return []
    for child in sorted(children, key=lambda item: item.name):
        headers_path = child / "_headers_"
        if not headers_path.is_file():
            continue
        try:
            headers = headers_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        subject = header_value(headers, "Subject")
        if not subject.startswith("CBCS-SYNC/1 "):
            continue
        body = ""
        body_path = child / "textfile0"
        if body_path.is_file():
            try:
                body = body_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                body = ""
        attachments: Dict[str, bytes] = {}
        try:
            for entry in child.iterdir():
                if not entry.is_file() or entry.name in {"_headers_", "textfile0"}:
                    continue
                attachments[entry.name] = entry.read_bytes()
        except OSError:
            continue
        found.append(
            InboundMail(
                source=str(child),
                subject=subject,
                from_header=header_value(headers, "From"),
                body=body,
                attachments=attachments,
            )
        )
    return found


def _tree_stamp(roots: Sequence[str]) -> Tuple[Tuple[str, Optional[int]], ...]:
    stamps: List[Tuple[str, Optional[int]]] = []
    for root in roots:
        account = Path(root)
        for name in ("zip_in", "inbox"):
            path = account / name
            try:
                stamps.append((str(path), path.stat().st_mtime_ns))
            except OSError:
                stamps.append((str(path), None))
    return tuple(stamps)


def _parse_watchdog(path: Path) -> Optional[datetime]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _unique_id(out_root: Path, mail_id: str) -> str:
    candidate = mail_id
    for _offset in range(1000):
        if not (out_root / candidate).exists() and not (out_root.parent / "sent" / candidate).exists():
            return candidate
        candidate = f"{int(candidate) + 1:017d}"
    raise TeamSyncError("Could not find a free outgoing mail id.")


def _attachment_file_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in base)
    return cleaned or "attachment.bin"


def _address(name: str, email_address: str) -> str:
    safe = name.replace('"', "")
    return f"{safe} <{email_address}>" if safe else email_address


def _mkdir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        return
    finally:
        os.close(fd)


def _remove_tree(path: Path) -> None:
    import shutil

    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        pass


def _copy_verified(source: Path, dest: Path) -> None:
    data = source.read_bytes()
    atomic_write_bytes(dest, data)
    written = dest.read_bytes()
    if written != data:
        raise TeamSyncError(f"Outgoing mail {dest.name} did not read back.")


def _note(trace: Optional[List[str]], step: str) -> None:
    if trace is not None:
        trace.append(step)
