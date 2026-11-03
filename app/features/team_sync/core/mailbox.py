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
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from app.features.shop_sharing.model import Machine
from app.features.shop_sharing.storage import logical_path, share_roots, visible_child_dirs
from app.features.team_sync.api import TERMINAL_NONE, TERMINAL_OFFLINE, TERMINAL_OK, Mailbox
from app.features.team_sync.core import TeamSyncError

ACCOUNT_CONF = "account_settings_v2.conf"
WATCHDOG_STALE = timedelta(minutes=5)


class MailNotReady(TeamSyncError):
    """A mailbox file is not readable yet. The next poll tries it again."""


@dataclass(frozen=True)
class InboundMail:
    source: str
    subject: str
    from_header: str
    body: str
    attachments: Dict[str, bytes]
    key: Tuple[str, int, int] = ()


@dataclass
class MailScan:
    """Directory mtime short-circuit, then per-file (name, size, mtime) memory.

    Attachments stay unread until :meth:`load_attachments`. A file that cannot
    be read yet is not part of the saved stamp, so the next poll tries it again.
    """

    roots: Tuple[str, ...]
    _stamp: Optional[Tuple[Tuple[str, Optional[int]], ...]] = None
    _known: Dict[Tuple[str, int, int], str] = field(default_factory=dict)
    hits: List[InboundMail] = field(default_factory=list)
    failed: bool = False

    def scan(self) -> List[InboundMail]:
        stamp = _tree_stamp(self.roots)
        if stamp == self._stamp and not self.failed:
            return []
        self.failed = False
        found: List[InboundMail] = []
        for root in self.roots:
            account = Path(root)
            found.extend(self._take(account / "zip_in", "zip"))
            found.extend(self._take(account / "inbox", "inbox"))
        if not self.failed:
            self._stamp = stamp
        self.hits = found
        return found

    def invalidate(self) -> None:
        """Forget the directory stamp so a message that failed handling is retried."""

        self._stamp = None
        self.failed = True

    def remember(self, key: Tuple[str, int, int], result: str) -> None:
        if key:
            self._known[key] = result

    def load_attachments(self, mail: InboundMail) -> InboundMail:
        if mail.attachments:
            return mail
        path = Path(mail.source)
        try:
            if path.suffix == ".zip":
                attachments = _zip_attachments(path)
            else:
                attachments = _dir_attachments(path)
        except (OSError, KeyError) as exc:
            raise MailNotReady(str(exc)) from exc
        return InboundMail(
            source=mail.source,
            subject=mail.subject,
            from_header=mail.from_header,
            body=mail.body,
            attachments=attachments,
            key=mail.key,
        )

    def _take(self, directory: Path, kind: str) -> List[InboundMail]:
        if not directory.is_dir():
            return []
        found: List[InboundMail] = []
        try:
            children = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError:
            self.failed = True
            return []
        for path in children:
            if kind == "zip" and path.suffix != ".zip":
                continue
            if kind == "inbox" and not path.is_dir():
                continue
            try:
                key = _file_key(path)
            except OSError:
                self.failed = True
                continue
            state = self._known.get(key)
            if state in {"skip", "done"}:
                continue
            if state == "fail":
                self._known[key] = "skip"
                continue
            try:
                mail = _peek_zip(path, key) if kind == "zip" else _peek_inbox(path, key)
            except MailNotReady:
                self._known[key] = "fail"
                self.failed = True
                continue
            if mail is None:
                self._known[key] = "skip"
                continue
            self._known[key] = "done"
            found.append(mail)
        return found

    def forget(self, key: Tuple[str, int, int]) -> None:
        self._known.pop(key, None)
        self._stamp = None
        self.failed = True


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
            email_address, _size, user_name, company_name = read_account_profile(conf)
            found.append(
                Mailbox(
                    path=identity,
                    email=email_address,
                    label=child.name,
                    user_name=user_name,
                    company_name=company_name,
                )
            )
    return found


def read_account_settings(path: Path) -> Tuple[str, Optional[int]]:
    email_address, max_size, _user_name, _company_name = read_account_profile(path)
    return email_address, max_size


def read_account_profile(path: Path) -> Tuple[str, Optional[int], str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise TeamSyncError(f"Could not read the FaxMail account settings: {exc}") from exc
    email_address = _conf_field(text, "EmailAddress")
    user_name = _conf_field(text, "UserName")
    company_name = _conf_field(text, "CompanyName")
    raw_size = _conf_field(text, "MaxMsgSize")
    max_size = int(raw_size) if raw_size.isdigit() else None
    return email_address, max_size, user_name, company_name


def _conf_field(text: str, key: str) -> str:
    prefix = key + "}{"
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split("}{", 1)[1].strip()
    return ""


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
    on_claimed: Optional[Callable[[str], None]] = None,
) -> str:
    """Build on local disk. Claim ``out/<id>/`` with ``os.mkdir``, then lock, copy, unlock.

    Only the folder this call created is removed, and only when the copy fails
    before a message is in place. A folder that already existed is left alone.
    """

    import tempfile

    account_dir = Path(account_dir)
    if not account_dir.is_dir():
        raise TeamSyncError("The FaxMail account folder is missing.")
    out_root = account_dir / "out"
    if not out_root.exists():
        try:
            os.mkdir(out_root)
        except FileExistsError:
            pass
    if not out_root.is_dir():
        raise TeamSyncError("The FaxMail out folder is missing.")
    staging = Path(tempfile.mkdtemp(prefix="cbcs-mail-"))
    created: Optional[Path] = None
    try:
        atomic_write_bytes(staging / "message.mail", message)
        if attachments:
            att = staging / "att"
            os.mkdir(att)
            for name, payload in attachments.items():
                atomic_write_bytes(att / _attachment_file_name(name), payload)
        dest = _claim_out(out_root, mail_id)
        created = dest
        folder_id = dest.name
        if on_claimed is not None:
            on_claimed(folder_id)
        lock_path = dest / ".lock"
        _note(trace, "lock")
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError as exc:
            raise TeamSyncError(f"Could not lock the outgoing mail folder: {exc}") from exc
        os.close(fd)
        _note(trace, "copy")
        _copy_verified(staging / "message.mail", dest / "message.mail")
        if attachments:
            os.mkdir(dest / "att")
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
        created = None
        return folder_id
    except Exception:
        if created is not None:
            _remove_tree(created)
        raise
    finally:
        _remove_tree(staging)


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


