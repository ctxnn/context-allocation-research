"""Harness-style recency allocator.

After the protected lane, conversation-like classes (history, tool results,
agent messages) are packed newest-first as one stream. Knowledge classes
(RAG, memory) fill whatever remains, by relevance.

No elastic floors or ceilings. This is a credible "keep the live thread"
policy, not a crippled strawman. It will starve knowledge under chat pressure
and can be dominated by a huge recent tool dump — that is the point of
including it.
"""

from __future__ import annotations

from benchmark.allocators.common import (
    auth_filter,
    class_demand,
    exclusions_from,
    pack_items,
    take_protected,
    used_with_overhead,
)
from benchmark.config import AllocConfig, ELASTIC
from benchmark.schema import AllocationResult, ContextItem
from benchmark.tokenizers import Tokenizer

LIVE_CLASSES = ("history", "tool_result", "agent")
KNOWLEDGE_CLASSES = ("rag", "memory")


class RecencyAllocator:
    name = "recency"
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

        notes = [
            "protected first",
            "live classes newest-first (no oldest-history pin)",
            "knowledge fills remainder by relevance",
            "no elastic floors/ceilings",
        ]
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

        live = [it for it in elastic if it.cls in LIVE_CLASSES]
        knowledge = [it for it in elastic if it.cls in KNOWLEDGE_CLASSES]

        # Pure recency over the live stream. Sequence is a shared clock in the generator.
        live.sort(key=lambda it: (-it.sequence, it.cls, it.id))
        packed_live, used_live, rest_live = pack_items(
            live, remaining, cfg, tokenizer, on_miss="stop"
        )
        selected.extend(packed_live)
        used += used_live
        remaining = budget - used

        knowledge.sort(key=lambda it: (-(it.relevance or 0.0), it.sequence, it.id))
        packed_k, used_k, rest_k = pack_items(knowledge, remaining, cfg, tokenizer)
        selected.extend(packed_k)
        used += used_k

        for cls in ELASTIC:
            class_budget[cls] = remaining if cls in KNOWLEDGE_CLASSES else (budget - (used - used_live - used_k))
        # More honest: live had `budget-protected` available; knowledge had what live left.
        prot_used = sum(
            s.token_count + cfg.per_item_overhead
            for s in selected
            if s.cls not in ELASTIC
        )
        class_budget = {cls: 0 for cls in demand}
        for s in selected:
            if s.cls not in ELASTIC:
                class_budget[s.cls] = class_budget.get(s.cls, 0) + s.token_count + cfg.per_item_overhead
        live_budget = budget - prot_used
        class_budget["history"] = live_budget
        class_budget["tool_result"] = live_budget
        class_budget["agent"] = live_budget
        class_budget["rag"] = remaining + used_k
        class_budget["memory"] = remaining + used_k

        excluded.extend(exclusions_from(rest_live, "recency_dropped"))
        excluded.extend(exclusions_from(rest_k, "knowledge_remainder_exhausted"))
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
