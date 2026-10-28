"""Status bar message generation handling."""

import pytest

from ui.status_bar_widget import StatusBarWidget

pytestmark = pytest.mark.qt


@pytest.fixture
def bar(qapp):
    widget = StatusBarWidget()
    yield widget
    widget.hide()


def test_timed_message_reset_is_ignored_after_newer_message(bar):
    bar.show_message("first", timeout=10)
    first_generation = bar._generation
    bar.show_message("second")

    bar._reset_if_current(first_generation)
    assert bar.current_message() == "second"


def test_current_timed_message_resets_to_ready(bar):
    bar.show_message("temporary", timeout=10)
    generation = bar._generation
    bar._reset_if_current(generation)
    assert bar.current_message() == "Ready"


def test_error_state_resets_only_while_current(bar):
    bar.show_error("boom")
    error_generation = bar._generation
    assert bar._status_label.property("error") is True

    bar.show_message("recovered")
    bar._reset_if_current(error_generation)

    assert bar.current_message() == "recovered"
    assert bar._status_label.property("error") is False


def test_show_ready_clears_error_state(bar):
    bar.show_error("boom")
    bar.show_ready()
    assert bar.current_message() == "Ready"
    assert bar._status_label.property("error") is False


def test_progress_visibility_follows_state(bar):
    bar.show_searching()
    assert bar._progress.isHidden() is False

    bar.show_playing()
    assert bar._progress.isHidden() is True

    bar.show_resolving()
    assert bar._progress.isHidden() is False

    bar.show_ready()
    assert bar._progress.isHidden() is True


def test_queue_count_uses_message(bar):
    bar.show_queue_count(3)
    assert bar.current_message() == "Queue: 3 videos"


def test_pending_reset_timer_is_owned_by_the_widget(qapp):
    from PyQt6 import sip

    widget = StatusBarWidget()
    widget.show_error("boom")
    timer = widget._reset_timer
    assert timer.isActive()
    assert timer.isSingleShot()

    sip.delete(widget)

    # A detached timer would fire after the window closed and touch deleted
    # labels, which PyQt runs as a fatal error.
    assert sip.isdeleted(timer)
