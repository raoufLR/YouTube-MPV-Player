"""Validation rules shared by the resolver, player, and service layer."""

import pytest

from core.quality import (
    DEFAULT_QUALITY,
    QUALITY_MAP,
    ResolvedStream,
    format_selector,
    is_valid_video_id,
    normalize_quality,
    validate_stream_url,
    validate_video_id,
    watch_url,
)


class TestQualities:
    @pytest.mark.parametrize("quality", list(QUALITY_MAP))
    def test_known_qualities_round_trip(self, quality):
        assert normalize_quality(quality) == quality
        assert format_selector(quality) == QUALITY_MAP[quality]

    @pytest.mark.parametrize("quality", [None, "", "4k", 720, object()])
    def test_unknown_quality_falls_back_to_best(self, quality):
        assert normalize_quality(quality) == "best"

    def test_default_quality_is_mapped(self):
        assert DEFAULT_QUALITY in QUALITY_MAP


class TestVideoIds:
    def test_valid_ids(self):
        assert is_valid_video_id("dQw4w9WgXcQ")
        assert is_valid_video_id("abc123def45")

    @pytest.mark.parametrize("value", ["", "short", "toolongvideoid", "../etc", None, 42])
    def test_invalid_ids(self, value):
        assert not is_valid_video_id(value)
        with pytest.raises(ValueError):
            validate_video_id(value)

    def test_watch_url_rejects_injection(self):
        with pytest.raises(ValueError):
            watch_url("abc&autoplay=1")

    def test_watch_url(self):
        assert watch_url("abc123def45") == "https://www.youtube.com/watch?v=abc123def45"


class TestResolvedStream:
    def test_progressive_stream(self):
        media = ResolvedStream("https://example.com/v")
        assert media.audio_url == ""
        assert media.urls == ("https://example.com/v",)

    def test_dash_stream_exposes_both_urls(self):
        media = ResolvedStream("https://example.com/v", "https://example.com/a", "720p")
        assert media.urls == ("https://example.com/v", "https://example.com/a")
        assert media.quality == "720p"

    @pytest.mark.parametrize(
        "video_url,audio_url",
        [
            ("", ""),
            ("file:///tmp/video", ""),
            ("https://example.com/v", "javascript:alert(1)"),
            (None, ""),
        ],
    )
    def test_invalid_urls_rejected(self, video_url, audio_url):
        with pytest.raises(ValueError):
            ResolvedStream(video_url, audio_url)

    def test_stream_url_validation(self):
        assert validate_stream_url("https://example.com/v") == "https://example.com/v"
        assert validate_stream_url("ytdl://abc") == "ytdl://abc"
        with pytest.raises(ValueError):
            validate_stream_url("ftp://example.com/v")

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/v\n--script=calc",
            "https://example.com/v with space",
            "https://user:pass@example.com/v",
            "https:///missing-host",
            "https://example.com/" + "a" * 3000,
        ],
    )
    def test_stream_urls_with_control_or_credentials_are_rejected(self, url):
        with pytest.raises(ValueError):
            validate_stream_url(url)
