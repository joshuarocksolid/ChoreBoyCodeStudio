"""Unit tests for plugin package staging helpers."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from app.core.errors import AppValidationError
from app.plugins.package_format import stage_plugin_source

pytestmark = pytest.mark.unit


def test_stage_plugin_source_rejects_zip_members_outside_staging_root(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe_plugin.zip"
    with zipfile.ZipFile(str(archive_path), "w") as archive:
        archive.writestr("../escape.py", "print('escape')\n")
        archive.writestr("plugin/plugin.json", "{}\n")

    with pytest.raises(AppValidationError, match="Unsafe archive member"):
        stage_plugin_source(archive_path)

    assert not (tmp_path / "escape.py").exists()
