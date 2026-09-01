from __future__ import annotations

from pathlib import Path

import pytest

from tools.dune.check import run

pytestmark = pytest.mark.unit

_SEVEN_PHASES = "\n".join(
    f"def install_phase_{index}(ctx):\n    pass\n"
    for index in range(7)
)
_EMPTY_FEATURE_SPECS = (
    "class FeatureSpec:\n"
    "    pass\n"
    "\n"
    "FEATURE_SPECS = ()\n"
)


def _write_source(repo_root: Path, relative_path: str, source: str) -> None:
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _write_fixture(
    repo_root: Path,
    *,
    phases: str = _SEVEN_PHASES,
    feature_specs: str = _EMPTY_FEATURE_SPECS,
    extra_sources: dict[str, str] | None = None,
) -> list[str]:
    (repo_root / "dune.yaml").write_text(
        "owners:\n"
        "  shell:\n"
        "    - app/shell/**\n"
        "  features:\n"
        "    - app/features/**\n",
        encoding="utf-8",
    )
    sources = {
        "app/shell/main_window_composition_phases.py": phases,
        "app/features/spec.py": feature_specs,
    }
    sources.update(extra_sources or {})
    for relative_path, source in sources.items():
        _write_source(repo_root, relative_path, source)
    return sorted(sources)


def test_eighth_install_phase_fails_with_composition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    tracked_files = _write_fixture(
        tmp_path,
        phases=_SEVEN_PHASES + "\ndef install_extra_feature(ctx):\n    pass\n",
    )

    exit_code = run(
        tmp_path,
        tracked_files,
        baseline_root=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "composition: app/shell/main_window_composition_phases.py: "
        "8 install_* functions exceed the committed count of 7\n"
    )


@pytest.mark.parametrize(
    "source",
    [
        "def wire(window):\n    window._extra_service = object()\n",
        (
            "def wire(window):\n"
            "    bind_private_attrs(window, {'_extra_service': object()})\n"
        ),
    ],
)
def test_undeclared_window_field_fails_with_composition(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source: str,
) -> None:
    tracked_files = _write_fixture(
        tmp_path,
        extra_sources={"app/shell/extra_feature.py": source},
    )

    exit_code = run(
        tmp_path,
        tracked_files,
        baseline_root=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert captured.err == (
        "composition: app/shell/extra_feature.py:2: "
        "window field _extra_service is not committed or owned by a FeatureSpec\n"
    )


def test_feature_spec_allows_owned_window_field(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    feature_specs = (
        "class FeatureSpec:\n"
        "    pass\n"
        "\n"
        "FEATURE_SPECS = (\n"
        "    FeatureSpec(\n"
        '        key="extra",\n'
        '        ownership_globs=("app/features/extra/**",),\n'
        "    ),\n"
        ")\n"
    )
    tracked_files = _write_fixture(
        tmp_path,
        feature_specs=feature_specs,
        extra_sources={
            "app/features/extra/install.py": (
                "def install(window):\n"
                "    window._extra_service = object()\n"
            )
        },
    )

    exit_code = run(
        tmp_path,
        tracked_files,
        baseline_root=tmp_path,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "dune check ok\n"
    assert captured.err == ""
