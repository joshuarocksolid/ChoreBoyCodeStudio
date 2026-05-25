"""Frame, scope, and variable inspection for runner debug sessions."""

from __future__ import annotations

import threading
from types import FrameType, TracebackType
from typing import Mapping

from app.debug.safe_eval import UnsafeExpressionError, safe_evaluate_expression
from app.runner.debug.helpers import (
    MAX_CHILD_VARS,
    MAX_REPR_CHARS,
    MAX_TOP_LEVEL_VARS,
    filtered_globals,
    parse_int,
    safe_repr,
)


class InspectorMixin:
    """Frame registry, variable serialization, and eval handlers."""

    def _handle_select_frame(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        frame_id = parse_int(arguments.get("frame_id"))
        frame = self._frame_registry.get(frame_id)
        if frame is None:
            self._send_response(
                command_name="select_frame",
                command_id=command_id,
                success=False,
                body={},
                error_message="Unknown frame id.",
            )
            return
        self._selected_frame_id = frame_id
        scopes, scope_variables = self._build_scope_payloads(frame)
        self._send_response(
            command_name="select_frame",
            command_id=command_id,
            success=True,
            body={
                "selected_frame_id": frame_id,
                "scopes": scopes,
                "scope_variables": scope_variables,
            },
        )

    def _handle_expand_variable(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        parent_reference = parse_int(arguments.get("variables_reference"))
        target = self._object_registry.get(parent_reference)
        if target is None:
            self._send_response(
                command_name="expand_variable",
                command_id=command_id,
                success=False,
                body={"parent_reference": parent_reference},
                error_message="Unknown variable reference.",
            )
            return
        variables = self._serialize_children(target)
        self._send_response(
            command_name="expand_variable",
            command_id=command_id,
            success=True,
            body={
                "parent_reference": parent_reference,
                "variables": variables,
            },
        )

    def _handle_evaluate(self, *, command_id: str, arguments: Mapping[str, object]) -> None:
        expression = str(arguments.get("expression", "")).strip()
        frame_id = parse_int(arguments.get("frame_id")) or int(self._selected_frame_id)
        frame = self._frame_registry.get(frame_id)
        if not expression:
            self._send_response(
                command_name="evaluate",
                command_id=command_id,
                success=False,
                body={"expression": expression},
                error_message="Expression cannot be empty.",
            )
            return
        if frame is None:
            self._send_response(
                command_name="evaluate",
                command_id=command_id,
                success=False,
                body={"expression": expression},
                error_message="Unknown frame id for evaluation.",
            )
            return
        try:
            unsafe = bool(arguments.get("unsafe", False))
            if unsafe:
                value = eval(expression, frame.f_globals, frame.f_locals)  # noqa: S307 - explicit unsafe debugger mode
            else:
                value = safe_evaluate_expression(expression, frame.f_globals, frame.f_locals)
            result = self._serialize_variable(expression, value)
            self._send_response(
                command_name="evaluate",
                command_id=command_id,
                success=True,
                body={"expression": expression, "result": result, "unsafe": unsafe},
            )
        except UnsafeExpressionError as exc:
            self._send_response(
                command_name="evaluate",
                command_id=command_id,
                success=False,
                body={"expression": expression, "unsafe": False},
                error_message="Unsafe expression: %s" % (exc,),
            )
        except Exception as exc:
            self._send_response(
                command_name="evaluate",
                command_id=command_id,
                success=False,
                body={"expression": expression},
                error_message="%s: %s" % (type(exc).__name__, exc),
            )

    def _build_scope_payloads(self, frame: FrameType) -> tuple[list[dict[str, object]], dict[int, list[dict[str, object]]]]:
        scopes: list[dict[str, object]] = []
        scope_variables: dict[int, list[dict[str, object]]] = {}

        locals_reference = self._register_object(dict(frame.f_locals))
        locals_variables = self._serialize_named_mapping(dict(frame.f_locals), limit=MAX_TOP_LEVEL_VARS)
        scopes.append({"name": "Locals", "variables_reference": locals_reference})
        scope_variables[locals_reference] = locals_variables

        globals_view = filtered_globals(frame.f_globals)
        globals_reference = self._register_object(globals_view)
        globals_variables = self._serialize_named_mapping(globals_view, limit=MAX_TOP_LEVEL_VARS)
        scopes.append({"name": "Globals", "variables_reference": globals_reference, "expensive": True})
        scope_variables[globals_reference] = globals_variables

        return scopes, scope_variables

    def _collect_frame_chain(self, frame: FrameType, *, thread_id: int) -> list[dict[str, object]]:
        frames: list[dict[str, object]] = []
        current_frame: FrameType | None = frame
        while current_frame is not None:
            frame_id = self._register_frame(current_frame)
            frames.append(
                {
                    "frame_id": frame_id,
                    "thread_id": thread_id,
                    "file_path": self._display_file_path(current_frame.f_code.co_filename),
                    "line_number": int(current_frame.f_lineno),
                    "function_name": str(current_frame.f_code.co_name),
                }
            )
            current_frame = current_frame.f_back
        return frames

    def _thread_payload(self, current_thread_id: int) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for thread in threading.enumerate():
            payload.append(
                {
                    "thread_id": int(thread.ident or 0),
                    "name": thread.name,
                    "is_current": int(thread.ident or 0) == current_thread_id,
                }
            )
        if not payload:
            payload.append({"thread_id": current_thread_id, "name": "MainThread", "is_current": True})
        return payload

    def _serialize_named_mapping(self, mapping_value: Mapping[str, object], *, limit: int) -> list[dict[str, object]]:
        items = sorted(mapping_value.items(), key=lambda item: item[0])[:limit]
        return [self._serialize_variable(name, value) for name, value in items]

    def _serialize_children(self, value: object) -> list[dict[str, object]]:
        children: list[dict[str, object]] = []
        if isinstance(value, dict):
            items = list(value.items())[:MAX_CHILD_VARS]
            for child_key, child_value in items:
                children.append(self._serialize_variable(repr(child_key), child_value))
            return children
        if isinstance(value, (list, tuple)):
            for index, child_value in enumerate(list(value)[:MAX_CHILD_VARS]):
                children.append(self._serialize_variable("[%s]" % (index,), child_value))
            return children
        if isinstance(value, set):
            sorted_values = sorted([repr(item) for item in value])[:MAX_CHILD_VARS]
            for index, child_value in enumerate(sorted_values):
                children.append(self._serialize_variable("{%s}" % (index,), child_value))
            return children
        if hasattr(value, "__dict__"):
            attributes = sorted(vars(value).items(), key=lambda item: item[0])[:MAX_CHILD_VARS]
            for child_name, child_value in attributes:
                children.append(self._serialize_variable(child_name, child_value))
        return children

    def _serialize_variable(self, name: str, value: object) -> dict[str, object]:
        type_name = type(value).__name__
        value_repr = safe_repr(value)
        named_child_count = None
        indexed_child_count = None
        variables_reference = 0
        if isinstance(value, dict):
            named_child_count = len(value)
            variables_reference = self._register_object(value) if value else 0
        elif isinstance(value, (list, tuple)):
            indexed_child_count = len(value)
            variables_reference = self._register_object(value) if value else 0
        elif isinstance(value, set):
            indexed_child_count = len(value)
            variables_reference = self._register_object(value) if value else 0
        elif hasattr(value, "__dict__"):
            named_child_count = len(vars(value))
            variables_reference = self._register_object(value) if vars(value) else 0
        return {
            "name": str(name),
            "value_repr": value_repr,
            "type_name": type_name,
            "variables_reference": variables_reference,
            "named_child_count": named_child_count,
            "indexed_child_count": indexed_child_count,
            "truncated": len(value_repr) >= MAX_REPR_CHARS,
            "error_message": "",
        }

    def _register_frame(self, frame: FrameType) -> int:
        frame_id = len(self._frame_registry) + 1
        self._frame_registry[frame_id] = frame
        return frame_id

    def _register_object(self, value: object) -> int:
        reference = len(self._object_registry) + 1
        self._object_registry[reference] = value
        return reference

    def _reset_pause_state(self) -> None:
        self._frame_registry.clear()
        self._object_registry.clear()
        self._selected_frame_id = 0

    def _display_file_path(self, runtime_file_path: str) -> str:
        normalized = str(runtime_file_path)
        return self._source_map_by_runtime.get(normalized, normalized)
