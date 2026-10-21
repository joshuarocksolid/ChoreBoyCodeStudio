"""Lease, snapshot, install, revert, release. Revert and release are idempotent."""

from __future__ import annotations

import json
import os
import signal
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from scenarios.adapter import INSTALL_DIR, default_runner
from scenarios.probes import ASIDE_SCRIPT, INSTALL_PRESENT, RESTORE_SCRIPT, SNAPSHOT_SCRIPT

FREE_PREFERENCE = ("ChoreBoy4", "ChoreBoy5", "ChoreBoy3")
ARTIFACT_ROOT = Path.home() / "ChoreBoy" / "artifacts" / "verify-cbcs"
GUEST_SHARE = "/mnt/cbprobe"
INSTALL_PARENT = "/home/default"
INSTALLER_DIR = "/home/default/choreboy_code_studio_installer_v0.4.13"
OUR_TREES = (
    INSTALLER_DIR,
    INSTALL_DIR,
    "/home/default/verify-aside",
    "/home/default/verify-cb1",
    "/home/default/verify-completion",
    "/home/default/verify-files",
    "/home/default/verify-groups",
    "/home/default/verify-pkg",
    "/home/default/verify-pkg-out",
    "/home/default/verify-reload",
    "/home/default/verify-cb7",
    "/home/default/verify-cold",
    "/home/default/crud_showcase.desktop",
    "/home/default/choreboy_code_studio.desktop",
    "/home/default/Desktop/choreboy_code_studio.desktop",
    "/home/default/FreeCAD/Apps/crud_showcase",
    "/home/default/share/verify-shared",
    "/home/default/share/verify-parent",
    "/home/default/share/verify-no-such-parent",
    "/home/default/share/Chore_Boy/CBCS/cbcs_state_root",
)


