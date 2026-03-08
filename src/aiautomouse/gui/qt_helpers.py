from __future__ import annotations

from io import BytesIO

from PySide6.QtGui import QImage, QPixmap


def pil_image_to_qpixmap(image) -> QPixmap:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    qimage = QImage.fromData(buffer.getvalue(), "PNG")
    return QPixmap.fromImage(qimage)
