"""Filesystem utilities shared across app modules."""

from app.filesystem.trash import TrashMoveResult, move_path_to_trash

__all__ = ["TrashMoveResult", "move_path_to_trash"]
