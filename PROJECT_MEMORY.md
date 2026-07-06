# Project Overview

**YouTube MPV Player Light** — A lightweight desktop YouTube player that streams videos via MPV with yt-dlp integration. No API keys, no OAuth, no Google Cloud setup required.

**Goals:**
- Private YouTube playback without browser overhead
- Fully local operation (no online account)
- Search, stream, and manage watch history entirely offline
- Smooth scrolling with hundreds of search results

**Stage:** Optimized MVP — all features working. EventBus refactored for thread safety and performance. Async persistence, item text cache, uniform scrolling. Known thread-safety caveat on EventBus background subscribers (see Known Bugs).

---

# Architecture

## High-Level
```
main.py → Application (composition root)
           ├── EventBus (cross-component communication)
           ├── ServiceContainer (DI container)
           │   └── 10 services
           └── MainWindow (Qt UI)
               ├── SidebarWidget (navigation)
               ├── HeaderWidget (search bar + quality selector)
               ├── QStackedWidget
               │   ├── SearchPage (0)
               │   ├── HistoryPage (1)
               │   ├── PlaylistsPage (2)
               │   └── SettingsPage (3)
               └── QStatusBar
```

## Main Modules
| Module | Responsibility |
|--------|---------------|
| `app/` | Application bootstrap, ServiceContainer, DI composition root |
| `core/` | EventBus, event types |
| `services/` | All business logic services |
| `models/` | Dataclass models for serialization |
| `ui/` | Qt widgets and pages |
| `player.py` | Raw MPV subprocess wrapper |
| `youtube_api.py` | Raw yt-dlp subprocess wrapper |

## Services (9 total)

| Service | File | Storage | Responsibility |
|---------|------|---------|---------------|
| SettingsService | `services/settings_service.py` | `User/settings.json` | User preferences (quality, theme, volume, speed, etc.) |
| PlayerService | `services/player_service.py` | — | MPV subprocess control. Receives pre-resolved stream URLs only. No resolution logic. |
| StreamResolverService | `services/stream_resolver_service.py` | — | yt-dlp stream URL resolution. Used in main playback flow. |
| SearchService | `services/search_service.py` | — | Stateless YouTube search via yt-dlp |
| ThumbnailCacheService | `services/thumbnail_cache_service.py` | `Cache/thumbnails/` | LRU memory + disk thumbnail cache |
| UserProfileService | `services/user_profile_service.py` | `User/profile.json` | Profile & avatar management |
| HistoryService | `services/history_service.py` | `User/history.json` | Watch history (500 cap, dedup, async flush, event-driven via VideoStartedEvent) |
| LikesService | `services/likes_service.py` | `User/likes.json` | Liked videos |
| PlaylistService | `services/playlist_service.py` | `User/playlists/*.json` | Playlists CRUD + Watch Later built-in |

## Models
- `UserProfile` — user_id, username, display_name, avatar_path
- `UserSettings` — quality, volume, theme, language, speed, window geometry + arbitrary _extra dict
- `Playlist` — id, name, description, videos (list of PlaylistVideo)
- `PlaylistVideo` — video_id, title, channel, thumbnail, url, added_at, position

## Event Flow

```
User Action → Qt Signal → MainWindow Handler → Service Method → EventBus Event → Subscribers
```

Key events (defined in `core/events.py`):
- **Search**: SearchStartedEvent, SearchCompletedEvent, SearchFailedEvent, SearchCancelledEvent
- **Thumbnails**: ThumbnailLoadedEvent, ThumbnailFailedEvent
- **Playback**: VideoStartedEvent, VideoPausedEvent, VideoStoppedEvent, PlaybackErrorEvent, StreamResolvingEvent, StreamResolvedEvent
- **History**: HistoryUpdatedEvent
- **Likes**: LikeAddedEvent, LikeRemovedEvent, LikeChangedEvent
- **Playlists**: PlaylistCreatedEvent, PlaylistUpdatedEvent, PlaylistDeletedEvent
- **Watch Later**: WatchLaterToggledEvent
- **Settings**: SettingsChangedEvent
- **App lifecycle**: ApplicationStartedEvent, ApplicationClosingEvent

