"""Watch Claude Code Desktop's transcripts for token usage.

Strategy: the most-recently-modified file under ~/.claude/sessions/<PID>.json
identifies the active session by sessionId, and we tail the matching JSONL
under ~/.claude/projects/<workspace>/<sessionId>.jsonl.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, field

CLAUDE_DIR = pathlib.Path.home() / ".claude"
SESSIONS_DIR = CLAUDE_DIR / "sessions"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# A session is considered active if its registry file changed within this window.
ACTIVE_WITHIN_SECONDS = 60 * 60 * 6


@dataclass
class TurnUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0
    model: str = ""

    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read + self.cache_write


@dataclass
class SessionState:
    session_id: str
    transcript_path: pathlib.Path
    pid: int
    workspace: str
    last_offset: int = 0
    total: TurnUsage = field(default_factory=TurnUsage)
    last_turn: TurnUsage = field(default_factory=TurnUsage)
    started_ts: str = ""  # ISO timestamp of first message in this session


def _find_transcript(session_id: str) -> pathlib.Path | None:
    if not PROJECTS_DIR.exists():
        return None
    for project in PROJECTS_DIR.iterdir():
        if not project.is_dir():
            continue
        candidate = project / f"{session_id}.jsonl"
        if candidate.exists():
            return candidate
    return None


def discover_active_sessions(now_ts: float) -> list[SessionState]:
    """Return SessionState for every recently-touched session file."""
    if not SESSIONS_DIR.exists():
        return []
    out: list[SessionState] = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            mtime = f.stat().st_mtime
        except OSError:
            continue
        if now_ts - mtime > ACTIVE_WITHIN_SECONDS:
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        sid = data.get("sessionId")
        if not sid:
            continue
        transcript = _find_transcript(sid)
        if transcript is None:
            continue
        out.append(SessionState(
            session_id=sid,
            transcript_path=transcript,
            pid=int(f.stem) if f.stem.isdigit() else 0,
            workspace=transcript.parent.name,
        ))
    out.sort(key=lambda s: s.transcript_path.stat().st_mtime, reverse=True)
    return out


def _extract_usage(line: str) -> tuple[TurnUsage | None, str]:
    """Return (usage, ts) parsed from one JSONL line. Skip lines without usage."""
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None, ""
    msg = obj.get("message") or {}
    usage = msg.get("usage")
    if not isinstance(usage, dict):
        return None, ""
    return TurnUsage(
        input_tokens=int(usage.get("input_tokens", 0) or 0),
        output_tokens=int(usage.get("output_tokens", 0) or 0),
        cache_read=int(usage.get("cache_read_input_tokens", 0) or 0),
        cache_write=int(usage.get("cache_creation_input_tokens", 0) or 0),
        model=str(msg.get("model", "") or ""),
    ), str(obj.get("timestamp", "") or "")


def update_session(state: SessionState) -> bool:
    """Read newly-appended bytes; returns True if any usage was added."""
    try:
        size = state.transcript_path.stat().st_size
    except OSError:
        return False
    if size <= state.last_offset:
        return False
    changed = False
    try:
        with state.transcript_path.open("rb") as f:
            f.seek(state.last_offset)
            chunk = f.read(size - state.last_offset)
            state.last_offset = size
    except OSError:
        return False
    for raw in chunk.splitlines():
        if not raw.strip():
            continue
        try:
            line = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        usage, ts = _extract_usage(line)
        if usage is None:
            continue
        state.total.input_tokens  += usage.input_tokens
        state.total.output_tokens += usage.output_tokens
        state.total.cache_read    += usage.cache_read
        state.total.cache_write   += usage.cache_write
        if usage.model:
            state.total.model = usage.model
        state.last_turn = usage
        if not state.started_ts and ts:
            state.started_ts = ts
        changed = True
    return changed


def seed_session(state: SessionState) -> None:
    """Read the entire transcript once to populate totals before tailing."""
    state.last_offset = 0
    state.total = TurnUsage()
    state.last_turn = TurnUsage()
    state.started_ts = ""
    update_session(state)
