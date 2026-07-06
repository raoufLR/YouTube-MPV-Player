#!/usr/bin/env python3
"""YouTube MPV Player - Simple executable build script"""

import PyInstaller.__main__
import os
import sys
import shutil

def clean_build():
    """Clean previous builds"""
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    print("Cleaned previous builds")

def create_spec_file():
    """Create a working PyInstaller spec file"""
    spec_content = """block_cipher = None

a = Analysis(
    ['youtube_video_player.py'],
    pathex=[],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtNetwork',
        'requests',
        'subprocess',
        'json',
        'os',
        'sys',
        'time',
        'shutil',
        'logging',
        'threading',
        'typing',
        'dataclasses',
    ],
    binaries=[
        ('mpv.exe', '.'),
        ('yt-dlp.exe', '.'),
    ],
    datas=[
        ('User/', 'User'),
        ('Cache/', 'Cache'),
        ('pyproject.toml', '.'),
        ('requirements.txt', '.'),
        ('README.md', '.'),
        ('LICENSE', '.'),
    ],
    scripts=[],
)

exe = Executable(
    'youtube_video_player.py',
    a.binaries,
    {'name': 'YouTube MPV Player', 'version': '1.0.0'},
    'gui.',
    a.hiddenimports,
    a.hookspath,
    a.hooksourcedir,
)

dist = ''
create_exe = True
"""
    
    spec_file = 'youtube_video_player.spec'
    with open(spec_file, 'w') as f:
        f.write(spec_content)
    
    print(f"Created spec file: {spec_file}")

def build_executable():
    """Build the executable using PyInstaller"""
    try:
        print("Building executable with PyInstaller...")
        PyInstaller.__main__.run(['youtube_video_player.spec'])
        return True
    except Exception as e:
        print(f"Build failed: {e}")
        return False

def main():
    """Main build function"""
    print("=" * 60)
    print("YouTube MPV Player - Executable Builder")
    print("=" * 60)
    
    clean_build()
    create_spec_file()
    
    if build_executable():
        print("\n" + "=" * 60)
        print("Build completed successfully!")
        print("Executable location: dist/youtube_video_player.exe")
        
        exe_path = os.path.join('dist', 'youtube_video_player.exe')
        if os.path.exists(exe_path):
            print(f"✓ Executable file exists: {exe_path}")
            return True
        else:
            print("✗ Executable file not found!")
            return False
    else:
        print("\n" + "=" * 60)
        print("Build failed!")
        return False

if __name__ == '__main__':
    sys.exit(0 if main() else 1)
