"""Frameless taskbar-adjacent widget with three rows of bars/numbers."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QPoint, QRectF, QSettings
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QMouseEvent
from PySide6.QtWidgets import QWidget

from . import plan as plan_mod, theme as theme_mod
from .aggregator import Snapshot
from .icon import abbrev


def _fmt_remaining(iso_ts: str | None) -> str:
    if not iso_ts:
        return ""
    raw = iso_ts.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            target = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    else:
        return ""
    delta = target - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "now"
    days = secs // 86400
    secs %= 86400
    hours = secs // 3600
    secs %= 3600
    minutes = secs // 60
    if days:
        return f"{days}d {hours:02d}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


class TaskbarWidget(QWidget):
    HEIGHT = 78
    WIDTH = 440

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(self.WIDTH, self.HEIGHT)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        self.setToolTip("Drag to move · Right-click tray icon for menu")
        self._snap: Snapshot | None = None
        self._drag_origin: QPoint | None = None

        self._settings = QSettings("panohopper", "TokenMonitor")
        pos = self._settings.value("widget/pos")
        screen = self.screen().availableGeometry() if self.screen() else None
        if isinstance(pos, QPoint) and screen and screen.contains(pos):
            self.move(pos)
        elif screen:
            # Default: near bottom-right, but not in the very corner where
            # the Claude Code footer ("Opus 4.7 · Medium") usually sits.
            self.move(
                screen.right() - self.WIDTH - 360,
                screen.bottom() - self.HEIGHT - 80,
            )

    def reset_position(self) -> None:
        """Move the widget back to its default spot and persist."""
        self._settings.remove("widget/pos")
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            self.move(
                screen.right() - self.WIDTH - 360,
                screen.bottom() - self.HEIGHT - 80,
            )
        self.show()
        self.raise_()
        self._settings.setValue("widget/pos", self.pos())

    def update_snapshot(self, snap: Snapshot) -> None:
        self._snap = snap
        self.update()

    def mousePressEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            ev.accept()

    def mouseMoveEvent(self, ev: QMouseEvent) -> None:
        if self._drag_origin is not None and (ev.buttons() & Qt.MouseButton.LeftButton):
            self.move(ev.globalPosition().toPoint() - self._drag_origin)
            ev.accept()

    def mouseReleaseEvent(self, ev: QMouseEvent) -> None:
        if ev.button() == Qt.MouseButton.LeftButton and self._drag_origin is not None:
            self._drag_origin = None
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            self._settings.setValue("widget/pos", self.pos())

    def paintEvent(self, _ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        pal = theme_mod.resolve(self._settings.value("theme", theme_mod.DEFAULT_KEY))

        bg = QPainterPath()
        bg.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        p.fillPath(bg, pal.bg)
        p.setPen(pal.border)
        p.drawPath(bg)

        snap = self._snap
        if snap is None:
            return

        font = QFont("Segoe UI", 9)
        bold = QFont("Segoe UI", 9, QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(pal.text)

        x = 12
        bar_x = 80
        right_text_w = 170
        bar_w = self.width() - bar_x - right_text_w - 12
        y = 6

        # Prefer Anthropic's own utilization headers (authoritative, matches
        # Claude Code Desktop's display). Fall back to local token-window math
        # only when the API call hasn't returned data yet.
        rows: list[tuple[str, float | None, str]] = []
        if snap.quota and snap.quota.five_hour:
            w = snap.quota.five_hour
            rows.append(("Claude 5h", w.used_pct,
                         f"{w.used_pct:.0f}% · resets {_fmt_remaining(w.resets_at_iso)}"))
        else:
            rows.append(("Claude 5h", None, f"{abbrev(snap.claude_5h_tokens)} tok"))
        if snap.quota and snap.quota.seven_day:
            w = snap.quota.seven_day
            rows.append(("Claude 7d", w.used_pct,
                         f"{w.used_pct:.0f}% · resets {_fmt_remaining(w.resets_at_iso)}"))
        else:
            rows.append(("Claude 7d", None, f"{abbrev(snap.claude_7d_tokens)} tok"))

        scale_max = max(snap.claude_5h_tokens, snap.claude_7d_tokens, 1)
        for label, pct, txt in rows:
            p.setFont(bold)
            p.drawText(x, y + 14, label)
            p.setFont(font)
            if pct is not None:
                self._draw_bar(p, bar_x, y + 4, bar_w, 14, pct, pal=pal)
            else:
                used = snap.claude_5h_tokens if "5h" in label else snap.claude_7d_tokens
                self._draw_bar(p, bar_x, y + 4, bar_w, 14,
                               used / scale_max * 100.0, neutral=True, pal=pal)
            p.drawText(bar_x + bar_w + 8, y + 14, txt)
            y += 22

        # Worker footer line
        p.setFont(bold)
        p.setPen(pal.text_muted)
        p.drawText(x, y + 12, "Worker")
        p.setFont(font)
        worker_total = snap.worker_total_in + snap.worker_total_out
        provider = snap.worker_provider_label or "—"
        if worker_total > 0:
            cost = snap.worker_cost_usd
            if not snap.worker_cost_known:
                cost_part = "—"
            elif cost == 0:
                cost_part = "free (local)"
            elif cost < 0.01:
                cost_part = "<0.01$"
            else:
                cost_part = f"{cost:.2f}$"
            footer = (f"{abbrev(snap.worker_total_in)} tok in / "
                      f"{abbrev(snap.worker_total_out)} tok out · "
                      f"{provider} · {cost_part}")
        else:
            footer = "no calls yet"
        p.drawText(bar_x, y + 12, footer)

    @staticmethod
    def _draw_bar(p: QPainter, x: int, y: int, w: int, h: int, pct: float,
                  neutral: bool = False, pal=None) -> None:
        track = QPainterPath()
        track.addRoundedRect(QRectF(x, y, w, h), h / 2, h / 2)
        p.fillPath(track, pal.bar_track if pal else QColor(50, 50, 58))
        pct = max(0.0, min(100.0, pct))
        if pct <= 0:
            return
        fill = QPainterPath()
        fill.addRoundedRect(QRectF(x, y, w * pct / 100.0, h), h / 2, h / 2)
        if neutral:
            color = pal.neutral_fill if pal else QColor(110, 130, 200)
        elif pct < 50:
            color = QColor(60, 170, 110)
        elif pct < 80:
            color = QColor(220, 160, 50)
        else:
            color = QColor(220, 80, 80)
        p.fillPath(fill, color)
