"""Formula helper sources. One string per helper, executed for design-time eval."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from datetime import date, datetime, time
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _define(name: str, args: str, body: str, fallback: str) -> Tuple[str, str]:
    lines = ["def %s(%s):" % (name, args), "    try:"]
    for raw in body.strip("\n").split("\n"):
        if raw.strip() == "":
            lines.append("")
        else:
            lines.append("        " + raw)
    lines.append("    except Exception:")
    lines.append("        return %s" % fallback)
    return name, "\n".join(lines) + "\n"


def _read(name: str, args: str, fetch: str, parse: str) -> Tuple[str, str]:
    body = fetch.strip("\n") + "\n" + parse.strip("\n")
    return _define(name, args, body, "None")


_MONEY = """
if raw is None:
    return None
parsed = str(raw).strip()
if parsed == "":
    return None
negative = False
if len(parsed) >= 2 and parsed[0] == "(" and parsed[-1] == ")":
    negative = True
    parsed = parsed[1:-1].strip()
parsed = parsed.replace("$", "").replace(",", "").strip()
if parsed.startswith("+"):
    parsed = parsed[1:].strip()
if parsed.startswith("-"):
    negative = True
    parsed = parsed[1:].strip()
if parsed == "" or parsed == ".":
    return None
amount = Decimal(parsed)
if negative:
    amount = -amount
return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
"""

_NUMBER = """
if raw is None:
    return None
parsed = str(raw).strip().replace(",", "").replace("$", "").strip()
if parsed == "":
    return None
return Decimal(parsed).quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_UP)
"""

_WHOLE = """
if raw is None:
    return None
parsed = str(raw).strip().replace(",", "").replace("$", "").strip()
if parsed == "":
    return None
return int(Decimal(parsed))
"""

_PERCENT = """
if raw is None:
    return None
parsed = str(raw).strip().replace(",", "").replace("%", "").strip()
if parsed == "":
    return None
return Decimal(parsed) / Decimal(100)
"""

_DATE = """
if raw is None:
    return None
parsed = str(raw).strip()
if parsed == "":
    return None
if "-" in parsed:
    bits = parsed.split("-")
    if len(bits) != 3:
        return None
    return date(int(bits[0]), int(bits[1]), int(bits[2]))
if "/" in parsed:
    bits = parsed.split("/")
    if len(bits) != 3:
        return None
    return date(int(bits[2]), int(bits[0]), int(bits[1]))
return None
"""

_TIME = """
if raw is None:
    return None
parsed = str(raw).strip()
if parsed == "":
    return None
bits = parsed.split(":")
if len(bits) == 2:
    return time(int(bits[0]), int(bits[1]))
if len(bits) == 3:
    return time(int(bits[0]), int(bits[1]), int(bits[2]))
return None
"""

_ITEMS = """
if len(args) == 1 and isinstance(args[0], (list, tuple)):
    items = args[0]
else:
    items = args
"""


HELPERS = (
    _define(
        "_cbcs_is_blank",
        "value",
        """
if value is None:
    return True
if isinstance(value, str) and value.strip() == "":
    return True
return False
""",
        "False",
    ),
    _define(
        "_cbcs_bool",
        "value",
        """
if _cbcs_is_blank(value):
    return False
return bool(value)
""",
        "False",
    ),
    _define(
        "_cbcs_not",
        "value",
        """
return not _cbcs_bool(value)
""",
        "False",
    ),
    _define(
        "_cbcs_and",
        "a, b",
        """
return bool(_cbcs_bool(a) and _cbcs_bool(b))
""",
        "False",
    ),
    _define(
        "_cbcs_or",
        "a, b",
        """
