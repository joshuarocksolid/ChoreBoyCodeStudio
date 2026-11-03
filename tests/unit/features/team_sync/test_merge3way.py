"""Merge engine matrix from the Team Sync spec."""

from __future__ import annotations

from app.features.team_sync.core.merge3way import (
    both_lines,
    inspect_text,
    join_lines,
    merge_lines,
    merge_trees,
)


def test_non_overlapping_hunks_merge() -> None:
    base = ("alpha", "beta", "gamma")
    ours = ("ALPHA", "beta", "gamma")
    theirs = ("alpha", "beta", "GAMMA")
    merged = merge_lines(base, ours, theirs).merged_lines()
    assert merged == ("ALPHA", "beta", "GAMMA")


def test_identical_edits_merge_once() -> None:
    base = ("alpha", "beta", "gamma")
    edited = ("alpha", "BETA", "gamma")
    merged = merge_lines(base, edited, edited).merged_lines()
    assert merged == edited


def test_overlapping_edits_clash() -> None:
    base = ("alpha", "beta", "gamma")
    result = merge_lines(base, ("alpha", "ours", "gamma"), ("alpha", "theirs", "gamma"))
    assert result.merged_lines() is None
    assert len(result.clashes) == 1
    clash = result.clashes[0]
    assert clash.ours == ("ours",)
    assert clash.theirs == ("theirs",)
    assert clash.line == 2


def test_add_add_same_content_and_different_content() -> None:
    same = merge_trees({}, {"a.txt": b"one\n"}, {"a.txt": b"one\n"})
    assert same.clashes == ()
    assert same.files["a.txt"] == b"one\n"
    different = merge_trees({}, {"a.txt": b"one\n"}, {"a.txt": b"two\n"})
    assert len(different.clashes) == 1
    assert different.clashes[0].path == "a.txt"
    assert "a.txt" not in different.files or different.files.get("a.txt") is None


def test_delete_versus_edit_is_a_deleted_clash() -> None:
    base = {"a.txt": b"keep\n"}
    result = merge_trees(base, {"a.txt": b"keep\nedited\n"}, {})
    assert len(result.clashes) == 1
    assert result.clashes[0].kind == "deleted"
    assert result.clashes[0].ours_present is True
    assert result.clashes[0].theirs_present is False


def test_ui_form_is_a_whole_file_clash() -> None:
    base = {"form.ui": b"<widget>1</widget>\n"}
    result = merge_trees(
        base,
        {"form.ui": b"<widget>2</widget>\n"},
        {"form.ui": b"<widget>3</widget>\n"},
    )
    assert len(result.clashes) == 1
    assert result.clashes[0].kind == "form"


def test_binary_nul_is_a_whole_file_clash() -> None:
    base = {"pic.bin": b"aaa"}
    result = merge_trees(
        base,
        {"pic.bin": b"a\0b"},
        {"pic.bin": b"a\0c"},
    )
    assert result.clashes[0].kind == "binary"


def test_crlf_is_preserved() -> None:
    base = b"alpha\r\nbeta\r\ngamma\r\n"
    ours = b"ALPHA\r\nbeta\r\ngamma\r\n"
    theirs = b"alpha\r\nbeta\r\nGAMMA\r\n"
    result = merge_trees({"a.txt": base}, {"a.txt": ours}, {"a.txt": theirs})
    assert result.clashes == ()
    assert result.files["a.txt"] == b"ALPHA\r\nbeta\r\nGAMMA\r\n"


def test_missing_trailing_newline_is_preserved() -> None:
    base = b"alpha\nbeta"
    ours = b"ALPHA\nbeta"
    theirs = b"alpha\nBETA"
    result = merge_trees({"a.txt": base}, {"a.txt": ours}, {"a.txt": theirs})
    assert result.files["a.txt"] == b"ALPHA\nBETA"
    lines, sep, trailing = inspect_text(result.files["a.txt"])
    assert lines == ("ALPHA", "BETA")
    assert sep == "\n"
    assert trailing is False
    assert join_lines(lines, sep, trailing) == result.files["a.txt"]


def test_both_keeps_the_longer_prefix_line() -> None:
    assert both_lines(("return x",), ("return x + 1",)) == ("return x + 1",)
    assert both_lines(("left",), ("right",)) == ("left", "right")


def test_same_point_insertions_at_start_middle_and_end() -> None:
    cases = (
        ((), ("x",), ("y",)),
        (("a", "b"), ("a", "x", "b"), ("a", "y", "b")),
        (("a",), ("a", "x"), ("a", "y")),
    )
    for base, ours, theirs in cases:
        result = merge_lines(base, ours, theirs)
        assert result.merged_lines() is None
        assert len(result.clashes) == 1
        assert result.clashes[0].ours == tuple(line for line in ours if line not in base) or result.clashes[0].ours
        identical = merge_lines(base, ours, ours).merged_lines()
        assert identical == ours


def test_adjacent_edits_and_deletion_beside_an_edit_merge() -> None:
    adjacent = merge_lines(("a", "b", "c"), ("A", "b", "c"), ("a", "b", "C")).merged_lines()
    assert adjacent == ("A", "b", "C")
    deleted = merge_lines(("a", "b", "c"), ("a", "c"), ("a", "b", "C")).merged_lines()
    assert deleted == ("a", "C")


def test_trailing_newline_added_by_theirs_is_kept() -> None:
    base = b"alpha\nbeta"
    ours = b"ALPHA\nbeta"
    theirs = b"alpha\nBETA\n"
    result = merge_trees({"a.txt": base}, {"a.txt": ours}, {"a.txt": theirs})
    assert result.clashes == ()
    assert result.files["a.txt"] == b"ALPHA\nBETA\n"


def test_crlf_change_by_theirs_only_is_kept() -> None:
    base = b"alpha\nbeta\n"
    ours = b"ALPHA\nbeta\n"
    theirs = b"alpha\r\nBETA\r\n"
    result = merge_trees({"a.txt": base}, {"a.txt": ours}, {"a.txt": theirs})
    assert result.clashes == ()
    assert result.files["a.txt"] == b"ALPHA\r\nBETA\r\n"
