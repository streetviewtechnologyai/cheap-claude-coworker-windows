"""Per-model pricing in USD per 1M tokens.

Anthropic figures match the public price sheet at the time of writing; verify
before relying on absolute numbers. Worker rates are list prices for each
provider's chat completions endpoint.
"""
from __future__ import annotations

CLAUDE_RATES: dict[str, dict[str, float]] = {
    "claude-opus-4-7":   {"in": 15.00, "out": 75.00, "cache_read": 1.50,  "cache_write": 18.75},
    "claude-opus-4-6":   {"in": 15.00, "out": 75.00, "cache_read": 1.50,  "cache_write": 18.75},
    "claude-sonnet-4-7": {"in":  3.00, "out": 15.00, "cache_read": 0.30,  "cache_write":  3.75},
    "claude-sonnet-4-6": {"in":  3.00, "out": 15.00, "cache_read": 0.30,  "cache_write":  3.75},
    "claude-haiku-4-5":  {"in":  1.00, "out":  5.00, "cache_read": 0.10,  "cache_write":  1.25},
}

WORKER_RATES: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {"in": 0.07, "out": 0.28, "cache_read": 0.014},
    "deepseek-v4-pro":   {"in": 0.27, "out": 1.10, "cache_read": 0.054},
    "kimi":              {"in": 0.60, "out": 2.50, "cache_read": 0.06},
    "kimi-k2.5":         {"in": 0.60, "out": 2.50, "cache_read": 0.06},
}


def is_local_url(base_url: str) -> bool:
    if not base_url:
        return False
    u = base_url.lower()
    return "localhost" in u or "127.0.0.1" in u or "://192.168." in u or "://10." in u

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"


def _match(name: str, table: dict[str, dict[str, float]]) -> dict[str, float] | None:
    if not name:
        return None
    if name in table:
        return table[name]
    low = name.lower()
    for key, val in table.items():
        if key in low or low.startswith(key):
            return val
    return None


def claude_cost(model: str, in_tok: int, out_tok: int,
                cache_read_tok: int = 0, cache_write_tok: int = 0) -> float:
    rates = _match(model, CLAUDE_RATES) or CLAUDE_RATES[DEFAULT_CLAUDE_MODEL]
    return (
        in_tok        * rates["in"]          +
        out_tok       * rates["out"]         +
        cache_read_tok  * rates["cache_read"]  +
        cache_write_tok * rates["cache_write"]
    ) / 1_000_000.0


def worker_cost(provider: str, in_tok: int, out_tok: int,
                cached_tok: int = 0, base_url: str = "") -> float | None:
    """Return USD cost. None means rate unknown (display as '—').
    A literal 0.0 means we know the run was free (e.g. local Ollama)."""
    if is_local_url(base_url):
        return 0.0
    rates = _match(provider, WORKER_RATES)
    if rates is None:
        return None
    billable_in = max(in_tok - cached_tok, 0)
    return (
        billable_in   * rates["in"]                      +
        cached_tok    * rates.get("cache_read", rates["in"]) +
        out_tok       * rates["out"]
    ) / 1_000_000.0


def counterfactual_claude_cost(claude_model: str, in_tok: int, out_tok: int) -> float:
    """What the worker call would have cost if run through Claude instead."""
    rates = _match(claude_model, CLAUDE_RATES) or CLAUDE_RATES[DEFAULT_CLAUDE_MODEL]
    return (in_tok * rates["in"] + out_tok * rates["out"]) / 1_000_000.0