return bool(_cbcs_bool(a) or _cbcs_bool(b))
""",
        "False",
    ),
    _define(
        "_cbcs_add",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return None
if type(a) is int and type(b) is int:
    return a + b
return Decimal(a) + Decimal(b)
""",
        "None",
    ),
    _define(
        "_cbcs_sub",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return None
if type(a) is int and type(b) is int:
    return a - b
return Decimal(a) - Decimal(b)
""",
        "None",
    ),
    _define(
        "_cbcs_mul",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return None
if type(a) is int and type(b) is int:
    return a * b
return Decimal(a) * Decimal(b)
""",
        "None",
    ),
    _define(
        "_cbcs_div",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return None
denominator = Decimal(b)
if denominator == 0:
    return None
return Decimal(a) / denominator
""",
        "None",
    ),
    _define(
        "_cbcs_neg",
        "a",
        """
if _cbcs_is_blank(a):
    return None
if type(a) is int:
    return -a
return -Decimal(a)
""",
        "None",
    ),
    _define(
        "_cbcs_concat",
        "a, b",
        """
def _piece(value):
    if _cbcs_is_blank(value):
        return ""
    return str(value)
return _piece(a) + _piece(b)
""",
        '""',
    ),
    _define(
        "_cbcs_lt",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return False
return bool(a < b)
""",
        "False",
    ),
    _define(
        "_cbcs_le",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return False
return bool(a <= b)
""",
        "False",
    ),
    _define(
        "_cbcs_gt",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return False
return bool(a > b)
""",
        "False",
    ),
    _define(
        "_cbcs_ge",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return False
return bool(a >= b)
""",
        "False",
    ),
    _define(
        "_cbcs_eq",
        "a, b",
        """
a_blank = _cbcs_is_blank(a)
b_blank = _cbcs_is_blank(b)
if a_blank and b_blank:
    return True
if a_blank or b_blank:
    return False
return bool(a == b)
""",
        "False",
    ),
    _define(
        "_cbcs_ne",
        "a, b",
        """
return not _cbcs_eq(a, b)
""",
        "False",
    ),
    _define(
        "_cbcs_in",
        "value, options",
        """
if _cbcs_is_blank(value):
    return False
return bool(value in options)
""",
        "False",
    ),
    _define(
        "_cbcs_not_in",
        "value, options",
        """
return not _cbcs_in(value, options)
""",
        "False",
    ),
    _define(
        "_cbcs_dec",
        "value, places",
        """
if value is None:
    return None
return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
""",
        "None",
    ),
    _define(
        "_cbcs_money",
        "value",
        """
if value is None:
    return ""
value = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
sign = "-$" if value < 0 else "$"
return sign + format(abs(value), ",.2f")
""",
        '""',
    ),
    _define(
        "_cbcs_read_line",
        "widget",
        """
text = widget.text().strip()
if text == "":
    return None
return text
""",
        "None",
    ),
    _define(
        "_cbcs_read_plain",
        "widget",
        """
text = widget.toPlainText().strip()
if text == "":
    return None
return text
""",
        "None",
    ),
    _read("_cbcs_read_money", "widget", "raw = widget.text().strip()", _MONEY),
    _read("_cbcs_read_label_money", "widget", "raw = widget.text()", _MONEY),
    _read("_cbcs_read_plain_money", "widget", "raw = widget.toPlainText().strip()", _MONEY),
    _read("_cbcs_read_number", "widget, places", "raw = widget.text().strip()", _NUMBER),
    _read("_cbcs_read_label_number", "widget, places", "raw = widget.text()", _NUMBER),
    _read(
        "_cbcs_read_plain_number",
        "widget, places",
        "raw = widget.toPlainText().strip()",
        _NUMBER,
    ),
    _read("_cbcs_read_whole", "widget", "raw = widget.text().strip()", _WHOLE),
    _read("_cbcs_read_label_whole", "widget", "raw = widget.text()", _WHOLE),
    _read("_cbcs_read_plain_whole", "widget", "raw = widget.toPlainText().strip()", _WHOLE),
    _read("_cbcs_read_percent", "widget", "raw = widget.text().strip()", _PERCENT),
    _read("_cbcs_read_label_percent", "widget", "raw = widget.text()", _PERCENT),
    _read("_cbcs_read_plain_percent", "widget", "raw = widget.toPlainText().strip()", _PERCENT),
    _read("_cbcs_read_date", "widget", "raw = widget.text().strip()", _DATE),
    _read("_cbcs_read_label_date", "widget", "raw = widget.text()", _DATE),
    _read("_cbcs_read_plain_date", "widget", "raw = widget.toPlainText().strip()", _DATE),
    _read("_cbcs_read_time", "widget", "raw = widget.text().strip()", _TIME),
    _read("_cbcs_read_label_time", "widget", "raw = widget.text()", _TIME),
    _read("_cbcs_read_plain_time", "widget", "raw = widget.toPlainText().strip()", _TIME),
    _define(
        "_cbcs_read_list",
        "widget",
        """
item = widget.currentItem()
if item is None:
    return None
return item.text()
""",
        "None",
    ),
    _define(
        "_cbcs_read_check",
        "widget",
        """
state = widget.checkState()
number = getattr(state, "value", state)
try:
    number = int(number)
except Exception:
    number = -1
label = getattr(state, "name", "")
if number == 1 or label == "PartiallyChecked":
    return None
return bool(widget.isChecked())
""",
        "None",
    ),
    _define(
        "_cbcs_read_spin",
        "widget",
        """
if widget.specialValueText() and widget.value() == widget.minimum():
    return None
return widget.value()
""",
        "None",
    ),
    _define(
        "_cbcs_read_double",
        "widget, places",
        """
if widget.specialValueText() and widget.value() == widget.minimum():
    return None
return _cbcs_dec(widget.value(), places)
""",
        "None",
    ),
    _define(
        "_cbcs_read_dateedit",
        "widget",
        """
if widget.specialValueText() and widget.date() == widget.minimumDate():
    return None
return widget.date().toPython()
""",
        "None",
    ),
    _define(
        "_cbcs_read_timeedit",
        "widget",
        """
if widget.specialValueText() and widget.time() == widget.minimumTime():
    return None
return widget.time().toPython()
""",
        "None",
    ),
    _define(
        "_cbcs_read_datetime",
        "widget",
        """
if widget.specialValueText() and widget.dateTime() == widget.minimumDateTime():
    return None
return widget.dateTime().toPython()
""",
        "None",
    ),
    _define(
        "_cbcs_read_radio",
        "group",
        """
button = group.checkedButton()
if button is None:
    return None
choice = button.property("cbcsChoice")
if isinstance(choice, str) and choice != "":
    return choice
return button.objectName()
""",
        "None",
    ),
    _define(
        "_cbcs_read_shown",
        "widget",
        """
reader = getattr(widget, "text", None)
if callable(reader):
    raw = reader()
else:
    reader = getattr(widget, "currentText", None)
    if callable(reader):
        raw = reader()
    else:
        raw = widget.toPlainText()
if raw is None:
    return None
shown = str(raw).strip()
if shown == "":
    return None
return shown
""",
        "None",
    ),
    _define(
        "_cbcs_read_enabled",
        "widget",
        """
return bool(widget.isEnabled())
""",
        "False",
    ),
    _define(
        "_cbcs_read_visible",
        "widget",
        """
return bool(widget.isVisible())
""",
        "False",
    ),
    _define(
        "_cbcs_read_checked",
        "widget",
        """
return bool(widget.isChecked())
""",
        "False",
    ),
    _define(
        "_cbcs_read_count",
        "widget",
        """
return int(widget.count())
""",
        "0",
    ),
    _define(
        "_cbcs_if_blank",
        "value, fallback",
        """
if _cbcs_is_blank(value):
    return fallback
return value
""",
        "None",
    ),
    _define(
        "_cbcs_round",
        "value, places=0",
        """
if _cbcs_is_blank(value):
    return None
if type(places) is bool:
    return None
count = places if type(places) is int else int(Decimal(places))
return Decimal(value).quantize(Decimal(1).scaleb(-count), rounding=ROUND_HALF_UP)
""",
        "None",
    ),
    _define(
        "_cbcs_abs",
        "value",
        """
if _cbcs_is_blank(value):
    return None
if type(value) is int:
    return abs(value)
return abs(Decimal(value))
""",
        "None",
    ),
    _define(
        "_cbcs_min",
        "*args",
        _ITEMS
        + """
best = None
seen = False
for item in items:
    if _cbcs_is_blank(item):
        continue
    if not seen:
        best = item
        seen = True
        continue
    if item < best:
        best = item
return best
""",
        "None",
    ),
    _define(
        "_cbcs_max",
        "*args",
        _ITEMS
        + """
best = None
seen = False
for item in items:
    if _cbcs_is_blank(item):
        continue
    if not seen:
        best = item
        seen = True
        continue
    if item > best:
        best = item
return best
""",
        "None",
    ),
    _define(
        "_cbcs_sum",
        "*args",
        _ITEMS
        + """
values = []
for item in items:
    if not _cbcs_is_blank(item):
        values.append(item)
if not values:
    return 0
if all(type(item) is int for item in values):
    total = 0
    for item in values:
        total = total + item
    return total
total_dec = Decimal(0)
for item in values:
    total_dec = total_dec + Decimal(item)
return total_dec
""",
        "0",
    ),
    _define(
        "_cbcs_avg",
        "*args",
        _ITEMS
        + """
values = []
for item in items:
    if not _cbcs_is_blank(item):
        values.append(item)
if not values:
    return None
total_dec = Decimal(0)
for item in values:
    total_dec = total_dec + Decimal(item)
return total_dec / Decimal(len(values))
""",
        "None",
    ),
    _define(
        "_cbcs_count",
        "*args",
        _ITEMS
        + """
total = 0
for item in items:
    if not _cbcs_is_blank(item):
        total = total + 1
return total
""",
        "0",
    ),
    _define(
        "_cbcs_number",
        "text",
        """
if isinstance(text, Decimal):
    return text
if type(text) is int:
    return Decimal(text)
if type(text) is bool or _cbcs_is_blank(text):
    return None
parsed = str(text).strip()
if parsed == "":
    return None
negative = False
if len(parsed) >= 2 and parsed[0] == "(" and parsed[-1] == ")":
    negative = True
    parsed = parsed[1:-1].strip()
parsed = parsed.replace("$", "").replace(",", "").strip()
if parsed.startswith("+"):
    parsed = parsed[1:].strip()
if parsed.startswith("-"):
    negative = True
    parsed = parsed[1:].strip()
if parsed == "" or parsed == ".":
    return None
amount = Decimal(parsed)
if negative:
    amount = -amount
return amount
""",
        "None",
    ),
    _define(
        "_cbcs_whole",
        "value",
        """
if _cbcs_is_blank(value) or type(value) is bool:
    return None
if type(value) is int:
    return value
return int(Decimal(value))
""",
        "None",
    ),
    _define(
        "_cbcs_text",
        'value, fmt=""',
        """
if _cbcs_is_blank(value):
    return None
if not isinstance(fmt, str) or fmt == "":
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)
if fmt == "money":
    return _cbcs_money(value)
