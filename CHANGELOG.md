# Changelog

All notable changes to YouTube MPV Player are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Single-instance guard: a PID-aware lock file in `User/` stops a second GUI
  copy (or `--self-test` run) from sharing one profile directory. The second
  launch shows a notice and exits; locks left by a crash are reclaimed.

### Fixed

- Packaged builds now keep `User/`, `Cache/` and `Logs/` beside the executable
  instead of trusting the process working directory. Launching the `.exe` from
  a shortcut or from a read-only directory used to abort startup with
  `[WinError 5] Access is denied: 'Logs'`.
- File logging falls back to console output when the log directory cannot be
  created or written, so a logging problem can never block the UI.
- yt-dlp updates now verify downloads against the published `SHA2-256SUMS`
  asset when a per-asset `.sha256` sidecar is unavailable, instead of accepting
  the payload on its size alone.

## [1.0.0] — 2026-10-24

First production release. Feature-complete for the planned scope: search,
playback, history, likes, playlists, profiles, settings, and local analytics,
with centralized security boundaries and a measured UI.

### Added

- **Analytics page** — per-profile watch time, videos played, rewatches, and the
  five most-watched channels. Totals are derived from `VideoStartedEvent` /
  `VideoStoppedEvent`, stored in `analytics.json`, refreshed live after playback,
  and can be reset with confirmation. Nothing leaves the device.
- `AnalyticsService` (14th service), subscribed to playback events with
  thread-safe aggregation, bounded channel/video maps, and load-time repair.
- `VideoStoppedEvent` now carries `video_id`, `position`, and `duration`.
- `tests/test_analytics_service.py` (14 tests) and `tests/test_analytics_page.py`
  (16 cases), plus analytics in the application bootstrap checks.
- `CHANGELOG.md`, release checklist in `BUILD.md`, and a production release
  section in `PROJECT_MEMORY.md`.
- `--version` and `--self-test` entry points (introduced in 0.9.0, verified for
  the packaged onefile executable in this release).

### Changed

- Version bumped to **1.0.0**.
- `Build` documentation now describes the actual onefile output
  (`dist/youtube_video_player.exe`) and the bundled `d3dcompiler_43.dll`.
- README, architecture diagram, service table, project structure, and test
  baseline (542 tests, 78.6% coverage) updated for 1.0.
- Analytics statistics are intentionally **not** part of the export/import
  bundle; totals are installation-local and `DATA_SCHEMA_VERSION` stays at 1.

### Removed

- Unused `cli.py` and the `plugins/` package (never imported or instantiated).
- Unused `services/database_service.py` and `services/migration_service.py`.
- Their packaging (`pyproject.toml`) and CI (`compileall`) references.

### Fixed

- Analytics previously displayed only zeros because `record_playback()` had no
  caller; the page is now wired end-to-end.
- Analytics channel rows are created once and reused instead of rebuilt on every
  refresh, avoiding widget churn and a Qt teardown crash under coverage.
- The playback monitor no longer logs a full traceback when MPV reports
  `property unavailable` while a file is still loading. That response is now a
  dedicated `MpvPropertyUnavailableError` and is treated as "not ready yet", so
  the monitor keeps polling silently instead of flooding `app.log`.

### Security

- Thumbnail fetches are restricted to a YouTube image-host allowlist with
  manually re-validated redirects, `image/*` responses, and a 5 MiB cap.
- yt-dlp always runs with `--ignore-config`, `--no-playlist`, closed stdin, and
  never resolves its executable from the working directory.
- Logs redact signed URL queries, tokens, credentials, and control characters.
- Avatars must be plain local files and are copied atomically with private modes.
- Local data is not encrypted at rest; isolation relies on per-profile
  directories, OS ACLs, and private file modes.

### Verification

- 542 passed, 1 skipped (POSIX-only permission test on Windows); 78.6% coverage.
- Ruff clean; `compileall` clean; `--version` and `--self-test` exit 0.
- Live 8-page UI smoke test and home-feed probe pass with real profile data.
- `python build.py` produces `dist/youtube_video_player.exe` (~107 MB); the
  packaged `--self-test` exits 0 and the archive contains no `User/`, `Cache/`,
  or `Logs/` entries.

## [0.9.0] — 2026-10-23

Production baseline (Milestone 1): pinned dependencies, pytest + coverage +
Ruff, Windows CI, `--version`/`--self-test`, and bootstrap tests.

### Added

- Milestones 2–7 delivered after the 0.9.0 baseline:
  - **Core correctness (M2)** — thread-safe EventBus with subscription tokens,
    atomic `JsonStore` persistence with `.bak` recovery and corruption
    quarantine, opaque profile directories, keyed lazy page navigation.
  - **Playback reliability (M3)** — `yt-dlp -g` resolution to direct video and
    optional DASH audio URLs, async `PlaybackService` with newest-request-wins
    cancellation, unique MPV named pipe per playback, EOF/crash monitoring,
    cached position/duration/pause state, working seek/volume controls.
  - **Data, profiles & settings (M4)** — centralized validation/coercion,
    repair-on-load for settings/history/likes/playlists/profiles,
    copy-then-save-then-commit mutations, versioned export/import bundles.
  - **UI/UX (M5)** — focus-aware keyboard filter, real Liked Videos page,
    playlist playback fixes, like/watch-later markers, application-wide theme,
    window geometry persistence, generation-safe status messages.
  - **Security hardening (M6)** — `core/security.py` boundaries, thumbnail
    allowlist and download limits, yt-dlp config isolation, log redaction,
    safe avatar copies; removed the unreachable `EncryptionService` and the
    `cryptography` dependency.
  - **Performance (M7)** — cached SVG icons, theme-based card styling, on-demand
    hover shadows, shared decoded-thumbnail pixmaps, batched row population,
    and `tools/benchmark_perf.py` (card construction 1.76 → 0.62 ms).

[1.0.0]: https://github.com/raoufLR/YouTube-MPV-Player/releases/tag/v1.0.0
[0.9.0]: https://github.com/raoufLR/YouTube-MPV-Player/releases/tag/v0.9.0