class Session:
    def __init__(self, run_id: str, zip_path: str, want: Optional[str], snapshot: bool) -> None:
        self.run_id = run_id
        self.zip_path = str(Path(zip_path).expanduser().resolve()) if zip_path else ""
        self.want = want
        self.snapshot = snapshot
        self.artifacts = ARTIFACT_ROOT / run_id
        self.slot = ""
        self.leased = False
        self.checkpoint_name = "verify-cbcs-" + run_id
        self.slot_snapshot = False
        self.before_hash = ""
        self.after_hash = ""
        self.restored = False
        self.released = False
        self.install_dir = INSTALL_DIR
        self._env_backup: Dict[str, Optional[str]] = {}

    def lease(self) -> str:
        self.slot = self.want or pick_free_slot()
        if not slot_is_free(self.slot):
            raise SystemExit("refusing to lease {}: it is not free".format(self.slot))
        proc = _run(
            [
                "cb-slot", "acquire", "--no-wait", "--export",
                "--want", self.slot,
            ],
            40,
        )
        if proc.returncode != 0:
            raise SystemExit((proc.stdout or "") + (proc.stderr or "") or "acquire failed")
        exports = parse_exports(proc.stdout or "")
        if not exports.get("CB_SLOT_TOKEN"):
            raise SystemExit("acquire did not print CB_SLOT_TOKEN:\n" + (proc.stdout or ""))
        self._apply_exports(exports)
        self.leased = True
        self.artifacts.mkdir(parents=True, exist_ok=True)
        (self.artifacts / "lease.json").write_text(
            json.dumps({"slot": self.slot, "run_id": self.run_id}, indent=2) + "\n",
            encoding="utf-8",
        )
        _ensure_running()
        return self.slot

    def checkpoint(self) -> str:
        if not self.snapshot:
            return "snapshot disabled"
        from scenarios.adapter import Adapter

        adapter = Adapter()
        adapter.probe_slot_snapshot()
        self.slot_snapshot = bool(adapter.caps.slot_snapshot)
        (self.artifacts / "caps-slot.json").write_text(
            json.dumps(adapter.caps.to_dict(), indent=2) + "\n", encoding="utf-8"
        )
        if adapter.caps.slot_snapshot:
            proc = _run(["cb-slot", "checkpoint", "--name", self.checkpoint_name], 180)
            if proc.returncode != 0:
                raise SystemExit("checkpoint failed\n" + (proc.stderr or proc.stdout or ""))
            self.before_hash = "cb-slot:" + self.checkpoint_name
            return self.before_hash
        self.before_hash = self._tar_home("before")
        return self.before_hash

    def install(self) -> None:
        if not self.zip_path or not os.path.isfile(self.zip_path):
            raise SystemExit("zip not found: " + self.zip_path)
        self.guest(ASIDE_SCRIPT)
        proc = _run(
            [
                "cbapp", "install-test", self.zip_path,
                "--extract-parent", INSTALL_PARENT,
                "--extract-dest", INSTALLER_DIR,
                "--installer-entry", "installer/install.py",
                "--password", "rsd",
                "--env", "HOME=/home/default",
                "--name", "verify-cbcs-install",
                "--timeout", "600",
            ],
            700,
        )
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        (self.artifacts / "install.log").write_text(log, encoding="utf-8")
        self._stop_installer(log)
        present = self.guest(INSTALL_PRESENT)
        if "PRESENT" not in present:
            raise SystemExit("install dir missing after install-test:\n" + log[-1500:] + "\n" + present[-1500:])
        if proc.returncode != 0 and "ChoreBoy Code Studio is installed" not in log:
            raise SystemExit("install-test failed\n" + log[-2000:])

    def _stop_installer(self, log: str) -> None:
        for line in log.splitlines():
            if line.startswith("installer session:"):
                sid = line.split(":", 1)[1].strip()
                _run(["cbapp", "stop", sid], 40)
                return

    def revert(self) -> str:
        if self.restored or not self.leased:
            return self.after_hash or "not leased"
        self.restored = True
        if not self.snapshot:
            return "snapshot disabled"
        if not self.before_hash:
            return "no checkpoint"
        if self.before_hash.startswith("cb-slot:"):
            proc = _run(["cb-slot", "revert", "--name", self.checkpoint_name], 240)
            text = (proc.stdout or "") + (proc.stderr or "")
            (self.artifacts / "revert.log").write_text(text, encoding="utf-8")
            if proc.returncode != 0:
                self.restored = False
                raise SystemExit("revert failed\n" + text[-2000:])
            self.after_hash = self.before_hash
            return self.after_hash
        self.after_hash = self._tar_home("restore")
        proof = {
            "before": self.before_hash,
            "after": self.after_hash,
            "match": self.before_hash == self.after_hash,
        }
        (self.artifacts / "restore-proof.json").write_text(
            json.dumps(proof, indent=2) + "\n", encoding="utf-8"
        )
        return self.after_hash

    def release(self) -> None:
        if self.released or not self.leased:
            return
        self.released = True
        proc = _run(["cb-slot", "release"], 40)
        (self.artifacts / "release.log").write_text(
            (proc.stdout or "") + (proc.stderr or ""), encoding="utf-8"
        )
        self._restore_env()
        self.leased = False

    def cleanup(self):
        result = None
        try:
            result = self.revert()
        finally:
            self.release()
        return result

    def guest(self, code: str) -> str:
        probe = Path("/tmp") / ("verify-cbcs-probe-" + uuid.uuid4().hex)
        (probe / "results").mkdir(parents=True)
        (probe / "results" / "keep.txt").write_text("keep\n", encoding="utf-8")
        header = (
            "import os as _cbcs_os\n"
            "_cbcs_os.makedirs(_cbcs_os.path.join(_cbcs_os.path.dirname(_cbcs_os.path.abspath(__file__)), 'results'), exist_ok=True)\n"
        )
        (probe / "run_probe.py").write_text(header + code, encoding="utf-8")
        dest = self.artifacts / ("probe-" + uuid.uuid4().hex[:8])
        proc = _run(
            ["cbprobe", "submit", str(probe), "--wait", "--dest", str(dest), "--timeout", "180"],
            220,
        )
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        report = _find_report(dest)
        report_text = report.read_text(encoding="utf-8", errors="replace") if report else ""
        combined = report_text + "\n" + log
        if proc.returncode != 0 and "SHA256 " not in combined and "PRESENT" not in combined and "aside" not in combined:
            (self.artifacts / "guest-fail.log").write_text(combined, encoding="utf-8")
            raise SystemExit("guest probe failed\n" + combined[-4000:])
        return combined

    def _tar_home(self, phase: str) -> str:
        rel = "verify-cbcs/{}/pre-run.tar.gz".format(self.run_id)
        tar_guest = GUEST_SHARE + "/" + rel
        if phase == "before":
            code = SNAPSHOT_SCRIPT.replace("__TAR__", tar_guest)
        else:
            code = RESTORE_SCRIPT.replace("__TAR__", tar_guest).replace(
                "__TREES__", json.dumps(list(OUR_TREES))
            )
        text = self.guest(code)
        (self.artifacts / "home-{}.log".format(phase)).write_text(text, encoding="utf-8")
        digest = ""
        for line in text.splitlines():
            if line.startswith("SHA256 "):
                digest = line.split(" ", 1)[1].strip()
        if not digest:
            raise SystemExit("home {} did not print SHA256\n".format(phase) + text[-1500:])
        return digest

    def _apply_exports(self, exports: Dict[str, str]) -> None:
        for key, value in exports.items():
            if key not in self._env_backup:
                self._env_backup[key] = os.environ.get(key)
            os.environ[key] = value

    def _restore_env(self) -> None:
        for key, previous in self._env_backup.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        self._env_backup.clear()


