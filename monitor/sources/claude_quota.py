"""Fetch authoritative 5h/7d quota from Anthropic.

Strategy mirrors the open-source CodeZeno/Claude-Code-Usage-Monitor:
1. Try GET /api/oauth/usage first (works on some plans).
2. Fall back to a tiny POST /v1/messages — the response *headers* always carry
   `anthropic-ratelimit-unified-{5h,7d}-utilization` and reset timestamps,
   even when the request itself errors. We use claude-3-haiku and max_tokens=1
   to keep the cost at literally one token.

Credentials come from ~/.claude/.credentials.json (OAuth bearer used by the
official Claude Code CLI).
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone

try:
    import requests  # type: ignore
except ImportError:
    requests = None  # type: ignore

CREDENTIALS_PATH = pathlib.Path.home() / ".claude" / ".credentials.json"


def _desktop_search_dirs() -> list[pathlib.Path]:
    """Directories that may contain Claude Desktop's config.json + Local State.

    Claude Desktop is shipped as an MSIX-packaged app on Windows 11, which
    redirects all %APPDATA% writes into a per-package private LocalCache.
    We probe the standard location first (works for non-MSIX installs and
    older builds), then glob the MSIX Packages directory for any
    Claude_*\\LocalCache\\Roaming\\Claude folder.
    """
    dirs: list[pathlib.Path] = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(pathlib.Path(appdata) / "Claude")
    localappdata = os.environ.get("LOCALAPPDATA")
    if localappdata:
        pkgs = pathlib.Path(localappdata) / "Packages"
        try:
            for pkg in pkgs.glob("Claude_*"):
                candidate = pkg / "LocalCache" / "Roaming" / "Claude"
                if candidate.exists():
                    dirs.append(candidate)
        except OSError:
            pass
    return dirs


# Exposed for diagnostic scripts; resolved on import so the first existing
# pair stays consistent across calls. Falls back to the legacy paths if none
# of the candidates exist yet (so the values are never None).
def _resolve_desktop_paths() -> tuple[pathlib.Path, pathlib.Path]:
    for d in _desktop_search_dirs():
        cfg = d / "config.json"
        ls = d / "Local State"
        if cfg.exists() and ls.exists():
            return cfg, ls
    # Default to the legacy %APPDATA%\Claude paths if nothing matched —
    # callers will see exists()==False and skip the desktop bearer branch.
    appdata = pathlib.Path(os.environ.get("APPDATA", ""))
    return appdata / "Claude" / "config.json", appdata / "Claude" / "Local State"


DESKTOP_CONFIG_PATH, DESKTOP_LOCAL_STATE_PATH = _resolve_desktop_paths()
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MESSAGES_URL = "https://api.anthropic.com/v1/messages"
MODEL_FALLBACKS = ("claude-haiku-4-5-20251001", "claude-3-haiku-20240307")


@dataclass
class QuotaWindow:
    used_pct: float
    resets_at_iso: str | None


@dataclass
class Quota:
    five_hour: QuotaWindow | None = None
    seven_day: QuotaWindow | None = None


def _bearer() -> str | None:
    """Read OAuth bearer from Claude Code CLI file or Claude Desktop's encrypted store."""
    # 1. Claude Code CLI plain JSON.
    if CREDENTIALS_PATH.exists():
        try:
            data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
            tok = ((data or {}).get("claudeAiOauth") or {}).get("accessToken")
            if tok:
                return str(tok)
        except (OSError, json.JSONDecodeError):
            pass
    # 2. Claude Desktop (Electron safeStorage, AES-256-GCM, key wrapped by DPAPI).
    return _bearer_from_desktop()


def _bearer_from_desktop() -> str | None:
    if not (DESKTOP_CONFIG_PATH.exists() and DESKTOP_LOCAL_STATE_PATH.exists()):
        return None
    try:
        import win32crypt  # type: ignore
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    except ImportError:
        return None
    try:
        ls = json.loads(DESKTOP_LOCAL_STATE_PATH.read_text(encoding="utf-8"))
        enc_key = base64.b64decode(ls["os_crypt"]["encrypted_key"])
        if enc_key[:5] != b"DPAPI":
            return None
        key = win32crypt.CryptUnprotectData(enc_key[5:], None, None, None, 0)[1]
        cfg = json.loads(DESKTOP_CONFIG_PATH.read_text(encoding="utf-8"))
        blob = base64.b64decode(cfg.get("oauth:tokenCache", ""))
        if blob[:3] != b"v10":
            return None
        plain = AESGCM(key).decrypt(blob[3:15], blob[15:], None)
        cache = json.loads(plain.decode("utf-8"))
    except Exception:
        return None
    # cache is a dict keyed by a long composite key; pick the first entry that
    # has a usable access token.
    for entry in cache.values() if isinstance(cache, dict) else []:
        if isinstance(entry, dict):
            tok = entry.get("token") or entry.get("accessToken")
            if tok:
                return str(tok)
    return None


