"""Shared allocator primitives.

Every serious candidate should call these so safety invariants stay comparable:
auth filter, protected lane, integer budget split, and within-class packing.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from benchmark.config import AllocConfig
from benchmark.schema import (
    ELASTIC_CLASSES,
    PROTECTED_ORDER,
    ContextItem,
    Exclusion,
    SelectedItem,
)
from benchmark.tokenizers import Tokenizer


def cost_of(item: ContextItem, cfg: AllocConfig) -> int:
    tokens = item.token_count if item.token_count is not None else 0
    return tokens + cfg.per_item_overhead


def auth_filter(
    items: Iterable[ContextItem],
    tenant_id: str,
    cfg: AllocConfig,
) -> tuple[list[ContextItem], list[Exclusion]]:
    kept: list[ContextItem] = []
    dropped: list[Exclusion] = []
    allowed = {tenant_id, cfg.platform_tenant_id}
    for item in items:
        tokens = item.token_count or 0
        if item.tenant_id in allowed:
            kept.append(item)
        else:
            dropped.append(Exclusion(item.id, item.cls, "unauthorized_tenant", tokens))
    return kept, dropped


def class_demand(items: Iterable[ContextItem], cfg: AllocConfig) -> dict[str, int]:
    demand = {cls: 0 for cls in (*PROTECTED_ORDER, *ELASTIC_CLASSES)}
    for item in items:
        demand[item.cls] = demand.get(item.cls, 0) + cost_of(item, cfg)
    return demand


def sort_class(items: list[ContextItem], cls: str, cfg: AllocConfig) -> list[ContextItem]:
    """Deterministic within-class order used for packing."""
    if cls == "history":
        if not items:
            return []
        if cfg.pin_oldest_history:
            oldest = min(items, key=lambda x: (x.sequence, x.id))
            rest = [x for x in items if x.id != oldest.id]
            rest_sorted = sorted(rest, key=lambda x: (-x.sequence, x.id))
            return [oldest, *rest_sorted]
        return sorted(items, key=lambda x: (-x.sequence, x.id))
    if cls in ("rag", "memory"):
        return sorted(items, key=lambda x: (-(x.relevance or 0.0), x.sequence, x.id))
    if cls in ("tool_result", "agent"):
        return sorted(items, key=lambda x: (-x.sequence, x.id))
    return sorted(items, key=lambda x: (x.sequence, x.id))


def to_selected(item: ContextItem, content: str, tokens: int, truncated: bool) -> SelectedItem:
    return SelectedItem(
        id=item.id,
        cls=item.cls,
        content=content,
        token_count=tokens,
        truncated=truncated,
        original_token_count=item.token_count or tokens,
        sequence=item.sequence,
        relevance=item.relevance,
        tenant_id=item.tenant_id,
    )


def pack_items(
    items: list[ContextItem],
    budget: int,
    cfg: AllocConfig,
    tokenizer: Tokenizer,
    on_miss: str = "skip",
) -> tuple[list[SelectedItem], int, list[ContextItem]]:
    """Greedy pack in the given order.

    If an item does not fit:
      - truncatable items consume a prefix
      - on_miss="skip": try the next item (smaller later items may still fit)
      - on_miss="stop": keep a prefix of the ordered list; do not backfill holes
    """
    selected: list[SelectedItem] = []
    leftover_items: list[ContextItem] = []
    used = 0
    if budget <= 0:
        return selected, 0, list(items)

    for idx, item in enumerate(items):
        remaining = budget - used
        full_cost = cost_of(item, cfg)
        if full_cost <= remaining:
            selected.append(to_selected(item, item.content, item.token_count or 0, False))
            used += full_cost
            continue
        body_room = remaining - cfg.per_item_overhead
        if item.truncatable and body_room >= cfg.min_truncate_tokens:
            truncated = tokenizer.truncate(item.content, body_room)
            actual = tokenizer.count(truncated)
            if actual <= 0:
                leftover_items.append(item)
                if on_miss == "stop":
                    leftover_items.extend(items[idx + 1 :])
                    break
                continue
            selected.append(to_selected(item, truncated, actual, True))
            used += actual + cfg.per_item_overhead
            continue
        leftover_items.append(item)
        if on_miss == "stop":
            leftover_items.extend(items[idx + 1 :])
            break
    return selected, used, leftover_items


def take_protected(
    items: list[ContextItem],
    budget: int,
    cfg: AllocConfig,
    tokenizer: Tokenizer,
) -> tuple[list[SelectedItem], int, list[Exclusion], bool, str | None]:
    """Protected lane. System/security never truncate. User may truncate.

    If a non-truncatable protected item cannot fit, we fail closed: keep what
    already fit in hierarchy order and do not admit elastic items.
    """
    selected: list[SelectedItem] = []
    excluded: list[Exclusion] = []
    used = 0
    failed = False
    reason: str | None = None
    remaining_budget = budget

    by_cls: dict[str, list[ContextItem]] = {}
    for item in items:
        by_cls.setdefault(item.cls, []).append(item)

    for cls in PROTECTED_ORDER:
        ordered = sort_class(by_cls.get(cls, []), cls, cfg)
        packed, packed_used, leftover = pack_items(ordered, remaining_budget, cfg, tokenizer)
        selected.extend(packed)
        used += packed_used
        remaining_budget = budget - used
        for item in leftover:
            if not item.truncatable:
                failed = True
                reason = f"protected_overflow:{item.id}"
            excluded.append(
                Exclusion(item.id, item.cls, "protected_overflow", item.token_count or 0)
            )
        if failed and cls in ("system", "security"):
            # Do not continue into lower protected classes or elastic.
            for later in PROTECTED_ORDER[PROTECTED_ORDER.index(cls) + 1 :]:
                for item in by_cls.get(later, []):
                    excluded.append(
                        Exclusion(item.id, item.cls, "failed_closed", item.token_count or 0)
                    )
            break
    return selected, used, excluded, failed, reason


def split_integer(total: int, shares: dict[str, float], order: tuple[str, ...]) -> dict[str, int]:
    """Largest-remainder split. `shares` should sum to ~1.0 for a full partition."""
    raw = {k: total * shares.get(k, 0.0) for k in order}
    out = {k: int(math.floor(raw[k])) for k in order}
    leftover = total - sum(out.values())
    frac_order = sorted(order, key=lambda k: (-(raw[k] - math.floor(raw[k])), k))
    i = 0
    while leftover > 0 and frac_order:
        out[frac_order[i % len(frac_order)]] += 1
        leftover -= 1
        i += 1
    return out


def scale_to_budget(values: dict[str, int], budget: int) -> dict[str, int]:
    total = sum(values.values())
    if total <= budget:
        return dict(values)
    if total == 0:
        return dict(values)
    scaled = {k: int(math.floor(budget * (v / total))) for k, v in values.items()}
    leftover = budget - sum(scaled.values())
    order = sorted(values.keys(), key=lambda k: (-(values[k] - scaled[k] * (total / max(budget, 1))), k))
    i = 0
    while leftover > 0 and order:
        scaled[order[i % len(order)]] += 1
        leftover -= 1
        i += 1
    return scaled


def weighted_waterfill(
    demands: dict[str, int],
    weights: dict[str, float],
    budget: int,
) -> dict[str, int]:
    """Weighted max-min (water-fill) over integer token budgets.

    Classes whose demand is below their current fair share are fully satisfied;
    unused share is redistributed among classes that still have demand.
    """
    alloc = {k: 0 for k in demands}
    demand_left = {k: max(0, int(d)) for k, d in demands.items()}
    left = max(0, int(budget))
    guard = 0
    while left > 0 and guard < 10_000:
        guard += 1
        active = [k for k, d in demand_left.items() if d > 0 and weights.get(k, 0) > 0]
        if not active:
            break
        wsum = sum(weights[k] for k in active)
        shares = {k: left * (weights[k] / wsum) for k in active}
        satisfied = [k for k in active if demand_left[k] <= shares[k] + 1e-9]
        if satisfied:
            for k in satisfied:
                give = demand_left[k]
                alloc[k] += give
                left -= give
                demand_left[k] = 0
            continue
        base = {k: int(math.floor(shares[k])) for k in active}
        leftover = left - sum(base.values())
        frac_order = sorted(active, key=lambda k: (-(shares[k] - math.floor(shares[k])), k))
        give = dict(base)
        idx = 0
        while leftover > 0:
            k = frac_order[idx % len(frac_order)]
            give[k] += 1
            leftover -= 1
            idx += 1
        for k in active:
            g = min(give[k], demand_left[k])
            alloc[k] += g
            demand_left[k] -= g
            left -= g
        break
    return alloc


def waterfill_with_ceilings(
    demands: dict[str, int],
    weights: dict[str, float],
    budget: int,
    ceilings: dict[str, int],
) -> dict[str, int]:
    """Water-fill, then clip to per-class ceilings and redistribute surplus."""
    alloc = {k: 0 for k in demands}
    remaining_demand = {k: max(0, int(d)) for k, d in demands.items()}
    remaining_budget = max(0, int(budget))
    blocked: set[str] = set()
    guard = 0
    while remaining_budget > 0 and guard < 10_000:
        guard += 1
        active = []
        capped: dict[str, int] = {}
        for k, d in remaining_demand.items():
            if d <= 0 or k in blocked:
                continue
            room = max(0, ceilings.get(k, remaining_budget) - alloc[k])
            take = min(d, room)
            if take > 0:
                active.append(k)
                capped[k] = take
        if not active:
            break
        step = weighted_waterfill(capped, weights, remaining_budget)
        progressed = False
        for k, g in step.items():
            if g <= 0:
                continue
            room = max(0, ceilings.get(k, remaining_budget) - alloc[k])
            g = min(g, room, remaining_demand[k], remaining_budget)
            if g <= 0:
                blocked.add(k)
                continue
            alloc[k] += g
            remaining_demand[k] -= g
            remaining_budget -= g
            progressed = True
            if alloc[k] >= ceilings.get(k, alloc[k]):
                blocked.add(k)
        if not progressed:
            break
    return alloc


def recency_norm(item: ContextItem, class_items: list[ContextItem]) -> float:
    """Map sequence to 0.35..1.0 within a class when relevance is missing."""
    seqs = [x.sequence for x in class_items]
    lo, hi = min(seqs), max(seqs)
    if hi == lo:
        return 1.0
    return 0.35 + 0.65 * ((item.sequence - lo) / (hi - lo))


def utility_score(item: ContextItem, class_items: list[ContextItem], cfg: AllocConfig) -> float:
    if item.relevance is not None:
        rel = item.relevance
    else:
        rel = recency_norm(item, class_items)
    return rel * cfg.class_weight(item.cls)


def spillover_pack(
    leftover_by_class: dict[str, list[ContextItem]],
    leftover_budget: int,
    order: tuple[str, ...],
    cfg: AllocConfig,
    tokenizer: Tokenizer,
    ceilings: dict[str, int] | None,
    already_used: dict[str, int],
) -> tuple[list[SelectedItem], int, dict[str, list[ContextItem]]]:
    """Give unused tokens to classes that still have items, in a fixed order."""
    selected: list[SelectedItem] = []
    used_total = 0
    remaining = leftover_budget
    leftover = {k: list(v) for k, v in leftover_by_class.items()}
    for cls in order:
        if remaining <= 0:
            break
        room = remaining
        if ceilings is not None:
            room = min(room, max(0, ceilings.get(cls, remaining) - already_used.get(cls, 0)))
        packed, used, rest = pack_items(leftover.get(cls, []), room, cfg, tokenizer)
        leftover[cls] = rest
        selected.extend(packed)
        used_total += used
        remaining -= used
        already_used[cls] = already_used.get(cls, 0) + used
    return selected, used_total, leftover


def exclusions_from(items: Iterable[ContextItem], reason: str) -> list[Exclusion]:
    return [Exclusion(it.id, it.cls, reason, it.token_count or 0) for it in items]


def used_with_overhead(selected: list[SelectedItem], cfg: AllocConfig) -> dict[str, int]:
    used: dict[str, int] = {}
    for item in selected:
        used[item.cls] = used.get(item.cls, 0) + item.token_count + cfg.per_item_overhead
    return used
