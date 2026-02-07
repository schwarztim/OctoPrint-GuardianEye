"""
API Cost Estimation for GuardianEye.

Per-call cost lookup by provider/model. Tracks session + lifetime cost.
Ollama is always $0.00.

Costs are approximate — based on typical image token counts (~800 input
tokens for a JPEG + ~50 output tokens for a verdict).
"""

import logging

_logger = logging.getLogger("octoprint.plugins.guardianeye.cost")

# Approximate cost per vision call (input image + prompt + output)
# Based on: ~800 input tokens (image) + ~200 prompt tokens + ~50 output tokens
_COST_TABLE = {
    # OpenAI
    ("openai", "gpt-4o-mini"): 0.0003,
    ("openai", "gpt-4o"): 0.005,
    ("openai", "gpt-4.1-mini"): 0.0003,
    ("openai", "gpt-4.1"): 0.004,
    # Azure OpenAI (same models, same pricing)
    ("azure_openai", "gpt-4o-mini"): 0.0003,
    ("azure_openai", "gpt-4o"): 0.005,
    ("azure_openai", "gpt-4.1-mini"): 0.0003,
    ("azure_openai", "gpt-4.1"): 0.004,
    # Anthropic
    ("anthropic", "claude-sonnet-4-20250514"): 0.005,
    ("anthropic", "claude-haiku-4-5-20251001"): 0.001,
    # xAI
    ("xai", "grok-2-vision-latest"): 0.005,
    # Gemini
    ("gemini", "gemini-2.0-flash"): 0.0001,
    ("gemini", "gemini-1.5-flash"): 0.0001,
    ("gemini", "gemini-1.5-pro"): 0.003,
    # Ollama (always free)
    ("ollama", "llava"): 0.0,
    ("ollama", "llava:13b"): 0.0,
    ("ollama", "llava:34b"): 0.0,
    ("ollama", "bakllava"): 0.0,
}

# Default cost when model not in table
_DEFAULT_COSTS = {
    "openai": 0.001,
    "azure_openai": 0.001,
    "anthropic": 0.005,
    "xai": 0.005,
    "gemini": 0.0005,
    "ollama": 0.0,
}


def estimate_cost(provider, model):
    """Estimate cost for a single vision API call."""
    cost = _COST_TABLE.get((provider, model))
    if cost is not None:
        return cost
    return _DEFAULT_COSTS.get(provider, 0.001)


class CostTracker:
    """Track API costs per session and lifetime."""

    def __init__(self):
        self.session_cost = 0.0
        self.session_calls = 0
        self.lifetime_cost = 0.0
        self.lifetime_calls = 0

    def record(self, cost):
        self.session_cost += cost
        self.session_calls += 1
        self.lifetime_cost += cost
        self.lifetime_calls += 1

    def reset_session(self):
        self.session_cost = 0.0
        self.session_calls = 0

    def to_dict(self):
        return {
            "session_cost": round(self.session_cost, 4),
            "session_calls": self.session_calls,
            "lifetime_cost": round(self.lifetime_cost, 4),
            "lifetime_calls": self.lifetime_calls,
        }

    def load(self, data):
        """Restore lifetime stats from saved data."""
        self.lifetime_cost = data.get("lifetime_cost", 0.0)
        self.lifetime_calls = data.get("lifetime_calls", 0)
