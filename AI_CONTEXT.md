# AI_CONTEXT.md - YouTube MPV Player Light

## Project Overview
A lightweight desktop YouTube player using **MPV** for playback and **yt-dlp** for search/extraction. No API keys, no OAuth, no Google Cloud setup required.

**Target users**: Users who want a simple, private YouTube player without browser overhead.

---

## Current Status
- **Stage**: Working MVP
- **Completed**: Search (yt-dlp), thumbnails, playback with quality selection, dark theme, play/pause/stop/volume controls
- **Removed**: OAuth auth, Liked Videos, Subscriptions tabs (required Google API)

---

## Architecture
```
G:\000\YouTubeMpvPlayer\
├── main.py          # UI + threading + search orchestration
├── player.py        # MPV wrapper with IPC control
├── youtube_api.py   # yt-dlp search wrapper (unused in current main.py)
├── yt-dlp.exe       # Local binary (v2026.06.09)
├── mpv.exe          # Local binary (v0.41.0-dev)
├── requirements.txt # PyQt5, requests
└── AI_CONTEXT.md    # This file
```

**Data Flow**:
1. User enters query → `SearchWorker` (thread) runs `yt-dlp ytsearch10:query --flat-playlist --print-json`
2. JSON parsed → video list emitted via Qt signal → `populate_search_results` creates list items
3. Thumbnails loaded async via `ThumbnailLoader` threads → Qt signal updates item icons
4. Double-click → `play_direct_url()` → `MpvPlayer.play(url, quality)` spawns MPV subprocess
5. Controls (pause/volume) → MPV JSON IPC via named pipe (`\\.\pipe\mpv_ipc`)

**Threading**: 
- SearchWorker + ThumbnailLoader run in daemon threads
- Qt signals (`pyqtSignal`) marshal results back to main thread (thread-safe UI updates)

---

## Technologies
| Tech | Version | Purpose |
|------|---------|---------|
| Python | 3.x | Main language |
| PyQt5 | Latest | GUI framework |
| requests | Latest | Thumbnail downloads |
| yt-dlp | 2026.06.09 | YouTube search + format extraction |
| MPV | 0.41.0-dev | Video playback |

---

## Code Standards
- **Naming**: CamelCase classes, snake_case functions/variables
- **Thread safety**: All UI updates via Qt signals, never direct from worker threads
- **Error handling**: Try/except with silent fail for thumbnails, QMessageBox for player errors
- **No config file**: All settings hardcoded (quality presets, search count=10, window size, theme)

---

## Important Systems

### SearchWorker (main.py:37-88)
- **Purpose**: Run yt-dlp search in background
- **Input**: Query string
- **Output**: List of dicts `{title, videoId, thumbnail, channel}` via `finished` signal
- **Limitation**: No caching, re-searches on every query

### ThumbnailLoader (main.py:17-34)
- **Purpose**: Download & convert thumbnail to QIcon
- **Input**: URL, target QListWidgetItem
- **Output**: `finished` signal with (item, icon)
- **Limitation**: Threads accumulate in `self.thumbnail_loaders` list (minor leak)

### MpvPlayer (player.py:9-92)
- **Purpose**: Spawn/control MPV process
- **API**: `play(url, quality)`, `pause_resume()`, `set_volume(0-100)`, `stop()`
- **IPC**: Named pipe JSON commands (`cycle pause`, `set volume`, `quit`)
- **Quality mapping**: Preset ytdl-format strings (1080p→bestvideo[height<=1080]+bestaudio...)

---

## Current Problems
| Bug | Cause | Workaround | Priority |
|-----|-------|------------|----------|
| yt-dlp version drift breaks playback | YouTube changes break old extractors | Run `yt-dlp.exe -U` manually | High |
| Thumbnail threads not cleaned up | List never cleared | Negligible for typical use | Low |
| No search history/caching | Not implemented | Re-search manually | Medium |
| No keyboard shortcuts | Not implemented | Mouse only | Low |

---

## Performance
- **Bottleneck**: Network latency (yt-dlp search + thumbnail downloads)
- **Optimized**: Flat playlist (no per-video extraction), async thumbnails, local binaries
- **Possible**: Cache search results, lazy-load thumbnails, reuse thumbnail threads

---

