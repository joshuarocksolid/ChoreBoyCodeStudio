"""Qt-free engine (CONTRACTS.md section 1).

No module under ``engine/`` may import PySide2, PySide6, shiboken, ``app.qt``,
``app.shell``, ``app.editors``, ``qtside`` or ``integration``. The only
``app.*`` imports allowed are ``app.features.form_builder.engine.*`` and
``app.plugins.rpc_protocol``.
"""
