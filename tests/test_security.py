"""Security boundary tests: URLs, local paths, log redaction, permissions."""

import logging
import os

import pytest

from core.security import (
    DEFAULT_THUMBNAIL_HOSTS,
    RedactionFilter,
    copy_private_file,
    install_redaction,
    is_safe_local_path,
    redact_text,
    redact_url,
    sanitize_local_path,
    validate_fetch_url,
)


class TestRedaction:
    def test_signed_url_query_is_redacted(self):
        result = redact_url(
            "https://i.ytimg.com/vi/x/hq.jpg?sqp=abc123&rs=AOn4CLsecret#frag"
        )
        assert result == "https://i.ytimg.com/vi/x/hq.jpg?<redacted>#<redacted>"
        assert "AOn4CLsecret" not in result

    def test_credentials_are_stripped_from_url(self):
        result = redact_url("https://user:pass@example.com/path?a=1")
        assert result == "https://example.com/path?<redacted>"
        assert "pass" not in result

    def test_non_url_text_keeps_path_only(self):
        assert redact_url("not-a-url?token=abc") == "not-a-url"

    def test_secret_parameters_are_masked(self):
        text = "token=abc123 key=secret sig=xyz password=hunter2"
        result = redact_text(text)
        assert "abc123" not in result
        assert "secret" not in result
        assert "xyz" not in result
        assert "hunter2" not in result
        assert result.count("<redacted>") == 4

    def test_bearer_tokens_are_masked(self):
        result = redact_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.secret")
        assert "eyJhbGciOiJIUzI1NiJ9.secret" not in result
        assert "<redacted>" in result

    def test_urllib3_request_line_query_is_masked(self):
        message = (
            'https://i.ytimg.com "GET /vi/x/hq720.jpg?sqp=abc123&rs=AOn4CLsecret'
            '&usqp=CBU HTTP/1.1" 200 33676'
        )
        result = redact_text(message)

        assert "abc123" not in result
        assert "AOn4CLsecret" not in result
        assert "GET /vi/x/hq720.jpg?<redacted>" in result
        assert result.endswith('HTTP/1.1" 200 33676')

    def test_request_line_without_query_is_unchanged(self):
        message = 'GET /vi/x/hq720.jpg HTTP/1.1" 200'
        assert redact_text(message) == message

    def test_absolute_url_in_request_line_is_still_redacted(self):
        result = redact_text("GET https://i.ytimg.com/a.jpg?rs=secret HTTP/1.1")
        assert "secret" not in result

    def test_control_characters_are_stripped(self):
        assert redact_text("line1\r\nline2\x00\x1b[31m") == "line1line2[31m"

    def test_text_is_truncated(self):
        result = redact_text("x" * 10_000, max_length=100)
        assert len(result) == 100
        assert result.endswith("\u2026")

    def test_filter_rewrites_record_in_place(self):
        record = logging.LogRecord(
            "test",
            logging.INFO,
            __file__,
            1,
            "fetching %s",
            ("https://i.ytimg.com/a.jpg?expire=123&sig=secret",),
            None,
        )
        RedactionFilter().filter(record)
        assert "sig=secret" not in record.getMessage()
        assert record.args == ()

    def test_install_redaction_is_idempotent(self):
        logger = logging.getLogger("test.redaction.install")
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        try:
            install_redaction(logger)
            install_redaction(logger)
            filters = [f for f in handler.filters if isinstance(f, RedactionFilter)]
            assert len(filters) == 1
        finally:
            logger.removeHandler(handler)


class TestFetchUrlValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "https://i.ytimg.com/vi/x/hq.jpg",
            "http://img.youtube.com/vi/x/0.jpg",
            "https://yt3.ggpht.com/abc",
            "https://lh3.googleusercontent.com/abc",
        ],
    )
    def test_accepts_youtube_thumbnail_hosts(self, url):
        assert validate_fetch_url(url, DEFAULT_THUMBNAIL_HOSTS) == url

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://i.ytimg.com/x.jpg",
            "file:///etc/passwd",
            "https://user:pass@i.ytimg.com/x.jpg",
            "https://i.ytimg.com:8080/x.jpg",
            "https://i.ytimg.com.evil.example/x.jpg",
            "https://evil.example/x.jpg",
            "http://127.0.0.1/x.jpg",
            "http://169.254.1.1/x.jpg",
            "http://[::1]/x.jpg",
            "http://localhost/x.jpg",
            "https://i.ytimg.com/x.jpg\n--exec=calc",
            "https://i.ytimg.com/x y.jpg",
            "https://i.ytimg.com/" + "a" * 3000,
        ],
    )
    def test_rejects_unsafe_urls(self, url):
        with pytest.raises(ValueError):
            validate_fetch_url(url, DEFAULT_THUMBNAIL_HOSTS)

    def test_allowlist_can_be_disabled_explicitly(self):
        # Empty allowlist rejects every host, including otherwise public ones.
        with pytest.raises(ValueError):
            validate_fetch_url("https://example.com/x.jpg", ())

    def test_public_host_passes_without_allowlist(self):
        assert validate_fetch_url("https://example.com/x.jpg") == (
            "https://example.com/x.jpg"
        )

    @pytest.mark.parametrize("value", ["", None, 42, "https://"])
    def test_rejects_non_urls(self, value):
        with pytest.raises(ValueError):
            validate_fetch_url(value)


