"""Combine Claude Code and coworker token streams into a single snapshot."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import pricing
from .sources import claude_code, coworker, claude_quota, windows_5h_7d
from .sources.claude_code import SessionState, TurnUsage
from .sources.coworker import WorkerState
from .sources.claude_quota import Quota
from .sources.windows_5h_7d import FileState as _WinFileState


@dataclass
class Snapshot:
    sessions: list[SessionState] = field(default_factory=list)
    quota: Quota | None = None
    claude_total_tokens: int = 0
    claude_cost_usd: float = 0.0
    last_turn_in: int = 0
    last_turn_out: int = 0
    worker_total_in: int = 0
    worker_total_out: int = 0
    worker_cost_usd: float = 0.0
    worker_cost_known: bool = True   # False if any worker call had unknown rate
    worker_provider_label: str = ""
    savings_usd: float = 0.0
    last_worker_in: int = 0
    last_worker_out: int = 0
    claude_5h_tokens: int = 0
    claude_7d_tokens: int = 0
    worker_5h_tokens: int = 0
    worker_7d_tokens: int = 0
    saved_tokens: int = 0


def _session_started(s: SessionState) -> datetime | None:
    if not s.started_ts:
        return None
    raw = s.started_ts.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def build_snapshot(
    cc_sessions: list[SessionState],
    worker: WorkerState,
    quota: Quota | None,
) -> Snapshot:
    snap = Snapshot(sessions=cc_sessions, quota=quota)

    # Claude Code aggregate across active sessions.
    last_turn: TurnUsage | None = None
    last_turn_session: SessionState | None = None
    for s in cc_sessions:
        t = s.total
        snap.claude_total_tokens += t.total()
        snap.claude_cost_usd += pricing.claude_cost(
            t.model, t.input_tokens, t.output_tokens, t.cache_read, t.cache_write
        )
        if s.last_turn.total() > 0 and (
            last_turn is None or s.transcript_path.stat().st_mtime
            >= last_turn_session.transcript_path.stat().st_mtime  # type: ignore[union-attr]
        ):
            last_turn = s.last_turn
            last_turn_session = s
    if last_turn:
        snap.last_turn_in = last_turn.input_tokens + last_turn.cache_read + last_turn.cache_write
        snap.last_turn_out = last_turn.output_tokens

    # Worker entries since the *earliest* active session start (otherwise:
    # everything in the log).
    earliest: datetime | None = None
    for s in cc_sessions:
        started = _session_started(s)
        if started and (earliest is None or started < earliest):
            earliest = started

    relevant = coworker.entries_since(worker, earliest)
    counterfactual_model = (
        last_turn.model if last_turn and last_turn.model else pricing.DEFAULT_CLAUDE_MODEL
    )
    for e in relevant:
        snap.worker_total_in += e.prompt_tokens
        snap.worker_total_out += e.completion_tokens
        wc = pricing.worker_cost(
            e.provider, e.prompt_tokens, e.completion_tokens,
            e.cached_tokens, e.base_url,
        )
        if wc is None:
            snap.worker_cost_known = False
        else:
            snap.worker_cost_usd += wc
            cf = pricing.counterfactual_claude_cost(
                counterfactual_model, e.prompt_tokens, e.completion_tokens
            )
            snap.savings_usd += cf - wc
    if relevant:
        snap.worker_provider_label = relevant[-1].provider
        snap.last_worker_in = relevant[-1].prompt_tokens
        snap.last_worker_out = relevant[-1].completion_tokens

    return snap


@dataclass
class Aggregator:
    """Holds long-lived state across polling ticks."""
    cc_sessions: dict[str, SessionState] = field(default_factory=dict)
    worker_state: WorkerState = field(default_factory=WorkerState)
    quota: Quota | None = None
    last_quota_fetch: float = 0.0
    # Each fetch costs ~1 output token via /v1/messages, so don't poll quickly.
    quota_refresh_seconds: float = 300.0
    window_cache: dict = field(default_factory=dict)

    def tick(self) -> Snapshot:
        now_ts = time.time()
        # Discover sessions (may add new ones, drop stale).
        live = claude_code.discover_active_sessions(now_ts)
        live_ids = set()
        for s in live:
            live_ids.add(s.session_id)
            existing = self.cc_sessions.get(s.session_id)
            if existing is None:
                claude_code.seed_session(s)
                self.cc_sessions[s.session_id] = s
            else:
                claude_code.update_session(existing)
        for sid in list(self.cc_sessions):
            if sid not in live_ids:
                self.cc_sessions.pop(sid, None)

        coworker.update(self.worker_state)

        if now_ts - self.last_quota_fetch > self.quota_refresh_seconds:
            self.quota = claude_quota.fetch()
            self.last_quota_fetch = now_ts

        snap = build_snapshot(
            list(self.cc_sessions.values()),
            self.worker_state,
            self.quota,
        )

        win = windows_5h_7d.update_and_compute(now_ts, self.window_cache)
        snap.claude_5h_tokens = win.five_hour_tokens
        snap.claude_7d_tokens = win.seven_day_tokens
        wwin = windows_5h_7d.worker_window_tokens(self.worker_state.entries, now_ts)
        snap.worker_5h_tokens = wwin.five_hour_tokens
        snap.worker_7d_tokens = wwin.seven_day_tokens
        # "Saved tokens" = worker tokens (i.e. work that didn't burn Claude quota).
        snap.saved_tokens = snap.worker_total_in + snap.worker_total_out
        return snap
