"""Performance benchmark harness for the UI building blocks.

The player builds a home page out of seven rows of ten :class:`VideoCard`
instances, each with four SVG icons and an inline stylesheet.  This script
measures those paths (plus the thumbnail disk cache and the JSON store) on
synthetic data so performance work can be validated instead of guessed.

Usage::

    python tools/benchmark_perf.py                 # human readable table
    python tools/benchmark_perf.py --json out.json # machine readable results

The benchmark runs with the offscreen Qt platform by default, so it never
opens a window and can run in CI.  Timings are the median of ``--runs``
samples after one warm-up run; the first (cold) sample is not reported.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

CARD_COUNT = 10
SECTION_COUNT = 7
ICONS_PER_CARD = 4
THUMBNAIL_COUNT = 70
THUMBNAIL_BYTES = 40 * 1024


def _videos(count: int, prefix: str = "vid") -> list:
    return [
        {
            "videoId": f"{prefix}{index:04d}",
            "title": f"Benchmark video {index} with a fairly long title",
            "channel": f"Channel {index % 13}",
            "thumbnail": (
                f"https://i.ytimg.com/vi/{prefix}{index:04d}/hqdefault.jpg"
            ),
            "duration": "10:00",
            "views": "1.2M views",
            "uploadDate": "2 days ago",
        }
        for index in range(count)
    ]


def _bench(name: str, description: str, ops: int, fn, runs: int) -> dict:
    """Run *fn* ``runs`` times (plus one warm-up) and record ms per op.

    ``fn`` may return a cleanup callable that runs after the timer stops, so
    widget teardown never inflates a measurement.
    """
    samples = []
    for index in range(runs + 1):
        gc.collect()
        start = time.perf_counter()
        cleanup = fn()
        elapsed = time.perf_counter() - start
        if cleanup is not None:
            cleanup()
        if index:
            samples.append(elapsed / ops * 1000.0)

    median = statistics.median(samples)
    return {
        "name": name,
        "description": description,
        "ops_per_run": ops,
        "median_ms": round(median, 4),
        "min_ms": round(min(samples), 4),
        "max_ms": round(max(samples), 4),
        "samples_ms": [round(value, 4) for value in samples],
    }


def _bench_icons(qapp, runs: int) -> dict:
    from ui import icons

    def run():
        for _ in range(SECTION_COUNT * CARD_COUNT):
            icons.play(20)
            icons.like(20)
            icons.watch_later_add(20)
            icons.more_vert(20)

    return _bench(
        "icon_render",
        "Create the four icons used by one VideoCard (280 icons)",
        SECTION_COUNT * CARD_COUNT * ICONS_PER_CARD,
        run,
        runs,
    )


def _bench_card_create(qapp, runs: int) -> dict:
    from ui.components.video_card import VideoCard

    videos = _videos(SECTION_COUNT * CARD_COUNT)

    def run():
        cards = [VideoCard(video) for video in videos]

        def cleanup():
            for card in cards:
                card.deleteLater()
            qapp.processEvents()

        return cleanup

    return _bench(
        "video_card_create",
        "Construct 70 VideoCards (widgets, labels, buttons, shadow)",
        len(videos),
        run,
        runs,
    )


def _bench_section_populate(qapp, runs: int, temp_dir: str, warm: bool = False) -> dict:
    from PyQt6.QtGui import QColor, QImage, QPainter, QPixmapCache

    from services.thumbnail_cache_service import ThumbnailCacheService
    from ui.components.home_section import HomeSection

    service = ThumbnailCacheService(
        disk_cache=True, disk_dir=os.path.join(temp_dir, "row-thumbnails")
    )
    service.shutdown()

    videos = _videos(CARD_COUNT, prefix="row")
    for video in videos:
        image = QImage(480, 360, QImage.Format.Format_RGB32)
        image.fill(QColor(32, 33, 36))
        painter = QPainter(image)
        painter.fillRect(0, 0, 480, 180, QColor(60, 62, 66))
        painter.end()
        image.save(service._disk_path(video["thumbnail"]), "JPEG", 85)

    section = HomeSection("Benchmark")

    def run():
        if not warm:
            QPixmapCache.clear()
        section.set_videos(videos, thumbnail_service=service)

    return _bench(
        "home_section_populate_warm" if warm else "home_section_populate",
        "Populate one 10-card home row from decoded (warm) thumbnails"
        if warm else
        "Populate one 10-card home row, decoding thumbnails from cache bytes",
        len(videos),
        run,
        runs,
    )


def _bench_thumbnail_disk(qapp, runs: int, temp_dir: str) -> dict:
    from services.thumbnail_cache_service import ThumbnailCacheService

    service = ThumbnailCacheService(
        disk_cache=True, disk_dir=os.path.join(temp_dir, "thumbnails")
    )
    # The benchmark only exercises cache hits, so the network worker is not
    # needed (and must not run against the real cache directory).
    service.shutdown()

    urls = [
        f"https://i.ytimg.com/vi/disk{index:04d}/hqdefault.jpg"
        for index in range(THUMBNAIL_COUNT)
    ]
    for url in urls:
        with open(service._disk_path(url), "wb") as handle:
            handle.write(os.urandom(THUMBNAIL_BYTES))

    def run():
        service._memory.clear()
        for url in urls:
            service.load_thumbnail_data(url)

    return _bench(
        "thumbnail_disk_read",
        "Read 70 cached thumbnails (40 KiB each) through the public API",
        len(urls),
        run,
        runs,
    )


def _bench_event_bus(qapp, runs: int) -> dict:
    from core.event_bus import EventBus
    from core.events import ThumbnailLoadedEvent

    bus = EventBus()
    received = []
    bus.subscribe(
        "thumbnail_loaded",
        lambda event: received.append(event),
        weak=False,
    )

    def run():
        received.clear()
        for index in range(2000):
            bus.publish(ThumbnailLoadedEvent(item=str(index), icon=b""))

    return _bench(
        "event_bus_publish",
        "Publish 2000 ThumbnailLoadedEvents to one subscriber",
        2000,
        run,
        runs,
    )


def _bench_json_store(qapp, runs: int, temp_dir: str) -> dict:
    from core.json_store import JsonStore

    store = JsonStore(os.path.join(temp_dir, "bench-settings.json"))
    payload = [
        {"video_id": f"vid{index:04d}", "title": f"Video {index}"}
        for index in range(100)
    ]

    def run():
        for _ in range(10):
            store.save(payload)

    return _bench(
        "json_store_save",
        "Persist a 100-entry JSON document (atomic write + fsync)",
        10,
        run,
        runs,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5, help="samples per benchmark")
    parser.add_argument("--json", help="write results to this path")
    parser.add_argument(
        "--only",
        action="append",
        choices=[
            "icon_render",
            "video_card_create",
            "home_section_populate",
            "home_section_populate_warm",
            "thumbnail_disk_read",
            "event_bus_publish",
            "json_store_save",
        ],
        help="run only the named benchmark (repeatable)",
    )
    args = parser.parse_args(argv)

    from PyQt6.QtWidgets import QApplication

    qapp = QApplication.instance() or QApplication([])

    # Mirror the real application: card styling lives in the theme
    # stylesheet, not in per-widget inline styles.
    from ui.themes.theme_manager import ThemeManager

    qapp.setStyleSheet(ThemeManager().stylesheet())

    results = []
    with tempfile.TemporaryDirectory() as temp_dir:
        benchmarks = [
            ("icon_render", lambda: _bench_icons(qapp, args.runs)),
            ("video_card_create", lambda: _bench_card_create(qapp, args.runs)),
            ("home_section_populate", lambda: _bench_section_populate(qapp, args.runs, temp_dir)),
            (
                "home_section_populate_warm",
                lambda: _bench_section_populate(qapp, args.runs, temp_dir, warm=True),
            ),
            ("thumbnail_disk_read", lambda: _bench_thumbnail_disk(qapp, args.runs, temp_dir)),
            ("event_bus_publish", lambda: _bench_event_bus(qapp, args.runs)),
            ("json_store_save", lambda: _bench_json_store(qapp, args.runs, temp_dir)),
        ]
        for name, factory in benchmarks:
            if args.only and name not in args.only:
                continue
            results.append(factory())

    width = max(len(item["name"]) for item in results) if results else 10
    print(f"{'benchmark'.ljust(width)}  {'ops':>6}  {'median ms/op':>12}  {'min':>8}  {'max':>8}")
    for item in results:
        print(
            f"{item['name'].ljust(width)}  {item['ops_per_run']:>6}  "
            f"{item['median_ms']:>12.4f}  {item['min_ms']:>8.4f}  {item['max_ms']:>8.4f}"
        )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
