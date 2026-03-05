from __future__ import annotations

import base64
import datetime
import os
from typing import Any, Dict, List, Optional

from .errors import ParameterError


class ImageParam:
    def __init__(self, path: Optional[str] = None, *, data: Optional[bytes] = None) -> None:
        if (path is None and data is None) or (path is not None and data is not None):
            raise ParameterError("ImageParam requires exactly one of path or data")
        if path is not None:
            resolved_path = os.path.abspath(path)
            if not os.path.exists(resolved_path):
                raise ParameterError("Image path does not exist: {}".format(resolved_path))
            self.path = resolved_path
            self.data = None
        else:
            if not isinstance(data, (bytes, bytearray)):
                raise ParameterError("ImageParam data must be bytes")
            self.path = None
            self.data = bytes(data)


class DateParam:
    def __init__(self, year: int, month: int, day: int) -> None:
        self._value = datetime.date(year, month, day)

    def to_iso(self) -> str:
        return self._value.isoformat()


class TimeParam:
    def __init__(self, hour: int, minute: int, second: int) -> None:
        self._value = datetime.time(hour, minute, second)

    def to_iso(self) -> str:
        return self._value.strftime("%H:%M:%S")


class DateTimeParam:
    def __init__(
        self, year: int, month: int, day: int, hour: int, minute: int, second: int
    ) -> None:
        self._value = datetime.datetime(year, month, day, hour, minute, second)

    def to_iso(self) -> str:
        return self._value.strftime("%Y-%m-%dT%H:%M:%S")


def serialize_params(params: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if params is None:
        return []
    if not isinstance(params, dict):
        raise ParameterError("params must be a dict of name -> value")

    serialized: List[Dict[str, Any]] = []
    for name, value in params.items():
        if not isinstance(name, str) or not name:
            raise ParameterError("Parameter names must be non-empty strings")

        if isinstance(value, str):
            serialized.append({"name": name, "type": "string", "value": value})
            continue
        if isinstance(value, bool):
            serialized.append({"name": name, "type": "boolean", "value": value})
            continue
        if isinstance(value, int):
            serialized.append({"name": name, "type": "long", "value": value})
            continue
        if isinstance(value, float):
            serialized.append({"name": name, "type": "double", "value": value})
            continue
        if isinstance(value, (bytes, bytearray)):
            encoded = base64.b64encode(bytes(value)).decode("ascii")
            serialized.append({"name": name, "type": "bytes", "value": encoded})
            continue
        if isinstance(value, ImageParam):
            if value.path is not None:
                serialized.append({"name": name, "type": "image_path", "value": value.path})
            else:
                encoded = base64.b64encode(value.data).decode("ascii")
                serialized.append({"name": name, "type": "image_bytes", "value": encoded})
            continue
        if isinstance(value, DateParam):
            serialized.append({"name": name, "type": "date", "value": value.to_iso()})
            continue
        if isinstance(value, TimeParam):
            serialized.append({"name": name, "type": "time", "value": value.to_iso()})
            continue
        if isinstance(value, DateTimeParam):
            serialized.append({"name": name, "type": "datetime", "value": value.to_iso()})
            continue
        if isinstance(value, datetime.datetime):
            serialized.append(
                {
                    "name": name,
                    "type": "datetime",
                    "value": value.strftime("%Y-%m-%dT%H:%M:%S"),
                }
            )
            continue
        if isinstance(value, datetime.date):
            serialized.append({"name": name, "type": "date", "value": value.isoformat()})
            continue
        if isinstance(value, datetime.time):
            serialized.append({"name": name, "type": "time", "value": value.strftime("%H:%M:%S")})
            continue

        raise ParameterError(
            "Unsupported parameter type for {}: {}".format(name, type(value).__name__)
        )

    return serialized
