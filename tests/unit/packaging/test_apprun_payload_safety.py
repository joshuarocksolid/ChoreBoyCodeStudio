"""AppRun -c payloads must survive FreeCAD 1.1's per-argument path check."""

from __future__ import annotations

import pytest

from app.packaging.launcher_bootstrap import (
    APPRUN_PAYLOAD_NAME_MAX,
    apprun_safe_python,
    build_fixed_root_bootstrap,
    build_path_key_installer_exec,
    longest_slash_free_run,
)
from app.run.runtime_launch import build_runpy_bootstrap_payload

pytestmark = pytest.mark.unit


def _run(code: str) -> dict:
    namespace: dict = {}
    exec(compile(code, "<payload>", "exec"), namespace)
    namespace.pop("__builtins__", None)
    return namespace


def test_long_payload_is_split_without_changing_what_it_does() -> None:
    code = ";".join(f"value_{index}={index}" for index in range(60)) + ";marker='a;b'"
    assert longest_slash_free_run(code) > APPRUN_PAYLOAD_NAME_MAX

    safe = apprun_safe_python(code)

    assert longest_slash_free_run(safe) <= APPRUN_PAYLOAD_NAME_MAX
    assert _run(safe) == _run(code)


def test_statement_that_cannot_be_split_is_refused() -> None:
    with pytest.raises(ValueError):
        apprun_safe_python("x='" + "a" * 300 + "'")


@pytest.mark.parametrize(
    "payload",
    [
        build_fixed_root_bootstrap("/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.14", "run_editor.py"),
        build_fixed_root_bootstrap("/home/default/FreeCAD/Apps/My Inventory App_v1.2.3", "app_files/main.py"),
        build_path_key_installer_exec("/opt/freecad/AppRun"),
        build_runpy_bootstrap_payload(
            script_path="/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.14/run_runner.py",
            path_entry="/home/default/FreeCAD/CBCS/choreboy_code_studio_v0.4.14",
            argv=["run_runner.py", "--manifest", "/tmp/manifest.json"],
        ),
    ],
)
def test_launcher_payloads_fit_freecad_11_argument_limit(payload: str) -> None:
    assert longest_slash_free_run(payload) <= APPRUN_PAYLOAD_NAME_MAX
