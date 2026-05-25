"""Shared pytest outcome and node-kind vocabulary."""

from __future__ import annotations

from typing import Literal

TestOutcome = Literal["passed", "failed", "skipped", "error", "not_run"]
TestNodeKind = Literal["file", "class", "function"]
