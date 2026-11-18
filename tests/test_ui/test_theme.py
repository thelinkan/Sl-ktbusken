"""Theme switching must not leave the classic beige palette behind.

Regression: ``style().standardPalette()`` is the classic Windows palette
(window #d4d0c8). Applying it for the "system" and "light" themes gave a beige
window, and with Windows in dark mode the natively drawn menus, tabs and combo
boxes turned white on that beige.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from slaktbusken.app import Application

CLASSIC_BEIGE = "#d4d0c8"


def _apply(theme: str) -> None:
    # _apply_theme only uses the QApplication instance, not the Application.
    Application._apply_theme(None, theme)  # type: ignore[arg-type]


@pytest.fixture
def restore_theme(qapp: QApplication):
    original = QPalette(qapp.palette())
    yield
    _apply("system")
    qapp.setPalette(original)
    qapp.setStyleSheet("")


@pytest.mark.parametrize("theme", ["system", "light"])
def test_light_and_system_theme_do_not_use_classic_beige(
    qapp: QApplication, restore_theme, theme: str
) -> None:
    _apply(theme)
    assert qapp.palette().window().color().name() != CLASSIC_BEIGE
    assert qapp.styleSheet() == ""


def test_switching_from_dark_back_to_system_restores_the_platform_palette(
    qapp: QApplication, restore_theme
) -> None:
    _apply("system")
    before = qapp.palette().window().color().name()
    _apply("dark")
    assert qapp.palette().window().color().name() == "#353535"
    assert qapp.styleSheet() != ""
    _apply("system")
    assert qapp.palette().window().color().name() == before
    assert qapp.styleSheet() == ""


def test_dark_theme_text_is_light_on_dark(qapp: QApplication, restore_theme) -> None:
    _apply("dark")
    palette = qapp.palette()
    assert palette.windowText().color().lightness() > palette.window().color().lightness()
    assert palette.text().color().lightness() > palette.base().color().lightness()