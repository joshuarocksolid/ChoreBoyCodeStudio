"""Drop Jedi's parse cache after a generated module is replaced.

The engine cannot import ``app.bootstrap`` to put vendor on ``sys.path``.
If this process has not loaded Jedi yet, the next completion reads the new
file itself. If it has, the in-memory parse cache would keep the old names.
"""

from __future__ import annotations

import sys


def clear_inference_cache() -> None:
    """Forget parsed modules Jedi already loaded in this process."""
    parso_cache = sys.modules.get("parso.cache")
    if parso_cache is not None:
        parser_cache = getattr(parso_cache, "parser_cache", None)
        if parser_cache is not None:
            parser_cache.clear()
    jedi_cache = sys.modules.get("jedi.cache")
    if jedi_cache is None:
        return
    clear = getattr(jedi_cache, "clear_time_caches", None)
    if clear is not None:
        clear(delete_all=True)