## Key Decisions
| Decision | Why | Alternative | Trade-off |
|----------|-----|-------------|-----------|
| yt-dlp over YouTube Data API | No API key, no quota, no OAuth | Official API | No Liked/Subscriptions without auth |
| Local binaries (yt-dlp.exe, mpv.exe) | Portable, version-locked, no PATH issues | System install | Manual updates needed |
| Qt signals for threading | Thread-safe UI updates | QThread/moveToThread | Slightly more boilerplate |
| Flat single-tab UI | Simplicity after OAuth removal | Multi-tab (Search/Liked/Subs) | Lost personal features |
| Hardcoded dark theme | Zero config, consistent look | Theme switching + config file | No user preference |

---

## TODO (Priority Order)
1. **Auto-update yt-dlp** on startup (Easy, depends on network)
2. **Search result cache** (Medium, local JSON file)
3. **Keyboard shortcuts** (Easy, Space=play/pause, Esc=stop, arrows=volume)
4. **Config file** (Medium, JSON for quality default, window geometry)
5. **Trending tab** (Medium, `yt-dlp "yttrending"`)
6. **Playlist support** (Hard, parse playlist URLs)
7. **Download option** (Medium, yt-dlp `-o` template)

---

## AI Notes
- **Critical**: `yt-dlp.exe` and `mpv.exe` must stay in project root (referenced by relative path)
- **Thread safety**: Never call `item.setIcon()` from worker thread - always use Qt signal
- **MPV IPC**: Named pipe path hardcoded to `\\.\pipe\mpv_ipc` (Windows only)
- **Quality mapping**: Must match yt-dlp format selector syntax exactly
- **Common mistake**: Forgetting `creationflags=CREATE_NO_WINDOW` shows console window on Windows
- **Risky area**: `ThumbnailLoader` threads accumulate - fix before long-running sessions

---

## Development History
| Date | Changes |
|------|---------|
| 2026-07-04 | Removed OAuth/Google API (auth.py, client_secret.json, token.pickle) |
| 2026-07-04 | Migrated search to yt-dlp (SearchWorker in main.py) |
| 2026-07-04 | Fixed thumbnail extraction (thumbnails array → largest) |
| 2026-07-04 | Updated yt-dlp 2025.12.08 → 2026.06.09 (fixed playback) |
| 2026-07-04 | Simplified UI: single Search tab, removed Liked/Subscriptions |

---

## Testing
**Run**: `python main.py` (requires PyQt5, requests, local yt-dlp.exe/mpv.exe)
**Manual test**:
1. Search "python tutorial" → results appear with thumbnails
2. Double-click video → MPV window opens, plays video
3. Play/Pause, Stop, Volume slider work
4. Paste direct YouTube URL → plays immediately

---

## Configuration (Hardcoded)
| Setting | Value | Location |
|---------|-------|----------|
| Search results count | 10 | main.py:50 (`ytsearch10:`) |
| Default quality | 720p | main.py:186 |
| Quality presets | 1080p/720p/480p/360p/best | player.py:30-36 |
| Window size | 900x700 | main.py:95 |
| Thumbnail size | 160x90 | main.py:198 |
| Theme colors | Dark (#2b2b2b bg) | main.py:104-167 |

---

## Dependencies
| Dep | Why |
|-----|-----|
| PyQt5 | GUI framework (Qt5) |
| requests | Thumbnail HTTP downloads |
| yt-dlp.exe | YouTube search + format extraction (external binary) |
| mpv.exe | Video playback engine (external binary) |

---

## Future Ideas
- Playlist parsing/playback
- Video download (format selection dialog)
- Proxy/TUI)
- History + favorites (local SQLite/JSON)
- Multi-window (detached player)
- Linux/macOS support (pipe path, binary names)

---

## FAQ
**Q: Why no API key needed?**
A: Uses yt-dlp's built-in YouTube extractor (scrapes public pages).

**Q: Where do thumbnails come from?**
A: yt-dlp returns `thumbnails[]` array; we pick the largest (last element).

**Q: How to update yt-dlp?**
A: Run `yt-dlp.exe -U` in project folder, or replace binary.

**Q: Can I use system mpv/yt-dlp?**
A: Yes, code falls back to PATH if local binary missing (player.py:21-27).

**Q: Why does MPV show console window?**
A: Fixed with `CREATE_NO_WINDOW` flag (player.py:52-53).

---

## Session Summary (2026-07-04)
- **Files modified**: main.py (rewritten), player.py (kept), youtube_api.py (simplified), requirements.txt (reduced)
- **Files deleted**: auth.py, client_secret.json, token.pickle
- **Features added**: yt-dlp search, async thumbnails, dark theme
- **Bugs fixed**: yt-dlp version incompatibility, thumbnail extraction
- **Decisions**: Removed OAuth entirely, local binaries, single-tab UI
- **Remaining**: Auto-update, cache, shortcuts, config, trending tab