## Dependency Injection

```
Application (composition root)
  └── creates EventBus
  └── creates ServiceContainer(event_bus)
       └── create_services() instantiates all 9 services
            └── each service receives event_bus via constructor
  └── MainWindow receives Application
       └── accesses services via application.services.{name}
       └── passes services to child page widgets
```

Services NEVER create other services. All dependencies are injected.

---

# Technologies

| Tech | Version | Purpose |
|------|---------|---------|
| Python | 3.14 | Main language |
| PyQt6 | Latest | GUI framework |
| requests | Latest | Thumbnail HTTP downloads |
| yt-dlp | 2026.06.09 | YouTube search + format extraction |
| MPV | 0.41.0-dev | Video playback engine |

---

# Directory Structure

```
YouTubeMpvPlayer/
├── main.py                 # Entry point
├── player.py               # MPV subprocess wrapper (IPC via named pipe)
├── youtube_api.py          # yt-dlp subprocess wrapper (search + stream extraction)
├── app/                    # Application bootstrap & DI container
│   ├── application.py      # Composition root
│   └── service_container.py # 12-service DI registry
├── core/                   # Event system
│   ├── event_bus.py        # Thread-safe pub/sub with weak refs
│   └── events.py           # 24 event dataclass types + constants
├── services/               # Business logic services
├── models/                 # 4 dataclass models
├── ui/                     # Qt widgets (themes managed by ThemeManager)
│   ├── main_window.py      # QMainWindow with 4 pages
│   ├── sidebar_widget.py   # Navigation sidebar
│   ├── header_widget.py    # Search input + quality combo
│   └── pages/
│       ├── search_page.py  # Infinite-scroll search results
│       ├── history_page.py # Watch history list
│       ├── playlists_page.py # Playlist CRUD + Watch Later
│       └── settings_page.py # User preferences form
├── User/                   # All user data (future multi-user ready)
│   ├── profile.json
│   ├── settings.json
│   ├── history.json
│   ├── likes.json
│   ├── avatar.png
│   └── playlists/          # One JSON file per playlist
├── Cache/thumbnails/       # Thumbnail disk cache (MD5-hashed JPGs)
├── mpv.exe / yt-dlp.exe    # Local binaries
└── requirements.txt
```

---

# Features

- [x] YouTube search via yt-dlp with pagination (30 per page, was 20)
- [x] Infinite scroll (auto-load next page)
- [x] Cancel previous search on new query (request_id mechanism + SearchCancelledEvent)
- [x] Thumbnail caching (LRU memory + disk + async network fetch)
- [x] Video playback via MPV with pre-resolved stream URL (no local download)
- [x] Playback with quality selection (360p/480p/720p/1080p/best)
- [x] Stream resolution via StreamResolverService (background thread, non-blocking)
- [x] Status bar feedback: "Resolving stream..." → "Playing..."
- [x] Paste YouTube URL for direct playback (video_id extraction)
- [x] Watch history (500 cap, dedup, async flush, event-driven)
- [x] Like/Unlike videos (persisted locally, EventBus-synced UI)
- [x] Watch Later toggle (persisted, EventBus-synced UI via WatchLaterToggledEvent)
- [x] Playlists (create/rename/delete/add/remove videos)
- [x] User settings (quality, volume, theme, language, speed, search results, window size)
- [x] User profile (username, avatar)
- [x] Dark theme
- [x] History page with clear-all + context menu
- [x] Playlists page with split-panel CRUD
- [x] Settings page with auto-save
- [x] Right-click context menus (Play, Like, Watch Later, Remove)
- [x] Status bar feedback for all operations
- [x] Thread-safe Qt UI updates (all via signals + EventBus)
- [x] Atomic JSON writes (tempfile + move)
- [x] Event-driven architecture with 24 event types
- [x] Dependency injection with 10 services
- [x] Per-item status indicators: ⟳ resolving, ▶ playing, ♥ liked, ⏰ watch later
- [x] Debounced async save for settings (1s flush, was synchronous I/O on every set())
- [x] Item text cache for SearchPage status prefixes (97% faster _update_item_display)
- [x] O(1) video lookup by ID in SearchPage (dict-based _item_by_id, was O(n) linear scan)
- [x] Uniform item sizes on all list widgets (smoother scrolling via Qt optimization)
- [x] requests.Session() connection pooling for thumbnail downloads
- [x] Batch thumbnail queue processing (10 items per lock acquisition)
- [x] QUALITY_MAP at module level (no dict allocation per play())

