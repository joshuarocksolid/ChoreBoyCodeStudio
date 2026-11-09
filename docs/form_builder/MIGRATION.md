# Move a form off QUiLoader

A form that your code loads with `QUiLoader`, `loadUi`, or `FreeCADGui.PySideUic.loadUi` can be adopted. Adopt writes `ui_<name>.py` and `<name>_window.py` next to the `.ui` file, records the form in `cbcs/project.json`, and shows a suggestion. It does not change your own Python.

1. Right-click the `.ui` file in the project tree and choose **Adopt this form**.
2. Copy the suggestion into the window class.

```python
from forms.ui_invoice import Ui_Invoice

class InvoiceWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Invoice()
        self.ui.setupUi(self)
```

3. Delete the loader call. The window builds itself from the generated module. Widget references change from `widget.nameEdit` to `self.ui.nameEdit`.

Save the form after you change the layout. Saving rewrites `ui_<name>.py`. A packaged app imports that module. It does not ship a `.ui` loader, and it does not ship the hand-edit backups under `cbcs/form_builder/`.

A window you built only in code, with no `.ui` file, stays as it is. There is nothing to adopt.
