"""Results the scenario runner writes. Callers observe this shape."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


SCENARIO_IDS = (
    "smoke",
    "gates",
    "cb1",
    "cb2",
    "cb3",
    "cb3-latency",
    "cb4",
    "reload",
    "cb5",
    "cb6",
    "cb7",
    "cb8",
    "cb9",
    "cb10",
    "ts",
)

# FreeCAD 1.0 acceptance. smoke is a separate launch check.
ALL_IDS = tuple(scenario_id for scenario_id in SCENARIO_IDS if scenario_id != "smoke")

STATUSES = ("pass", "fail", "error", "skipped")


@dataclass
class Check:
    name: str
    ok: bool
    expected: str
    actual: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ok": bool(self.ok),
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class Shot:
    name: str
    path: str
    kind: str

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "path": self.path, "kind": self.kind}


@dataclass
class ScenarioResult:
    scenario: str
    status: str
    started: str
    duration_s: float
    checks: List[Check] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    screenshots: List[Shot] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "status": self.status,
            "started": self.started,
            "duration_s": round(float(self.duration_s), 3),
            "checks": [item.to_dict() for item in self.checks],
            "metrics": self.metrics,
            "screenshots": [item.to_dict() for item in self.screenshots],
            "notes": self.notes,
        }


class Skip(Exception):
    """Scenario is not runnable. The message is the results.json notes."""


def status_for(checks: List[Check], *, skipped: Optional[str], error: Optional[str]) -> str:
    """pass when every check is ok. skipped and error win over checks."""
    if skipped:
        return "skipped"
    if error:
        return "error"
    if not checks:
        return "error"
    if all(item.ok for item in checks):
        return "pass"
    return "fail"


def summarize(results: List[ScenarioResult], *, run_id: str, started: str, duration_s: float, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    counts = {name: 0 for name in STATUSES}
    for result in results:
        if result.status in counts:
            counts[result.status] += 1
        else:
            counts["error"] += 1
    payload: Dict[str, Any] = {
        "run_id": run_id,
        "started": started,
        "duration_s": round(float(duration_s), 3),
        "counts": counts,
        "scenarios": [result.to_dict() for result in results],
    }
    if extra:
        payload.update(extra)
    return payload


def summary_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# verify-cbcs {}".format(payload.get("run_id", "")),
        "",
        "Wall clock {:.1f}s.".format(float(payload.get("duration_s") or 0)),
        "",
        "| scenario | status | duration_s | checks |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload.get("scenarios") or []:
        checks = row.get("checks") or []
        ok = sum(1 for item in checks if item.get("ok"))
        lines.append(
            "| {} | {} | {} | {}/{} |".format(
                row.get("scenario"),
                row.get("status"),
                row.get("duration_s"),
                ok,
                len(checks),
            )
        )
    counts = payload.get("counts") or {}
    lines.append("")
    lines.append(
        "Counts: pass {pass}, fail {fail}, error {error}, skipped {skipped}.".format(
            **{key: counts.get(key, 0) for key in STATUSES}
        )
    )
    lines.append("")
    return "\n".join(lines)


def canonical_listing(entries: List[Dict[str, Any]]) -> str:
    """Stable text for a home-tree hash. Order and size changes both move the hash."""
    rows = []
    for entry in entries:
        rows.append(
            "{}\t{}\t{}".format(
                entry.get("path", ""),
                entry.get("kind", ""),
                entry.get("size", ""),
            )
        )
    rows.sort()
    return "\n".join(rows) + ("\n" if rows else "")


def listing_sha256(entries: List[Dict[str, Any]]) -> str:
    return hashlib.sha256(canonical_listing(entries).encode("utf-8")).hexdigest()
