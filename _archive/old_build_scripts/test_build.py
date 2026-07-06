#!/usr/bin/env python3
"""Simple test to verify PyInstaller works"""

import PyInstaller.__main__
import sys

# Run PyInstaller with the spec file
PyInstaller.__main__.run(['youtube_video_player.spec'])
