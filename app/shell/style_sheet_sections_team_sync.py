"""Team Sync chrome. Rules key off ``shell.teamSync.*`` names and properties."""

from __future__ import annotations

from app.features.team_sync.ui.theme import (
    accent_soft,
    added_soft,
    mine_bg,
    removed_soft,
    theirs_bg,
    warning_soft,
)
from app.shell.theme_tokens import ShellThemeTokens


def shell_section_team_sync(tokens: ShellThemeTokens) -> str:
    accent = tokens.accent
    text = tokens.text_primary
    muted = tokens.text_muted
    border = tokens.border
    panel = tokens.panel_bg
    editor = tokens.editor_bg
    hover = tokens.tree_hover_bg or tokens.row_alt_bg or border
    selected = tokens.tree_selected_bg or hover
    ok = tokens.test_passed_color or "#1A7F37"
    warn = tokens.diag_warning_color or "#D97706"
    err = tokens.diag_error_color or "#E03131"
    popup = tokens.popup_bg or panel
    popup_border = tokens.popup_border or border
    focus = tokens.focus_border_width
    fg = tokens.toolbar_package_fg or "#FFFFFF"
    soft = accent_soft(tokens)
    warn_bg = warning_soft(tokens)
    mine = mine_bg(tokens)
    theirs = theirs_bg(tokens)
    add_bg = added_soft(tokens)
    del_bg = removed_soft(tokens)
    chip = tokens.row_alt_bg or hover
    return f"""
QWidget#shell\\.teamSync\\.teamView {{
    background: {panel};
    color: {text};
    font-size: 13px;
}}
QWidget#shell\\.teamSync\\.teamHeader {{
    background: transparent;
    min-height: 30px;
    max-height: 30px;
}}
QWidget#shell\\.teamSync\\.empty QLabel {{
    color: {text};
    background: transparent;
    font-size: 13px;
}}
QScrollArea#shell\\.teamSync\\.feed,
QWidget#shell\\.teamSync\\.feedHost,
QWidget#shell\\.teamSync\\.feedViewport,
QWidget#shell\\.teamSync\\.empty {{
    background: {panel};
    color: {text};
    border: none;
}}
QWidget#shell\\.teamSync\\.feedMessage {{
    background: transparent;
}}
QWidget#shell\\.teamSync\\.feedMessage[incoming="true"] {{
    background: {soft};
    border-radius: 6px;
}}
QLabel#shell\\.teamSync\\.feedName {{
    color: {text};
    background: transparent;
    font-weight: 700;
}}
QLabel#shell\\.teamSync\\.feedTime,
QLabel#shell\\.teamSync\\.feedSystem {{
    color: {muted};
    background: transparent;
    font-size: 11px;
}}
QLabel#shell\\.teamSync\\.feedNote {{
    color: {text};
    background: transparent;
}}
QPushButton#shell\\.teamSync\\.feedFiles {{
    color: {accent};
    background: transparent;
    border: none;
    padding: 0;
    font-size: 12px;
    text-align: left;
}}
QPushButton#shell\\.teamSync\\.feedFiles:hover {{
    text-decoration: underline;
}}
QLabel#shell\\.teamSync\\.feedMark[delivery="queued"] {{
    color: {muted};
    background: transparent;
    font-size: 12px;
}}
QLabel#shell\\.teamSync\\.feedMark[delivery="sent"],
QLabel#shell\\.teamSync\\.feedMark[delivery="delivered"] {{
    color: {ok};
    background: transparent;
    font-size: 12px;
    font-weight: 700;
}}
QPushButton#shell\\.teamSync\\.feedReview,
QPushButton#shell\\.teamSync\\.infoBarReview,
QPushButton#shell\\.teamSync\\.infoBarResolve,
QPushButton#shell\\.teamSync\\.reviewAccept,
QPushButton#shell\\.teamSync\\.combineFinish,
QPushButton#shell\\.teamSync\\.shareButton,
QPushButton#shell\\.teamSync\\.sendSheetSend {{
    background: {accent};
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 0 10px;
    min-height: 24px;
    font-weight: 700;
    font-size: 12px;
}}
QPushButton#shell\\.teamSync\\.combineFinish:disabled,
QPushButton#shell\\.teamSync\\.shareButton:disabled {{
    background: {border};
    color: {muted};
}}
QPushButton#shell\\.teamSync\\.feedReview:focus,
QPushButton#shell\\.teamSync\\.reviewAccept:focus,
QPushButton#shell\\.teamSync\\.combineFinish:focus,
QPushButton#shell\\.teamSync\\.shareButton:focus,
QPushButton#shell\\.teamSync\\.sendSheetSend:focus,
QToolButton#shell\\.teamSync\\.composerSend:focus {{
    border: {focus}px solid {text};
}}
QWidget#shell\\.teamSync\\.setAside {{
    background: transparent;
    border-top: 1px dashed {border};
}}
QWidget#shell\\.teamSync\\.composer {{
    background: {panel};
    border-top: 1px solid {border};
}}
QToolButton#shell\\.teamSync\\.composerFiles {{
    background: {chip};
    color: {text};
    border: none;
    border-radius: 10px;
    padding: 0 9px;
    min-height: 20px;
    max-height: 20px;
    font-size: 11px;
    font-weight: 700;
}}
QLineEdit#shell\\.teamSync\\.composerNote,
QLineEdit#shell\\.teamSync\\.historySearch,
QTextEdit#shell\\.teamSync\\.sendSheetNote {{
    background: {tokens.input_bg or editor};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 28px;
    selection-background-color: {accent};
}}
QToolButton#shell\\.teamSync\\.composerSend {{
    background: {accent};
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 0;
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
}}
QToolButton#shell\\.teamSync\\.composerSend::menu-indicator {{
    subcontrol-origin: padding;
    subcontrol-position: right center;
    width: 8px;
}}
QToolButton#shell\\.teamSync\\.toolbar\\.send {{
    background: {tokens.toolbar_package_bg or accent};
    color: {fg};
    border: none;
    border-radius: 5px;
    padding: 5px 12px;
    font-weight: 600;
}}
QToolButton#shell\\.teamSync\\.toolbar\\.send:hover {{
    background: {tokens.toolbar_package_hover_bg or tokens.accent_hover or accent};
}}
QLabel#shell\\.teamSync\\.toolbar\\.sendBadge {{
    background: {text};
    color: {tokens.toolbar_package_bg or accent};
    border-radius: 7px;
    padding: 0 4px;
    font-size: 10px;
    font-weight: 700;
}}
QWidget#shell\\.teamSync\\.statusSegment,
QWidget#shell\\.teamSync\\.experimentSegment {{
    background: transparent;
    border: none;
    border-radius: 3px;
}}
QWidget#shell\\.teamSync\\.statusSegment:hover,
QWidget#shell\\.teamSync\\.experimentSegment:hover {{
    background: {hover};
}}
QStatusBar#shell\\.statusBar QLabel#shell\\.teamSync\\.statusLabel,
QStatusBar#shell\\.statusBar QLabel#shell\\.teamSync\\.experimentLabel {{
    color: {text};
    background: transparent;
    font-size: 11px;
    padding: 0;
}}
QWidget#shell\\.teamSync\\.statusDot,
QWidget#shell\\.teamSync\\.terminalDot {{
    min-width: 7px;
    max-width: 7px;
    min-height: 7px;
    max-height: 7px;
    border-radius: 3px;
    background: {ok};
}}
QWidget#shell\\.teamSync\\.statusDot[level="warn"],
QWidget#shell\\.teamSync\\.terminalDot[level="warn"] {{
    background: {warn};
}}
QWidget#shell\\.teamSync\\.statusDot[level="info"],
QWidget#shell\\.teamSync\\.terminalDot[level="info"] {{
    background: {accent};
}}
QWidget#shell\\.teamSync\\.statusDot[level="ok"],
QWidget#shell\\.teamSync\\.terminalDot[level="ok"] {{
    background: {ok};
}}
QFrame#shell\\.teamSync\\.statusPopover,
QFrame#shell\\.teamSync\\.sendSheet,
QFrame#shell\\.teamSync\\.hoverCard,
QFrame#shell\\.toast,
QFrame#shell\\.teamSync\\.toast {{
    background: {popup};
    color: {text};
    border: 1px solid {popup_border};
    border-radius: 6px;
}}
QFrame#shell\\.teamSync\\.hoverCard QLabel,
QFrame#shell\\.teamSync\\.statusPopover QLabel,
QFrame#shell\\.toast QLabel,
QFrame#shell\\.teamSync\\.toast QLabel {{
    color: {text};
    background: transparent;
}}
QLabel#shell\\.teamSync\\.popoverTitle,
QLabel#shell\\.teamSync\\.hoverName {{
    font-weight: 700;
}}
QLabel#shell\\.teamSync\\.hoverMeta,
QLabel#shell\\.teamSync\\.terminalText,
QLabel#shell\\.teamSync\\.popoverMuted {{
    color: {muted};
    font-size: 11px;
}}
QWidget#shell\\.teamSync\\.popoverRow {{
    background: transparent;
    min-height: 28px;
    max-height: 28px;
}}
QPushButton#shell\\.teamSync\\.statusHistory,
QPushButton#shell\\.teamSync\\.hoverOpen,
QPushButton#shell\\.teamSync\\.hoverHistory,
QPushButton#shell\\.teamSync\\.reviewShowFile,
QPushButton#shell\\.teamSync\\.reviewNotNow,
QPushButton#shell\\.teamSync\\.combineCancel,
QPushButton#shell\\.teamSync\\.combineBoth,
QPushButton#shell\\.teamSync\\.combineEdit,
QPushButton#shell\\.teamSync\\.combineUse,
QPushButton#shell\\.teamSync\\.infoBarCancel,
QPushButton#shell\\.teamSync\\.bringBack,
QPushButton#shell\\.teamSync\\.gutterUndo {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 0 10px;
    min-height: 24px;
}}
QPushButton#shell\\.teamSync\\.statusMenu {{
    background: transparent;
    color: {text};
    border: none;
    border-radius: 4px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 0;
    font-weight: 700;
}}
QPushButton#shell\\.teamSync\\.statusMenu:hover,
QToolButton#shell\\.teamSync\\.combinePrev:hover,
QToolButton#shell\\.teamSync\\.combineNext:hover {{
    background: {hover};
}}
QToolButton#shell\\.teamSync\\.combinePrev,
QToolButton#shell\\.teamSync\\.combineNext {{
    background: transparent;
    color: {text};
    border: none;
    border-radius: 4px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 0;
}}
QFrame#shell\\.teamSync\\.infoBar {{
    min-height: 34px;
    max-height: 34px;
    background: {soft};
    border: none;
    border-bottom: 1px solid {border};
}}
QFrame#shell\\.teamSync\\.infoBar[teamNotice="clash"] {{
    background: {warn_bg};
}}
QLabel#shell\\.teamSync\\.infoBarMessage {{
    color: {text};
    background: transparent;
    font-weight: 700;
}}
QFrame#shell\\.teamSync\\.gutterPeek {{
    background: {panel};
    color: {text};
    border: 1px solid {accent};
    border-radius: 5px;
}}
QLabel#shell\\.teamSync\\.peekRemoved {{
    background: {del_bg};
    color: {text};
    font-family: "DejaVu Sans Mono", monospace;
    padding: 0 8px;
}}
QLabel#shell\\.teamSync\\.peekAdded {{
    background: {add_bg};
    color: {text};
    font-family: "DejaVu Sans Mono", monospace;
    padding: 0 8px;
}}
QWidget#shell\\.teamSync\\.reviewTab,
QWidget#shell\\.teamSync\\.combineTab,
QWidget#shell\\.teamSync\\.historyTab {{
    background: {editor};
    color: {text};
}}
QWidget#shell\\.teamSync\\.reviewHeader,
QWidget#shell\\.teamSync\\.combineHeader,
QWidget#shell\\.teamSync\\.historyTools {{
    background: {panel};
    border-bottom: 1px solid {border};
}}
QLabel#shell\\.teamSync\\.combineSummary,
QLabel#shell\\.teamSync\\.reviewNote {{
    color: {text};
    background: transparent;
    font-weight: 700;
}}
QListWidget#shell\\.teamSync\\.reviewFiles,
QListWidget#shell\\.teamSync\\.combineClashes {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: 5px;
    outline: none;
}}
QListWidget#shell\\.teamSync\\.reviewFiles::item:selected,
QListWidget#shell\\.teamSync\\.combineClashes::item:selected {{
    background: {selected};
    color: {text};
}}
QLabel#shell\\.teamSync\\.fileKind[kind="M"] {{
    color: {warn};
    background: transparent;
    font-weight: 700;
}}
QLabel#shell\\.teamSync\\.fileKind[kind="A"] {{
    color: {ok};
    background: transparent;
    font-weight: 700;
}}
QLabel#shell\\.teamSync\\.fileKind[kind="D"] {{
    color: {err};
    background: transparent;
    font-weight: 700;
}}
QLabel#shell\\.teamSync\\.combineFileHeader {{
    color: {muted};
    background: transparent;
    font-size: 11px;
    font-weight: 700;
}}
QLabel#shell\\.teamSync\\.combineSettled {{
    color: {ok};
    background: transparent;
    font-weight: 700;
}}
QFrame#shell\\.teamSync\\.combineOurs,
QFrame#shell\\.teamSync\\.combineTheirs,
QFrame#shell\\.teamSync\\.combineResult {{
    background: {editor};
    border: 1px solid {border};
    border-radius: 5px;
}}
QFrame#shell\\.teamSync\\.combineOurs[picked="true"],
QFrame#shell\\.teamSync\\.combineTheirs[picked="true"] {{
    border: 2px solid {accent};
}}
QPlainTextEdit#shell\\.teamSync\\.combineCode {{
    background: {editor};
    color: {text};
    border: none;
    font-family: "DejaVu Sans Mono", monospace;
    font-size: 12px;
}}
QLabel#shell\\.teamSync\\.combinePlaceholder {{
    color: {muted};
    background: transparent;
    font-style: italic;
}}
QScrollArea#shell\\.teamSync\\.historyList,
QWidget#shell\\.teamSync\\.historyHost,
QWidget#shell\\.teamSync\\.historyViewport {{
    background: {editor};
    color: {text};
    border: none;
}}
QWidget#shell\\.teamSync\\.historyRow {{
    background: transparent;
    min-height: 30px;
    max-height: 30px;
}}
QWidget#shell\\.teamSync\\.historyRow[selected="true"] {{
    background: {selected};
}}
QLabel#shell\\.teamSync\\.historyDate,
QLabel#shell\\.teamSync\\.historyMeta {{
    color: {muted};
    background: transparent;
    font-size: 11px;
}}
QLabel#shell\\.teamSync\\.milestoneChip {{
    background: {soft};
    color: {accent};
    border-radius: 10px;
    padding: 0 6px;
    font-size: 11px;
    font-weight: 700;
}}
QComboBox#shell\\.teamSync\\.historyFilter {{
    background: {panel};
    color: {text};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 2px 8px;
    min-height: 24px;
}}
QFrame#shell\\.toast QPushButton,
QFrame#shell\\.teamSync\\.toast QPushButton {{
    background: {accent};
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 10px;
    font-weight: 600;
}}
"""
