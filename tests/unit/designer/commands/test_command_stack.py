"""Unit tests for designer command stack."""

from __future__ import annotations

import pytest

from app.designer.commands import CommandStack, SnapshotCommand

pytestmark = pytest.mark.unit


def test_command_stack_undo_redo_applies_snapshots_in_order() -> None:
    applied: list[str] = []
    stack = CommandStack(apply_snapshot=applied.append)
    stack.push(SnapshotCommand("add", before_xml="<a/>", after_xml="<a><b/></a>"))
    stack.push(SnapshotCommand("layout", before_xml="<a><b/></a>", after_xml="<a><layout/></a>"))

    assert stack.can_undo is True
    assert stack.can_redo is False

    assert stack.undo() is True
    assert applied[-1] == "<a><b/></a>"
    assert stack.undo() is True
    assert applied[-1] == "<a/>"
    assert stack.can_undo is False

    assert stack.redo() is True
    assert applied[-1] == "<a><b/></a>"
    assert stack.redo() is True
    assert applied[-1] == "<a><layout/></a>"
    assert stack.can_redo is False


def test_command_stack_drops_redo_branch_after_new_push() -> None:
    applied: list[str] = []
    stack = CommandStack(apply_snapshot=applied.append)
    stack.push(SnapshotCommand("add", before_xml="A", after_xml="B"))
    stack.push(SnapshotCommand("edit", before_xml="B", after_xml="C"))
    assert stack.undo() is True
    stack.push(SnapshotCommand("replace", before_xml="B", after_xml="D"))

    assert stack.can_redo is False
    assert stack.undo() is True
    assert applied[-1] == "B"
