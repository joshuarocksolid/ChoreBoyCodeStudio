from __future__ import annotations

import datetime
import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from . import compiler as compiler_module
from . import exporter as exporter_module
from . import filler as filler_module
from . import jvm
from .errors import ExportError, FillError, ParameterError
from .params import DateParam, DateTimeParam, ImageParam, TimeParam


class Report:
    def __init__(self, jrxml_path: str) -> None:
        self._jrxml_path = os.path.abspath(jrxml_path)
        if not os.path.exists(self._jrxml_path):
            raise FileNotFoundError(self._jrxml_path)
        self._compiled = False
        self._filled = False
        self._compiled_path: Optional[str] = None
        self._page_count = 0
        self._last_page_images: List[str] = []
        self._info_cache: Optional[Dict[str, Any]] = None

    def compile(self, output: str = None) -> str:
        compiled_path = compiler_module.compile_jrxml(self._jrxml_path, output)
        self._compiled_path = compiled_path
        self._compiled = True
        return compiled_path

    def fill(
        self,
        params: Dict[str, Any] = None,
        jdbc: str = None,
        user: str = None,
        password: str = None,
        json_file: str = None,
        select_expression: str = None,
        csv_file: str = None,
        subreport_dir: str = None,
        validate_params: bool = False,
    ) -> Dict[str, Any]:
        if validate_params:
            self._validate_parameters(params or {}, subreport_dir=subreport_dir)
        response = filler_module.fill_report(
            self._compiled_path or self._jrxml_path,
            params=params,
            jdbc=jdbc,
            user=user,
            password=password,
            json_file=json_file,
            select_expression=select_expression,
            csv_file=csv_file,
            subreport_dir=subreport_dir,
        )
        self._compiled = True
        self._filled = True
        self._page_count = int(response.get("page_count", 0))
        return response

    def export_pdf(self, path: str, overwrite: bool = True) -> str:
        self._require_filled()
        return exporter_module.export_pdf(path, overwrite=overwrite)

    def export_png(self, path: str, zoom: float = 1.0, overwrite: bool = True) -> List[str]:
        self._require_filled()
        pages = exporter_module.export_png(path, zoom=zoom, overwrite=overwrite)
        self._last_page_images = pages
        return pages

    def export_html(self, path: str, overwrite: bool = True) -> str:
        self._require_filled()
        return exporter_module.export_html(path, overwrite=overwrite)

    def export_csv(self, path: str, overwrite: bool = True) -> str:
        self._require_filled()
        return exporter_module.export_csv(path, overwrite=overwrite)

    def export_xls(self, path: str, overwrite: bool = True) -> str:
        self._require_filled()
        return exporter_module.export_xls(path, overwrite=overwrite)

    def export_text(
        self,
        path: str,
        page_width: int = 120,
        page_height: int = 60,
        overwrite: bool = True,
    ) -> str:
        self._require_filled()
        return exporter_module.export_text(
            path,
            page_width=page_width,
            page_height=page_height,
            overwrite=overwrite,
        )

    def export_xml(self, path: str, overwrite: bool = True) -> str:
        self._require_filled()
        return exporter_module.export_xml(path, overwrite=overwrite)

    def export_xlsx(self, path: str, overwrite: bool = True) -> str:
        self._require_filled()
        return exporter_module.export_xlsx(path, overwrite=overwrite)

    def preview(self, title: str = "Report Preview") -> None:
        self._require_filled()
        if not self._last_page_images:
            temp_dir = tempfile.mkdtemp(prefix="jasper_bridge_preview_")
            self._last_page_images = self.export_png(temp_dir, zoom=2.0, overwrite=True)
        from .preview import preview as preview_pages

        preview_pages(self._last_page_images, title=title)

    def print(self, title: str = "Print Report", **kwargs) -> bool:
        self._require_filled()
        if not self._last_page_images:
            temp_dir = tempfile.mkdtemp(prefix="jasper_bridge_print_")
            self._last_page_images = self.export_png(temp_dir, zoom=2.0, overwrite=True)
        from .printing import print_report

        return print_report(self._last_page_images, title=title, **kwargs)

    def info(self, refresh: bool = False) -> Dict[str, Any]:
        if self._info_cache is not None and not refresh:
            return dict(self._info_cache)

        command = {
            "action": "info",
            "jrxml_or_jasper": self._compiled_path or self._jrxml_path,
        }
        _, env_ptr = jvm.ensure_jvm()
        raw_output = jvm.call_java_main(env_ptr, "JasperBridge", [json.dumps(command)])
        try:
            response = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            raise FillError(
                "Failed to parse Java metadata response: {}".format(raw_output),
                java_stacktrace=str(exc),
            )
        if response.get("status") != "ok":
            raise FillError(
                response.get("error_message", "Failed to read report metadata"),
                java_stacktrace=response.get("stacktrace"),
            )
        self._info_cache = response
        return dict(response)

    def export_all(
        self,
        exports: List[Dict[str, Any]],
        params: Dict[str, Any] = None,
        jdbc: str = None,
        user: str = None,
        password: str = None,
        json_file: str = None,
        select_expression: str = None,
        csv_file: str = None,
        subreport_dir: str = None,
        validate_params: bool = False,
    ) -> Dict[str, Any]:
        if validate_params:
            self._validate_parameters(params or {}, subreport_dir=subreport_dir)

        response = filler_module.fill_and_export(
            self._compiled_path or self._jrxml_path,
            exports=exports,
            params=params,
            jdbc=jdbc,
            user=user,
            password=password,
            json_file=json_file,
            select_expression=select_expression,
            csv_file=csv_file,
            subreport_dir=subreport_dir,
        )
        self._compiled = True
        self._filled = True
        self._page_count = int(response.get("page_count", 0))

        for export_entry in response.get("exports", []):
            if export_entry.get("format") == "png":
                self._last_page_images = export_entry.get("pages", [])
                break
        return response

    @property
    def page_count(self) -> int:
        return self._page_count

    @property
    def is_compiled(self) -> bool:
        return self._compiled

    @property
    def is_filled(self) -> bool:
        return self._filled

    def _require_filled(self) -> None:
        if not self._filled:
            raise ExportError("Report has not been filled. Call fill() first.")

    def _validate_parameters(self, params: Dict[str, Any], subreport_dir: str = None) -> None:
        metadata = self.info()
        declared_params = metadata.get("parameters", [])
        effective_params = dict(params or {})
        if subreport_dir and "SUBREPORT_DIR" not in effective_params:
            resolved = os.path.abspath(subreport_dir)
            if not resolved.endswith(os.sep):
                resolved = resolved + os.sep
            effective_params["SUBREPORT_DIR"] = resolved

        missing: List[str] = []
        mismatched: List[str] = []
        for parameter in declared_params:
            if parameter.get("system_defined"):
                continue
            name = parameter.get("name")
            if not name:
                continue
            has_default = bool(parameter.get("has_default"))
            if not has_default and name not in effective_params:
                missing.append(name)
                continue
            if name not in effective_params:
                continue
            expected = parameter.get("value_class_name") or parameter.get("type")
            if expected and not _matches_java_type(expected, effective_params[name]):
                mismatched.append("{} expected {}".format(name, expected))

        if missing or mismatched:
            details = []
            if missing:
                details.append("missing: {}".format(", ".join(sorted(missing))))
            if mismatched:
                details.append("mismatched: {}".format(", ".join(sorted(mismatched))))
            raise ParameterError("Parameter validation failed ({})".format("; ".join(details)))


