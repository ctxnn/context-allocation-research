"""Experimental allocator knobs.

ASSUMED: every number here is an experimental default for the synthetic
benchmark. None of these are proven production values.
"""

from __future__ import annotations

from dataclasses import dataclass, field


ELASTIC = ("history", "rag", "tool_result", "agent", "memory")


def _quotas() -> dict[str, float]:
    # Must sum to 1.0. Used by the fixed-quota allocator.
    return {
        "history": 0.30,
        "rag": 0.25,
        "tool_result": 0.20,
        "agent": 0.15,
        "memory": 0.10,
    }


def _floors() -> dict[str, float]:
    # Fraction of post-protected remaining budget. 5 * 0.08 = 40% reserved
    # as class floors before leftover sharing.
    return {name: 0.08 for name in ELASTIC}


def _weights() -> dict[str, float]:
    # Relative importance for water-fill leftover sharing and utility scoring.
    return {
        "history": 8.0,
        "rag": 6.0,
        "tool_result": 5.0,
        "agent": 4.0,
        "memory": 3.0,
    }


def _ceilings() -> dict[str, float]:
    # Max fraction of post-protected remaining a single elastic class may take.
    return {
        "history": 0.50,
        "rag": 0.45,
        "tool_result": 0.40,
        "agent": 0.30,
        "memory": 0.25,
    }


@dataclass(frozen=True)
class AllocConfig:
    quotas: dict[str, float] = field(default_factory=_quotas)
    floors: dict[str, float] = field(default_factory=_floors)
    weights: dict[str, float] = field(default_factory=_weights)
    ceilings: dict[str, float] = field(default_factory=_ceilings)
    spillover_order: tuple[str, ...] = ELASTIC
    pin_oldest_history: bool = True
    # Wrapper tokens around each item in assemble() are ~8-12 with cl100k_base.
    # 16 is a conservative stand-in so packing does not silently overflow.
    per_item_overhead: int = 16
    # Section headers in assemble() are ~46 tokens. Held back from the allocator.
    assembly_reserve: int = 64
    min_truncate_tokens: int = 32
    # Platform-owned items are always authorized, regardless of request tenant.
    platform_tenant_id: str = "platform"

    def class_weight(self, cls: str) -> float:
        return self.weights.get(cls, 1.0)


DEFAULT_CONFIG = AllocConfig()
