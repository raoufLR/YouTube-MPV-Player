import sys
from PyQt6.QtWidgets import QApplication
from app import Application
from ui.main_window import MainWindow
from ui.pages.profile_selector import ProfileSelectorWindow


def main():
    qt_app = QApplication(sys.argv)
    application = Application()
    application.startup()

    um = application.services.user_manager_service
    if um.profile_count() > 1:
        chosen = ProfileSelectorWindow.select_profile(application.services.user_manager_service)
        if chosen:
            application.load_profile(chosen)
    else:
        profiles = um.list_profiles()
        if profiles:
            application.load_profile(profiles[0].name)

    window = MainWindow(application)
    window.show()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
