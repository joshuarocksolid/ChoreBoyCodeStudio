"""Pure text-editing helper functions shared by editor widgets/tests."""

from __future__ import annotations


def indent_lines(text: str, *, indent_text: str = "    ") -> str:
    """Indent every non-empty line in text."""
    lines = text.splitlines()
    return "\n".join(f"{indent_text}{line}" if line.strip() else line for line in lines)


def outdent_lines(text: str, *, indent_text: str = "    ") -> str:
    """Outdent lines by one indentation unit when present."""
    lines = text.splitlines()
    outdented: list[str] = []
    for line in lines:
        if line.startswith(indent_text):
            outdented.append(line[len(indent_text) :])
        elif line.startswith("\t"):
            outdented.append(line[1:])
        elif line.startswith(" "):
            outdented.append(line[1:])
        else:
            outdented.append(line)
    return "\n".join(outdented)


def toggle_comment_lines(text: str, *, comment_prefix: str = "# ") -> str:
    """Toggle Python line comments for multi-line selection."""
    lines = text.splitlines()
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return text
    should_uncomment = all(line.lstrip().startswith("#") for line in non_empty)

    transformed: list[str] = []
    for line in lines:
        if not line.strip():
            transformed.append(line)
            continue
        leading = len(line) - len(line.lstrip(" "))
        indent = line[:leading]
        body = line[leading:]
        if should_uncomment:
            if body.startswith("# "):
                transformed.append(f"{indent}{body[2:]}")
            elif body.startswith("#"):
                transformed.append(f"{indent}{body[1:]}")
            else:
                transformed.append(line)
        else:
            transformed.append(f"{indent}{comment_prefix}{body}")
    return "\n".join(transformed)
