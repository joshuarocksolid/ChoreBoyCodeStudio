"""Generic standalone installer for manifest-driven ChoreBoy packages.

This file must remain self-contained because installable packages copy it directly
into the exported artifact and run it through FreeCAD AppRun on the target.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
import shutil
import stat
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from PySide2.QtCore import Qt, QThread, Signal
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

PACKAGE_MANIFEST_FILENAME = "package_manifest.json"
CBCS_PACKAGE_ROOT_ENV = "CBCS_PACKAGE_ROOT"

SLOT_EMPTY = "empty"
SLOT_SAME_PACKAGE = "same_package"
SLOT_FOREIGN_PACKAGE = "foreign_package"
SLOT_UNMARKED = "unmarked"

SLOT_ACTION_CONTINUE = "continue"
SLOT_ACTION_CONFIRM_REPLACE = "confirm_replace"
SLOT_ACTION_REFUSE = "refuse"

LEGACY_MACRO_APPS_BASE = "~/.local/share/FreeCAD/Macro/Apps"


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
    ask_install_location: bool = False


@dataclass(frozen=True)
class SlotOccupancy:
    kind: str
    path: str
    occupant_package_id: str = ""
    occupant_version: str = ""


@dataclass(frozen=True)
class ShortcutPublishResult:
    ok: bool
    path: str
    error: str = ""


@dataclass(frozen=True)
class InstallOutcome:
    ok: bool
    install_dir: str
    warnings: tuple[str, ...] = ()
    error: str = ""
    unchanged: bool = False
    published_paths: tuple[str, ...] = ()
    replaced_version: str = ""


@dataclass(frozen=True)
class UninstallOutcome:
    removed_paths: tuple[str, ...]
    kept_data_dir: str = ""


def _home_roots_for_manifest(manifest: PackageManifest) -> list[Path]:
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in (Path(manifest.staging_parent), Path.home()):
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        roots.append(candidate)
    return roots


def _default_legacy_bases() -> list[Path]:
    bases = [
        Path(LEGACY_MACRO_APPS_BASE).expanduser(),
        Path("/home/default/.local/share/FreeCAD/Macro/Apps"),
    ]
    unique: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        key = str(base)
        if key in seen:
            continue
        seen.add(key)
        unique.append(base)
    return unique


def _source_root() -> Path:
    return Path(__file__).resolve().parent


def _package_root() -> Path:
    env_root = os.environ.get(CBCS_PACKAGE_ROOT_ENV, "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    return _source_root().parent


def _payload_root(manifest: PackageManifest) -> Path:
    return _package_root() / manifest.payload_dirname


def _load_launcher_bootstrap() -> Any:
    try:
        from app.packaging import launcher_bootstrap

        return launcher_bootstrap
    except Exception:
        helper_path = _source_root() / "launcher_bootstrap.py"
        if not helper_path.is_file():
            raise RuntimeError(
                "Installer helper is missing: installer/launcher_bootstrap.py. "
                "Keep the entire installer package together and rerun the installer launcher."
            )
        spec = importlib.util.spec_from_file_location("cbcs_installer_launcher_bootstrap", helper_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load installer helper: {helper_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


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
        ask_install_location=_parse_ask_install_location(payload),
    )


def _parse_ask_install_location(payload: dict[str, Any]) -> bool:
    if "ask_install_location" not in payload:
        return False
    ask_install_location = payload["ask_install_location"]
    if not isinstance(ask_install_location, bool):
        raise ValueError("ask_install_location must be a boolean.")
    return ask_install_location


def is_silent_apps_install(manifest: PackageManifest) -> bool:
    return manifest.package_kind == "project" and not manifest.ask_install_location


def resolve_silent_install_dir(manifest: PackageManifest) -> Path:
    return Path(manifest.default_install_base).expanduser() / manifest.default_install_dirname


def build_default_install_dir(manifest: PackageManifest) -> str:
    return str(resolve_silent_install_dir(manifest))


def classify_install_slot(
    path: str | Path,
    *,
    package_id: str,
    marker_filename: str,
) -> SlotOccupancy:
    target = Path(path).expanduser()
    target_str = str(target)
    if not target.exists():
        return SlotOccupancy(kind=SLOT_EMPTY, path=target_str)
    if not target.is_dir():
        return SlotOccupancy(kind=SLOT_UNMARKED, path=target_str)
    try:
        next(target.iterdir())
    except StopIteration:
        return SlotOccupancy(kind=SLOT_EMPTY, path=target_str)
    marker_path = target / marker_filename
    if not marker_path.is_file():
        return SlotOccupancy(kind=SLOT_UNMARKED, path=target_str)
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return SlotOccupancy(kind=SLOT_UNMARKED, path=target_str)
    if not isinstance(payload, dict):
        return SlotOccupancy(kind=SLOT_UNMARKED, path=target_str)
    occupant_id = payload.get("package_id")
    occupant_version = payload.get("version", "")
    if not isinstance(occupant_id, str) or not occupant_id.strip():
        return SlotOccupancy(kind=SLOT_UNMARKED, path=target_str)
    occupant_id = occupant_id.strip()
    version_text = occupant_version.strip() if isinstance(occupant_version, str) else ""
    if occupant_id == package_id:
        return SlotOccupancy(
            kind=SLOT_SAME_PACKAGE,
            path=target_str,
            occupant_package_id=occupant_id,
            occupant_version=version_text,
        )
    return SlotOccupancy(
        kind=SLOT_FOREIGN_PACKAGE,
        path=target_str,
        occupant_package_id=occupant_id,
        occupant_version=version_text,
    )


def install_slot_decision(occupancy: SlotOccupancy) -> str:
    if occupancy.kind == SLOT_EMPTY:
        return SLOT_ACTION_CONTINUE
    if occupancy.kind == SLOT_SAME_PACKAGE:
        return SLOT_ACTION_CONFIRM_REPLACE
    return SLOT_ACTION_REFUSE


def slot_refusal_message(occupancy: SlotOccupancy) -> str:
    if occupancy.kind == SLOT_FOREIGN_PACKAGE:
        occupant = occupancy.occupant_package_id or "another package"
        return (
            f"The folder {occupancy.path} already belongs to package {occupant}. "
            "The installer will not overwrite it."
        )
    if occupancy.kind == SLOT_UNMARKED:
        return (
            f"The folder {occupancy.path} already contains files that are not "
            "a ChoreBoy packaged app. The installer will not overwrite it."
        )
    return ""


def ensure_install_parent(target: Path) -> Path:
    parent = Path(target).expanduser().parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(
            f"Could not create the install folder parent: {parent}. {exc}"
        ) from exc
    return parent


def build_installed_desktop_entry(install_dir: str | Path, manifest: PackageManifest) -> str:
    resolved_install_dir = str(Path(install_dir).expanduser().resolve())
    icon_line = ""
    if manifest.icon_relative_path:
        icon_line = f"Icon={Path(resolved_install_dir, manifest.icon_relative_path).resolve()}\n"
    bootstrap = _load_launcher_bootstrap().build_fixed_root_bootstrap(
        resolved_install_dir,
        manifest.entry_relative_path,
    )
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={manifest.launcher_name}\n"
        f"Comment={manifest.launcher_comment}\n"
        "Terminal=false\n"
        "Categories=Utility;Development;\n"
        "StartupNotify=true\n"
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


def write_installed_package_record(
    install_dir: Path,
    manifest: PackageManifest,
    *,
    owned_relative_paths: tuple[str, ...] = (),
    published_launcher_paths: tuple[str, ...] = (),
    icon_path: str = "",
) -> None:
    record = {
        "package_id": manifest.package_id,
        "display_name": manifest.display_name,
        "version": manifest.version,
        "package_kind": manifest.package_kind,
        "profile": manifest.profile,
        "install_dir": str(install_dir.resolve()),
        "launcher_filename": manifest.launcher_filename,
        "owned_relative_paths": list(owned_relative_paths),
        "published_launcher_paths": list(published_launcher_paths),
        "icon_path": icon_path,
    }
    (install_dir / manifest.install_marker_filename).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_installed_marker(install_dir: Path, marker_filename: str) -> dict[str, Any]:
    marker_path = Path(install_dir) / marker_filename
    if not marker_path.is_file():
        return {}
    try:
        payload = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def version_relation(installed: str, incoming: str) -> str:
    """Return same, older, or newer for the incoming installer version."""
    left = _version_key(installed)
    right = _version_key(incoming)
    width = max(len(left), len(right))
    left = left + (0,) * (width - len(left))
    right = right + (0,) * (width - len(right))
    if left == right:
        return "same"
    if right < left:
        return "older"
    return "newer"


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def replace_action_label(installed_version: str, incoming_version: str) -> str:
    if version_relation(installed_version, incoming_version) == "same":
        return "Reinstall"
    return "Replace"


def discover_same_package_slots(
    base: Path,
    *,
    package_id: str,
    marker_filename: str,
) -> list[Path]:
    root = Path(base).expanduser()
    if not root.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(root.iterdir()):
        occupancy = classify_install_slot(
            child,
            package_id=package_id,
            marker_filename=marker_filename,
        )
        if occupancy.kind == SLOT_SAME_PACKAGE:
            found.append(child)
    return found


def iter_launcher_destinations(home_root: Path) -> list[tuple[str, Path]]:
    """Home copy, Desktop when that folder already exists, and the applications menu."""
    destinations = [("home", Path(home_root))]
    desktop = Path(home_root) / "Desktop"
    if desktop.is_dir():
        destinations.append(("desktop", desktop))
    destinations.append(("menu", Path(home_root) / ".local" / "share" / "applications"))
    return destinations


def publish_home_launchers(
    launcher_text: str,
    launcher_filename: str,
    *,
    home_roots: list[Path],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Write launcher copies. Failures become warnings and do not raise."""
    published: list[str] = []
    warnings: list[str] = []
    for home_root in home_roots:
        for kind, directory in iter_launcher_destinations(home_root):
            destination = directory / launcher_filename
            try:
                if kind != "desktop":
                    directory.mkdir(parents=True, exist_ok=True)
                destination.write_text(launcher_text, encoding="utf-8")
                destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except OSError as exc:
                warnings.append(
                    f"Could not write the {kind} launcher at {destination}: {exc.__class__.__name__}: {exc}"
                )
            else:
                published.append(str(destination))
    return tuple(published), tuple(warnings)


