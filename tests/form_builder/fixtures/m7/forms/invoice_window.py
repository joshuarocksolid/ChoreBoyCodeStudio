# pyright: reportMissingImports=false
from PySide6.QtWidgets import QDialog

from forms.ui_invoice import Ui_Invoice


class InvoiceWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Invoice()
        self.ui.setupUi(self)

    def save_invoice(self):
        """Runs when saveButton is clicked."""
        pass
