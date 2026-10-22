"""Launch, Runtime ready, a main-window crop, and a state dump."""

from __future__ import annotations

import json

from scenarios.ctx import Ctx


def run(ctx: Ctx) -> None:
    exp = ctx.session.slot == "ChoreBoyExp"
    ctx.launch(name="verify-smoke", wait_ready=90)
    needle = "Runtime ready" if exp else "9/9"
    label = ctx.wait_chip(needle, timeout=45)
    if exp:
        ok = "Runtime ready" in label
        expected = "Runtime ready"
    else:
        ok = "Runtime ready" in label and "9/9" in label
        expected = "Runtime ready (9/9 checks)"
    ctx.check("runtime-ready", ok, expected, label)
    ctx.shot("smoke-main", selector="#shell.mainWindow", kind="crop")
    state = ctx.adapter.state()
    (ctx.artifacts / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    windows = state.get("windows") or []
    titles = [str(row.get("title") or "") for row in windows]
    ctx.metric("window_titles", titles)
    ctx.check("main-window", any("ChoreBoy Code Studio" in title for title in titles), "ChoreBoy Code Studio window", " | ".join(titles))
    binding = str(state.get("qt_binding") or "")
    if not binding:
        binding = ctx.eval(
            "mods = []\n"
            "for name in ('PySide6', 'PySide2'):\n"
            "    try:\n"
            "        mod = __import__(name)\n"
            "        mods.append(name + ' ' + str(getattr(mod, '__version__', '')))\n"
            "    except ImportError:\n"
            "        pass\n"
            "print(' '.join(mods))\n",
            wait=15,
        ).strip()
    ctx.metric("qt_binding", binding)
    ctx.check("qt-binding", "PySide" in binding, "resolved Qt binding", binding)
    ctx.metric("caps", ctx.adapter.caps.to_dict())
