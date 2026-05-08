"""Light / Dark theme palettes; System mode follows Windows AppsUseLightTheme."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Palette:
    bg: QColor
    border: QColor
    text: QColor
    text_muted: QColor
    bar_track: QColor
    neutral_fill: QColor


DARK = Palette(
    bg=QColor(28, 28, 32, 235),
    border=QColor(70, 70, 80),
    text=QColor(220, 220, 225),
    text_muted=QColor(180, 180, 190),
    bar_track=QColor(50, 50, 58),
    neutral_fill=QColor(110, 130, 200),
)

LIGHT = Palette(
    bg=QColor(250, 250, 252, 240),
    border=QColor(200, 200, 210),
    text=QColor(28, 28, 36),
    text_muted=QColor(95, 95, 105),
    bar_track=QColor(220, 220, 226),
    neutral_fill=QColor(60, 100, 200),
)

VALID_KEYS = ("system", "light", "dark")
DEFAULT_KEY = "system"


def _windows_is_dark() -> bool:
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as k:
            apps_light, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return apps_light == 0
    except OSError:
        return True  # default dark on failure


def resolve(key: str | None) -> Palette:
    k = (key or DEFAULT_KEY).lower()
    if k == "light":
        return LIGHT
    if k == "dark":
        return DARK
    return DARK if _windows_is_dark() else LIGHT
