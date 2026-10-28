# Project Overview

**YouTube MPV Player Light** — A lightweight desktop YouTube player that streams videos via MPV with yt-dlp integration. No API keys, no OAuth, no Google Cloud setup required.

**Goals:**
- Private YouTube playback without browser overhead
- Fully local operation (no online account)
- Search, stream, and manage watch history entirely offline
- Smooth scrolling with hundreds of search results

**Stage:** Production 1.0 — feature-complete for the planned scope. All eight
milestones are implemented, tested, documented, and archived. EventBus is
thread-safe; persistence is async and atomic; playback is measured and
cancellation-safe; security boundaries are centralized.

---

# Architecture

## High-Level
```
main.py → Application (composition root)
           ├── EventBus (cross-component communication)
           ├── ServiceContainer (DI container)
           │   └── 14 services
           └── MainWindow (Qt UI)
               ├── SidebarWidget (navigation)
               ├── HeaderWidget (search bar + quality selector)
               ├── PageRegistry (keyed lazy pages: home, search, history,
               │   playlists, liked, settings, profile, analytics)
               ├── NowPlayingBar (transport controls + progress)
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

## Services (14 total)

All per-profile paths below are relative to the active profile directory
`User/profiles/<opaque-id>/`.  Profile directories use opaque IDs so display
names can never escape the profile root.

| Service | File | Storage | Responsibility |
|---------|------|---------|---------------|
| LoggingService | `services/logging_service.py` | — | Centralized logging setup |
| UserManagerService | `services/user_manager_service.py` | `User/profiles/<id>/profile.json` | Profile registry, validation, legacy migration, duplicate-name/lost-metadata recovery |
| SettingsService | `services/settings_service.py` | `settings.json` | Validated user preferences (quality, theme, volume, speed, etc.), repair on load, revision-based flush |
| AnalyticsService | `services/analytics_service.py` | `analytics.json` | Per-profile playback statistics (watch time, plays, rewatches, channel counts) derived from playback events; sanitized load; reset |
| PlayerService | `services/player_service.py` | — | MPV lifecycle + cached playback state (position/duration/pause/volume), monitor thread for EOF/crash detection |
| StreamResolverService | `services/stream_resolver_service.py` | — | yt-dlp resolution to `ResolvedStream` (direct video URL + optional DASH audio URL), cancellation-aware |
| PlaybackService | `services/playback_service.py` | — | Async resolve→play orchestration; newest-request-wins cancellation; metadata enrichment; replay/stop |
| SearchService | `services/search_service.py` | — | Stateless YouTube search via yt-dlp |
| ThumbnailCacheService | `services/thumbnail_cache_service.py` | `cache/thumbnails/` | LRU memory + disk thumbnail cache |
| UserProfileService | `services/user_profile_service.py` | `user_profile.json` | Display name & avatar (separate from the profile registry file), transactional updates |
| HistoryService | `services/history_service.py` | `history.json` | Watch history (500 cap, dedup, sanitized load, async flush, event-driven via VideoStartedEvent) |
| LikesService | `services/likes_service.py` | `likes.json` | Liked videos (sanitized load, transactional writes) |
| PlaylistService | `services/playlist_service.py` | `playlists/*.json` | Playlists CRUD + Watch Later built-in; duplicate-name repair, transactional writes |
| RecommendationService | `services/recommendation_service.py` | — | Recommendation feed assembly |

Shared core helpers: `core/validation.py` (defensive coercion), `core/json_store.py`
(atomic persistence), `core/data_bundle.py` (versioned export/import bundles).

## Models
- `Profile` — id, name, avatar, theme, language, timestamps (profile registry)
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
- **Playback**: VideoStartedEvent, VideoPausedEvent (with `is_paused`), VideoStoppedEvent (with `reason`, `video_id`, `position`, `duration`), PlaybackErrorEvent (with `video_id`/`stage`), StreamResolvingEvent, StreamResolvedEvent, StreamResolveFailedEvent
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
       └── create_services() instantiates all 14 services
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
| Python | 3.15 | Main language (requires >=3.14) |
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
│   └── service_container.py # 14-service DI registry
├── core/                   # Event system + persistence
│   ├── event_bus.py        # Thread-safe pub/sub with weak refs
│   ├── events.py           # 30 event dataclass types + constants
│   ├── json_store.py       # Atomic JSON persistence with recovery
│   ├── playback_errors.py  # Cancellation / resolution errors
│   ├── security.py         # URL/path validation, log redaction, private file modes
│   └── quality.py          # Quality map + URL/video-id validation
├── services/               # Business logic services
├── models/                 # 4 dataclass models
├── ui/                     # Qt widgets (themes managed by ThemeManager)
│   ├── main_window.py      # QMainWindow with keyed lazy page registry
│   ├── page_registry.py    # Key-based navigation (no stack indices)
│   ├── sidebar_widget.py   # Navigation sidebar
│   ├── header_widget.py    # Search input + quality combo (Escape clears search)
│   ├── shortcuts.py        # Focus-aware playback key filter
│   ├── window_state.py     # Geometry restore/save with clamping
│   ├── status_bar_widget.py # Generation-safe status messages
│   └── pages/
│       ├── search_page.py  # Infinite-scroll search results
│       ├── history_page.py # Watch history list
│       ├── playlists_page.py # Playlist CRUD + Watch Later
│       ├── liked_page.py   # Liked Videos
│       ├── analytics_page.py # Local playback statistics
│       └── settings_page.py # User preferences form
├── User/                   # All user data
│   └── profiles/
│       └── <opaque-id>/    # One directory per profile
│           ├── profile.json       # Profile registry metadata
│           ├── user_profile.json  # Display name / avatar
│           ├── settings.json
│           ├── history.json
│           ├── likes.json
│           ├── analytics.json      # Local playback statistics
│           ├── avatar.png
│           ├── cache/thumbnails/
│           └── playlists/         # One JSON file per playlist
├── Cache/thumbnails/       # Legacy/global thumbnail disk cache
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
- [x] Stream resolution via PlaybackService worker + StreamResolverService (never blocks the UI thread)
- [x] Status bar feedback: "Resolving stream..." → "Playing..."
- [x] Paste YouTube URL for direct playback (video_id extraction)
- [x] Watch history (500 cap, dedup, async flush, event-driven)
- [x] Like/Unlike videos (persisted locally, EventBus-synced UI)
- [x] Liked Videos page (live updates, thumbnails, empty state, play/unlike/watch-later)
- [x] Watch Later toggle (persisted, EventBus-synced UI via WatchLaterToggledEvent)
- [x] Playlists (create/rename/delete/add/remove videos)
- [x] User settings (quality, volume, theme, language, speed, search results, window size, maximized)
- [x] Window geometry persistence with on-screen clamping
- [x] User profile (username, avatar)
- [x] Analytics page: per-profile watch time, videos played, rewatches, and top channels from local playback events (nothing uploaded; reset supported)
- [x] Dark theme applied application-wide (dialogs/menus included)
- [x] Focus-aware keyboard shortcuts (Space/Esc/arrows; never steal keys from inputs/lists/sliders)
- [x] History page with clear-all + context menu
- [x] Playlists page with split-panel CRUD
- [x] Settings page with auto-save
- [x] Right-click context menus (Play, Like, Watch Later, Remove)
- [x] Status bar feedback for all operations
- [x] Thread-safe Qt UI updates (all via signals + EventBus)
- [x] Atomic JSON writes (tempfile + move)
- [x] Event-driven architecture with 30 event types
- [x] Dependency injection with 14 services
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
- Home feed personalization improvements
- Light theme
- Playlist drag-drop reorder
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
- Video playback via MPV with async stream resolution (never blocks the UI thread)
- Playback flow: double-click → PlaybackService worker → StreamResolverService (`yt-dlp -g`) → PlayerService → MPV → plays → history auto-saved
- DASH playback: separate video and audio URLs are passed to MPV via `--audio-file`
- Playback controls: pause/resume, absolute/relative seek, volume, stop, restart; now-playing bar tracks position/duration with cached state
- Superseded playback requests are cancelled (token + `threading.Event` + yt-dlp process termination)
- MPV crash/EOF detection via monitor thread; unique IPC pipe per playback; bounded stop escalation
- Pasted YouTube URL: metadata is enriched in the playback worker, so history entries are complete
- History, Likes, Playlists, Settings — all persisted with atomic writes
- Analytics page shows per-profile watch time, plays, rewatches, and the top five channels; totals update live after each playback and can be reset
- All UI pages (home, search, history, playlists, liked, settings, profile, analytics) render correctly
- Liked Videos page lists likes newest-first, updates live, and supports play/unlike/watch-later actions
- Context menus for like/watch-later/play/remove across search, history, playlists, and liked
- EventBus communication between all components
- EventBus-driven UI sync: like/WL/stream/playback events update Search, History, Playlists, Liked, and Home cards
- Per-item status indicators (resolving, playing, liked, watch later) in every video list
- Focus-aware keyboard shortcuts: Space/arrows/Escape never fire while typing, dragging a slider, or navigating a list; Escape in the search box clears the query
- Application-wide theming so dialogs, menus, message boxes, and tooltips match the selected theme
- Window size/position/maximized state persisted and clamped to visible screens on launch
- Failed profile switches keep the current profile and its pages intact; profile create/rename/duplicate/delete failures show explicit warnings
- Search failures surface an inline message and a status-bar error; home-feed refreshes coalesce instead of stacking threads; status messages cannot be clobbered by stale timers
- Architecture verification passes (100%)
- EventBus bugfixes: weak ref subscribe, unsubscribe by identity, publish dispatch (was calling weakref.ref directly instead of dereferencing)
- ServiceContainer shutdown calls service.shutdown() on all services (was clearing dict, orphaning threads)
- Data integrity: settings/history/likes/playlists/profiles are validated and repaired on load; unsafe IDs never reach the filesystem
- Durable mutations: likes, playlists, and user-profile updates write before committing, so failures return `False` without diverging memory and disk
- Profile safety: missing metadata recovery, duplicate-name repair, active-profile deletion refused at service level
- Versioned export/import bundles for settings, history, likes, playlists, and profile details
- Performance optimizations: async settings save, item text cache, O(1) video lookup, uniform item sizes, HTTP session pooling, batch thumbnails
- Language setting added to SettingsPage (was missing from UI despite being in model)
- Live UI smoke test against the real app, services, and profile data: all 8 pages render, theme/shortcut filter/title/search-Escape/transport checks pass, and per-page screenshots are archived for review
- Security boundaries centralized in `core/security.py`: remote-URL validation with YouTube-only thumbnail allowlist, local-path validation (no UNC/device/ADS/URLs), log redaction, and owner-only file modes on POSIX
- Thumbnail downloads: validated redirects (max 3), `image/*` only, 5 MiB cap (header + streamed), SHA-256 disk keys, atomic `os.replace`, private permissions
- yt-dlp runs with `--ignore-config` (a planted `yt-dlp.conf` can no longer inject `--exec`), `--no-playlist` for single videos, no stdin, and no working-directory executable lookup
- Logs redact signed URL queries (`sqp`/`rs`), tokens, credentials, bearer/basic values, and control characters before reaching disk or the console
- Avatar sources must be plain local files; copies are atomic and private. Unreachable `EncryptionService` and the `cryptography` dependency were removed (local data is not encrypted at rest)
- Home carousels now consume asynchronously downloaded thumbnails: `HomePage` subscribes to `ThumbnailLoadedEvent` and updates every card sharing the URL (previously only cache hits were painted on first load)
- Home rendering is optimized and measured: cached SVG icons, card styling in the theme instead of per-widget stylesheets, hover shadow created only while hovering, decoded thumbnail pixmaps shared through `QPixmapCache`, batched row updates. Card construction 1.76 → 0.62 ms, warm row populate 4.28 → 1.30 ms per card (see Performance Notes)
- Production release readiness: version `1.0.0`; Analytics wired end-to-end; dead scaffolding removed (`cli.py`, `plugins/`, `database_service.py`, `migration_service.py`); onefile build verified to run `--self-test` without bundling user data

**Partially working:**
- (none known in the implemented UI scope)

**Missing:**
- Search result caching
- Light theme
- Auto-update yt-dlp
- ~~Structured logging~~ DONE (LoggingService + Logs/app.log)
- ~~Test coverage~~ DONE (542 pytest tests, 78.6% coverage + live UI smoke test)
- ~~Keyboard shortcuts~~ DONE (focus-aware Space, Esc, arrows for seek/volume, Ctrl+1..5, Ctrl+Tab)
- ~~Liked Videos page~~ DONE (real page with live updates and actions)
- ~~Window geometry persistence~~ DONE (`ui/window_state.py`, `window_maximized`)
- ~~Security hardening~~ DONE (Milestone 6 — `core/security.py`, hardened yt-dlp/thumbnail/avatar/log boundaries)
- ~~Performance tuning~~ DONE (Milestone 7 — measured icon/style/texture/shadow optimizations, `tools/benchmark_perf.py`)
- ~~Production release readiness~~ DONE (Milestone 8 — Analytics wired end-to-end, dead modules removed, version `1.0.0`, onefile release build verified)

---

# Decisions

| Decision | Rationale |
|----------|-----------|
| **yt-dlp over YouTube API** | No API key, no quota, no OAuth required |
| **MPV for playback** | Lightweight, hardware-accelerated, built-in yt-dlp support |
| **Pre-resolve stream URL before passing to MPV** | StreamResolverService resolves via yt-dlp `-g`; PlayerService receives only direct media URLs (video + optional audio). Avoids MPV's built-in resolution for consistent quality/error handling. |
| **Async `PlaybackService`** | Resolution runs on a worker thread; a monotonically increasing token + `threading.Event` make newer requests win. The UI thread only mutates state and publishes events. |
| **Unique MPV IPC pipe per playback** | `\\.\pipe\ytmpv-{pid}-{token}` prevents a new playback from sending commands to a stale MPV instance. |
| **Single IPC worker thread** | All pipe writes/reads are serialized off the UI thread; `PlayerService` caches position/duration/pause so widgets never block on IPC. |
| **EventBus with weak refs** | Decouples components. Bound methods use `WeakMethod`; subscription tokens make cancellation explicit and prevent leaks |
| **Qt signals for UI thread safety** | PyQt6 signals marshal to main thread automatically |
| **EventBus for UI state sync** | Like, watch later, stream resolving, and playback state all synchronized via EventBus events — no direct coupling between MainWindow and SearchPage |
| **Atomic JSON writes via `JsonStore`** | Serialize → temp file → flush/fsync → `os.replace`; keeps `.bak`, quarantines corrupt files |
| **Opaque profile directories** | `User/profiles/<uuid>/` decouples display names from filesystem paths, preventing traversal and rename collisions |
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
| **Defensive validation at load and mutation boundaries** | A hand-edited, truncated, or partially-written JSON file can no longer inject the wrong type into the UI or MPV. Invalid records are dropped or normalized and the repaired file is written back. |
| **Copy-then-save-then-commit mutations** | Likes, playlists, and user-profile changes write a candidate snapshot before committing it to memory, so a failed write returns `False` instead of leaving memory ahead of disk. |
| **Versioned data bundle** | Export/import carries `schema_version`; unsupported versions are rejected instead of being silently coerced by current model defaults. On-disk file shapes are unchanged. |
| **Application event filter for playback keys** | Window-level `QShortcut`s fire even while the user types. A single `QApplication` event filter classifies the focused widget (text/value/navigation) and yields Space/arrows/Escape accordingly; Escape in a text field belongs to the field (search clears itself). |
| **Application-wide stylesheet** | `MainWindow` sets the theme stylesheet on `QApplication` as well as itself, so dialogs, menus, message boxes, and tooltips inherit the theme instead of falling back to the OS palette. |
| **Geometry persisted as normal geometry** | On close, maximized windows save `normalGeometry()` plus `window_maximized`, so restoring a maximized window does not lose its previous size/position. Restored rects are clamped to visible screen area. |
| **Boolean profile-switch results** | `Application.load_profile`/`switch_profile` return `True`/`False`. The UI treats `False` as failure and leaves the current pages/services untouched rather than tearing down a still-valid profile. |
| **Rebuild-on-event for history** | Replaying a video moves its history entry to the top, so the page rebuilds rows on `HistoryUpdatedEvent` instead of inserting; this removes duplicate rows and keeps section grouping correct. |
| **Generation tokens for status messages** | Delayed resets capture the message generation they were scheduled for, so an old timer can never overwrite a newer status message or error state. |
| **Explicit carousel content sizing** | Fixed-width cards cannot be laid out by a plain `QHBoxLayout` inside a scroll area: the content widget needs `N*card + (N-1)*spacing`. `HomeSection` activates the layout before reading `sizeHint`, ignores zero hints, removes old items with `takeAt` before `deleteLater`, and re-syncs once after deferred deletions settle. |
| **List pages own the page height** | `QListWidget` on History/Liked takes stretch factor 1 and the trailing stretch is removed (empty-state label is `Expanding`), so rows fill the page instead of being clipped at the list's 192px size hint. |
| **Security helpers in one module** | `core/security.py` owns remote-URL validation, local-path validation, log redaction, and private file modes. Services call these helpers instead of re-implementing checks, so the thumbnail fetcher, avatar importer, and JSON store cannot drift apart. |
| **Thumbnail fetches are allowlisted** | Only `ytimg.com`, `youtube.com`, `ggpht.com`, and `googleusercontent.com` (plus subdomains) may be fetched, over http/https on ports 80/443, with no credentials and no private/loopback addresses. Redirects are followed manually and re-validated, so a feed entry can never redirect the client to a LAN host. |
| **yt-dlp always ignores config files** | `--ignore-config` is passed on every invocation. A `yt-dlp.conf` placed next to the executable can inject `--exec` (arbitrary command execution); the app's own format/search flags are the only ones that should apply. `--no-playlist` prevents a single-video request from resolving a whole playlist. |
| **No working-directory executable lookup** | `youtube_api` resolves the bundled `yt-dlp.exe`, then `PATH`; it never runs `.\yt-dlp.exe`. Launching from a downloads folder must not execute a planted binary. Child processes get `stdin=DEVNULL`. |
| **Logs are redacted at the handler** | A `RedactionFilter` is installed on every root handler. Signed media/thumbnail URLs (`sqp`, `rs`), tokens, credentials, bearer/basic values, and control characters are scrubbed before they reach disk or the console — including urllib3 request lines. |
| **Local data is not encrypted at rest** | The unreachable `EncryptionService` (machine-derived AES key, no callers) was deleted along with the `cryptography` dependency. Real protection comes from OS user-ACL isolation, private file modes on POSIX, and not writing secrets to logs. Encrypting JSON with a key stored beside it would have implied security that did not exist. |
| **Async thumbnails reach home cards** | `HomePage` subscribes to `ThumbnailLoadedEvent` through `QtEventDispatcher`; `HomeSection` keeps a URL→cards index so one download updates every card showing that URL (a cold cache previously left the row grey forever). |
| **Analytics is wired, not removed** | The page was visible but always showed zeros because `record_playback()` had no caller. Statistics now come from `VideoStartedEvent`/`VideoStoppedEvent` (with the new `video_id`/`position`/`duration` payload) and are stored per profile, so the shipped feature is real without adding a second source of truth for history. |
| **Statistics stay out of the export bundle** | `analytics.json` counts time watched on this installation. Merging counters from another machine would double-count sessions, so the bundle keeps `DATA_SCHEMA_VERSION = 1` and each profile starts with its own totals. |
| **Dead scaffolding is deleted** | `cli.py`, `plugins/`, `database_service.py`, and `migration_service.py` were never imported or instantiated. Keeping unreachable modules in a 1.0 release advertises capability that does not exist, so they were removed from the tree, `pyproject.toml`, and CI. |

---

# Data Storage

```
User/
└── profiles/
    └── <opaque-id>/            # One directory per profile (UUID hex)
        ├── profile.json        # Profile registry: {id, name, avatar, theme, language, timestamps}
        ├── user_profile.json   # Display profile: {user_id, username, display_name, avatar_path, timestamps}
        ├── settings.json       # {default_quality, volume, theme, language, playback_speed, ...}
        ├── history.json        # [{id, title, channel, thumbnail, watched_at}, ...]  (max 500)
        ├── likes.json          # [{video_id, title, channel, thumbnail, liked_at}, ...]
        ├── analytics.json      # {version, watch_seconds, videos_played, channels, videos, last_played_at}
        ├── avatar.png          # Local avatar image
        ├── cache/thumbnails/   # Per-profile thumbnail cache
        └── playlists/
            ├── watch-later.json # Built-in playlist (protected from delete/rename)
            ├── <id>.json        # User-created playlists
            └── ...

Cache/thumbnails/        # Legacy/global thumbnail cache
```

Legacy `User/<profile-name>/` directories are migrated automatically on the
next startup: the directory is moved under `User/profiles/<uuid>/` and its
`profile.json` is rewritten with the opaque ID.  Existing history, settings,
likes, playlists, avatars, and thumbnails are preserved.

All writes go through `core.json_store.JsonStore`: JSON is serialized first,
written to a temporary file in the same directory, flushed and `fsync`ed, then
atomically replaced with `os.replace`.  The previous valid file is kept as
`.bak`; corrupt files are moved aside as `.corrupt-<timestamp>-<pid>` instead of
being silently discarded.

Persisted data is validated on load and on every mutation.  `core/validation.py`
provides total coercion helpers (safe IDs, bounded text, booleans, integers,
floats, timestamps) that never raise.  Known settings are clamped, unknown keys
are preserved for forward compatibility, and invalid history/like/playlist
entries are dropped or normalized while the repaired file is written back.
Mutations that must be durable (likes, playlists, user profile) use
copy-then-save-then-commit ordering, so a failed disk write leaves memory and
disk in agreement and returns `False` instead of raising.

Profile directories are recovered when `profile.json` is missing but profile
data is present; duplicate profile and playlist names are deterministically
renamed and persisted rather than hiding data.  The active profile cannot be
deleted by the service; `Application.delete_profile` switches to `Default`
first.

Cross-install moves use a versioned bundle (`core/data_bundle.py`,
`DATA_SCHEMA_VERSION = 1`) through `Application.export_data()` /
`Application.import_data()`.  The bundle contains `user_profile`, `settings`,
`history`, `likes`, and `playlists`; newer schema versions are rejected, while
each service sanitizes its own section on import.

`analytics.json` keeps an installation-local `STATS_SCHEMA_VERSION = 1`
snapshot.  Channel names are bounded text, counts are non-negative integers, a
single session is capped at 24 hours, and the channel/video maps are capped
(500 / 2000 entries) so a corrupted or hand-edited file cannot grow the page
without bound.  Invalid values are repaired and written back on load.  The
statistics are deliberately not part of the export bundle: they describe
playback on this installation, and merging them across machines would
double-count sessions.

---

# Security

All security boundaries live in `core/security.py` so services cannot drift:

| Boundary | Rule |
|----------|------|
| Remote URLs (thumbnails) | http/https only, ports 80/443, no credentials, no whitespace/control characters, ≤2048 chars, host allowlist (`ytimg.com`, `youtube.com`, `ggpht.com`, `googleusercontent.com`), IP literals must be globally routable, `localhost` rejected |
| Redirects | Followed manually, maximum 3, each hop re-validated against the same rules |
| Downloads | `image/*` content type required, 5 MiB cap checked from `Content-Length` and while streaming, bytes written to a private temp file and atomically replaced |
| Disk cache keys | SHA-256 of the URL; the URL itself is never used as a filename (signed query strings are not persisted in filenames) |
| yt-dlp | `--ignore-config` always, `--no-playlist` for single videos, `stdin=DEVNULL`, bundled executable then `PATH` (never the working directory) |
| Search input | Non-empty, ≤200 chars, no control characters; `max_results` clamped to 1–100 |
| yt-dlp output | Result IDs must match `^[A-Za-z0-9_-]{11}$`; titles/channels have control characters stripped and are length-bounded |
| Media URLs | Parsed (not prefix-matched): http/https/ytdl only, no credentials, host required, no whitespace/control characters |
| Avatars | Plain local paths only — no URLs, UNC/device paths, or Windows alternate data streams; copies are atomic (`copy_private_file`) and owner-only on POSIX |
| Logs | `RedactionFilter` on every handler scrubs URL queries, `key=token` parameters, bearer/basic credentials, control characters, and truncates at 4096 chars |
| File modes | `User/`, `Logs/`, and thumbnail cache directories are `0700`; JSON files, `.bak` copies, and cached images are `0600` on POSIX (Windows uses the user's ACLs) |

**Data at rest is not encrypted.** The previous `EncryptionService` was
unreachable and derived its key from machine information stored beside the
data; it was deleted together with the `cryptography` dependency. Isolation
comes from per-profile directories under the OS user account, private file
modes, and never logging signed URLs.

---

# APIs / Integrations

**yt-dlp (subprocess)**
- Search: `yt-dlp ytsearch{count}:{query} --ignore-config --flat-playlist --print-json --no-warnings --skip-download --playlist-start --playlist-end`
- Resolve stream: `yt-dlp -f {format} -g --ignore-config --no-warnings --no-playlist {url}` — prints the video URL and, for DASH, the separate audio URL on the next line. (`--dump-json` is **not** used for playback: merged `bestvideo+bestaudio` selectors have no usable top-level `url`.)
- Metadata (best-effort, for history): `yt-dlp --ignore-config --dump-json --skip-download --no-warnings --no-playlist {url}`
- Quality mapping: bestvideo[height<=N]+bestaudio/best[height<=N]
- Every call is cancellable: a superseded request terminates the yt-dlp process and raises `StreamCancelledError`.
- `--ignore-config` is mandatory: a config file beside the executable could otherwise add `--exec` and run arbitrary commands. `stdin` is closed and the working directory is never searched for the executable.

**MPV (subprocess + IPC)**
- Launch: `mpv.exe {video_url} [--audio-file={audio_url}] --input-ipc-server=\\.\pipe\ytmpv-{pid}-{token} --ytdl-format={selector} --no-terminal --wid={hwnd} ...`
- One unique named pipe per player instance; commands are serialized through a single background IPC worker.
- IPC commands: `set_property pause`, `seek <seconds> absolute`, `set_property volume`, `get_property time-pos/duration/pause/eof-reached`, `quit`.
- **Does not use built-in yt-dlp for normal playback** — receives pre-resolved direct media URLs.

---

# Performance Notes

- **Thumbnail Cache**: LRU OrderedDict (500 entries) + disk cache (7-day TTL) + async worker thread with requests.Session() HTTP connection pooling. Batch processing (10 items per lock).
- **Smooth scrolling**: QListWidgetItem with icon + text, uniform item sizes enabled on all lists (Qt skips per-item height calc). Spacing reduced 5→3/4→2.
- **Search**: Uses --flat-playlist (no per-video extraction), paginated in 30-result pages (was 20)
- **Settings**: Debounced async flush thread writes every 1s — was synchronous I/O on every set()
- **History**: Async flush thread writes every 2 seconds, never blocks UI
- **Stream resolution**: Runs in `PlaybackService`'s worker (daemon), never on the UI thread; superseded requests terminate their yt-dlp process.
- **Known bottleneck**: yt-dlp subprocess latency (network-bound) — affects both search and stream resolution
- **Thread safety**: RLock on all shared data structures. All UI updates via Qt signals. Background-published playback/stream events are delivered through `QtEventDispatcher`.

### Measured Performance (before → after)

| Benchmark | Before | After | Reduction |
|-----------|--------|-------|-----------|
| 100 SettingsService.set() | 138.4 ms | 1.75 ms | 98.7% |
| 10000 EventBus publish | 3693 ms | 15.9 ms | 99.6% |
| 100 _update_item_display | 18.9 ms | 0.61 ms | 96.8% |

### Milestone 7: home-page rendering (measured)

Harness: `python tools/benchmark_perf.py --runs 15` (offscreen Qt, synthetic
video data and JPEG thumbnails, median ms per operation). The "before" column
is the M6 archive measured with the same harness on the same machine; compare
ratios, not absolute values.

| Benchmark | Before | After | Change |
|-----------|--------|-------|--------|
| One 20 px SVG icon | 0.0573 ms | 0.0002 ms | ~99.6% (cached) |
| `VideoCard` construction | 1.762 ms | 0.617 ms | −65% |
| Home row populate, cold pixmaps (per card) | 4.41 ms | 2.94 ms | −33% |
| Home row populate, warm pixmaps (per card) | 4.28 ms | 1.30 ms | −70% |
| Thumbnail disk read (40 KiB) | 0.184 ms | 0.154 ms | unchanged path |
| EventBus publish | 0.0010 ms | 0.0008 ms | unchanged |
| JSON store save (100 entries) | 3.47 ms | 2.34 ms | unchanged (fsync-bound) |

Extrapolated to a full home page (7 rows × 10 cards): card construction
123 → 43 ms; first population 309 → 206 ms; re-population with decoded
pixmaps 300 → 91 ms. Remaining per-card cost is dominated by Qt layout
activation and the first JPEG decode; thumbnails are still decoded on the GUI
thread on a cold cache (~1.5 ms each, 38 images in the real profile ≈ 57 ms).

What changed:
- `ui/icons.py`: `_icon()` is `lru_cache`d by ``(SVG, size)``. Every card
  requested four icons, so a home page parsed and rasterised the same handful
  of SVGs ~280 times per load.
- `ui/components/video_card.py`: five per-card `setStyleSheet` calls moved into
  the theme stylesheet (object names `videoCardThumb`, `videoCardTitle`,
  `videoCardMeta`, `cardStatus`). Qt previously parsed and resolved a
  stylesheet for every label of every card. `set_liked`/`set_watch_later` now
  skip work when the state is already correct (rows call them on every card).
- Hover shadow is created on first hover and detached again when the blur
  animation returns to zero. A `QGraphicsDropShadowEffect` on every card forced
  offscreen rendering while scrolling; idle cards now paint directly.
- `ui/thumbnail_pixmaps.py`: decoded, display-sized pixmaps are stored in Qt's
  global `QPixmapCache` keyed by URL + size, so rebuilding a row decodes each
  JPEG at most once per run. Used by `HomeSection.set_videos`.
- `HomeSection.set_videos` disables updates while building a row and
  `_sync_content_size` skips redundant identical resizes.
- `tools/benchmark_perf.py` keeps this measurable: run it before and after any
  UI performance change.

---

# Known Bugs

- Like/Watch Later state indicators only on search page items (not history/playlists pages)
- Empty home sections (Watch Later / Liked with no data) render placeholder skeletons indefinitely instead of an empty state; they are visually indistinguishable from still-loading rows. Scheduled for the UI polish milestone.
- EventBus subscribers run on the publisher's thread. UI subscribers that may receive background events must use `ui/event_dispatcher.QtEventDispatcher`; any new direct Qt subscription from a background-publishing service is a bug. Playback/stream events are all dispatched this way (MainWindow, NowPlayingBar, SearchPage).

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
- `youtube_video_player.spec` — PyInstaller onefile spec (bundles `mpv.exe`, `yt-dlp.exe`, `d3dcompiler_43.dll`; excludes `User/`, `Cache/`, and `Logs/`)
- `_archive/old_build_scripts/` — Previous build scripts archived for reference

**Output:** `dist/youtube_video_player.exe` (single file, ~107 MB)

## Rollback Archives

Git is unavailable in this environment, so source archives are the rollback mechanism.
Archives exclude `User/`, `Cache/`, `Logs/`, and tool caches.

| Milestone | Archive | SHA-256 |
|-----------|---------|---------|
| M8 Production 1.0 | `youtube-mpv-player-m8-20261026-123634.zip` | `98770EB657A6406B4754FDB66CDA1B39050F55C451AE16041BAF0871AD3D5FA2` |
| M7 Performance tuning | `youtube-mpv-player-m7-20261024-022555.zip` | `90001071EE5D688E0F7CF2271E5C1BEBD101AAEC87CAC78ED20A69B0E48FB87F` |
| M6 Security hardening | `youtube-mpv-player-m6-20261024-013224.zip` | `13F77EDCE9B76C213C293FFFC1E9B9002EFE9FB22411B3F26E64DC974708869E` |
| M5 UI/UX (post-smoke fixes) | `youtube-mpv-player-m5-smokefix-20261024-005842.zip` | `F954A3348E5081EA96AD47A36DFC284C11DFE48AD99063EEECA790F9D264F1BF` |
| M5 UI/UX | `youtube-mpv-player-m5-20261024-003819.zip` | `82429A6F76E8E8AB642FBEC8AA26F981BB33BD8545C539BB853DE3A8172B7AD3` |
| M4 Data, profiles & settings | `youtube-mpv-player-m4-20261024-001103.zip` | `2DD6F4BB4842828528A04444F531B45102D9F34256C04F85EE7B003EBEB5307B` |
| M3 Playback reliability | `youtube-mpv-player-m3-20261023-234110.zip` | `4B5DE94DFCADE2A3ECB1C24D7E9637B4CD705A439461B78D1BD13468C241B3CD` |
| M2 Core correctness | `youtube-mpv-player-m2-20261023-231434.zip` | `CA373A99CD76EF604301DCF7A0AA7B96E41D52BD1368809EBE7CB5C7DA79BACD` |
| Baseline 0.9.0 | `youtube-mpv-player-baseline-0.9.0-20261023-205110.zip` | `3d0d55530833bd0b36cfa24a54862f1285cc3622d065ab018cd6798385fd9434` |

Archive directory: `C:\Users\Administrator\AppData\Local\Temp\opencode\`.

---

# TODO

1. [DONE] Fix EventBus thread safety — Qt calls now delegate via pyqtSignal (ui/event_dispatcher.py)
2. [DONE] Structured logging via LoggingService (no print() calls remain)
3. [DONE] Pasted YouTube URLs now enrich metadata in the playback worker, so history is complete
4. [DONE] Test coverage: 542 tests, 78.6% coverage (EventBus/JsonStore, validation, profiles, playback orchestration, MPV IPC, navigation, data bundles, shutdown, UI pages/shortcuts/window state, security boundaries, analytics service/page, icon/pixmap caches)
4b. [DONE] Live UI smoke test against real services/profile data: every page renders, theme/filter/title/transport behave, screenshots captured; fixed home-card overlap, clipped list heights, and blank search state it exposed
4c. [DONE] Security hardening: central `core/security.py`, thumbnail allowlist/redirect/size limits, yt-dlp `--ignore-config`, log redaction, safe avatar copies, private file modes; removed dead `EncryptionService`/`cryptography`
5. [MEDIUM] Search result caching (JSON or SQLite)
6. [DONE] Keyboard shortcuts (focus-aware Space=play/pause, Esc=stop, arrows=seek/volume, Ctrl+1..5, Ctrl+Tab)
7. [DONE] MpvPlayer injected into PlayerService via ServiceContainer
8. [DONE] Removed unused EVENT_TYPES dict
9. [LOW] Light theme stylesheet
10. [LOW] Auto-update yt-dlp on startup
11. [LOW] Playlist drag-drop video reorder
12. [DONE] Export/Import for all user data (versioned bundle via `core/data_bundle.py`)
13. [DONE] Like/WL/stream/playback EventBus subscriptions in History, Playlists, Liked, and Home sections
14. [DONE] Liked Videos page (real page with live updates, context menu, thumbnails, empty state)
15. [DONE] Window geometry/maximized persistence with on-screen clamping
16. [DONE] Application-wide theming and failure feedback (search, profile CRUD, playlist CRUD, playback errors)
17. [DONE] Security hardening — URL/path/log/permission boundaries (`core/security.py`), yt-dlp config isolation, thumbnail download limits, avatar path validation
18. [LOW] Empty home sections should show an empty state instead of placeholder skeletons
19. [DONE] Performance tuning (Milestone 7): cached SVG icons, theme-based card styling, lazy/released hover shadows, shared decoded-pixmap cache, batched row population; benchmark harness in `tools/benchmark_perf.py`
20. [LOW] Decode cold-cache thumbnails off the GUI thread (currently ~1.5 ms per image; a real home page decodes 38 on first load)
21. [DONE] Analytics wired end-to-end (Milestone 8): `AnalyticsService` subscribes to playback events, per-profile `analytics.json`, stats page with reset, 30 tests
22. [DONE] Dead scaffolding removed (Milestone 8): `cli.py`, `plugins/`, `database_service.py`, `migration_service.py`, plus their packaging/CI references
23. [DONE] Version bumped to `1.0.0`; README/BUILD/CHANGELOG updated; onefile build and `--self-test` verified

---

# Recent Changes

| Date | Change |
|------|--------|
| 2026-10-26 | **Live-log fix: MPV "property unavailable" noise.** Running the real app showed `MpvIPCError: MPV command failed: property unavailable` tracebacks in `Logs/app.log` whenever the monitor polled `time-pos` before MPV had loaded the file (and briefly after EOF). Added `MpvPropertyUnavailableError` (a subclass of `MpvIPCError`) in `player.py`; `PlayerService._monitor_loop` now treats it as "not ready yet" and continues silently instead of logging `MPV state poll failed` with a full traceback. Added 2 regression tests (IPC classification and a monitor poll that fails twice before succeeding). 544 tests, 78.6% coverage, Ruff clean. |
| 2026-10-24 | **Milestone 8: production 1.0.** Wired the Analytics page to real data instead of removing it: `AnalyticsService` now subscribes to `VideoStartedEvent`/`VideoStoppedEvent` (the stop event gained `video_id`, `position`, and `duration`), keeps per-profile `analytics.json` with atomic writes and load-time repair, and exposes watch time, plays, rewatches, and top channels. The page shows four stat cards, a top-five channel list, an empty state, live refresh on playback end, and a confirmed reset. Removed dead scaffolding that was never imported: `cli.py`, `plugins/`, `services/database_service.py`, and `services/migration_service.py`, including their `pyproject.toml` and CI references. Bumped the version to `1.0.0`, added `CHANGELOG.md`, and corrected `BUILD.md`. Verified: 542 tests / 78.6% coverage, Ruff clean, `--self-test` OK, onefile `dist/youtube_video_player.exe` (106.8 MB) runs `--self-test` with exit 0 and bundles no `User/`, `Cache/`, or `Logs/` data. |
| 2026-10-24 | **Milestone 7: performance tuning (measured).** Added `tools/benchmark_perf.py` (offscreen harness, median of N samples) and measured the home page before changing anything. SVG icons are now `lru_cache`d (280 renders per home page → 4 unique icons); card label styling moved from five per-widget stylesheets into the theme QSS (`videoCardThumb`/`videoCardTitle`/`videoCardMeta`/`cardStatus`), which removed ~0.7 ms of style resolution per card; the drop shadow is created on first hover and detached once idle, so scrolling cards paint directly; decoded/scaled thumbnails go through Qt's global `QPixmapCache` (`ui/thumbnail_pixmaps.py`), so re-populating a row or navigating back to Home does not re-decode every JPEG; `HomeSection.set_videos` batches updates and skips redundant content resizes; redundant `set_liked`/`set_watch_later` calls are ignored. Measured: card construction 1.76 → 0.62 ms (−65%), warm row population 4.28 → 1.30 ms per card (−70%). 512 tests, 75.9% coverage, Ruff clean, live 8-page smoke PASS (38/38 thumbnails, 0 overlaps). |
| 2026-10-24 | **Milestone 6: security hardening.** Added `core/security.py` (remote-URL validation with a YouTube image-host allowlist, public-IP checks, manual redirect re-validation, local-path validation rejecting URLs/UNC/device paths/ADS, log redaction, private file modes, atomic private copies). Thumbnail downloads now enforce `image/*`, a 5 MiB header+stream cap, SHA-256 disk keys, and atomic replacement. All yt-dlp invocations pass `--ignore-config` and `--no-playlist`, close stdin, and never execute a working-directory binary; search input and result metadata are validated/sanitized. Logs redact signed `sqp`/`rs` URL queries, tokens, credentials, bearer/basic values, and control characters, including urllib3 request lines. Avatar imports reject non-local sources and copy atomically. Removed the unreachable `EncryptionService` and the `cryptography` dependency (data is not encrypted at rest; isolation is OS/ACL and private modes). Also fixed home carousels never receiving background thumbnails, and fixed the smoke script that reported 37/38 by stopping before the last download finished. 499 tests, 75.88% coverage, Ruff clean. |
| 2026-10-24 | **Milestone 5 verification: live UI smoke test.** Booted the real application with real services/profile data and captured every page. Fixed three layout defects it exposed: home carousels overlapped because the scroll content was sized from a stale layout hint (now `activate()` + zero-hint guard + post-deletion re-sync, 0 overlaps across 7 sections); History/Liked lists were clipped to ~192px by a trailing stretch (lists now take stretch factor 1 and the empty label expands); the Search page was blank on first visit (now shows "Search for videos to get started", also after `clear_search()`). Added 4 regression tests. 408 tests, 72.80% coverage, Ruff clean. |
| 2026-10-24 | **Milestone 5: UI/UX.** Replaced window-level playback `QShortcut`s with a focus-aware application event filter (`ui/shortcuts.py`): Space/arrows/Escape now yield to text fields, sliders, combo boxes, buttons, and item views, while Escape in the search box clears the query. Added a real `LikedPage` (thumbnails, empty state, live updates, Play/Unlike/Watch Later context menu). Fixed playlist playback (entries use `video_id`), preserved playlist/video selection across reloads, and repaired the duplicate-row bug when replaying a history entry. Added like/Watch Later markers and playback/resolving badges across Search, History, Playlists, Liked, and Home cards. Applied the theme stylesheet application-wide so dialogs/menus/message boxes match. Persisted window size/position/maximized state via `ui/window_state.py` + `window_maximized`, clamped to visible screens. Coalesced home-feed refreshes with generation tokens, made status-bar timed messages generation-safe, surfaced search/playlist/profile failures, and made failed profile switches keep the current pages. 404 tests, 72.78% coverage. |
| 2026-10-24 | **Milestone 4: Data, profiles & settings.** Added `core/validation.py` for total, non-raising coercion of persisted user data. Settings now validate/clamp every known field, preserve unknown keys, repair stale schema versions, and keep `_dirty` set when a flush fails (retrying until the write succeeds). History sanitizes/dedupes entries and rejects unsafe IDs; likes and playlists use copy-then-save-then-commit mutations so failed writes no longer diverge memory from disk. Playlist load repairs duplicate names, reindexes videos, and enforces authoritative Watch Later metadata. Profiles recover missing `profile.json`, persist duplicate-name repairs, keep directory IDs authoritative, and refuse deletion of the active profile; `Application.delete_profile` switches to Default first. Added versioned export/import bundles (`DATA_SCHEMA_VERSION = 1`) through `Application.export_data()`/`import_data()`. Default theme is now `default` to match `THEME_REGISTRY`. 301 tests, 72.34% coverage. |
| 2026-10-23 | **Milestone 3: Playback reliability.** Playback now resolves streams with `yt-dlp -g` and passes the direct video URL plus the optional DASH audio URL to MPV via `--audio-file` (verified against MPV 0.41.0; `--dump-json` exposes no usable URL for merged formats). New async `PlaybackService` with newest-request-wins token cancellation and a commit-vs-stop lock, so a superseded request can never start MPV. `player.py` rewritten around a single background IPC worker, one unique named pipe per playback, startup crash detection, bounded stop escalation, and explicit `set_property`/`seek` commands. `PlayerService` caches position/duration/pause/volume and monitors EOF/unexpected exit. UI: async playback, working pause/seek/volume, `Esc`/stop through `PlaybackService`, progress-tracking now-playing bar, and `QtEventDispatcher` for all playback/stream events. Added shared `core/quality.py` validation and `core/playback_errors.py`. 255 tests, 66.77% coverage. |
| 2026-10-23 | **Milestone 2: Core correctness & data safety.** EventBus: `WeakMethod` support, subscription tokens, exception isolation, deterministic unsubscribe. New `core/json_store.py` with atomic writes, `.bak` recovery, corrupt-file quarantine, per-path locks; adopted by settings/history/likes/playlists/profile services. Profiles now use opaque `User/profiles/<uuid>/` directories with safe names, CRUD validation, and automatic legacy migration. `user_profile.json` separated from `profile.json`. Added keyed lazy `ui/page_registry.py` (no index-based navigation) and reverse-order idempotent shutdown. 141 tests, 60.99% coverage. |
| 2026-10-23 | **Milestone 1: Production baseline.** Version `0.9.0`, `--version`/`--self-test` entry points, pinned runtime/dev dependencies, pytest + coverage + Ruff configuration, Windows CI workflow, bootstrap tests, README/BUILD updates. |
| 2026-07-05 | **Phase 7: Performance optimization + production readiness review**. SettingsService: debounced async save (1s flush). EventBus: fixed 3 bugs (weak ref attr set, publish dispatch for weakref, unsubscribe by identity). ThumbnailCacheService: requests.Session(), batch processing (10/op), faster poll. SearchPage: O(1) video lookup dict, item text cache, uniform sizes, PAGE_SIZE 20→30. HistoryPage/PlaylistsPage: uniform item sizes. player.py: module-level QUALITY_MAP. ServiceContainer: shutdown calls service shutdown methods. SettingsPage: added Language combo. |
| 2026-07-05 | Phase 5: SearchPage EventBus-driven UI sync. Added WatchLaterToggledEvent. SearchPage subscribes to 7 events for auto-updating like/WL/resolving/playing status prefixes on items. MainWindow no longer directly updates SearchPage. |
| 2026-07-05 | Phase 4: StreamResolverService integration into playback flow. Stream resolution in background thread. Status bar shows "Resolving stream..." → "Playing...". Pasted URL video_id extraction. SearchCancelledEvent publishing. |
| 2026-07-05 | Phase 3: Removed Configuration service from DI container (12 services). Removed config_file plumbing from Application and ServiceContainer. |
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
YouTube MPV Player Light is a desktop YouTube player using **PyQt6** for UI, **MPV** for playback, and **yt-dlp** for search and stream resolution. All data is stored locally as JSON files under `User/profiles/<opaque-id>/`. No API keys or online accounts required.

## Architecture Pattern
1. **Composition Root**: `Application` creates `EventBus` + `ServiceContainer` → all 14 services → `MainWindow`
2. **Event-Driven**: Cross-component communication via `EventBus.publish()` / `EventBus.subscribe()`
3. **Qt Signals**: UI-to-UI communication and thread marshaling via `pyqtSignal`
4. **Stateless Services**: Services own one domain concern + one JSON file. SearchService is fully stateless (request IDs in UI layer)

## Playback Flow (critical path)
```
SearchPage double-click / paste URL / HomePage card
  → play_video_requested(video_id, quality, video_data) Qt signal
  → MainWindow._on_play_video_requested
  → MainWindow._start_playback(video_id, quality, video_data)
  → status_bar: "Resolving stream..."
  → PlaybackService.play() [returns immediately; worker thread]
      → cancels any older request (newest-request-wins token check)
      → publishes StreamResolvingEvent (SearchPage shows ⟳ prefix, main thread via QtEventDispatcher)
      → StreamResolverService.resolve_stream()
          → yt-dlp -g → ResolvedStream(video_url, audio_url)
      → publishes StreamResolvedEvent (SearchPage clears ⟳ prefix)
      → under _start_lock (commit-vs-stop):
          PlayerService.play_video(video_url, audio_url=audio_url)
            → MpvPlayer.play() → spawns MPV with a unique IPC pipe
            → VideoStartedEvent
                → HistoryService adds entry (title/channel enriched in worker)
                → MainWindow shows the embedded container
                → NowPlayingBar shows title and starts the progress timer
  → PlayerService monitor thread polls MPV every 0.5 s:
      time-pos / duration / pause / eof-reached → cached state
      EOF or unexpected process exit → VideoStoppedEvent (+ PlaybackErrorEvent on crash)
```

UI controls never perform IPC: `MainWindow` and `NowPlayingBar` call
`PlayerService.pause_resume()`, `seek_absolute()`, `seek_relative()`,
`set_volume()`, and read cached `get_position()/get_duration()`. `Esc` and the
stop button go through `PlaybackService.stop()`, which cancels a pending
resolver before stopping MPV.

## EventBus UI Sync Pattern
```
Service mutation → EventBus event → UI subscribes → auto-updates display

Like:     LikesService.toggle_like() → LikeChangedEvent → Search/History/Playlists/Liked/Home → ♥ prefix / button state
WL:       PlaylistService.toggle_watch_later() → WatchLaterToggledEvent → same pages → ⏰ prefix / button state
Resolve:  StreamResolverService.resolve_stream() → StreamResolvingEvent/StreamResolvedEvent → SearchPage → badge
Playback: PlayerService.play_video() → VideoStartedEvent → SearchPage → ▶ badge
Stop:     PlayerService.stop()/_handle_end() → VideoStoppedEvent (reason, video_id, position, duration) → NowPlayingBar/MainWindow → reset; AnalyticsService → totals; AnalyticsPage → refresh
```

## Key Principles
- **Never call Qt methods from background threads** — use signals only
- **EventBus subscribers run on the publisher's thread** — UI subscribers for playback/stream events must wrap callbacks in `ui/event_dispatcher.QtEventDispatcher` (MainWindow, NowPlayingBar, SearchPage, HistoryPage, PlaylistsPage, LikedPage do).
- **Playback keys go through one focus-aware filter** (`ui/shortcuts.py`) installed on `QApplication`; never add a window-level Space/arrow/Escape `QShortcut`.
- **Theme the application, not just the window** — `MainWindow` calls `QApplication.setStyleSheet` so dialogs/menus/message boxes inherit the theme.
- **All services use threading.RLock** for thread safety
- **Atomic writes**: all JSON persistence goes through `core/json_store.JsonStore` (`tempfile` + flush/fsync + `os.replace`, `.bak` recovery, corrupt-file quarantine)
- **Validate persisted data at both boundaries**: `core/validation.py` helpers coerce every loaded/mutated value; unsafe IDs are rejected before they reach a filename; repair writes happen automatically
- **Durable mutations write before commit**: likes, playlists, and user-profile changes save a candidate snapshot and only then update memory
- **No service creates another service** — all dependencies injected via constructor. `PlayerService` keeps a default `MpvPlayer()` only for standalone use; `ServiceContainer` always injects the shared instance.
- **UI sync via EventBus** — never directly manipulate another widget's state; publish events instead
- **Video containers may use any id spelling** — always resolve through `ui.components.video_card.extract_video_id` (`videoId` / `video_id` / `id`)
- **Profile switches are transactional from the UI's perspective** — `Application.switch_profile()` returns `False` on failure; the UI keeps the existing pages instead of rebuilding them
- **User data** lives under `User/profiles/<opaque-id>/`
- **Export/import** uses a versioned bundle (`core/data_bundle.py`, `DATA_SCHEMA_VERSION = 1`) so migrations never guess at older formats
- **Async persistence**: SettingsService uses debounced 1s flush thread (was sync I/O per set). A failed flush keeps the dirty flag set and retries; shutdown forces a final write.
- **Uniform item sizes**: All QListWidgets use setUniformItemSizes(True). Qt skips per-item height calc during scroll — major smoothness win.
- **Generation tokens for async UI work** — home-feed loads and status-bar timers capture a generation; stale completions are ignored rather than rendered/timer-clobbered.
- **Untrusted input goes through `core/security.py`** — thumbnail URLs are allowlisted and size-capped, local paths reject URLs/UNC/ADS, and every log handler has a `RedactionFilter`. Never log a raw URL or hand a feed-provided URL to `requests` without validation.
- **yt-dlp is always launched with `--ignore-config`** — never let a config file next to the executable add `--exec`; keep `stdin=DEVNULL` and never resolve the binary from the working directory.
- **UI performance is measured, not guessed** — use `tools/benchmark_perf.py` before/after. Keep styling in the theme QSS (object names), cache repeated renders (icons, decoded pixmaps), and never attach a graphics effect to every card.
- **Reuse row widgets; never rebuild a list on every refresh** — creating/deleting widgets (even with `deleteLater`) churns the Qt object tree. The analytics page pre-creates its five channel rows and only toggles visibility; the old rebuild approach caused an access violation in a later `QApplication.setStyleSheet()` polish pass once coverage timing shifted. Prefer updating existing labels; call `processEvents()` in test teardown after `deleteLater()`.
- **Statistics are an observer, not a source of truth** — `AnalyticsService` derives totals from playback events and stores them per profile. It must never be used to decide playback/history behaviour, and it is intentionally not exported in the data bundle.

## Performance Benchmarks

| Benchmark | Before | After | Reduction |
|-----------|--------|-------|-----------|
| 100 SettingsService.set() | 138.4 ms | 1.75 ms | 98.7% |
| 10000 EventBus publish | 3693 ms | 15.9 ms | 99.6% |
| 100 _update_item_display | 18.9 ms | 0.61 ms | 96.8% |
| One 20 px SVG icon (M7) | 0.0573 ms | 0.0002 ms | 99.6% |
| `VideoCard` construction (M7) | 1.762 ms | 0.617 ms | 65% |
| Home row, warm pixmaps (M7, per card) | 4.28 ms | 1.30 ms | 70% |

Reproduce the M7 numbers with `python tools/benchmark_perf.py --runs 15`
(offscreen Qt; `--json out.json` for comparisons).

## Known Critical Issues
1. **Thread safety (RESOLVED for playback)**: Playback/stream UI subscribers go through QtEventDispatcher; services have no Qt dependency.
2. **Logging**: DONE — LoggingService writes to Logs/app.log.
3. **Tests**: 542 pytest tests, 78.6% coverage; remaining gaps: recommendation search paths, some dialog internals. Security boundaries (`core/security.py`) are at 89.6%, analytics at 95.0%. Live UI smoke test passes on all 8 pages.
4. **Dead code**: core/task_manager.py and core/workers.py removed; entry.py and _archive removed.

## Files to Know
| File | Why It Matters |
|------|----------------|
| `ui/main_window.py` | Central hub — wires all pages, starts async playback, pauses/seeks/stops via services, installs the shortcut filter, applies app-wide theme, restores/saves geometry |
| `ui/shortcuts.py` | Focus-aware Space/arrow/Escape routing; the single place to change playback key bindings |
| `ui/window_state.py` | Window geometry clamping, restore, and save (`window_maximized`) |
| `ui/now_playing_bar.py` | Playback controls + timer-driven position/duration; never performs IPC |
| `ui/pages/liked_page.py` | Liked Videos page — live updates, thumbnails, context actions |
| `ui/pages/analytics_page.py` | Local statistics page — stat cards, reusable channel rows, live refresh, confirmed reset |
| `services/analytics_service.py` | Playback statistics from start/stop events; per-profile `analytics.json`; sanitize/repair/bounded maps |
| `ui/pages/search_page.py` | Most complex UI — infinite scroll, cancel search, context menus, thumbnail loading, EventBus-driven status indicators |
| `services/playback_service.py` | Async orchestration, newest-request-wins cancellation, metadata enrichment, commit-vs-stop lock |
| `services/stream_resolver_service.py` | yt-dlp → `ResolvedStream` (video + DASH audio), cancellation, failure events |
| `services/player_service.py` | MPV lifecycle, cached playback state, monitor thread (EOF/crash), pause/seek/volume |
| `player.py` | MPV subprocess + async named-pipe IPC worker + startup crash detection |
| `core/quality.py` | Quality map, video-id/URL validation, `ResolvedStream` |
| `core/security.py` | Single source of truth for remote-URL allowlists, local-path checks, log redaction, and private file permissions — review before adding any new network or file boundary |
| `services/thumbnail_cache_service.py` | Validated thumbnail downloads (allowlist, redirects, 5 MiB cap, SHA-256 disk keys) |
| `ui/thumbnail_pixmaps.py` | Shared decoded/scaled pixmap cache (`QPixmapCache`) used by home rows — avoids re-decoding JPEGs on every rebuild |
| `tools/benchmark_perf.py` | Offscreen performance harness for icons, cards, rows, thumbnail reads, EventBus, and JSON persistence |
| `core/validation.py` | Total coercion helpers for persisted user data (IDs, text, numbers, timestamps) |
| `core/data_bundle.py` | Versioned export/import bundle validation |
| `core/json_store.py` | Atomic writes, `.bak` recovery, corruption quarantine |
| `services/history_service.py` | Event-driven — subscribes to VideoStartedEvent, async flush |
| `core/event_bus.py` | Thread-safe pub/sub with weak references and RLock |
| `core/events.py` | 30 event dataclass types — add new events here first |
| `app/service_container.py` | DI registry — add/remove services here |
| `youtube_api.py` | yt-dlp subprocess wrapper — edit for search/extraction/metadata changes |
