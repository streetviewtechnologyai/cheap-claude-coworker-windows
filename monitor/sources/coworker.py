"""Tail ~/.claude/coworker-tokens.jsonl and bucket entries by timestamp."""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

LOG_PATH = pathlib.Path.home() / ".claude" / "coworker-tokens.jsonl"


@dataclass
class WorkerEntry:
    ts: datetime
    tool: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    base_url: str = ""


@dataclass
class WorkerState:
    last_offset: int = 0
    entries: list[WorkerEntry] = field(default_factory=list)


def _parse(line: str) -> WorkerEntry | None:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    ts_raw = str(obj.get("ts", "") or "")
    try:
        ts = datetime.strptime(ts_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return WorkerEntry(
        ts=ts,
        tool=str(obj.get("tool", "")),
        provider=str(obj.get("provider", "")),
        model=str(obj.get("model", "")),
        prompt_tokens=int(obj.get("prompt_tokens", 0) or 0),
        completion_tokens=int(obj.get("completion_tokens", 0) or 0),
        cached_tokens=int(obj.get("cached_tokens", 0) or 0),
        base_url=str(obj.get("base_url", "")),
    )


def update(state: WorkerState) -> bool:
    if not LOG_PATH.exists():
        return False
    try:
        size = LOG_PATH.stat().st_size
    except OSError:
        return False
    if size < state.last_offset:
        # File was truncated/rotated.
        state.last_offset = 0
        state.entries.clear()
    if size == state.last_offset:
        return False
    try:
        with LOG_PATH.open("rb") as f:
            f.seek(state.last_offset)
            chunk = f.read(size - state.last_offset)
            state.last_offset = size
    except OSError:
        return False
    added = False
    for raw in chunk.splitlines():
        if not raw.strip():
            continue
        entry = _parse(raw.decode("utf-8", errors="replace"))
        if entry is None:
            continue
        state.entries.append(entry)
        added = True
    return added


def entries_since(state: WorkerState, since: datetime | None) -> list[WorkerEntry]:
    if since is None:
        return list(state.entries)
    return [e for e in state.entries if e.ts >= since]
