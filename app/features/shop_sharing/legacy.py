"""Convert a v0.4.13 pointer file or legacy home link into shop sharing, once.

Remove in v0.4.16, together with its one call in ``service.py``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple

from app.core import constants
from app.features.shop_sharing.model import (
    MARKER_FILENAME,
    Machine,
    Present,
    RecentsAddMissing,
    ShopDoc,
    classify_project,
)
from app.features.shop_sharing.storage import (
    marker_payload,
    read_shop_file,
    shop_folder_at,
    visible_child_dirs,
    write_shop_doc_if_absent,
)

_LOGGER = logging.getLogger(__name__)

_POINTER_TAIL = ("Chore_Boy", "CBCS", constants.CBCS_STATE_ROOT_POINTER_FILENAME)


def pointer_candidates(machine: Machine) -> Tuple[Path, ...]:
    """``/home/default/share/...``, ``~/share/...``, then ``~/share/<child>/...`` sorted by name."""
    ordered: list[Path] = []
    share = machine.home / "share"
    for candidate in (
        machine.default_home.joinpath("share", *_POINTER_TAIL),
        share.joinpath(*_POINTER_TAIL),
        *(child.joinpath(*_POINTER_TAIL) for child in visible_child_dirs(share)),
    ):
        logical = Path(os.path.abspath(str(candidate)))
        if logical not in ordered:
            ordered.append(logical)
    return tuple(ordered)


def find_legacy_folder(machine: Machine) -> Optional[Path]:
    """The first pointer line whose folder exists here, then the legacy home link into ``~/share``.

    A relative line resolves against the pointer file's folder, lexically. The
    legacy link's identity is the logical path of the link itself.
    """
    for pointer in pointer_candidates(machine):
        try:
            text = pointer.read_text(encoding="utf-8") if pointer.is_file() else ""
        except OSError:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            target = os.path.abspath(os.path.join(str(pointer.parent), os.path.expanduser(stripped)))
            if os.path.isdir(target):
                return Path(target)
    return _legacy_share_link(machine)


def convert_if_found(machine: Machine, utc_now: Callable[[], datetime]) -> Optional[Path]:
    """Prepare the legacy folder for shop sharing and return it. The caller writes the choice file.

    Every step is skip-if-present, so a crash before the choice file re-runs
    harmlessly. Nothing is moved, renamed, or deleted. A folder that cannot be
    written is not a hit; the machine stays undecided and retries next launch.
    """
    folder = find_legacy_folder(machine)
    if folder is None:
        return None
    try:
        write_shop_doc_if_absent(folder, MARKER_FILENAME, marker_payload(machine.hostname, utc_now()), hostname=machine.hostname)
        old_recents = read_shop_file(folder, constants.GLOBAL_RECENT_PROJECTS_FILENAME)
        old_paths = old_recents.payload.get("projects") if isinstance(old_recents, Present) else None
        shop_folder = shop_folder_at(folder, machine)
        refs = tuple(
            classify_project(path, folder=shop_folder, hostname=machine.hostname)
            for path in (old_paths if isinstance(old_paths, list) else [])
            if isinstance(path, str) and os.path.isabs(path)
        )
        recents = RecentsAddMissing(op_id="legacy", refs=refs).apply(ShopDoc.RECENTS.empty())
        write_shop_doc_if_absent(folder, ShopDoc.RECENTS.value, recents, hostname=machine.hostname)
    except OSError as exc:
        _LOGGER.warning("Could not convert legacy shared settings at %s: %s", folder, exc)
        return None
    return folder


def _legacy_share_link(machine: Machine) -> Optional[Path]:
    link = machine.home / constants.GLOBAL_STATE_DIRNAME
    try:
        if not link.is_symlink() or not link.is_dir():
            return None
        raw_target = os.readlink(str(link))
    except OSError:
        return None
    target = os.path.abspath(os.path.join(str(link.parent), raw_target))
    share = os.path.abspath(str(machine.home / "share"))
    if target == share or target.startswith(share + os.sep):
        return Path(os.path.abspath(str(link)))
    return None
