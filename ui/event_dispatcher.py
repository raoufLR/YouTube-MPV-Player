from PyQt6.QtCore import QObject, pyqtSignal


class QtEventDispatcher(QObject):
    _triggered = pyqtSignal(object)

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self._triggered.connect(self._on_triggered)

    def __call__(self, event):
        self._triggered.emit(event)

    def _on_triggered(self, event):
        self._callback(event)
