"""Application data-root resolution."""

import os
import sys

from core.paths import data_root


def test_source_runs_use_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert data_root() == os.getcwd()


def test_frozen_builds_keep_data_beside_the_executable(tmp_path, monkeypatch):
    exe = tmp_path / "app" / "youtube_video_player.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.chdir(tmp_path)

    assert data_root() == str(exe.parent)
