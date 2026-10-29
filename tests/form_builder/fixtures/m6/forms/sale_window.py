# pyright: reportMissingImports=false
from PySide6.QtWidgets import QDialog

from forms.ui_sale import Ui_Sale


class SaleWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Sale()
        self.ui.setupUi(self)

    def show_total(self):
        """Shows the total."""
        pass

    # Notes for the next person: more methods go above this line.
