"""Codegen expanders (CONTRACTS.md sections 1.4 and 9.4).

``engine/codegen/logic_hooks.load_expanders`` imports every module in this
package in sorted name order and collects its ``EXPANDER`` object (a module
with no ``EXPANDER`` is skipped). Expanders then run ordered by
``(order, expander_id)``: 100 steps, 200 rules (with defaults), 300 checks,
350 formats, 900+ "after everything" (form events).

A lane adds an expander by adding a module here and edits no shared file. The
package itself is empty on purpose; it exists since M6.0s so the first expander
lane has nothing to create. An expander never raises: the core catches it, adds
nothing for it and reports a diagnostic.
"""
