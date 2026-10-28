"""Render ``icon/yt-mpv-icon-fusion.svg`` into a multi-size Windows ``.ico``.

Run after editing the SVG::

    python tools/make_icon.py

The result is embedded in the executable by ``youtube_video_player.spec``.
"""

from __future__ import annotations

import os
import struct
import sys

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "icon", "yt-mpv-icon-fusion.svg")
DST = os.path.join(ROOT, "icon", "yt-mpv-icon-fusion.ico")
SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    saved = image.save(buffer, "PNG")
    buffer.close()
    if not saved:
        raise RuntimeError(f"could not encode {size}x{size} PNG")
    return bytes(data)


def write_ico(images: list[tuple[int, bytes]], path: str) -> None:
    """Write a PNG-compressed ICO container (supported since Windows Vista)."""
    offset = 6 + 16 * len(images)
    entries = []
    for size, payload in images:
        # Width/height 0 encodes 256 pixels in the ICO directory.
        entries.append(
            struct.pack(
                "<BBBBHHII",
                size % 256,
                size % 256,
                0,
                0,
                1,
                32,
                len(payload),
                offset,
            )
        )
        offset += len(payload)

    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(images)))
        fh.writelines(entries)
        for _, payload in images:
            fh.write(payload)


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QGuiApplication.instance() or QGuiApplication([])

    renderer = QSvgRenderer(SRC)
    if not renderer.isValid():
        print(f"invalid SVG: {SRC}")
        return 1

    images = [(size, render_png(renderer, size)) for size in SIZES]
    write_ico(images, DST)
    print(
        f"Wrote {DST} ({os.path.getsize(DST)} bytes; "
        f"sizes: {', '.join(str(size) for size in SIZES)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