def pick_free_slot() -> str:
    free = free_slots()
    for name in FREE_PREFERENCE:
        if name in free:
            return name
    raise SystemExit("no free slot among " + ", ".join(FREE_PREFERENCE))


def free_slots() -> List[str]:
    found = []
    for line in _status_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "free":
            found.append(parts[0])
    return found


def slot_is_free(name: str) -> bool:
    return name in free_slots()


def parse_exports(text: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    for line in text.splitlines():
        raw = line.strip()
        if raw.startswith("export "):
            raw = raw[len("export ") :]
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        if key.startswith("CB") or key.startswith("CHOREBOY"):
            found[key] = _unquote(value.strip())
    return found


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _status_text() -> str:
    proc = _run(["cb-slot", "status"], 20)
    return (proc.stdout or "") + (proc.stderr or "")


def _ensure_running() -> None:
    import time

    proc = _run(["cb-virsh", "status"], 20)
    text = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
    first = text[0].strip().lower() if text else ""
    if first == "running":
        return
    if first in ("shut off", "shutdown"):
        start = _run(["cb-virsh", "start"], 30)
        if start.returncode != 0:
            raise SystemExit("could not start leased domain")
        for _ in range(45):
            time.sleep(2)
            again = _run(["cb-virsh", "status"], 20)
            line = ((again.stdout or "") + (again.stderr or "")).strip().splitlines()
            if line and line[0].strip().lower() == "running":
                time.sleep(45)
                return
        raise SystemExit("leased domain did not reach running")
    raise SystemExit("leased domain is not running: " + (first or "unknown"))


def _run(args: List[str], timeout: int):
    return default_runner(args, timeout)


def _find_report(dest: Path) -> Optional[Path]:
    if not dest.exists():
        return None
    for path in dest.rglob("report.txt"):
        return path
    return None


def now_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return stamp + "-" + uuid.uuid4().hex[:6]


def install_signal_cleanup(session: Session) -> None:
    def _handle(signum, _frame):
        try:
            session.cleanup()
        finally:
            raise SystemExit(128 + int(signum))

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)
