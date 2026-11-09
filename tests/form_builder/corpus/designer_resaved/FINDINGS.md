# Designer 6.8.3 resave pins

Qt Designer 6.8.3 from the FreeCAD 1.1.4 AppImage re-saved 209 forms (63 `qt_examples`, 146 `synthetic`). Each save is Designer's own Save action (`__qt_save_form_action`, `QDesignerActions::saveForm`, `QSaveFile`). 22 Qt examples were already in that shape, so their bytes did not change. The other 187 files changed. Licence for each file is the source file's licence, recorded in `MANIFEST.json`.

## Pin table

| Question | What Designer 6.8.3 writes | Example |
| --- | --- | --- |
| Empty element form | Self-closing when the element is present and empty. This corpus has no `<x></x>`. Empty `<author>`, `<comment>`, and `<exportmacro>` are omitted. Empty `<string/>` and `<string notr="true"/>` are kept. | `calculatorform.ui` drops `<author></author>`. `bookwindow.ui` has `<string/>`. `downloadwidget.ui` has `<string notr="true"/>`. |
| `<float>` precision | Not observable. Designer drops `<float>` properties on save. Zero `<float>` elements remain. | `synthetic/properties/float.ui` |
| `<double>` precision | Fixed 15 fraction digits, including doubles inside `pointf`, `rectf`, and gradient stops. | `3.14` becomes `3.140000000000000` in `synthetic/properties/double.ui` |
| How `-0` is written | `<double>-0</double>` becomes `0.000000000000000`. A negative value that is not zero keeps the sign (`-1.000000000000000`). `<float>-0</float>` is dropped with the rest of `<float>`. | `synthetic/properties/negative_zero.ui` |
| `DEFAULT_ENUM_STYLE` | Qualified. `Qt::Horizontal` becomes `Qt::Orientation::Horizontal`. `QFrame::Box` becomes `QFrame::Shape::Box`. The attribute enum `TopToolBarArea` stays a single token. Unknown dynamic enums and sets are dropped. | `calculatorform.ui`, `synthetic/schema/kitchen_sink.ui`, `synthetic/properties/enum.ui` |
| Empty `<resources/>` and `<connections/>` | Always written, self-closed, even when the source omitted them. Non-empty ones stay. The `name` attribute on `<resources>` is dropped. | `synthetic/edges/empty_form.ui`, `synthetic/schema/kitchen_sink.ui` |
| `stdset="0"` `cbcs*` placement and `notr` | After the widget's standard properties. `stdset="0"` is kept. Attribute order on the property is `name` then `stdset`. `notr="true"` is kept. Designer does not add `notr` when the source had none. | `synthetic/cbcs/enabled_bind.ui`, `synthetic/cbcs/logic_json.ui`, `synthetic/cbcs/splitter_sizes.ui` |
| Attribute order on `<property>` and `<string>` | `<property name stdset>`. `<string>` uses `notr`, `comment`, `extracomment`, `id`, omitting any that are absent. The same order is used on `<stringlist>`. | `kitchen_sink.ui` window title and `cbcsTags` |
| Line endings | `\n` for the 208 files that were LF. The one CRLF source is rewritten with CRLF on every line, including the declaration. | `synthetic/edges/crlf_endings.ui` |
| Indentation | One space per level. No trailing whitespace. The file ends with a newline after `</ui>`. | every resaved file |
| XML declaration | First line is `<?xml version="1.0" encoding="UTF-8"?>`. Designer adds it when the source omitted it. `<ui version="4.0">` has no space before `>`. | `calculatorform.ui` |
| Other normalisation | See the list under the diffs. | several files below |

## Also normalised

Designer rewrites these on the way through Save.

