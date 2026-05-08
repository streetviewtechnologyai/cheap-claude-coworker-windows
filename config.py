"""Worker model configuration.

Set the active provider below. It must match the key in PROVIDERS below. Not "label, not "model".
"""
ACTIVE_PROVIDER = "deepseek-v4-flash"

PROVIDERS = {
    "deepseek-v4-flash": {
        "label": "DeepSeek V4 Flash",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key": "",
    },
    "deepseek-v4-pro": {
        "label": "DeepSeek V4 Pro",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-pro",
        "api_key": "",
    },
    "kimi": {
        "label": "Kimi (Moonshot AI)",
        "base_url": "https://api.moonshot.ai/v1",
        "model": "kimi-k2.5",
        "api_key": "",
    },
    "ollama": {
        "label": "Ollama (local)",
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5-coder:14b",
        "api_key": "ollama",  # Ollama ignores the key but the SDK requires non-empty
    },
}

"""For a quick switch to another provider: 
    First make sure the API keys are stored in the "api_key" field of each provider.
    
    Then run:
    cd claude-coworker-model
    coworker-config list
    coworker-config use <name>
"""

def resolve(provider_name: str | None = None) -> dict:
    """Return {api_key, base_url, model, label, name} for the given (or active) provider."""
    name = provider_name or ACTIVE_PROVIDER
    if name not in PROVIDERS:
        raise SystemExit(
            f"Unknown provider: {name!r}. Known: {', '.join(PROVIDERS)}"
        )
    p = PROVIDERS[name]
    return {
        "name": name,
        "label": p["label"],
        "base_url": p["base_url"],
        "model": p["model"],
        "api_key": p.get("api_key", ""),
    }


def log_usage(cfg: dict, tool: str, usage, finish_reason: str) -> None:
    """Append one JSONL record per worker call to ~/.claude/coworker-tokens.jsonl.

    Read by the token-monitor tray app. Silent on any failure so worker tools
    never break because of logging. Disable with WORKER_LOG_TOKENS=0.
    """
    import os
    if os.environ.get("WORKER_LOG_TOKENS", "1") == "0":
        return
    try:
        import json
        import pathlib
        from datetime import datetime, timezone

        cached = getattr(getattr(usage, "prompt_tokens_details", None),
                         "cached_tokens", 0) or 0
        rec = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tool": tool,
            "provider": cfg["name"],
            "model": cfg["model"],
            "base_url": cfg.get("base_url", ""),
            "prompt_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
            "cached_tokens": int(cached),
            "finish_reason": finish_reason or "",
            "ppid": os.getppid(),
        }
        path = pathlib.Path.home() / ".claude" / "coworker-tokens.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