def fetch() -> Quota | None:
    if requests is None:
        return None
    token = _bearer()
    if not token:
        return None
    q = _try_oauth_usage(token)
    if q is not None and (q.five_hour or q.seven_day):
        return q
    return _try_messages_headers(token)


# --- /api/oauth/usage -----------------------------------------------------

def _try_oauth_usage(token: str) -> Quota | None:
    try:
        resp = requests.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
            },
            timeout=5,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return _parse_oauth_body(body)


def _parse_oauth_body(body: dict) -> Quota:
    q = Quota()
    five = body.get("five_hour")
    seven = body.get("seven_day")
    if isinstance(five, dict):
        pct = _pct_from_obj(five)
        if pct is not None:
            q.five_hour = QuotaWindow(used_pct=pct, resets_at_iso=_resets_iso(five))
    if isinstance(seven, dict):
        pct = _pct_from_obj(seven)
        if pct is not None:
            q.seven_day = QuotaWindow(used_pct=pct, resets_at_iso=_resets_iso(seven))
    return q


def _pct_from_obj(obj: dict) -> float | None:
    for k in ("utilization", "percentage", "used_pct", "usage_percentage"):
        if k in obj and obj[k] is not None:
            try:
                v = float(obj[k])
                return v if v > 1.5 else v * 100.0
            except (TypeError, ValueError):
                pass
    return None


def _resets_iso(obj: dict) -> str | None:
    for k in ("resets_at", "reset_at", "reset_time"):
        v = obj.get(k)
        if v:
            return str(v)
    return None


# --- /v1/messages rate-limit headers --------------------------------------

def _try_messages_headers(token: str) -> Quota | None:
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "oauth-2025-04-20",
        "Content-Type": "application/json",
    }
    for model in MODEL_FALLBACKS:
        body = {
            "model": model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}],
        }
        try:
            resp = requests.post(MESSAGES_URL, headers=headers, json=body, timeout=10)
        except requests.RequestException:
            continue
        if resp.status_code in (401, 403):
            return None
        h5 = resp.headers.get("anthropic-ratelimit-unified-5h-utilization")
        h7 = resp.headers.get("anthropic-ratelimit-unified-7d-utilization")
        if h5 is None and h7 is None:
            continue
        return _parse_rate_limit_headers(resp.headers)
    return None


def _parse_rate_limit_headers(h) -> Quota:
    q = Quota()
    pct5 = _hdr_float(h, "anthropic-ratelimit-unified-5h-utilization")
    pct7 = _hdr_float(h, "anthropic-ratelimit-unified-7d-utilization")
    if pct5 is not None:
        q.five_hour = QuotaWindow(
            used_pct=pct5 * 100.0,
            resets_at_iso=_unix_to_iso(_hdr_int(h, "anthropic-ratelimit-unified-5h-reset")),
        )
    if pct7 is not None:
        q.seven_day = QuotaWindow(
            used_pct=pct7 * 100.0,
            resets_at_iso=_unix_to_iso(_hdr_int(h, "anthropic-ratelimit-unified-7d-reset")),
        )
    # If both report 0% but status says rejected, infer 100% from the claim.
    if q.five_hour and q.seven_day and q.five_hour.used_pct == 0 and q.seven_day.used_pct == 0:
        if h.get("anthropic-ratelimit-unified-status") == "rejected":
            claim = h.get("anthropic-ratelimit-unified-representative-claim")
            if claim == "five_hour":
                q.five_hour = QuotaWindow(100.0, q.five_hour.resets_at_iso)
            elif claim == "seven_day":
                q.seven_day = QuotaWindow(100.0, q.seven_day.resets_at_iso)
    return q


def _hdr_float(h, key: str) -> float | None:
    v = h.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _hdr_int(h, key: str) -> int | None:
    v = h.get(key)
    if v is None:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _unix_to_iso(unix: int | None) -> str | None:
    if unix is None or unix <= 0:
        return None
    return datetime.fromtimestamp(unix, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