- Value tags use Designer's spelling. `<longlong>` becomes `<longLong>`. `<uint>` becomes `<UInt>`. `<ulonglong>` becomes `<uLongLong>`. `<gradientStop>` becomes `<gradientstop>`. `<cursor>4</cursor>` becomes `<cursorShape>IBeamCursor</cursorShape>`.
- `<sizepolicy>` stores the policies as attributes (`hsizetype="Preferred"`), not as numeric children.
- `stdset="1"` is omitted. `stdset="0"` is written. Layout `margin` is stored as `stdset="0"`.
- `objectName` is omitted when it only repeats the widget or layout name, including an empty `<string notr="true"/>`.
- Quotes inside text become `&quot;`. `cbcsLogic` keeps `notr` and its line breaks.
- Icon sets drop `resource` and `alias`. The normal path is written once as text after the last state, on the same line as `</iconset>`.
- Comments, including SPDX comments, are dropped.
- Custom-widget metadata that Designer does not edit (`<script>`, `<widgetdata>`, `<propertyspecifications>`, `<images>`, `<addpagemethod>`) is dropped from `kitchen_sink.ui`.
- A label with no geometry gains a small default geometry on the CRLF form.

## Diff examples

`synthetic/edges/empty_form.ui` gains the two empty wrappers and loses the comment and the blank lines.

```diff
-<!-- SPDX-License-Identifier: MIT -->
  </widget>
-
+ <resources/>
+ <connections/>
 </ui>
```

`synthetic/properties/double.ui` pads a double to 15 fraction digits.

```diff
-   <double>3.14</double>
+   <double>3.140000000000000</double>
```

`synthetic/properties/negative_zero.ui` turns `-0` into a positive zero of 15 digits and drops both floats.

```diff
-   <double>-0</double>
-  </property>
-  <property name="negFloat" stdset="0">
-   <float>-0</float>
+   <double>0.000000000000000</double>
```

`synthetic/properties/float.ui` drops the only float property.

```diff
-  <property name="ratio" stdset="0">
-   <float>0.5</float>
-  </property>
```

`qt_examples/qttools/examples/designer/calculatorform_mi/calculatorform.ui` adds the declaration, omits empty author fields, and rewrites size policy.

```diff
- <author></author>
- <comment></comment>
- <exportmacro></exportmacro>
+<?xml version="1.0" encoding="UTF-8"?>
   <property name="sizePolicy">
-   <sizepolicy>
-    <hsizetype>5</hsizetype>
-    <vsizetype>5</vsizetype>
+   <sizepolicy hsizetype="Preferred" vsizetype="Preferred">
```

The same file qualifies frame and orientation enums (`QFrame::Shape::Box`, `Qt::Orientation::Vertical`).

`synthetic/properties/enum.ui` drops a dynamic enum Designer does not own. `synthetic/properties/set.ui` drops `Qt::AlignLeft|Qt::AlignVCenter` the same way.

`synthetic/properties/longlong.ui` and `synthetic/properties/uint.ui` rename the value tags.

```diff
-   <longlong>-1</longlong>
+   <longLong>-1</longLong>
```

```diff
-   <uint>12</uint>
+   <UInt>12</UInt>
```

`synthetic/properties/cursor.ui` replaces the numeric cursor.

```diff
-   <cursor>4</cursor>
+   <cursorShape>IBeamCursor</cursorShape>
```

`synthetic/cbcs/logic_json.ui` moves `cbcsLogic` to after `windowTitle`, keeps `notr="true"`, and escapes quotes.

```diff
   <property name="cbcsLogic" stdset="0">
    <string notr="true">{
- "version": 1
+ &quot;version&quot;: 1
 }</string>
```

`synthetic/cbcs/enabled_bind.ui` moves `cbcsEnabledWhen` and `cbcsBind` to after `geometry` and `text`. Both keep `stdset="0"`. `cbcsBind` keeps `notr` then `comment`.

`synthetic/cbcs/splitter_sizes.ui` keeps `cbcsSplitterSizes` as `<string notr="true">200,400</string>` after `orientation`, which is rewritten to `Qt::Orientation::Horizontal`.

`synthetic/schema/kitchen_sink.ui` shows the string attribute order and the bare toolbar enum.

```xml
<string comment="window title" extracomment="shown in the title bar" id="window.title">Kitchen sink</string>
<stringlist notr="true" comment="tags" extracomment="list comment" id="tags.id">
<enum>TopToolBarArea</enum>
```

`synthetic/edges/crlf_endings.ui` is the only CRLF file. Every line, including the declaration, ends in `\r\n`. The other 208 files are `\n` only.
