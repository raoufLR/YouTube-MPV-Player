"""Translation hook: source-text fallback and optional ``.qm`` installation."""

import pytest

from ui.i18n import install_translations, tr, translations_dir, trn

pytestmark = pytest.mark.qt


def test_tr_returns_source_text_without_a_translator(qapp):
    assert tr("Settings") == "Settings"


def test_trn_selects_the_matching_source_form(qapp):
    assert trn("{count} video", "{count} videos", 1).format(count=1) == "1 video"
    assert trn("{count} video", "{count} videos", 3).format(count=3) == "3 videos"


def test_install_translations_returns_none_when_no_catalog_exists(qapp, tmp_path):
    assert install_translations(qapp, str(tmp_path)) is None


def test_translations_dir_is_named_translations():
    assert translations_dir().replace("\\", "/").endswith("/translations")
