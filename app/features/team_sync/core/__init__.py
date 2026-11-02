"""Team Sync engine: pure Python, no Qt. The only package that imports dulwich."""

from __future__ import annotations


class TeamSyncError(Exception):
    """A Team Sync operation stopped. The message is what the UI can show."""


__all__ = ["TeamSyncError"]
