from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide2.QtWidgets import *  # noqa: F401,F403
    from PySide2.QtWidgets import QAction, QActionGroup, QShortcut  # noqa: F401
else:
    from app.qt.qt_compat import QtWidgets as _m

    globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
