"""A behavior rule does not rerun data checks. A binding or a handler still does."""

from __future__ import annotations

from types import SimpleNamespace

from app.features.form_builder.integration import data_checks_bridge as bridge


class _Log:
    def __init__(self) -> None:
        self.listener = None

    def subscribe(self, listener, priority=None):  # type: ignore[no-untyped-def]
        del priority
        self.listener = listener


def _change(name: str, added: tuple = ()) -> SimpleNamespace:
    return SimpleNamespace(
        replaced=False,
        renamed=(),
        added=added,
        removed=(),
        structure_dirty=(),
        property_dirty=((1, "property", name),),
    )


def test_a_visibility_rule_does_not_republish_and_a_bind_does(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []
    monkeypatch.setattr(bridge, "publish_session", lambda session: calls.append(session))
    log = _Log()
    session = SimpleNamespace(log=log)
    bridge.arm(session)
    assert calls == [session]
    assert log.listener is not None
    log.listener(_change("cbcsVisibleWhen"))
    assert calls == [session]
    log.listener(_change("cbcsBind"))
    assert calls == [session, session]
    log.listener(_change("cbcsOnClicked"))
    assert len(calls) == 3
    log.listener(_change("cbcsVisibleWhen", added=(1,)))
    assert len(calls) == 4
