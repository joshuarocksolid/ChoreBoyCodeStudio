from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class _ConnectionConfig:
    jdbc: str
    user: str
    password: str


class ConnectionPool:
    def __init__(self) -> None:
        self._configs: Dict[str, _ConnectionConfig] = {}

    def add(self, connection_id: str, jdbc: str, user: str, password: str) -> None:
        if not connection_id:
            raise ValueError("connection_id is required")
        if not jdbc:
            raise ValueError("jdbc is required")
        self._configs[connection_id] = _ConnectionConfig(jdbc=jdbc, user=user, password=password)

    def remove(self, connection_id: str) -> None:
        self._configs.pop(connection_id, None)

    def has(self, connection_id: str) -> bool:
        return connection_id in self._configs

    def get(self, connection_id: str) -> Dict[str, str]:
        config = self._configs.get(connection_id)
        if config is None:
            raise KeyError(connection_id)
        return {"jdbc": config.jdbc, "user": config.user, "password": config.password}

    def list_ids(self) -> List[str]:
        return sorted(self._configs.keys())

    def clear(self) -> None:
        self._configs.clear()
