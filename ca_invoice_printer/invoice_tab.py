import json
import os

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAbstractItemView,
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
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import db
from jasper_bridge import ConnectionPool, Report
from ca_invoice_printer.error_handling import JASPER_ERROR_TYPES, show_error_dialog

USER_ROLE = 32
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POOL_ID = "invoice_default"


class InvoiceTab(QWidget):
    def __init__(self, status_callback=None, runtime_callback=None, parent=None):
        super().__init__(parent)
        self._status_callback = status_callback
        self._runtime_callback = runtime_callback
        self.connection_pool = ConnectionPool()
        self.connection = None
        self.all_invoices = []
        self.filtered_invoices = []
        self.last_report = None
        self._build_ui()
        self._set_default_report_path()
        self._update_actions()

    def _build_ui(self):
        page = QVBoxLayout(self)

        conn_group = QGroupBox("Database Connection", self)
        conn_layout = QGridLayout(conn_group)
        self.host_input = QLineEdit("localhost", conn_group)
        self.port_input = QLineEdit("5432", conn_group)
        self.database_input = QLineEdit("classicaccounting", conn_group)
        self.user_input = QLineEdit("postgres", conn_group)
        self.password_input = QLineEdit("", conn_group)
        self.password_input.setEchoMode(QLineEdit.Password)
        self.connect_button = QPushButton("Connect", conn_group)
        self.refresh_button = QPushButton("Refresh Invoices", conn_group)
        self.connection_state = QLabel("Not connected", conn_group)

        conn_layout.addWidget(QLabel("Host:", conn_group), 0, 0)
        conn_layout.addWidget(self.host_input, 0, 1)
        conn_layout.addWidget(QLabel("Port:", conn_group), 0, 2)
        conn_layout.addWidget(self.port_input, 0, 3)
        conn_layout.addWidget(QLabel("Database:", conn_group), 0, 4)
        conn_layout.addWidget(self.database_input, 0, 5)
        conn_layout.addWidget(QLabel("User:", conn_group), 1, 0)
        conn_layout.addWidget(self.user_input, 1, 1)
        conn_layout.addWidget(QLabel("Password:", conn_group), 1, 2)
        conn_layout.addWidget(self.password_input, 1, 3)
        conn_layout.addWidget(self.connect_button, 1, 4)
        conn_layout.addWidget(self.refresh_button, 1, 5)
        conn_layout.addWidget(self.connection_state, 2, 0, 1, 6)

        invoices_group = QGroupBox("Invoices", self)
        invoices_layout = QVBoxLayout(invoices_group)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit("", invoices_group)
        self.search_input.setPlaceholderText("Search by doc number, customer, status, date, total, or trans id")
        search_row.addWidget(QLabel("Search:", invoices_group))
        search_row.addWidget(self.search_input)
        invoices_layout.addLayout(search_row)

        self.invoice_table = QTableWidget(0, 5, invoices_group)
        self.invoice_table.setHorizontalHeaderLabels(["Doc #", "Customer", "Date", "Status", "Total"])
        self.invoice_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.invoice_table.setSelectionMode(QTableWidget.SingleSelection)
        self.invoice_table.setEditTriggers(QAbstractItemView.EditTriggers(0))
        self.invoice_table.setSortingEnabled(True)
        self.invoice_table.verticalHeader().setVisible(False)
        self.invoice_table.horizontalHeader().setStretchLastSection(True)
        self.invoice_table.horizontalHeader().setSectionResizeMode(0, self.invoice_table.horizontalHeader().Stretch)
        self.invoice_table.horizontalHeader().setSectionResizeMode(1, self.invoice_table.horizontalHeader().Stretch)
        self.invoice_table.horizontalHeader().setSectionResizeMode(2, self.invoice_table.horizontalHeader().ResizeToContents)
        self.invoice_table.horizontalHeader().setSectionResizeMode(3, self.invoice_table.horizontalHeader().ResizeToContents)
        self.invoice_table.horizontalHeader().setSectionResizeMode(4, self.invoice_table.horizontalHeader().ResizeToContents)
        invoices_layout.addWidget(self.invoice_table)

        report_group = QGroupBox("Invoice Report Actions", self)
        report_layout = QFormLayout(report_group)
        report_row = QHBoxLayout()
        self.report_input = QLineEdit("", report_group)
        self.browse_button = QPushButton("Browse", report_group)
        self.info_button = QPushButton("Info", report_group)
        report_row.addWidget(self.report_input)
        report_row.addWidget(self.browse_button)
        report_row.addWidget(self.info_button)
        report_layout.addRow("Report (JRXML/JASPER):", report_row)

        actions_row = QHBoxLayout()
        self.preview_button = QPushButton("Preview", report_group)
        self.print_button = QPushButton("Print", report_group)
        actions_row.addWidget(self.preview_button)
        actions_row.addWidget(self.print_button)
        actions_row.addStretch()
        report_layout.addRow("Actions:", actions_row)

        print_options_row = QHBoxLayout()
        self.copies_input = QSpinBox(report_group)
        self.copies_input.setMinimum(1)
        self.copies_input.setMaximum(99)
        self.copies_input.setValue(1)
        self.collate_input = QCheckBox("Collate", report_group)
        self.duplex_input = QCheckBox("Duplex", report_group)
        print_options_row.addWidget(QLabel("Copies:", report_group))
        print_options_row.addWidget(self.copies_input)
        print_options_row.addWidget(self.collate_input)
        print_options_row.addWidget(self.duplex_input)
        print_options_row.addStretch()
        report_layout.addRow("Print options:", print_options_row)

        export_row = QHBoxLayout()
        self.export_format_combo = QComboBox(report_group)
        self.export_format_combo.addItem("PDF", "pdf")
        self.export_format_combo.addItem("HTML", "html")
        self.export_format_combo.addItem("CSV", "csv")
        self.export_format_combo.addItem("XLS", "xls")
        self.export_format_combo.addItem("XLSX", "xlsx")
        self.export_format_combo.addItem("Text", "text")
        self.export_format_combo.addItem("XML", "xml")
        self.export_button = QPushButton("Export", report_group)
        export_row.addWidget(self.export_format_combo)
        export_row.addWidget(self.export_button)
        export_row.addStretch()
        report_layout.addRow("Export:", export_row)

        state_row = QHBoxLayout()
        self.compiled_state = QLabel("Compiled: no", report_group)
        self.filled_state = QLabel("Filled: no", report_group)
        self.page_count_state = QLabel("Pages: 0", report_group)
        state_row.addWidget(self.compiled_state)
        state_row.addWidget(self.filled_state)
        state_row.addWidget(self.page_count_state)
        state_row.addStretch()
        report_layout.addRow("Report state:", state_row)

        page.addWidget(conn_group)
        page.addWidget(invoices_group)
        page.addWidget(report_group)

        self.connect_button.clicked.connect(self._toggle_connection)
        self.refresh_button.clicked.connect(self._load_invoices)
        self.search_input.textChanged.connect(self._apply_filter)
        self.invoice_table.itemSelectionChanged.connect(self._update_actions)
        self.invoice_table.cellDoubleClicked.connect(self._preview_selected)
        self.browse_button.clicked.connect(self._pick_report)
        self.info_button.clicked.connect(self._show_report_info)
        self.preview_button.clicked.connect(self._preview_selected)
        self.print_button.clicked.connect(self._print_selected)
        self.export_button.clicked.connect(self._export_selected)
        self.report_input.textChanged.connect(self._update_actions)

    def _set_default_report_path(self):
        preferred = "/home/joshua/Documents/CA_2025.0.22/classicaccounting/reports/CustomerInvoice.jrxml"
        bundled = os.path.join(BASE_DIR, "reports", "CustomerInvoice.jrxml")
        if os.path.isfile(preferred):
            self.report_input.setText(preferred)
            return
        self.report_input.setText(bundled)

    def _pick_report(self):
        start_dir = os.path.dirname(self.report_input.text().strip()) or BASE_DIR
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Jasper Report",
            start_dir,
            "Jasper Reports (*.jrxml *.jasper);;All Files (*)",
        )
        if path:
            self.report_input.setText(path)

    def _is_connected(self):
        return self.connection is not None

    def _toggle_connection(self):
        if self._is_connected():
            self._disconnect()
            return
        self._connect()

    def _disconnect(self):
        if self.connection is not None:
            db.close(self.connection)
            self.connection = None
        if self.connection_pool.has(POOL_ID):
            self.connection_pool.remove(POOL_ID)
        self.connect_button.setText("Connect")
        self.connection_state.setText("Not connected")
        self.all_invoices = []
        self.filtered_invoices = []
        self._render_table()
        self._set_report_state(None)
        self._update_actions()
        self._notify("Disconnected", 4000)
        self._notify_runtime()

    def _connect(self):
        host = self.host_input.text().strip() or "localhost"
        port = self.port_input.text().strip() or "5432"
        database = self.database_input.text().strip()
        user = self.user_input.text().strip()
        password = self.password_input.text()
        if not database or not user:
            self._show_error("Missing fields", ValueError("Database and user are required."))
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.connection = db.connect(host, port, database, user, password)
            self.connection_pool.add(
                POOL_ID,
                self._build_jdbc_url(host, port, database),
                user,
                password,
            )
            self.connect_button.setText("Disconnect")
            self.connection_state.setText("Connected")
            self._notify("Connected to Classic Accounting database", 5000)
            self._load_invoices()
        except Exception as exc:
            self.connection = None
            self._show_error("Connection failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _load_invoices(self):
        if not self._is_connected():
            self._show_error("Not connected", ValueError("Connect to the database first."))
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.all_invoices = db.fetch_invoices(self.connection, "", 500)
            self._apply_filter()
            self._notify("Loaded {} invoices".format(len(self.all_invoices)), 5000)
        except Exception as exc:
            self._show_error("Failed to load invoices", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _apply_filter(self):
        term = self.search_input.text().strip().lower()
        if not term:
            self.filtered_invoices = list(self.all_invoices)
            self._render_table()
            return

        matched = []
        for invoice in self.all_invoices:
            values = [
                str(invoice.get("doc_number", "")),
                str(invoice.get("customer", "")),
                str(invoice.get("status", "")),
                self._format_date(invoice.get("transdate")),
                self._format_total(invoice.get("total")),
                str(invoice.get("transid", "")),
            ]
            blob = " ".join(values).lower()
            if term in blob:
                matched.append(invoice)
        self.filtered_invoices = matched
        self._render_table()

    def _render_table(self):
        self.invoice_table.setSortingEnabled(False)
        self.invoice_table.setRowCount(len(self.filtered_invoices))
        for row_index, invoice in enumerate(self.filtered_invoices):
            transid = invoice.get("transid")
            doc_item = QTableWidgetItem(str(invoice.get("doc_number", "")))
            doc_item.setData(USER_ROLE, transid)
            customer_item = QTableWidgetItem(str(invoice.get("customer", "")))
            date_item = QTableWidgetItem(self._format_date(invoice.get("transdate")))
            status_item = QTableWidgetItem(str(invoice.get("status", "")))
            total_item = QTableWidgetItem(self._format_total(invoice.get("total")))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.invoice_table.setItem(row_index, 0, doc_item)
            self.invoice_table.setItem(row_index, 1, customer_item)
            self.invoice_table.setItem(row_index, 2, date_item)
            self.invoice_table.setItem(row_index, 3, status_item)
            self.invoice_table.setItem(row_index, 4, total_item)
        self.invoice_table.setSortingEnabled(True)
        self._update_actions()

    def _selected_transid(self):
        row = self.invoice_table.currentRow()
        if row < 0:
            return None
        item = self.invoice_table.item(row, 0)
        if item is None:
            return None
        return item.data(USER_ROLE)

    def _selected_report_path(self):
        report_path = self.report_input.text().strip()
        if not report_path:
            raise ValueError("Select a Jasper report file.")
        if not os.path.isfile(report_path):
            raise FileNotFoundError(report_path)
        return report_path

    def _require_selection_and_report(self):
        transid = self._selected_transid()
        if transid is None:
            raise ValueError("Select an invoice first.")
        report_path = self._selected_report_path()
        return transid, report_path

    def _current_connection_config(self):
        host = self.host_input.text().strip() or "localhost"
        port = self.port_input.text().strip() or "5432"
        database = self.database_input.text().strip()
        user = self.user_input.text().strip()
        password = self.password_input.text()
        if not database or not user:
            raise ValueError("Database and user are required.")

        self.connection_pool.add(
            POOL_ID,
            self._build_jdbc_url(host, port, database),
            user,
            password,
        )
        return self.connection_pool.get(POOL_ID)

    def _build_jdbc_url(self, host, port, database):
        return "jdbc:postgresql://{}:{}/{}".format(host, int(port), database)

    def _build_filled_report(self, report_path, transid):
        cfg = self._current_connection_config()
        report = Report(report_path)
        report.compile()
        report.fill(
            jdbc=cfg["jdbc"],
            user=cfg["user"],
            password=cfg["password"],
            params={
                "?TransID": int(transid),
                "?CompNameAddr": "",
            },
        )
        self.last_report = report
        self._set_report_state(report)
        return report

    def _preview_selected(self):
        try:
            transid, report_path = self._require_selection_and_report()
        except Exception as exc:
            self._show_error("Preview failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = self._build_filled_report(report_path, transid)
            report.preview(title="Invoice Preview")
            self._notify("Preview ready", 4000)
        except JASPER_ERROR_TYPES as exc:
            self._show_error("Preview failed", exc)
        except Exception as exc:
            self._show_error("Preview failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _print_selected(self):
        try:
            transid, report_path = self._require_selection_and_report()
        except Exception as exc:
            self._show_error("Print failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = self._build_filled_report(report_path, transid)
            printed = report.print(
                title="Print Invoice",
                copies=self.copies_input.value(),
                collate=self.collate_input.isChecked(),
                duplex=self.duplex_input.isChecked(),
            )
            if printed:
                self._notify("Print job completed", 5000)
            else:
                self._notify("Print cancelled", 5000)
        except JASPER_ERROR_TYPES as exc:
            self._show_error("Print failed", exc)
        except Exception as exc:
            self._show_error("Print failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _export_selected(self):
        try:
            transid, report_path = self._require_selection_and_report()
        except Exception as exc:
            self._show_error("Export failed", exc)
            return

        export_format = self.export_format_combo.currentData()
        output_path = self._pick_export_path(export_format, transid)
        if not output_path:
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            report = self._build_filled_report(report_path, transid)
            result = self._run_export(report, export_format, output_path)
            if isinstance(result, list):
                self._notify("Exported {} files".format(len(result)), 5000)
            else:
                self._notify("Exported {}".format(result), 5000)
        except JASPER_ERROR_TYPES as exc:
            self._show_error("Export failed", exc)
        except Exception as exc:
            self._show_error("Export failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _run_export(self, report, export_format, output_path):
        if export_format == "pdf":
            return report.export_pdf(output_path)
        if export_format == "html":
            return report.export_html(output_path)
        if export_format == "csv":
            return report.export_csv(output_path)
        if export_format == "xls":
            return report.export_xls(output_path)
        if export_format == "xlsx":
            return report.export_xlsx(output_path)
        if export_format == "text":
            return report.export_text(output_path, page_width=120, page_height=60)
        if export_format == "xml":
            return report.export_xml(output_path)
        raise ValueError("Unsupported export format: {}".format(export_format))

    def _pick_export_path(self, export_format, transid):
        extensions = {
            "pdf": ("PDF Files (*.pdf)", ".pdf"),
            "html": ("HTML Files (*.html)", ".html"),
            "csv": ("CSV Files (*.csv)", ".csv"),
            "xls": ("XLS Files (*.xls)", ".xls"),
            "xlsx": ("XLSX Files (*.xlsx)", ".xlsx"),
            "text": ("Text Files (*.txt)", ".txt"),
            "xml": ("XML Files (*.xml)", ".xml"),
        }
        file_filter, ext = extensions[export_format]
        start_dir = os.path.dirname(self.report_input.text().strip()) or BASE_DIR
        default_name = "invoice_{}{}".format(transid, ext)
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Invoice",
            os.path.join(start_dir, default_name),
            file_filter + ";;All Files (*)",
        )
        return output_path

    def _show_report_info(self):
        try:
            report_path = self._selected_report_path()
        except Exception as exc:
            self._show_error("Report info failed", exc)
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            info = Report(report_path).info(refresh=True)
            parameters = info.get("parameters", [])
            visible_params = [item for item in parameters if not item.get("system_defined")]
            details = json.dumps(info, indent=2, sort_keys=True)
            message = "Name: {}\nParameters: {}\nFields: {}".format(
                info.get("name", ""),
                len(visible_params),
                len(info.get("fields", [])),
            )
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Information)
            dialog.setWindowTitle("Report info")
            dialog.setText(message)
            dialog.setDetailedText(details)
            dialog.exec_()
            self._notify("Loaded report metadata", 5000)
        except JASPER_ERROR_TYPES as exc:
            self._show_error("Report info failed", exc)
        except Exception as exc:
            self._show_error("Report info failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

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
        has_selection = self._selected_transid() is not None
        has_report = os.path.isfile(self.report_input.text().strip())
        can_run = has_selection and has_report
        self.refresh_button.setEnabled(self._is_connected())
        self.preview_button.setEnabled(can_run)
        self.print_button.setEnabled(can_run)
        self.export_button.setEnabled(can_run)
        self.info_button.setEnabled(has_report)

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

    def _format_date(self, value):
        if value is None:
            return ""
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")
        return str(value)

    def _format_total(self, value):
        if value is None:
            return ""
        try:
            return "{:,.2f}".format(float(value))
        except Exception:
            return str(value)

    def shutdown(self):
        if self.connection is not None:
            db.close(self.connection)
            self.connection = None
