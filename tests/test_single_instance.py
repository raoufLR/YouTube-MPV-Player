"""The single-instance lock keeps two copies off the same profile data."""

import os

from core.single_instance import SingleInstanceGuard


def test_second_guard_cannot_acquire_until_released(tmp_path):
    path = os.path.join(tmp_path, "User", "app.lock")
    first = SingleInstanceGuard(path)
    second = SingleInstanceGuard(path)
    try:
        assert first.acquire() is True
        assert second.acquire() is False
    finally:
        first.release()

    try:
        assert second.acquire() is True
    finally:
        second.release()


def test_lock_file_lives_in_the_data_directory(tmp_path):
    path = os.path.join(tmp_path, "User", "app.lock")
    guard = SingleInstanceGuard(path)
    try:
        assert guard.acquire() is True
        assert os.path.isfile(path)
    finally:
        guard.release()


def test_second_gui_instance_stops_before_starting_services(
    temp_dir, monkeypatch, qapp
):
    from main import main

    monkeypatch.chdir(temp_dir)
    holder = SingleInstanceGuard(os.path.join(temp_dir, "User", "app.lock"))
    assert holder.acquire() is True

    shown = []
    started = []
    monkeypatch.setattr(
        "PyQt6.QtWidgets.QMessageBox.information",
        lambda *args, **kwargs: shown.append(args) or 0,
    )
    monkeypatch.setattr("app.Application.startup", lambda self: started.append(True))

    try:
        assert main([]) == 0
    finally:
        holder.release()

    assert len(shown) == 1
    assert started == []


def test_self_test_reports_a_running_instance(
    temp_dir, monkeypatch, qapp, capsys
):
    from main import main

    monkeypatch.chdir(temp_dir)
    holder = SingleInstanceGuard(os.path.join(temp_dir, "User", "app.lock"))
    assert holder.acquire() is True

    try:
        assert main(["--self-test"]) == 1
    finally:
        holder.release()

    assert "another instance is running" in capsys.readouterr().err