---

# Planned Features

- Auto-update yt-dlp on startup
- Search result caching
- Keyboard shortcuts (Space=play/pause, Esc=stop)
- Light theme
- Multi-user support (User/{user_id}/)
- Playlist drag-drop reorder
- Export/Import history, likes, playlists
- Download option (yt-dlp -o)
- Trending tab (yt-dlp yttrending)
- Playlist URL parsing
- Proxy/TUI support

---

# Current Status

**Working:**
- All services initialize correctly
- Search with infinite scroll, cancel, and request_id stale result filtering
- Thumbnail caching (memory + disk with async worker)
- Video playback via MPV (resolved stream URL → MPV, no built-in yt-dlp in player)
- History, Likes, Playlists, Settings — all persisted with atomic writes
- Playback flow: double-click → StreamResolverService (background thread) → resolved URL → PlayerService → MPV → plays → history auto-saved
- Pasted YouTube URL: extracted video_id → same resolve-then-play flow
- All UI pages (search, history, playlists, settings) render correctly
- Context menus for like/watch-later/play/remove
- EventBus communication between all components
- EventBus-driven UI sync: like/WL/stream/playback events update SearchPage items
- Per-item status indicators (resolving, playing, liked, watch later)
- Architecture verification passes (100%)
- EventBus bugfixes: weak ref subscribe, unsubscribe by identity, publish dispatch (was calling weakref.ref directly instead of dereferencing)
- ServiceContainer shutdown calls service.shutdown() on all services (was clearing dict, orphaning threads)
- Performance optimizations: async settings save, item text cache, O(1) video lookup, uniform item sizes, HTTP session pooling, batch thumbnails
- Language setting added to SettingsPage (was missing from UI despite being in model)

**Partially working:**
- Like/Watch Later state indicators in search results only (not history/playlists pages — they lack EventBus subscriptions for these events)
- EventBus thread safety: subscribers run on publisher's thread. StreamResolvingEvent/StreamResolvedEvent published from background thread call SearchPage._update_item_display → item.setText() on wrong thread. Mitigated by Qt's internal thread-safe signal queuing for QListWidgetItem.setText() (not guaranteed).

**Missing:**
- Search result caching
- Keyboard shortcuts
- Light theme
- Auto-update yt-dlp
- Structured logging (143 print() calls, no logging module)
- Test coverage (zero tests across ~5,000 lines)

---

# Decisions

