"""The inspector registry: discovery order, overrides, and conflicts."""

from __future__ import annotations

import importlib
import textwrap
import uuid
from pathlib import Path
from types import ModuleType
from typing import Dict

import pytest

from app.features.form_builder.qtside.inspector import editors
from app.features.form_builder.qtside.inspector.api import EditorKey, GroupId
from app.features.form_builder.qtside.inspector.catalog import RegistryConflict
from app.features.form_builder.qtside.inspector.editors import load_catalog
from app.features.form_builder.qtside.inspector.editors.scalars import TextEditor

pytestmark = pytest.mark.unit

_ROW = """
from app.features.form_builder.qtside.inspector.api import GroupId, Prop, RowSpec

def register(registrar):
    registrar.row(RowSpec({key!r}, GroupId.CONTENT, {label!r}, "", Prop({key!r})))
"""


def _package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modules: Dict[str, str]) -> ModuleType:
    name = "inspector_contrib_%s" % uuid.uuid4().hex
    root = tmp_path / name
    root.mkdir()
    (root / "__init__.py").write_text("")
    for module, body in modules.items():
        (root / (module + ".py")).write_text(textwrap.dedent(body))
    monkeypatch.syspath_prepend(str(tmp_path))
    return importlib.import_module(name)


def test_modules_load_in_sorted_name_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _package(
        tmp_path,
        monkeypatch,
        {"b": _ROW.format(key="b", label="B"), "a": _ROW.format(key="a", label="A")},
    )

    assert [spec.key for spec in load_catalog(package).rows()] == ["a", "b"]


def test_underscore_modules_are_never_imported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    package = _package(
        tmp_path,
        monkeypatch,
        {"_skip": "raise RuntimeError('imported')\n", "a": _ROW.format(key="a", label="A")},
    )

    assert [spec.key for spec in load_catalog(package).rows()] == ["a"]


def test_a_public_module_without_register_fails_to_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = _package(tmp_path, monkeypatch, {"forgot": "VALUE = 1\n"})

    with pytest.raises(TypeError, match="forgot"):
        load_catalog(package)


def test_a_later_package_overrides_baselines_without_editing_shared_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    later = _package(
        tmp_path,
        monkeypatch,
        {
            "m4_3b_font": """
                from app.features.form_builder.qtside.inspector.api import EditorKey

                class FontStub:
                    pass

                def register(registrar):
                    registrar.editor(EditorKey("font"), FontStub)
            """,
            "m3_6_size": """
                from app.features.form_builder.qtside.inspector.api import GroupId

                class SizeBody:
                    pass

                def register(registrar):
                    registrar.group_body(GroupId.SIZE, SizeBody)
            """,
        },
    )

    catalog = load_catalog(editors, later)

    assert catalog.editor(EditorKey("font")) is importlib.import_module(later.__name__ + ".m4_3b_font").FontStub
    assert catalog.group_body(GroupId.SIZE) is importlib.import_module(later.__name__ + ".m3_6_size").SizeBody
    assert catalog.editor(EditorKey("string")) is TextEditor


def test_an_overriding_row_keeps_the_baseline_position(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    baseline = [spec.key for spec in load_catalog(editors).rows()]
    later = _package(tmp_path, monkeypatch, {"m4_text": _ROW.format(key="text", label="Caption")})

    rows = load_catalog(editors, later).rows()

    assert [spec.key for spec in rows] == baseline
    assert rows[baseline.index("text")].label == "Caption"


@pytest.mark.parametrize(
    "call",
    [
        'registrar.editor(EditorKey("font"), object)',
        'registrar.editor(EditorKey("font"), object, baseline=True)',
        'registrar.row(RowSpec("dup", GroupId.CONTENT, "Dup", "", Prop("dup")))',
        "registrar.group_body(GroupId.SIZE, object)",
    ],
    ids=["editor", "baseline-editor", "row", "group-body"],
)
def test_two_registrations_of_one_key_fail_naming_both_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, call: str
) -> None:
    body = (
        "from app.features.form_builder.qtside.inspector.api import EditorKey, GroupId, Prop, RowSpec\n"
        "\n"
        "def register(registrar):\n"
        "    %s\n" % call
    )
    package = _package(tmp_path, monkeypatch, {"one": body, "two": body})

    with pytest.raises(RegistryConflict) as raised:
        load_catalog(package)

    assert package.__name__ + ".one" in str(raised.value)
    assert package.__name__ + ".two" in str(raised.value)
