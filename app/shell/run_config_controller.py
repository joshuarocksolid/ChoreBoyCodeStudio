"""Run-configuration CRUD/persistence controller for shell workflows."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.core.errors import AppValidationError, ProjectManifestValidationError
from app.core.models import LoadedProject
from app.project.project_manifest import save_project_manifest
from app.project.run_configs import (
    RunConfiguration,
    parse_env_overrides_text,
    parse_run_config,
    parse_run_configs,
    remove_run_config,
    upsert_run_config,
)


class RunConfigController:
    """Coordinates run-config parsing, mutation, and manifest persistence."""

    def load_configs(self, loaded_project: LoadedProject) -> list[RunConfiguration]:
        return parse_run_configs(loaded_project.metadata.run_configs)

    def build_default_config(self, loaded_project: LoadedProject) -> RunConfiguration:
        return RunConfiguration(
            name="Default",
            entry_file=loaded_project.metadata.default_entry,
            argv=list(loaded_project.metadata.default_argv),
            working_directory=loaded_project.metadata.working_directory,
            env_overrides=dict(loaded_project.metadata.env_overrides),
        )

    def delete_config(
        self,
        *,
        loaded_project: LoadedProject,
        existing_configs: list[RunConfiguration],
        config_name: str,
    ) -> list[RunConfiguration]:
        remaining_configs = remove_run_config(existing_configs, config_name)
        self.persist_run_configs(loaded_project=loaded_project, run_configs=remaining_configs)
        return remaining_configs

    def parse_config_input(
        self,
        *,
        name: str,
        entry_file: str,
        argv_text: str,
        working_directory_text: str,
        env_overrides_text: str,
    ) -> RunConfiguration:
        parsed_env_overrides = parse_env_overrides_text(env_overrides_text)
        return parse_run_config(
            {
                "name": name.strip(),
                "entry_file": entry_file.strip(),
                "argv": [token for token in argv_text.split(" ") if token.strip()],
                "working_directory": working_directory_text.strip() or None,
                "env_overrides": parsed_env_overrides,
            }
        )

    def upsert_config(
        self,
        *,
        loaded_project: LoadedProject,
        existing_configs: list[RunConfiguration],
        updated_config: RunConfiguration,
    ) -> list[RunConfiguration]:
        merged_configs = upsert_run_config(existing_configs, updated_config)
        self.persist_run_configs(loaded_project=loaded_project, run_configs=merged_configs)
        return merged_configs

    def persist_run_configs(self, *, loaded_project: LoadedProject, run_configs: list[RunConfiguration]) -> None:
        manifest_path = Path(loaded_project.manifest_path)
        merged = replace(
            loaded_project.metadata,
            run_configs=[config.to_payload() for config in run_configs],
        )
        try:
            save_project_manifest(manifest_path, merged)
        except (OSError, ProjectManifestValidationError) as exc:
            raise AppValidationError(f"Unable to save run configurations: {exc}") from exc
