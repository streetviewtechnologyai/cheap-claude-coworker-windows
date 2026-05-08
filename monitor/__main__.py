"""Token monitor entry point. Usage: python -m monitor"""
from __future__ import annotations

import sys
import time

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .aggregator import Aggregator
from .foreground import foreground_exe
from .tray import TrayController
from .widget import TaskbarWidget

# Process names whose foreground state should keep the widget visible.
_FOLLOW_EXES = {"claude.exe"}
# Shell processes are *transparent*: while one is foreground we don't change
# the widget's state. This keeps the widget visible when the user clicks
# Windows' notification-area chevron with Claude already focused, and keeps
# it hidden when they click the chevron with Chrome focused.
_SHELL_EXES = {"explorer.exe", "applicationframehost.exe",
               "shellexperiencehost.exe", "startmenuexperiencehost.exe",
               "searchhost.exe", "textinputhost.exe"}
# After an explicit show, hold the widget visible for this many seconds.
_GRACE_AFTER_SHOW_S = 3.0
# How many consecutive non-Claude foreground samples before we hide. With a
# 400 ms tick this is ~800 ms of dwell, enough to ride out shell flicker.
_HIDE_AFTER_N_TICKS = 2


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[token-monitor] System tray is not available on this session.",
              file=sys.stderr)
        return 1

    settings = QSettings("panohopper", "TokenMonitor")
    interval_seconds = int(settings.value("update/interval_s", 1) or 1)
    widget_visible = bool(settings.value("widget/visible", True, type=bool))
    follow_claude = bool(settings.value("widget/follow_claude", True, type=bool))

    aggregator = Aggregator()
    tray = TrayController()
    widget = TaskbarWidget()
    if widget_visible:
        widget.show()

    paused = False

    def tick() -> None:
        if paused:
            return
        snap = aggregator.tick()
        tray.update_snapshot(snap)
        widget.update_snapshot(snap)

    timer = QTimer()
    timer.setInterval(interval_seconds * 1000)
    timer.timeout.connect(tick)
    timer.start()
    QTimer.singleShot(0, tick)

    # Foreground watcher: only show the widget when Claude (or the widget
    # itself) has focus. The widget hides during Chrome/IDE/etc.
    def check_foreground() -> None:
        if not settings.value("widget/follow_claude", True, type=bool):
            return
        if not settings.value("widget/visible", True, type=bool):
            return  # user explicitly hid it via tray click
        if time.monotonic() < grace_until[0]:
            if not widget.isVisible():
                widget.show()
            return
        # Don't hide while the tray menu is open (clicking the menu shifts
        # focus to explorer.exe and we'd flicker).
        cmenu = tray.tray.contextMenu()
        if cmenu is not None and cmenu.isVisible():
            return
        exe = foreground_exe()
        # Three-way decision:
        #  - claude / our own widget   → show
        #  - shell (explorer, hosts)   → preserve current visibility
        #  - anything else             → hide (after dwell)
        if exe in _FOLLOW_EXES or exe.startswith("python"):
            miss_count[0] = 0
            if not widget.isVisible():
                widget.show()
        elif exe in _SHELL_EXES:
            return  # transparent
        else:
            miss_count[0] += 1
            if miss_count[0] >= _HIDE_AFTER_N_TICKS and widget.isVisible():
                widget.hide()

    fg_timer = QTimer()
    fg_timer.setInterval(400)
    fg_timer.timeout.connect(check_foreground)
    fg_timer.start()

    grace_until = [0.0]  # mutable cell for closures
    miss_count = [0]

    def toggle_widget() -> None:
        if widget.isVisible():
            widget.hide()
            settings.setValue("widget/visible", False)
        else:
            widget.show()
            widget.raise_()
            settings.setValue("widget/visible", True)
            grace_until[0] = time.monotonic() + _GRACE_AFTER_SHOW_S

    def reset_session() -> None:
        aggregator.cc_sessions.clear()
        aggregator.worker_state.entries.clear()
        aggregator.worker_state.last_offset = 0
        tick()

    def set_pause(p: bool) -> None:
        nonlocal paused
        paused = p

    def set_frequency(seconds: int) -> None:
        timer.setInterval(seconds * 1000)
        settings.setValue("update/interval_s", seconds)

    tray.toggle_widget.connect(toggle_widget)
    tray.request_refresh.connect(tick)
    tray.request_reset.connect(reset_session)
    tray.request_reset_position.connect(widget.reset_position)
    tray.request_pause.connect(set_pause)
    tray.update_frequency_changed.connect(set_frequency)
    tray.plan_changed.connect(lambda _k: tick())
    tray.theme_changed.connect(lambda _k: widget.update())

    def on_follow_changed(on: bool) -> None:
        if not on and settings.value("widget/visible", True, type=bool):
            widget.show()  # show immediately when feature disabled
    tray.follow_claude_changed.connect(on_follow_changed)
    tray.request_quit.connect(app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
