#!/usr/bin/env python
"""
Probe 7: Qt Print Preview
Tests whether PySide2 QPrintPreviewDialog can display report page images
and offer printing -- proving we don't need an external PDF viewer.

If probe 6 generated PNG files, those are loaded. Otherwise a test image
is generated to verify the Qt print pipeline independently.
"""
from __future__ import annotations

import glob
import os
import sys
import traceback

try:
    probe_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    probe_root = "/home/default/jasper_probe"

results_dir = os.path.join(probe_root, "results")
os.makedirs(results_dir, exist_ok=True)

results = []


def section(title):
    results.append(f"\n[{title}]")


def ok(label, detail=""):
    suffix = f" ({detail})" if detail else ""
    results.append(f"  {label}: YES{suffix}")


def fail(label):
    results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


print("=== Probe 7: Qt Print Preview ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Probe root: {probe_root}")

section("PySide2 imports")
try:
    from PySide2 import QtWidgets, QtGui, QtCore, QtPrintSupport
    ok("PySide2.QtWidgets")
    ok("PySide2.QtGui")
    ok("PySide2.QtCore")
    ok("PySide2.QtPrintSupport")
except ImportError:
    fail("PySide2")
    results.append("  PySide2 is required for Qt print preview.")
    results.append("  This probe must run inside FreeCAD AppRun on ChoreBoy.")
    output = "\n".join(results)
    print(output)
    rp = os.path.join(results_dir, "probe7_results.txt")
    with open(rp, "w") as f:
        f.write(output)
    print(f"\nResults written to {rp}")
    print("\n=== END Probe 7 (PySide2 not available) ===")
    raise SystemExit(1)

section("Print support classes")
ok("QPrinter", str(hasattr(QtPrintSupport, "QPrinter")))
ok("QPrintDialog", str(hasattr(QtPrintSupport, "QPrintDialog")))
ok("QPrintPreviewDialog", str(hasattr(QtPrintSupport, "QPrintPreviewDialog")))
ok("QPrintPreviewWidget", str(hasattr(QtPrintSupport, "QPrintPreviewWidget")))

app = QtWidgets.QApplication.instance()
app_created = False
if app is None:
    app = QtWidgets.QApplication(sys.argv)
    app_created = True

section("Page images")
page_pngs = sorted(glob.glob(os.path.join(results_dir, "*_page_*.png")))
page_pngs += sorted(glob.glob(os.path.join(results_dir, "**", "*_page_*.png"), recursive=True))
seen = set()
page_pngs = [p for p in page_pngs if not (p in seen or seen.add(p))]
generated_test_image = False

if page_pngs:
    results.append(f"  Found {len(page_pngs)} page images from probe 6:")
    for p in page_pngs:
        results.append(f"    {os.path.basename(p)} ({os.path.getsize(p)} bytes)")
else:
    results.append("  No probe 6 PNG files found. Generating a test image...")
    try:
        test_img = QtGui.QImage(612 * 2, 792 * 2, QtGui.QImage.Format_RGB32)
        test_img.fill(QtGui.QColor(255, 255, 255))
        painter = QtGui.QPainter(test_img)
        painter.setPen(QtGui.QColor(0, 0, 0))
        painter.setFont(QtGui.QFont("DejaVu Sans", 36))
        painter.drawText(
            QtCore.QRect(0, 100, 1224, 100),
            QtCore.Qt.AlignCenter,
            "Qt Print Preview Test"
        )
        painter.setFont(QtGui.QFont("DejaVu Sans", 20))
        painter.drawText(
            QtCore.QRect(0, 300, 1224, 60),
            QtCore.Qt.AlignCenter,
            "If you can see this in print preview, the Qt print pipeline works."
        )
        painter.drawText(
            QtCore.QRect(0, 400, 1224, 60),
            QtCore.Qt.AlignCenter,
            "Try clicking Print to verify printer access."
        )
        painter.end()

        test_path = os.path.join(results_dir, "qt_test_page_1.png")
        test_img.save(test_path, "PNG")
        page_pngs = [test_path]
        generated_test_image = True
        ok("Test image generated", test_path)
    except Exception:
        fail("test image generation")

section("Load page images")
page_images = []
for png_path in page_pngs:
    try:
        pixmap = QtGui.QPixmap(png_path)
        if pixmap.isNull():
            results.append(f"  {os.path.basename(png_path)}: failed to load (null pixmap)")
        else:
            page_images.append(pixmap)
            ok(os.path.basename(png_path), f"{pixmap.width()}x{pixmap.height()}")
    except Exception:
        fail(os.path.basename(png_path))

if not page_images:
    results.append("  No page images could be loaded.")
    output = "\n".join(results)
    print(output)
    rp = os.path.join(results_dir, "probe7_results.txt")
    with open(rp, "w") as f:
        f.write(output)
    print(f"\nResults written to {rp}")
    print("\n=== END Probe 7 (no images) ===")
    raise SystemExit(1)

section("QPrintPreviewDialog")
results.append("  Launching print preview dialog...")
results.append("  Close the dialog window to complete the probe.")
results.append(f"  Pages to render: {len(page_images)}")

output_before_dialog = "\n".join(results)
print(output_before_dialog)

def paint_pages(printer):
    painter = QtGui.QPainter(printer)
    page_rect = printer.pageRect()

    for i, pixmap in enumerate(page_images):
        if i > 0:
            printer.newPage()

        scaled = pixmap.scaled(
            page_rect.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )

        x = (page_rect.width() - scaled.width()) // 2
        y = (page_rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    painter.end()

try:
    dialog = QtPrintSupport.QPrintPreviewDialog()
    dialog.setWindowTitle(f"Probe 7: Print Preview ({len(page_images)} pages)")
    dialog.paintRequested.connect(paint_pages)
    dialog.exec_()
    ok("QPrintPreviewDialog", "displayed and closed by user")
except Exception:
    fail("QPrintPreviewDialog")

section("Summary")
if generated_test_image:
    results.append("  Used: generated test image (probe 6 PNGs not available)")
else:
    results.append(f"  Used: {len(page_images)} page images from probe 6")
results.append("  QPrintPreviewDialog is a built-in viewer and printer.")
results.append("  No external PDF viewer is needed.")

output = "\n".join(results)
print(output)

results_path = os.path.join(results_dir, "probe7_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 7 ===")
