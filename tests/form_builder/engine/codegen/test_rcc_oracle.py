"""Resource bytes read back through QFile match ``rcc -g python``."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.features.form_builder.engine.codegen.resources import (
    compile_resource_tree,
    read_qrc,
    render_rc_module,
)

_CORPUS = Path(__file__).resolve().parents[2] / "corpus"


def _qfile_bytes(module_text: str, paths: list) -> dict:
    from PySide6.QtCore import QFile

    namespace: dict = {"__name__": "cbcs_rc_oracle"}
    exec(compile(module_text, "<rc>", "exec"), namespace)
    found = {}
    try:
        for resource in paths:
            handle = QFile(resource)
            if not handle.open(QFile.ReadOnly):
                found[resource] = None
                continue
            found[resource] = bytes(handle.readAll())
            handle.close()
    finally:
        cleanup = namespace.get("qCleanupResources")
        if cleanup is not None:
            cleanup()
    return found


def _paths(qrc_text: str) -> list:
    document = read_qrc(qrc_text)
    paths = []
    for entry in document.files:
        prefix = entry.prefix.strip().strip("/")
        tail = (entry.alias or entry.path).replace("\\", "/").strip().strip("/")
        parts = [part for part in (prefix + "/" + tail).split("/") if part]
        paths.append(":/" + "/".join(parts))
    return paths


def _compare_qrc(qrc_path: Path, rcc: str) -> tuple:
    text = qrc_path.read_text(encoding="utf-8")
    document = read_qrc(text)
    paths = _paths(text)

    def read_file(rel: str, base: Path = qrc_path.parent) -> bytes:
        return (base / rel).read_bytes()

    tree, diagnostics = compile_resource_tree(document, read_file=read_file)
    if diagnostics:
        return "missing", [item.message for item in diagnostics]
    ours = render_rc_module(tree, qrc_file_name=qrc_path.name)
    with tempfile.TemporaryDirectory(prefix="fb-rcc-") as folder:
        out = Path(folder) / "rcc_out.py"
        proc = subprocess.run(
            [rcc, "-g", "python", "-o", str(out), str(qrc_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return "rcc-fail", proc.stderr[:300]
        theirs = out.read_text(encoding="utf-8")
    left = _qfile_bytes(ours, paths)
    right = _qfile_bytes(theirs, paths)
    mismatches = []
    for resource in paths:
        if left.get(resource) != right.get(resource):
            mismatches.append(
                "%s ours %s rcc %s"
                % (
                    resource,
                    None if left.get(resource) is None else len(left[resource]),
                    None if right.get(resource) is None else len(right[resource]),
                )
            )
    if mismatches:
        return "diff", mismatches
    return "ok", paths


@pytest.mark.oracle
@pytest.mark.timeout(120)
def test_qfile_bytes_match_rcc(qapp) -> None:
    del qapp
    rcc = os.environ.get("CBCS_FB_RCC", "")
    if not rcc or not Path(rcc).is_file():
        pytest.skip("CBCS_FB_RCC is not set")
    files = sorted(_CORPUS.rglob("*.qrc"))
    assert files
    counts = {}
    problems = []
    for path in files:
        try:
            status, detail = _compare_qrc(path, rcc)
        except Exception as exc:
            status, detail = "crash", "%s: %s" % (type(exc).__name__, exc)
        counts[status] = counts.get(status, 0) + 1
        # A corpus qrc can name a file the checkout did not vendor. rcc refuses
        # the whole file then, and there is nothing to compare. FB503 covers it.
        if status not in ("ok", "rcc-fail", "missing"):
            problems.append((str(path), status, detail))
    print("rcc-oracle", counts)
    assert not problems, problems


@pytest.mark.oracle
@pytest.mark.timeout(60)
def test_alias_tree_matches_rcc(qapp, tmp_path: Path) -> None:
    """A two-file tree with an alias, so a corpus gap cannot hide a format bug."""
    del qapp
    rcc = os.environ.get("CBCS_FB_RCC", "")
    if not rcc or not Path(rcc).is_file():
        pytest.skip("CBCS_FB_RCC is not set")
    (tmp_path / "dot.bin").write_bytes(b"HELLO")
    (tmp_path / "nested.bin").write_bytes(b"WORLD!!")
    qrc = tmp_path / "demo.qrc"
    qrc.write_text(
        "<RCC><qresource prefix=\"/cbcs\">"
        "<file>dot.bin</file>"
        '<file alias="icons/dot.bin">nested.bin</file>'
        "</qresource></RCC>",
        encoding="utf-8",
    )
    status, detail = _compare_qrc(qrc, rcc)
    assert status == "ok", (status, detail)
    assert ":/cbcs/dot.bin" in detail
    assert ":/cbcs/icons/dot.bin" in detail


def _read_resource(module_text: str, resource: str, locale_name: str):
    from PySide6.QtCore import QFile, QIODevice, QLocale

    QLocale.setDefault(QLocale(locale_name))
    namespace = {"__name__": "cbcs_rc_locale"}
    exec(compile(module_text, "<rc>", "exec"), namespace)
    try:
        handle = QFile(resource)
        if not handle.open(QIODevice.OpenModeFlag.ReadOnly):
            return None
        try:
            return bytes(handle.readAll().data())
        finally:
            handle.close()
    finally:
        cleanup = namespace.get("qCleanupResources")
        if cleanup is not None:
            cleanup()


@pytest.mark.oracle
@pytest.mark.timeout(60)
def test_locale_and_nonbmp_names_match_rcc(qapp, tmp_path: Path) -> None:
    """A later ``lang`` must not hide the default, and a non-BMP name must be readable."""
    del qapp
    rcc = os.environ.get("CBCS_FB_RCC", "")
    if not rcc or not Path(rcc).is_file():
        pytest.skip("CBCS_FB_RCC is not set")
    (tmp_path / "en.txt").write_bytes(b"HELLO")
    (tmp_path / "fr.txt").write_bytes(b"BONJOUR")
    face = "a\U0001f600.txt"
    (tmp_path / face).write_bytes(b"FACE")
    qrc = tmp_path / "demo.qrc"
    qrc.write_text(
        "<RCC>"
        '<qresource prefix="/p"><file alias="a.txt">en.txt</file></qresource>'
        '<qresource prefix="/p" lang="fr"><file alias="a.txt">fr.txt</file></qresource>'
        '<qresource prefix="/e"><file>%s</file></qresource>'
        "</RCC>" % face,
        encoding="utf-8",
    )
    document = read_qrc(qrc.read_text(encoding="utf-8"))

    def read_file(rel: str) -> bytes:
        return (tmp_path / rel).read_bytes()

    tree, diagnostics = compile_resource_tree(document, read_file=read_file)
    assert not diagnostics
    ours = render_rc_module(tree, qrc_file_name=qrc.name)
    with tempfile.TemporaryDirectory(prefix="fb-rcc-") as folder:
        out = Path(folder) / "rcc_out.py"
        proc = subprocess.run(
            [rcc, "-g", "python", "-o", str(out), str(qrc)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        theirs = out.read_text(encoding="utf-8")
    emoji = ":/e/" + face
    for locale_name, resource, expected in (
        ("en_US", ":/p/a.txt", b"HELLO"),
        ("fr_FR", ":/p/a.txt", b"BONJOUR"),
        ("C", emoji, b"FACE"),
    ):
        assert _read_resource(ours, resource, locale_name) == expected
        assert _read_resource(theirs, resource, locale_name) == expected
