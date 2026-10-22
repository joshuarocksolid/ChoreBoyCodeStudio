"""Load every committed corpus form with QUiLoader and Qt 6 uic.

Writes ``MANIFEST.json`` next to this file. Exits 0 when the corpus meets
the M0.4 gate.

Lab:
    QT_QPA_PLATFORM=offscreen /home/joshua/opt/freecad/bin/python \\
        tests/form_builder/corpus/validate.py

Mac:
    QT_QPA_PLATFORM=offscreen \\
        /Applications/FreeCAD.app/Contents/Resources/bin/python \\
        tests/form_builder/corpus/validate.py

Set ``CBCS_UIC`` if Qt 6 ``uic`` is not in one of the known FreeCAD locations.
``CBCS_FREECAD_ROOT`` is an extra root for ``freecad_locator``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


CORPUS = Path(__file__).resolve().parent
MIN_COMMITTED_UI = 200

if __package__ in {None, ""}:
    sys.path.insert(0, str(CORPUS))
    from schema_contract import ATTRIBUTES, ELEMENTS, REQUIRED_PARENTS
else:
    from tests.form_builder.corpus.schema_contract import (  # pyright: ignore[reportMissingImports]
        ATTRIBUTES,
        ELEMENTS,
        REQUIRED_PARENTS,
    )


def _uic_version_text(path: Path) -> str:
    proc = subprocess.run(
        [str(path), "-v"],
        capture_output=True,
        text=True,
        check=False,
    )
    return ((proc.stdout or "") + (proc.stderr or "")).strip()


def find_uic() -> Tuple[str, str]:
    """Return ``(path, version text)`` for a Qt 6 uic binary."""
    candidates: List[str] = []
    override = os.environ.get("CBCS_UIC")
    if override:
        candidates.append(override)
    freecad_root = os.environ.get("CBCS_FREECAD_ROOT")
    if freecad_root:
        candidates.append(str(Path(freecad_root) / "lib" / "qt6" / "uic"))
    home = Path.home()
    candidates.extend(
        [
            "/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic",
            str(home / "opt" / "freecad" / "lib" / "qt6" / "uic"),
            "/home/joshua/opt/freecad/lib/qt6/uic",
            "/opt/freecad/lib/qt6/uic",
            str(home / "opt" / "freecad" / "bin" / "pyside6-uic"),
            "/home/joshua/opt/freecad/bin/pyside6-uic",
        ]
    )
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if not path.is_file():
            continue
        version = _uic_version_text(path)
        if "uic 6." in version or version.startswith("6."):
            return str(path), version
    raise SystemExit(
        "Qt 6 uic not found. Set CBCS_UIC to the Qt 6 uic binary "
        "(FreeCAD.app lib/qt6/uic on macOS, ~/opt/freecad/lib/qt6/uic on the lab)."
    )


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def scan_features(path: Path) -> Tuple[List[str], Set[str], Set[Tuple[str, str]], Set[str]]:
    """Return feature labels, element names, parent edges, and attribute names."""
    try:
        tree = ET.parse(str(path))
    except ET.ParseError:
        return [], set(), set(), set()
    elements: Set[str] = set()
    attributes: Set[str] = set()
    edges: Set[Tuple[str, str]] = set()
    classes: Set[str] = set()
    root = tree.getroot()
    edges.add(("#document", _local(root.tag)))

    def walk(node: ET.Element, parent: str) -> None:
        name = _local(node.tag)
        elements.add(name)
        edges.add((parent, name))
        for key in node.attrib:
            attributes.add(_local(key))
        if name == "widget" and node.attrib.get("class"):
            classes.add(node.attrib["class"])
        for child in list(node):
            walk(child, name)

    walk(root, "#document")
    features = sorted(elements | {"@%s" % name for name in attributes} | classes)
    return features, elements, edges, attributes


def _load_provenance() -> Dict[str, dict]:
    found: Dict[str, dict] = {}
    for folder in ("qt_examples", "synthetic", "malformed"):
        path = CORPUS / folder / "provenance.json"
        if not path.is_file():
            raise SystemExit("missing %s" % path.relative_to(CORPUS))
        payload = json.loads(path.read_text(encoding="utf-8"))
        for entry in payload["files"]:
            rel = entry["path"]
            if rel in found:
                raise SystemExit("duplicate provenance path %s" % rel)
            found[rel] = entry
    return found


def _ui_paths() -> List[Path]:
    paths = [path for path in CORPUS.rglob("*.ui") if path.is_file() and "freecad" not in path.parts]
    paths.sort()
    return paths


def _load_in_subprocess(path: Path) -> Tuple[bool, str]:
    """Load one file in a child process so a QUiLoader crash names that file."""
    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--load", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    stdout = proc.stdout or ""
    result = ""
    for line in stdout.splitlines():
        if line.startswith("CBCS_RESULT "):
            result = line[len("CBCS_RESULT ") :]
    if proc.returncode != 0 or not result:
        detail = (proc.stderr or stdout or "no output").strip().replace("\n", " ")
        return False, "QUiLoader process exited %s. %s" % (proc.returncode, detail[:400])
    stderr = (proc.stderr or "").strip().replace("\n", " ")
    if result.startswith("OK"):
        return True, ""
    if result.startswith("FAIL "):
        detail = result[5:]
        if stderr:
            detail = "%s %s" % (detail, stderr)
        return False, detail[:500]
    return False, (result or stderr)[:500]


def _load_main(path: str) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    for module_name in (
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtPdfWidgets",
        "PySide6.QtCharts",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtOpenGLWidgets",
        "PySide6.QtSvgWidgets",
        "PySide6.QtPrintSupport",
    ):
        try:
            __import__(module_name)
        except Exception:
            pass
    from PySide6.QtWidgets import QApplication
    from PySide6.QtUiTools import QUiLoader

    QApplication([])
    loader = QUiLoader()
    try:
        widget = loader.load(path)
    except Exception as exc:
        print("CBCS_RESULT FAIL %s: %s" % (type(exc).__name__, exc))
        return 0
    if widget is None:
        print("CBCS_RESULT FAIL %s" % (loader.errorString() or "QUiLoader.load returned None"))
        return 0
    print("CBCS_RESULT OK")
    return 0


def _oracle(uic: str, path: Path) -> dict:
    quiloader_ok, quiloader_error = _load_in_subprocess(path)
    proc = subprocess.run(
        [uic, "-g", "python", str(path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    uic_ok = proc.returncode == 0
    uic_error = (proc.stderr or "").strip()
    if not uic_ok and not uic_error:
        uic_error = (proc.stdout or "").strip()[:500]
    return {
        "quiloader_ok": quiloader_ok,
        "quiloader_error": _redact(quiloader_error, path)[:500],
        "uic_ok": uic_ok,
        "uic_stderr": _redact(uic_error, path)[:500],
    }


def _redact(text: str, path: Path) -> str:
    """Drop machine-local paths so a re-run on another host does not churn the manifest."""
    if not text:
        return text
    text = text.replace(str(path.resolve()), path.relative_to(CORPUS).as_posix())
    text = text.replace(str(path), path.relative_to(CORPUS).as_posix())
    text = text.replace(str(CORPUS.resolve()), "corpus")
    text = text.replace(str(CORPUS), "corpus")
    return text


_ELEMENT_CANON = {name.casefold(): name for name in ELEMENTS}


def _canon_element(name: str) -> str:
    """Map Qt's tag spelling onto the ui4 schema name.

    Qt 6.8 writes ``cursorShape`` and ``gradientstop``. The schema names are
    ``cursorshape`` and ``gradientStop``. Coverage is case-insensitive so a
    Qt-sourced file still counts for the schema name.
    """
    return _ELEMENT_CANON.get(name.casefold(), name)


def _coverage(rows: List[dict]) -> dict:
    element_counts: Dict[str, int] = defaultdict(int)
    attribute_counts: Dict[str, int] = defaultdict(int)
    parents: Dict[str, Set[str]] = defaultdict(set)
    samples: Dict[str, str] = {}
    for row in rows:
        if row["folder"] == "malformed":
            continue
        for name in row["_elements"]:
            canon = _canon_element(name)
            element_counts[canon] += 1
            samples.setdefault(canon, row["path"])
        for name in row["_attributes"]:
            attribute_counts[name] += 1
            samples.setdefault("@%s" % name, row["path"])
        for parent, child in row["_edges"]:
            parents[_canon_element(child)].add(_canon_element(parent))
    missing_elements = sorted(ELEMENTS - set(element_counts))
    missing_attributes = sorted(ATTRIBUTES - set(attribute_counts))
    missing_parents = []
    for child, required in sorted(REQUIRED_PARENTS.items()):
        have = parents.get(child, set())
        absent = sorted(required - have)
        if absent:
            missing_parents.append({"element": child, "missing_parents": absent, "seen_parents": sorted(have)})
    return {
        "elements": {name: element_counts[name] for name in sorted(ELEMENTS)},
        "attributes": {name: attribute_counts[name] for name in sorted(ATTRIBUTES)},
        "samples": {name: samples[name] for name in sorted(samples) if name in samples},
        "missing_elements": missing_elements,
        "missing_attributes": missing_attributes,
        "missing_parents": missing_parents,
    }


def _folder_of(rel: str) -> str:
    return rel.split("/", 1)[0]


def validate() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    uic, uic_version = find_uic()
    provenance = _load_provenance()
    ui_paths = _ui_paths()
    rels = [path.relative_to(CORPUS).as_posix() for path in ui_paths]
    missing_prov = sorted(set(rels) - set(provenance))
    extra_prov = sorted(set(provenance) - set(rels))
    rows = []
    failures = []
    for path, rel in zip(ui_paths, rels):
        meta = provenance.get(rel, {})
        features, elements, edges, attributes = scan_features(path)
        print("LOAD %s" % rel, flush=True)
        oracle = _oracle(uic, path)
        folder = _folder_of(rel)
        row = {
            "path": rel,
            "source": meta.get("source", ""),
            "licence": meta.get("licence", ""),
            "features": features,
            "quiloader_ok": oracle["quiloader_ok"],
            "uic_ok": oracle["uic_ok"],
            "notes": meta.get("notes", ""),
            "folder": folder,
            "quiloader_error": oracle["quiloader_error"],
            "uic_stderr": oracle["uic_stderr"],
            "_elements": elements,
            "_attributes": attributes,
            "_edges": edges,
        }
        rows.append(row)
        if not meta:
            failures.append("%s has no provenance entry" % rel)
            continue
        if not row["source"] or not row["licence"]:
            failures.append("%s provenance is missing source or licence" % rel)
        if folder == "malformed":
            if row["quiloader_ok"] and row["uic_ok"]:
                failures.append("%s is in malformed/ but both oracles passed" % rel)
            if not str(row["notes"]).strip():
                failures.append("%s is missing an expected-error note" % rel)
            expected = meta.get("expect", "")
            blob = "%s\n%s" % (row["quiloader_error"], row["uic_stderr"])
            if expected and expected not in blob:
                failures.append("%s error did not contain %r (got %s)" % (rel, expected, blob[:300]))
        else:
            if not row["quiloader_ok"] or not row["uic_ok"]:
                failures.append(
                    "%s quiloader_ok=%s uic_ok=%s loader=%s uic=%s"
                    % (
                        rel,
                        row["quiloader_ok"],
                        row["uic_ok"],
                        row["quiloader_error"],
                        row["uic_stderr"][:200],
                    )
                )
    coverage = _coverage(rows)
    if coverage["missing_elements"]:
        failures.append("missing elements: %s" % ", ".join(coverage["missing_elements"]))
    if coverage["missing_attributes"]:
        failures.append("missing attributes: %s" % ", ".join(coverage["missing_attributes"]))
    if coverage["missing_parents"]:
        failures.append("missing parents: %s" % json.dumps(coverage["missing_parents"]))
    if len(rows) < MIN_COMMITTED_UI:
        failures.append("committed .ui count %d is below %d" % (len(rows), MIN_COMMITTED_UI))
    if missing_prov:
        failures.append("ui files missing provenance: %s" % ", ".join(missing_prov))
    if extra_prov:
        failures.append("provenance entries without files: %s" % ", ".join(extra_prov))

    counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["folder"]] += 1
        if row["quiloader_ok"]:
            counts["quiloader_ok"] += 1
        if row["uic_ok"]:
            counts["uic_ok"] += 1
    counts["committed_ui"] = len(rows)

    public_rows = []
    for row in rows:
        public_rows.append(
            {
                "path": row["path"],
                "source": row["source"],
                "licence": row["licence"],
                "features": row["features"],
                "quiloader_ok": row["quiloader_ok"],
                "uic_ok": row["uic_ok"],
                "notes": row["notes"],
                "folder": row["folder"],
                "quiloader_error": row["quiloader_error"],
                "uic_stderr": row["uic_stderr"],
            }
        )
    manifest = {
        "validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "uic": uic,
        "uic_version": uic_version,
        "python": sys.version.split()[0],
        "counts": {key: counts[key] for key in sorted(counts)},
        "minimum_committed_ui": MIN_COMMITTED_UI,
        "feature_coverage": {
            "elements": coverage["elements"],
            "attributes": coverage["attributes"],
            "missing_elements": coverage["missing_elements"],
            "missing_attributes": coverage["missing_attributes"],
            "missing_parents": coverage["missing_parents"],
        },
        "files": public_rows,
    }
    (CORPUS / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print("uic %s" % uic_version)
    print("counts %s" % json.dumps(manifest["counts"], sort_keys=True))
    print(
        "coverage elements %d/%d attributes %d/%d"
        % (
            len(ELEMENTS) - len(coverage["missing_elements"]),
            len(ELEMENTS),
            len(ATTRIBUTES) - len(coverage["missing_attributes"]),
            len(ATTRIBUTES),
        )
    )
    if failures:
        print("FAILED %d" % len(failures))
        for line in failures:
            print(line)
        return 1
    print("OK")
    return 0


def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "--load":
        sys.exit(_load_main(sys.argv[2]))
    sys.exit(validate())


if __name__ == "__main__":
    main()
