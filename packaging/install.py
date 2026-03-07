"""ChoreBoy Code Studio Installer.

Self-contained PySide2 GUI installer. Runs on the ChoreBoy target via:
    /opt/freecad/AppRun python3 install.py

Requirements: Python 3.9+, PySide2 (both provided by FreeCAD AppRun).
No imports from the app package -- this file must stand alone.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Optional

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

APP_NAME = "ChoreBoy Code Studio"
APP_RUN_PATH = "/opt/freecad/AppRun"
DEFAULT_INSTALL_DIR = "/home/default/choreboy_code_studio"
DESKTOP_FILENAME = "choreboy_code_studio.desktop"

SKIP_NAMES = {"install.py", "INSTALL.txt"}

DESKTOP_TEMPLATE = """\
[Desktop Entry]
Type=Application
Version=1.0
Name=ChoreBoy Code Studio
Comment=Launch ChoreBoy Code Studio (Qt via FreeCAD AppRun)
Terminal=false
Categories=Utility;Development;
Exec=/opt/freecad/AppRun -c "import os,runpy,sys;root='{install_dir}';sys.path.insert(0,root) if root not in sys.path else None;os.chdir(root);runpy.run_path(os.path.join(root,'run_editor.py'),run_name='__main__')"
"""


def _source_root() -> Path:
    """The directory containing this install.py (the extracted package root)."""
    return Path(__file__).resolve().parent


def _app_version() -> str:
    """Best-effort version extraction from constants.py without importing app."""
    constants_path = _source_root() / "app" / "core" / "constants.py"
    if constants_path.is_file():
        for line in constants_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_VERSION"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip("\"'")
    return "unknown"


# ---------------------------------------------------------------------------
# Worker thread for copying files
# ---------------------------------------------------------------------------

class InstallWorker(QThread):
    """Copies source files to the install directory in a background thread."""

    progress = Signal(int)
    status = Signal(str)
    finished_ok = Signal()
    finished_err = Signal(str)

    def __init__(
        self,
        source_root: Path,
        install_dir: Path,
        add_desktop_shortcut: bool,
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self.source_root = source_root
        self.install_dir = install_dir
        self.add_desktop_shortcut = add_desktop_shortcut

    def run(self) -> None:
        try:
            self._do_install()
            self.finished_ok.emit()
        except Exception as exc:
            self.finished_err.emit(str(exc))

    def _do_install(self) -> None:
        src = self.source_root
        dst = self.install_dir

        items = [
            entry
            for entry in sorted(src.iterdir())
            if entry.name not in SKIP_NAMES
        ]
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
        content = DESKTOP_TEMPLATE.format(install_dir=str(self.install_dir))

        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        apps_desktop = apps_dir / DESKTOP_FILENAME
        apps_desktop.write_text(content, encoding="utf-8")
        apps_desktop.chmod(apps_desktop.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        if self.add_desktop_shortcut:
            desktop_dir = Path.home() / "Desktop"
            if desktop_dir.is_dir():
                desk_file = desktop_dir / DESKTOP_FILENAME
                desk_file.write_text(content, encoding="utf-8")
                desk_file.chmod(
                    desk_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                )


# ---------------------------------------------------------------------------
# Wizard pages
# ---------------------------------------------------------------------------

class WelcomePage(QWizardPage):
    def __init__(self, version: str, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle(f"Welcome to {APP_NAME} Installer")

        layout = QVBoxLayout(self)
        layout.addSpacing(20)
        layout.addWidget(
            QLabel(
                f"This wizard will install <b>{APP_NAME}</b> v{version} "
                "on your ChoreBoy system.\n\n"
                "Click <b>Next</b> to choose an installation directory."
            )
        )
        layout.addStretch()


class DirectoryPage(QWizardPage):
    def __init__(self, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self.setTitle("Choose Installation Directory")
        self.setSubTitle(
            "Select where to install ChoreBoy Code Studio. "
            "The directory will be created if it does not exist."
        )

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.path_edit = QLineEdit(DEFAULT_INSTALL_DIR)
        self.path_edit.setMinimumWidth(350)
        row.addWidget(self.path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        row.addWidget(browse_btn)
        layout.addLayout(row)

        self.desktop_check = QCheckBox("Also add shortcut to Desktop")
        self.desktop_check.setChecked(True)
        layout.addWidget(self.desktop_check)
        layout.addStretch()

        self.registerField("install_dir*", self.path_edit)
        self.registerField("desktop_shortcut", self.desktop_check)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Installation Directory",
            str(Path.home()),
        )
        if chosen:
            chosen_path = Path(chosen) / "choreboy_code_studio"
            self.path_edit.setText(str(chosen_path))

    def validatePage(self) -> bool:
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
        desktop = self.field("desktop_shortcut")
        desktop_text = "Yes" if desktop else "No"
        self.summary_label.setText(
            f"<b>Install directory:</b><br>{install_dir}<br><br>"
            f"<b>Desktop shortcut:</b> {desktop_text}<br><br>"
            f"<b>Menu entry:</b> ~/.local/share/applications/{DESKTOP_FILENAME}<br><br>"
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
        desktop_shortcut = bool(self.field("desktop_shortcut"))

        self.worker = InstallWorker(
            source_root=_source_root(),
            install_dir=install_dir,
            add_desktop_shortcut=desktop_shortcut,
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
            "A launcher entry has been added to your application menu.<br><br>"
            "You can launch it from the application menu or desktop shortcut.<br><br>"
            "Click <b>Finish</b> to close the installer."
        )


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

class InstallerWizard(QWizard):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} Installer")
        self.setMinimumSize(560, 380)
        self.setWizardStyle(QWizard.ModernStyle)

        version = _app_version()
        self.addPage(WelcomePage(version))
        self.addPage(DirectoryPage())
        self.addPage(ConfirmPage())
        self.addPage(InstallPage())
        self.addPage(DonePage())


def main() -> int:
    app = QApplication(sys.argv)
    wizard = InstallerWizard()
    wizard.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
