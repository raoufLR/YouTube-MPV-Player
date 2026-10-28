"""Application brand icon shipped in ``icon/``."""

import os

import pytest

from ui import app_icon

pytestmark = pytest.mark.qt


def test_icon_file_ships_with_the_project():
    assert os.path.isfile(app_icon.icon_path())


def test_app_icon_renders(qapp):
    icon = app_icon.app_icon()

    assert not icon.isNull()
    assert not icon.pixmap(64).isNull()


def test_brand_pixmap_uses_a_high_dpi_ratio(qapp):
    pixmap = app_icon.brand_pixmap(28, ratio=2.0)

    assert not pixmap.isNull()
    assert pixmap.width() == 56
    assert pixmap.deviceIndependentSize().width() == pytest.approx(28.0)
