"""Analytics page.

Shows the active profile's local playback statistics: total watch time, plays,
rewatches, and the channels watched most.  All numbers come from
:class:`services.analytics_service.AnalyticsService`; nothing leaves the
device.  The page refreshes itself whenever a playback ends and whenever it is
shown again.
"""

from __future__ import annotations

import contextlib

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.events import EVENT_VIDEO_STOPPED
from services.analytics_service import TOP_CHANNEL_LIMIT
from ui.event_dispatcher import QtEventDispatcher
from ui.i18n import tr, trn

_MAX_CHANNEL_CHARS = 26


def format_watch_time(seconds: float) -> str:
    """Format a duration in seconds for a stat card (``0m``, ``<1m``, ``2h 05m``)."""
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        total = 0
    if total <= 0:
        return tr("0m")
    if total < 60:
        return tr("<1m")
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return tr("{hours}h {minutes:02d}m").format(hours=hours, minutes=minutes)
    if hours:
        return tr("{hours}h").format(hours=hours)
    return tr("{minutes}m").format(minutes=minutes)


def _shorten(text: str, limit: int = _MAX_CHANNEL_CHARS) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


class _StatCard(QWidget):
    """A single value/caption tile."""

    def __init__(self, caption: str, parent=None):
        super().__init__(parent)
        self.setObjectName("analyticsCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(4)

        self._value = QLabel("—")
        self._value.setObjectName("statValue")
        layout.addWidget(self._value)

        label = QLabel(caption)
        label.setObjectName("statLabel")
        layout.addWidget(label)

    def set_value(self, text: str, tooltip: str = ""):
        self._value.setText(text)
        self._value.setToolTip(tooltip)


class AnalyticsPage(QWidget):
    """Local playback statistics for the active profile."""

    def __init__(self, analytics_service, event_bus=None, parent=None):
        super().__init__(parent)
        self._analytics = analytics_service
        self._event_bus = event_bus
        self._subscriptions = []

        self._setup_ui()
        self._connect_events()
        self.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel(tr("Analytics"))
        title.setObjectName("pageTitle")
        header.addWidget(title)
        header.addStretch()

        self._reset_button = QPushButton(tr("Reset statistics"))
        self._reset_button.setToolTip(tr("Delete the statistics stored for this profile"))
        self._reset_button.clicked.connect(self._on_reset_clicked)
        header.addWidget(self._reset_button)
        layout.addLayout(header)

        subtitle = QLabel(
            tr("Local playback statistics for this profile — nothing is uploaded.")
        )
        subtitle.setObjectName("pageSubtitle")
        layout.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self._watch_card = _StatCard(tr("Watch time"))
        self._plays_card = _StatCard(tr("Videos played"))
        self._rewatch_card = _StatCard(tr("Rewatches"))
        self._channel_card = _StatCard(tr("Top channel"))
        for card in (
            self._watch_card,
            self._plays_card,
            self._rewatch_card,
            self._channel_card,
        ):
            cards.addWidget(card, 1)
        layout.addLayout(cards)

        channels_title = QLabel(tr("Most watched channels"))
        channels_title.setObjectName("sectionTitle")
        layout.addWidget(channels_title)

        self._channels_box = QVBoxLayout()
        self._channels_box.setSpacing(6)
        layout.addLayout(self._channels_box)

        # Rows are created once and reused: rebuilding the section on every
        # refresh would churn widgets (and stack deferred deletions).
        self._channel_rows = []
        for _ in range(TOP_CHANNEL_LIMIT):
            row = QWidget()
            row.setObjectName("analyticsChannelRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)

            name_label = QLabel("")
            name_label.setObjectName("analyticsChannelName")
            row_layout.addWidget(name_label)
            row_layout.addStretch()

            count_label = QLabel("")
            count_label.setObjectName("analyticsChannelCount")
            row_layout.addWidget(count_label)

            row.hide()
            self._channels_box.addWidget(row)
            self._channel_rows.append((row, name_label, count_label))

        self._empty_label = QLabel(
            tr("No playback statistics yet.\nPlay a video to start collecting them.")
        )
        self._empty_label.setObjectName("emptyState")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.hide()
        layout.addWidget(self._empty_label)
        layout.addStretch()

    def _connect_events(self):
        if self._event_bus is None:
            return
        callback = QtEventDispatcher(self._on_video_stopped)
        self._event_bus.subscribe(EVENT_VIDEO_STOPPED, callback, weak=False)
        self._subscriptions.append((EVENT_VIDEO_STOPPED, callback))

    def cleanup(self):
        """Detach from the event bus (used when pages are rebuilt)."""
        for event_type, callback in self._subscriptions:
            with contextlib.suppress(Exception):
                self._event_bus.unsubscribe(event_type, callback)
        self._subscriptions = []

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _on_video_stopped(self, event):
        self.refresh()

    def refresh(self):
        """Reload the statistics snapshot from the service."""
        stats = self._analytics.get_stats()
        watch_seconds = stats.get("watch_seconds", 0.0)

        self._watch_card.set_value(
            format_watch_time(watch_seconds),
            tr("{seconds} seconds watched").format(seconds=f"{watch_seconds:.0f}"),
        )
        self._plays_card.set_value(str(stats.get("videos_played", 0)))
        self._rewatch_card.set_value(str(stats.get("rewatches", 0)))

        top_channel = str(stats.get("top_channel", "") or "")
        self._channel_card.set_value(
            _shorten(top_channel) if top_channel else tr("N/A"),
            top_channel,
        )

        self._render_channels(stats.get("top_channels", {}))

    def _render_channels(self, channels):
        entries = list((channels or {}).items())
        for index, (row, name_label, count_label) in enumerate(self._channel_rows):
            if index >= len(entries):
                row.hide()
                continue
            name, count = entries[index]
            name_label.setText(_shorten(name, 80))
            name_label.setToolTip(str(name))
            plays = int(count)
            count_label.setText(
                trn("{count} play", "{count} plays", plays).format(count=plays)
            )
            row.show()

        self._empty_label.setVisible(not entries)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_reset_clicked(self):
        if not self._confirm_reset():
            return
        self._analytics.reset()
        self.refresh()

    def _confirm_reset(self) -> bool:
        answer = QMessageBox.question(
            self,
            tr("Reset statistics"),
            tr("Delete all playback statistics for this profile?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