class TestLocalPaths:
    @pytest.mark.parametrize(
        "path",
        [
            r"C:\Users\me\Pictures\avatar.png",
            "avatar.png",
            "User/profiles/abc/avatar.png",
            "/home/me/avatar.png",
        ],
    )
    def test_accepts_plain_local_paths(self, path):
        assert is_safe_local_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "",
            None,
            r"\\server\share\avatar.png",
            "//server/share/avatar.png",
            r"\\?\C:\Windows\avatar.png",
            "file:///C:/Windows/avatar.png",
            "https://example.com/avatar.png",
            "avatar\r\n.png",
        ],
    )
    def test_rejects_remote_or_device_paths(self, path):
        assert not is_safe_local_path(path)

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific paths")
    def test_rejects_windows_alternate_data_streams(self):
        assert not is_safe_local_path(r"C:\Users\me\avatar.png:hidden")
        assert not is_safe_local_path(r"C:relative\avatar.png")

    def test_sanitize_falls_back_to_default(self):
        assert sanitize_local_path(r"\\evil\share\x.png", "fallback") == "fallback"
        assert sanitize_local_path("avatar.png", "fallback") == "avatar.png"


class TestPrivateFiles:
    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_copy_sets_owner_only_mode(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("data", encoding="utf-8")
        destination = tmp_path / "nested" / "target.txt"

        copy_private_file(str(source), str(destination))

        assert destination.read_text(encoding="utf-8") == "data"
        assert os.stat(destination).st_mode & 0o777 == 0o600
        assert os.stat(destination.parent).st_mode & 0o777 == 0o700

    def test_copy_overwrites_atomically(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("new", encoding="utf-8")
        destination = tmp_path / "target.txt"
        destination.write_text("old", encoding="utf-8")

        copy_private_file(str(source), str(destination))

        assert destination.read_text(encoding="utf-8") == "new"
        assert not list(tmp_path.glob(".copy-*"))


class TestAvatarPathHardening:
    def test_profile_model_drops_unc_avatar(self):
        from models.profile import Profile

        profile = Profile(avatar=r"\\attacker\share\avatar.png")
        assert profile.avatar == ""

    def test_profile_model_keeps_local_avatar(self):
        from models.profile import Profile

        local = os.path.join("User", "profiles", "abc", "avatar.png")
        assert Profile(avatar=local).avatar == local

    def test_user_profile_model_drops_url_avatar(self):
        from models.user_profile import DEFAULT_AVATAR_PATH, UserProfile

        assert UserProfile(avatar_path="file:///C:/Windows/win.ini").avatar_path == (
            DEFAULT_AVATAR_PATH
        )

    def test_user_profile_import_sanitizes_avatar(self, temp_dir):
        from models.user_profile import DEFAULT_AVATAR_PATH
        from services.user_profile_service import UserProfileService

        service = UserProfileService(data_dir=temp_dir)

        assert service.import_data(
            {"username": "u", "avatar_path": r"\\attacker\share\avatar.png"}
        )
        assert service.get_profile().avatar_path == DEFAULT_AVATAR_PATH

    def test_user_manager_rejects_unc_avatar(self, temp_dir):
        from services.user_manager_service import UserManagerService

        manager = UserManagerService(base_dir=temp_dir)

        assert manager.set_profile_avatar(
            "Default", r"\\attacker\share\avatar.png"
        ) is False
        assert manager.current_profile().avatar == ""

    def test_user_profile_rejects_unc_avatar(self, temp_dir):
        from services.user_profile_service import UserProfileService

        service = UserProfileService(data_dir=temp_dir)
        before = service.get_profile().avatar_path

        assert service.set_avatar(r"\\attacker\share\avatar.png") is False
        assert service.get_profile().avatar_path == before