def launcher_removal_paths(
    marker: dict[str, Any],
    *,
    home_roots: list[Path],
) -> list[Path]:
    paths: list[Path] = []
    for item in marker.get("published_launcher_paths") or []:
        if isinstance(item, str) and item.strip():
            paths.append(Path(item))
    launcher_filename = marker.get("launcher_filename")
    if isinstance(launcher_filename, str) and launcher_filename.strip():
        for home_root in home_roots:
            for _kind, directory in iter_launcher_destinations(home_root):
                paths.append(directory / launcher_filename)
            paths.append(Path(home_root) / "Desktop" / launcher_filename)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _relative_files(root: Path) -> list[str]:
    files: list[str] = []
    if not root.is_dir():
        return files
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return files


def _copy_tree_files(source: Path, destination: Path) -> list[str]:
    copied: list[str] = []
    for path in sorted(source.rglob("*")):
        rel = path.relative_to(source)
        target = destination / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(target))
        copied.append(rel.as_posix())
    return copied


def _preserved_relative_paths(
    install_dir: Path,
    *,
    previous_owned: set[str],
    new_payload: set[str],
    skip: set[str] | None = None,
) -> list[str]:
    skipped = skip or set()
    preserved: list[str] = []
    for rel in _relative_files(install_dir):
        if rel in new_payload or rel in skipped:
            continue
        if previous_owned and rel in previous_owned:
            continue
        preserved.append(rel)
    return preserved


