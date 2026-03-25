"""Debug command builder helpers for runner stdin channel."""

from __future__ import annotations


def continue_command() -> str:
    return "continue\n"


def step_over_command() -> str:
    return "next\n"


def step_into_command() -> str:
    return "step\n"


def step_out_command() -> str:
    return "return\n"


def stack_command() -> str:
    return "where\n"


def locals_command() -> str:
    return "p locals()\n"


def evaluate_command(expression: str) -> str:
    clean = expression.strip()
    if not clean:
        return "\n"
    return f"p {clean}\n"
