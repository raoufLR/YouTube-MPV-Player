"""Re-render the three views at 2x device pixel ratio (crisp, unclipped)."""

import os
import sys
import time
import traceback

from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QPixmap, QRegion
from PyQt6.QtWidgets import QApplication, QScrollArea, QWidget

OUT_DIR = r"D:\New folder (2)\YouTube-MPV-Player-main\YouTube-MPV-Player-main"
SCALE = 2


def render_hires(window, name):
    size = window.size()
    pix = QPixmap(int(size.width()) * SCALE, int(size.height()) * SCALE)
    pix.setDevicePixelRatio(SCALE)
    pix.fill(window.palette().window().color())
    try:
        window.render(
            pix,
            QPoint(0, 0),
            QRegion(0, 0, size.width(), size.height()),
            QWidget.RenderFlag.DrawWindowBackground
            | QWidget.RenderFlag.DrawChildren,
        )
    except Exception:
        traceback.print_exc()
    out = os.path.join(OUT_DIR, name)
    print("SAVED", out, pix.save(out, "PNG"), pix.width(), "x", pix.height())


def main():
    qt_app = QApplication.instance() or QApplication([sys.argv[0]])

    from app import Application
    application = Application()
    application.startup()

    from ui.main_window import MainWindow

    um = application.services.user_manager_service
    profiles = um.list_profiles()
    if profiles:
        application.load_profile(profiles[0].name)

    window = MainWindow(application)
    # Lay the window out with real platform fonts without mapping it to the
    # screen, so the capture is not clamped to the desktop height.
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    window.resize(1280, 750)

    steps = []

    def section_ready(window, key: str) -> bool:
        """True once *key* shows real cards instead of skeleton placeholders."""
        from ui.components.skeleton import SkeletonWidget

        page = window.page_registry.ensure("home")
        section = page._sections.get(key)
        if section is None:
            return True
        for index in range(section._scroll_layout.count()):
            widget = section._scroll_layout.itemAt(index).widget()
            if widget is not None:
                return not isinstance(widget, SkeletonWidget)
        return False

    def home():
        window.page_registry.show("home")
        deadline = time.monotonic() + 30

        def poll():
            if section_ready(window, "recommended") or time.monotonic() > deadline:
                # Let the last thumbnails paint before rendering.
                QTimer.singleShot(900, lambda: (
                    render_hires(window, "screenshot.png"), steps[0]()))
            else:
                QTimer.singleShot(250, poll)

        QTimer.singleShot(500, poll)

    def settings_top():
        page = window.page_registry.ensure("settings")
        window.page_registry.show("settings")
        scroll = page.findChild(QScrollArea)
        if scroll is not None:
            scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(600, lambda: (
            render_hires(window, "screenshot_settings.png"), steps[1]()))

    def settings_updates():
        page = window.page_registry.ensure("settings")
        scroll = page.findChild(QScrollArea)
        label = page.update_status_label
        inner = scroll.widget()
        top = label.mapTo(inner, label.rect().topLeft()).y()
        scroll.verticalScrollBar().setValue(max(0, top - 40))
        QTimer.singleShot(600, lambda: (
            render_hires(window, "screenshot_settings_updates.png"), steps[2]()))

    def finish():
        qt_app.quit()

    steps.append(settings_top)
    steps.append(settings_updates)
    steps.append(finish)

    QTimer.singleShot(1400, home)
    qt_app.exec()

    application.shutdown()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
