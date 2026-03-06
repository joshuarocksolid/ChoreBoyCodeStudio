from __future__ import annotations

from pathlib import Path

from app.bootstrap.paths import PathInput, global_plugins_installed_dir
from app.core import constants
from app.plugins.manifest import load_plugin_manifest
from app.plugins.models import DiscoveredPlugin, PluginCompatibility, PluginManifest


def discover_installed_plugins(
    *,
    state_root: PathInput | None = None,
    current_app_version: str = constants.APP_VERSION,
    current_api_version: int = constants.PLUGIN_API_VERSION,
) -> list[DiscoveredPlugin]:
    installed_root = global_plugins_installed_dir(state_root)
    if not installed_root.exists() or not installed_root.is_dir():
        return []

    discovered: list[DiscoveredPlugin] = []
    for plugin_dir in sorted(installed_root.iterdir(), key=lambda path: path.name):
        if not plugin_dir.is_dir():
            continue
        for version_dir in sorted(plugin_dir.iterdir(), key=lambda path: path.name):
            if not version_dir.is_dir():
                continue
            manifest_path = version_dir / constants.PLUGIN_MANIFEST_FILENAME
            if not manifest_path.exists() or not manifest_path.is_file():
                discovered.append(
                    DiscoveredPlugin(
                        plugin_id=plugin_dir.name,
                        version=version_dir.name,
                        install_path=str(version_dir.resolve()),
                        manifest_path=str(manifest_path.resolve()),
                        errors=[f"Missing {constants.PLUGIN_MANIFEST_FILENAME}."],
                    )
                )
                continue
            try:
                manifest = load_plugin_manifest(manifest_path)
            except Exception as exc:
                discovered.append(
                    DiscoveredPlugin(
                        plugin_id=plugin_dir.name,
                        version=version_dir.name,
                        install_path=str(version_dir.resolve()),
                        manifest_path=str(manifest_path.resolve()),
                        errors=[str(exc)],
                    )
                )
                continue
            compatibility = evaluate_manifest_compatibility(
                manifest,
                current_app_version=current_app_version,
                current_api_version=current_api_version,
            )
            discovered.append(
                DiscoveredPlugin(
                    plugin_id=manifest.plugin_id,
                    version=manifest.version,
                    install_path=str(version_dir.resolve()),
                    manifest_path=str(manifest_path.resolve()),
                    manifest=manifest,
                    compatibility=compatibility,
                    errors=[] if compatibility.is_compatible else list(compatibility.reasons),
                )
            )
    return discovered


def evaluate_manifest_compatibility(
    manifest: PluginManifest,
    *,
    current_app_version: str,
    current_api_version: int,
) -> PluginCompatibility:
    reasons: list[str] = []
    if manifest.api_version != current_api_version:
        reasons.append(
            f"Plugin api_version {manifest.api_version} does not match editor api_version {current_api_version}."
        )

    min_api_version = manifest.engine.min_api_version
    max_api_version = manifest.engine.max_api_version
    if min_api_version is not None and current_api_version < min_api_version:
        reasons.append(
            f"Editor api_version {current_api_version} is below plugin minimum {min_api_version}."
        )
    if max_api_version is not None and current_api_version > max_api_version:
        reasons.append(
            f"Editor api_version {current_api_version} is above plugin maximum {max_api_version}."
        )

    min_app_version = manifest.engine.min_app_version
    max_app_version = manifest.engine.max_app_version
    if min_app_version is not None and _compare_versions(current_app_version, min_app_version) < 0:
        reasons.append(
            f"Editor app version {current_app_version} is below plugin minimum {min_app_version}."
        )
    if max_app_version is not None and _compare_versions(current_app_version, max_app_version) > 0:
        reasons.append(
            f"Editor app version {current_app_version} is above plugin maximum {max_app_version}."
        )

    return PluginCompatibility(is_compatible=not reasons, reasons=reasons)


def _compare_versions(left: str, right: str) -> int:
    left_parts = _normalize_version_parts(left)
    right_parts = _normalize_version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    for index in range(max_len):
        left_value = left_parts[index] if index < len(left_parts) else 0
        right_value = right_parts[index] if index < len(right_parts) else 0
        if left_value < right_value:
            return -1
        if left_value > right_value:
            return 1
    return 0


def _normalize_version_parts(version: str) -> list[int]:
    parts: list[int] = []
    for segment in version.split("."):
        segment = segment.strip()
        if not segment:
            parts.append(0)
            continue
        digits = "".join(character for character in segment if character.isdigit())
        if not digits:
            parts.append(0)
        else:
            parts.append(int(digits))
    return parts
