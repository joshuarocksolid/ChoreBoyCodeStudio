"""A style sheet read into rules and declarations, with line-and-column problems. Qt-free.

``parse_sheet`` never raises and always returns what it could read. Problems
come in two severities, chosen so the check agrees with Qt's own parser
(UX-STYLE-004, tested against a hidden Qt widget):

* ``error``: the shape Qt refuses (an unclosed or stray ``}``, ``)`` or ``]``,
  an unclosed quote). Qt ignores the whole sheet.
* ``warning``: Qt reads the sheet and skips the line (a declaration with no
  colon, a missing ``;``, a property Qt doesn't know, an unclosed comment).

A sheet with no rule, only declarations, is what a widget's own sheet usually
is; Qt applies it to the widget and its children as if it were wrapped in
``* { ... }``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.features.form_builder.engine.style.properties import is_known_property, is_known_state
from app.features.form_builder.engine.style.tokenizer import AT, DELIM, IDENT, Token, tokenize

ERROR = "error"
WARNING = "warning"

#: ``Problem.kind`` values.
MISSING = "missing"
STRAY = "stray"
COLON = "colon"
SEMICOLON = "semicolon"
PROPERTY = "property"
SELECTOR = "selector"
STATE = "state"

_OPEN = {"{": "}", "(": ")", "[": "]"}
_CLOSE = {"}": "{", ")": "(", "]": "["}


@dataclass(frozen=True)
class Problem:
    """``text`` is the sentence without its place; ``line`` is 1-based, 0 for none."""

    severity: str
    kind: str
    line: int
    column: int
    text: str
    word: str = ""

    @property
    def sentence(self) -> str:
        return "Line %d: %s" % (self.line, self.text) if self.line > 0 else self.text


@dataclass(frozen=True)
class Declaration:
    """``name: value``. Offsets index the sheet text; ``end`` is after the ``;`` when there is one."""

    name: str
    value: str
    line: int
    column: int
    start: int
    value_start: int
    value_end: int
    end: int


@dataclass(frozen=True)
class Rule:
    """``selector { declarations }``. ``close`` is -1 when the ``}`` is missing."""

    selector: str
    line: int
    column: int
    start: int
    open: int
    close: int
    declarations: Tuple[Declaration, ...]

    @property
    def end(self) -> int:
        return self.close + 1 if self.close >= 0 else self.open + 1


@dataclass(frozen=True)
class Sheet:
    text: str
    rules: Tuple[Rule, ...]
    declarations: Tuple[Declaration, ...]
    problems: Tuple[Problem, ...]

    @property
    def rule_count(self) -> int:
        """A sheet of only declarations counts as one rule (Qt wraps it in ``*``)."""
        return len(self.rules) + (1 if self.declarations and not self.rules else 0)

    def errors(self) -> Tuple[Problem, ...]:
        return tuple(problem for problem in self.problems if problem.severity == ERROR)


def parse_sheet(text: str) -> Sheet:
    tokens, lex = tokenize(text)
    significant = [token for token in tokens if token.significant]
    problems: List[Problem] = []
    for item in lex:
        if item.missing == "*/":
            problems.append(Problem(WARNING, MISSING, item.line, item.column, "a */ is missing.", "*/"))
        else:
            problems.append(Problem(ERROR, MISSING, item.line, item.column, "a %s is missing." % item.missing, item.missing))
    problems.extend(_balance(significant))
    rules: List[Rule] = []
    declarations: List[Declaration] = []
    _structure(text, significant, rules, declarations, problems)
    problems.sort(key=lambda found: (0 if found.severity == ERROR else 1, found.line, found.column))
    return Sheet(text, tuple(rules), tuple(declarations), tuple(problems))


def _is(token: Token, char: str) -> bool:
    return token.kind == DELIM and token.text == char


def _balance(tokens: List[Token]) -> List[Problem]:
    found: List[Problem] = []
    stack: List[Token] = []
    for token in tokens:
        if token.kind != DELIM:
            continue
        if token.text in _OPEN:
            stack.append(token)
        elif token.text in _CLOSE:
            wanted = _CLOSE[token.text]
            if not any(opener.text == wanted for opener in stack):
                found.append(Problem(ERROR, STRAY, token.line, token.column, "a %s is missing." % wanted, wanted))
                continue
            while stack[-1].text != wanted:
                opener = stack.pop()
                closer = _OPEN[opener.text]
                found.append(Problem(ERROR, MISSING, opener.line, opener.column, "a %s is missing." % closer, closer))
            stack.pop()
    for opener in stack:
        closer = _OPEN[opener.text]
        found.append(Problem(ERROR, MISSING, opener.line, opener.column, "a %s is missing." % closer, closer))
    return found


def _structure(
    text: str,
    tokens: List[Token],
    rules: List[Rule],
    declarations: List[Declaration],
    problems: List[Problem],
) -> None:
    count = len(tokens)
    index = 0
    while index < count:
        first = index
        depth = 0
        while index < count:
            token = tokens[index]
            if token.kind == DELIM:
                if token.text in "([":
                    depth += 1
                elif token.text in ")]":
                    depth = max(0, depth - 1)
                elif depth == 0 and token.text in "{};":
                    break
            index += 1
        prelude = tokens[first:index]
        if prelude and prelude[0].kind == AT:
            # An at-rule (``@import``, ``@media``): Qt reads it, this check has nothing to say about it.
            if index < count and tokens[index].text == "{":
                close = _matching_brace(tokens, index)
                index = (close if close >= 0 else count - 1) + 1
            else:
                index += 1
            continue
        if index >= count:
            if prelude:
                _loose(text, prelude, declarations, problems)
            return
        stop = tokens[index]
        if stop.text == "{":
            close = _matching_brace(tokens, index)
            body = tokens[index + 1 : close if close >= 0 else count]
            _states(prelude, problems)
            rule_declarations = _declarations(text, body, problems)
            first_token = prelude[0] if prelude else stop
            selector = text[first_token.start : prelude[-1].end] if prelude else ""
            rules.append(
                Rule(
                    selector,
                    first_token.line,
                    first_token.column,
                    first_token.start,
                    stop.start,
                    tokens[close].start if close >= 0 else -1,
                    tuple(rule_declarations),
                )
            )
            index = (close if close >= 0 else count - 1) + 1
            if close < 0:
                return
        elif stop.text == ";":
            if prelude:
                _declaration(text, prelude, stop, declarations, problems)
            index += 1
        else:
            index += 1


def _states(prelude: List[Token], problems: List[Problem]) -> None:
    """A warning for each pseudo-state Qt doesn't know: the rule then matches nothing (UX-STYLE-004)."""
    for position, token in enumerate(prelude):
        if not _is(token, ":") or (position > 0 and _is(prelude[position - 1], ":")):
            continue
        after = position + 1
        if after < len(prelude) and _is(prelude[after], ":"):
            continue
        if after < len(prelude) and _is(prelude[after], "!"):
            after += 1
        if after < len(prelude) and prelude[after].kind == IDENT and not is_known_state(prelude[after].text):
            word = prelude[after]
            problems.append(
                Problem(WARNING, STATE, word.line, word.column, "%s isn't a state Qt knows." % _quoted(word.text), word.text)
            )


