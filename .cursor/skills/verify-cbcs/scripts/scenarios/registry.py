"""Scenario registry. all is the FreeCAD 1.0 acceptance, without smoke."""

from __future__ import annotations

from typing import Callable, Dict, List

from scenarios.model import ALL_IDS, SCENARIO_IDS

BLURBS = {
    "smoke": "Launch, Runtime ready, main-window grab, state dump",
    "gates": "Fresh install, runtime chip, Runtime Center, Python keyword color",
    "cb1": "Settings import, history OSError, fatal MainWindow RuntimeError",
    "cb2": "Plugin host PermissionError, same error on Run",
    "cb3": "Manual completion, Ctrl+Space, camelCase, tab, docs, off mode, console",
    "cb3-latency": "Median popup to_paint_ms under 150",
    "cb4": "Stepped drag, rename, cut-paste, missing file",
    "reload": "Clean reload, keep buffer, stale save, dirty keep",
    "cb5": "Tab drag, split, close group, restore after restart",
    "cb6": "Package five projects and read the runtime report",
    "cb7": "Run opens FreeCAD, log noise format, Keep and Stop",
    "cb8": "Example app install, replace, uninstall, forced failure, idesk launcher",
    "cb9": "Shop settings pointer, JSON-only share, missing parent",
    "cb10": "Macro/Apps migration into FreeCAD/Apps",
    "ts": "Tree-sitter colors for py, json, md, yaml, html; SQL is plain",
}


def load():
    from scenarios import (
        cb1,
        cb10,
        cb2,
        cb3,
        cb3_latency,
        cb4,
        cb5,
        cb6,
        cb7,
        cb8,
        cb9,
        gates,
        reload as reload_mod,
        smoke,
        ts,
    )

    return {
        "smoke": smoke.run,
        "gates": gates.run,
        "cb1": cb1.run,
        "cb2": cb2.run,
        "cb3": cb3.run,
        "cb3-latency": cb3_latency.run,
        "cb4": cb4.run,
        "reload": reload_mod.run,
        "cb5": cb5.run,
        "cb6": cb6.run,
        "cb7": cb7.run,
        "cb8": cb8.run,
        "cb9": cb9.run,
        "cb10": cb10.run,
        "ts": ts.run,
    }


def resolve(names: List[str]) -> List[str]:
    if names == ["all"]:
        return list(ALL_IDS)
    unknown = [name for name in names if name not in SCENARIO_IDS]
    if unknown:
        raise SystemExit("unknown scenario: " + ", ".join(unknown))
    return list(names)