def perform_install(
    *,
    manifest: PackageManifest,
    package_root: Path,
    install_dir: Path,
    home_roots: list[Path],
    legacy_bases: list[Path] | None = None,
) -> InstallOutcome:
    """Copy the payload, keep files the payload does not own, then publish launchers."""
    payload_root = package_root / manifest.payload_dirname
    if not payload_root.is_dir():
        return InstallOutcome(
            ok=False,
            install_dir=str(install_dir),
            error=f"Payload directory not found: {payload_root}",
            unchanged=True,
        )
    try:
        verify_package_checksums(package_root, manifest)
        ensure_install_parent(install_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        return InstallOutcome(ok=False, install_dir=str(install_dir), error=str(exc), unchanged=True)

    stage_dir = install_dir.parent / f"{install_dir.name}_installing"
    backup_dir = install_dir.parent / f"{install_dir.name}_backup"
    if not install_dir.exists() and backup_dir.exists():
        backup_dir.rename(install_dir)
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    if backup_dir.exists() and install_dir.exists():
        shutil.rmtree(backup_dir)

    previous = read_installed_marker(install_dir, manifest.install_marker_filename)
    previous_owned = {
        str(item)
        for item in previous.get("owned_relative_paths", [])
        if isinstance(item, str)
    }
    replaced_version = str(previous.get("version", "")) if previous.get("package_id") == manifest.package_id else ""
    new_payload = set(_relative_files(payload_root))
    skip_names = {manifest.install_marker_filename, manifest.launcher_filename}
    preserved = _preserved_relative_paths(
        install_dir,
        previous_owned=previous_owned,
        new_payload=new_payload,
        skip=skip_names,
    )
    legacy_slots = _legacy_slots(manifest, install_dir, legacy_bases or [])
    for slot in legacy_slots:
        legacy_marker = read_installed_marker(slot, manifest.install_marker_filename)
        legacy_launcher = legacy_marker.get("launcher_filename")
        slot_skip = set(skip_names)
        if isinstance(legacy_launcher, str) and legacy_launcher.strip():
            slot_skip.add(legacy_launcher)
        preserved.extend(
            _preserved_relative_paths(
                slot,
                previous_owned=set(),
                new_payload=new_payload | set(preserved),
                skip=slot_skip,
            )
        )

    stage_dir.mkdir(parents=True, exist_ok=True)
    copied = _copy_tree_files(payload_root, stage_dir)
    for rel in preserved:
        source = _find_preserved_source(rel, install_dir, legacy_slots)
        if source is None:
            continue
        target = stage_dir / rel
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source), str(target))

    icon_path = ""
    if manifest.icon_relative_path:
        icon_file = stage_dir / manifest.icon_relative_path
        if icon_file.is_file():
            icon_path = str((install_dir / manifest.icon_relative_path).resolve())
    launcher_path = stage_dir / manifest.launcher_filename
    launcher_path.write_text(build_installed_desktop_entry(install_dir, manifest), encoding="utf-8")
    launcher_path.chmod(launcher_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    owned = tuple(sorted(set(copied) | {manifest.launcher_filename, manifest.install_marker_filename}))
    write_installed_package_record(
        stage_dir,
        manifest,
        owned_relative_paths=owned,
        icon_path=icon_path,
    )

    previous_existed = install_dir.exists()
    try:
        if install_dir.exists():
            install_dir.rename(backup_dir)
        stage_dir.rename(install_dir)
    except OSError as exc:
        if previous_existed and backup_dir.exists() and not install_dir.exists():
            backup_dir.rename(install_dir)
        if stage_dir.exists():
            shutil.rmtree(stage_dir)
        return InstallOutcome(
            ok=False,
            install_dir=str(install_dir),
            error=f"Could not switch the install folder into place: {exc}",
            unchanged=True,
        )
    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    warnings_after: list[str] = []
    for slot in legacy_slots:
        marker = read_installed_marker(slot, manifest.install_marker_filename)
        for path in launcher_removal_paths(marker, home_roots=home_roots):
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        if slot.exists():
            try:
                shutil.rmtree(slot)
            except OSError as exc:
                warnings_after.append(
                    f"Could not remove the old install folder at {slot}: {exc.__class__.__name__}: {exc}"
                )

    published, warnings = publish_home_launchers(
        (install_dir / manifest.launcher_filename).read_text(encoding="utf-8"),
        manifest.launcher_filename,
        home_roots=home_roots,
    )
    warnings = warnings + tuple(warnings_after)
    try:
        write_installed_package_record(
            install_dir,
            manifest,
            owned_relative_paths=owned,
            published_launcher_paths=published,
            icon_path=icon_path,
        )
    except OSError as exc:
        warnings = warnings + (
            f"Could not record the published shortcuts in {manifest.install_marker_filename}: {exc.__class__.__name__}: {exc}",
        )
    return InstallOutcome(
        ok=True,
        install_dir=str(install_dir.resolve()),
        warnings=warnings,
        published_paths=published,
        replaced_version=replaced_version,
    )


def uninstall_installed_package(
    install_dir: Path,
    *,
    marker_filename: str,
    delete_data: bool,
    home_roots: list[Path],
) -> UninstallOutcome:
    """Remove payload-owned files, launchers, and the icon. Keep other files unless asked."""
    marker = read_installed_marker(install_dir, marker_filename)
    removed: list[str] = []
    icon_path = marker.get("icon_path")
    if isinstance(icon_path, str) and icon_path.strip():
        icon = Path(icon_path)
        if icon.is_file():
            icon.unlink()
            removed.append(str(icon))
    for path in launcher_removal_paths(marker, home_roots=home_roots):
        if path.is_file():
            path.unlink()
            removed.append(str(path))
    kept = ""
    if delete_data:
        if install_dir.exists():
            shutil.rmtree(install_dir)
            removed.append(str(install_dir))
    else:
        owned = [str(item) for item in marker.get("owned_relative_paths", []) if isinstance(item, str)]
        for rel in owned:
            target = install_dir / rel
            if target.is_file():
                target.unlink()
                removed.append(str(target))
        _remove_empty_owned_dirs(install_dir, owned)
        if install_dir.exists():
            kept = str(install_dir.resolve())
    return UninstallOutcome(removed_paths=tuple(removed), kept_data_dir=kept)


def _remove_empty_owned_dirs(install_dir: Path, owned: list[str]) -> None:
    parents = {str(Path(rel).parent) for rel in owned if Path(rel).parent != Path(".")}
    for rel in sorted(parents, key=lambda item: item.count("/"), reverse=True):
        directory = install_dir / rel
        if not directory.is_dir():
            continue
        if any(directory.iterdir()):
            continue
        directory.rmdir()


def _legacy_slots(
    manifest: PackageManifest,
    install_dir: Path,
    legacy_bases: list[Path],
) -> list[Path]:
    slots: list[Path] = []
    seen: set[str] = set()
    try:
        install_key = str(install_dir.resolve())
    except OSError:
        install_key = str(install_dir)
    for base in legacy_bases:
        for slot in discover_same_package_slots(
            base,
            package_id=manifest.package_id,
            marker_filename=manifest.install_marker_filename,
        ):
            try:
                key = str(slot.resolve())
            except OSError:
                key = str(slot)
            if key == install_key or key in seen:
                continue
            seen.add(key)
            slots.append(slot)
    return slots


def _find_preserved_source(rel: str, install_dir: Path, legacy_slots: list[Path]) -> Path | None:
    for root in [install_dir, *legacy_slots]:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def publish_launcher_copy(launcher_path: Path, destination_dir: Path) -> ShortcutPublishResult:
    destination_path = destination_dir / launcher_path.name
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(launcher_path), str(destination_path))
        destination_path.chmod(destination_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as exc:
        return ShortcutPublishResult(
            ok=False,
            path=str(destination_path),
            error=f"{exc.__class__.__name__}: {exc}",
        )
    return ShortcutPublishResult(ok=True, path=str(destination_path))


def publish_desktop_shortcut(
    launcher_path: Path,
    destination_dir: Path,
    source_icon: Optional[Path] = None,
) -> ShortcutPublishResult:
    """Copy a launcher. Icon= stays pointed at the install-folder icon."""
    del source_icon
    return publish_launcher_copy(launcher_path, destination_dir)


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
        uninstall: bool = False,
        delete_data: bool = False,
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)
        self.manifest = manifest
        self.install_dir = install_dir
        self.publish_menu_entry = publish_menu_entry
        self.publish_desktop_shortcut = publish_desktop_shortcut
        self.cleanup_install_dirs = cleanup_install_dirs
        self.uninstall = uninstall
        self.delete_data = delete_data
        self.shortcut_warnings: list[str] = []
        self.install_outcome: InstallOutcome | None = None
        self.uninstall_outcome: UninstallOutcome | None = None
        self.files_committed = False
        self.error_text = ""

    def run(self) -> None:
        try:
            self._do_install()
            self.finished_ok.emit()
        except Exception as exc:
            self.error_text = traceback.format_exc()
            if not self.error_text.strip():
                self.error_text = str(exc)
            self.finished_err.emit(self.error_text)

    def _do_install(self) -> None:
        self.status.emit("Installing ...")
        self.progress.emit(10)
        home_roots = _home_roots_for_manifest(self.manifest)
        legacy_bases = _default_legacy_bases()
        if self.uninstall:
            outcome = uninstall_installed_package(
                self.install_dir,
                marker_filename=self.manifest.install_marker_filename,
                delete_data=self.delete_data,
                home_roots=home_roots,
            )
            self.uninstall_outcome = outcome
            self.progress.emit(100)
            return
        result = perform_install(
            manifest=self.manifest,
            package_root=_package_root(),
            install_dir=self.install_dir,
            home_roots=home_roots,
            legacy_bases=legacy_bases,
        )
        self.install_outcome = result
        self.shortcut_warnings.extend(result.warnings)
        self.progress.emit(100)
        if not result.ok:
            self.files_committed = False
            raise RuntimeError(result.error or "Installation failed.")
        self.files_committed = True


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
        if is_silent_apps_install(manifest):
            intro_lines.extend(
                [
                    "",
                    "This app will install into the FreeCAD Apps folder.",
                    "A Desktop shortcut will be created after install.",
                ]
            )
        else:
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

    def nextId(self) -> int:
        wizard = self.wizard()
        if not isinstance(wizard, Installer):
            return super().nextId()
        if not is_silent_apps_install(self._manifest):
            return wizard.page_id("directory")
        if wizard.same_package_occupancy() is not None:
            return wizard.page_id("existing")
        return wizard.page_id("confirm")


