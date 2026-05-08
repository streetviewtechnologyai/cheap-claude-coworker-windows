"""User's Anthropic plan — controls how cost is displayed.

On a subscription plan you pay a flat monthly fee, so per-token list-price
dollar figures are misleading as "your cost." We surface the subscription
price instead and label per-token totals as "API-equivalent value."
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    monthly_usd: float | None  # None = pay-per-token API
    cap_5h_tokens: int | None   # rough public cap; None = uncapped/unknown
    cap_7d_tokens: int | None


# Anthropic doesn't publish exact token caps — they enforce by messages/effort
# in opaque ways. We don't fake numbers here. If you know your cap, set it via
# QSettings: panohopper/TokenMonitor → cap_5h_tokens / cap_7d_tokens.
PLANS: dict[str, Plan] = {
    "api":        Plan("api",        "API (pay-per-token)", None,  None, None),
    "pro":        Plan("pro",        "Pro ($20/mo)",         20.0, None, None),
    "max5x":      Plan("max5x",      "Max 5× ($100/mo)",    100.0, None, None),
    "max20x":     Plan("max20x",     "Max 20× ($200/mo)",   200.0, None, None),
    "teams":      Plan("teams",      "Teams ($25/user/mo)",  25.0, None, None),
    "enterprise": Plan("enterprise", "Enterprise",            None, None, None),
}

DEFAULT_KEY = "pro"


def get(key: str | None) -> Plan:
    return PLANS.get((key or DEFAULT_KEY).lower(), PLANS[DEFAULT_KEY])


def is_subscription(plan: Plan) -> bool:
    return plan.key != "api"
