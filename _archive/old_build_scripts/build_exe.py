#!/usr/bin/env python3
"""Simplest possible Python installer using PyInstaller."""

import PyInstaller.__main__
import os

def main():
    spec_file = os.path.join(
        os.getcwd(),
        'youtube_video_player.spec'
    )
    
    PyInstaller.__main__.run([
        spec_file,
        '--clean',
        '--noconfirm',  
    ])

if __name__ == '__main__':
    main()