class DirectoryPage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        silent = is_silent_apps_install(manifest)
        if silent:
            self.setTitle("Install Destination")
            self.setSubTitle("This app will be installed into the FreeCAD Apps folder.")
        else:
            self.setTitle("Choose Installation Directory")
            self.setSubTitle("Select the final location for the installed package.")

        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        row.addWidget(self.path_edit)
        self._browse_button = QPushButton("Browse...")
        self._browse_button.clicked.connect(self._browse)
        row.addWidget(self._browse_button)
        layout.addLayout(row)
        layout.addStretch()
        self.registerField("install_dir", self.path_edit)
        self.path_edit.textChanged.connect(self.completeChanged)
        self.path_edit.setText(build_default_install_dir(manifest))
        if silent:
            self.path_edit.setReadOnly(True)
            self._browse_button.hide()

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Installation Directory",
            str(Path(self._manifest.default_install_base).expanduser()),
        )
        if chosen:
            self.path_edit.setText(str(Path(chosen) / self._manifest.default_install_dirname))

    def isComplete(self) -> bool:
        return bool(self.path_edit.text().strip())

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
        try:
            ensure_install_parent(target)
        except OSError as exc:
            QMessageBox.warning(self, "Install Folder", str(exc))
            return False
        occupancy = classify_install_slot(
            target,
            package_id=self._manifest.package_id,
            marker_filename=self._manifest.install_marker_filename,
        )
        decision = install_slot_decision(occupancy)
        if decision == SLOT_ACTION_REFUSE:
            QMessageBox.warning(self, "Folder In Use", slot_refusal_message(occupancy))
            return False
        return True

    def nextId(self) -> int:
        wizard = self.wizard()
        if isinstance(wizard, Installer) and wizard.same_package_occupancy() is not None:
            return wizard.page_id("existing")
        if isinstance(wizard, Installer):
            return wizard.page_id("confirm")
        return super().nextId()


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
        self.menu_checkbox.setChecked(True)
        self.menu_checkbox.setVisible(False)
        layout.addWidget(self.menu_checkbox)

        self.desktop_checkbox = QCheckBox("Create Desktop shortcut")
        self.desktop_checkbox.setChecked(True)
        self.desktop_checkbox.setVisible(False)
        layout.addWidget(self.desktop_checkbox)

        self.cleanup_checkbox = QCheckBox("Remove older installed versions after successful install")
        self.cleanup_checkbox.setVisible(False)
        layout.addWidget(self.cleanup_checkbox)
        layout.addStretch()

    def nextId(self) -> int:
        wizard = self.wizard()
        if isinstance(wizard, Installer):
            return wizard.page_id("install")
        return super().nextId()

        self.registerField("publish_menu_entry", self.menu_checkbox)
        self.registerField("publish_desktop_shortcut", self.desktop_checkbox)
        self.registerField("cleanup_older_versions", self.cleanup_checkbox)

    def initializePage(self) -> None:
        raw_dir = str(self.field("install_dir") or "").strip()
        install_dir = Path(raw_dir).expanduser().resolve() if raw_dir else resolve_silent_install_dir(self._manifest)
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
        occupancy = classify_install_slot(
            install_dir,
            package_id=self._manifest.package_id,
            marker_filename=self._manifest.install_marker_filename,
        )
        replace_text = ""
        if occupancy.kind == SLOT_SAME_PACKAGE:
            version = occupancy.occupant_version or "unknown"
            replace_text = f"<br>This replaces version {version} of the same package."
        launcher_path = install_dir / self._manifest.launcher_filename
        self.summary_label.setText(
            f"<b>Install directory:</b><br><code>{install_dir}</code><br><br>"
            f"<b>Installed launcher:</b><br><code>{launcher_path}</code><br><br>"
            "The installer performs a staged copy before switching the final install directory."
            f"{replace_text}"
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
        self._failed = False

    def isComplete(self) -> bool:
        return self._complete

    def initializePage(self) -> None:
        self._failed = False
        wizard = self.wizard()
        uninstall = isinstance(wizard, Installer) and wizard.uninstall_requested
        delete_data = isinstance(wizard, Installer) and wizard.delete_app_data
        install_dir = wizard.selected_install_dir() if isinstance(wizard, Installer) else Path(str(self.field("install_dir")))
        if uninstall:
            self.setTitle(f"Uninstalling {self._manifest.display_name}...")
        self.worker = InstallWorker(
            manifest=self._manifest,
            install_dir=Path(install_dir).expanduser().resolve(),
            publish_menu_entry=True,
            publish_desktop_shortcut=True,
            cleanup_install_dirs=[],
            uninstall=uninstall,
            delete_data=delete_data,
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
        self._failed = True
        self.status_label.setText("Installation failed.")
        self.completeChanged.emit()
        wizard = self.wizard()
        if isinstance(wizard, Installer):
            wizard.failure_text = message
            wizard.failure_unchanged = not bool(getattr(self.worker, "files_committed", False))
            self.wizard().next()

    def nextId(self) -> int:
        wizard = self.wizard()
        if not isinstance(wizard, Installer):
            return super().nextId()
        if self._failed:
            return wizard.page_id("failure")
        return wizard.page_id("done")


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
        self._warning_details = QPlainTextEdit()
        self._warning_details.setReadOnly(True)
        self._warning_details.setMaximumHeight(72)
        self._warning_details.hide()
        layout.addWidget(self._warning_details)
        self._copy_button = QPushButton("Copy Details")
        self._copy_button.hide()
        self._copy_button.clicked.connect(self._copy_warning)
        layout.addWidget(self._copy_button)
        layout.addStretch()

    def nextId(self) -> int:
        return -1

    def initializePage(self) -> None:
        wizard = self.wizard()
        worker = wizard.install_page.worker if isinstance(wizard, Installer) else None
        if isinstance(wizard, Installer) and wizard.uninstall_requested:
            self._show_uninstall_done(worker)
            return
        self._show_install_done(worker)

    def _show_uninstall_done(self, worker: object) -> None:
        outcome = getattr(worker, "uninstall_outcome", None)
        kept = getattr(outcome, "kept_data_dir", "")
        name = self._manifest.display_name
        lines = [
            f"<b>{name} was uninstalled.</b>",
            "Removed the app folder's program files, the home launcher, the desktop shortcut, the menu entry, and the app icon.",
        ]
        if kept:
            lines.append(f"Kept: {name}'s data in <code>{kept}</code>")
        else:
            lines.append(f"Also deleted {name}'s data.")
        lines.append(f"To install {name} again, run its installer.")
        self.setTitle(f"{name} was uninstalled")
        self.done_label.setText("<br>".join(lines))

    def _show_install_done(self, worker: object) -> None:
        install_dir = Path(str(self.field("install_dir"))).expanduser().resolve()
        warnings = tuple(getattr(worker, "shortcut_warnings", ()))
        name = self._manifest.display_name
        home = Path(self._manifest.staging_parent)
        if warnings:
            self.setTitle(f"{name} is installed")
            warning_text = "\n".join(warnings)
            self._warning_details.setPlainText(warning_text)
            self._warning_details.show()
            self._copy_button.show()
            self.done_label.setText(
                "<br>".join(
                    [
                        "<b>The app is installed, but a shortcut could not be made.</b>",
                        "Run this installer again and choose Replace to try the shortcut again. "
                        "If it still fails, click Copy Details and post them to the LibrePy group.",
                        f"Installed in: <code>{install_dir}</code>",
                        f"To uninstall, run this installer again and choose Uninstall {name}.",
                    ]
                )
            )
            return
        self._warning_details.hide()
        self._copy_button.hide()
        self.setTitle(f"{name} is installed")
        self.done_label.setText(
            "<br>".join(
                [
                    f"<b>{name}</b> is installed.",
                    f"Installed in: <code>{install_dir}</code>",
                    f"Home launcher: <code>{home / self._manifest.launcher_filename}</code>",
                    f"Menu entry: <code>{home / '.local' / 'share' / 'applications' / self._manifest.launcher_filename}</code>",
                    "If you move the app folder, run this installer again so the shortcut still works.",
                    f"To uninstall, run this installer again and choose Uninstall {name}.",
                ]
            )
        )

    def _copy_warning(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._warning_details.toPlainText())
        self._copy_button.setText("Copied")


class ExistingInstallPage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)
        self._replace_radio = QRadioButton(self)
        self._uninstall_radio = QRadioButton("Uninstall", self)
        self._replace_radio.setChecked(True)
        layout.addWidget(self._replace_radio)
        self._replace_help = QLabel()
        self._replace_help.setWordWrap(True)
        layout.addWidget(self._replace_help)
        layout.addWidget(self._uninstall_radio)
        self._uninstall_help = QLabel(
            f"Removes the app, its desktop shortcut, and its menu entry. Nothing new is installed."
        )
        self._uninstall_help.setWordWrap(True)
        layout.addWidget(self._uninstall_help)
        self._warning = QLabel()
        self._warning.setWordWrap(True)
        layout.addWidget(self._warning)
        layout.addStretch()
        self._replace_radio.toggled.connect(self._refresh_button)
        self._uninstall_radio.toggled.connect(self._refresh_button)

    def initializePage(self) -> None:
        wizard = self.wizard()
        occupancy = wizard.same_package_occupancy() if isinstance(wizard, Installer) else None
        installed = occupancy.occupant_version if occupancy is not None else ""
        name = self._manifest.display_name
        relation = version_relation(installed, self._manifest.version)
        action = replace_action_label(installed, self._manifest.version)
        self.setTitle(f"{name} is already installed")
        self.setSubTitle(f"Version {installed or 'unknown'} is on this computer. This installer has version {self._manifest.version}.")
        self._summary.setText(f"Installed in: {occupancy.path if occupancy is not None else ''}")
        self._replace_radio.setText(f"{action} it with version {self._manifest.version}")
        self._replace_help.setText(
            "Keeps the app's data, like its database and saved settings. Only the program files are replaced."
        )
        self._uninstall_radio.setText(f"Uninstall {name}")
        if relation == "older":
            self._warning.setText(
                "This installer is older than the installed version. Replacing installs the older version and keeps the app's data."
            )
        else:
            self._warning.setText("")
        self._refresh_button()

    def _refresh_button(self) -> None:
        wizard = self.wizard()
        if not isinstance(wizard, Installer):
            return
        if self._uninstall_radio.isChecked():
            wizard.setButtonText(QWizard.NextButton, "Uninstall...")
            wizard.uninstall_requested = True
        else:
            installed = ""
            occupancy = wizard.same_package_occupancy()
            if occupancy is not None:
                installed = occupancy.occupant_version
            label = replace_action_label(installed, self._manifest.version)
            wizard.setButtonText(QWizard.NextButton, label)
            wizard.uninstall_requested = False

    def nextId(self) -> int:
        wizard = self.wizard()
        if not isinstance(wizard, Installer):
            return super().nextId()
        if self._uninstall_radio.isChecked():
            return wizard.page_id("uninstall")
        return wizard.page_id("confirm")


class UninstallConfirmPage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self.setCommitPage(True)
        self.setButtonText(QWizard.CommitButton, "Uninstall")
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        self._summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self._summary)
        self._delete_data = QCheckBox(self)
        layout.addWidget(self._delete_data)
        self._data_note = QLabel()
        self._data_note.setWordWrap(True)
        layout.addWidget(self._data_note)
        layout.addStretch()

    def initializePage(self) -> None:
        wizard = self.wizard()
        occupancy = wizard.same_package_occupancy() if isinstance(wizard, Installer) else None
        install_dir = occupancy.path if occupancy is not None else ""
        name = self._manifest.display_name
        version = occupancy.occupant_version if occupancy is not None else self._manifest.version
        self.setTitle(f"Uninstall {name} {version}?")
        self.setSubTitle("These items will be removed from this computer.")
        home = Path(self._manifest.staging_parent)
        lines = [
            f"App folder: {install_dir}",
            f"Home launcher: {home / self._manifest.launcher_filename}",
            f"Menu entry: {home / '.local' / 'share' / 'applications' / self._manifest.launcher_filename}",
            f"Desktop shortcut: {home / 'Desktop' / self._manifest.launcher_filename}",
        ]
        if self._manifest.icon_relative_path and install_dir:
            lines.append(f"App icon: {Path(install_dir) / self._manifest.icon_relative_path}")
        self._summary.setText("<br>".join(lines))
        self._delete_data.setText(f"Also delete {name}'s data")
        self._delete_data.setChecked(False)
        self._data_note.setText(
            "If you leave this box unchecked, the data stays in the app folder so a later install can use it again."
        )

    def validatePage(self) -> bool:
        wizard = self.wizard()
        if isinstance(wizard, Installer):
            wizard.delete_app_data = self._delete_data.isChecked()
            wizard.uninstall_requested = True
        return True

    def nextId(self) -> int:
        wizard = self.wizard()
        if isinstance(wizard, Installer):
            return wizard.page_id("install")
        return super().nextId()


