"""Style sheets, Qt-free (M5.3, UX-STYLE-001 .. 013).

* ``tokenizer`` and ``sheet`` read the text into rules and declarations with a
  line and column for every problem.
* ``check`` turns that and Qt's own verdict (from ``qtside/style/probe.py``)
  into the one status sentence the drawer shows.
* ``selectors`` says which widgets of a form a rule reaches.
* ``edit`` adds, replaces and removes the ``color`` declaration the Text
  colour row manages, and rewrites ``#name`` selectors on a rename.
"""
