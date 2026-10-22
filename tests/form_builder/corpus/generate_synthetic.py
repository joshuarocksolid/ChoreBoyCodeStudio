"""Write the MIT synthetic .ui corpus.

Safe to rerun. Rewrites ``synthetic/`` and ``malformed/`` only.

    python3 tests/form_builder/corpus/generate_synthetic.py
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path
from typing import Dict, List


CORPUS = Path(__file__).resolve().parent
SYNTHETIC = CORPUS / "synthetic"
MALFORMED = CORPUS / "malformed"

# QUiLoader 6.8.3 creates these as a form root. It refuses QColorDialog,
# QErrorMessage, QFileDialog, QFocusFrame, QFontDialog, QInputDialog,
# QMdiSubWindow, QMessageBox, QProgressDialog, QRhiWidget, QSplashScreen,
# and QTabBar even though PySide can construct them.
WIDGET_CLASSES = (
    "QAbstractScrollArea",
    "QAbstractSlider",
    "QAbstractSpinBox",
    "QCalendarWidget",
    "QCheckBox",
    "QColumnView",
    "QComboBox",
    "QCommandLinkButton",
    "QDateEdit",
    "QDateTimeEdit",
    "QDial",
    "QDialog",
    "QDialogButtonBox",
    "QDockWidget",
    "QDoubleSpinBox",
    "QFontComboBox",
    "QFrame",
    "QGraphicsView",
    "QGroupBox",
    "QKeySequenceEdit",
    "QLCDNumber",
    "QLabel",
    "QLineEdit",
    "QListView",
    "QListWidget",
    "QMainWindow",
    "QMdiArea",
    "QMenu",
    "QMenuBar",
    "QPlainTextEdit",
    "QProgressBar",
    "QPushButton",
    "QRadioButton",
    "QScrollArea",
    "QScrollBar",
    "QSlider",
    "QSpinBox",
    "QSplitter",
    "QStackedWidget",
    "QStatusBar",
    "QTabWidget",
    "QTableView",
    "QTableWidget",
    "QTextBrowser",
    "QTextEdit",
    "QTimeEdit",
    "QToolBar",
    "QToolBox",
    "QToolButton",
    "QTreeView",
    "QTreeWidget",
    "QUndoView",
    "QWidget",
    "QWizard",
    "QWizardPage",
)

FORM_SPECS = (
    ("invoice_dialog", "Invoice", (("Customer", "QLineEdit", "customerEdit"), ("Number", "QLineEdit", "numberEdit"), ("Issued", "QDateEdit", "issuedEdit"), ("Due", "QDateEdit", "dueEdit"), ("Notes", "QPlainTextEdit", "notesEdit"), ("Total", "QDoubleSpinBox", "totalEdit"), ("Taxable", "QCheckBox", "taxableCheck"))),
    ("customer_dialog", "Customer", (("Name", "QLineEdit", "nameEdit"), ("Phone", "QLineEdit", "phoneEdit"), ("Email", "QLineEdit", "emailEdit"), ("City", "QLineEdit", "cityEdit"), ("Active", "QCheckBox", "activeCheck"), ("Since", "QDateEdit", "sinceEdit"))),
    ("payment_dialog", "Payment", (("Amount", "QDoubleSpinBox", "amountEdit"), ("Method", "QComboBox", "methodCombo"), ("Paid", "QDateEdit", "paidEdit"), ("Reference", "QLineEdit", "referenceEdit"), ("Memo", "QPlainTextEdit", "memoEdit"))),
    ("item_editor", "Item", (("SKU", "QLineEdit", "skuEdit"), ("Description", "QLineEdit", "descriptionEdit"), ("Quantity", "QSpinBox", "qtyEdit"), ("Price", "QDoubleSpinBox", "priceEdit"), ("Taxable", "QCheckBox", "taxableCheck"))),
    ("search_panel", "Search", (("Query", "QLineEdit", "queryEdit"), ("From", "QDateEdit", "fromEdit"), ("To", "QDateEdit", "toEdit"), ("Status", "QComboBox", "statusCombo"), ("Include closed", "QCheckBox", "closedCheck"))),
    ("preferences_general", "Preferences", (("Company", "QLineEdit", "companyEdit"), ("Start", "QDateEdit", "startEdit"), ("Autosave", "QCheckBox", "autosaveCheck"), ("Minutes", "QSpinBox", "minutesEdit"))),
    ("preferences_appearance", "Appearance", (("Family", "QFontComboBox", "familyCombo"), ("Size", "QSpinBox", "sizeEdit"), ("Zoom", "QSlider", "zoomSlider"), ("Compact", "QCheckBox", "compactCheck"))),
    ("printer_dialog", "Print", (("Printer", "QComboBox", "printerCombo"), ("Copies", "QSpinBox", "copiesEdit"), ("Color", "QCheckBox", "colorCheck"), ("Range", "QLineEdit", "rangeEdit"))),
    ("user_account", "User", (("Username", "QLineEdit", "usernameEdit"), ("Role", "QComboBox", "roleCombo"), ("Enabled", "QCheckBox", "enabledCheck"), ("Expires", "QDateEdit", "expiresEdit"))),
    ("address_form", "Address", (("Line 1", "QLineEdit", "line1Edit"), ("Line 2", "QLineEdit", "line2Edit"), ("City", "QLineEdit", "cityEdit"), ("Region", "QLineEdit", "regionEdit"), ("Postal", "QLineEdit", "postalEdit"), ("Country", "QComboBox", "countryCombo"))),
    ("schedule_dialog", "Schedule", (("Start", "QDateTimeEdit", "startEdit"), ("End", "QDateTimeEdit", "endEdit"), ("All day", "QCheckBox", "allDayCheck"), ("Reminder", "QSpinBox", "reminderEdit"))),
    ("filter_bar", "Filter", (("Text", "QLineEdit", "textEdit"), ("Minimum", "QSpinBox", "minEdit"), ("Maximum", "QSpinBox", "maxEdit"), ("Category", "QComboBox", "categoryCombo"))),
    ("note_editor", "Note", (("Title", "QLineEdit", "titleEdit"), ("Body", "QPlainTextEdit", "bodyEdit"), ("Pinned", "QCheckBox", "pinnedCheck"))),
    ("contact_card", "Contact", (("Name", "QLineEdit", "nameEdit"), ("Phone", "QLineEdit", "phoneEdit"), ("Email", "QLineEdit", "emailEdit"), ("Birthday", "QDateEdit", "birthdayEdit"), ("Favorite", "QCheckBox", "favoriteCheck"))),
    ("inventory_adjust", "Adjustment", (("Item", "QComboBox", "itemCombo"), ("Delta", "QSpinBox", "deltaEdit"), ("Reason", "QLineEdit", "reasonEdit"), ("When", "QDateTimeEdit", "whenEdit"))),
    ("tax_settings", "Tax", (("Rate", "QDoubleSpinBox", "rateEdit"), ("Inclusive", "QCheckBox", "inclusiveCheck"), ("Label", "QLineEdit", "labelEdit"), ("Effective", "QDateEdit", "effectiveEdit"))),
    ("shipping_form", "Shipping", (("Carrier", "QComboBox", "carrierCombo"), ("Service", "QComboBox", "serviceCombo"), ("Weight", "QDoubleSpinBox", "weightEdit"), ("Insured", "QCheckBox", "insuredCheck"), ("Ship date", "QDateEdit", "shipEdit"))),
    ("login_dialog", "Sign in", (("User", "QLineEdit", "userEdit"), ("Remember", "QCheckBox", "rememberCheck"))),
    ("status_filters", "Status", (("Open", "QCheckBox", "openCheck"), ("Pending", "QCheckBox", "pendingCheck"), ("Closed", "QCheckBox", "closedCheck"), ("Owner", "QComboBox", "ownerCombo"))),
    ("date_range", "Dates", (("Start", "QDateEdit", "startEdit"), ("End", "QDateEdit", "endEdit"), ("Preset", "QComboBox", "presetCombo"))),
    ("number_formats", "Numbers", (("Decimals", "QSpinBox", "decimalsEdit"), ("Prefix", "QLineEdit", "prefixEdit"), ("Suffix", "QLineEdit", "suffixEdit"), ("Sample", "QLabel", "sampleLabel"))),
    ("message_dialog", "Message", (("Title", "QLineEdit", "titleEdit"), ("Body", "QTextEdit", "bodyEdit"), ("Urgent", "QCheckBox", "urgentCheck"))),
    ("backup_dialog", "Backup", (("Folder", "QLineEdit", "folderEdit"), ("Keep", "QSpinBox", "keepEdit"), ("Compress", "QCheckBox", "compressCheck"), ("When", "QTimeEdit", "whenEdit"))),
    ("export_dialog", "Export", (("Format", "QComboBox", "formatCombo"), ("Path", "QLineEdit", "pathEdit"), ("Headers", "QCheckBox", "headersCheck"), ("From", "QDateEdit", "fromEdit"), ("To", "QDateEdit", "toEdit"))),
    ("reminder_dialog", "Reminder", (("Title", "QLineEdit", "titleEdit"), ("At", "QDateTimeEdit", "atEdit"), ("Repeat", "QComboBox", "repeatCombo"), ("Enabled", "QCheckBox", "enabledCheck"))),
    ("discount_dialog", "Discount", (("Name", "QLineEdit", "nameEdit"), ("Percent", "QDoubleSpinBox", "percentEdit"), ("Starts", "QDateEdit", "startsEdit"), ("Ends", "QDateEdit", "endsEdit"), ("Stack", "QCheckBox", "stackCheck"))),
    ("warehouse_dialog", "Warehouse", (("Code", "QLineEdit", "codeEdit"), ("Name", "QLineEdit", "nameEdit"), ("Aisles", "QSpinBox", "aislesEdit"), ("Active", "QCheckBox", "activeCheck"))),
    ("shift_dialog", "Shift", (("Name", "QLineEdit", "nameEdit"), ("Start", "QTimeEdit", "startEdit"), ("End", "QTimeEdit", "endEdit"), ("Overnight", "QCheckBox", "overnightCheck"))),
    ("label_print", "Labels", (("Template", "QComboBox", "templateCombo"), ("Copies", "QSpinBox", "copiesEdit"), ("Border", "QCheckBox", "borderCheck"))),
    ("audit_filter", "Audit", (("Actor", "QLineEdit", "actorEdit"), ("Action", "QComboBox", "actionCombo"), ("Since", "QDateTimeEdit", "sinceEdit"), ("Failures only", "QCheckBox", "failuresCheck"))),
    ("vendor_dialog", "Vendor", (("Name", "QLineEdit", "nameEdit"), ("Account", "QLineEdit", "accountEdit"), ("Terms", "QComboBox", "termsCombo"), ("Active", "QCheckBox", "activeCheck"))),
    ("receipt_dialog", "Receipt", (("Number", "QLineEdit", "numberEdit"), ("Amount", "QDoubleSpinBox", "amountEdit"), ("Received", "QDateEdit", "receivedEdit"), ("Cash", "QCheckBox", "cashCheck"))),
    ("route_dialog", "Route", (("Name", "QLineEdit", "nameEdit"), ("Stops", "QSpinBox", "stopsEdit"), ("Driver", "QComboBox", "driverCombo"), ("Starts", "QTimeEdit", "startsEdit"))),
    ("bin_dialog", "Bin", (("Code", "QLineEdit", "codeEdit"), ("Row", "QSpinBox", "rowEdit"), ("Capacity", "QDoubleSpinBox", "capacityEdit"), ("Locked", "QCheckBox", "lockedCheck"))),
    ("season_dialog", "Season", (("Name", "QLineEdit", "nameEdit"), ("Opens", "QDateEdit", "opensEdit"), ("Closes", "QDateEdit", "closesEdit"), ("Current", "QCheckBox", "currentCheck"))),
    ("crew_dialog", "Crew", (("Lead", "QLineEdit", "leadEdit"), ("Size", "QSpinBox", "sizeEdit"), ("Shift", "QComboBox", "shiftCombo"), ("On call", "QCheckBox", "onCallCheck"))),
    ("quote_dialog", "Quote", (("Customer", "QLineEdit", "customerEdit"), ("Valid until", "QDateEdit", "validEdit"), ("Total", "QDoubleSpinBox", "totalEdit"), ("Approved", "QCheckBox", "approvedCheck"))),
    ("meter_dialog", "Meter", (("Serial", "QLineEdit", "serialEdit"), ("Reading", "QDoubleSpinBox", "readingEdit"), ("Read on", "QDateTimeEdit", "readEdit"), ("Estimated", "QCheckBox", "estimatedCheck"))),
)


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _png(width: int, height: int, rgb: bytes) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + rgb * width for _ in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def _wipe(directory: Path) -> None:
    if directory.exists():
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    directory.mkdir(parents=True, exist_ok=True)


def _geometry() -> str:
    return """  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>640</width>
    <height>480</height>
   </rect>
  </property>"""


def _document(class_name: str, widget_class: str, title: str, inner: str, tail: str = "", ui_attrs: str = 'version="4.0"') -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- SPDX-License-Identifier: MIT -->
<ui %s>
 <class>%s</class>
 <widget class="%s" name="%s">
%s
  <property name="windowTitle">
   <string>%s</string>
  </property>
%s
 </widget>
%s
</ui>
""" % (
        ui_attrs,
        class_name,
        widget_class,
        class_name,
        _geometry(),
        _esc(title),
        inner,
        tail,
    )


