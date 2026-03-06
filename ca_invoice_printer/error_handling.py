from PySide2.QtWidgets import QMessageBox

from jasper_bridge import (
    CompileError,
    DataSourceError,
    ExportError,
    FillError,
    JVMError,
    ParameterError,
    PrintError,
)

JASPER_ERROR_TYPES = (
    CompileError,
    FillError,
    DataSourceError,
    ParameterError,
    ExportError,
    PrintError,
    JVMError,
)


def format_exception(exc):
    message = getattr(exc, "message", None) or str(exc) or exc.__class__.__name__
    details = getattr(exc, "java_stacktrace", None)
    if details:
        return message, str(details)
    return message, None


def show_error_dialog(parent, title, exc):
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Critical)
    dialog.setWindowTitle(str(title))
    message, details = format_exception(exc)
    dialog.setText(message)
    if details:
        dialog.setDetailedText(details)
    dialog.exec_()
    return message
