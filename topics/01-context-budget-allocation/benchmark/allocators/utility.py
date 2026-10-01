"""Protected constrained utility packing.

After the protected lane and elastic floors, remaining items compete globally
by score = relevance * class_weight (recency stands in for missing relevance).

Ceilings still apply so one high-scoring class cannot erase the floors.
"""

from __future__ import annotations

from benchmark.allocators.common import (
    auth_filter,
    class_demand,
    exclusions_from,
    pack_items,
    scale_to_budget,
    sort_class,
    take_protected,
    used_with_overhead,
    utility_score,
)
from benchmark.config import AllocConfig, ELASTIC
from benchmark.schema import AllocationResult, ContextItem
from benchmark.tokenizers import Tokenizer


class UtilityAllocator:
    name = "utility"
    version = "1"

    def allocate(
        self,
        items: list[ContextItem],
        budget: int,
        tenant_id: str,
        cfg: AllocConfig,
        tokenizer: Tokenizer,
    ) -> AllocationResult:
        authorized, excluded = auth_filter(items, tenant_id, cfg)
        demand = class_demand(authorized, cfg)
        selected, used, prot_excl, failed, fail_reason = take_protected(
            authorized, budget, cfg, tokenizer
        )
        excluded.extend(prot_excl)
        class_budget = {cls: 0 for cls in demand}
        for item in selected:
            class_budget[item.cls] = class_budget.get(item.cls, 0) + item.token_count + cfg.per_item_overhead

        notes = ["protected first", "elastic floors", "greedy score packing", "ceilings"]
        if failed:
            rest = [it for it in authorized if it.id not in {s.id for s in selected}]
            excluded.extend(exclusions_from(rest, "failed_closed"))
            excluded = _dedupe_excl(excluded)
            return AllocationResult(
                allocator=self.name,
                allocator_version=self.version,
                selected=selected,
                excluded=excluded,
                class_demand=demand,
                class_budget=class_budget,
                class_used=used_with_overhead(selected, cfg),
                failed_closed=True,
                failure_reason=fail_reason,
                notes=notes + ["failed closed; elastic omitted"],
            )

        remaining = budget - used
        selected_ids = {s.id for s in selected}
        elastic = [it for it in authorized if it.cls in ELASTIC and it.id not in selected_ids]
        by_cls: dict[str, list[ContextItem]] = {cls: [] for cls in ELASTIC}
        for item in elastic:
            by_cls[item.cls].append(item)

        elastic_demand = {cls: demand.get(cls, 0) for cls in ELASTIC}
        floors = {
            cls: min(elastic_demand[cls], int(cfg.floors[cls] * remaining)) for cls in ELASTIC
        }
        if sum(floors.values()) > remaining:
            floors = scale_to_budget(floors, remaining)
            notes.append("floors scaled because they exceeded remaining budget")
        ceilings = {cls: int(cfg.ceilings[cls] * remaining) for cls in ELASTIC}

        class_used = {cls: 0 for cls in ELASTIC}
        leftover_by_class: dict[str, list[ContextItem]] = {cls: [] for cls in ELASTIC}
        for cls in ELASTIC:
            ordered = sort_class(by_cls[cls], cls, cfg)
            packed, packed_used, rest = pack_items(ordered, floors[cls], cfg, tokenizer)
            selected.extend(packed)
            leftover_by_class[cls] = rest
            class_used[cls] += packed_used
            used += packed_used
            class_budget[cls] = floors[cls]

        # Global greedy over remaining items.
        remaining_items: list[ContextItem] = []
        for cls, rest in leftover_by_class.items():
            remaining_items.extend(rest)
        remaining_items.sort(
            key=lambda it: (
                -utility_score(it, by_cls[it.cls], cfg),
                it.id,
            )
        )

        leftover_unpacked: list[ContextItem] = []
        hole = budget - used
        packed, packed_used, rest = _pack_with_ceilings(
            remaining_items, hole, class_used, ceilings, cfg, tokenizer
        )
        selected.extend(packed)
        used += packed_used
        leftover_unpacked.extend(rest)

        excluded.extend(exclusions_from(leftover_unpacked, "utility_not_selected"))
        excluded = _dedupe_excl(excluded)
        # class_budget for elastic is floors plus what greedy added, capped by ceiling
        final_used = used_with_overhead(selected, cfg)
        for cls in ELASTIC:
            class_budget[cls] = max(class_budget.get(cls, 0), final_used.get(cls, 0))
        return AllocationResult(
            allocator=self.name,
            allocator_version=self.version,
            selected=selected,
            excluded=excluded,
            class_demand=demand,
            class_budget=class_budget,
            class_used=final_used,
            failed_closed=False,
            failure_reason=None,
            notes=notes,
        )


def _pack_with_ceilings(items, budget, class_used, ceilings, cfg, tokenizer):
    selected = []
    leftover = []
    used = 0
    if budget <= 0:
        return selected, 0, list(items)
    for item in items:
        remaining = budget - used
        room = min(remaining, max(0, ceilings.get(item.cls, remaining) - class_used.get(item.cls, 0)))
        packed, packed_used, rest = pack_items([item], room, cfg, tokenizer)
        if packed:
            selected.extend(packed)
            used += packed_used
            class_used[item.cls] = class_used.get(item.cls, 0) + packed_used
        if rest:
            leftover.extend(rest)
    return selected, used, leftover


def _dedupe_excl(excluded):
    seen = set()
    out = []
    for ex in excluded:
        if ex.id in seen:
            continue
        seen.add(ex.id)
        out.append(ex)
    return out