def _form_xml(class_name: str, title: str, rows: tuple) -> str:
    items = []
    stops = []
    for index, (label, widget_class, name) in enumerate(rows):
        label_name = "label_%s" % name
        items.append(
            """   <item row="%d" column="0">
    <widget class="QLabel" name="%s">
     <property name="text">
      <string>%s</string>
     </property>
     <property name="buddy">
      <cstring>%s</cstring>
     </property>
    </widget>
   </item>
   <item row="%d" column="1">
    <widget class="%s" name="%s"/>
   </item>"""
            % (index, label_name, _esc(label), name, index, widget_class, name)
        )
        stops.append("  <tabstop>%s</tabstop>" % name)
    inner = """  <layout class="QFormLayout" name="formLayout">
%s
  </layout>""" % "\n".join(items)
    tail = """ <tabstops>
%s
 </tabstops>""" % "\n".join(stops)
    return _document(class_name, "QDialog", title, inner, tail)


def _widget_xml(widget_class: str) -> str:
    class_name = "%sHost" % widget_class[1:]
    return _document(
        class_name,
        widget_class,
        widget_class,
        """  <property name="toolTip">
   <string>%s host</string>
  </property>"""
        % widget_class,
    )


def _property_xml(type_name: str, body: str, prop_name: str) -> str:
    class_name = "Prop%s" % type_name[:1].upper() + type_name[1:]
    inner = """  <property name="%s" stdset="0">
   %s
  </property>""" % (prop_name, body)
    return _document(class_name, "QWidget", type_name, inner)


