from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

from .errors import CompileError
from . import jvm

logger = logging.getLogger(__name__)


def _parse_response(raw_output: str) -> Dict[str, Any]:
    try:
        return json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise CompileError(
            "Failed to parse Java response as JSON: {}".format(raw_output),
            java_stacktrace=str(exc),
        )


def compile_jrxml(jrxml_path: str, output_path: str = None) -> str:
    jrxml_abs = os.path.abspath(jrxml_path)
    if not os.path.exists(jrxml_abs):
        raise FileNotFoundError(jrxml_abs)

    if output_path is None:
        if jrxml_abs.endswith(".jrxml"):
            output_abs = jrxml_abs[:-6] + "jasper"
        else:
            output_abs = jrxml_abs + ".jasper"
    else:
        output_abs = os.path.abspath(output_path)

    output_parent = os.path.dirname(output_abs)
    if output_parent:
        os.makedirs(output_parent, exist_ok=True)

    command = {
        "action": "compile",
        "jrxml": jrxml_abs,
        "output": output_abs,
    }
    logger.info("Compiling JRXML %s -> %s", jrxml_abs, output_abs)

    _, env_ptr = jvm.ensure_jvm()
    raw_output = jvm.call_java_main(env_ptr, "JasperBridge", [json.dumps(command)])
    response = _parse_response(raw_output)

    if response.get("status") != "ok":
        raise CompileError(
            response.get("error_message", "JRXML compilation failed"),
            java_stacktrace=response.get("stacktrace"),
        )

    jasper_path = response.get("jasper_path", output_abs)
    logger.info("Compilation complete: %s", jasper_path)
    return jasper_path
