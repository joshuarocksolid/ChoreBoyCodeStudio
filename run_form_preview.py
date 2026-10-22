"""Launch the form-preview child.

AppRun runs this file. Stdin and stdout are split off before Qt is imported,
and ``CBCS_QT_API`` is forced to PySide6 for this process only.
"""

import os
import sys

os.environ["CBCS_QT_API"] = "pyside6"

from app.features.form_builder.qtside.preview.child.stdio import isolate_stdio

_STREAMS = isolate_stdio()

from app.features.form_builder.qtside.preview.child.main import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], _STREAMS))
