"""Theme stylesheet for the Data tab and its sheets. Colours come from tokens."""

from __future__ import annotations

from app.features.form_builder.qtside.checkbox_qss import checkbox_indicators


def chrome_qss(tokens: object, root_name: str) -> str:
    name = root_name.replace(".", "\\.")
    root = "QWidget#%s" % name
    sheet = (
        "%s { background: %s; color: %s; }"
        "%s QLabel[fbFaint=\"true\"] { color: %s; }"
        "%s QLabel[fbProblem=\"warning\"] { color: %s; }"
        "%s QLabel[fbProblem=\"error\"] { color: %s; }"
        "%s QLabel[fbLink=\"true\"] { color: %s; }"
    ) % (
        root,
        tokens.panel_bg,  # type: ignore[attr-defined]
        tokens.text_primary,  # type: ignore[attr-defined]
        root,
        tokens.text_muted,  # type: ignore[attr-defined]
        root,
        tokens.diag_warning_color,  # type: ignore[attr-defined]
        root,
        tokens.diag_error_color,  # type: ignore[attr-defined]
        root,
        tokens.accent,  # type: ignore[attr-defined]
    )
    return sheet + checkbox_indicators(tokens)


def apply_chrome(widget: object, tokens: object) -> None:
    if tokens is None:
        return
    name = str(getattr(widget, "objectName", lambda: "")() or "formBuilder.dataChrome")
    widget.setStyleSheet(chrome_qss(tokens, name))  # type: ignore[attr-defined]