def _matches_java_type(java_type: str, value: Any) -> bool:
    numeric_int_types = {
        "java.lang.Long",
        "java.lang.Integer",
        "java.lang.Short",
        "java.lang.Byte",
        "java.math.BigInteger",
    }
    numeric_float_types = {
        "java.lang.Double",
        "java.lang.Float",
        "java.math.BigDecimal",
        "double",
        "float",
    }
    if java_type in ("java.lang.String", "String"):
        return isinstance(value, str)
    if java_type in numeric_int_types:
        return isinstance(value, int) and not isinstance(value, bool)
    if java_type in numeric_float_types:
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if java_type in ("java.lang.Boolean", "boolean"):
        return isinstance(value, bool)
    if java_type in ("java.sql.Date",):
        return isinstance(value, DateParam) or isinstance(value, datetime.date)
    if java_type in ("java.sql.Time",):
        return isinstance(value, TimeParam) or isinstance(value, datetime.time)
    if java_type in ("java.sql.Timestamp", "java.util.Date"):
        return isinstance(value, DateTimeParam) or isinstance(value, datetime.datetime)
    if java_type in ("java.awt.Image", "java.awt.image.BufferedImage"):
        return isinstance(value, ImageParam) or isinstance(value, (bytes, bytearray))
    if java_type == "[B":
        return isinstance(value, (bytes, bytearray))
    return True


def compile_jrxml(jrxml_path: str, output_path: str = None) -> str:
    return compiler_module.compile_jrxml(jrxml_path, output_path)


def quick_pdf(jrxml_path: str, output_path: str, **fill_kwargs) -> str:
    report = Report(jrxml_path)
    report.fill(**fill_kwargs)
    return report.export_pdf(output_path)


def preview_pdf(pdf_path: str) -> None:
    pdf_abs = os.path.abspath(pdf_path)
    if not os.path.exists(pdf_abs):
        raise FileNotFoundError(pdf_abs)
    raise NotImplementedError("preview_pdf is not implemented in this release")
