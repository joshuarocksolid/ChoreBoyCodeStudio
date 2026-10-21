"""Child side of the preview process (CONTRACTS.md section 10.4). [M2.5]

Entered from the repo-root ``run_form_preview.py`` (a three-line runpy shim,
like ``run_plugin_host.py``). This is the only place user code, promoted
custom widget classes, generated modules and ``*_rc.py`` modules run.

Startup order:
1. ``frames = os.fdopen(os.dup(1), "w", buffering=1)``; ``os.dup2(2, 1)`` so any
   C-level stdout write lands on stderr and the frame stream stays clean.
2. ``sys.stdout`` is replaced by a writer that turns user prints into ``Log``
   frames (stream ``stdout``). A Qt message handler emits ``Log`` (stream ``qt``).
3. Force PySide6 (``CBCS_QT_API=pyside6`` in the env), create QApplication,
   send ``Ready``, then serve stdin frames on a reader thread that posts each
   decoded message to the GUI thread.
4. Exit 0 on Shutdown, on stdin EOF (host died), or after IDLE_EXIT_SECONDS
   with no views. Exit 3 after a protocol mismatch.
Must not import ``app.shell``, ``app.editors``, ``integration`` or any CBCS
editor state.
"""

from __future__ import annotations

from typing import Sequence


def main(argv: Sequence[str]) -> int:
    ...