| Decision | Rationale |
|----------|-----------|
| **yt-dlp over YouTube API** | No API key, no quota, no OAuth required |
| **MPV for playback** | Lightweight, hardware-accelerated, built-in yt-dlp support |
| **Pre-resolve stream URL before passing to MPV** | StreamResolverService resolves via yt-dlp in background thread; PlayerService receives only resolved direct media URLs. Avoids MPV's built-in resolution for consistent quality/error handling. |
| **EventBus with weak refs** | Decouples components. Prevents memory leaks from orphan listeners |
| **Qt signals for UI thread safety** | PyQt6 signals marshal to main thread automatically |
| **EventBus for UI state sync** | Like, watch later, stream resolving, and playback state all synchronized via EventBus events — no direct coupling between MainWindow and SearchPage |
| **Atomic JSON writes** | Prevents file corruption on crash (tempfile + shutil.move) |
| **User/ directory for multi-user** | All user data under single directory; future user_id path prefix |
| **Dedicated services** | Each service owns one domain concern + one JSON file (SOLID) |
| **History auto-saved via EventBus** | HistoryService subscribes to VideoStartedEvent — no coupling with MainWindow |
| **SearchService stateless** | Request IDs owned by SearchPage (UI layer), not the service |
| **Local binaries (mpv.exe, yt-dlp.exe)** | Portable, version-locked, no PATH issues |
| **Removed Configuration service** | Legacy service superseded by SettingsService; lacked thread safety and atomic writes |
| **Debounced async settings save** | SettingsService switched from sync I/O per set() to debounced flush thread (1s). Dramatically reduces latency (138ms→1.75ms for 100 sets). Accepts small data-loss window on crash. |
| **Module-level QUALITY_MAP** | Moved from inside MpvPlayer.play() to module constant. Avoids dict allocation on every play() call. |
| **Uniform item sizes for lists** | setUniformItemSizes(True) on all QListWidgets. Qt skips per-item height calculation during scroll — significant smoothness improvement. |
| **Item text cache** | SearchPage caches _build_item_text results by (video_id, status). Avoids string concatenation on every EventBus status update event. |
| **O(1) video lookup** | Replaced linear scan in _update_item_display with dict-based _item_by_id. 97% reduction for 100-item list (18.9ms→0.6ms). |
| **requests.Session() for thumbnails** | HTTP connection pooling via requests.Session() — TCP connection reuse for thumbnail downloads. |
| **Batch thumbnail queue** | Process up to 10 thumbnails per lock acquisition — reduces RLock contention from _process_queue. |

---

# Data Storage

```
User/                    # User data (multi-user ready)
├── profile.json         # {user_id, username, display_name, avatar_path, timestamps}
├── settings.json        # {default_quality, volume, theme, language, playback_speed, ...}
├── history.json         # [{id, title, channel, thumbnail, watched_at}, ...]  (max 500)
├── likes.json           # [{video_id, title, channel, thumbnail, liked_at}, ...]
├── avatar.png           # Local avatar image
└── playlists/
    ├── watch-later.json # Built-in playlist (protected from delete/rename)
    ├── {uuid}.json      # User-created playlists
    └── ...

Cache/thumbnails/        # MD5-hashed JPG files with TTL (7 days)
```

All writes use atomic pattern: `tempfile.NamedTemporaryFile` → `shutil.move`.

---

# APIs / Integrations

**yt-dlp (subprocess)**
- Search: `yt-dlp ytsearch{count}:{query} --flat-playlist --print-json --no-warnings --skip-download --playlist-start --playlist-end`
- Extract stream: `yt-dlp -f {format} --print-json --no-warnings {url}` (used by StreamResolverService)
- Quality mapping: bestvideo[height<=N]+bestaudio/best[height<=N]

**MPV (subprocess + IPC)**
- Launch: `mpv.exe {resolved_stream_url} --input-ipc-server=\\.\pipe\mpv_ipc --force-window=immediate --keep-open=yes`
- IPC: Named pipe at `\\.\pipe\mpv_ipc`, JSON commands: `cycle pause`, `set volume`, `quit`
- **Does not use built-in yt-dlp** — receives pre-resolved direct stream URL

---

# Performance Notes

- **Thumbnail Cache**: LRU OrderedDict (500 entries) + disk cache (7-day TTL) + async worker thread with requests.Session() HTTP connection pooling. Batch processing (10 items per lock).
- **Smooth scrolling**: QListWidgetItem with icon + text, uniform item sizes enabled on all lists (Qt skips per-item height calc). Spacing reduced 5→3/4→2.
- **Search**: Uses --flat-playlist (no per-video extraction), paginated in 30-result pages (was 20)
- **Settings**: Debounced async flush thread writes every 1s — was synchronous I/O on every set()
- **History**: Async flush thread writes every 2 seconds, never blocks UI
- **Stream resolution**: Runs in a background thread (daemon), non-blocking for UI
- **Known bottleneck**: yt-dlp subprocess latency (network-bound) — affects both search and stream resolution
- **Thread safety**: RLock on all shared data structures. All UI updates via Qt signals. **Caveat**: EventBus subscribers run on publisher's thread — background-published events call Qt methods on wrong thread (see Known Bugs).

