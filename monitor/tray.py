"""System tray icon: dynamic badge, hover tooltip, click & menu actions."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import icon, plan as plan_mod, theme as theme_mod
from .aggregator import Snapshot
from .icon import abbrev


class TrayController(QObject):
    toggle_widget = Signal()
    request_refresh = Signal()
    request_reset = Signal()
    request_reset_position = Signal()
    request_pause = Signal(bool)
    request_quit = Signal()
    update_frequency_changed = Signal(int)
    plan_changed = Signal(str)
    theme_changed = Signal(str)
    follow_claude_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._settings = QSettings("panohopper", "TokenMonitor")
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(icon.render(0, None))
        self.tray.setToolTip("Token Monitor")
        self.tray.activated.connect(self._on_activated)

        menu = QMenu()
        act_refresh = QAction("Refresh now", menu)
        act_refresh.triggered.connect(self.request_refresh.emit)
        menu.addAction(act_refresh)

        freq_menu = menu.addMenu("Update frequency")
        for label, secs in (("1 s", 1), ("5 s", 5), ("15 s", 15)):
            a = QAction(label, freq_menu)
            a.triggered.connect(lambda _checked=False, s=secs:
                                self.update_frequency_changed.emit(s))
            freq_menu.addAction(a)

        act_reset = QAction("Reset session counter", menu)
        act_reset.triggered.connect(self.request_reset.emit)
        menu.addAction(act_reset)

        act_reset_pos = QAction("Reset widget position", menu)
        act_reset_pos.triggered.connect(self.request_reset_position.emit)
        menu.addAction(act_reset_pos)

        act_open_log = QAction("Open coworker log", menu)
        act_open_log.triggered.connect(self._open_log)
        menu.addAction(act_open_log)

        plan_menu = menu.addMenu("Plan")
        plan_group = QActionGroup(plan_menu)
        plan_group.setExclusive(True)
        current_plan_key = str(self._settings.value("plan", plan_mod.DEFAULT_KEY))
        for key, p in plan_mod.PLANS.items():
            a = QAction(p.label, plan_menu)
            a.setCheckable(True)
            a.setChecked(key == current_plan_key)
            a.triggered.connect(lambda _checked=False, k=key: self._set_plan(k))
            plan_group.addAction(a)
            plan_menu.addAction(a)

        theme_menu = menu.addMenu("Theme")
        theme_group = QActionGroup(theme_menu)
        theme_group.setExclusive(True)
        current_theme_key = str(self._settings.value("theme", theme_mod.DEFAULT_KEY))
        for key, label in (("system", "System"), ("light", "Light"), ("dark", "Dark")):
            a = QAction(label, theme_menu)
            a.setCheckable(True)
            a.setChecked(key == current_theme_key)
            a.triggered.connect(lambda _checked=False, k=key: self._set_theme(k))
            theme_group.addAction(a)
            theme_menu.addAction(a)

        act_pause = QAction("Pause polling", menu)
        act_pause.setCheckable(True)
        act_pause.toggled.connect(self.request_pause.emit)
        menu.addAction(act_pause)

        act_follow = QAction("Show only with Claude focused", menu)
        act_follow.setCheckable(True)
        act_follow.setChecked(bool(self._settings.value(
            "widget/follow_claude", True, type=bool)))
        act_follow.toggled.connect(self._set_follow_claude)
        menu.addAction(act_follow)

        menu.addSeparator()

        act_startup = QAction("Start with Windows", menu)
        act_startup.setCheckable(True)
        act_startup.setChecked(_startup_enabled())
        act_startup.toggled.connect(_set_startup_enabled)
        menu.addAction(act_startup)

        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(self.request_quit.emit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_widget.emit()

    def _set_plan(self, key: str) -> None:
        self._settings.setValue("plan", key)
        self.plan_changed.emit(key)

    def _set_theme(self, key: str) -> None:
        self._settings.setValue("theme", key)
        self.theme_changed.emit(key)

    def _set_follow_claude(self, on: bool) -> None:
        self._settings.setValue("widget/follow_claude", on)
        self.follow_claude_changed.emit(on)

    def update_snapshot(self, snap: Snapshot) -> None:
        pct = None
        if snap.quota and snap.quota.five_hour:
            pct = snap.quota.five_hour.used_pct
        self.tray.setIcon(icon.render(snap.claude_total_tokens, pct))
        plan = plan_mod.get(self._settings.value("plan", plan_mod.DEFAULT_KEY))
        self.tray.setToolTip(_format_tooltip(snap, plan))

    def _open_log(self) -> None:
        path = pathlib.Path.home() / ".claude" / "coworker-tokens.jsonl"
        if not path.exists():
            return
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError:
            pass


def _format_tooltip(snap: Snapshot, plan) -> str:
    lines: list[str] = [f"Plan:       {plan.label}"]

    if snap.quota and snap.quota.five_hour:
        lines.append(f"Claude 5h:  {snap.quota.five_hour.used_pct:5.1f}% (Anthropic)")
    else:
        lines.append(f"Claude 5h:  {snap.claude_5h_tokens:,} tok (local estimate)")
    if snap.quota and snap.quota.seven_day:
        lines.append(f"Claude 7d:  {snap.quota.seven_day.used_pct:5.1f}% (Anthropic)")
    else:
        lines.append(f"Claude 7d:  {snap.claude_7d_tokens:,} tok (local estimate)")

    if plan_mod.is_subscription(plan):
        lines.append(
            f"Session:    {snap.claude_total_tokens:,} tok  "
            f"(API value ≈ ${snap.claude_cost_usd:.2f})"
        )
    else:
        lines.append(
            f"Session:    {snap.claude_total_tokens:,} tok  "
            f"≈ ${snap.claude_cost_usd:.2f}"
        )
    if snap.worker_total_in or snap.worker_total_out:
        provider = snap.worker_provider_label or "worker"
        c = snap.worker_cost_usd
        cost_str = f"${c:.4f}" if c >= 0.0001 else "≈ $0.00"
        lines.append(
            f"Worker:     {(snap.worker_total_in + snap.worker_total_out):,} tok  "
            f"({provider}, off Claude quota)"
        )
        lines.append(
            f"Worker $:   {cost_str}  (list price × tokens)"
        )
    if snap.last_turn_in or snap.last_turn_out:
        lines.append(
            f"Last turn:  {abbrev(snap.last_turn_in)} in / {abbrev(snap.last_turn_out)} out"
        )
    return "\n".join(lines)


# --- Start with Windows ---------------------------------------------------

_STARTUP_DIR = pathlib.Path(os.environ.get("APPDATA", "")) / (
    "Microsoft/Windows/Start Menu/Programs/Startup"
)
_STARTUP_LINK = _STARTUP_DIR / "TokenMonitor.lnk"


def _startup_enabled() -> bool:
    return _STARTUP_LINK.exists()


def _set_startup_enabled(enabled: bool) -> None:
    if enabled:
        _create_startup_shortcut()
    else:
        try:
            _STARTUP_LINK.unlink(missing_ok=True)
        except OSError:
            pass


def _create_startup_shortcut() -> None:
    pythonw = pathlib.Path(sys.executable).with_name("pythonw.exe")
    target = str(pythonw if pythonw.exists() else sys.executable)
    args = "-m monitor"
    workdir = str(pathlib.Path(__file__).resolve().parent.parent)
    ps = (
        "$WshShell = New-Object -ComObject WScript.Shell;"
        f"$lnk = $WshShell.CreateShortcut('{_STARTUP_LINK}');"
        f"$lnk.TargetPath = '{target}';"
        f"$lnk.Arguments = '{args}';"
        f"$lnk.WorkingDirectory = '{workdir}';"
        "$lnk.Save()"
    )
    try:
        _STARTUP_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            check=False, capture_output=True,
        )
    except OSError:
        pass
