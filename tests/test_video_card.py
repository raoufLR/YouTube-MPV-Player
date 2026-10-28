"""Video card state, id handling, and playback badges."""

import pytest
from PyQt6.QtGui import QPixmap

from ui.components.video_card import VideoCard, extract_video_id

pytestmark = pytest.mark.qt


@pytest.mark.parametrize(
    "data,expected",
    [
        ({"videoId": "abc"}, "abc"),
        ({"video_id": "def"}, "def"),
        ({"id": "ghi"}, "ghi"),
        ({"videoId": "", "video_id": "xyz"}, "xyz"),
        ({}, ""),
        (None, ""),
    ],
)
def test_extract_video_id_accepts_every_spelling(data, expected):
    assert extract_video_id(data) == expected


def test_card_uses_video_id_from_playlist_entries(qapp):
    card = VideoCard({"video_id": "playlist1", "title": "Title"})
    assert card.video_id() == "playlist1"


def test_card_like_state_controls_button(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    card.set_liked(True)
    assert card.is_liked() is True
    assert card._like_btn.isChecked() is True
    assert card._like_btn.toolTip() == "Unlike"

    card.set_liked(False)
    assert card.is_liked() is False
    assert card._like_btn.isChecked() is False
    assert card._like_btn.toolTip() == "Like"


def test_card_watch_later_state_controls_button(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    card.set_watch_later(True)
    assert card.is_watch_later() is True
    assert card._wl_btn.toolTip() == "Remove from Watch Later"

    card.set_watch_later(False)
    assert card.is_watch_later() is False
    assert card._wl_btn.toolTip() == "Watch Later"


def test_card_like_and_watch_later_buttons_emit(qapp):
    data = {"videoId": "v1", "title": "T"}
    card = VideoCard(data)
    likes = []
    watch_later = []
    plays = []
    card.like_toggled.connect(likes.append)
    card.watch_later_toggled.connect(watch_later.append)
    card.play_requested.connect(lambda vid, q, d: plays.append((vid, d)))

    card._like_btn.click()
    card._wl_btn.click()
    card._play_btn.click()

    assert likes == [data]
    assert watch_later == [data]
    assert plays == [("v1", data)]


def test_playback_state_badge(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    assert card._status_label.isHidden() is True

    card.set_playback_state(resolving=True)
    assert card._status_label.isHidden() is False
    assert "Resolving" in card._status_label.text()

    card.set_playback_state(playing=True)
    assert "Playing" in card._status_label.text()

    card.set_playback_state()
    assert card._status_label.isHidden() is True


def test_set_thumbnail_scales_pixmap(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    pixmap = QPixmap(64, 48)
    pixmap.fill()
    card.set_thumbnail(pixmap)
    shown = card._thumbnail_label.pixmap()
    assert not shown.isNull()
    # Cover-scaling fills the label width and crops overflow vertically.
    assert shown.width() == VideoCard.THUMBNAIL_WIDTH
    assert shown.height() >= VideoCard.THUMBNAIL_HEIGHT


def test_set_thumbnail_ignores_null_pixmap(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    card.set_thumbnail(QPixmap())
    assert card._thumbnail_label.pixmap().isNull()


def test_hover_shadow_is_created_lazily(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    # No graphics effect until the card is hovered: effects force offscreen
    # rendering and cost memory on every card in a long row.
    assert card._shadow is None
    assert card._anim is None
    assert card.graphicsEffect() is None

    card._setup_hover_effect()
    assert card._shadow is not None
    assert card.graphicsEffect() is card._shadow
    assert card._shadow.blurRadius() == 0


def test_hover_setup_is_idempotent(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    card._setup_hover_effect()
    shadow = card._shadow
    card._setup_hover_effect()
    assert card._shadow is shadow
    assert card.graphicsEffect() is shadow


def test_idle_card_releases_its_shadow(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    card._setup_hover_effect()
    card._release_hover_effect()
    assert card._shadow is None
    assert card._anim is None
    assert card.graphicsEffect() is None


def test_leave_event_without_shadow_is_safe(qapp):
    from PyQt6.QtCore import QEvent

    card = VideoCard({"videoId": "v1", "title": "T"})
    card.leaveEvent(QEvent(QEvent.Type.Leave))
    assert card._shadow is None


def test_repeated_set_liked_does_not_touch_the_button(qapp):
    card = VideoCard({"videoId": "v1", "title": "T"})
    calls = []
    original = card._like_btn.setIcon
    card._like_btn.setIcon = lambda icon: calls.append(icon) or original(icon)
    card.set_liked(False)  # already the initial state
    assert calls == []
    card.set_liked(True)
    assert len(calls) == 1
