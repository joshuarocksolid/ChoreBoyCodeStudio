"""Spacing, type, and control sizes for builder chrome.

Layout steps sit on the 4 px grid. Type sizes and the 10 px chevron come from
the host type scale and the follow-up 2 brief. Call sites use these names
instead of raw margins and fixed heights.
"""

from __future__ import annotations

# Spacing scale.
S1 = 4
S2 = 8
S3 = 12
S4 = 16
S6 = 24
S8 = 32

# Heights.
ROW = 24
CONTROL = 24
INSPECTOR_ROW = 28
SECTION_HEADER = 28
TOOLBAR = 36
PRIMARY_BUTTON = 28
BANNER = 32
INFO_BAR = 32
CHIP = 18
BREADCRUMB = 20
TAB = 28

# Radii.
R_CONTROL = 4
R_POPOVER = 6
R_CARD = 8
R_SEGMENT = 3

# Pane padding. Compact when the tab is under COMPACT_PANE_WIDTH.
PANE_PAD = 12
PANE_PAD_COMPACT = 8
COMPACT_PANE_WIDTH = 1180

# Icons.
ICON = 16
ICON_BUTTON = 24
ICON_BUTTON_HEADER = 20
CHEVRON = 10
CHEVRON_SMALL = 8

# Type. These match the host, not the prototype's 13 px.
TYPE_SECTION = 10
TYPE_FINE = 11
TYPE_BODY = 12
TYPE_EMPHASIS = 13
TYPE_HERO = 22
LETTER_SECTION = 0.6

# Inspector label column. 38% of the pane, clamped.
LABEL_RATIO = 0.38
LABEL_MIN = 88
LABEL_MAX = 120

# Popovers.
POPOVER_WIDTH = 280
POPOVER_WIDTH_WIDE = 320
POPOVER_ROWS = 8
POPOVER_MOTION_MS = 120
POPOVER_SLIDE = 4

# Tabs and toolbar.
TAB_PAD = 8
TAB_PAD_COMPACT = 6
ZOOM_READOUT = 44
DIVIDER = 16
LEFT_PANE_TABS = 200

# Responsive widths from the brief.
TILE_PANE = 232
STACK_HEIGHT = 560
LABEL_COLLAPSE = 1000
NARROW_INSPECTOR = 300
SEGMENT_CELL = 28
MAPPING_ROW = 32
CONNECTION_ROW = 40
TABLE_LIST = 160
ORDER_SEGMENT = 56
PREVIEW_INSET = 16
CARD_W = 200
CARD_H = 156
THUMB_H = 120
START_MAX = 960
