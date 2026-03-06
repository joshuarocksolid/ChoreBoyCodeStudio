from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QApplication,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from jasper_bridge import __version__, jvm
from ca_invoice_printer.error_handling import show_error_dialog


class SystemTab(QWidget):
    def __init__(self, status_callback=None, runtime_callback=None, parent=None):
        super().__init__(parent)
        self._status_callback = status_callback
        self._runtime_callback = runtime_callback
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        page = QVBoxLayout(self)

        summary_group = QGroupBox("Runtime Summary", self)
        summary_layout = QFormLayout(summary_group)
        self.version_label = QLabel("", summary_group)
        self.jvm_status_label = QLabel("", summary_group)
        self.java_version_label = QLabel("", summary_group)
        summary_layout.addRow("jasper_bridge version:", self.version_label)
        summary_layout.addRow("JVM status:", self.jvm_status_label)
        summary_layout.addRow("Java/JNI version:", self.java_version_label)

        classpath_group = QGroupBox("Classpath", self)
        classpath_layout = QVBoxLayout(classpath_group)
        self.classpath_view = QTextEdit(classpath_group)
        self.classpath_view.setReadOnly(True)
        classpath_layout.addWidget(self.classpath_view)

        actions_row = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh", self)
        actions_row.addWidget(self.refresh_button)
        actions_row.addStretch()

        page.addWidget(summary_group)
        page.addWidget(classpath_group)
        page.addLayout(actions_row)

        self.refresh_button.clicked.connect(self.refresh)

    def refresh(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            status_value = jvm.status()
            version_value = jvm.java_version()
            classpath_entries = jvm.classpath()

            self.version_label.setText(str(__version__))
            self.jvm_status_label.setText(str(status_value))
            self.java_version_label.setText(str(version_value))
            if classpath_entries:
                self.classpath_view.setPlainText("\n".join(classpath_entries))
            else:
                self.classpath_view.setPlainText("(classpath is empty)")

            self._notify("System diagnostics refreshed", 4000)
        except Exception as exc:
            self._show_error("System diagnostics failed", exc)
        finally:
            QApplication.restoreOverrideCursor()
            self._notify_runtime()

    def _notify(self, message, timeout_ms=5000):
        if self._status_callback is not None:
            self._status_callback(str(message), int(timeout_ms))

    def _notify_runtime(self):
        if self._runtime_callback is not None:
            self._runtime_callback()

    def _show_error(self, title, exc):
        message = show_error_dialog(self, title, exc)
        self._notify(message, 7000)
