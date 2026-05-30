"""Bootstrap shim that exposes ``os.memfd_create`` when the running Python lacks it."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
from typing import Optional

MFD_CLOEXEC = 0x0001
MFD_ALLOW_SEALING = 0x0002
MFD_HUGETLB = 0x0004

_X86_64_SYS_MEMFD_CREATE = 319
_AARCH64_SYS_MEMFD_CREATE = 279

_INSTALLED = False


class _MemfdShimError(RuntimeError):
    pass


def _resolve_libc() -> ctypes.CDLL:
    libc_path = ctypes.util.find_library("c") or "libc.so.6"
    return ctypes.CDLL(libc_path, use_errno=True)


def _build_libc_memfd(libc: ctypes.CDLL) -> Optional[object]:
    if not hasattr(libc, "memfd_create"):
        return None
    fn = libc.memfd_create
    fn.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    fn.restype = ctypes.c_int
    return fn


def _build_syscall_memfd(libc: ctypes.CDLL) -> object:
    machine = os.uname().machine
    if machine == "x86_64":
        nr = _X86_64_SYS_MEMFD_CREATE
    elif machine in ("aarch64", "arm64"):
        nr = _AARCH64_SYS_MEMFD_CREATE
    else:
        raise _MemfdShimError(
            "no memfd_create syscall number known for machine: {0}".format(machine)
        )
    syscall = libc.syscall
    syscall.restype = ctypes.c_long

    def _call(name: bytes, flags: int) -> int:
        return int(syscall(nr, name, ctypes.c_uint(flags)))

    return _call


def _normalize_name(name: object) -> bytes:
    if isinstance(name, bytes):
        return name
    if isinstance(name, str):
        return name.encode("utf-8")
    if isinstance(name, os.PathLike):
        return os.fspath(name).encode("utf-8")
    raise TypeError(
        "memfd_create() argument 'name' must be str or bytes, not {0}".format(
            type(name).__name__
        )
    )


def install() -> bool:
    """Install ``os.memfd_create`` if missing."""
    global _INSTALLED
    if hasattr(os, "memfd_create"):
        return False
    if _INSTALLED:
        return False

    libc = _resolve_libc()
    impl = _build_libc_memfd(libc)
    if impl is None:
        impl = _build_syscall_memfd(libc)

    def memfd_create(name, flags=0):  # type: ignore[no-untyped-def]
        encoded = _normalize_name(name)
        fd = impl(encoded, int(flags))
        if fd < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err))
        return int(fd)

    memfd_create.__doc__ = (
        "Dev shim for os.memfd_create backed by libc/syscall. "
        "Installed by app.bootstrap.memfd_shim when the runtime Python "
        "was built without the os.memfd_create binding."
    )

    setattr(os, "memfd_create", memfd_create)
    for const_name, const_value in (
        ("MFD_CLOEXEC", MFD_CLOEXEC),
        ("MFD_ALLOW_SEALING", MFD_ALLOW_SEALING),
        ("MFD_HUGETLB", MFD_HUGETLB),
    ):
        if not hasattr(os, const_name):
            setattr(os, const_name, const_value)

    _INSTALLED = True
    return True
