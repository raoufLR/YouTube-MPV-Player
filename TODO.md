# YouTube-MPV-Player — Actionable Remediation & Development Roadmap

This document outlines the actionable remediation checklist and future development roadmap derived from the 1.0.0 architecture and code audit.

---

## 🔴 1. Critical & Operational Tasks
- [x] **Continuous `yt-dlp` binary updates:** Implement a periodic check or release update process for the bundled `yt-dlp.exe` binary to ensure ongoing compatibility with YouTube API/page structure changes. *(Verification status: 17 `tests/test_ytdlp_update.py` tests + 7 `tests/test_update_settings_ui.py` UI tests passed — update status card in the Settings page with "Check now" / "Install update" buttons without touching the public event queue.)*
- [x] **Memory profiling for large collections:** Monitor memory consumption and test LRU cache eviction behavior under large history logs (up to 500 entries) and large playlists to prevent memory bloat on low-RAM systems.

---

## 🟡 2. Technical & Code Quality Tasks
- [x] **Expand `Ruff` linter rules:** Gradually expand the lint selection in `pyproject.toml` (e.g., adding `I` for import sorting and `UP` for modern Python syntax upgrades compatible with Python >= 3.14).
- [x] **UI Integration Tests:** Add mock-based integration tests covering complete playback lifecycle flows through `MainWindow` and `HomePage` to prevent future regressions.

---

## 🟢 3. UX & Feature Enhancements
- [x] **Interactive error actions:** Provide quick action buttons in the Status Bar when stream resolution fails (e.g., "Retry" or "Open in External Browser").
- [x] **Keyboard shortcuts reference:** Add a dedicated modal or help section in `SettingsPage` displaying all available keyboard shortcuts (volume control, seeking, pause/resume, etc.).
