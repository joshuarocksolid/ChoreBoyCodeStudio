"""Fixture form with logic for the M6.0b tests. Not collected."""

from __future__ import annotations

from typing import Dict, Tuple

from app.features.form_builder.engine.commands.refs import identity_name
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import StringValue

CLEAR_STEPS = (
    "[\n"
    '  {"do": "slot", "target": "nameEdit", "slot": "clear()"},\n'
    '  {"do": "call", "when": "len(nameEdit.text) > 0 and nameEdit != other", "method": "log_clear"},\n'
    '  {"do": "slot", "target": "other", "slot": "setFocus()", "note": {"keep": "nameEdit"}}\n'
    "]"
)

CHECKS = (
    "[\n"
    '  {"check": "formula", "formula": "len(nameEdit.text) > 2", "message": "nameEdit is too short"},\n'
    '  {"check": "range", "min": "today()", "max": 5}\n'
    "]"
)


def prop_xml(name: str, text: str, notr: bool = True) -> str:
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")
    return (
        '    <property name="%s" stdset="0">\n     <string%s>%s</string>\n    </property>\n'
        % (name, ' notr="true"' if notr else "", esc)
    )


def form(marker: str = '{"version":1}', extra_root: str = "", connections: str = "") -> str:
    root_marker = prop_xml("cbcsLogic", marker) if marker else ""
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
%s%s
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLineEdit" name="nameEdit">
%s%s%s    </widget>
   </item>
   <item>
    <widget class="QLabel" name="nameError"/>
   </item>
   <item>
    <widget class="QLineEdit" name="other"/>
   </item>
   <item>
    <widget class="QCheckBox" name="useName"/>
   </item>
   <item>
    <widget class="QPushButton" name="clearButton">
%s    </widget>
   </item>
   <item>
    <widget class="QLabel" name="total">
%s    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections>%s</connections>
</ui>
""" % (
        root_marker,
        extra_root,
        prop_xml("cbcsEnabledWhen", "useName  and   not (other == nameEdit)  # nameEdit"),
        prop_xml("cbcsErrorLabel", "nameError"),
        prop_xml("cbcsValidate", CHECKS),
        prop_xml("cbcsOnClicked", CLEAR_STEPS),
        prop_xml("cbcsValue", "f(nameEdit=1, key=nameEdit) + nameEdit.nameEdit + \"nameEdit\""),
        connections,
    )


CONNECTION = """
  <connection>
   <sender>clearButton</sender>
   <signal>clicked()</signal>
   <receiver>nameEdit</receiver>
   <slot>selectAll()</slot>
  </connection>"""


def texts(doc: UiDocument) -> Dict[Tuple[str, str], str]:
    found = {}
    for node in doc.iter_preorder():
        owner = identity_name(node) or node.kind
        for entry in node.properties():
            if entry.name.startswith("cbcs") and isinstance(entry.value, StringValue):
                found[(owner, entry.name)] = entry.value.text
    return found
