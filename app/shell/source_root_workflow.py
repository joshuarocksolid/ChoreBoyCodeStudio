"""Mark/unmark project source roots without a full plugin reindex."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from PySide2.QtWidgets import QMessageBox, QWidget

from app.core.errors import ProjectManifestValidationError
from app.core.models import LoadedProject
from app.project.import_layout import detect_suggested_source_root
from app.project.project_manifest import append_project_source_root, remove_project_source_root
from app.shell.project_rescan_workflow import MainWindowProjectRescanHost, ProjectRescanWorkflow


class SourceRootWorkflow:
    """Source-root manifest edits and optional first-open prompt."""

    def __init__(
        self,
        *,
        parent_widget: QWidget,
        loaded_project: Callable[[], LoadedProject | None],
        set_loaded_project: Callable[[LoadedProject], None],
        rescan_workflow: ProjectRescanWorkflow,
    ) -> None:
        self._parent = parent_widget
        self._loaded_project = loaded_project
        self._set_loaded_project = set_loaded_project
        self._rescan = rescan_workflow

    def mark_source_root(self, relative_path: str) -> None:
        loaded_project = self._loaded_project()
        if loaded_project is None:
            return
        try:
            updated_metadata = append_project_source_root(
                loaded_project.manifest_path,
                relative_path,
                metadata_if_absent=None
                if loaded_project.manifest_materialized
                else loaded_project.metadata,
            )
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(self._parent, "Sources Root", str(exc))
            return
        self._set_loaded_project(
            replace(loaded_project, metadata=updated_metadata, manifest_materialized=True)
        )
        self._rescan.rescan_from_disk(reload_plugins=False, reindex=False)

    def unmark_source_root(self, relative_path: str) -> None:
        loaded_project = self._loaded_project()
        if loaded_project is None:
            return
        try:
            updated_metadata = remove_project_source_root(loaded_project.manifest_path, relative_path)
        except (ProjectManifestValidationError, ValueError) as exc:
            QMessageBox.warning(self._parent, "Sources Root", str(exc))
            return
        self._set_loaded_project(replace(loaded_project, metadata=updated_metadata))
        self._rescan.rescan_from_disk(reload_plugins=False, reindex=False)

    def maybe_prompt_import_source_roots(self) -> None:
        loaded_project = self._loaded_project()
        if loaded_project is None or loaded_project.metadata.source_roots:
            return
        suggested = detect_suggested_source_root(loaded_project.project_root)
        if suggested is None:
            return
        confirm = QMessageBox.question(
            self._parent,
            "Import Roots",
            (
                f"This project looks like it uses a `{suggested}/` layout. "
                f"Mark `{suggested}` as a source root so local imports resolve correctly?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if confirm != QMessageBox.Yes:
            return
        self.mark_source_root(suggested)


def build_source_root_workflow(window: Any) -> SourceRootWorkflow:
    rescan = ProjectRescanWorkflow(MainWindowProjectRescanHost(window))
    return SourceRootWorkflow(
        parent_widget=window,
        loaded_project=lambda: window._loaded_project,
        set_loaded_project=lambda project: setattr(window, "_loaded_project", project),
        rescan_workflow=rescan,
    )
