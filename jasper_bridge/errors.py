from __future__ import annotations

from typing import Optional


class JasperBridgeError(Exception):
    def __init__(self, message: str, *, java_stacktrace: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.java_stacktrace = java_stacktrace

    def __str__(self) -> str:
        if self.java_stacktrace:
            return "{}\n{}".format(self.message, self.java_stacktrace)
        return self.message


class JVMError(JasperBridgeError):
    pass


class CompileError(JasperBridgeError):
    pass


class FillError(JasperBridgeError):
    pass


class ExportError(JasperBridgeError):
    pass


class DataSourceError(FillError):
    pass


class ParameterError(FillError):
    pass


class PrintError(JasperBridgeError):
    pass
