"""Wizard UI for project packaging/export."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ProjectMetadata
from app.packaging.models import (
    PACKAGE_PROFILE_INSTALLABLE,
    ProjectPackageConfig,
)
from app.shell.dialog_chrome import (
    FOOTER_ROLE_PRIMARY,
    FOOTER_ROLE_SECONDARY,
    add_footer_button,
    add_footer_stretch,
    add_meta_chip,
    build_dialog_chrome,
    clear_meta_chips,
)
from app.shell.field_action_button import make_field_action_button
from app.shell.file_dialogs import choose_existing_directory, choose_open_file
from app.shell.run_form_section import build_run_form_section
from app.shell.style_sheet import build_package_wizard_style_sheet
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette
from app.shell.toolbar_icons import icon_package

_DIALOG_OBJECT_NAME = "shell.packageWizardDialog"

_PAGE_HEADERS: tuple[tuple[str, str], ...] = (
    (
        "Choose Package Destination",
        "Select where the installable export should be written.",
    ),
    (
        "Review Package Metadata",
        "These fields are stored in `cbcs/package.json` for future exports.",
    ),
)


class PackageProjectWizard(QDialog):
    """Collect package profile, output location, and package metadata."""

    def __init__(
        self,
        *,
        project_root: str,
        project_metadata: ProjectMetadata,
        package_config: ProjectPackageConfig,
        parent=None,
        tokens: ShellThemeTokens | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_root = Path(project_root).expanduser().resolve()
        self._project_metadata = project_metadata
        self._initial_config = package_config

        self.setObjectName(_DIALOG_OBJECT_NAME)
        self.setWindowTitle("Package Project")
        self.setModal(True)
        self.setMinimumSize(720, 520)
        self.resize(720, 520)

        if tokens is None:
            tokens = tokens_from_palette(self.palette())
        self._tokens = tokens
        self.setStyleSheet(build_package_wizard_style_sheet(tokens))

        self._current_page = 0
        self._step_chip: QLabel | None = None

        chrome = build_dialog_chrome(
            self,
            title=_PAGE_HEADERS[0][0],
            subtitle=_PAGE_HEADERS[0][1],
            object_name=_DIALOG_OBJECT_NAME,
            icon=icon_package(tokens.accent),
        )
        self._chrome = chrome
        self._step_chip = add_meta_chip(chrome.meta_row, "Step 1 of 2")

        body_layout = chrome.body.layout()
        assert isinstance(body_layout, QVBoxLayout)

        self._stack = QStackedWidget(chrome.body)
        self._destination_page = _DestinationPage(
            parent=self._stack,
            on_browse=lambda: self._browse_output_dir(),
        )
        self._metadata_page = _MetadataPage(
            project_root=self._project_root,
            project_metadata=project_metadata,
            initial_config=package_config,
            parent=self._stack,
            on_browse_icon=lambda: self._browse_icon(),
        )
        self._stack.addWidget(self._destination_page.widget)
        self._stack.addWidget(self._metadata_page.widget)
        body_layout.addWidget(self._stack, 1)

        self._back_button = add_footer_button(chrome, "Back", role=FOOTER_ROLE_SECONDARY)
        self._back_button.clicked.connect(self._go_back)
        self._back_button.setVisible(False)

        add_footer_stretch(chrome)
        cancel_button = add_footer_button(chrome, "Cancel", role=FOOTER_ROLE_SECONDARY)
        cancel_button.clicked.connect(self.reject)

        self._next_button = add_footer_button(
            chrome,
            "Next",
            role=FOOTER_ROLE_PRIMARY,
            default=True,
        )
        self._next_button.clicked.connect(self._go_next)

        self._update_page_chrome()

    @property
    def output_dir(self) -> str:
        return self._destination_page.output_dir()

    @property
    def selected_profile(self) -> str:
        return PACKAGE_PROFILE_INSTALLABLE

    def build_package_config(self) -> ProjectPackageConfig:
        return self._metadata_page.build_package_config()

    def _update_page_chrome(self) -> None:
        title, subtitle = _PAGE_HEADERS[self._current_page]
        self._chrome.title_label.setText(title)
        self._chrome.subtitle_label.setText(subtitle)
        self._chrome.subtitle_label.setVisible(bool(subtitle))
        clear_meta_chips(self._chrome.meta_row)
        self._step_chip = add_meta_chip(
            self._chrome.meta_row,
            f"Step {self._current_page + 1} of {len(_PAGE_HEADERS)}",
        )
        self._back_button.setVisible(self._current_page > 0)
        self._next_button.setText("Package" if self._current_page == len(_PAGE_HEADERS) - 1 else "Next")
        self._stack.setCurrentIndex(self._current_page)

    def _validate_current_page(self) -> bool:
        if self._current_page == 0:
            if not self._destination_page.output_dir():
                QMessageBox.warning(
                    self,
                    "Package Project",
                    "Choose an output folder before continuing.",
                )
                return False
            return True
        if not self._metadata_page.validate_fields(self):
            return False
        return True

    def _go_back(self) -> None:
        if self._current_page <= 0:
            return
        self._current_page -= 1
        self._update_page_chrome()

    def _go_next(self) -> None:
        if not self._validate_current_page():
            return
        if self._current_page >= len(_PAGE_HEADERS) - 1:
            self.accept()
            return
        self._current_page += 1
        self._update_page_chrome()

    def _browse_output_dir(self) -> None:
        selected = choose_existing_directory(
            self,
            "Choose Package Output Folder",
            self._destination_page.output_dir() or str(Path.home()),
        )
        if selected:
            self._destination_page.set_output_dir(selected)

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
            self._metadata_page.set_icon_path(str(selected_path))
            return
        self._metadata_page.set_icon_path(relative_path)


class _DestinationPage:
    """First wizard page: output folder selection."""

    def __init__(self, *, parent: QWidget, on_browse: Callable[[], None]) -> None:
        self.widget = QWidget(parent)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        intro = QLabel(
            "Package Project exports installable, manifest-driven artifacts. Validation and dependency audit "
            "run after you finish the wizard.",
            self.widget,
        )
        intro.setWordWrap(True)
        intro.setProperty("previewLabel", True)
        outer.addWidget(intro)

        export_section, export_layout = build_run_form_section(self.widget, "Export Setup")
        export_form = QWidget(export_section)
        form = QFormLayout(export_form)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        output_row = QWidget(export_form)
        output_row_layout = QHBoxLayout(output_row)
        output_row_layout.setContentsMargins(0, 0, 0, 0)
        output_row_layout.setSpacing(8)
        self._output_line = QLineEdit(str(Path.home()), output_row)
        browse_button = make_field_action_button("Browse\u2026", output_row)
        browse_button.clicked.connect(on_browse)
        output_row_layout.addWidget(self._output_line, 1)
        output_row_layout.addWidget(browse_button, 0)
        form.addRow("Output Folder:", output_row)
        export_layout.addWidget(export_form)
        outer.addWidget(export_section)

        profile_description = QLabel(
            "Installable exports include a checksum-verified installer, Desktop shortcut publishing, "
            "and upgrade-aware install behavior.",
            self.widget,
        )
        profile_description.setWordWrap(True)
        profile_description.setProperty("previewLabel", True)
        outer.addWidget(profile_description)
        outer.addStretch(1)

    def output_dir(self) -> str:
        return self._output_line.text().strip()

    def set_output_dir(self, path: str) -> None:
        self._output_line.setText(path)


class _MetadataPage:
    """Second wizard page: package metadata fields."""

    def __init__(
        self,
        *,
        project_root: Path,
        project_metadata: ProjectMetadata,
        initial_config: ProjectPackageConfig,
        parent: QWidget,
        on_browse_icon: Callable[[], None],
    ) -> None:
        self._project_root = project_root
        self._initial_config = initial_config

        self.widget = QWidget(parent)
        outer = QVBoxLayout(self.widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)

        metadata_section, metadata_layout = build_run_form_section(self.widget, "Package Metadata")
        metadata_form = QWidget(metadata_section)
        form = QFormLayout(metadata_form)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._package_id_line = QLineEdit(initial_config.package_id, metadata_form)
        form.addRow("Package ID:", self._package_id_line)

        self._display_name_line = QLineEdit(initial_config.display_name, metadata_form)
        form.addRow("Display Name:", self._display_name_line)

        self._version_line = QLineEdit(initial_config.version, metadata_form)
        form.addRow("Version:", self._version_line)

        self._entry_line = QLineEdit(
            initial_config.entry_file or project_metadata.default_entry,
            metadata_form,
        )
        form.addRow("Entry File:", self._entry_line)

        icon_row = QWidget(metadata_form)
        icon_row_layout = QHBoxLayout(icon_row)
        icon_row_layout.setContentsMargins(0, 0, 0, 0)
        icon_row_layout.setSpacing(8)
        self._icon_line = QLineEdit(initial_config.icon_path, icon_row)
        icon_browse_button = make_field_action_button("Browse\u2026", icon_row)
        icon_browse_button.clicked.connect(on_browse_icon)
        icon_row_layout.addWidget(self._icon_line, 1)
        icon_row_layout.addWidget(icon_browse_button, 0)
        form.addRow("Icon Path:", icon_row)

        self._description_edit = QTextEdit(initial_config.description, metadata_form)
        self._description_edit.setMinimumHeight(120)
        form.addRow("Description:", self._description_edit)
        metadata_layout.addWidget(metadata_form)
        outer.addWidget(metadata_section)

        tip = QLabel(
            "Tip: keep `package_id` stable across releases so installable packages can "
            "offer clearer upgrade and cleanup behavior.",
            self.widget,
        )
        tip.setWordWrap(True)
        tip.setProperty("previewLabel", True)
        outer.addWidget(tip)
        outer.addStretch(1)

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

    def set_icon_path(self, path: str) -> None:
        self._icon_line.setText(path)

    def validate_fields(self, parent: QWidget) -> bool:
        if not self._package_id_line.text().strip():
            QMessageBox.warning(parent, "Package Project", "Package ID cannot be empty.")
            return False
        if not self._display_name_line.text().strip():
            QMessageBox.warning(parent, "Package Project", "Display name cannot be empty.")
            return False
        if not self._version_line.text().strip():
            QMessageBox.warning(parent, "Package Project", "Version cannot be empty.")
            return False
        return True
