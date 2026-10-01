"""Protected floors + weighted water-fill leftover sharing (PHTB-WF).

1. Protected lane
2. Elastic floors (starvation guard)
3. Weighted water-fill of leftover demand
4. Per-class ceilings
5. Deterministic within-class packing
6. Spill leftover packing holes
"""

from __future__ import annotations

from benchmark.allocators.common import (
    auth_filter,
    class_demand,
    exclusions_from,
    pack_items,
    scale_to_budget,
    sort_class,
    spillover_pack,
    take_protected,
    used_with_overhead,
    waterfill_with_ceilings,
)
from benchmark.config import AllocConfig, ELASTIC
from benchmark.schema import AllocationResult, ContextItem
from benchmark.tokenizers import Tokenizer


class WaterfillAllocator:
    name = "waterfill"
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

        notes = ["protected first", "elastic floors", "weighted water-fill", "ceilings"]
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
        for cls in ELASTIC:
            by_cls[cls] = sort_class(by_cls[cls], cls, cfg)

        elastic_demand = {cls: demand.get(cls, 0) for cls in ELASTIC}
        floors = {
            cls: min(elastic_demand[cls], int(cfg.floors[cls] * remaining)) for cls in ELASTIC
        }
        if sum(floors.values()) > remaining:
            floors = scale_to_budget(floors, remaining)
            notes.append("floors scaled because they exceeded remaining budget")

        leftover_after_floors = remaining - sum(floors.values())
        demand_after = {cls: max(0, elastic_demand[cls] - floors[cls]) for cls in ELASTIC}
        ceilings = {cls: int(cfg.ceilings[cls] * remaining) for cls in ELASTIC}
        # Floor already reserved; extra cannot push a class past its ceiling.
        extra_cap_demand = {
            cls: min(demand_after[cls], max(0, ceilings[cls] - floors[cls])) for cls in ELASTIC
        }
        extra = waterfill_with_ceilings(
            extra_cap_demand, cfg.weights, leftover_after_floors, extra_cap_demand
        )
        # extra_cap_demand used as ceiling so extra itself cannot exceed remaining demand/cap
        for cls in ELASTIC:
            class_budget[cls] = floors[cls] + extra.get(cls, 0)

        leftover_by_class: dict[str, list[ContextItem]] = {}
        for cls in ELASTIC:
            packed, packed_used, rest = pack_items(by_cls[cls], class_budget[cls], cfg, tokenizer)
            selected.extend(packed)
            leftover_by_class[cls] = rest
            used += packed_used

        hole = budget - used
        already = used_with_overhead(selected, cfg)
        # Spillover may use unused tokens but still respects ceilings.
        extra_sel, extra_used, leftover_by_class = spillover_pack(
            leftover_by_class,
            hole,
            tuple(sorted(ELASTIC, key=lambda c: (-cfg.weights[c], c))),
            cfg,
            tokenizer,
            ceilings=ceilings,
            already_used=already,
        )
        selected.extend(extra_sel)
        used += extra_used
        if extra_sel:
            notes.append("spillover consumed packing leftover under ceilings")

        leftover_items = [it for rest in leftover_by_class.values() for it in rest]
        excluded.extend(exclusions_from(leftover_items, "class_budget_exhausted"))
        excluded = _dedupe_excl(excluded)
        return AllocationResult(
            allocator=self.name,
            allocator_version=self.version,
            selected=selected,
            excluded=excluded,
            class_demand=demand,
            class_budget=class_budget,
            class_used=used_with_overhead(selected, cfg),
            failed_closed=False,
            failure_reason=None,
            notes=notes,
        )


def _dedupe_excl(excluded):
    seen = set()
    out = []
    for ex in excluded:
        if ex.id in seen:
            continue
        seen.add(ex.id)
        out.append(ex)
    return out
