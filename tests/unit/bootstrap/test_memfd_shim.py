"""Tests for the dev memfd shim."""

from __future__ import annotations

import importlib
import os

import pytest

from app.bootstrap import memfd_shim

pytestmark = pytest.mark.unit


def _fresh_module():
    import sys

    sys.modules.pop("app.bootstrap.memfd_shim", None)
    return importlib.import_module("app.bootstrap.memfd_shim")


def _libc_loadable() -> bool:
    try:
        memfd_shim._resolve_libc()
    except OSError:
        return False
    return True


requires_libc = pytest.mark.skipif(
    not _libc_loadable(), reason="ctypes cannot load libc here (FreeCAD 1.1 jails ctypes to /opt/freecad)"
)


@pytest.fixture
def restore_memfd():
    had_native = hasattr(os, "memfd_create")
    native_impl = getattr(os, "memfd_create", None)
    yield
    if had_native:
        setattr(os, "memfd_create", native_impl)
    elif hasattr(os, "memfd_create"):
        delattr(os, "memfd_create")
    memfd_shim._INSTALLED = False


def test_install_is_noop_when_native_available(restore_memfd: None) -> None:
    if not hasattr(os, "memfd_create"):
        pytest.skip("native os.memfd_create not available on this Python")

    native_impl = os.memfd_create
    module = _fresh_module()
    installed = module.install()
    assert installed is False
    assert os.memfd_create is native_impl


@requires_libc
def test_install_provides_working_memfd_when_missing(restore_memfd: None) -> None:
    if hasattr(os, "memfd_create"):
        delattr(os, "memfd_create")

    module = _fresh_module()
    installed = module.install()
    assert installed is True
    assert hasattr(os, "memfd_create")

    fd = os.memfd_create("dev_shim_test", 0)
    try:
        assert isinstance(fd, int)
        assert fd >= 0
        os.write(fd, b"payload")
        os.lseek(fd, 0, os.SEEK_SET)
        assert os.read(fd, 7) == b"payload"
    finally:
        os.close(fd)


@requires_libc
def test_install_is_idempotent_after_shim(restore_memfd: None) -> None:
    if hasattr(os, "memfd_create"):
        delattr(os, "memfd_create")

    module = _fresh_module()
    first = module.install()
    second = module.install()
    assert first is True
    assert second is False


def test_install_reports_false_when_ctypes_refuses_libc(
    restore_memfd: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    if hasattr(os, "memfd_create"):
        monkeypatch.delattr(os, "memfd_create")
    module = _fresh_module()

    def refuse() -> None:
        raise PermissionError("ctypes: loading libraries is restricted to files under /opt/freecad")

    monkeypatch.setattr(module, "_resolve_libc", refuse)
    assert module.install() is False
    assert not hasattr(os, "memfd_create")
