# -*- mode: python ; coding: utf-8 -*-
"""YouTube MPV Player - PyInstaller spec file

Build: pyinstaller youtube_video_player.spec
"""

from PyInstaller.building.build_main import Analysis
from PyInstaller.building.api import PYZ, EXE

block_cipher = None

a = Analysis(
    ['youtube_video_player.py'],
    pathex=[],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'requests',
        'subprocess',
        'json',
        'os',
        'sys',
        'time',
        'shutil',
        'logging',
    ],
    binaries=[
        ('mpv.exe', './'),
        ('yt-dlp.exe', './'),
    ],
    datas=[],  # User/ and Cache/ are auto-created at runtime
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='youtube_video_player',
    debug=False,
    console=False,
    icon=None,
)
