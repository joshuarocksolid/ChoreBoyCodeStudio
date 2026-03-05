import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENDOR_DIR = os.path.join(BASE_DIR, "vendor")
if os.path.isdir(VENDOR_DIR) and VENDOR_DIR not in sys.path:
    sys.path.insert(0, VENDOR_DIR)

USER_ROLE = 32

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import db
import printer


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.connection = None
        self.all_invoices = []
        self.filtered_invoices = []
        self.setWindowTitle("CA Invoice Printer Demo")
        self.resize(980, 640)
        self._build_ui()
        self._set_default_report_path()
        self._update_actions()

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)
        page = QVBoxLayout(root)

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

        search_group = QGroupBox("Invoices", self)
        search_layout = QVBoxLayout(search_group)
        search_row = QHBoxLayout()
        self.search_input = QLineEdit("", search_group)
        self.search_input.setPlaceholderText("Search by doc number, customer, status, date, or total")
        search_row.addWidget(QLabel("Search:", search_group))
        search_row.addWidget(self.search_input)
        search_layout.addLayout(search_row)

        self.invoice_table = QTableWidget(0, 5, search_group)
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
        search_layout.addWidget(self.invoice_table)

        report_group = QGroupBox("Printing", self)
        report_layout = QFormLayout(report_group)
        report_row = QHBoxLayout()
        self.report_input = QLineEdit("", report_group)
        self.browse_button = QPushButton("Browse", report_group)
        report_row.addWidget(self.report_input)
        report_row.addWidget(self.browse_button)
        action_row = QHBoxLayout()
        self.preview_button = QPushButton("Preview", report_group)
        self.print_button = QPushButton("Print", report_group)
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.print_button)
        action_row.addStretch()
        report_layout.addRow("Report (JRXML):", report_row)
        report_layout.addRow("", action_row)

        page.addWidget(conn_group)
        page.addWidget(search_group)
        page.addWidget(report_group)

        self.connect_button.clicked.connect(self._toggle_connection)
        self.refresh_button.clicked.connect(self._load_invoices)
        self.search_input.textChanged.connect(self._apply_filter)
        self.invoice_table.itemSelectionChanged.connect(self._update_actions)
        self.invoice_table.cellDoubleClicked.connect(self._preview_selected)
        self.browse_button.clicked.connect(self._pick_report)
        self.preview_button.clicked.connect(self._preview_selected)
        self.print_button.clicked.connect(self._print_selected)

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
            db.close(self.connection)
            self.connection = None
            self.connect_button.setText("Connect")
            self.connection_state.setText("Not connected")
            self.statusBar().showMessage("Disconnected", 4000)
            self.all_invoices = []
            self.filtered_invoices = []
            self._render_table()
            self._update_actions()
            return
        self._connect()

    def _connect(self):
        host = self.host_input.text().strip() or "localhost"
        port = self.port_input.text().strip() or "5432"
        database = self.database_input.text().strip()
        user = self.user_input.text().strip()
        password = self.password_input.text()
        if not database or not user:
            self._show_error("Missing fields", "Database and user are required.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.connection = db.connect(host, port, database, user, password)
            self.connect_button.setText("Disconnect")
            self.connection_state.setText("Connected")
            self.statusBar().showMessage("Connected to Classic Accounting database", 5000)
            self._load_invoices()
        except Exception as exc:
            self.connection = None
            self._show_error("Connection failed", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _load_invoices(self):
        if not self._is_connected():
            self._show_error("Not connected", "Connect to the database first.")
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.all_invoices = db.fetch_invoices(self.connection, "", 500)
            self._apply_filter()
            self.statusBar().showMessage(
                "Loaded {} invoices".format(len(self.all_invoices)),
                5000,
            )
        except Exception as exc:
            self._show_error("Failed to load invoices", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

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
            self._show_error("Missing report", "Select a Jasper report file.")
            return None
        if not os.path.isfile(report_path):
            self._show_error("Report not found", report_path)
            return None
        return report_path

    def _preview_selected(self):
        self._run_print_action(preview=True)

    def _print_selected(self):
        self._run_print_action(preview=False)

    def _run_print_action(self, preview):
        transid = self._selected_transid()
        if transid is None:
            self._show_error("No invoice selected", "Select an invoice first.")
            return
        report_path = self._selected_report_path()
        if report_path is None:
            return

        host = self.host_input.text().strip() or "localhost"
        port = self.port_input.text().strip() or "5432"
        database = self.database_input.text().strip()
        user = self.user_input.text().strip()
        password = self.password_input.text()
        if not database or not user:
            self._show_error("Missing fields", "Database and user are required.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if preview:
                self.statusBar().showMessage("Building preview...", 2000)
                printer.preview_invoice(report_path, host, port, database, user, password, transid)
            else:
                self.statusBar().showMessage("Sending to print...", 2000)
                printer.print_invoice(report_path, host, port, database, user, password, transid)
        except Exception as exc:
            self._show_error("Print failed", str(exc))
        finally:
            QApplication.restoreOverrideCursor()

    def _update_actions(self):
        has_selection = self._selected_transid() is not None
        self.preview_button.setEnabled(has_selection)
        self.print_button.setEnabled(has_selection)

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

    def _show_error(self, title, text):
        QMessageBox.critical(self, title, text)
        self.statusBar().showMessage(text, 6000)

    def closeEvent(self, event):
        if self.connection is not None:
            db.close(self.connection)
            self.connection = None
        super().closeEvent(event)


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
