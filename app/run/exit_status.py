from __future__ import annotations

import signal


def describe_exit_code(return_code: int | None) -> str:
    if return_code is None:
        return "unknown exit status"
    if return_code >= 0:
        return f"exit code {return_code}"
    signal_number = -return_code
    try:
        signal_name = signal.Signals(signal_number).name
    except (ValueError, AttributeError):
        signal_name = f"signal {signal_number}"
    return f"{signal_name} (signal {signal_number})"
