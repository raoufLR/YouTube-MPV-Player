"""Thumbnail cache: fetch validation, redirects, size caps, disk layout."""

import os

import pytest

from services import thumbnail_cache_service as thumbnails
from services.thumbnail_cache_service import ThumbnailCacheService


class FakeResponse:
    def __init__(self, chunks=(b"image-bytes",), status=200, headers=None):
        self._chunks = list(chunks)
        self.status_code = status
        self.headers = headers or {
            "Content-Type": "image/jpeg",
            "Content-Length": str(sum(len(c) for c in self._chunks)),
        }
        self.closed = False

    def iter_content(self, size):
        yield from self._chunks

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"status {self.status_code}")

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)

    def close(self):
        pass


@pytest.fixture
def service():
    svc = ThumbnailCacheService(
        event_bus=None,
        disk_cache=False,
        allowed_hosts=("ytimg.com", "youtube.com"),
    )
    yield svc
    svc.shutdown()


def _use(svc, *responses):
    session = FakeSession(*responses)
    svc._http = session
    return session


class TestFetchValidation:
    def test_valid_image_is_downloaded(self, service):
        session = _use(service, FakeResponse([b"image-bytes"]))

        data = service._fetch_from_network("https://i.ytimg.com/vi/x/hq.jpg")

        assert data == b"image-bytes"
        assert session.calls[0][0] == "https://i.ytimg.com/vi/x/hq.jpg"
        assert session.calls[0][1]["stream"] is True
        assert session.calls[0][1]["allow_redirects"] is False

    def test_disallowed_host_never_reaches_the_network(self, service):
        session = _use(service)

        assert service.load_thumbnail_data("http://127.0.0.1:8080/x.jpg") is None
        assert session.calls == []
        assert service.stats()["pending"] == 0

    def test_disallowed_host_is_refused_on_direct_fetch(self, service):
        session = _use(service)

        assert service._fetch_from_network("https://evil.example/x.jpg") is None
        assert session.calls == []

    def test_non_image_content_type_is_refused(self, service):
        _use(
            service,
            FakeResponse(
                [b"<html>"],
                headers={"Content-Type": "text/html; charset=utf-8"},
            ),
        )

        assert service._fetch_from_network("https://i.ytimg.com/vi/x") is None

    def test_content_length_over_cap_is_refused(self, service):
        _use(
            service,
            FakeResponse(
                [b"x"],
                headers={
                    "Content-Type": "image/jpeg",
                    "Content-Length": str(thumbnails.MAX_THUMBNAIL_BYTES + 1),
                },
            ),
        )

        assert service._fetch_from_network("https://i.ytimg.com/vi/x") is None

    def test_streamed_body_over_cap_is_refused(self, service):
        chunk = b"x" * (thumbnails.MAX_THUMBNAIL_BYTES // 2 + 1)
        _use(
            service,
            FakeResponse(
                [chunk, chunk],
                headers={"Content-Type": "image/jpeg"},
            ),
        )

        assert service._fetch_from_network("https://i.ytimg.com/vi/x") is None

    def test_redirect_to_allowed_host_is_followed(self, service):
        session = _use(
            service,
            FakeResponse(
                headers={"Location": "https://img.youtube.com/vi/x/0.jpg"},
                status=302,
            ),
            FakeResponse([b"redirected"]),
        )

        assert service._fetch_from_network("https://i.ytimg.com/vi/x") == b"redirected"
        assert [call[0] for call in session.calls] == [
            "https://i.ytimg.com/vi/x",
            "https://img.youtube.com/vi/x/0.jpg",
        ]

    def test_redirect_to_disallowed_host_is_refused(self, service):
        session = _use(
            service,
            FakeResponse(headers={"Location": "http://127.0.0.1/x.jpg"}, status=302),
        )

        assert service._fetch_from_network("https://i.ytimg.com/vi/x") is None
        assert len(session.calls) == 1

    def test_too_many_redirects_give_up(self, service):
        redirect = FakeResponse(
            headers={"Location": "https://i.ytimg.com/next.jpg"}, status=302
        )
        _use(service, *([redirect] * (thumbnails.MAX_REDIRECTS + 1)))

        assert service._fetch_from_network("https://i.ytimg.com/vi/x") is None


class TestDiskCache:
    def test_disk_key_is_sha256_and_content_round_trips(self, tmp_path):
        svc = ThumbnailCacheService(
            event_bus=None, disk_cache=True, disk_dir=str(tmp_path)
        )
        try:
            url = "https://i.ytimg.com/vi/x/hq.jpg"
            svc._store_disk(url, b"cached")

            filename = os.path.basename(svc._disk_path(url))
            assert len(filename) == 64 + len(".jpg")
            assert filename.endswith(".jpg")
            assert all(ch in "0123456789abcdef" for ch in filename[:-4])
            assert svc._get_disk(url) == b"cached"
        finally:
            svc.shutdown()

    def test_invalid_url_is_not_cached_in_memory(self, service):
        assert service.load_thumbnail_data("file:///etc/passwd") is None
        assert service.stats()["memory"] == 0
