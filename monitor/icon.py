"""Render the tray icon as a 32x32 PNG with a token-count badge."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap


def abbrev(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _bg_color(quota_pct: float | None) -> QColor:
    if quota_pct is None:
        return QColor(60, 60, 70)
    if quota_pct < 50:
        return QColor(30, 130, 80)
    if quota_pct < 80:
        return QColor(200, 140, 30)
    return QColor(200, 60, 60)


def render(token_total: int, quota_pct: float | None, size: int = 32) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    rect = QRectF(0.5, 0.5, size - 1, size - 1)
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.22, size * 0.22)
    p.fillPath(path, _bg_color(quota_pct))

    text = abbrev(token_total) if token_total > 0 else "0"
    font = QFont("Segoe UI", 10, QFont.Weight.Bold)
    if len(text) >= 4:
        font.setPointSize(8)
    if len(text) >= 5:
        font.setPointSize(7)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return QIcon(pix)
