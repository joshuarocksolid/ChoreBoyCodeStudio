#!/usr/bin/env python3
"""Schema helper entry point for ``AppRun -c`` and a direct interpreter."""

from __future__ import annotations

import sys
from pathlib import Path

sys.dont_write_bytecode = True

_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.features.form_builder.qtside.preview.child.stdio import isolate_stdio

_STREAMS = isolate_stdio()

from app.features.form_builder.engine.data.helper.main import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv, _STREAMS))