def _file_key(path: Path) -> Tuple[str, int, int]:
    st = path.stat()
    return (str(path), int(st.st_size), int(st.st_mtime_ns))


def _peek_zip(path: Path, key: Tuple[str, int, int]) -> Optional[InboundMail]:
    import zipfile

    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise MailNotReady(str(exc)) from exc
    try:
        headers_name = ""
        for info in archive.infolist():
            if info.filename.endswith("/_headers_") or info.filename == "_headers_":
                headers_name = info.filename
                break
        if not headers_name:
            return None
        try:
            headers = archive.read(headers_name).decode("utf-8", "replace")
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            raise MailNotReady(str(exc)) from exc
        subject = header_value(headers, "Subject")
        if not subject.startswith("CBCS-SYNC/1 "):
            return None
        prefix = headers_name[: -len("_headers_")]
        body_name = prefix + "textfile0"
        body = ""
        names = set(archive.namelist())
        if body_name in names:
            try:
                body = archive.read(body_name).decode("utf-8", "replace")
            except (OSError, zipfile.BadZipFile, KeyError) as exc:
                raise MailNotReady(str(exc)) from exc
        return InboundMail(
            source=str(path),
            subject=subject,
            from_header=header_value(headers, "From"),
            body=body,
            attachments={},
            key=key,
        )
    finally:
        archive.close()


def _zip_attachments(path: Path) -> Dict[str, bytes]:
    import zipfile
    import zlib

    attachments: Dict[str, bytes] = {}
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile, zlib.error) as exc:
        raise MailNotReady(str(exc)) from exc
    with archive:
        headers_name = ""
        for info in archive.infolist():
            if info.filename.endswith("/_headers_") or info.filename == "_headers_":
                headers_name = info.filename
                break
        prefix = headers_name[: -len("_headers_")] if headers_name else ""
        body_name = prefix + "textfile0"
        for info in archive.infolist():
            filename = info.filename
            if filename.endswith("/") or filename in {headers_name, body_name}:
                continue
            base = filename.rsplit("/", 1)[-1]
            if not base or base in {"_headers_", "textfile0"}:
                continue
            if ".cbcsbundle" not in base:
                continue
            try:
                attachments[base] = archive.read(info)
            except (OSError, zipfile.BadZipFile, zlib.error, KeyError) as exc:
                raise MailNotReady(str(exc)) from exc
    return attachments


def _peek_inbox(path: Path, key: Tuple[str, int, int]) -> Optional[InboundMail]:
    headers_path = path / "_headers_"
    if not headers_path.is_file():
        return None
    try:
        headers = headers_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise MailNotReady(str(exc)) from exc
    subject = header_value(headers, "Subject")
    if not subject.startswith("CBCS-SYNC/1 "):
        return None
    body = ""
    body_path = path / "textfile0"
    if body_path.is_file():
        try:
            body = body_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise MailNotReady(str(exc)) from exc
    return InboundMail(
        source=str(path),
        subject=subject,
        from_header=header_value(headers, "From"),
        body=body,
        attachments={},
        key=key,
    )


def _dir_attachments(path: Path) -> Dict[str, bytes]:
    attachments: Dict[str, bytes] = {}
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        raise MailNotReady(str(exc)) from exc
    for entry in entries:
        if not entry.is_file() or entry.name in {"_headers_", "textfile0"}:
            continue
        if ".cbcsbundle" not in entry.name:
            continue
        try:
            attachments[entry.name] = entry.read_bytes()
        except OSError as exc:
            raise MailNotReady(str(exc)) from exc
    return attachments


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


def _claim_out(out_root: Path, mail_id: str) -> Path:
    """Claim one outgoing folder. ``os.mkdir`` is the claim. A taken id is skipped."""

    candidate = mail_id
    for _offset in range(1000):
        dest = out_root / candidate
        sent = out_root.parent / "sent" / candidate
        if sent.exists():
            candidate = f"{int(candidate) + 1:017d}"
            continue
        try:
            os.mkdir(dest)
        except FileExistsError:
            candidate = f"{int(candidate) + 1:017d}"
            continue
        return dest
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
