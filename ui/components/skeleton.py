from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QBrush


class SkeletonWidget(QWidget):
    def __init__(self, width: int = 280, height: int = 240, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(800)

    def _animate(self):
        self._phase = (self._phase + 1) % 4
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        brightness = 40 + self._phase * 3
        base = QColor(brightness, brightness, brightness)
        lighter = QColor(brightness + 10, brightness + 10, brightness + 10)

        painter.setBrush(QBrush(base))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, self.width(), 158, 10, 10)

        painter.setBrush(QBrush(lighter))
        painter.drawRoundedRect(8, 170, 200, 12, 4, 4)
        painter.drawRoundedRect(8, 190, 140, 10, 4, 4)

        painter.end()

    def stop(self):
        self._timer.stop()