class FailurePage(QWizardPage):
    def __init__(self, manifest: PackageManifest, parent: Optional[QWizard] = None) -> None:
        super().__init__(parent)
        self._manifest = manifest
        self.setFinalPage(True)
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._summary.setWordWrap(True)
        layout.addWidget(self._summary)
        self._details = QPlainTextEdit()
        self._details.setReadOnly(True)
        layout.addWidget(self._details, 1)
        self._copy_button = QPushButton("Copy Details")
        self._copy_button.clicked.connect(self._copy)
        layout.addWidget(self._copy_button)

    def initializePage(self) -> None:
        wizard = self.wizard()
        name = self._manifest.display_name
        self.setTitle("Installation failed")
        unchanged = bool(getattr(wizard, "failure_unchanged", True))
        if unchanged:
            subtitle = f"{name} {self._manifest.version} was not installed. What was already installed was left unchanged."
        else:
            subtitle = f"The program files for {name} were copied. Shortcut publishing did not finish."
        self.setSubTitle(subtitle)
        self._summary.setText(
            "What to try: close the app if it is open, then run the installer again. "
            "If it fails again, click Copy Details and post them to the LibrePy group."
        )
        self._details.setPlainText(str(getattr(wizard, "failure_text", "")))

    def nextId(self) -> int:
        return -1

    def _copy(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._details.toPlainText())
        self._copy_button.setText("Copied")


