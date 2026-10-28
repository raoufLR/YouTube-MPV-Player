"""Profile manager failure feedback and current-profile handling."""

import pytest
from PyQt6.QtCore import Qt

from ui.pages.profile_manager import ProfileManagerDialog

pytestmark = pytest.mark.qt


@pytest.fixture
def dialog(qapp, user_manager_service):
    widget = ProfileManagerDialog(user_manager_service)
    yield widget, user_manager_service
    widget.close()
    widget.deleteLater()


def _item_for(dialog, name):
    for row in range(dialog._list.count()):
        item = dialog._list.item(row)
        if item.data(Qt.ItemDataRole.UserRole) == name:
            return item
    raise AssertionError(f"profile {name} not listed")


def test_current_profile_is_marked(dialog):
    widget, manager = dialog
    item = _item_for(widget, "Default")
    assert "(current)" in item.text()


def test_current_profile_comparison_is_case_insensitive(dialog, monkeypatch):
    widget, manager = dialog
    monkeypatch.setattr(manager, "current_profile_name", lambda: "default")
    widget._refresh()

    item = _item_for(widget, "Default")
    assert "(current)" in item.text()

    info = []
    monkeypatch.setattr(
        "ui.pages.profile_manager.QMessageBox.information",
        lambda *args, **kwargs: info.append(args[2] if len(args) > 2 else ""),
    )

    emitted = []
    widget.profile_switched.connect(emitted.append)
    widget._on_switch(item)

    assert emitted == []
    assert widget._picked_name is None
    assert info and "already active" in info[0]


def test_switch_emits_selected_profile(dialog):
    widget, manager = dialog
    manager.create_profile("Alpha")
    widget._refresh()

    emitted = []
    widget.profile_switched.connect(emitted.append)
    widget._on_switch(_item_for(widget, "Alpha"))

    assert emitted == ["Alpha"]
    assert widget._picked_name == "Alpha"


def test_duplicate_create_warns(dialog, monkeypatch):
    widget, manager = dialog
    manager.create_profile("Alpha")
    widget._refresh()

    warnings = []
    monkeypatch.setattr(
        "ui.pages.profile_manager.QInputDialog.getText",
        lambda *args, **kwargs: ("alpha", True),
    )
    monkeypatch.setattr(
        "ui.pages.profile_manager.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else ""),
    )

    widget._on_create()
    assert warnings and "already exists" in warnings[0]


def test_duplicate_name_warns(dialog, monkeypatch):
    widget, manager = dialog
    manager.create_profile("Alpha")
    widget._refresh()
    widget._list.setCurrentItem(_item_for(widget, "Alpha"))

    warnings = []
    monkeypatch.setattr(
        "ui.pages.profile_manager.QInputDialog.getText",
        lambda *args, **kwargs: ("Alpha", True),
    )
    monkeypatch.setattr(
        "ui.pages.profile_manager.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else ""),
    )

    widget._on_duplicate()
    assert warnings and "already in use" in warnings[0]


def test_rename_failure_warns(dialog, monkeypatch):
    widget, manager = dialog
    manager.create_profile("Alpha")
    manager.create_profile("Beta")
    widget._refresh()
    widget._list.setCurrentItem(_item_for(widget, "Alpha"))

    warnings = []
    monkeypatch.setattr(
        "ui.pages.profile_manager.QInputDialog.getText",
        lambda *args, **kwargs: ("Beta", True),
    )
    monkeypatch.setattr(
        "ui.pages.profile_manager.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else ""),
    )

    widget._on_rename()
    assert warnings and "already in use" in warnings[0]
    assert manager.has_profile("Alpha")


def test_delete_active_profile_is_refused(dialog, monkeypatch):
    widget, manager = dialog
    manager.create_profile("Active")
    manager.switch_profile("Active")
    widget._refresh()
    widget._list.setCurrentItem(_item_for(widget, "Active"))

    warnings = []
    monkeypatch.setattr(
        "ui.pages.profile_manager.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else ""),
    )

    widget._on_delete()
    assert warnings and "active profile" in warnings[0]
    assert manager.has_profile("Active")


def test_default_profile_cannot_be_renamed(dialog, monkeypatch):
    widget, manager = dialog
    widget._list.setCurrentItem(_item_for(widget, "Default"))

    warnings = []
    monkeypatch.setattr(
        "ui.pages.profile_manager.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(args[2] if len(args) > 2 else ""),
    )

    widget._on_rename()
    assert warnings and "cannot be renamed" in warnings[0]
