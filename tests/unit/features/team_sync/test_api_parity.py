"""Pyright reads these assignments and rejects a fake or service that drifts from TeamSyncApi."""

from __future__ import annotations

from app.features.team_sync.api import TeamSyncApi
from app.features.team_sync.core.fake import InMemoryTeamSync
from app.features.team_sync.core.service import TeamSyncService


def _fake_matches_contract() -> TeamSyncApi:
    api: TeamSyncApi = InMemoryTeamSync()
    return api


def _service_matches_contract() -> TeamSyncApi:
    api: TeamSyncApi = TeamSyncService("")
    return api
