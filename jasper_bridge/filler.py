from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

from . import jvm
from .errors import DataSourceError, FillError, ParameterError
from .params import serialize_params

logger = logging.getLogger(__name__)


def _parse_response(raw_output: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise FillError(
            "Failed to parse Java response as JSON: {}".format(raw_output),
            java_stacktrace=str(exc),
        )


def _merged_params(params: Dict[str, Any], subreport_dir: str = None) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(params or {})
    if subreport_dir and "SUBREPORT_DIR" not in merged:
        resolved = os.path.abspath(subreport_dir)
        if not resolved.endswith(os.sep):
            resolved = resolved + os.sep
        merged["SUBREPORT_DIR"] = resolved
    return merged


def _base_fill_payload(
    jrxml_or_jasper: str,
    params: Dict[str, Any] = None,
    jdbc: str = None,
    user: str = None,
    password: str = None,
    json_file: str = None,
    select_expression: str = None,
    csv_file: str = None,
    subreport_dir: str = None,
) -> Dict[str, Any]:
    report_path = os.path.abspath(jrxml_or_jasper)
    if not os.path.exists(report_path):
        raise FileNotFoundError(report_path)

    payload: Dict[str, Any] = {"jrxml_or_jasper": report_path}
    if json_file:
        payload["json_file"] = os.path.abspath(json_file)
        if select_expression:
            payload["select_expression"] = select_expression
    elif csv_file:
        payload["csv_file"] = os.path.abspath(csv_file)
    elif jdbc:
        if user is None or password is None:
            raise DataSourceError("JDBC fill requires user and password")
        payload["jdbc_url"] = jdbc
        payload["user"] = user
        payload["pass"] = password

    merged_params = _merged_params(params, subreport_dir=subreport_dir)
    if merged_params:
        try:
            payload["params"] = serialize_params(merged_params)
        except ParameterError:
            raise
        except Exception as exc:
            raise ParameterError(str(exc))
    return payload


def _map_fill_error(response: Dict[str, Any]) -> None:
    error_type = response.get("error_type", "")
    message = response.get("error_message", "Report fill failed")
    stacktrace = response.get("stacktrace")
    if "SQLException" in error_type or "sql" in error_type.lower():
        raise DataSourceError(message, java_stacktrace=stacktrace)
    raise FillError(message, java_stacktrace=stacktrace)


def fill_report(
    jrxml_or_jasper: str,
    params: Dict[str, Any] = None,
    jdbc: str = None,
    user: str = None,
    password: str = None,
    json_file: str = None,
    select_expression: str = None,
    csv_file: str = None,
    subreport_dir: str = None,
) -> Dict[str, Any]:
    command = _base_fill_payload(
        jrxml_or_jasper,
        params=params,
        jdbc=jdbc,
        user=user,
        password=password,
        json_file=json_file,
        select_expression=select_expression,
        csv_file=csv_file,
        subreport_dir=subreport_dir,
    )

    if json_file:
        command["action"] = "fill_json"
    elif csv_file:
        command["action"] = "fill_csv"
    elif jdbc:
        command["action"] = "fill_jdbc"
    else:
        command["action"] = "fill_empty"

    logger.info("Filling report action=%s report=%s", command["action"], command["jrxml_or_jasper"])
    _, env_ptr = jvm.ensure_jvm()
    raw_output = jvm.call_java_main(env_ptr, "JasperBridge", [json.dumps(command)])
    response = _parse_response(raw_output)

    if response.get("status") != "ok":
        _map_fill_error(response)

    logger.info(
        "Fill complete action=%s pages=%s",
        command["action"],
        response.get("page_count"),
    )
    return response


def fill_and_export(
    jrxml_or_jasper: str,
    exports: List[Dict[str, Any]],
    params: Dict[str, Any] = None,
    jdbc: str = None,
    user: str = None,
    password: str = None,
    json_file: str = None,
    select_expression: str = None,
    csv_file: str = None,
    subreport_dir: str = None,
) -> Dict[str, Any]:
    if not exports:
        raise FillError("exports must contain at least one export spec")

    command = _base_fill_payload(
        jrxml_or_jasper,
        params=params,
        jdbc=jdbc,
        user=user,
        password=password,
        json_file=json_file,
        select_expression=select_expression,
        csv_file=csv_file,
        subreport_dir=subreport_dir,
    )
    command["action"] = "fill_and_export"
    command["exports"] = exports

    logger.info("Running fill_and_export with %d export spec(s)", len(exports))
    _, env_ptr = jvm.ensure_jvm()
    raw_output = jvm.call_java_main(env_ptr, "JasperBridge", [json.dumps(command)])
    response = _parse_response(raw_output)

    if response.get("status") != "ok":
        _map_fill_error(response)
    return response