def _nested_xml() -> str:
    # Outermost frame, 13 nested frames, and the leaf label: 15 widgets.
    widget = """<widget class="QLabel" name="leaf">
 <property name="text"><string>leaf</string></property>
</widget>"""
    for level in range(13, 0, -1):
        widget = """<widget class="QFrame" name="level%d">
 <layout class="QVBoxLayout" name="lay%d">
  <item>
   %s
  </item>
 </layout>
</widget>""" % (level, level, widget)
    return _document("NestedFifteen", "QFrame", "Nested 15", """  <layout class="QVBoxLayout" name="layOuter">
   <item>
    %s
   </item>
  </layout>""" % widget)


def _thousand_xml() -> str:
    items = []
    for index in range(1000):
        row, column = divmod(index, 40)
        items.append(
            """   <item row="%d" column="%d">
    <widget class="QLabel" name="w%04d">
     <property name="text"><string>%d</string></property>
    </widget>
   </item>"""
            % (row, column, index, index)
        )
    inner = """  <layout class="QGridLayout" name="grid1000">
%s
  </layout>""" % "\n".join(items)
    return _document("ThousandWidgets", "QWidget", "1000 widgets", inner)


def _kitchen_sink() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!-- SPDX-License-Identifier: MIT -->
<ui version="4.0" language="c++" displayname="Kitchen sink" idbasedtr="true" connectslotsbyname="true" stdsetdef="0" stdSetDef="1">
 <author>ChoreBoy Code Studio corpus</author>
 <comment>Synthetic form that exercises the ui4 element set.</comment>
 <exportmacro>CBCS_EXPORT</exportmacro>
 <class>KitchenSink</class>
 <widget class="QMainWindow" name="KitchenSink">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>900</width>
    <height>640</height>
   </rect>
  </property>
  <property name="windowTitle">
   <string notr="false" comment="window title" extracomment="shown in the title bar" id="window.title">Kitchen sink</string>
  </property>
  <property name="locale">
   <locale language="English" country="UnitedStates"/>
  </property>
  <widget class="QWidget" name="centralwidget">
   <layout class="QGridLayout" name="gridLayout" stretch="1,0" rowstretch="1,0,0" columnstretch="2,1" rowminimumheight="24,0,0" columnminimumwidth="80,40">
    <property name="spacing">
     <number>6</number>
    </property>
    <attribute name="cbcsLayoutNote" stdset="0">
     <string>grid</string>
    </attribute>
    <item row="0" column="0" rowspan="1" colspan="2" alignment="Qt::AlignRight|Qt::AlignVCenter">
     <layout class="QVBoxLayout" name="nestedBox" stretch="1,0">
      <item>
       <widget class="QLabel" name="nameLabel">
        <class>QLabel</class>
        <property name="text">
         <string>&amp;Name</string>
        </property>
        <property name="buddy">
         <cstring>nameEdit</cstring>
        </property>
       </widget>
      </item>
      <item>
       <spacer name="verticalSpacer">
        <property name="orientation">
         <enum>Qt::Vertical</enum>
        </property>
        <property name="sizeType">
         <enum>QSizePolicy::Expanding</enum>
        </property>
        <property name="sizeHint" stdset="0">
         <size>
          <width>20</width>
          <height>40</height>
         </size>
        </property>
       </spacer>
      </item>
     </layout>
    </item>
    <item row="1" column="0">
     <widget class="QLineEdit" name="nameEdit">
      <property name="text">
       <string>Ada</string>
      </property>
      <property name="cursor">
       <cursor>4</cursor>
      </property>
     </widget>
    </item>
    <item row="1" column="1">
     <widget class="QLabel" name="cursorLabel">
      <property name="text">
       <string>cursor</string>
      </property>
      <property name="cursor">
       <cursorShape>PointingHandCursor</cursorShape>
      </property>
      <property name="pos">
       <point>
        <x>3</x>
        <y>4</y>
       </point>
      </property>
     </widget>
    </item>
    <item row="2" column="0">
     <widget class="QWidget" name="sampleHost">
      <property name="minimumSize">
       <size>
        <width>10</width>
        <height>10</height>
       </size>
      </property>
      <property name="palette">
       <palette>
        <active>
         <color>
          <red>1</red>
          <green>2</green>
          <blue>3</blue>
         </color>
         <colorrole role="Window">
          <brush brushstyle="SolidPattern">
           <color alpha="255">
            <red>240</red>
            <green>240</green>
            <blue>240</blue>
           </color>
          </brush>
         </colorrole>
         <colorrole role="WindowText">
          <brush brushstyle="LinearGradientPattern">
           <gradient startx="0" starty="0" endx="100" endy="20" centralx="50" centraly="10" focalx="40" focaly="10" radius="12" angle="15" type="LinearGradient" spread="PadSpread" coordinatemode="LogicalMode">
            <gradientstop position="0">
             <color alpha="255">
              <red>255</red>
              <green>0</green>
              <blue>0</blue>
             </color>
            </gradientstop>
            <gradientstop position="1">
             <color alpha="128">
              <red>0</red>
              <green>0</green>
              <blue>255</blue>
             </color>
            </gradientstop>
           </gradient>
          </brush>
         </colorrole>
        </active>
        <inactive>
         <colorrole role="Button">
          <brush brushstyle="RadialGradientPattern">
           <gradient startx="0" starty="0" endx="1" endy="1" centralx="0.5" centraly="0.5" focalx="0.4" focaly="0.4" radius="0.8" angle="0" type="RadialGradient" spread="RepeatSpread" coordinatemode="ObjectMode">
            <gradientstop position="0.2">
             <color alpha="255">
              <red>0</red>
              <green>255</green>
              <blue>0</blue>
             </color>
            </gradientstop>
           </gradient>
          </brush>
         </colorrole>
        </inactive>
        <disabled>
         <colorrole role="Base">
          <brush brushstyle="ConicalGradientPattern">
           <gradient startx="0" starty="0" endx="1" endy="1" centralx="0.5" centraly="0.5" focalx="0.5" focaly="0.5" radius="1" angle="45" type="ConicalGradient" spread="ReflectSpread" coordinatemode="StretchToDeviceMode">
            <gradientstop position="0.5">
             <color alpha="200">
              <red>10</red>
              <green>10</green>
              <blue>10</blue>
             </color>
            </gradientstop>
           </gradient>
          </brush>
         </colorrole>
         <colorrole role="AlternateBase">
          <brush brushstyle="TexturePattern">
           <texture name="windowTexture">
            <pixmap resource="icons.qrc" alias="dot">:/cbcs/icons/dot.png</pixmap>
           </texture>
          </brush>
         </colorrole>
        </disabled>
       </palette>
      </property>
      <property name="font">
       <font>
        <family>DejaVu Sans</family>
        <pointsize>12</pointsize>
        <weight>75</weight>
        <italic>true</italic>
        <bold>true</bold>
        <underline>false</underline>
        <strikeout>false</strikeout>
        <antialiasing>true</antialiasing>
        <stylestrategy>PreferDefault</stylestrategy>
        <kerning>true</kerning>
        <hintingpreference>PreferDefaultHinting</hintingpreference>
        <fontweight>Bold</fontweight>
       </font>
      </property>
      <property name="sizePolicy">
       <sizepolicy hsizetype="Expanding" vsizetype="Preferred">
        <hsizetype>7</hsizetype>
        <vsizetype>5</vsizetype>
        <horstretch>1</horstretch>
        <verstretch>0</verstretch>
       </sizepolicy>
      </property>
      <property name="cbcsPointF" stdset="0">
       <pointf>
        <x>1.5</x>
        <y>2.5</y>
       </pointf>
      </property>
      <property name="cbcsRectF" stdset="0">
       <rectf>
        <x>0.5</x>
        <y>1.5</y>
        <width>3.5</width>
        <height>4.5</height>
       </rectf>
      </property>
      <property name="cbcsSizeF" stdset="0">
       <sizef>
        <width>8.25</width>
        <height>9.25</height>
       </sizef>
      </property>
      <property name="cbcsFloat" stdset="0">
       <float>1.25</float>
      </property>
      <property name="cbcsDouble" stdset="0">
       <double>2.5</double>
      </property>
      <property name="cbcsLongLong" stdset="0">
       <longlong>9223372036854775807</longlong>
      </property>
      <property name="cbcsUInt" stdset="0">
       <uint>4294967295</uint>
      </property>
      <property name="cbcsULongLong" stdset="0">
       <ulonglong>18446744073709551615</ulonglong>
      </property>
      <property name="cbcsChar" stdset="0">
       <char>
        <unicode>65</unicode>
       </char>
      </property>
      <property name="cbcsUrl" stdset="0">
       <url>
        <string>https://example.com/forms</string>
       </url>
      </property>
      <property name="cbcsTags" stdset="0">
       <stringlist notr="true" comment="tags" extracomment="list comment" id="tags.id">
        <string>alpha</string>
        <string>beta</string>
       </stringlist>
      </property>
      <property name="cbcsLogicLevel" stdset="0">
       <number>3</number>
      </property>
      <property name="cbcsRule" stdset="0">
       <string>when saved then refresh</string>
      </property>
      <property name="styleSheet" stdset="1">
       <string>QWidget { color: #222; }</string>
      </property>
      <widget class="QWidget" name="nativeHost" native="true">
       <property name="minimumSize">
        <size>
         <width>8</width>
         <height>8</height>
        </size>
       </property>
      </widget>
      <widget class="QPushButton" name="backButton">
       <property name="text"><string>Back</string></property>
      </widget>
      <widget class="QPushButton" name="frontButton">
       <property name="text"><string>Front</string></property>
      </widget>
      <zorder>nativeHost</zorder>
      <zorder>backButton</zorder>
      <zorder>frontButton</zorder>
      <script/>
      <widgetdata/>
     </widget>
    </item>
    <item row="2" column="1">
     <widget class="QDateTimeEdit" name="whenEdit">
      <property name="date">
       <date>
        <year>2026</year>
        <month>10</month>
        <day>21</day>
       </date>
      </property>
      <property name="time">
       <time>
        <hour>15</hour>
        <minute>4</minute>
        <second>5</second>
       </time>
      </property>
      <property name="dateTime">
       <datetime>
        <hour>15</hour>
        <minute>4</minute>
        <second>5</second>
        <year>2026</year>
        <month>10</month>
        <day>21</day>
       </datetime>
      </property>
     </widget>
    </item>
   </layout>
   <widget class="QListWidget" name="listWidget">
    <item>
     <property name="text">
      <string>Alpha</string>
     </property>
    </item>
   </widget>
   <widget class="QTreeWidget" name="treeWidget">
    <column>
     <property name="text">
      <string>Name</string>
     </property>
    </column>
    <item>
     <property name="text">
      <string>Parent</string>
     </property>
     <item>
      <property name="text">
       <string>Child</string>
      </property>
     </item>
    </item>
   </widget>
   <widget class="QTableWidget" name="tableWidget">
    <property name="rowCount"><number>1</number></property>
    <property name="columnCount"><number>1</number></property>
    <row>
     <property name="text"><string>Row</string></property>
    </row>
    <column>
     <property name="text"><string>Column</string></property>
    </column>
    <item row="0" column="0">
     <property name="text"><string>cell</string></property>
    </item>
   </widget>
   <widget class="QTabWidget" name="tabWidget">
    <property name="currentIndex"><number>0</number></property>
    <widget class="QWidget" name="tabOne">
     <attribute name="title"><string>One</string></attribute>
    </widget>
    <widget class="QWidget" name="tabTwo">
     <attribute name="title"><string>Two</string></attribute>
    </widget>
   </widget>
   <widget class="QStackedWidget" name="stack">
    <widget class="QWidget" name="pageA"/>
    <widget class="QWidget" name="pageB"/>
   </widget>
   <widget class="QToolBox" name="toolBox">
    <widget class="QWidget" name="boxPage">
     <attribute name="label"><string>Tools</string></attribute>
    </widget>
   </widget>
   <widget class="QScrollArea" name="scrollArea">
    <widget class="QWidget" name="scrollContents"/>
   </widget>
   <widget class="QMdiArea" name="mdiArea">
    <widget class="QWidget" name="mdiChild"/>
   </widget>
   <widget class="QWizard" name="wizard">
    <widget class="QWizardPage" name="wizardPage">
     <attribute name="title"><string>Intro</string></attribute>
    </widget>
   </widget>
   <widget class="QSplitter" name="splitter">
    <property name="orientation"><enum>Qt::Horizontal</enum></property>
    <widget class="QListWidget" name="splitList"/>
    <widget class="QPlainTextEdit" name="splitText"/>
   </widget>
   <widget class="QGroupBox" name="groupBox">
    <property name="title"><string>Choices</string></property>
    <layout class="QVBoxLayout" name="choiceLayout">
     <item>
      <widget class="QRadioButton" name="radioYes">
       <property name="text"><string>Yes</string></property>
       <attribute name="buttonGroup"><string>choiceGroup</string></attribute>
      </widget>
     </item>
     <item>
      <widget class="QRadioButton" name="radioNo">
       <property name="text"><string>No</string></property>
       <attribute name="buttonGroup"><string>choiceGroup</string></attribute>
      </widget>
     </item>
    </layout>
   </widget>
   <widget class="QDialogButtonBox" name="buttonBox">
    <property name="standardButtons">
     <set>QDialogButtonBox::Cancel|QDialogButtonBox::Ok</set>
    </property>
   </widget>
   <widget class="QKeySequenceEdit" name="shortcutEdit">
    <property name="keySequence">
     <string notr="true">Ctrl+Shift+S</string>
    </property>
   </widget>
  </widget>
  <widget class="QMenuBar" name="menuBar">
   <widget class="QMenu" name="menuFile">
    <property name="title"><string>&amp;File</string></property>
    <addaction name="actionNew"/>
    <addaction name="separator"/>
    <addaction name="actionQuit"/>
   </widget>
   <addaction name="menuFile"/>
  </widget>
  <widget class="QToolBar" name="toolBar">
   <property name="windowTitle"><string>Main</string></property>
   <addaction name="actionNew"/>
  </widget>
  <widget class="QStatusBar" name="statusBar"/>
  <widget class="QDockWidget" name="dockWidget">
   <property name="windowTitle"><string>Dock</string></property>
   <attribute name="dockWidgetArea">
    <number>1</number>
   </attribute>
   <widget class="QWidget" name="dockContents"/>
  </widget>
  <action name="actionNew">
   <property name="text"><string>New</string></property>
   <property name="shortcut"><string>Ctrl+N</string></property>
   <property name="icon">
    <iconset theme="document-new" resource="icons.qrc">
     <normaloff resource="icons.qrc" alias="dot">:/cbcs/icons/dot.png</normaloff>
     <normalon resource="icons.qrc" alias="mark">:/cbcs/icons/mark.png</normalon>
     <disabledoff resource="icons.qrc">:/cbcs/icons/dot.png</disabledoff>
     <disabledon resource="icons.qrc">:/cbcs/icons/mark.png</disabledon>
     <activeoff resource="icons.qrc">:/cbcs/icons/dot.png</activeoff>
     <activeon resource="icons.qrc">:/cbcs/icons/mark.png</activeon>
     <selectedoff resource="icons.qrc">:/cbcs/icons/dot.png</selectedoff>
     <selectedon resource="icons.qrc">:/cbcs/icons/mark.png</selectedon>:/cbcs/icons/dot.png
    </iconset>
   </property>
   <attribute name="cbcsActionRole" stdset="0">
    <string>file</string>
   </attribute>
  </action>
  <action name="actionQuit" menu="menuFile">
   <property name="text"><string>Quit</string></property>
  </action>
  <actiongroup name="outerGroup">
   <property name="exclusive"><bool>false</bool></property>
   <attribute name="cbcsGroupNote" stdset="0">
    <string>outer</string>
   </attribute>
   <actiongroup name="innerGroup">
    <property name="exclusive"><bool>true</bool></property>
    <action name="actionLeft">
     <property name="text"><string>Left</string></property>
     <property name="checkable"><bool>true</bool></property>
    </action>
   </actiongroup>
  </actiongroup>
  <addaction name="actionNew"/>
 </widget>
 <layoutdefault spacing="6" margin="11"/>
 <layoutfunction spacing="cbcsSpacing" margin="cbcsMargin"/>
 <pixmapfunction>cbcsPixmap</pixmapfunction>
 <customwidgets>
  <customwidget>
   <class>InvoiceHeader</class>
   <extends>QWidget</extends>
   <header location="global">shop.widgets.invoice_header</header>
   <sizehint>
    <width>120</width>
    <height>48</height>
   </sizehint>
   <addpagemethod>addPage</addpagemethod>
   <container>1</container>
   <sizepolicy/>
   <pixmap>:/cbcs/icons/dot.png</pixmap>
   <script/>
   <properties/>
   <slots>
    <signal>changed()</signal>
    <slot>reset()</slot>
   </slots>
   <propertyspecifications>
    <tooltip name="title">Title shown on the page</tooltip>
    <stringpropertyspecification name="title" type="singleline" notr="true"/>
   </propertyspecifications>
  </customwidget>
 </customwidgets>
 <tabstops>
  <tabstop>nameEdit</tabstop>
  <tabstop>whenEdit</tabstop>
  <tabstop>shortcutEdit</tabstop>
 </tabstops>
 <images/>
 <includes>
  <include location="local" impldecl="in implementation">shop.widgets.invoice_header</include>
  <include location="global" impldecl="in declaration">PySide6.QtCore</include>
 </includes>
 <resources name="cbcsResources">
  <include location="icons.qrc"/>
  <include location="extra.qrc"/>
 </resources>
 <connections>
  <connection>
   <sender>buttonBox</sender>
   <signal>accepted()</signal>
   <receiver>KitchenSink</receiver>
   <slot>close()</slot>
   <hints>
    <hint type="sourcelabel">
     <x>10</x>
     <y>20</y>
    </hint>
    <hint type="destinationlabel">
     <x>30</x>
     <y>40</y>
    </hint>
   </hints>
  </connection>
  <connection>
   <sender>KitchenSink</sender>
   <signal>customSignal(int)</signal>
   <receiver>nameEdit</receiver>
   <slot>setFocus()</slot>
  </connection>
 </connections>
 <designerdata>
  <property name="gridDeltaX"><number>10</number></property>
  <property name="gridDeltaY"><number>10</number></property>
  <property name="gridSnapX"><bool>true</bool></property>
  <property name="gridSnapY"><bool>true</bool></property>
  <property name="gridVisible"><bool>true</bool></property>
 </designerdata>
 <slots>
  <signal>customSignal(int)</signal>
  <slot>on_nameEdit_textChanged(QString)</slot>
 </slots>
 <buttongroups>
  <buttongroup name="choiceGroup">
   <property name="exclusive"><bool>true</bool></property>
   <attribute name="cbcsGroupId" stdset="0">
    <string>choices</string>
   </attribute>
  </buttongroup>
 </buttongroups>
</ui>
"""


def _property_bodies() -> Dict[str, tuple]:
    return {
        "bool": ("flag", "<bool>true</bool>"),
        "color": ("swatch", "<color alpha=\"255\"><red>9</red><green>8</green><blue>7</blue></color>"),
        "cstring": ("buddyName", "<cstring>nameEdit</cstring>"),
        "cursor": ("pointer", "<cursor>4</cursor>"),
        "cursorshape": ("pointer", "<cursorShape>IBeamCursor</cursorShape>"),
        "enum": ("direction", "<enum>Qt::LeftToRight</enum>"),
        "font": ("face", "<font><family>DejaVu Sans</family><pointsize>11</pointsize><bold>true</bold></font>"),
        "iconset": ("icon", "<iconset theme=\"document-open\" resource=\"icons.qrc\"><normaloff>:/cbcs/icons/dot.png</normaloff>:/cbcs/icons/dot.png</iconset>"),
        "pixmap": ("image", "<pixmap resource=\"icons.qrc\" alias=\"dot\">:/cbcs/icons/dot.png</pixmap>"),
        "palette": ("colors", "<palette><active><colorrole role=\"Window\"><brush brushstyle=\"SolidPattern\"><color alpha=\"255\"><red>255</red><green>255</green><blue>255</blue></color></brush></colorrole></active><inactive><colorrole role=\"Window\"><brush brushstyle=\"SolidPattern\"><color><red>240</red><green>240</green><blue>240</blue></color></brush></colorrole></inactive><disabled><colorrole role=\"Window\"><brush brushstyle=\"SolidPattern\"><color><red>200</red><green>200</green><blue>200</blue></color></brush></colorrole></disabled></palette>"),
        "point": ("origin", "<point><x>2</x><y>3</y></point>"),
        "rect": ("bounds", "<rect><x>0</x><y>0</y><width>12</width><height>14</height></rect>"),
        "set": ("flags", "<set>Qt::AlignLeft|Qt::AlignVCenter</set>"),
        "locale": ("locale", "<locale language=\"English\" country=\"UnitedStates\"/>"),
        "sizepolicy": ("policy", "<sizepolicy hsizetype=\"Preferred\" vsizetype=\"Minimum\"><horstretch>0</horstretch><verstretch>0</verstretch></sizepolicy>"),
        "size": ("extent", "<size><width>16</width><height>16</height></size>"),
        "string": ("caption", "<string notr=\"true\" comment=\"cap\" extracomment=\"hint\" id=\"cap.id\">Hello</string>"),
        "stringlist": ("tags", "<stringlist><string>one</string><string>two</string></stringlist>"),
        "number": ("count", "<number>7</number>"),
        "float": ("ratio", "<float>0.5</float>"),
        "double": ("amount", "<double>3.14</double>"),
        "date": ("when", "<date><year>2026</year><month>10</month><day>21</day></date>"),
        "time": ("clock", "<time><hour>8</hour><minute>30</minute><second>0</second></time>"),
        "datetime": ("stamp", "<datetime><hour>8</hour><minute>30</minute><second>1</second><year>2026</year><month>1</month><day>2</day></datetime>"),
        "pointf": ("originF", "<pointf><x>1.25</x><y>2.5</y></pointf>"),
        "rectf": ("boundsF", "<rectf><x>0.5</x><y>0.5</y><width>2.5</width><height>3.5</height></rectf>"),
        "sizef": ("extentF", "<sizef><width>1.5</width><height>2.5</height></sizef>"),
        "longlong": ("big", "<longlong>-1</longlong>"),
        "char": ("letter", "<char><unicode>66</unicode></char>"),
        "url": ("link", "<url><string>https://example.com/a</string></url>"),
        "uint": ("bits", "<uint>12</uint>"),
        "ulonglong": ("wide", "<ulonglong>99</ulonglong>"),
        "brush": ("fill", "<brush brushstyle=\"SolidPattern\"><color alpha=\"255\"><red>1</red><green>2</green><blue>3</blue></color></brush>"),
    }


def _extra_forms() -> List[tuple]:
    slider = _document(
        "SliderLab",
        "QWidget",
        "Sliders",
        """  <layout class="QHBoxLayout" name="row">
   <item><widget class="QSlider" name="hSlider"><property name="orientation"><enum>Qt::Horizontal</enum></property></widget></item>
   <item><widget class="QDial" name="dial"/></item>
   <item><widget class="QProgressBar" name="progress"/></item>
   <item><widget class="QLCDNumber" name="lcd"/></item>
  </layout>""",
    )
    texts = _document(
        "TextLab",
        "QWidget",
        "Text",
        """  <layout class="QVBoxLayout" name="col">
   <item><widget class="QLineEdit" name="line"/></item>
   <item><widget class="QTextEdit" name="rich"/></item>
   <item><widget class="QPlainTextEdit" name="plain"/></item>
   <item><widget class="QTextBrowser" name="browser"/></item>
  </layout>""",
    )
    choices = _document(
        "ChoiceLab",
        "QWidget",
        "Choices",
        """  <layout class="QVBoxLayout" name="col">
   <item><widget class="QRadioButton" name="radioA"><property name="text"><string>A</string></property><attribute name="buttonGroup"><string>ab</string></attribute></widget></item>
   <item><widget class="QRadioButton" name="radioB"><property name="text"><string>B</string></property><attribute name="buttonGroup"><string>ab</string></attribute></widget></item>
   <item><widget class="QCheckBox" name="flag"><property name="text"><string>Flag</string></property></widget></item>
   <item><widget class="QComboBox" name="combo"><item><property name="text"><string>One</string></property></item></widget></item>
  </layout>""",
        """ <buttongroups>
  <buttongroup name="ab"/>
 </buttongroups>""",
    )
    buttons = _document(
        "ButtonRow",
        "QWidget",
        "Buttons",
        """  <layout class="QHBoxLayout" name="row">
   <item><widget class="QPushButton" name="push"><property name="text"><string>Push</string></property></widget></item>
   <item><widget class="QToolButton" name="tool"><property name="text"><string>Tool</string></property></widget></item>
   <item><widget class="QCommandLinkButton" name="command"><property name="text"><string>Command</string></property></widget></item>
   <item><widget class="QDialogButtonBox" name="box"/></item>
  </layout>""",
    )
    calendar = _document(
        "CalendarPanel",
        "QWidget",
        "Calendar",
        """  <layout class="QHBoxLayout" name="row">
   <item><widget class="QCalendarWidget" name="calendar"/></item>
   <item><widget class="QDateEdit" name="dateEdit"/></item>
   <item><widget class="QTimeEdit" name="timeEdit"/></item>
  </layout>""",
    )
    trees = _document(
        "TreeAndTable",
        "QWidget",
        "Trees",
        """  <layout class="QHBoxLayout" name="row">
   <item><widget class="QTreeWidget" name="tree"><column><property name="text"><string>Node</string></property></column></widget></item>
   <item><widget class="QTableWidget" name="table"/></item>
  </layout>""",
    )
    scroll = _document(
        "ScrollSettings",
        "QScrollArea",
        "Scroll",
        """  <widget class="QWidget" name="scrollBody">
   <layout class="QFormLayout" name="form">
    <item row="0" column="0"><widget class="QLabel" name="a"><property name="text"><string>A</string></property></widget></item>
    <item row="0" column="1"><widget class="QLineEdit" name="aEdit"/></item>
    <item row="1" column="0"><widget class="QLabel" name="b"><property name="text"><string>B</string></property></widget></item>
    <item row="1" column="1"><widget class="QSpinBox" name="bEdit"/></item>
   </layout>
  </widget>""",
    )
    split = _document(
        "SplitEditor",
        "QSplitter",
        "Split",
        """  <property name="orientation"><enum>Qt::Horizontal</enum></property>
  <widget class="QListView" name="nav"/>
  <widget class="QPlainTextEdit" name="editor"/>""",
    )
    absolute = """<?xml version="1.0" encoding="UTF-8"?>
<!-- SPDX-License-Identifier: MIT -->
<ui version="4.0">
 <class>AbsoluteOrder</class>
 <widget class="QWidget" name="AbsoluteOrder">
  <property name="geometry"><rect><x>0</x><y>0</y><width>200</width><height>120</height></rect></property>
  <widget class="QLabel" name="back">
   <property name="geometry"><rect><x>10</x><y>10</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>back</string></property>
  </widget>
  <widget class="QLabel" name="front">
   <property name="geometry"><rect><x>24</x><y>20</y><width>80</width><height>24</height></rect></property>
   <property name="text"><string>front</string></property>
  </widget>
  <zorder>back</zorder>
  <zorder>front</zorder>
 </widget>
</ui>
"""
    unicode_doc = """<?xml version="1.0" encoding="UTF-8"?>
<!-- SPDX-License-Identifier: MIT -->
<ui version="4.0">
 <class>UnicodeForm</class>
 <widget class="QDialog" name="UnicodeForm">
  <property name="geometry"><rect><x>0</x><y>0</y><width>320</width><height>160</height></rect></property>
  <property name="windowTitle"><string>café 東京</string></property>
  <widget class="QLabel" name="名前">
   <property name="geometry"><rect><x>8</x><y>8</y><width>280</width><height>24</height></rect></property>
   <property name="text"><string>café — 日本語 «quotes» &amp; more</string></property>
  </widget>
  <widget class="QPushButton" name="виджет">
   <property name="geometry"><rect><x>8</x><y>40</y><width>120</width><height>28</height></rect></property>
   <property name="text"><string>Да</string></property>
  </widget>
 </widget>
</ui>
"""
    odd = """<?xml version="1.0" encoding="UTF-8"?>
<!-- SPDX-License-Identifier: MIT -->
<ui stdSetDef="0" stdsetdef="1" connectslotsbyname="false" idbasedtr="false" displayname="Odd order" language="c++" version="4.0">
 <class>OddOrder</class>
 <widget native="false" name="OddOrder" class="QLabel">
  <property stdset="1" name="text">
   <string id="odd.text" extracomment="order" comment="ctx" notr="true">Fish &amp; chips &lt;today&gt;</string>
  </property>
 </widget>
</ui>
"""
    crlf = _document("CrlfForm", "QDialog", "CRLF", """  <widget class="QLabel" name="label"><property name="text"><string>crlf</string></property></widget>""")
    empty = _document("EmptyForm", "QWidget", "Empty", "")
    return [
        ("synthetic/labs/slider_lab.ui", slider, ""),
        ("synthetic/labs/text_lab.ui", texts, ""),
        ("synthetic/labs/choice_lab.ui", choices, ""),
        ("synthetic/labs/button_row.ui", buttons, ""),
        ("synthetic/labs/calendar_panel.ui", calendar, ""),
        ("synthetic/labs/tree_and_table.ui", trees, ""),
        ("synthetic/labs/scroll_settings.ui", scroll, ""),
        ("synthetic/labs/split_editor.ui", split, ""),
        ("synthetic/edges/absolute_zorder.ui", absolute, ""),
        ("synthetic/edges/unicode_names.ui", unicode_doc, ""),
        ("synthetic/edges/unusual_attribute_order.ui", odd, ""),
        ("synthetic/edges/crlf_endings.ui", crlf, "crlf"),
        ("synthetic/edges/empty_form.ui", empty, ""),
        ("synthetic/edges/nested_15.ui", _nested_xml(), ""),
        ("synthetic/edges/thousand_widgets.ui", _thousand_xml(), ""),
    ]


def _qformbuilder_palette_cursor() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="windowFilePath">
   <string/>
  </property>
  <property name="enabled">
   <bool>true</bool>
  </property>
  <property name="size" stdset="0">
   <size>
    <width>640</width>
    <height>480</height>
   </size>
  </property>
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>640</width>
    <height>480</height>
   </rect>
  </property>
  <property name="tabletTracking">
   <bool>false</bool>
  </property>
  <property name="pos" stdset="0">
   <point>
    <x>0</x>
    <y>0</y>
   </point>
  </property>
  <property name="objectName">
   <string notr="true">Form</string>
  </property>
  <property name="toolTipDuration">
   <number>-1</number>
  </property>
  <property name="font">
   <font/>
  </property>
  <property name="toolTip">
   <string/>
  </property>
  <property name="cursor">
   <cursorShape>IBeamCursor</cursorShape>
  </property>
  <property name="accessibleDescription">
   <string/>
  </property>
  <property name="maximumHeight">
   <number>16777215</number>
  </property>
  <property name="maximumWidth">
   <number>16777215</number>
  </property>
  <property name="windowModified">
   <bool>false</bool>
  </property>
  <property name="acceptDrops">
   <bool>false</bool>
  </property>
  <property name="windowIconText">
   <string/>
  </property>
  <property name="visible">
   <bool>false</bool>
  </property>
  <property name="locale">
   <locale language="English" country="UnitedStates"/>
  </property>
  <property name="sizePolicy">
   <sizepolicy hsizetype="Preferred" vsizetype="Preferred">
    <horstretch>0</horstretch>
    <verstretch>0</verstretch>
   </sizepolicy>
  </property>
  <property name="baseSize">
   <size>
    <width>0</width>
    <height>0</height>
   </size>
  </property>
  <property name="accessibleName">
   <string/>
  </property>
  <property name="maximumSize">
   <size>
    <width>16777215</width>
    <height>16777215</height>
   </size>
  </property>
  <property name="autoFillBackground">
   <bool>false</bool>
  </property>
  <property name="styleSheet">
   <string notr="true"/>
  </property>
  <property name="palette">
   <palette>
    <active>
     <colorrole role="Window">
      <brush brushstyle="LinearGradientPattern">
       <gradient startx="0.000000000000000" starty="0.000000000000000" endx="1.000000000000000" endy="1.000000000000000" type="LinearGradient" spread="PadSpread" coordinatemode="LogicalMode">
        <gradientstop position="0.000000000000000">
         <color alpha="255">
          <red>255</red>
          <green>0</green>
          <blue>0</blue>
         </color>
        </gradientstop>
        <gradientstop position="1.000000000000000">
         <color alpha="128">
          <red>0</red>
          <green>0</green>
          <blue>255</blue>
         </color>
        </gradientstop>
       </gradient>
      </brush>
     </colorrole>
    </active>
    <inactive/>
    <disabled/>
   </palette>
  </property>
  <property name="whatsThis">
   <string/>
  </property>
  <property name="minimumHeight">
   <number>0</number>
  </property>
  <property name="mouseTracking">
   <bool>false</bool>
  </property>
  <property name="windowTitle">
   <string/>
  </property>
  <property name="sizeIncrement">
   <size>
    <width>0</width>
    <height>0</height>
   </size>
  </property>
  <property name="minimumSize">
   <size>
    <width>0</width>
    <height>0</height>
   </size>
  </property>
  <property name="updatesEnabled">
   <bool>true</bool>
  </property>
  <property name="windowOpacity">
   <double>1.000000000000000</double>
  </property>
  <property name="statusTip">
   <string/>
  </property>
  <property name="minimumWidth">
   <number>0</number>
  </property>
 </widget>
 <connections/>
</ui>
"""


def _designer_two_state_icon() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>IconForm</class>
 <widget class="QWidget" name="IconForm">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>640</width>
    <height>480</height>
   </rect>
  </property>
  <property name="windowTitle">
   <string>Icons</string>
  </property>
  <property name="windowIcon">
   <iconset>
    <normaloff>tests/form_builder/corpus/synthetic/qt/normaloff.png</normaloff>
    <normalon>tests/form_builder/corpus/synthetic/qt/normalon.png</normalon>tests/form_builder/corpus/synthetic/qt/normaloff.png
   </iconset>
  </property>
 </widget>
</ui>
"""


def _write(path: Path, text: str, newline: str) -> None:
    if not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def generate() -> None:
    _wipe(SYNTHETIC)
    _wipe(MALFORMED)
    icons = SYNTHETIC / "schema" / "icons"
    icons.mkdir(parents=True)
    (icons / "dot.png").write_bytes(_png(1, 1, b"\x20\x60\xc0"))
    (icons / "mark.png").write_bytes(_png(1, 1, b"\xc0\x40\x20"))
    (SYNTHETIC / "schema" / "icons.qrc").write_text(
        """<RCC>
 <qresource prefix="/cbcs">
  <file>icons/dot.png</file>
  <file alias="mark">icons/mark.png</file>
 </qresource>
</RCC>
""",
        encoding="utf-8",
    )
    (SYNTHETIC / "schema" / "extra.qrc").write_text(
        """<RCC>
 <qresource prefix="/extra">
  <file>icons/mark.png</file>
 </qresource>
</RCC>
""",
        encoding="utf-8",
    )
    # Property fixtures that reference icons.qrc live next to the schema qrc files.
    entries: List[dict] = []

    def add(
        rel: str,
        text: str,
        notes: str = "",
        expect: str = "",
        newline: str = "\n",
        source: str = "hand-authored by tests/form_builder/corpus/generate_synthetic.py",
    ) -> None:
        if expect == "":
            ET.fromstring(text.encode("utf-8"))
        path = CORPUS / rel
        _write(path, text, newline)
        item = {
            "path": rel,
            "source": source,
            "licence": "MIT",
            "notes": notes,
        }
        if expect:
            item["expect"] = expect
        entries.append(item)

    add("synthetic/schema/kitchen_sink.ui", _kitchen_sink(), "Covers the ui4 element and attribute names, containers, resources, and cbcs* dynamic properties.")
    qt_dir = SYNTHETIC / "qt"
    qt_dir.mkdir(parents=True)
    (qt_dir / "normaloff.png").write_bytes(_png(1, 1, b"\xff\x00\x00"))
    (qt_dir / "normalon.png").write_bytes(_png(1, 1, b"\x00\x00\xff"))
    add(
        "synthetic/qt/palette_gradient_cursor.ui",
        _qformbuilder_palette_cursor(),
        "Active Window is a two-stop linear gradient. cursorShape is IBeamCursor.",
        source="PySide6 6.8.3 QFormBuilder.save, captured 2026-10-22",
    )
    add(
        "synthetic/qt/iconset_two_state.ui",
        _designer_two_state_icon(),
        "Compat path is written once after the last state and equals normaloff. normaloff.png and normalon.png differ. QFormBuilder.save on PySide6 6.8.3 does not emit iconset.",
        source="Designer iconset form, captured 2026-10-22",
    )
    for type_name, (prop_name, body) in _property_bodies().items():
        # iconset/pixmap files must sit beside icons.qrc. The other property
        # files do not reference it.
        if type_name in {"iconset", "pixmap"}:
            rel = "synthetic/schema/property_%s.ui" % type_name
        else:
            rel = "synthetic/properties/%s.ui" % type_name
        add(rel, _property_xml(type_name, body, prop_name), "Property value element <%s>." % type_name)
    for widget_class in WIDGET_CLASSES:
        add(
            "synthetic/widgets/%s.ui" % widget_class,
            _widget_xml(widget_class),
            "Root widget class %s." % widget_class,
        )
    for class_slug, title, rows in FORM_SPECS:
        class_name = "".join(part[:1].upper() + part[1:] for part in class_slug.split("_"))
        add(
            "synthetic/forms/%s.ui" % class_slug,
            _form_xml(class_name, title, rows),
            "Form layout with buddies and tab stops.",
        )
    for rel, text, kind in _extra_forms():
        newline = "\r\n" if kind == "crlf" else "\n"
        note = "CRLF line endings." if kind == "crlf" else ""
        add(rel, text, note, newline=newline)

    malformed = [
        (
            "malformed/not_xml.ui",
            "this is not xml\n",
            "Not XML. uic reports Start tag expected. QUiLoader raises Unable to open/read ui device.",
            "Start tag expected",
        ),
        (
            "malformed/truncated.ui",
            '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><class>D</class><widget class="QDialog" name="D">\n',
            "Truncated document. uic reports Premature end of document.",
            "Premature end of document",
        ),
        (
            "malformed/wrong_root.ui",
            '<?xml version="1.0" encoding="UTF-8"?>\n<form version="4.0"><widget class="QDialog" name="D"/></form>\n',
            "Root element is form, not ui. uic reports Unexpected element form.",
            "Unexpected element form",
        ),
        (
            "malformed/empty_ui.ui",
            '<ui version="4.0"></ui>\n',
            "ui element with no widget. uic reports the file is not valid. QUiLoader raises Unable to open/read ui device.",
            "not valid",
        ),
        (
            "malformed/missing_widget_class.ui",
            '<?xml version="1.0" encoding="UTF-8"?>\n<ui version="4.0"><class>D</class><widget name="D"><property name="windowTitle"><string>D</string></property></widget></ui>\n',
            "Widget has no class attribute. QUiLoader raises Unable to open/read ui device. uic still emits Python.",
            "Unable to open/read ui device",
        ),
        (
            "malformed/language_python.ui",
            _document("PythonLang", "QDialog", "Python", "", ui_attrs='version="4.0" language="python"'),
            "language=python is rejected by QUiLoader 6.8.3. The attribute is still legal in the schema. Use language=c++ on forms that must load.",
            "created using python",
        ),
    ]
    refused = (
        "QColorDialog",
        "QErrorMessage",
        "QFileDialog",
        "QFocusFrame",
        "QFontDialog",
        "QInputDialog",
        "QMdiSubWindow",
        "QMessageBox",
        "QProgressDialog",
        "QRhiWidget",
        "QSplashScreen",
        "QTabBar",
    )
    for widget_class in refused:
        malformed.append(
            (
                "malformed/refused_%s.ui" % widget_class,
                _widget_xml(widget_class),
                "QUiLoader 6.8.3 cannot construct %s. uic may still emit Python." % widget_class,
                "unable to create a widget of the class '%s'" % widget_class,
            )
        )
    for rel, text, notes, expect in malformed:
        add(rel, text, notes, expect)

    synthetic_entries = [item for item in entries if item["path"].startswith("synthetic/")]
    malformed_entries = [item for item in entries if item["path"].startswith("malformed/")]
    (SYNTHETIC / "provenance.json").write_text(
        json.dumps({"files": synthetic_entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    (MALFORMED / "provenance.json").write_text(
        json.dumps({"files": malformed_entries}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("synthetic %d malformed %d" % (len(synthetic_entries), len(malformed_entries)))


def main() -> None:
    generate()


if __name__ == "__main__":
    main()
