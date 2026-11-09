"""Switch the free-placement dot grid on for each canvas (UX-FSET-006).

The grid shows while the form's "Show grid" is on and some container has no
layout; its step follows "Step across" and "Step down". The layer itself is
``qtside/canvas/layers/free_grid.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.features.form_builder.engine.commands.catalog_ext.form_fields import form_grid, has_free_container
from app.features.form_builder.engine.events import PRIORITY_VIEWS
from app.features.form_builder.qtside.canvas.layers.free_grid import NAME, FreeGrid

logger = logging.getLogger(__name__)


def _attach(workbench: Any) -> None:
    session = workbench._session
    canvas = workbench.canvas

    def sync(*_changes: object) -> None:
        document = session.document
        try:
            grid = form_grid(document)
            if grid.show and has_free_container(document):
                canvas.show_layer(NAME, FreeGrid(grid.across, grid.down))
            else:
                canvas.hide_layer(NAME)
        except Exception:
            logger.exception("free-placement grid could not update")

    sync()
    session.log.subscribe(sync, priority=PRIORITY_VIEWS + 1)


def register(slots: Any) -> None:
    slots.on_workbench(_attach, module=__name__)
