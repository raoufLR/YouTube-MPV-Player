# Building YouTube MPV Player

## Prerequisites

- **Python 3.14+** — Must be installed and on PATH
- **PyInstaller 6.22.3** — Install via `pip install -r requirements-dev.txt`
- **mpv.exe** — Place in the project root
- **yt-dlp.exe** — Place in the project root
- **d3dcompiler_43.dll** — Place in the project root (required by MPV for rendering)

All Python dependencies are pinned in `requirements.txt`; build/test tools are in
`requirements-dev.txt`.

## Quick Start

```powershell
# Install dependencies
pip install -r requirements-dev.txt

# Build the executable
python build.py
```

`build.py` removes `build/` and `dist/`, checks for the three binaries, then runs:

```powershell
python -m PyInstaller youtube_video_player.spec --clean --noconfirm
```

## What the Build Does

1. **Analyzes** `youtube_video_player.py` and its imports
2. **Bundles** into a single self-extracting executable:
   - `mpv.exe` (video playback engine)
   - `yt-dlp.exe` (YouTube search and stream resolution)
   - `d3dcompiler_43.dll` (MPV rendering dependency)
   - `icon/yt-mpv-icon-fusion.svg` (window, taskbar and sidebar logo)
   - Application code (including `services/`, `core/`, `ui/`, `models/`) and pinned dependencies
3. **Outputs** a onefile build to `dist/youtube_video_player.exe`

`User/` and `Cache/` are **not** bundled. They are created on first launch beside
the executable, with per-profile data under `User/profiles/<opaque-id>/`.
The executable icon comes from `icon/yt-mpv-icon-fusion.ico`; regenerate it with
`python tools/make_icon.py` after editing the SVG.

## Output

| Artifact | Path | Notes |
|---|---|---|
| Executable | `dist/youtube_video_player.exe` | Single file, ~107 MB |
| Build work directory | `build/` | Temporary; safe to delete |

## Verifying a Build

```powershell
# Version and headless service bootstrap
.\dist\youtube_video_player.exe --version
.\dist\youtube_video_player.exe --self-test
```

`--self-test` exits with code `0` and prints `YouTube MPV Player <version> self-test OK`.
Because the executable is a windowed build, logging may still be written to
`Logs/app.log` next to it.

Confirm no user data was baked into the image (PowerShell):

```powershell
python -m PyInstaller.utils.cliutils.archive_viewer -l dist\youtube_video_player.exe |
    Select-String "(^|[\\/])(User|Cache|Logs)[\\/]"
```

The command should return no matches; the listing must include `mpv.exe`,
`yt-dlp.exe`, and `d3dcompiler_43.dll`.

## Release Checklist

1. `python -m pytest -q` — all tests pass
2. `python -m pytest --cov --cov-report=term --cov-fail-under=50` — coverage gate
3. `python -m ruff check .`
4. `python -m compileall -q app core models services ui tools main.py player.py youtube_api.py version.py youtube_video_player.py`
5. `python main.py --version` / `python main.py --self-test`
6. `python build.py`
7. `dist\youtube_video_player.exe --self-test` (exit code `0`)
8. Archive listing contains the bundled binaries and no `User/`, `Cache/`, or `Logs/`

## Project Structure (Build-Related)

```
YouTubeMpvPlayer/
├── build.py                              # Canonical build script (run this)
├── youtube_video_player.spec             # PyInstaller onefile spec
├── youtube_video_player.py               # Application entry point
├── version.py                            # Version metadata (single source)
├── requirements.txt                      # Runtime dependencies (pinned)
├── requirements-dev.txt                  # Test/build/lint dependencies (pinned)
├── mpv.exe                               # Video player binary
├── yt-dlp.exe                            # YouTube streaming binary
├── d3dcompiler_43.dll                    # MPV rendering dependency
├── User/                                 # Runtime data (never bundled)
├── Cache/thumbnails/                     # Legacy/global thumbnail cache
├── app/                                  # Application core + DI container
├── core/                                 # Event system + persistence helpers
├── models/                               # Data models
├── services/                             # Business logic services
├── ui/                                   # PyQt6 UI components
├── tests/                                # Pytest suite
├── tools/                                # Benchmark harness
└── _archive/old_build_scripts/           # Previous build scripts (archived)
```

## Troubleshooting

- **Missing imports?** Add them to `hiddenimports` in `youtube_video_player.spec`
- **Binary not found?** Ensure `mpv.exe`, `yt-dlp.exe`, and `d3dcompiler_43.dll` are in the project root
- **`--self-test` exits non-zero?** Run it from a console-enabled Python build first (`python main.py --self-test`) to see the traceback
- **PyInstaller errors?** Run `python -m PyInstaller youtube_video_player.spec --clean --noconfirm` directly for verbose output
- **Antivirus flags the executable?** PyInstaller onefile builds are frequently false-positive; sign the binary or distribute a `--onedir` build if this matters
