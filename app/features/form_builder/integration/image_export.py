"""Form > Save image… and Print… (M5.5a, UX-PREV-002, UX-PREV-003, R3 180).

Both use the same picture: the open Preview of this form when there is one
(the real classes in the chosen style), else the canvas page at 100% without
overlays, chips or placeholders. Neither writes the ``.ui`` (the form's bytes
and undo stack are untouched), and neither blocks: the file dialog and the
print dialog are opened with ``open()`` and answer through callbacks.

Print… is absent, not disabled, where Qt print support is missing
(``print_available``). On ChoreBoy the only printer is "PDF-Printer", so the
print dialog's "Print to PDF file" is the usual route.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from app.features.form_builder.integration.toast import ToastNote
from app.qt.QtCore import QBuffer, QIODevice, QPointF, QRectF, QSize, Qt, QUrl
from app.qt.QtGui import QDesktopServices, QImage, QPainter
from app.qt.QtWidgets import QFileDialog

logger = logging.getLogger(__name__)

SHOW = "Show"
PNG_FILTER = "PNG image (*.png)"
_DIALOG_NAME = "formBuilder.saveImageDialog"


def default_name(form_path: str) -> str:
    """``{form stem}.png``."""
    stem = os.path.splitext(os.path.basename(form_path))[0]
    return "%s.png" % (stem or "form")


def saved_sentence(file_name: str) -> str:
    """The toast text (UX-PREV-002): ``Saved invoice.png.``"""
    return "Saved %s." % file_name


def print_available() -> bool:
    """True when Qt print support imports and a printer object can be made."""
    try:
        from app.qt.QtPrintSupport import QPrinter

        QPrinter()
    except Exception:
        return False
    return True


def canvas_image(surface: Any) -> Optional[QImage]:
    """The canvas page at 100%: the realized form, with no overlay, chip or placeholder drawn over it.

    One pixel per logical pixel: a 480 x 520 page is a 480 x 520 picture, also on a
    screen whose scale is 200% (``QWidget.grab`` would give 960 x 1040 device pixels).
    """
    page = surface.page_widget()
    if page is None:
        return None
    size = page.size()
    if size.isEmpty():
        return None
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(1.0)
    image.fill(Qt.GlobalColor.transparent)
    page.render(image)
    return image


def png_bytes(image: QImage) -> bytes:
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise OSError("the picture could not be encoded")
    return bytes(buffer.data())


def _image_from(png: Optional[bytes], surface: Any) -> Optional[QImage]:
    if png:
        image = QImage()
        if image.loadFromData(png):
            return image
    return canvas_image(surface)


def picture(surface: Any, done: Callable[[Optional[QImage]], None]) -> None:
    """The picture to save or print: the open Preview when there is one, else the canvas page."""
    control = getattr(surface, "preview_control", None)
    if control is None or not control.is_open:
        done(canvas_image(surface))
        return
    control.grab(lambda png: done(_image_from(png, surface)))


# ---- Save image…


def save_image(surface: Any) -> QFileDialog:
    """Open the file dialog in the form's folder with the name ``{stem}.png``. Returns the dialog."""
    path = str(surface.form_path())
    folder = os.path.dirname(path) or os.path.expanduser("~")
    dialog = QFileDialog(surface.window(), "Save image", folder, PNG_FILTER)
    dialog.setObjectName(_DIALOG_NAME)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setDefaultSuffix("png")
    dialog.selectFile(default_name(path))
    dialog.fileSelected.connect(lambda chosen, host=surface: write_image(host, str(chosen)))
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.open()
    return dialog


def write_image(surface: Any, target: str) -> None:
    """Save the picture to ``target``, then say so with a toast. The form file is never touched."""
    if not target:
        return
    if not target.lower().endswith(".png"):
        target += ".png"

    def got(image: Optional[QImage]) -> None:
        name = os.path.basename(target)
        if image is None:
            surface.narrate("There is no form to save as an image.")
            return
        try:
            data = png_bytes(image)
            with open(target, "wb") as handle:
                handle.write(data)
        except OSError:
            logger.exception("save image failed")
            surface.narrate("%s could not be saved." % name)
            return
        _toast(surface, saved_sentence(name), os.path.dirname(target))

    picture(surface, got)


def _toast(surface: Any, text: str, folder: str) -> None:
    toast = getattr(surface, "_command_toast", None)
    show = getattr(toast, "show_note", None)
    if not callable(show):
        return

    def reveal(_note: ToastNote) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    show(ToastNote(text, SHOW, "", 0), reveal)


# ---- Print…


def paint_page(image: QImage, printer: Any) -> None:
    """Draw ``image`` on the printer's first page, centred, at its screen size or smaller to fit."""
    painter = QPainter()
    if not painter.begin(printer):
        raise OSError("the printer could not be opened")
    try:
        from app.qt.QtPrintSupport import QPrinter

        page = printer.pageRect(QPrinter.Unit.DevicePixel)
        width = float(page.width())
        height = float(page.height())
        scale = float(printer.resolution()) / 96.0
        natural = QSize(max(1, int(image.width() * scale)), max(1, int(image.height() * scale)))
        if natural.width() > width or natural.height() > height:
            natural = natural.scaled(int(width), int(height), Qt.AspectRatioMode.KeepAspectRatio)
        left = (width - natural.width()) / 2.0
        top = (height - natural.height()) / 2.0
        painter.drawImage(QRectF(QPointF(left, top), QSize(natural)), image)
    finally:
        painter.end()


def print_form(surface: Any) -> Optional[Any]:
    """Open Qt's print dialog; on OK, print the picture. Returns the dialog (None when printing is not available)."""
    if not print_available():
        return None
    from app.qt.QtPrintSupport import QPrintDialog, QPrinter

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    dialog = QPrintDialog(printer, surface.window())
    dialog.setObjectName("formBuilder.printDialog")

    def accepted() -> None:
        def got(image: Optional[QImage]) -> None:
            if image is None:
                surface.narrate("There is no form to print.")
                return
            try:
                paint_page(image, printer)
            except OSError:
                logger.exception("print failed")
                surface.narrate("The form could not be printed.")

        picture(surface, got)

    dialog.accepted.connect(accepted)
    dialog.open()
    return dialog


__all__ = [
    "PNG_FILTER",
    "SHOW",
    "canvas_image",
    "default_name",
    "paint_page",
    "picture",
    "png_bytes",
    "print_available",
    "print_form",
    "save_image",
    "saved_sentence",
    "write_image",
]
