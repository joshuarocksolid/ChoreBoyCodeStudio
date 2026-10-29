"""Codegen expanders (CONTRACTS.md sections 1.4 and 9.4).

``engine/codegen/logic_hooks.load_expanders`` imports every module in this
package in sorted name order and collects its ``EXPANDER`` object (a module
with no ``EXPANDER`` is skipped). Expanders then run ordered by
``(order, expander_id)``: built-ins use 100 step lists (``steps.py``, M6.1a),
200 state rules and values, 300 checks, 400 data.

A lane adds an expander by adding a module here and edits no shared file. The
package itself is empty on purpose; it exists since M6.0s so the first expander
lane has nothing to create. An expander never raises: the core catches it, adds
nothing for it and reports a diagnostic.
"""
