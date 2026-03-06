from app.plugins.discovery import DiscoveredPlugin, discover_installed_plugins
from app.plugins.installer import PluginInstallResult, install_plugin, set_plugin_enabled, uninstall_plugin
from app.plugins.manifest import PluginManifest, load_plugin_manifest, parse_plugin_manifest
from app.plugins.registry_store import load_plugin_registry

__all__ = [
    "DiscoveredPlugin",
    "PluginManifest",
    "PluginInstallResult",
    "discover_installed_plugins",
    "install_plugin",
    "load_plugin_registry",
    "load_plugin_manifest",
    "parse_plugin_manifest",
    "set_plugin_enabled",
    "uninstall_plugin",
]
