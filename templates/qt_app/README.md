# Qt App Template

This template starts a simple Qt window from `main.py`.

Import Qt from `PySide` (`from PySide.QtWidgets import ...`).
Import `QAction`, `QActionGroup`, and `QShortcut` from `PySide.QtGui`.
Start the event loop with `(getattr(app, "exec", None) or app.exec_)()`.
