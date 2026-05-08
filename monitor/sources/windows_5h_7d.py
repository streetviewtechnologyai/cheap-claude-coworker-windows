"""Compute 5h and 7d Claude token totals from transcript JSONLs.

We do this ourselves because the Anthropic OAuth usage endpoint isn't reliably
available on every plan. Strategy: walk every transcript modified in the last
8 days, tail incrementally, store (epoch_ts, tokens) per message in memory,
and aggregate by window on each tick.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .claude_code import PROJECTS_DIR

FIVE_HOUR_S = 5 * 3600
SEVEN_DAY_S = 7 * 86400
SCAN_HORIZON_S = SEVEN_DAY_S + 3600  # one extra hour of slack


@dataclass
class FileState:
    path: pathlib.Path
    last_offset: int = 0
    entries: list[tuple[float, int]] = field(default_factory=list)


@dataclass
class Windows:
    five_hour_tokens: int = 0
    seven_day_tokens: int = 0


def _parse_iso_epoch(raw: str) -> float | None:
    if not raw:
        return None
    s = raw.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return None


def _iter_recent_transcripts(now_ts: float) -> Iterable[pathlib.Path]:
    if not PROJECTS_DIR.exists():
        return
    cutoff = now_ts - SCAN_HORIZON_S
    for project in PROJECTS_DIR.iterdir():
        if not project.is_dir():
            continue
        for jl in project.glob("*.jsonl"):
            try:
                if jl.stat().st_mtime >= cutoff:
                    yield jl
            except OSError:
                continue


def update_and_compute(
    now_ts: float,
    cache: dict[pathlib.Path, FileState],
) -> Windows:
    seen: set[pathlib.Path] = set()
    for path in _iter_recent_transcripts(now_ts):
        seen.add(path)
        st = cache.get(path)
        if st is None:
            st = FileState(path=path)
            cache[path] = st
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size < st.last_offset:
            st.last_offset = 0
            st.entries.clear()
        if size > st.last_offset:
            try:
                with path.open("rb") as f:
                    f.seek(st.last_offset)
                    chunk = f.read(size - st.last_offset)
                    st.last_offset = size
            except OSError:
                continue
            for raw in chunk.splitlines():
                if not raw.strip():
                    continue
                try:
                    obj = json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message") or {}
                usage = msg.get("usage")
                if not isinstance(usage, dict):
                    continue
                ts = _parse_iso_epoch(str(obj.get("timestamp", "") or ""))
                if ts is None:
                    continue
                # Cache reads are billed ~10% and don't drive subscription
                # caps; cache creation counts as fresh input the first time.
                tokens = (
                    int(usage.get("input_tokens", 0) or 0)
                    + int(usage.get("output_tokens", 0) or 0)
                    + int(usage.get("cache_creation_input_tokens", 0) or 0)
                )
                if tokens <= 0:
                    continue
                st.entries.append((ts, tokens))

    # Drop cache entries for files that haven't been touched in 8d.
    for path in list(cache.keys()):
        if path not in seen:
            cache.pop(path, None)

    cutoff_5h = now_ts - FIVE_HOUR_S
    cutoff_7d = now_ts - SEVEN_DAY_S
    win = Windows()
    for st in cache.values():
        # Prune ancient entries to keep memory bounded.
        st.entries = [e for e in st.entries if e[0] >= cutoff_7d]
        for ts, tokens in st.entries:
            if ts >= cutoff_5h:
                win.five_hour_tokens += tokens
            win.seven_day_tokens += tokens
    return win


def worker_window_tokens(
    entries: list,  # list[WorkerEntry]
    now_ts: float,
) -> Windows:
    cutoff_5h = now_ts - FIVE_HOUR_S
    cutoff_7d = now_ts - SEVEN_DAY_S
    win = Windows()
    for e in entries:
        ts = e.ts.timestamp()
        if ts < cutoff_7d:
            continue
        tok = e.prompt_tokens + e.completion_tokens
        if ts >= cutoff_5h:
            win.five_hour_tokens += tok
        win.seven_day_tokens += tok
    return win