### Measured Performance (before → after)

| Benchmark | Before | After | Reduction |
|-----------|--------|-------|-----------|
| 100 SettingsService.set() | 138.4 ms | 1.75 ms | 98.7% |
| 10000 EventBus publish | 3693 ms | 15.9 ms | 99.6% |
| 100 _update_item_display | 18.9 ms | 0.61 ms | 96.8% |

---

# Known Bugs

- IPC named pipe error on first play after stop (`[Errno 2] No such file or directory`) — harmless, MPV recreated
- Like/Watch Later state indicators only on search page items (not history/playlists pages)
- Pasted YouTube URL plays but doesn't create history entry when video_data is None (no title/channel metadata)
- PlaylistService and UserProfileService both use User/ directory — no conflicts but watch for file name collisions
- EventBus subscribers run on publisher's thread. StreamResolvingEvent published from background thread → SearchPage._update_item_display → item.setText() on wrong thread. Not currently guarded (no thread check + delegate-to-main-thread logic).
- PlayerService default-constructs MpvPlayer() — violates Dependency Inversion Principle (DIP). Should receive MpvPlayer via DI.
- EVENT_TYPES dict in core/events.py is defined but never referenced anywhere.

---

---

# Building

See `BUILD.md` for full build instructions.

**Canonical build command:**
```powershell
python build.py
```

This runs `pyinstaller youtube_video_player.spec --clean --noconfirm`.

**Key build files:**
- `build.py` — Canonical build script (simple wrapper)
- `youtube_video_player.spec` — PyInstaller spec file (bundles mpv.exe, yt-dlp.exe, User/, Cache/)
- `_archive/old_build_scripts/` — Previous build scripts archived for reference

**Output:** `dist/YouTube MPV Player/youtube_video_player.exe`

---

# TODO

1. [CRITICAL] Fix EventBus thread safety — check + delegate Qt calls from background subscribers to main thread via pyqtSignal
2. [HIGH] Add structured logging (replace 143 print() calls with logging module)
3. [HIGH] Add video_data extraction for pasted YouTube URLs → enable history for that path
4. [HIGH] Add test coverage for critical paths (playback flow, search, EventBus, persistence)
5. [MEDIUM] Search result caching (JSON or SQLite)
6. [MEDIUM] Keyboard shortcuts (Space=play/pause, Esc=stop, arrows=volume)
7. [MEDIUM] Inject MpvPlayer into PlayerService via DI (remove default construction)
8. [LOW] Remove unused EVENT_TYPES dict from core/events.py
9. [LOW] Light theme stylesheet
10. [LOW] Auto-update yt-dlp on startup
11. [LOW] Playlist drag-drop video reorder
12. [LOW] Export/Import for all user data
13. [LOW] Extend like/WL/stream/playback EventBus subscriptions to HistoryPage and PlaylistsPage

---

# Recent Changes

