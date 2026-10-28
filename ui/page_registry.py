"""Key-based navigation for the main window's stacked pages.

Pages are registered with stable string keys and lazy factories.  Navigation
never depends on widget creation order or on hard-coded stack indices.
"""

from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtWidgets import QStackedWidget, QWidget

PageFactory = Callable[[], QWidget]


class PageRegistry:
    """Manage a :class:`QStackedWidget` as a keyed, lazily populated page set."""

    def __init__(self, stack: QStackedWidget):
        if stack is None:
            raise ValueError("PageRegistry requires a QStackedWidget")
        self._stack = stack
        self._factories: dict[str, PageFactory] = {}
        self._pages: dict[str, QWidget] = {}
        self._order: list[str] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, key: str, factory: PageFactory, *, eager: bool = False
    ) -> QWidget | None:
        """Register *factory* under *key*.  Returns the page when ``eager``."""
        if not isinstance(key, str) or not key:
            raise ValueError("Page key must be a non-empty string")
        if not callable(factory):
            raise TypeError("Page factory must be callable")
        if key in self._factories:
            raise KeyError(f"Page '{key}' is already registered")
        self._factories[key] = factory
        self._order.append(key)
        if eager:
            return self.ensure(key)
        return None

    def register_many(self, pages, *, eager: bool = False):
        for key, factory in pages:
            self.register(key, factory, eager=eager)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def ensure(self, key: str) -> QWidget:
        """Create and add the page for *key* if it does not exist yet."""
        page = self._pages.get(key)
        if page is not None:
            return page
        try:
            factory = self._factories[key]
        except KeyError:
            raise KeyError(f"Unknown page key: {key!r}") from None
        page = factory()
        if not isinstance(page, QWidget):
            raise TypeError(
                f"Page factory for '{key}' returned {type(page).__name__}, "
                "expected QWidget"
            )
        self._pages[key] = page
        self._stack.addWidget(page)
        return page

    def show(self, key: str) -> QWidget:
        """Ensure the page exists and make it the current page."""
        page = self.ensure(key)
        self._stack.setCurrentWidget(page)
        return page

    def get(self, key: str) -> QWidget | None:
        """Return an already-created page without instantiating it."""
        return self._pages.get(key)

    def is_created(self, key: str) -> bool:
        return key in self._pages

    def current_key(self) -> str | None:
        current = self._stack.currentWidget()
        for key, page in self._pages.items():
            if page is current:
                return key
        return None

    def next_key(self, step: int = 1) -> str | None:
        if not self._order:
            return None
        current = self.current_key()
        if current in self._order:
            index = (self._order.index(current) + step) % len(self._order)
        else:
            index = 0 if step >= 0 else len(self._order) - 1
        return self._order[index]

    def previous_key(self) -> str | None:
        return self.next_key(-1)

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def clear(self) -> list[QWidget]:
        """Remove all pages and factories, returning created widgets.

        Callers are responsible for calling page ``cleanup()`` and
        ``deleteLater()`` on the returned widgets.
        """
        pages = list(self._pages.values())
        for page in pages:
            self._stack.removeWidget(page)
        self._pages.clear()
        self._factories.clear()
        self._order.clear()
        return pages

    def keys(self) -> list[str]:
        return list(self._order)

    def __contains__(self, key: str) -> bool:
        return key in self._factories

    def __len__(self) -> int:
        return len(self._order)
