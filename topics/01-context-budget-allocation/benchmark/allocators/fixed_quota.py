"""Protected fixed quotas with deterministic spillover.

After the protected lane, each elastic class gets a fixed share of leftover
budget. Unused share spills in a declared order to classes that still have
items.
"""

from __future__ import annotations

from benchmark.allocators.common import (
    auth_filter,
    class_demand,
    exclusions_from,
    pack_items,
    sort_class,
    spillover_pack,
    split_integer,
    take_protected,
    used_with_overhead,
)
from benchmark.config import AllocConfig, ELASTIC
from benchmark.schema import AllocationResult, ContextItem
from benchmark.tokenizers import Tokenizer


class FixedQuotaAllocator:
    name = "fixed_quota"
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

        notes = ["protected first", "fixed elastic quotas", "spillover in spillover_order"]
        if failed:
            rest = [it for it in authorized if it.id not in {s.id for s in selected}]
            excluded.extend(exclusions_from(rest, "failed_closed"))
            # de-dup excluded ids
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

        quotas = split_integer(remaining, cfg.quotas, ELASTIC)
        leftover_by_class: dict[str, list[ContextItem]] = {}
        for cls in ELASTIC:
            class_budget[cls] = quotas[cls]
            packed, packed_used, rest = pack_items(by_cls[cls], quotas[cls], cfg, tokenizer)
            selected.extend(packed)
            leftover_by_class[cls] = rest
            used += packed_used

        hole = budget - used
        already = used_with_overhead(selected, cfg)
        extra, extra_used, leftover_by_class = spillover_pack(
            leftover_by_class,
            hole,
            cfg.spillover_order,
            cfg,
            tokenizer,
            ceilings=None,
            already_used=already,
        )
        selected.extend(extra)
        used += extra_used
        if extra:
            notes.append("spillover consumed packing leftover")

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