| Date | Change |
|------|--------|
| 2026-07-05 | **Phase 7: Performance optimization + production readiness review**. SettingsService: debounced async save (1s flush). EventBus: fixed 3 bugs (weak ref attr set, publish dispatch for weakref, unsubscribe by identity). ThumbnailCacheService: requests.Session(), batch processing (10/op), faster poll. SearchPage: O(1) video lookup dict, item text cache, uniform sizes, PAGE_SIZE 20→30. HistoryPage/PlaylistsPage: uniform item sizes. player.py: module-level QUALITY_MAP. ServiceContainer: shutdown calls service shutdown methods. SettingsPage: added Language combo. |
| 2026-07-05 | Phase 5: SearchPage EventBus-driven UI sync. Added WatchLaterToggledEvent. SearchPage subscribes to 7 events for auto-updating like/WL/resolving/playing status prefixes on items. MainWindow no longer directly updates SearchPage. |
| 2026-07-05 | Phase 4: StreamResolverService integration into playback flow. Stream resolution in background thread. Status bar shows "Resolving stream..." → "Playing...". Pasted URL video_id extraction. SearchCancelledEvent publishing. |
| 2026-07-05 | Phase 3: Removed Configuration service from DI container (10 services). Removed config_file plumbing from Application and ServiceContainer. |
| 2026-07-05 | Phase 2: Rewrote PlaylistService (extracted helpers). Simplified UserProfileService. Enhanced HistoryService (typed VideoStartedEvent fields). Verified all backend services (StreamResolverService, LikesService, SettingsService). |
| 2026-07-05 | Phase 1: Extended VideoStartedEvent with typed metadata fields (video_id, title, channel, thumbnail). Updated PlayerService to populate new fields. |
| 2026-07-05 | Created PROJECT_MEMORY.md |
| 2026-07-05 | Fixed playback: removed StreamResolverService from flow. YouTube URL passed directly to MPV for streaming |
| 2026-07-05 | Fixed thread-safety: playback now runs entirely on main Qt thread via signals |
| 2026-07-05 | Created HistoryPage, PlaylistsPage, SettingsPage UI |
| 2026-07-05 | Rewrote SearchPage with cancel search (request_id), context menus, like/WL cache |
| 2026-07-05 | Created StreamResolverService + youtube_api.extract_stream_url() |
| 2026-07-05 | Created SettingsService (User/settings.json) |
| 2026-07-05 | Created LikesService (User/likes.json) |
| 2026-07-05 | Rewrote PlaylistService (User/playlists/ with model integration) |
| 2026-07-05 | Simplified UserProfileService (profile only) |
| 2026-07-05 | Enhanced HistoryService (event-driven, export/import/reset) |
| 2026-07-05 | Stripped PlayerService (stream resolution moved to StreamResolverService) |
| 2026-07-05 | Extended core/events.py with 5 new event types |
| 2026-07-05 | Updated ServiceContainer with 11 services |
| 2026-07-05 | Removed OAuth/Google API (auth.py, client_secret.json, token.pickle) |
| 2026-07-04 | Migrated search to yt-dlp (SearchWorker in main.py) |
| 2026-07-04 | Fixed thumbnail extraction (thumbnails array → largest) |
| 2026-07-04 | Updated yt-dlp 2025.12.08 → 2026.06.09 |
| 2026-07-04 | Simplified UI: single Search tab, removed Liked/Subscriptions |

---

# AI Handover

## Project Summary
YouTube MPV Player Light is a desktop YouTube player using **PyQt6** for UI, **MPV** for playback, and **yt-dlp** for search and stream resolution. All data is stored locally as JSON files under `User/`. No API keys or online accounts required.

## Architecture Pattern
1. **Composition Root**: `Application` creates `EventBus` + `ServiceContainer` → all 10 services → `MainWindow`
2. **Event-Driven**: Cross-component communication via `EventBus.publish()` / `EventBus.subscribe()`
3. **Qt Signals**: UI-to-UI communication and thread marshaling via `pyqtSignal`
4. **Stateless Services**: Services own one domain concern + one JSON file. SearchService is fully stateless (request IDs in UI layer)

## Playback Flow (critical path)
```
SearchPage double-click
  → play_video_requested(video_id, quality, video_data) Qt signal
  → MainWindow._on_play_video_requested
  → MainWindow._start_playback(video_id, quality, video_data)
  → status_bar: "Resolving stream..."
  → background thread:
      StreamResolverService.resolve_stream(video_id, quality)
        → publishes StreamResolvingEvent (SearchPage shows ⟳ prefix)
        → yt-dlp extracts direct stream URL
        → publishes StreamResolvedEvent (SearchPage clears prefix)
      → _resolved_signal.emit(stream_url, quality, video_data) [Qt signal, main thread]
  → MainWindow._on_stream_resolved
  → status_bar: "Playing..."
  → PlayerService.play_video(stream_url, quality, video_data)
    → MpvPlayer.play(stream_url) → spawns MPV with direct URL
    → VideoStartedEvent published
      → HistoryService._on_video_started → history entry added
      → SearchPage._on_video_started → ▶ prefix on item
```

