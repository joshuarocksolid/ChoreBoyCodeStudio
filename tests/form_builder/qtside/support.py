"""Open a FormSession the way the editor tab will."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence, Tuple

from app.features.form_builder.engine.project.forms import FormScope
from app.features.form_builder.engine.session import FormSession
from app.features.form_builder.qtside.realize import Realizer


def open_session(text: str, path: str = "/tmp/cbcs-form.ui") -> FormSession:
    scope = FormScope(kind="external", ui_path=path)
    return FormSession.open(text, path=path, scope=scope)


def realize(text: str, path: str = "/tmp/cbcs-form.ui") -> Tuple[FormSession, Realizer]:
    session = open_session(text, path)
    realizer = Realizer(session)
    realizer.build()
    return session, realizer


@contextmanager
def opened(text: str, path: str = "/tmp/cbcs-form.ui") -> Iterator[Tuple[FormSession, Realizer]]:
    session, realizer = realize(text, path)
    try:
        yield session, realizer
    finally:
        realizer.dispose()
        session.dispose()


def run_module(module: str, args: Sequence[str]) -> "subprocess.CompletedProcess[str]":
    """Run ``module`` under this interpreter.

    FreeCAD AppRun rejects ``-m``. A short ``-c`` payload plus ``runpy`` works
    there and on a normal Python. Arguments travel in the environment so the
    payload stays under AppRun's slash-free limit.
    """
    repo = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["CBCS_FB_MODULE"] = module
    env["CBCS_FB_MODULE_ARGS"] = json.dumps(list(args))
    payload = (
        "import json, os, runpy, sys\n"
        "sys.argv = [os.environ['CBCS_FB_MODULE']] + json.loads(os.environ['CBCS_FB_MODULE_ARGS'])\n"
        "runpy.run_module(os.environ['CBCS_FB_MODULE'], run_name='__main__')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", payload],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
    )


def form(opening: str, inner: str, tail: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<ui version="4.0">\n <class>Form</class>\n <widget %s>\n%s\n </widget>\n%s\n</ui>\n'
        % (opening, inner, tail)
    )
