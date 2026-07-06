import os

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFileDialog
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPixmap, QPainter, QBrush, QColor, QFont, QIcon


DEFAULT_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#34495e",
    "#16a085", "#c0392b", "#2980b9", "#8e44ad",
]


def _color_for_name(name: str) -> str:
    idx = abs(hash(name or "")) % len(DEFAULT_COLORS)
    return DEFAULT_COLORS[idx]


class AvatarWidget(QWidget):
    def __init__(self, size: int = 80, parent=None):
        super().__init__(parent)
        self._size = size
        self._pixmap: QPixmap = None
        self._name: str = ""
        self._image_path: str = ""
        self._editable = False
        self.setFixedSize(size, size)

    def set_name(self, name: str):
        self._name = name
        self._render()

    def set_image(self, path: str):
        self._image_path = path
        self._render()

    def set_editable(self, editable: bool):
        self._editable = editable
        self.update()

    def get_pixmap(self) -> QPixmap:
        return self._pixmap if self._pixmap else QPixmap(self._size, self._size)

    def _render(self):
        size = self._size
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRect(0, 0, size, size)
        if self._image_path and os.path.exists(self._image_path):
            src = QPixmap(self._image_path)
            if not src.isNull():
                src = src.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
                brush = QBrush(src)
                painter.setBrush(brush)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(rect)
                painter.end()
                self._pixmap = pixmap
                self.update()
                return

        color = QColor(_color_for_name(self._name))
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(rect)

        if self._name:
            initial = self._name[0].upper()
            font = QFont()
            font.setPixelSize(size // 2)
            painter.setFont(font)
            painter.setPen(QColor(Qt.GlobalColor.white))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initial)
        painter.end()
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        if self._pixmap:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.drawPixmap(0, 0, self._pixmap)
            painter.end()

    def mousePressEvent(self, event):
        if self._editable:
            path, _ = QFileDialog.getOpenFileName(
                self, "Choose Avatar", "", "Images (*.png *.jpg *.jpeg *.webp)"
            )
            if path:
                self.set_image(path)

    def to_icon(self) -> QIcon:
        return QIcon(self.get_pixmap())