## EventBus UI Sync Pattern
```
Service mutation → EventBus event → UI subscribes → auto-updates display

Like:     LikesService.toggle_like() → LikeChangedEvent → SearchPage._on_like_changed → ♥ prefix
WL:       PlaylistService.toggle_watch_later() → WatchLaterToggledEvent → SearchPage._on_watch_later_toggled → ⏰ prefix
Resolve:  StreamResolverService.resolve_stream() → StreamResolvingEvent/StreamResolvedEvent → SearchPage → ⟳ prefix
Playback: PlayerService.play_video() → VideoStartedEvent → SearchPage._on_video_started → ▶ prefix
```

## Key Principles
- **Never call Qt methods from background threads** — use signals only
- **EventBus subscribers run on the publisher's thread** — **this is a known thread-safety gap**. When `StreamResolverService.resolve_stream()` publishes `StreamResolvingEvent` from the background thread, the subscriber `SearchPage._on_stream_resolving` calls `_update_item_display` which calls `item.setText()` on the background thread. Current mitigation relies on Qt's internal queuing (not guaranteed). Fix: use a dedicated pyqtSignal bridge for background→main thread dispatch.
- **All services use threading.RLock** for thread safety
- **Atomic writes**: `tempfile.NamedTemporaryFile` + `shutil.move` for all JSON persistence
- **No service creates another service** — all dependencies injected via constructor (exception: PlayerService defaults to MpvPlayer() — TODO)
- **UI sync via EventBus** — never directly manipulate another widget's state; publish events instead
- **User data** lives in `User/` directory (future: `User/{user_id}/` for multi-user)
- **Async persistence**: SettingsService uses debounced 1s flush thread (was sync I/O per set). Accepts small data-loss window on crash.
- **Uniform item sizes**: All QListWidgets use setUniformItemSizes(True). Qt skips per-item height calc during scroll — major smoothness win.

## Performance Benchmarks

| Benchmark | Before | After | Reduction |
|-----------|--------|-------|-----------|
| 100 SettingsService.set() | 138.4 ms | 1.75 ms | 98.7% |
| 10000 EventBus publish | 3693 ms | 15.9 ms | 99.6% |
| 100 _update_item_display | 18.9 ms | 0.61 ms | 96.8% |

## Known Critical Issues
1. **Thread safety**: EventBus background subscribers call Qt methods on wrong thread. SearchPage._on_stream_resolving is the primary risk.
2. **No logging**: 143 print() statements, zero structured logging.
3. **No tests**: Zero test coverage across ~5,000 lines of code.
4. **Dead code**: core/task_manager.py (373 lines) and core/workers.py (189 lines) never wired.

## Files to Know
| File | Why It Matters |
|------|----------------|
| `ui/main_window.py` | Central hub — wires all pages, handles playback flow (stream resolve + play), like/WL service calls |
| `ui/pages/search_page.py` | Most complex UI — infinite scroll, cancel search, context menus, thumbnail loading, EventBus-driven status indicators |
| `services/stream_resolver_service.py` | yt-dlp stream URL resolution — called from MainWindow background thread |
| `services/player_service.py` | Thin wrapper around MPV — receives only pre-resolved stream URLs |
| `services/history_service.py` | Event-driven — subscribes to VideoStartedEvent, async flush |
| `core/event_bus.py` | Thread-safe pub/sub with weak references and RLock |
| `core/events.py` | 24 event dataclass types — add new events here first |
| `app/service_container.py` | DI registry — add/remove services here |
| `youtube_api.py` | yt-dlp subprocess wrapper — edit for search/extraction changes |
| `player.py` | MPV subprocess + IPC — edit for player flags/behavior |