def _matching_brace(tokens: List[Token], opening: int) -> int:
    depth = 0
    for position in range(opening, len(tokens)):
        token = tokens[position]
        if _is(token, "{"):
            depth += 1
        elif _is(token, "}"):
            depth -= 1
            if depth == 0:
                return position
    return -1


def _loose(text: str, prelude: List[Token], declarations: List[Declaration], problems: List[Problem]) -> None:
    """What is left at the end of the text: a last declaration without ``;``, or a selector with no body."""
    if any(_is(token, ":") for token in prelude) and prelude[0].kind == IDENT:
        _declaration(text, prelude, None, declarations, problems)
        return
    first = prelude[0]
    problems.append(Problem(WARNING, SELECTOR, first.line, first.column, "a { is missing.", "{"))


def _declarations(text: str, body: List[Token], problems: List[Problem]) -> List[Declaration]:
    found: List[Declaration] = []
    chunk: List[Token] = []
    depth = 0
    for token in body:
        if token.kind == DELIM:
            if token.text in "([{":
                depth += 1
            elif token.text in ")]}":
                depth = max(0, depth - 1)
            elif token.text == ";" and depth == 0:
                if chunk:
                    _declaration(text, chunk, token, found, problems)
                chunk = []
                continue
        chunk.append(token)
    if chunk:
        _declaration(text, chunk, None, found, problems)
    return found


def _declaration(
    text: str,
    chunk: List[Token],
    stop: Optional[Token],
    out: List[Declaration],
    problems: List[Problem],
) -> None:
    colon = _top_level_colon(chunk)
    head = chunk[0]
    if colon < 0:
        problems.append(
            Problem(WARNING, COLON, head.line, head.column, "a : is missing after %s." % _quoted(head.text), head.text)
        )
        return
    name_tokens = chunk[:colon]
    value_tokens = chunk[colon + 1 :]
    name = text[name_tokens[0].start : name_tokens[-1].end] if name_tokens else ""
    if not name or len(name_tokens) != 1 or name_tokens[0].kind != IDENT or not is_known_property(name):
        word = name or ":"
        problems.append(
            Problem(WARNING, PROPERTY, head.line, head.column, "%s isn't a property Qt knows." % _quoted(word), word)
        )
    value_start = value_tokens[0].start if value_tokens else chunk[colon].end
    value_end = value_tokens[-1].end if value_tokens else chunk[colon].end
    missing = _missing_semicolon(value_tokens)
    if missing is not None:
        problems.append(Problem(WARNING, SEMICOLON, missing.line, missing.column, "a ; is missing after the value.", ";"))
    end = stop.end if stop is not None else chunk[-1].end
    out.append(
        Declaration(
            name,
            text[value_start:value_end],
            head.line,
            head.column,
            head.start,
            value_start,
            value_end,
            end,
        )
    )


def _top_level_colon(chunk: List[Token]) -> int:
    depth = 0
    for position, token in enumerate(chunk):
        if token.kind != DELIM:
            continue
        if token.text in "([{":
            depth += 1
        elif token.text in ")]}":
            depth = max(0, depth - 1)
        elif token.text == ":" and depth == 0:
            return position
    return -1


def _missing_semicolon(value: List[Token]) -> Optional[Token]:
    """The last token of a value that runs into the next ``name:`` (``color: red background: blue``)."""
    depth = 0
    for position, token in enumerate(value):
        if token.kind == DELIM:
            if token.text in "([{":
                depth += 1
            elif token.text in ")]}":
                depth = max(0, depth - 1)
            continue
        if depth or token.kind != IDENT or position == 0:
            continue
        after = value[position + 1] if position + 1 < len(value) else None
        if after is not None and _is(after, ":"):
            return value[position - 1]
    return None


def _quoted(word: str) -> str:
    return "“%s”" % word
