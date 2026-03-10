"""ChoreBoy Code Studio Installer.

Self-contained PySide2 GUI installer. Runs on the ChoreBoy target via:
    /opt/freecad/AppRun python3 install.py

Requirements: Python 3.9+, PySide2 (both provided by FreeCAD AppRun).
No imports from the app package -- this file must stand alone.
"""

from __future__ import annotations

import shutil
import stat
import sys
from pathlib import Path
from typing import Optional

from PySide2.QtCore import Qt, QThread, Signal
from PySide2.QtWidgets import (
    QApplication,
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

APP_NAME = "ChoreBoy Code Studio"
APP_RUN_PATH = "/opt/freecad/AppRun"
_DEFAULT_INSTALL_BASE = "/home/default"
_DEFAULT_INSTALL_DIRNAME = "choreboy_code_studio"
DESKTOP_FILENAME = "choreboy_code_studio.desktop"
EXPECTED_STAGING_PARENT = Path("/home/default")

PAYLOAD_DIRNAME = "payload"

DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Version=1.0
Name=ChoreBoy Code Studio
Comment=Launch ChoreBoy Code Studio (Qt via FreeCAD AppRun)
Terminal=false
Categories=Utility;Development;
Icon={install_dir}/app/ui/icons/Python_Icon.png

Exec=/opt/freecad/AppRun -c "import os,runpy,sys;root='{install_dir}';sys.path.insert(0,root) if root not in sys.path else None;os.chdir(root);runpy.run_path(os.path.join(root,'run_editor.py'),run_name='__main__')"
"""


def _source_root() -> Path:
    """The directory containing this install.py (the installer/ subdir)."""
    return Path(__file__).resolve().parent


def _package_root() -> Path:
    """The copied installer package root containing installer/ and payload/."""
    return _source_root().parent


def _payload_root() -> Path:
    """The payload/ sibling directory containing the app files to install."""
    return _package_root() / PAYLOAD_DIRNAME


def _app_version() -> str:
    """Best-effort version extraction from constants.py without importing app."""
    constants_path = _payload_root() / "app" / "core" / "constants.py"
    if constants_path.is_file():
        for line in constants_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_VERSION"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip("\"'")
    return "unknown"


def _default_install_dir(version: str) -> str:
    """Build the default install directory path including the version."""
    suffix = "_v" + version if version and version != "unknown" else ""
    return str(Path(_DEFAULT_INSTALL_BASE) / (_DEFAULT_INSTALL_DIRNAME + suffix))


def _install_dirname(version: str) -> str:
    """Build the versioned install folder name for browse dialogs."""
    suffix = "_v" + version if version and version != "unknown" else ""
    return _DEFAULT_INSTALL_DIRNAME + suffix


def build_installed_desktop_entry(install_dir: str | Path) -> str:
    """Return the installed launcher that hardcodes the chosen install path."""
    resolved_install_dir = str(Path(install_dir).expanduser().resolve())
    return DESKTOP_TEMPLATE.format(install_dir=resolved_install_dir)


def build_staging_location_warning(package_root: Path) -> str | None:
    """Return a warning when the installer package is not staged in /home/default."""
    resolved_package_root = package_root.expanduser().resolve()
    try:
        resolved_package_root.relative_to(EXPECTED_STAGING_PARENT)
    except ValueError:
        return (
            "This installer package is intended to be copied into "
            f"{EXPECTED_STAGING_PARENT}/ before you run it.\n\n"
            f"Current package folder:\n{resolved_package_root}\n\n"
            "Keep the entire installer folder together in /home/default/, "
            "then launch install_choreboy_code_studio.desktop from there."
        )
    return None


# ---------------------------------------------------------------------------
# Worker thread for copying files
# ---------------------------------------------------------------------------

class InstallWorker(QThread):
    """Copies payload files to the install directory in a background thread."""

    progress = Signal(int)
    status = Signal(str)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(
        self,
        payload_root: Path,
        install_dir: Path,
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self.payload_root = payload_root
        self.install_dir = install_dir

    def run(self) -> None:
        try:
            self._do_install()
            self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))

    def _do_install(self) -> None:
        src = self.payload_root
        dst = self.install_dir

        if not src.is_dir():
            self.finished_err.emit(
                f"Payload directory not found: {src}\n"
                "Make sure the installer folder sits next to the payload/ folder."
            )
            return

        items = list(sorted(src.iterdir()))
        total = len(items)
        if total == 0:
            self.finished_err.emit("No files found in package directory.")
            return

        dst.mkdir(parents=True, exist_ok=True)

        for idx, entry in enumerate(items):
            self.status.emit(f"Copying {entry.name} ...")
            target = dst / entry.name
            if entry.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(str(entry), str(target))
            else:
                shutil.copy2(str(entry), str(target))
            self.progress.emit(int((idx + 1) / total * 80))

        self.status.emit("Creating .desktop launcher ...")
        self._write_desktop_files()
        self.progress.emit(100)

    def _write_desktop_files(self) -> None:
        content = build_installed_desktop_entry(self.install_dir)

        desktop_file = self.install_dir / DESKTOP_FILENAME
        desktop_file.write_text(content, encoding="utf-8")
        desktop_file.chmod(desktop_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)


# ---------------------------------------------------------------------------
# Installer pages
# ---------------------------------------------------------------------------

class WelcomePage(QWizardPage):
    def __init__(self, version: str, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle(f"Welcome to {APP_NAME} Installer")

        layout = QVBoxLayout(self)
        layout.addSpacing(20)
        package_root = _package_root()
        staging_warning = build_staging_location_warning(package_root)
        intro_lines = [
            f"This installer will set up <b>{APP_NAME}</b> v{version} on your ChoreBoy system.",
            "",
            f"Before running the installer, copy this entire package folder into <code>{EXPECTED_STAGING_PARENT}/</code>.",
            "Keep <code>install_choreboy_code_studio.desktop</code>, <code>installer/</code>, and <code>payload/</code> together.",
            "",
            "On the next page you will choose where the application files should live.",
            "The installed launcher will hardcode that chosen location.",
            "If you move the installed folder later, rerun the installer.",
        ]
        if staging_warning is not None:
            intro_lines.extend(
                [
                    "",
                    "<b>Current staging warning:</b>",
                    staging_warning.replace("\n", "<br>"),
                ]
            )
        intro_lines.extend(["", "Click <b>Next</b> to choose an installation directory."])
        intro_label = QLabel("<br>".join(intro_lines))
        intro_label.setWordWrap(True)
        intro_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(intro_label)
        layout.addStretch()


class DirectoryPage(QWizardPage):
    def __init__(self, version: str, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._version = version
        self.setTitle("Choose Installation Directory")
        self.setSubTitle(
            "Select the final location for the Code Studio files. "
            "The installed launcher will point to this exact directory."
        )

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.path_edit = QLineEdit(_default_install_dir(version))
        self.path_edit.setMinimumWidth(350)
        row.addWidget(self.path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)
        layout.addStretch()

        self.registerField("install_dir", self.path_edit)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Installation Directory",
            str(Path.home()),
        )
        if chosen:
            chosen_path = Path(chosen) / _install_dirname(self._version)
            self.path_edit.setText(str(chosen_path))

    def validatePage(self) -> bool:
        staging_warning = build_staging_location_warning(_package_root())
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
        path_text = self.path_edit.text().strip()
        if not path_text:
            QMessageBox.warning(self, "Invalid Path", "Please enter an installation directory.")
            return False
        target = Path(path_text)
        if target.exists() and any(target.iterdir()):
            reply = QMessageBox.question(
                self,
                "Directory Exists",
                f"The directory\n{target}\nalready contains files.\n\n"
                "Existing files will be overwritten. Continue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return False
        return True


class ConfirmPage(QWizardPage):
    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle("Confirm Installation")
        self.setCommitPage(True)
        self.setButtonText(QWizard.CommitButton, "Install")

        layout = QVBoxLayout(self)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        layout.addStretch()

    def initializePage(self) -> None:
        install_dir = self.field("install_dir")
        self.summary_label.setText(
            f"<b>Install directory:</b><br>{install_dir}<br><br>"
            f"<b>Launcher:</b> {install_dir}/{DESKTOP_FILENAME}<br><br>"
            "The installed launcher will hardcode this install directory.<br><br>"
            "If you later move the installed folder, rerun the installer.<br><br>"
            "Click <b>Install</b> to begin copying files."
        )


class InstallPage(QWizardPage):
    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
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
        self._error: Optional[str] = None

    def isComplete(self) -> bool:
        return self._complete

    def initializePage(self) -> None:
        install_dir = Path(self.field("install_dir"))

        self.worker = InstallWorker(
            payload_root=_payload_root(),
            install_dir=install_dir,
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

    def _on_error(self, msg: str) -> None:
        self._error = msg
        self._complete = True
        self.status_label.setText(f"Error: {msg}")
        self.completeChanged.emit()
        QMessageBox.critical(self, "Installation Failed", msg)


class DonePage(QWizardPage):
    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle("Installation Complete")
        self.setFinalPage(True)

        layout = QVBoxLayout(self)
        self.done_label = QLabel()
        self.done_label.setWordWrap(True)
        self.done_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.done_label)
        layout.addStretch()

    def initializePage(self) -> None:
        install_dir = self.field("install_dir")
        self.done_label.setText(
            f"<b>{APP_NAME}</b> has been installed to:<br>"
            f"<code>{install_dir}</code><br><br>"
            f"A <code>{DESKTOP_FILENAME}</code> launcher has been placed in the install directory.<br><br>"
            "To add it to your desktop or application menu, copy or move the "
            "<code>.desktop</code> file to your preferred location.<br><br>"
            "If you move the installed folder later, rerun the installer so the launcher is regenerated.<br><br>"
            "Click <b>Finish</b> to close the installer."
        )


# ---------------------------------------------------------------------------
# Main installer
# ---------------------------------------------------------------------------

class Installer(QWizard):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Installer")
        self.setMinimumSize(560, 380)
        self.setWizardStyle(QWizard.ModernStyle)

        version = _app_version()
        self.addPage(WelcomePage(version))
        self.addPage(DirectoryPage(version))
        self.addPage(ConfirmPage())
        self.addPage(InstallPage())
        self.addPage(DonePage())


def main() -> int:
    app = QApplication(sys.argv)
    installer = Installer()
    installer.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
