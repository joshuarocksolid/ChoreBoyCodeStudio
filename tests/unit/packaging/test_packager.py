"""Unit tests for app.packaging.packager."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.packaging.packager import (
    PackageResult,
    _paths_overlap,
    build_desktop_entry,
    package_project,
    sanitize_project_name,
)


class TestSanitizeProjectName:
    def test_lowercase_and_strip_spaces(self) -> None:
        assert sanitize_project_name("My Cool App") == "my_cool_app"

    def test_special_characters_replaced(self) -> None:
        assert sanitize_project_name("app@v2!#test") == "app_v2_test"

    def test_hyphens_and_underscores_preserved(self) -> None:
        assert sanitize_project_name("my-app_v2") == "my-app_v2"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        assert sanitize_project_name("  padded  ") == "padded"

    def test_consecutive_underscores_collapsed(self) -> None:
        assert sanitize_project_name("my   app") == "my_app"

    def test_empty_after_sanitization_returns_fallback(self) -> None:
        assert sanitize_project_name("!!!") == "project"

    def test_dots_replaced(self) -> None:
        assert sanitize_project_name("my.app.v2") == "my_app_v2"


class TestBuildDesktopEntry:
    def test_contains_desktop_entry_header(self) -> None:
        content = build_desktop_entry("myapp", "main.py", "app_files")
        assert "[Desktop Entry]" in content

    def test_type_is_application(self) -> None:
        content = build_desktop_entry("myapp", "main.py", "app_files")
        assert "Type=Application" in content

    def test_name_matches_project(self) -> None:
        content = build_desktop_entry("My App", "main.py", "app_files")
        assert "Name=My App" in content

    def test_terminal_false(self) -> None:
        content = build_desktop_entry("myapp", "main.py", "app_files")
        assert "Terminal=false" in content

    def test_exec_uses_apprun(self) -> None:
        content = build_desktop_entry("myapp", "main.py", "app_files")
        assert "/opt/freecad/AppRun" in content

    def test_exec_contains_entry_file_path(self) -> None:
        content = build_desktop_entry("myapp", "main.py", "app_files")
        assert "os.path.join(root,'app_files/main.py')" in content

    def test_exec_bootstraps_runpy_and_sys_path(self) -> None:
        content = build_desktop_entry("myapp", "main.py", "app_files")
        assert "runpy.run_path" in content
        assert "sys.path.insert(0,root)" in content
        assert "os.chdir(root)" in content

    def test_custom_entry_file(self) -> None:
        content = build_desktop_entry("myapp", "app/run.py", "app_files")
        assert "os.path.join(root,'app_files/app/run.py')" in content

    def test_comment_mentions_project(self) -> None:
        content = build_desktop_entry("Cool Tool", "main.py", "app_files")
        assert "Cool Tool" in content

    def test_exec_uses_desktop_file_location_for_relocation(self) -> None:
        content = build_desktop_entry("Cool Tool", "main.py", "app_files")
        assert "%k" in content
        assert "/home/default" not in content
        assert "/bin/sh" not in content


class TestPackageProject:
    def test_returns_success_result(self, tmp_path: Path) -> None:
        project = tmp_path / "my_project"
        project.mkdir()
        (project / "main.py").write_text("print('hello')\n")
        (project / "cbcs").mkdir()
        (project / "cbcs" / "project.json").write_text("{}")

        result = package_project(
            project_root=str(project),
            project_name="My Project",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        assert isinstance(result, PackageResult)
        assert result.success is True
        assert result.error is None
        assert Path(result.output_path).is_dir()

    def test_folder_contains_desktop_file(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")

        result = package_project(
            project_root=str(project),
            project_name="My Project",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        desktop_path = Path(result.output_path) / "my_project.desktop"
        assert desktop_path.is_file()

    def test_folder_contains_project_subfolder(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")

        result = package_project(
            project_root=str(project),
            project_name="My Project",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        hidden = Path(result.output_path) / "app_files"
        assert hidden.is_dir()

    def test_includes_source_files(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        app_dir = project / "app"
        app_dir.mkdir()
        (app_dir / "widget.py").write_text("class W: pass\n")

        result = package_project(
            project_root=str(project),
            project_name="Test App",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        hidden = Path(result.output_path) / "app_files"
        assert (hidden / "main.py").is_file()
        assert (hidden / "app" / "widget.py").is_file()

    def test_excludes_pycache(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        cache = project / "__pycache__"
        cache.mkdir()
        (cache / "main.cpython-39.pyc").write_bytes(b"\x00")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        hidden = Path(result.output_path) / "app_files"
        assert not (hidden / "__pycache__").exists()

    def test_excludes_cbcs_runs_and_cache(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        cbcs = project / "cbcs"
        cbcs.mkdir()
        (cbcs / "project.json").write_text("{}")
        runs = cbcs / "runs"
        runs.mkdir()
        (runs / "run_001.json").write_text("{}")
        cache_dir = cbcs / "cache"
        cache_dir.mkdir()
        (cache_dir / "index.db").write_bytes(b"\x00")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        hidden = Path(result.output_path) / "app_files"
        assert not (hidden / "cbcs" / "runs").exists()
        assert not (hidden / "cbcs" / "cache").exists()
        assert (hidden / "cbcs" / "project.json").is_file()

    def test_excludes_cbcs_logs_dir(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        logs = project / "cbcs" / "logs"
        logs.mkdir(parents=True)
        (logs / "run.log").write_text("log data")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        hidden = Path(result.output_path) / "app_files"
        assert not (hidden / "cbcs" / "logs").exists()

    def test_excludes_pyc_files(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        (project / "stale.pyc").write_bytes(b"\x00")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        hidden = Path(result.output_path) / "app_files"
        pyc_files = list(hidden.rglob("*.pyc"))
        assert pyc_files == []

    def test_error_on_missing_project_root(self, tmp_path: Path) -> None:
        result = package_project(
            project_root=str(tmp_path / "nonexistent"),
            project_name="ghost",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        assert result.success is False
        assert result.error is not None

    def test_output_dir_created_if_missing(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        out = tmp_path / "deep" / "nested" / "out"

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="main.py",
            output_dir=str(out),
        )
        assert result.success is True
        assert Path(result.output_path).is_dir()

    def test_desktop_entry_content_is_valid(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")

        result = package_project(
            project_root=str(project),
            project_name="Cool Tool",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        desktop_path = Path(result.output_path) / "cool_tool.desktop"
        content = desktop_path.read_text(encoding="utf-8")
        assert "[Desktop Entry]" in content
        assert "Name=Cool Tool" in content
        assert "/opt/freecad/AppRun" in content
        assert "os.path.join(root,'app_files/main.py')" in content

    def test_result_metadata_fields(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")

        result = package_project(
            project_root=str(project),
            project_name="My App",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        assert result.desktop_name == "my_app.desktop"
        assert result.project_folder_name == "app_files"
        assert Path(result.output_path).name == "my_app"

    def test_returns_failure_when_entry_file_missing(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="missing.py",
            output_dir=str(tmp_path / "out"),
        )

        assert result.success is False
        assert result.error == "Entry file not found in project: missing.py"

    def test_returns_failure_when_entry_file_outside_project(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text("print(1)\n")
        outside_entry = tmp_path / "outside.py"
        outside_entry.write_text("print('outside')\n")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file=str(outside_entry),
            output_dir=str(tmp_path / "out"),
        )

        assert result.success is False
        assert result.error == f"Entry file must be inside project root: {outside_entry}"

    def test_returns_failure_when_entry_file_is_excluded_path(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        logs_dir = project / "cbcs" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / "run_entry.py").write_text("print('run')\n")

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="cbcs/logs/run_entry.py",
            output_dir=str(tmp_path / "out"),
        )

        assert result.success is False
        assert result.error == "Entry file resolves to an excluded path and would not be packaged: cbcs/logs/run_entry.py"

    def test_repackage_removes_stale_files(self, tmp_path: Path) -> None:
        project = tmp_path / "proj"
        project.mkdir()
        (project / "a.py").write_text("print('a')\n")
        (project / "b.py").write_text("print('b')\n")
        out = tmp_path / "out"

        package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="a.py",
            output_dir=str(out),
        )
        hidden = out / "proj" / "app_files"
        assert (hidden / "b.py").is_file()

        (project / "b.py").unlink()

        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="a.py",
            output_dir=str(out),
        )
        assert result.success is True
        hidden = Path(result.output_path) / "app_files"
        assert (hidden / "a.py").is_file()
        assert not (hidden / "b.py").exists()


class TestPathsOverlap:
    def test_same_path(self, tmp_path: Path) -> None:
        d = tmp_path / "alpha"
        d.mkdir()
        assert _paths_overlap(d, d) is True

    def test_a_is_parent_of_b(self, tmp_path: Path) -> None:
        parent = tmp_path / "parent"
        child = parent / "child"
        parent.mkdir()
        child.mkdir()
        assert _paths_overlap(parent, child) is True

    def test_b_is_parent_of_a(self, tmp_path: Path) -> None:
        parent = tmp_path / "parent"
        child = parent / "child"
        parent.mkdir()
        child.mkdir()
        assert _paths_overlap(child, parent) is True

    def test_disjoint_paths(self, tmp_path: Path) -> None:
        a = tmp_path / "aaa"
        b = tmp_path / "bbb"
        a.mkdir()
        b.mkdir()
        assert _paths_overlap(a, b) is False

    def test_symlink_resolved_collision(self, tmp_path: Path) -> None:
        real = tmp_path / "real_dir"
        real.mkdir()
        link = tmp_path / "link_dir"
        link.symlink_to(real)
        assert _paths_overlap(real, link) is True


class TestPackageProjectOverlapGuard:
    """Verify that packaging refuses to proceed when output overlaps the project."""

    def _make_project(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / "main.py").write_text("print('hello')\n")
        return path

    def test_same_path_collision(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path / "my_project")
        result = package_project(
            project_root=str(project),
            project_name="my_project",
            entry_file="main.py",
            output_dir=str(tmp_path),
        )
        assert result.success is False
        assert "overlaps" in (result.error or "")
        assert (project / "main.py").is_file(), "project must not be deleted"

    def test_package_inside_project_root(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path / "proj")
        result = package_project(
            project_root=str(project),
            project_name="proj",
            entry_file="main.py",
            output_dir=str(project),
        )
        assert result.success is False
        assert "overlaps" in (result.error or "")

    def test_project_inside_package_dir(self, tmp_path: Path) -> None:
        outer = tmp_path / "outer"
        project = self._make_project(outer / "inner")
        result = package_project(
            project_root=str(project),
            project_name="outer",
            entry_file="main.py",
            output_dir=str(tmp_path),
        )
        assert result.success is False
        assert "overlaps" in (result.error or "")

    def test_symlink_resolved_collision(self, tmp_path: Path) -> None:
        real_project = self._make_project(tmp_path / "real_proj")
        link = tmp_path / "link_proj"
        link.symlink_to(real_project)
        result = package_project(
            project_root=str(link),
            project_name="real_proj",
            entry_file="main.py",
            output_dir=str(tmp_path),
        )
        assert result.success is False
        assert "overlaps" in (result.error or "")
        assert (real_project / "main.py").is_file(), "project must not be deleted"

    def test_non_overlapping_still_succeeds(self, tmp_path: Path) -> None:
        project = self._make_project(tmp_path / "src_project")
        result = package_project(
            project_root=str(project),
            project_name="src_project",
            entry_file="main.py",
            output_dir=str(tmp_path / "out"),
        )
        assert result.success is True
        assert Path(result.output_path).is_dir()
