"""Analytics page rendering, live refresh, and reset."""

import pytest

from core.events import VideoStartedEvent, VideoStoppedEvent
from services.analytics_service import AnalyticsService
from ui.pages.analytics_page import AnalyticsPage, format_watch_time

pytestmark = pytest.mark.qt


@pytest.fixture
def page(qapp, event_bus, temp_dir):
    service = AnalyticsService(event_bus=event_bus, data_dir=temp_dir)
    widget = AnalyticsPage(service, event_bus=event_bus)
    yield widget, service
    widget.cleanup()
    widget.setParent(None)
    widget.deleteLater()
    # Flush deferred deletions now: a later test applies the global stylesheet,
    # and Qt re-polishes every live widget when that happens.
    qapp.processEvents()
    service.shutdown()


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0m"),
        (0.4, "0m"),
        (30, "<1m"),
        (59, "<1m"),
        (60, "1m"),
        (3599, "59m"),
        (3600, "1h"),
        (3661, "1h 01m"),
        (7325, "2h 02m"),
        ("bad", "0m"),
    ],
)
def test_format_watch_time(seconds, expected):
    assert format_watch_time(seconds) == expected


def test_empty_state_is_shown(page):
    widget, _ = page
    assert widget._empty_label.isHidden() is False
    assert widget._watch_card._value.text() == "0m"
    assert widget._plays_card._value.text() == "0"
    assert widget._rewatch_card._value.text() == "0"
    assert widget._channel_card._value.text() == "N/A"


def test_page_renders_statistics(page):
    widget, service = page
    service.record_playback("abc123def45", 3661.0, "Chan A")
    service.record_playback("abc123def45", 60.0, "Chan A")
    service.record_playback("xyz987uvw65", 30.0, "Chan B")
    widget.refresh()

    assert widget._watch_card._value.text() == "1h 02m"
    assert widget._plays_card._value.text() == "3"
    assert widget._rewatch_card._value.text() == "1"
    assert widget._channel_card._value.text() == "Chan A"
    assert widget._empty_label.isHidden() is True
    visible = [row for row, _, _ in widget._channel_rows if not row.isHidden()]
    assert len(visible) == 2


def test_long_channel_names_are_shortened(page):
    widget, service = page
    service.record_playback("abc123def45", 60.0, "A channel name that is far too long to fit")
    widget.refresh()

    value = widget._channel_card._value.text()
    assert value.endswith("…")
    assert len(value) <= 26
    assert widget._channel_card._value.toolTip().startswith("A channel name")


def test_page_refreshes_when_playback_stops(page, qapp, event_bus):
    widget, _ = page
    assert widget._plays_card._value.text() == "0"

    event_bus.publish(VideoStartedEvent(video_id="vid1", channel="Chan"))
    event_bus.publish(VideoStoppedEvent(position=60.0, duration=120.0))
    qapp.processEvents()

    assert widget._plays_card._value.text() == "1"
    assert widget._watch_card._value.text() == "1m"


def test_reset_button_clears_statistics(page, monkeypatch):
    widget, service = page
    service.record_playback("abc123def45", 120.0, "Chan")
    widget.refresh()
    assert widget._plays_card._value.text() == "1"

    monkeypatch.setattr(widget, "_confirm_reset", lambda: True)
    widget._reset_button.click()

    assert widget._plays_card._value.text() == "0"
    assert widget._empty_label.isHidden() is False


def test_reset_button_can_be_cancelled(page, monkeypatch):
    widget, service = page
    service.record_playback("abc123def45", 120.0, "Chan")
    widget.refresh()

    monkeypatch.setattr(widget, "_confirm_reset", lambda: False)
    widget._reset_button.click()

    assert widget._plays_card._value.text() == "1"
