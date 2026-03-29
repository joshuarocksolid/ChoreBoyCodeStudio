"""Generic standalone installer for manifest-driven ChoreBoy packages.

This file must remain self-contained because installable packages copy it directly
into the exported artifact and run it through FreeCAD AppRun on the target.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import shutil
import stat
import sys
from pathlib import Path
from typing import Any, Optional

from PySide2.QtCore import Qt, QThread, Signal
from PySide2.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

PACKAGE_MANIFEST_FILENAME = "package_manifest.json"


@dataclass(frozen=True)
class ArtifactChecksum:
    relative_path: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class PackageManifest:
    package_kind: str
    profile: str
    package_id: str
    display_name: str
    version: str
    description: str
    payload_dirname: str
    installer_dirname: str
    readme_filename: str
    install_notes_filename: str
    install_marker_filename: str
    launcher_filename: str
    launcher_name: str
    launcher_comment: str
    launcher_mode: str
    entry_relative_path: str
    icon_relative_path: str
    default_install_base: str
    default_install_dirname: str
    staging_parent: str
    app_run_path: str
    write_menu_entry: bool
    write_desktop_shortcut: bool
    checksums: tuple[ArtifactChecksum, ...]


def _source_root() -> Path:
    return Path(__file__).resolve().parent


def _package_root() -> Path:
    return _source_root().parent


def _payload_root(manifest: PackageManifest) -> Path:
    return _package_root() / manifest.payload_dirname


def load_package_manifest(package_root: Path) -> PackageManifest:
    payload = json.loads((package_root / PACKAGE_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    checksums = tuple(
        ArtifactChecksum(
            relative_path=str(item["relative_path"]),
            sha256=str(item["sha256"]),
            size_bytes=int(item["size_bytes"]),
        )
        for item in payload.get("checksums", [])
    )
    return PackageManifest(
        package_kind=str(payload["package_kind"]),
        profile=str(payload["profile"]),
        package_id=str(payload["package_id"]),
        display_name=str(payload["display_name"]),
        version=str(payload["version"]),
        description=str(payload.get("description", "")),
        payload_dirname=str(payload["payload_dirname"]),
        installer_dirname=str(payload["installer_dirname"]),
        readme_filename=str(payload["readme_filename"]),
        install_notes_filename=str(payload["install_notes_filename"]),
        install_marker_filename=str(payload["install_marker_filename"]),
        launcher_filename=str(payload["launcher_filename"]),
        launcher_name=str(payload["launcher_name"]),
        launcher_comment=str(payload["launcher_comment"]),
        launcher_mode=str(payload["launcher_mode"]),
        entry_relative_path=str(payload["entry_relative_path"]),
        icon_relative_path=str(payload.get("icon_relative_path", "")),
        default_install_base=str(payload.get("default_install_base", str(Path.home()))),
        default_install_dirname=str(payload.get("default_install_dirname", "")),
        staging_parent=str(payload.get("staging_parent", "/home/default")),
        app_run_path=str(payload.get("app_run_path", "/opt/freecad/AppRun")),
        write_menu_entry=bool(payload.get("write_menu_entry", False)),
        write_desktop_shortcut=bool(payload.get("write_desktop_shortcut", True)),
        checksums=checksums,
    )


def build_default_install_dir(manifest: PackageManifest) -> str:
    return str(Path(manifest.default_install_base) / manifest.default_install_dirname)


def build_installed_desktop_entry(install_dir: str | Path, manifest: PackageManifest) -> str:
    resolved_install_dir = str(Path(install_dir).expanduser().resolve())
    icon_line = ""
    if manifest.icon_relative_path:
        icon_line = f"Icon={Path(resolved_install_dir, manifest.icon_relative_path).resolve()}\n"
    bootstrap = (
        "import os,runpy,sys;"
        f"root={resolved_install_dir!r};"
        "sys.path.insert(0, root) if root not in sys.path else None;"
        "os.chdir(root);"
        f"runpy.run_path(os.path.join(root, {manifest.entry_relative_path!r}), run_name='__main__')"
    )
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={manifest.launcher_name}\n"
        f"Comment={manifest.launcher_comment}\n"
        "Terminal=false\n"
        "Categories=Utility;Development;\n"
        f"{icon_line}"
        f'Exec={manifest.app_run_path} -c "{bootstrap}"\n'
    )


def build_staging_location_warning(package_root: Path, manifest: PackageManifest) -> str | None:
    expected_staging_parent = Path(manifest.staging_parent).expanduser().resolve()
    resolved_package_root = package_root.expanduser().resolve()
    try:
        resolved_package_root.relative_to(expected_staging_parent)
    except ValueError:
        return (
            "This installer package is intended to be copied into "
            f"{expected_staging_parent}/ before you run it.\n\n"
            f"Current package folder:\n{resolved_package_root}\n\n"
            "Keep the entire installer folder together in the expected staging directory, "
            "then launch the install desktop file from there."
        )
    return None


def discover_existing_installs(
    *,
    parent_dir: Path,
    manifest: PackageManifest,
    exclude_dir: Path | None = None,
) -> list[dict[str, str]]:
    installs: list[dict[str, str]] = []
    if not parent_dir.exists() or not parent_dir.is_dir():
        return installs
    for child in sorted(parent_dir.iterdir()):
        if exclude_dir is not None and child.resolve() == exclude_dir.resolve():
            continue
        marker_path = child / manifest.install_marker_filename
        if not marker_path.is_file():
            continue
        try:
            payload = json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(payload.get("package_id", "")) != manifest.package_id:
            continue
        installs.append(
            {
                "path": str(child.resolve()),
                "version": str(payload.get("version", "unknown")),
            }
        )
    return installs


def verify_package_checksums(package_root: Path, manifest: PackageManifest) -> None:
    for checksum in manifest.checksums:
        file_path = package_root / checksum.relative_path
        if not file_path.is_file():
            raise ValueError(f"Expected package file is missing: {checksum.relative_path}")
        if file_path.stat().st_size != checksum.size_bytes:
            raise ValueError(f"Package file size changed unexpectedly: {checksum.relative_path}")
        if _compute_sha256(file_path) != checksum.sha256:
            raise ValueError(f"Package checksum mismatch: {checksum.relative_path}")


def write_installed_package_record(install_dir: Path, manifest: PackageManifest) -> None:
    record = {
        "package_id": manifest.package_id,
        "display_name": manifest.display_name,
        "version": manifest.version,
        "package_kind": manifest.package_kind,
        "profile": manifest.profile,
        "install_dir": str(install_dir.resolve()),
        "launcher_filename": manifest.launcher_filename,
    }
    (install_dir / manifest.install_marker_filename).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def publish_launcher_copy(launcher_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination_path = destination_dir / launcher_path.name
    shutil.copy2(str(launcher_path), str(destination_path))
    destination_path.chmod(destination_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return destination_path


class InstallWorker(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(
        self,
        *,
        manifest: PackageManifest,
        install_dir: Path,
        publish_menu_entry: bool,
        publish_desktop_shortcut: bool,
        cleanup_install_dirs: list[Path],
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.install_dir = install_dir
        self.publish_menu_entry = publish_menu_entry
        self.publish_desktop_shortcut = publish_desktop_shortcut
        self.cleanup_install_dirs = cleanup_install_dirs

    def run(self) -> None:
        try:
            self._do_install()
            self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))

    def _do_install(self) -> None:
        package_root = _package_root()
        payload_root = _payload_root(self.manifest)
        if not payload_root.is_dir():
            raise ValueError(f"Payload directory not found: {payload_root}")

        self.status.emit("Verifying package integrity ...")
        self.progress.emit(5)
        verify_package_checksums(package_root, self.manifest)

        if self.install_dir.exists() and self.install_dir.is_file():
            raise ValueError(f"Install path is a file, not a directory: {self.install_dir}")
        self.install_dir.parent.mkdir(parents=True, exist_ok=True)

        stage_dir = self.install_dir.parent / f"{self.install_dir.name}_installing"
        backup_dir = self.install_dir.parent / f"{self.install_dir.name}_backup"
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        stage_dir.mkdir(parents=True, exist_ok=True)

        items = [path for path in sorted(payload_root.rglob("*"))]
        total_items = max(1, len(items))
        for index, path in enumerate(items, start=1):
            rel_path = path.relative_to(payload_root)
            target_path = stage_dir / rel_path
            if path.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(path), str(target_path))
            self.status.emit(f"Copying {rel_path.as_posix()} ...")
            self.progress.emit(10 + int(index / total_items * 70))

        launcher_path = stage_dir / self.manifest.launcher_filename
        launcher_path.write_text(
            build_installed_desktop_entry(stage_dir, self.manifest),
            encoding="utf-8",
        )
        launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        write_installed_package_record(stage_dir, self.manifest)

        self.status.emit("Switching install directory ...")
        self.progress.emit(85)
        previous_install_moved = False
        try:
            if self.install_dir.exists():
                self.install_dir.rename(backup_dir)
                previous_install_moved = True
            stage_dir.rename(self.install_dir)
        except Exception:
            if previous_install_moved and backup_dir.exists() and not self.install_dir.exists():
                backup_dir.rename(self.install_dir)
            raise
        finally:
            if stage_dir.exists():
                shutil.rmtree(stage_dir)

        if backup_dir.exists():
            shutil.rmtree(backup_dir)

        self.status.emit("Publishing launcher shortcuts ...")
        self.progress.emit(92)
        final_launcher_path = self.install_dir / self.manifest.launcher_filename
        if self.publish_menu_entry:
            publish_launcher_copy(
                final_launcher_path,
                Path.home() / ".local" / "share" / "applications",
            )
        if self.publish_desktop_shortcut:
            publish_launcher_copy(
                final_launcher_path,
                Path.home() / "Desktop",
            )

        if self.cleanup_install_dirs:
            self.status.emit("Cleaning older versions ...")
            for cleanup_dir in self.cleanup_install_dirs:
                if cleanup_dir.exists() and cleanup_dir.resolve() != self.install_dir.resolve():
                    shutil.rmtree(cleanup_dir)

        self.progress.emit(100)


class WelcomePage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self.setTitle(f"Welcome to {manifest.display_name} Installer")

        layout = QVBoxLayout(self)
        intro_lines = [
            f"This installer will set up <b>{manifest.display_name}</b> v{manifest.version}.",
            "",
            f"Profile: <code>{manifest.profile}</code>",
            f"Package ID: <code>{manifest.package_id}</code>",
        ]
        if manifest.description:
            intro_lines.extend(["", manifest.description])
        staging_warning = build_staging_location_warning(_package_root(), manifest)
        if staging_warning is not None:
            intro_lines.extend(["", "<b>Current staging warning:</b>", staging_warning.replace("\n", "<br>")])
        intro_lines.extend(
            [
                "",
                "On the next page you will choose the final install folder.",
                "The installed launcher hardcodes that location and can also be published to the application menu or Desktop.",
            ]
        )
        label = QLabel("<br>".join(intro_lines))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label)
        layout.addStretch()


class DirectoryPage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self.setTitle("Choose Installation Directory")
        self.setSubTitle("Select the final location for the installed package.")

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.path_edit = QLineEdit(build_default_install_dir(manifest))
        row.addWidget(self.path_edit)
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._browse)
        row.addWidget(browse_button)
        layout.addLayout(row)
        layout.addStretch()
        self.registerField("install_dir*", self.path_edit)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Installation Directory",
            self._manifest.default_install_base,
        )
        if chosen:
            self.path_edit.setText(str(Path(chosen) / self._manifest.default_install_dirname))

    def validatePage(self) -> bool:
        staging_warning = build_staging_location_warning(_package_root(), self._manifest)
        if staging_warning is not None:
            reply = QMessageBox.question(
                self,
                "Installer Location Warning",
                staging_warning + "\n\nContinue anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
        target = Path(self.path_edit.text().strip()).expanduser()
        if not str(target).strip():
            QMessageBox.warning(self, "Invalid Path", "Please enter an installation directory.")
            return False
        if target.exists() and target.is_file():
            QMessageBox.warning(self, "Invalid Path", f"{target} is a file, not a directory.")
            return False
        return True


class ConfirmPage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self._cleanup_candidates: list[Path] = []
        self.setTitle("Confirm Installation")
        self.setCommitPage(True)
        self.setButtonText(QWizard.CommitButton, "Install")

        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.summary_label)

        self.menu_checkbox = QCheckBox("Create application-menu launcher")
        self.menu_checkbox.setChecked(bool(manifest.write_menu_entry))
        layout.addWidget(self.menu_checkbox)

        self.desktop_checkbox = QCheckBox("Create Desktop shortcut")
        self.desktop_checkbox.setChecked(bool(manifest.write_desktop_shortcut))
        layout.addWidget(self.desktop_checkbox)

        self.cleanup_checkbox = QCheckBox("Remove older installed versions after successful install")
        self.cleanup_checkbox.setVisible(False)
        layout.addWidget(self.cleanup_checkbox)
        layout.addStretch()

        self.registerField("publish_menu_entry", self.menu_checkbox)
        self.registerField("publish_desktop_shortcut", self.desktop_checkbox)
        self.registerField("cleanup_older_versions", self.cleanup_checkbox)

    def initializePage(self) -> None:
        install_dir = Path(str(self.field("install_dir"))).expanduser().resolve()
        self._cleanup_candidates = [
            Path(item["path"])
            for item in discover_existing_installs(
                parent_dir=install_dir.parent,
                manifest=self._manifest,
                exclude_dir=install_dir,
            )
        ]
        existing_text = ""
        if self._cleanup_candidates:
            existing_lines = [f"- {path}" for path in self._cleanup_candidates]
            existing_text = "<br><b>Older installs found:</b><br>" + "<br>".join(existing_lines)
            self.cleanup_checkbox.setVisible(True)
        else:
            self.cleanup_checkbox.setChecked(False)
            self.cleanup_checkbox.setVisible(False)
        launcher_path = install_dir / self._manifest.launcher_filename
        self.summary_label.setText(
            f"<b>Install directory:</b><br><code>{install_dir}</code><br><br>"
            f"<b>Installed launcher:</b><br><code>{launcher_path}</code><br><br>"
            "The installer performs a staged copy before switching the final install directory."
            f"{existing_text}<br><br>"
            "Click <b>Install</b> to begin."
        )

    @property
    def cleanup_candidates(self) -> list[Path]:
        return list(self._cleanup_candidates)


class InstallPage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self.setTitle("Installing...")
        self.setFinalPage(False)

        layout = QVBoxLayout(self)
        self.status_label = QLabel("Preparing...")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)
        layout.addStretch()
        self._complete = False

    def isComplete(self) -> bool:
        return self._complete

    def initializePage(self) -> None:
        confirm_page = self.wizard().page(2)
        cleanup_candidates = confirm_page.cleanup_candidates if isinstance(confirm_page, ConfirmPage) else []
        self.worker = InstallWorker(
            manifest=self._manifest,
            install_dir=Path(str(self.field("install_dir"))).expanduser().resolve(),
            publish_menu_entry=bool(self.field("publish_menu_entry")),
            publish_desktop_shortcut=bool(self.field("publish_desktop_shortcut")),
            cleanup_install_dirs=cleanup_candidates if bool(self.field("cleanup_older_versions")) else [],
        )
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.status.connect(self.status_label.setText)
        self.worker.finished_ok.connect(self._on_success)
        self.worker.finished_err.connect(self._on_error)
        self.worker.start()

    def _on_success(self) -> None:
        self._complete = True
        self.status_label.setText("Installation complete.")
        self.completeChanged.emit()
        self.wizard().next()

    def _on_error(self, message: str) -> None:
        self._complete = True
        self.status_label.setText(f"Error: {message}")
        self.completeChanged.emit()
        QMessageBox.critical(self, "Installation Failed", message)


class DonePage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self.setTitle("Installation Complete")
        self.setFinalPage(True)

        layout = QVBoxLayout(self)
        self.done_label = QLabel()
        self.done_label.setWordWrap(True)
        self.done_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.done_label)
        layout.addStretch()

    def initializePage(self) -> None:
        install_dir = Path(str(self.field("install_dir"))).expanduser().resolve()
        lines = [
            f"<b>{self._manifest.display_name}</b> has been installed to:",
            f"<code>{install_dir}</code>",
            "",
            f"Installed launcher: <code>{install_dir / self._manifest.launcher_filename}</code>",
        ]
        if bool(self.field("publish_menu_entry")):
            lines.extend(["", f"Application menu launcher: <code>{Path.home() / '.local' / 'share' / 'applications' / self._manifest.launcher_filename}</code>"])
        if bool(self.field("publish_desktop_shortcut")):
            lines.extend(["", f"Desktop shortcut: <code>{Path.home() / 'Desktop' / self._manifest.launcher_filename}</code>"])
        lines.extend(
            [
                "",
                "If you later move the installed folder, rerun the installer so the launcher is regenerated.",
            ]
        )
        self.done_label.setText("<br>".join(lines))


class Installer(QWizard):
    def __init__(self, manifest: PackageManifest) -> None:
        super().__init__()
        self.setWindowTitle(f"{manifest.display_name} Installer")
        self.setMinimumSize(620, 420)
        self.setWizardStyle(QWizard.ModernStyle)
        self.addPage(WelcomePage(manifest))
        self.addPage(DirectoryPage(manifest))
        self.addPage(ConfirmPage(manifest))
        self.addPage(InstallPage(manifest))
        self.addPage(DonePage(manifest))


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    app = QApplication(sys.argv)
    package_root = _package_root()
    try:
        manifest = load_package_manifest(package_root)
    except Exception as exc:
        QMessageBox.critical(None, "Installer Error", f"Unable to load package manifest:\n{exc}")
        return 1
    installer = Installer(manifest)
    installer.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
