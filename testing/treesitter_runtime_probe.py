"""Standalone probe for validating tree-sitter runtime boot on a device."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import sysconfig

DEFAULT_APP_ROOT = Path(__file__).resolve().parents[1]
default_root_str = str(DEFAULT_APP_ROOT)
if default_root_str not in sys.path:
    sys.path.insert(0, default_root_str)

import app.treesitter.loader as loader
from app.treesitter.language_specs import LANGUAGE_SPECS


def _binding_candidates(package_dir: Path) -> list[str]:
    return sorted(path.name for path in package_dir.glob("_binding*.so"))


def _reset_loader_state() -> None:
    loader._RUNTIME_INITIALIZED = False
    loader._RUNTIME_STATUS = loader.TreeSitterRuntimeStatus(False, "not_initialized")
    loader._RUNTIME_TRACEBACK = None
    loader._TREE_SITTER_MODULE = None
    loader._LANGUAGE_MODULES = {}


def run_probe(app_root: Path) -> dict[str, object]:
    vendor_root = app_root / "vendor"
    soabi = sysconfig.get_config_var("SOABI")
    expected_binding = (
        str((vendor_root / "tree_sitter" / f"_binding.{soabi}.so").resolve())
        if isinstance(soabi, str) and soabi.strip()
        else None
    )
    package_candidates = {
        "tree_sitter": _binding_candidates(vendor_root / "tree_sitter"),
    }
    for spec in LANGUAGE_SPECS:
        package_candidates[spec.package_name] = _binding_candidates(vendor_root / spec.package_name)
    _reset_loader_state()
    status = loader.initialize_tree_sitter_runtime(app_root=app_root)
    return {
        "app_root": str(app_root.resolve()),
        "python_executable": sys.executable,
        "python_version": sys.version,
        "soabi": soabi,
        "expected_core_binding": expected_binding,
        "package_candidates": package_candidates,
        "is_available": status.is_available,
        "status_message": status.message,
        "available_language_keys": list(status.available_language_keys),
        "missing_default_language_keys": list(status.missing_default_language_keys),
        "skipped_optional_language_keys": list(status.skipped_optional_language_keys),
        "traceback": loader.runtime_traceback(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe tree-sitter runtime initialization for the current AppRun Python."
    )
    parser.add_argument(
        "--app-root",
        default=str(DEFAULT_APP_ROOT),
        help="Application root containing app/ and vendor/ directories.",
    )
    args = parser.parse_args()
    result = run_probe(Path(args.app_root).expanduser().resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["is_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
