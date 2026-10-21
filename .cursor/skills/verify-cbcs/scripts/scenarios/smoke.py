"""Launch, Runtime ready, a main-window crop, and a state dump."""

from __future__ import annotations

import json

from scenarios.ctx import Ctx


def run(ctx: Ctx) -> None:
    ctx.launch(name="verify-smoke", wait_ready=90)
    label = ctx.wait_chip("Runtime ready", timeout=40)
    settled = ctx.wait_chip("9/9", timeout=20)
    if "9/9" in settled:
        label = settled
    ctx.check("runtime-ready", "Runtime ready" in label, "contains Runtime ready", label)
    ctx.shot("smoke-main", selector="#shell.mainWindow", kind="crop")
    state = ctx.adapter.state()
    (ctx.artifacts / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    windows = state.get("windows") or []
    titles = [str(row.get("title") or "") for row in windows]
    ctx.metric("window_titles", titles)
    ctx.check("main-window", any("ChoreBoy Code Studio" in title for title in titles), "ChoreBoy Code Studio window", " | ".join(titles))
    ctx.metric("caps", ctx.adapter.caps.to_dict())
