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
