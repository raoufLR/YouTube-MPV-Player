"""Tests for the command-line entry point and self-test mode."""

import pytest

from main import build_parser, parse_args
from version import __version__


def test_version_flag_exits_zero_and_prints_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--version"])

    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_self_test_flag_and_qt_arguments_are_separated():
    args, qt_args = parse_args(["--self-test", "-platform", "offscreen"])

    assert args.self_test is True
    assert qt_args == ["-platform", "offscreen"]


def test_defaults_do_not_enable_self_test():
    args, qt_args = parse_args([])

    assert args.self_test is False
    assert qt_args == []


def test_emit_is_safe_without_console_streams(monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module.sys, "stdout", None)
    monkeypatch.setattr(main_module.sys, "stderr", None)

    main_module._emit("windowed build has no console")


def test_self_test_bootstraps_offscreen_services(temp_dir, monkeypatch, qapp, capsys):
    monkeypatch.chdir(temp_dir)
    monkeypatch.setattr("services.settings_service.FLUSH_INTERVAL", 0.01)
    monkeypatch.setattr("services.history_service.FLUSH_INTERVAL", 0.01)

    from main import main

    assert main(["--self-test"]) == 0
    assert "self-test OK" in capsys.readouterr().out
