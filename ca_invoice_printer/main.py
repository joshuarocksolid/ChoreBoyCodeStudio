import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BASE_DIR)
VENDOR_DIR = os.path.join(BASE_DIR, "vendor")
for candidate in (REPO_ROOT, BASE_DIR, VENDOR_DIR):
    if os.path.isdir(candidate) and candidate not in sys.path:
        sys.path.insert(0, candidate)

from PySide2.QtWidgets import QApplication, QLabel, QMainWindow, QTabWidget

from jasper_bridge import jvm

from invoice_tab import InvoiceTab
from standalone_tab import StandaloneTab
from system_tab import SystemTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CA Invoice Printer Demo")
        self.resize(1180, 760)
        self._build_ui()
        self._refresh_runtime_state()
        self.show_status("Ready", 2000)

    def _build_ui(self):
        self.jvm_state_label = QLabel(self)
        self.statusBar().addPermanentWidget(self.jvm_state_label)

        self.tabs = QTabWidget(self)
        self.setCentralWidget(self.tabs)

        self.invoice_tab = InvoiceTab(
            status_callback=self.show_status,
            runtime_callback=self._refresh_runtime_state,
            parent=self,
        )
        self.standalone_tab = StandaloneTab(
            status_callback=self.show_status,
            runtime_callback=self._refresh_runtime_state,
            parent=self,
        )
        self.system_tab = SystemTab(
            status_callback=self.show_status,
            runtime_callback=self._refresh_runtime_state,
            parent=self,
        )

        self.tabs.addTab(self.invoice_tab, "Invoices")
        self.tabs.addTab(self.standalone_tab, "Standalone Reports")
        self.tabs.addTab(self.system_tab, "System")
        self.tabs.currentChanged.connect(self._refresh_runtime_state)

    def show_status(self, message, timeout_ms=5000):
        self.statusBar().showMessage(str(message), int(timeout_ms))
        self._refresh_runtime_state()

    def _refresh_runtime_state(self, *_args):
        self.jvm_state_label.setText("JVM: {}".format(jvm.status()))

    def closeEvent(self, event):
        self.invoice_tab.shutdown()
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
