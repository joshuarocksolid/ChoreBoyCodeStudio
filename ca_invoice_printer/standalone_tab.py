import datetime
import json
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from jasper_bridge import (
    DateParam,
    DateTimeParam,
    ImageParam,
    IntegerParam,
    Report,
    TimeParam,
    compile_jrxml,
    quick_pdf,
)
from ca_invoice_printer.error_handling import show_error_dialog

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class StandaloneTab(QWidget):
    def __init__(self, status_callback=None, runtime_callback=None, parent=None):
        super().__init__(parent)
        self._status_callback = status_callback
        self._runtime_callback = runtime_callback
        self.current_report = None
        self._build_ui()
        self._set_default_paths()
        self._seed_default_params()
        self._refresh_data_source_controls()
        self._update_actions()

    def _build_ui(self):
        page = QVBoxLayout(self)

        report_group = QGroupBox("Standalone Report", self)
        report_layout = QFormLayout(report_group)
        report_row = QHBoxLayout()
        self.report_input = QLineEdit("", report_group)
        self.report_browse_button = QPushButton("Browse", report_group)
        self.compile_button = QPushButton("Compile", report_group)
        self.info_button = QPushButton("Info", report_group)
        report_row.addWidget(self.report_input)
        report_row.addWidget(self.report_browse_button)
        report_row.addWidget(self.compile_button)
        report_row.addWidget(self.info_button)
        report_layout.addRow("JRXML:", report_row)

        data_group = QGroupBox("Data Source", self)
        data_layout = QGridLayout(data_group)
        self.none_radio = QRadioButton("None", data_group)
        self.json_radio = QRadioButton("JSON", data_group)
        self.csv_radio = QRadioButton("CSV", data_group)
        self.none_radio.setChecked(True)
        data_layout.addWidget(self.none_radio, 0, 0)
        data_layout.addWidget(self.json_radio, 0, 1)
        data_layout.addWidget(self.csv_radio, 0, 2)

        self.json_path_input = QLineEdit("", data_group)
        self.json_browse_button = QPushButton("Browse", data_group)
        self.csv_path_input = QLineEdit("", data_group)
        self.csv_browse_button = QPushButton("Browse", data_group)
        self.select_expression_input = QLineEdit("", data_group)
        self.select_expression_input.setPlaceholderText("Optional JSON select expression")

        data_layout.addWidget(QLabel("JSON file:", data_group), 1, 0)
        data_layout.addWidget(self.json_path_input, 1, 1)
        data_layout.addWidget(self.json_browse_button, 1, 2)
        data_layout.addWidget(QLabel("CSV file:", data_group), 2, 0)
        data_layout.addWidget(self.csv_path_input, 2, 1)
        data_layout.addWidget(self.csv_browse_button, 2, 2)
        data_layout.addWidget(QLabel("Select expression:", data_group), 3, 0)
        data_layout.addWidget(self.select_expression_input, 3, 1, 1, 2)

        params_group = QGroupBox("Parameters", self)
        params_layout = QVBoxLayout(params_group)
        self.params_table = QTableWidget(0, 3, params_group)
        self.params_table.setHorizontalHeaderLabels(["Name", "Type", "Value"])
        self.params_table.horizontalHeader().setSectionResizeMode(0, self.params_table.horizontalHeader().Stretch)
        self.params_table.horizontalHeader().setSectionResizeMode(1, self.params_table.horizontalHeader().ResizeToContents)
        self.params_table.horizontalHeader().setSectionResizeMode(2, self.params_table.horizontalHeader().Stretch)
        self.params_table.verticalHeader().setVisible(False)
        params_layout.addWidget(self.params_table)
        params_buttons = QHBoxLayout()
        self.add_param_button = QPushButton("Add Row", params_group)
        self.remove_param_button = QPushButton("Remove Row", params_group)
        self.pick_image_button = QPushButton("Pick Image", params_group)
        params_buttons.addWidget(self.add_param_button)
        params_buttons.addWidget(self.remove_param_button)
        params_buttons.addWidget(self.pick_image_button)
        params_buttons.addStretch()
        params_layout.addLayout(params_buttons)

        options_group = QGroupBox("Options", self)
        options_layout = QHBoxLayout(options_group)
        self.validate_params_input = QCheckBox("Validate parameters", options_group)
        options_layout.addWidget(self.validate_params_input)
        options_layout.addStretch()

        actions_group = QGroupBox("Actions", self)
        actions_layout = QHBoxLayout(actions_group)
        self.fill_button = QPushButton("Fill", actions_group)
        self.quick_pdf_button = QPushButton("Quick PDF", actions_group)
        self.preview_button = QPushButton("Preview", actions_group)
        self.print_button = QPushButton("Print", actions_group)
        actions_layout.addWidget(self.fill_button)
        actions_layout.addWidget(self.quick_pdf_button)
        actions_layout.addWidget(self.preview_button)
        actions_layout.addWidget(self.print_button)
        actions_layout.addStretch()

        export_group = QGroupBox("Export", self)
        export_layout = QVBoxLayout(export_group)
        export_row = QHBoxLayout()
        self.export_format_combo = QComboBox(export_group)
        self.export_format_combo.addItem("PDF", "pdf")
        self.export_format_combo.addItem("HTML", "html")
        self.export_format_combo.addItem("CSV", "csv")
        self.export_format_combo.addItem("XLS", "xls")
        self.export_format_combo.addItem("XLSX", "xlsx")
        self.export_format_combo.addItem("Text", "text")
        self.export_format_combo.addItem("XML", "xml")
        self.export_button = QPushButton("Export", export_group)
        export_row.addWidget(self.export_format_combo)
        export_row.addWidget(self.export_button)
        export_row.addStretch()
        export_layout.addLayout(export_row)

        self.batch_checkboxes = {}
        batch_row = QHBoxLayout()
        for format_name in ("pdf", "png", "html", "csv", "xls", "xlsx", "text", "xml"):
            checkbox = QCheckBox(format_name.upper(), export_group)
            self.batch_checkboxes[format_name] = checkbox
            batch_row.addWidget(checkbox)
        batch_row.addStretch()
        export_layout.addLayout(batch_row)
        batch_actions = QHBoxLayout()
        self.batch_export_button = QPushButton("Batch Export", export_group)
        batch_actions.addWidget(self.batch_export_button)
        batch_actions.addStretch()
        export_layout.addLayout(batch_actions)

        state_group = QGroupBox("Report State", self)
        state_layout = QHBoxLayout(state_group)
        self.compiled_state = QLabel("Compiled: no", state_group)
        self.filled_state = QLabel("Filled: no", state_group)
        self.page_count_state = QLabel("Pages: 0", state_group)
        state_layout.addWidget(self.compiled_state)
        state_layout.addWidget(self.filled_state)
        state_layout.addWidget(self.page_count_state)
        state_layout.addStretch()

        page.addWidget(report_group)
        page.addWidget(data_group)
        page.addWidget(params_group)
        page.addWidget(options_group)
        page.addWidget(actions_group)
        page.addWidget(export_group)
        page.addWidget(state_group)

        self.report_browse_button.clicked.connect(self._pick_report)
        self.compile_button.clicked.connect(self._compile_report)
        self.info_button.clicked.connect(self._show_report_info)
        self.none_radio.toggled.connect(self._refresh_data_source_controls)
        self.json_radio.toggled.connect(self._refresh_data_source_controls)
        self.csv_radio.toggled.connect(self._refresh_data_source_controls)
        self.json_browse_button.clicked.connect(self._pick_json)
        self.csv_browse_button.clicked.connect(self._pick_csv)
        self.add_param_button.clicked.connect(self._add_param_row)
        self.remove_param_button.clicked.connect(self._remove_param_rows)
        self.pick_image_button.clicked.connect(self._pick_image_for_selected_row)
        self.fill_button.clicked.connect(self._fill_report)
        self.quick_pdf_button.clicked.connect(self._run_quick_pdf)
        self.preview_button.clicked.connect(self._preview_report)
        self.print_button.clicked.connect(self._print_report)
        self.export_button.clicked.connect(self._export_single)
        self.batch_export_button.clicked.connect(self._export_batch)

    def _set_default_paths(self):
        self.report_input.setText(os.path.join(BASE_DIR, "reports", "demo_params.jrxml"))
        self.json_path_input.setText(os.path.join(BASE_DIR, "reports", "sample_data.json"))
        self.csv_path_input.setText(os.path.join(BASE_DIR, "reports", "sample_data.csv"))

    def _seed_default_params(self):
        now = datetime.datetime.now()
        defaults = [
            ("TITLE", "String", "Standalone Demo"),
            ("QUANTITY", "Long", "3"),
            ("PRICE", "Float", "42.50"),
            ("PAID", "Boolean", "true"),
            ("INVOICE_DATE", "Date", now.strftime("%Y-%m-%d")),
            ("START_TIME", "Time", now.strftime("%H:%M:%S")),
            ("UPDATED_AT", "DateTime", now.strftime("%Y-%m-%dT%H:%M:%S")),
            ("NOTES", "String", "Demonstration run"),
            ("LOGO", "Image", ""),
        ]
        for name, kind, value in defaults:
            self._add_param_row(name=name, param_type=kind, value=value)

    def _add_param_row(self, _checked=False, name="", param_type="String", value=""):
        row = self.params_table.rowCount()
        self.params_table.insertRow(row)
        self.params_table.setItem(row, 0, QTableWidgetItem(name))
        type_combo = QComboBox(self.params_table)
        type_combo.addItems(["String", "Long", "Integer", "Float", "Boolean", "Date", "Time", "DateTime", "Image"])
        index = type_combo.findText(param_type)
        if index >= 0:
            type_combo.setCurrentIndex(index)
        self.params_table.setCellWidget(row, 1, type_combo)
        self.params_table.setItem(row, 2, QTableWidgetItem(value))

    def _remove_param_rows(self):
        rows = sorted({item.row() for item in self.params_table.selectedItems()}, reverse=True)
        if not rows and self.params_table.currentRow() >= 0:
            rows = [self.params_table.currentRow()]
        for row in rows:
            self.params_table.removeRow(row)

    def _pick_image_for_selected_row(self):
        row = self.params_table.currentRow()
        if row < 0:
            self._show_error("Parameter image", ValueError("Select a parameter row first."))
            return
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Image Parameter",
            os.path.dirname(self.report_input.text().strip()) or BASE_DIR,
            "Image Files (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All Files (*)",
        )
        if not image_path:
            return
        type_combo = self.params_table.cellWidget(row, 1)
        if isinstance(type_combo, QComboBox):
            image_index = type_combo.findText("Image")
            if image_index >= 0:
                type_combo.setCurrentIndex(image_index)
        value_item = self.params_table.item(row, 2)
        if value_item is None:
            value_item = QTableWidgetItem("")
            self.params_table.setItem(row, 2, value_item)
        value_item.setText(image_path)

    def _pick_report(self):
        start_dir = os.path.dirname(self.report_input.text().strip()) or BASE_DIR
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select JRXML",
            start_dir,
            "Jasper Reports (*.jrxml *.jasper);;All Files (*)",
        )
        if path:
            self.report_input.setText(path)

    def _pick_json(self):
        start_dir = os.path.dirname(self.json_path_input.text().strip()) or BASE_DIR
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select JSON file",
            start_dir,
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            self.json_path_input.setText(path)

    def _pick_csv(self):
        start_dir = os.path.dirname(self.csv_path_input.text().strip()) or BASE_DIR
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV file",
            start_dir,
            "CSV Files (*.csv);;All Files (*)",
        )
        if path:
            self.csv_path_input.setText(path)

    def _refresh_data_source_controls(self):
        json_selected = self.json_radio.isChecked()
        csv_selected = self.csv_radio.isChecked()
        self.json_path_input.setEnabled(json_selected)
        self.json_browse_button.setEnabled(json_selected)
        self.select_expression_input.setEnabled(json_selected)
        self.csv_path_input.setEnabled(csv_selected)
        self.csv_browse_button.setEnabled(csv_selected)

    def _selected_data_mode(self):
        if self.json_radio.isChecked():
            return "json"
        if self.csv_radio.isChecked():
            return "csv"
        return "none"

    def _require_report_path(self):
        path = self.report_input.text().strip()
        if not path:
            raise ValueError("Select a JRXML/JASPER file.")
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        return path

    def _build_fill_kwargs(self):
        kwargs = {
            "params": self._collect_params(),
            "validate_params": self.validate_params_input.isChecked(),
        }
        mode = self._selected_data_mode()
        if mode == "json":
            json_path = self.json_path_input.text().strip()
            if not json_path or not os.path.isfile(json_path):
                raise FileNotFoundError(json_path or "JSON file path is empty")
            kwargs["json_file"] = json_path
            expression = self.select_expression_input.text().strip()
            if expression:
                kwargs["select_expression"] = expression
        elif mode == "csv":
            csv_path = self.csv_path_input.text().strip()
            if not csv_path or not os.path.isfile(csv_path):
                raise FileNotFoundError(csv_path or "CSV file path is empty")
            kwargs["csv_file"] = csv_path
        return kwargs

    def _collect_params(self):
        params = {}
        for row in range(self.params_table.rowCount()):
            name_item = self.params_table.item(row, 0)
            value_item = self.params_table.item(row, 2)
            type_widget = self.params_table.cellWidget(row, 1)
            name = name_item.text().strip() if name_item is not None else ""
            raw_value = value_item.text().strip() if value_item is not None else ""
            param_type = type_widget.currentText() if isinstance(type_widget, QComboBox) else "String"
            if not name:
                continue
            if param_type != "String" and raw_value == "":
                continue
            params[name] = self._parse_param_value(param_type, raw_value, row + 1, name)
        return params

    def _parse_param_value(self, param_type, raw_value, row_number, name):
        try:
            if param_type == "String":
                return raw_value
            if param_type == "Long":
                return int(raw_value)
            if param_type == "Integer":
                return IntegerParam(int(raw_value))
            if param_type == "Float":
                return float(raw_value)
            if param_type == "Boolean":
                lowered = raw_value.lower()
                if lowered in ("true", "1", "yes", "y", "on"):
                    return True
                if lowered in ("false", "0", "no", "n", "off"):
                    return False
                raise ValueError("Expected true/false")
            if param_type == "Date":
                parsed = datetime.datetime.strptime(raw_value, "%Y-%m-%d")
                return DateParam(parsed.year, parsed.month, parsed.day)
            if param_type == "Time":
                parsed = datetime.datetime.strptime(raw_value, "%H:%M:%S")
                return TimeParam(parsed.hour, parsed.minute, parsed.second)
            if param_type == "DateTime":
                parsed = None
                for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                    try:
                        parsed = datetime.datetime.strptime(raw_value, fmt)
                        break
                    except ValueError:
                        continue
                if parsed is None:
                    raise ValueError("Expected YYYY-MM-DDTHH:MM:SS")
                return DateTimeParam(
                    parsed.year,
                    parsed.month,
                    parsed.day,
                    parsed.hour,
                    parsed.minute,
                    parsed.second,
                )
            if param_type == "Image":
                return ImageParam(raw_value)
        except Exception as exc:
            raise ValueError("Row {} ({}) invalid: {}".format(row_number, name, exc))
        raise ValueError("Unsupported parameter type: {}".format(param_type))

    def _compile_report(self):
        try:
            report_path = self._require_report_path()
        except Exception as exc:
            self._show_error("Compile failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            output = compile_jrxml(report_path)
            self._notify("Compiled report to {}".format(output), 5000)
        except Exception as exc:
            self._show_error("Compile failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _show_report_info(self):
        try:
            report_path = self._require_report_path()
        except Exception as exc:
            self._show_error("Report info failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            info = Report(report_path).info(refresh=True)
            details = json.dumps(info, indent=2, sort_keys=True)
            summary = "Name: {}\nParameters: {}\nFields: {}".format(
                info.get("name", ""),
                len(info.get("parameters", [])),
                len(info.get("fields", [])),
            )
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Information)
            dialog.setWindowTitle("Report info")
            dialog.setText(summary)
            dialog.setDetailedText(details)
            dialog.exec_()
            self._notify("Loaded report metadata", 5000)
        except Exception as exc:
            self._show_error("Report info failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _fill_report(self):
        try:
            report_path = self._require_report_path()
            fill_kwargs = self._build_fill_kwargs()
        except Exception as exc:
            self._show_error("Fill failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = Report(report_path)
            response = report.fill(**fill_kwargs)
            self.current_report = report
            self._set_report_state(report)
            self._update_actions()
            self._notify("Filled report with {} pages".format(response.get("page_count", 0)), 5000)
        except Exception as exc:
            self._show_error("Fill failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _run_quick_pdf(self):
        try:
            report_path = self._require_report_path()
            fill_kwargs = self._build_fill_kwargs()
        except Exception as exc:
            self._show_error("Quick PDF failed", exc)
            return

        start_dir = os.path.dirname(report_path) or BASE_DIR
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Quick PDF Output",
            os.path.join(start_dir, "standalone_quick.pdf"),
            "PDF Files (*.pdf);;All Files (*)",
        )
        if not output_path:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = quick_pdf(report_path, output_path, **fill_kwargs)
            self._notify("Quick PDF exported to {}".format(result), 5000)
        except Exception as exc:
            self._show_error("Quick PDF failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _require_filled_report(self):
        if self.current_report is None or not self.current_report.is_filled:
            raise ValueError("Fill the report first.")
        return self.current_report

    def _preview_report(self):
        try:
            report = self._require_filled_report()
        except Exception as exc:
            self._show_error("Preview failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report.preview(title="Standalone Report Preview")
            self._notify("Preview ready", 4000)
        except Exception as exc:
            self._show_error("Preview failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _print_report(self):
        try:
            report = self._require_filled_report()
        except Exception as exc:
            self._show_error("Print failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            printed = report.print(title="Standalone Report")
            if printed:
                self._notify("Print job completed", 5000)
            else:
                self._notify("Print cancelled", 5000)
        except Exception as exc:
            self._show_error("Print failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _export_single(self):
        try:
            report = self._require_filled_report()
        except Exception as exc:
            self._show_error("Export failed", exc)
            return

        export_format = self.export_format_combo.currentData()
        output_path = self._pick_single_export_path(export_format)
        if not output_path:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if export_format == "pdf":
                result = report.export_pdf(output_path)
            elif export_format == "html":
                result = report.export_html(output_path)
            elif export_format == "csv":
                result = report.export_csv(output_path)
            elif export_format == "xls":
                result = report.export_xls(output_path)
            elif export_format == "xlsx":
                result = report.export_xlsx(output_path)
            elif export_format == "text":
                result = report.export_text(output_path, page_width=120, page_height=60)
            elif export_format == "xml":
                result = report.export_xml(output_path)
            else:
                raise ValueError("Unsupported format {}".format(export_format))
            self._notify("Exported {}".format(result), 5000)
        except Exception as exc:
            self._show_error("Export failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _pick_single_export_path(self, export_format):
        mapping = {
            "pdf": ("PDF Files (*.pdf)", "standalone_export.pdf"),
            "html": ("HTML Files (*.html)", "standalone_export.html"),
            "csv": ("CSV Files (*.csv)", "standalone_export.csv"),
            "xls": ("XLS Files (*.xls)", "standalone_export.xls"),
            "xlsx": ("XLSX Files (*.xlsx)", "standalone_export.xlsx"),
            "text": ("Text Files (*.txt)", "standalone_export.txt"),
            "xml": ("XML Files (*.xml)", "standalone_export.xml"),
        }
        file_filter, default_name = mapping[export_format]
        start_dir = os.path.dirname(self.report_input.text().strip()) or BASE_DIR
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            os.path.join(start_dir, default_name),
            file_filter + ";;All Files (*)",
        )
        return output_path

    def _export_batch(self):
        selected_formats = [fmt for fmt, checkbox in self.batch_checkboxes.items() if checkbox.isChecked()]
        if not selected_formats:
            self._show_error("Batch export failed", ValueError("Select at least one format."))
            return

        try:
            report_path = self._require_report_path()
            fill_kwargs = self._build_fill_kwargs()
        except Exception as exc:
            self._show_error("Batch export failed", exc)
            return

        start_dir = os.path.dirname(self.report_input.text().strip()) or BASE_DIR
        output_dir = QFileDialog.getExistingDirectory(self, "Select batch export directory", start_dir)
        if not output_dir:
            return

        exports = self._build_export_specs(output_dir, selected_formats)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = Report(report_path)
            response = report.export_all(exports=exports, **fill_kwargs)
            self.current_report = report
            self._set_report_state(report)
            self._update_actions()
            self._notify(
                "Batch export completed: {} format(s)".format(len(response.get("exports", []))),
                6000,
            )
        except Exception as exc:
            self._show_error("Batch export failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _build_export_specs(self, output_dir, selected_formats):
        specs = []
        for export_format in selected_formats:
            if export_format == "png":
                specs.append(
                    {
                        "format": "png",
                        "output_dir": os.path.join(output_dir, "standalone_png_pages"),
                        "zoom": 2.0,
                    }
                )
                continue
            if export_format == "text":
                specs.append(
                    {
                        "format": "text",
                        "output_path": os.path.join(output_dir, "standalone_batch_text.txt"),
                        "page_width": 120,
                        "page_height": 60,
                    }
                )
                continue
            extension = "txt" if export_format == "text" else export_format
            specs.append(
                {
                    "format": export_format,
                    "output_path": os.path.join(
                        output_dir,
                        "standalone_batch_{}.{}".format(export_format, extension),
                    ),
                }
            )
        return specs

    def _set_report_state(self, report):
        if report is None:
            self.compiled_state.setText("Compiled: no")
            self.filled_state.setText("Filled: no")
            self.page_count_state.setText("Pages: 0")
            return
        self.compiled_state.setText("Compiled: {}".format("yes" if report.is_compiled else "no"))
        self.filled_state.setText("Filled: {}".format("yes" if report.is_filled else "no"))
        self.page_count_state.setText("Pages: {}".format(report.page_count))

    def _update_actions(self):
        has_filled = self.current_report is not None and self.current_report.is_filled
        self.preview_button.setEnabled(has_filled)
        self.print_button.setEnabled(has_filled)
        self.export_button.setEnabled(has_filled)

    def _notify(self, message, timeout_ms=5000):
        if self._status_callback is not None:
            self._status_callback(str(message), int(timeout_ms))

    def _notify_runtime(self):
        if self._runtime_callback is not None:
            self._runtime_callback()

    def _show_error(self, title, exc):
        message = show_error_dialog(self, title, exc)
        self._notify(message, 7000)
        self._notify_runtime()
