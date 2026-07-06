# Building YouTube MPV Player

## Prerequisites

- **Python 3.14+** — Must be installed and on PATH
- **PyInstaller** — Install via `pip install pyinstaller`
- **mpv.exe** — Place in the project root (or install system-wide)
- **yt-dlp.exe** — Place in the project root (or install system-wide)

All other Python dependencies are listed in `requirements.txt`.

## Quick Start

```powershell
# Install dependencies
pip install -r requirements.txt

# Build the executable
python build.py
```

This runs `pyinstaller youtube_video_player.spec --clean --noconfirm`.

## What the Build Does

1. **Analyzes** `youtube_video_player.py` and its imports
2. **Bundles** the following into a single executable:
   - `mpv.exe` (video playback engine)
   - `yt-dlp.exe` (YouTube streaming library)
   - `User/` directory (user profiles and settings)
   - `Cache/` directory (thumbnail cache)
3. **Outputs** the executable to `dist/YouTube MPV Player/`

## Output

| Artifact | Path |
|---|---|
| Main executable | `dist/YouTube MPV Player/youtube_video_player.exe` |
| Supporting files | `dist/YouTube MPV Player/` |

## Project Structure (Build-Related)

```
YouTubeMpvPlayer/
├── build.py                              # Canonical build script (run this)
├── youtube_video_player.spec             # PyInstaller spec file
├── youtube_video_player.py               # Application entry point
├── requirements.txt                      # Python dependencies
├── mpv.exe                               # Video player binary
├── yt-dlp.exe                            # YouTube streaming binary
├── User/                                 # User profiles, settings, history
├── Cache/thumbnails/                     # Thumbnail cache
├── app/                                  # Application core
├── core/                                 # Event system
├── models/                               # Data models
├── services/                             # Business logic services
├── ui/                                   # PyQt6 UI components
└── _archive/old_build_scripts/           # Previous build scripts (archived)
```

## Troubleshooting

- **Missing imports?** Add them to `hiddenimports` in `youtube_video_player.spec`
- **Binary not found?** Ensure `mpv.exe` and `yt-dlp.exe` are in the project root
- **PyInstaller errors?** Run `pyinstaller youtube_video_player.spec --clean --noconfirm` directly for verbose output