class Installer(QWizard):
    def __init__(self, manifest: PackageManifest) -> None:
        super().__init__()
        self._manifest = manifest
        self._page_ids: dict[str, int] = {}
        self.uninstall_requested = False
        self.delete_app_data = False
        self.failure_text = ""
        self.failure_unchanged = True
        self.setWindowTitle(f"{manifest.display_name} Installer")
        self.setMinimumSize(620, 420)
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnLastPage, True)
        self.setOption(QWizard.NoCancelButtonOnLastPage, True)
        if manifest.icon_relative_path:
            icon_path = _payload_root(manifest) / manifest.icon_relative_path
            if icon_path.is_file():
                self.setWindowIcon(QIcon(str(icon_path)))
        self._add_page("welcome", WelcomePage(manifest))
        self._add_page("directory", DirectoryPage(manifest))
        self._add_page("existing", ExistingInstallPage(manifest))
        self._add_page("uninstall", UninstallConfirmPage(manifest))
        self._add_page("confirm", ConfirmPage(manifest))
        self.install_page = InstallPage(manifest)
        self._add_page("install", self.install_page)
        self._add_page("done", DonePage(manifest))
        self._add_page("failure", FailurePage(manifest))

    def _add_page(self, name: str, page: QWizardPage) -> None:
        self._page_ids[name] = self.addPage(page)

    def page_id(self, name: str) -> int:
        return self._page_ids[name]

    def same_package_occupancy(self) -> SlotOccupancy | None:
        manifest = self._manifest
        candidates = [resolve_silent_install_dir(manifest)]
        raw_field = str(self.field("install_dir") or "").strip()
        if raw_field:
            candidates.insert(0, Path(raw_field).expanduser())
        for base in _default_legacy_bases():
            candidates.extend(
                discover_same_package_slots(
                    base,
                    package_id=manifest.package_id,
                    marker_filename=manifest.install_marker_filename,
                )
            )
        apps_base = Path(manifest.default_install_base).expanduser()
        candidates.extend(
            discover_same_package_slots(
                apps_base,
                package_id=manifest.package_id,
                marker_filename=manifest.install_marker_filename,
            )
        )
        seen: set[str] = set()
        for candidate in candidates:
            try:
                key = str(Path(candidate).resolve())
            except OSError:
                key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            occupancy = classify_install_slot(
                candidate,
                package_id=manifest.package_id,
                marker_filename=manifest.install_marker_filename,
            )
            if occupancy.kind == SLOT_SAME_PACKAGE:
                return occupancy
        return None

    def selected_install_dir(self) -> Path:
        occupancy = self.same_package_occupancy() if self.uninstall_requested else None
        if occupancy is not None:
            return Path(occupancy.path)
        text = str(self.field("install_dir") or "").strip()
        if text:
            return Path(text).expanduser()
        return resolve_silent_install_dir(self._manifest)


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
