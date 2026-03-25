"""Wizard UI for project packaging/export."""

from __future__ import annotations

from pathlib import Path

from PySide2.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from app.core.models import ProjectMetadata
from app.packaging.models import (
    PACKAGE_PROFILE_INSTALLABLE,
    PACKAGE_PROFILE_PORTABLE,
    ProjectPackageConfig,
)
from app.shell.file_dialogs import choose_existing_directory, choose_open_file

_PROFILE_DESCRIPTIONS = {
    PACKAGE_PROFILE_INSTALLABLE: (
        "Supported default. Exports a standalone installer folder with checksum verification, "
        "launcher publishing, and upgrade-aware install behavior."
    ),
    PACKAGE_PROFILE_PORTABLE: (
        "Portable launcher profile. Keep the `.desktop` file in the export root beside the packaged files. "
        "Use installable when you want menu integration or the clearest upgrade path."
    ),
}


class PackageProjectWizard(QWizard):
    """Collect package profile, output location, and package metadata."""

    def __init__(
        self,
        *,
        project_root: str,
        project_metadata: ProjectMetadata,
        package_config: ProjectPackageConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project_root = Path(project_root).expanduser().resolve()
        self._project_metadata = project_metadata
        self._initial_config = package_config

        self.setObjectName("shell.packageWizard")
        self.setWindowTitle("Package Project")
        self.setMinimumSize(720, 520)
        self.setWizardStyle(QWizard.ModernStyle)

        self._profile_page = _PackageProfilePage(
            project_root=self._project_root,
            project_metadata=project_metadata,
            initial_config=package_config,
            parent=self,
        )
        self._metadata_page = _PackageMetadataPage(
            project_root=self._project_root,
            project_metadata=project_metadata,
            initial_config=package_config,
            parent=self,
        )
        self.addPage(self._profile_page)
        self.addPage(self._metadata_page)

    @property
    def output_dir(self) -> str:
        return self._profile_page.output_dir()

    @property
    def selected_profile(self) -> str:
        return self._profile_page.selected_profile()

    def build_package_config(self) -> ProjectPackageConfig:
        return self._metadata_page.build_package_config()


class _PackageProfilePage(QWizardPage):
    def __init__(
        self,
        *,
        project_root: Path,
        project_metadata: ProjectMetadata,
        initial_config: ProjectPackageConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._project_metadata = project_metadata
        self._initial_config = initial_config
        self.setTitle("Choose Packaging Profile")
        self.setSubTitle("Select the export style and destination folder.")

        outer = QVBoxLayout(self)
        intro = QLabel(
            "Package Project now exports manifest-driven artifacts. Validation and dependency audit "
            "run after you finish the wizard."
        )
        intro.setWordWrap(True)
        outer.addWidget(intro)

        form_group = QGroupBox("Export Setup", self)
        form = QFormLayout(form_group)
        self._profile_combo = QComboBox(form_group)
        self._profile_combo.addItem("Installable", PACKAGE_PROFILE_INSTALLABLE)
        self._profile_combo.addItem("Portable", PACKAGE_PROFILE_PORTABLE)
        self._profile_combo.currentIndexChanged.connect(self._refresh_profile_description)
        form.addRow("Profile", self._profile_combo)

        output_row = QHBoxLayout()
        self._output_line = QLineEdit(str(Path.home()))
        browse_button = QPushButton("Browse...", form_group)
        browse_button.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self._output_line)
        output_row.addWidget(browse_button)
        form.addRow("Output Folder", output_row)
        outer.addWidget(form_group)

        self._profile_description = QLabel(self)
        self._profile_description.setWordWrap(True)
        outer.addWidget(self._profile_description)
        outer.addStretch()
        self._refresh_profile_description()

    def selected_profile(self) -> str:
        return str(self._profile_combo.currentData())

    def output_dir(self) -> str:
        return self._output_line.text().strip()

    def validatePage(self) -> bool:
        if not self.output_dir():
            QMessageBox.warning(self, "Package Project", "Choose an output folder before continuing.")
            return False
        return True

    def _browse_output_dir(self) -> None:
        selected = choose_existing_directory(self, "Choose Package Output Folder", self.output_dir() or str(Path.home()))
        if selected:
            self._output_line.setText(selected)

    def _refresh_profile_description(self) -> None:
        profile = self.selected_profile()
        self._profile_description.setText(_PROFILE_DESCRIPTIONS.get(profile, ""))


class _PackageMetadataPage(QWizardPage):
    def __init__(
        self,
        *,
        project_root: Path,
        project_metadata: ProjectMetadata,
        initial_config: ProjectPackageConfig,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project_root = project_root
        self._project_metadata = project_metadata
        self._initial_config = initial_config
        self.setTitle("Review Package Metadata")
        self.setSubTitle("These fields are stored in `cbcs/package.json` for future exports.")

        outer = QVBoxLayout(self)
        form_group = QGroupBox("Package Metadata", self)
        form = QFormLayout(form_group)

        self._package_id_line = QLineEdit(initial_config.package_id)
        form.addRow("Package ID", self._package_id_line)

        self._display_name_line = QLineEdit(initial_config.display_name)
        form.addRow("Display Name", self._display_name_line)

        self._version_line = QLineEdit(initial_config.version)
        form.addRow("Version", self._version_line)

        self._entry_line = QLineEdit(
            initial_config.entry_file or project_metadata.default_entry
        )
        form.addRow("Entry File", self._entry_line)

        icon_row = QHBoxLayout()
        self._icon_line = QLineEdit(initial_config.icon_path)
        icon_browse_button = QPushButton("Browse...", form_group)
        icon_browse_button.clicked.connect(self._browse_icon)
        icon_row.addWidget(self._icon_line)
        icon_row.addWidget(icon_browse_button)
        form.addRow("Icon Path", icon_row)

        self._description_edit = QTextEdit(initial_config.description)
        self._description_edit.setMinimumHeight(120)
        form.addRow("Description", self._description_edit)
        outer.addWidget(form_group)

        tip = QLabel(
            "Tip: keep `package_id` stable across releases so installable packages can "
            "offer clearer upgrade and cleanup behavior."
        )
        tip.setWordWrap(True)
        outer.addWidget(tip)
        outer.addStretch()

    def build_package_config(self) -> ProjectPackageConfig:
        return ProjectPackageConfig(
            schema_version=self._initial_config.schema_version,
            package_id=self._package_id_line.text().strip(),
            display_name=self._display_name_line.text().strip(),
            version=self._version_line.text().strip(),
            description=self._description_edit.toPlainText().strip(),
            entry_file=self._entry_line.text().strip(),
            icon_path=self._icon_line.text().strip(),
        )

    def validatePage(self) -> bool:
        if not self._package_id_line.text().strip():
            QMessageBox.warning(self, "Package Project", "Package ID cannot be empty.")
            return False
        if not self._display_name_line.text().strip():
            QMessageBox.warning(self, "Package Project", "Display name cannot be empty.")
            return False
        if not self._version_line.text().strip():
            QMessageBox.warning(self, "Package Project", "Version cannot be empty.")
            return False
        return True

    def _browse_icon(self) -> None:
        selected = choose_open_file(
            self,
            "Choose Package Icon",
            str(self._project_root),
            "Image Files (*.png *.svg *.jpg *.jpeg *.gif *.webp)",
        )
        if not selected:
            return
        selected_path = Path(selected).expanduser().resolve()
        try:
            relative_path = selected_path.relative_to(self._project_root).as_posix()
        except ValueError:
            self._icon_line.setText(str(selected_path))
            return
        self._icon_line.setText(relative_path)