if fmt.startswith("number:"):
    places = int(fmt.split(":", 1)[1])
    quantum = Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return format(quantum, ",.%df" % places)
if fmt.startswith("percent:"):
    places = int(fmt.split(":", 1)[1])
    scaled = Decimal(value) * Decimal(100)
    quantum = scaled.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    return format(quantum, ",.%df" % places) + "%"
if fmt == "date:iso" or fmt == "date:short" or fmt == "date:long":
    day_value = value.date() if isinstance(value, datetime) else value
    if fmt == "date:iso":
        return "%04d-%02d-%02d" % (day_value.year, day_value.month, day_value.day)
    if fmt == "date:short":
        return "%02d/%02d/%04d" % (day_value.month, day_value.day, day_value.year)
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    return "%s %d, %d" % (months[day_value.month - 1], day_value.day, day_value.year)
if fmt == "text:upper":
    return str(value).upper()
if fmt == "text:proper":
    return _cbcs_proper(str(value))
if isinstance(value, Decimal):
    return format(value, "f")
return str(value)
""",
        "None",
    ),
    _define(
        "_cbcs_len",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return len(str(value))
""",
        "None",
    ),
    _define(
        "_cbcs_upper",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return str(value).upper()
""",
        "None",
    ),
    _define(
        "_cbcs_lower",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return str(value).lower()
""",
        "None",
    ),
    _define(
        "_cbcs_trim",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return str(value).strip()
""",
        "None",
    ),
    _define(
        "_cbcs_proper",
        "value",
        """
if _cbcs_is_blank(value):
    return None
words = str(value).split(" ")
titled = []
for word in words:
    if word == "":
        titled.append("")
    else:
        titled.append(word[0].upper() + word[1:].lower())
return " ".join(titled)
""",
        "None",
    ),
    _define(
        "_cbcs_left",
        "text, n",
        """
if _cbcs_is_blank(text) or _cbcs_is_blank(n) or type(n) is bool:
    return None
count = n if type(n) is int else int(Decimal(n))
if count < 0:
    return None
return str(text)[:count]
""",
        "None",
    ),
    _define(
        "_cbcs_right",
        "text, n",
        """
if _cbcs_is_blank(text) or _cbcs_is_blank(n) or type(n) is bool:
    return None
count = n if type(n) is int else int(Decimal(n))
if count < 0:
    return None
if count == 0:
    return ""
return str(text)[-count:]
""",
        "None",
    ),
    _define(
        "_cbcs_contains",
        "text, part",
        """
if _cbcs_is_blank(text) or _cbcs_is_blank(part):
    return False
return str(part).lower() in str(text).lower()
""",
        "False",
    ),
    _define(
        "_cbcs_starts_with",
        "text, part",
        """
if _cbcs_is_blank(text) or _cbcs_is_blank(part):
    return False
return str(text).lower().startswith(str(part).lower())
""",
        "False",
    ),
    _define(
        "_cbcs_ends_with",
        "text, part",
        """
if _cbcs_is_blank(text) or _cbcs_is_blank(part):
    return False
return str(text).lower().endswith(str(part).lower())
""",
        "False",
    ),
    _define(
        "_cbcs_replace",
        "text, old, new",
        """
if _cbcs_is_blank(text):
    return None
base = text if isinstance(text, str) else str(text)
if _cbcs_is_blank(old):
    return base
replacement = "" if _cbcs_is_blank(new) else str(new)
return base.replace(str(old), replacement)
""",
        "None",
    ),
    _define(
        "_cbcs_matches",
        "text, pattern",
        """
if _cbcs_is_blank(text):
    return False
if not isinstance(pattern, str) or len(pattern) > 200:
    return False
import re
return re.fullmatch(pattern, str(text)) is not None
""",
        "False",
    ),
    _define(
        "_cbcs_is_email",
        "text",
        """
if _cbcs_is_blank(text):
    return False
import re
return re.fullmatch(r"^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", str(text)) is not None
""",
        "False",
    ),
    _define(
        "_cbcs_is_phone",
        "text",
        """
if _cbcs_is_blank(text):
    return False
kept = []
for ch in str(text):
    if ch in " -.()":
        continue
    kept.append(ch)
body = "".join(kept)
if body.startswith("+"):
    body = body[1:]
if body == "" or not body.isdigit():
    return False
size = len(body)
return size >= 10 and size <= 15
""",
        "False",
    ),
    _define(
        "_cbcs_is_zip",
        "text",
        """
if _cbcs_is_blank(text):
    return False
import re
return re.fullmatch(r"^\\d{5}(-\\d{4})?$", str(text)) is not None
""",
        "False",
    ),
    _define(
        "_cbcs_today",
        "",
        """
return date.today()
""",
        "None",
    ),
    _define(
        "_cbcs_now",
        "",
        """
return datetime.now()
""",
        "None",
    ),
    _define(
        "_cbcs_date",
        "y, m, d",
        """
if _cbcs_is_blank(y) or _cbcs_is_blank(m) or _cbcs_is_blank(d):
    return None
if type(y) is bool or type(m) is bool or type(d) is bool:
    return None
year_n = y if type(y) is int else int(Decimal(y))
month_n = m if type(m) is int else int(Decimal(m))
day_n = d if type(d) is int else int(Decimal(d))
return date(year_n, month_n, day_n)
""",
        "None",
    ),
    _define(
        "_cbcs_year",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return int(value.year)
""",
        "None",
    ),
    _define(
        "_cbcs_month",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return int(value.month)
""",
        "None",
    ),
    _define(
        "_cbcs_day",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return int(value.day)
""",
        "None",
    ),
    _define(
        "_cbcs_weekday",
        "value",
        """
if _cbcs_is_blank(value):
    return None
return int(value.weekday()) + 1
""",
        "None",
    ),
    _define(
        "_cbcs_add_days",
        "value, n",
        """
if _cbcs_is_blank(value) or _cbcs_is_blank(n) or type(n) is bool:
    return None
days = n if type(n) is int else int(Decimal(n))
from datetime import timedelta
return value + timedelta(days=days)
""",
        "None",
    ),
    _define(
        "_cbcs_add_months",
        "value, n",
        """
if _cbcs_is_blank(value) or _cbcs_is_blank(n) or type(n) is bool:
    return None
count = n if type(n) is int else int(Decimal(n))
is_dt = isinstance(value, datetime)
month_index = (value.month - 1) + count
year_n = value.year + (month_index // 12)
month_n = (month_index % 12) + 1
if month_n == 12:
    probe = date(year_n + 1, 1, 1)
else:
    probe = date(year_n, month_n + 1, 1)
last_day = date.fromordinal(probe.toordinal() - 1).day
day_n = value.day if value.day <= last_day else last_day
if is_dt:
    return datetime(
        year_n,
        month_n,
        day_n,
        value.hour,
        value.minute,
        value.second,
        value.microsecond,
    )
return date(year_n, month_n, day_n)
""",
        "None",
    ),
    _define(
        "_cbcs_days_between",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return None
try:
    return int((b - a).days)
except Exception:
    left = a.date() if isinstance(a, datetime) else a
    right = b.date() if isinstance(b, datetime) else b
    return int((right - left).days)
""",
        "None",
    ),
    _define(
        "_cbcs_date_diff",
        "a, b",
        """
if _cbcs_is_blank(a) or _cbcs_is_blank(b):
    return None
try:
    return int((a - b).days)
except Exception:
    left = a.date() if isinstance(a, datetime) else a
    right = b.date() if isinstance(b, datetime) else b
    return int((left - right).days)
""",
        "None",
    ),
)


_ids = [item[0] for item in HELPERS]
if len(_ids) != len(set(_ids)):
    raise RuntimeError("duplicate formula helper id")


_LIVE = None  # type: Optional[Dict[str, Any]]


def helper_table():
    # type: () -> Tuple[Tuple[str, str], ...]
    return HELPERS


def helper_sources(ids: Iterable[str]) -> str:
    wanted = set(ids)
    chunks = []  # type: List[str]
    for helper_id, source in HELPERS:
        if helper_id in wanted:
            chunks.append(source.strip("\n"))
    if not chunks:
        return ""
    return "\n\n".join(chunks) + "\n"


def live_helpers():
    # type: () -> Dict[str, Any]
    global _LIVE
    if _LIVE is None:
        namespace = {
            "Decimal": Decimal,
            "ROUND_HALF_UP": ROUND_HALF_UP,
            "date": date,
            "datetime": datetime,
            "time": time,
            "re": re,
        }  # type: Dict[str, object]
        for _helper_id, source in HELPERS:
            exec(source, namespace)  # noqa: S102
        _LIVE = {
            key: value
            for key, value in namespace.items()
            if key.startswith("_cbcs_")
        }
    return dict(_LIVE)
