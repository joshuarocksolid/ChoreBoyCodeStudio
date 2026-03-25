from __future__ import annotations

from pathlib import Path

from app.bootstrap.paths import PathInput, bundled_plugins_root, global_plugins_installed_dir
from app.core import constants
from app.plugins.auditor import audit_plugin_package_messages
from app.plugins.manifest import load_plugin_manifest
from app.plugins.models import DiscoveredPlugin, PluginCompatibility, PluginManifest


def discover_installed_plugins(
    *,
    state_root: PathInput | None = None,
    current_app_version: str = constants.APP_VERSION,
    current_api_version: int = constants.PLUGIN_API_VERSION,
    include_bundled: bool = False,
) -> list[DiscoveredPlugin]:
    discovered: list[DiscoveredPlugin] = []
    discovered.extend(
        _discover_installed_plugin_roots(
            state_root=state_root,
            current_app_version=current_app_version,
            current_api_version=current_api_version,
        )
    )
    if include_bundled:
        discovered.extend(
            _discover_bundled_plugin_roots(
                current_app_version=current_app_version,
                current_api_version=current_api_version,
            )
        )
    discovered.sort(key=lambda item: (item.plugin_id, item.version, item.source_kind))
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


def _discover_installed_plugin_roots(
    *,
    state_root: PathInput | None,
    current_app_version: str,
    current_api_version: int,
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
            discovered.append(
                _discover_plugin_from_manifest_root(
                    manifest_root=version_dir,
                    fallback_plugin_id=plugin_dir.name,
                    fallback_version=version_dir.name,
                    current_app_version=current_app_version,
                    current_api_version=current_api_version,
                    source_kind=constants.PLUGIN_SOURCE_INSTALLED,
                )
            )
    return discovered


def _discover_bundled_plugin_roots(
    *,
    current_app_version: str,
    current_api_version: int,
) -> list[DiscoveredPlugin]:
    bundled_root = bundled_plugins_root()
    if not bundled_root.exists() or not bundled_root.is_dir():
        return []
    discovered: list[DiscoveredPlugin] = []
    for plugin_root in sorted(bundled_root.iterdir(), key=lambda path: path.name):
        if not plugin_root.is_dir():
            continue
        discovered.append(
            _discover_plugin_from_manifest_root(
                manifest_root=plugin_root,
                fallback_plugin_id=plugin_root.name,
                fallback_version="bundled",
                current_app_version=current_app_version,
                current_api_version=current_api_version,
                source_kind=constants.PLUGIN_SOURCE_BUNDLED,
            )
        )
    return discovered


def _discover_plugin_from_manifest_root(
    *,
    manifest_root: Path,
    fallback_plugin_id: str,
    fallback_version: str,
    current_app_version: str,
    current_api_version: int,
    source_kind: str,
) -> DiscoveredPlugin:
    manifest_path = manifest_root / constants.PLUGIN_MANIFEST_FILENAME
    if not manifest_path.exists() or not manifest_path.is_file():
        return DiscoveredPlugin(
            plugin_id=fallback_plugin_id,
            version=fallback_version,
            install_path=str(manifest_root.resolve()),
            manifest_path=str(manifest_path.resolve()),
            source_kind=source_kind,
            errors=[f"Missing {constants.PLUGIN_MANIFEST_FILENAME}."],
        )
    try:
        manifest = load_plugin_manifest(manifest_path)
    except Exception as exc:
        return DiscoveredPlugin(
            plugin_id=fallback_plugin_id,
            version=fallback_version,
            install_path=str(manifest_root.resolve()),
            manifest_path=str(manifest_path.resolve()),
            source_kind=source_kind,
            errors=[str(exc)],
        )
    compatibility = evaluate_manifest_compatibility(
        manifest,
        current_app_version=current_app_version,
        current_api_version=current_api_version,
    )
    audit_messages = audit_plugin_package_messages(manifest_root, manifest)
    reasons = list(compatibility.reasons)
    for message in audit_messages:
        if message not in reasons:
            reasons.append(message)
    effective_compatibility = PluginCompatibility(
        is_compatible=compatibility.is_compatible and not audit_messages,
        reasons=reasons,
    )
    return DiscoveredPlugin(
        plugin_id=manifest.plugin_id,
        version=manifest.version,
        install_path=str(manifest_root.resolve()),
        manifest_path=str(manifest_path.resolve()),
        source_kind=source_kind,
        manifest=manifest,
        compatibility=effective_compatibility,
        errors=[] if effective_compatibility.is_compatible else list(effective_compatibility.reasons),
    )
