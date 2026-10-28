"""Central translation hook for every user-facing UI string.

Widgets call :func:`tr` on their source text (English).  With no translation
installed the source text is returned unchanged, so the default run and the
tests behave exactly as before; installing ``app_<locale>.qm`` from the
``translations`` directory is all that is needed to localise the UI later.
"""

from __future__ import annotations

import os
import sys

from PyQt6.QtCore import QCoreApplication, QLocale, QTranslator

CONTEXT = "YouTubeMPVPlayer"
_DIRECTORY = "translations"


def tr(text: str, disambiguation: str = "") -> str:
    """Return the translated *text* for the application's current locale."""
    return QCoreApplication.translate(CONTEXT, text, disambiguation)


def trn(singular: str, plural: str, count: int) -> str:
    """Translate a countable string, keeping English plural rules by default."""
    source = singular if count == 1 else plural
    return QCoreApplication.translate(CONTEXT, source, "", count)


def translations_dir() -> str:
    """Directory searched for compiled translation files."""
    bundle = getattr(sys, "_MEIPASS", None)
    base = bundle or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, _DIRECTORY)


def install_translations(app, directory: str | None = None) -> QTranslator | None:
    """Install ``app_<locale>.qm`` when present, otherwise stay in English.

    The translator is parented to *app* so it lives as long as the
    application; the caller does not need to keep a reference.
    """
    directory = directory or translations_dir()
    locale_name = QLocale.system().name()
    candidates = [f"app_{locale_name}.qm"]
    language = locale_name.split("_", 1)[0]
    if language != locale_name:
        candidates.append(f"app_{language}.qm")

    for filename in candidates:
        path = os.path.join(directory, filename)
        if not os.path.isfile(path):
            continue
        translator = QTranslator(app)
        if translator.load(path):
            app.installTranslator(translator)
            return translator
    return None
