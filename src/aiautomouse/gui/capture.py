from __future__ import annotations

from io import BytesIO

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QDialog

from aiautomouse.gui.qt_helpers import pil_image_to_qpixmap


class RegionCaptureDialog(QDialog):
    def __init__(self, screen_capture, window_manager, parent=None) -> None:
        super().__init__(parent)
        self.screen_capture = screen_capture
        self.window_manager = window_manager
        self._origin: QPoint | None = None
        self._selection = QRect()
        self._pixmap = pil_image_to_qpixmap(self.screen_capture.capture())
        self._image_bytes: bytes | None = None
        self._offset_x = self.window_manager.get_virtual_screen().left
        self._offset_y = self.window_manager.get_virtual_screen().top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        virtual_screen = self.window_manager.get_virtual_screen()
        self.setGeometry(
            virtual_screen.left,
            virtual_screen.top,
            virtual_screen.width,
            virtual_screen.height,
        )
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)

    @property
    def image_bytes(self) -> bytes | None:
        return self._image_bytes

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._selection = QRect(self._origin, self._origin)
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None:
            self._selection = QRect(self._origin, event.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._origin is not None:
            self._selection = QRect(self._origin, event.position().toPoint()).normalized()
            self._capture_selection()
            self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if not self._selection.isNull():
            painter.drawPixmap(self._selection, self._pixmap, self._selection)
            pen = QPen(QColor("#00d2ff"))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self._selection)

    def _capture_selection(self) -> None:
        if self._selection.width() <= 1 or self._selection.height() <= 1:
            self._image_bytes = None
            return
        image, _ = self.screen_capture.capture_with_rect(
            {
                "left": self._selection.left() + self._offset_x,
                "top": self._selection.top() + self._offset_y,
                "width": self._selection.width(),
                "height": self._selection.height(),
            }
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        self._image_bytes = buffer.getvalue()
