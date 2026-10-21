from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide2.QtGui import *  # noqa: F401,F403
else:
    from app.qt.qt_compat import QtGui as _m

    globals().update({k: getattr(_m, k) for k in dir(_m) if not k.startswith("__")})
