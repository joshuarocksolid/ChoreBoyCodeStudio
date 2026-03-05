from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any, Dict, List

from . import jvm
from .errors import ExportError

logger = logging.getLogger(__name__)


def _invoke_export(command: Dict[str, Any]) -> Dict[str, Any]:
    _, env_ptr = jvm.ensure_jvm()
    raw_output = jvm.call_java_main(env_ptr, "JasperBridge", [json.dumps(command)])
    try:
        response = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise ExportError(
            "Failed to parse Java response as JSON: {}".format(raw_output),
            java_stacktrace=str(exc),
        )

    if response.get("status") != "ok":
        raise ExportError(
            response.get("error_message", "Export failed"),
            java_stacktrace=response.get("stacktrace"),
        )
    return response


def _prepare_output_file(output_path: str, overwrite: bool) -> str:
    output_abs = os.path.abspath(output_path)
    if not overwrite and os.path.exists(output_abs):
        raise FileExistsError(output_abs)
    output_parent = os.path.dirname(output_abs)
    if output_parent:
        os.makedirs(output_parent, exist_ok=True)
    return output_abs


def export_pdf(output_path: str, overwrite: bool = True) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting PDF to %s", output_abs)
    response = _invoke_export({"action": "export_pdf", "output_path": output_abs})
    return response.get("output_path", output_abs)


def export_png(output_dir: str, zoom: float = 1.0, overwrite: bool = True) -> List[str]:
    output_abs = os.path.abspath(output_dir)
    os.makedirs(output_abs, exist_ok=True)

    if not overwrite:
        existing = glob.glob(os.path.join(output_abs, "page_*.png"))
        if existing:
            raise FileExistsError(existing[0])

    logger.info("Exporting PNG pages to %s zoom=%s", output_abs, zoom)
    response = _invoke_export(
        {"action": "export_png", "output_dir": output_abs, "zoom": zoom}
    )
    pages = response.get("pages", [])
    return [os.path.abspath(path) for path in pages]


def export_html(output_path: str, overwrite: bool = True) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting HTML to %s", output_abs)
    response = _invoke_export({"action": "export_html", "output_path": output_abs})
    return response.get("output_path", output_abs)


def export_csv(output_path: str, overwrite: bool = True) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting CSV to %s", output_abs)
    response = _invoke_export({"action": "export_csv", "output_path": output_abs})
    return response.get("output_path", output_abs)


def export_xls(output_path: str, overwrite: bool = True) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting XLS to %s", output_abs)
    response = _invoke_export({"action": "export_xls", "output_path": output_abs})
    return response.get("output_path", output_abs)


def export_text(
    output_path: str,
    page_width: int = 120,
    page_height: int = 60,
    overwrite: bool = True,
) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting text to %s", output_abs)
    response = _invoke_export(
        {
            "action": "export_text",
            "output_path": output_abs,
            "page_width": int(page_width),
            "page_height": int(page_height),
        }
    )
    return response.get("output_path", output_abs)


def export_xml(output_path: str, overwrite: bool = True) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting XML to %s", output_abs)
    response = _invoke_export({"action": "export_xml", "output_path": output_abs})
    return response.get("output_path", output_abs)


def export_xlsx(output_path: str, overwrite: bool = True) -> str:
    output_abs = _prepare_output_file(output_path, overwrite)
    logger.info("Exporting XLSX to %s", output_abs)
    response = _invoke_export({"action": "export_xlsx", "output_path": output_abs})
    return response.get("output_path", output_abs)
