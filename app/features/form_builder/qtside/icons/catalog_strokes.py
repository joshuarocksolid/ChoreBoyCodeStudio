"""Glyph strokes for the Insert catalog (UX-ICON-005): one miniature per entry.

Same grid and stroke rules as ``glyphs.py``: 16 units, points and polylines,
painted at 16 and 20 px. Each entry has its own name; rotated orientation pairs
get their own stroke set so every entry paints different pixels.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

Stroke = Tuple[Tuple[float, float], ...]


def _box(left: float, top: float, right: float, bottom: float) -> Stroke:
    return ((left, top), (right, top), (right, bottom), (left, bottom), (left, top))


def _ring(cx: float, cy: float, radius: float, steps: int = 16) -> Stroke:
    points = [
        (cx + radius * math.cos(2 * math.pi * index / steps), cy + radius * math.sin(2 * math.pi * index / steps))
        for index in range(steps + 1)
    ]
    return tuple(points)


def _arc(cx: float, cy: float, radius: float, start: float, end: float, steps: int = 4) -> Stroke:
    points = []
    for index in range(steps + 1):
        angle = math.radians(start + (end - start) * index / steps)
        points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return tuple(points)


def _rrect(left: float, top: float, right: float, bottom: float, radius: float) -> Stroke:
    r = radius
    return (
        (left + r, top),
        (right - r, top),
        *_arc(right - r, top + r, r, -90, 0)[1:],
        (right, bottom - r),
        *_arc(right - r, bottom - r, r, 0, 90)[1:],
        (left + r, bottom),
        *_arc(left + r, bottom - r, r, 90, 180)[1:],
        (left, top + r),
        *_arc(left + r, top + r, r, 180, 270)[1:],
    )


def _line(x1: float, y1: float, x2: float, y2: float) -> Stroke:
    return ((x1, y1), (x2, y2))


def _card(mark: Tuple[Stroke, ...]) -> Tuple[Stroke, ...]:
    """The page card the window kinds share: a page with a title rule, plus a mark."""
    return (_box(3, 2, 13, 14), _line(3, 5, 13, 5)) + mark


def _page_card_mark_main() -> Tuple[Stroke, ...]:
    return (_line(5, 8, 11, 8), _line(5, 11, 11, 11))


def _page_card_mark_dialog() -> Tuple[Stroke, ...]:
    return (_box(7.5, 9.5, 11.5, 12.5),)


def _page_card_mark_widget() -> Tuple[Stroke, ...]:
    return (_line(5, 8, 11, 8), _line(5, 11, 9, 11))


def _page_card_mark_wizard() -> Tuple[Stroke, ...]:
    return (((6.5, 8), (5, 10), (6.5, 12)), ((9.5, 8), (11, 10), (9.5, 12)))


CATALOG_STROKES: Dict[str, Tuple[Stroke, ...]] = {
    "layout_v": (_box(3, 2, 13, 14), _line(3, 6, 13, 6), _line(3, 10, 13, 10)),
    "layout_h": (_box(2, 3, 14, 13), _line(6, 3, 6, 13), _line(10, 3, 10, 13)),
    "layout_grid": (_line(2, 7, 7, 7), _line(9, 7, 14, 7), _line(2, 11, 7, 11), _line(9, 11, 14, 11), _line(4.5, 2, 4.5, 5), _line(11.5, 2, 11.5, 5)),
    "layout_form": (_line(2, 5, 6, 5), _box(8, 3, 14, 6), _line(2, 11, 6, 11), _box(8, 9, 14, 12)),
    "splitter_h": (_box(2, 3, 6.5, 13), _box(9.5, 3, 14, 13), _line(8, 2, 8, 14)),
    "splitter_v": (_box(3, 2, 13, 6.5), _box(3, 9.5, 13, 14), _line(2, 8, 14, 8)),
    "spacer_h": (_line(2, 8, 14, 8), ((4, 5.5), (2, 8), (4, 10.5)), ((12, 5.5), (14, 8), (12, 10.5))),
    "spacer_v": (_line(8, 2, 8, 14), ((5.5, 4), (8, 2), (10.5, 4)), ((5.5, 12), (8, 14), (10.5, 12))),
    "line_h": (_line(2, 8, 14, 8),),
    "line_v": (_line(8, 2, 8, 14),),
    "line_edit": (_box(2, 5, 14, 11), _line(4.5, 6.5, 4.5, 9.5)),
    "text_edit": (_box(2, 2, 14, 14), _line(2, 5, 14, 5), _line(4.5, 8.5, 11.5, 8.5), _line(4.5, 11.5, 9, 11.5)),
    "plain_text_edit": (_box(2, 2, 14, 14), _line(4, 6, 12, 6), _line(4, 8.5, 12, 8.5), _line(4, 11, 9, 11)),
    "spin_box": (_box(2, 4, 11, 12), _line(4, 8, 6.5, 8), ((12, 6.5), (13, 5), (14, 6.5)), ((12, 9.5), (13, 11), (14, 9.5))),
    "double_spin_box": (_box(2, 4, 11, 12), _line(3.5, 8, 5, 8), _line(6.5, 10.5, 7, 10.5), ((12, 6.5), (13, 5), (14, 6.5)), ((12, 9.5), (13, 11), (14, 9.5))),
    "slider_h": (_line(2, 8, 14, 8), _ring(9.5, 8, 2.6)),
    "slider_v": (_line(8, 2, 8, 14), _ring(8, 9.5, 2.6)),
    "dial": (_ring(8, 8, 5.5), _line(8, 8, 11, 5)),
    "scrollbar_h": (_box(2, 6, 14, 10), _box(5, 6.5, 10, 9.5)),
    "scrollbar_v": (_box(6, 2, 10, 14), _box(6.5, 5, 9.5, 10)),
    "key_sequence": (_box(2.5, 5, 7.5, 11), _box(8.5, 5, 13.5, 11), _line(4.5, 8, 5.5, 8)),
    "combo_box": (_box(2, 4, 14, 12), ((5, 7), (8, 10), (11, 7))),
    "font_combo": (_box(2, 4, 14, 12), ((3.5, 10.5), (5.5, 6), (7.5, 10.5)), _line(4.3, 9, 6.7, 9)),
    "check_box": (_box(2.5, 2.5, 13.5, 13.5), ((4.5, 8.5), (7, 11), (11.5, 5))),
    "radio_button": (_arc(8, 8, 5.5, 0, 80), _arc(8, 8, 5.5, 100, 170), _arc(8, 8, 5.5, 190, 260), _arc(8, 8, 5.5, 280, 350), _line(7.5, 8, 8.5, 8)),
    "pill": (_rrect(2, 5, 14, 11, 3),),
    "tool_button": (_rrect(3, 3, 13, 13, 3), ((6, 7), (10, 7), (8, 10), (6, 7))),
    "command_link": (_rrect(2, 4, 14, 12, 3), _line(5, 8, 11, 8), ((9, 6), (11, 8), (9, 10))),
    "button_box": (_rrect(1.5, 6, 7.5, 11, 2), _rrect(8.5, 6, 14.5, 11, 2)),
    "date_edit": (_box(2, 3.5, 14, 14), _line(2, 6.5, 14, 6.5), _line(5, 2, 5, 4.5), _line(11, 2, 11, 4.5)),
    "time_edit": (_ring(8, 8, 5.5), _line(8, 8, 8, 5), _line(8, 8, 10.5, 8)),
    "date_time_edit": (_box(2, 3.5, 11, 13), _line(2, 6.5, 11, 6.5), _ring(12, 11.5, 2.4)),
    "calendar": (_box(2, 3, 14, 14), _line(2, 6, 14, 6), _line(2, 10, 14, 10), _line(6, 6, 6, 14), _line(10, 6, 10, 14)),
    "list_widget": (_box(2.5, 3, 4.5, 5), _line(6.5, 4, 13.5, 4), _box(2.5, 7, 4.5, 9), _line(6.5, 8, 13.5, 8), _box(2.5, 11, 4.5, 13), _line(6.5, 12, 13.5, 12)),
    "list_view": (_box(2, 2, 14, 14), _line(4.5, 5, 11.5, 5), _line(4.5, 8, 11.5, 8), _line(4.5, 11, 11.5, 11)),
    "tree_widget": (_box(2.5, 3, 5.5, 5), _line(7, 4, 13.5, 4), _box(4.5, 7, 7.5, 9), _line(9.5, 8, 13.5, 8), _box(4.5, 11, 7.5, 13), _line(9.5, 12, 13.5, 12)),
    "tree_view": (_box(1.5, 1.5, 14.5, 14.5), _line(4, 5, 8, 5), _line(6, 8, 10, 8), _line(6, 11, 10, 11)),
    "table_widget": (_box(2, 2, 14, 14), _line(2, 6, 14, 6), _line(2, 10, 14, 10), _line(6, 2, 6, 14), _line(10, 2, 10, 14)),
    "table_view": (_box(2, 2, 14, 14), _line(2, 5, 14, 5), _line(8, 5, 8, 14)),
    "column_view": (_line(5, 2, 5, 14), _line(10, 2, 10, 14), ((11.5, 6), (13.5, 8), (11.5, 10))),
    "undo_view": (_line(2.5, 4.5, 13.5, 4.5), _line(2.5, 8, 10.5, 8), _line(2.5, 11.5, 7, 11.5), _arc(12, 11.5, 1.5, 0, 270)),
    "group_box": (((4, 4), (2, 4), (2, 13), (14, 13), (14, 4), (10, 4)),),
    "frame": (_box(2, 3, 14, 13), _box(4.5, 5.5, 11.5, 11)),
    "widget": (((2, 5), (2, 2), (5, 2)), ((11, 2), (14, 2), (14, 5)), ((14, 11), (14, 14), (11, 14)), ((5, 14), (2, 14), (2, 11))),
    "tab_widget": (_box(2, 5, 14, 14), ((2, 5), (2, 2), (7, 2), (8.5, 5))),
    "toolbox": (_box(2, 2, 14, 5), _box(2, 6.5, 14, 9.5), _box(2, 11, 14, 14)),
    "stacked_widget": (_box(2, 2, 11, 11), _box(5, 5, 14, 14)),
    "scroll_area": (_box(2, 2, 14, 14), _box(11, 5, 13, 9)),
    "wizard": (_box(2, 3, 14, 13), ((6, 6), (3.5, 8), (6, 10)), ((10, 6), (12.5, 8), (10, 10))),
    "wizard_page": (_box(3, 2, 13, 14), _line(5, 5, 11, 5), _line(5, 8, 11, 8), _line(5, 11, 9, 11)),
    "mdi_area": (_box(2, 2, 10, 10), _line(2, 4, 10, 4), _box(6, 6, 14, 14), _line(6, 8, 14, 8)),
    "dock_widget": (_box(2, 2, 14, 14), _line(5.5, 2, 5.5, 14)),
    "label": (((2, 13), (4.5, 4), (7, 13)), _line(3.2, 10, 5.8, 10), _ring(11, 10.5, 2.2), _line(13.2, 8.5, 13.2, 13)),
    "text_browser": (_box(2, 2, 14, 14), _line(4, 6, 12, 6), _line(4, 8.5, 10, 8.5), _line(4, 11.5, 8, 11.5)),
    "progress_bar": (_box(2, 6, 14, 10), _line(4, 6.5, 4, 9.5), _line(5.5, 6.5, 5.5, 9.5), _line(7, 6.5, 7, 9.5), _line(8.5, 6.5, 8.5, 9.5)),
    "lcd": (_box(2.5, 3, 6.5, 13), _box(9.5, 3, 13.5, 13), _line(2.5, 8, 6.5, 8), _line(9.5, 8, 13.5, 8)),
    "graphics_view": (_box(2, 2, 14, 14), ((4, 11), (7, 6), (10, 9), (12, 5))),
    "opengl": (((8, 2), (14, 5), (14, 11), (8, 14), (2, 11), (2, 5), (8, 2)), ((2, 5), (8, 8), (14, 5)), _line(8, 8, 8, 14)),
    "quick": (_ring(8, 8, 5.5), _ring(8, 8, 2)),
    "fc_quantity": (_box(2, 6, 14, 10), _line(4, 6, 4, 8.5), _line(7, 6, 7, 8.5), _line(10, 6, 10, 8.5), _line(13, 6, 13, 8.5)),
    "fc_input": (_box(2, 4, 14, 12), _line(5, 6, 5, 10), _line(8, 6, 11, 6), _line(8, 10, 11, 10)),
    "fc_file": (((2, 5), (2, 13), (14, 13), (14, 6), (8, 6), (6.5, 4), (2, 4), (2, 5)),),
    "fc_color": (_box(2, 2, 14, 14), _line(2, 14, 14, 2)),
    "fc_url": (_rrect(1.5, 6, 8.5, 10, 2), _rrect(7.5, 6, 14.5, 10, 2)),
    "fc_int": (_box(2, 4, 14, 12), _line(5.5, 6, 5.5, 10), _line(8.5, 6, 8.5, 10), _line(4, 7, 10, 7), _line(4, 9, 10, 9)),
    "fc_double": (_box(2, 4, 14, 12), _line(4, 8, 6, 8), _line(9, 10, 10, 10), _line(11.5, 6, 11.5, 10)),
    "custom": (_box(2, 2, 14, 14), _line(5, 8, 11, 8), _line(8, 5, 8, 11)),
    "window_main": _card(_page_card_mark_main()),
    "window_dialog": _card(_page_card_mark_dialog()),
    "window_widget": _card(_page_card_mark_widget()),
    "window_wizard": _card(_page_card_mark_wizard()),
}
