"""Metrics that help choose an allocator.

Utilization is recorded, but more tokens are not automatically better.
"""

from __future__ import annotations

from benchmark.config import AllocConfig, ELASTIC
from benchmark.schema import (
    PROTECTED_CLASSES,
    AllocationResult,
    ContextItem,
    GroundTruth,
    ModelProfile,
    Workload,
)
from benchmark.tokenizers import Tokenizer


def evaluate(
    workload: Workload,
    profile: ModelProfile,
    result: AllocationResult,
    assembled: str,
    assembled_tokens: int,
    tokenizer_name: str,
    tokenize_ms: float,
    allocate_ms: float,
    assemble_ms: float,
    cfg: AllocConfig,
    mismatch_tokens: int | None = None,
    mismatch_tokenizer_name: str | None = None,
) -> dict:
    items = workload.items
    gt: GroundTruth = workload.ground_truth
    selected_ids = [s.id for s in result.selected]
    selected_set = set(selected_ids)
    item_by_id = {it.id: it for it in items}

    candidate_tokens = sum((it.token_count or 0) + cfg.per_item_overhead for it in items)
    authorized_items = [
        it
        for it in items
        if it.tenant_id in {workload.tenant_id, cfg.platform_tenant_id}
    ]
    authorized_tokens = sum((it.token_count or 0) + cfg.per_item_overhead for it in authorized_items)
    selected_tokens = sum(s.token_count + cfg.per_item_overhead for s in result.selected)
    budget = profile.input_budget
    unused = budget - assembled_tokens
    utilization = assembled_tokens / budget if budget else 0.0

    prot_auth = [
        it
        for it in authorized_items
        if it.protected or it.cls in PROTECTED_CLASSES
    ]
    prot_kept = [it for it in prot_auth if it.id in selected_set]
    protected_retention = (len(prot_kept) / len(prot_auth)) if prot_auth else 1.0

    must_survive = gt.must_survive_ids
    survive_kept = [i for i in must_survive if i in selected_set]
    must_survive_retention = (len(survive_kept) / len(must_survive)) if must_survive else 1.0

    evidence = gt.critical_evidence_ids
    evidence_kept = [i for i in evidence if i in selected_set]
    evidence_recall = (len(evidence_kept) / len(evidence)) if evidence else 1.0

    leaked = [i for i in gt.must_never_ids if i in selected_set]
    tenant_leaks = [
        s.id
        for s in result.selected
        if s.tenant_id not in {workload.tenant_id, cfg.platform_tenant_id}
    ]
    unauthorized_leakage = len(set(leaked) | set(tenant_leaks))

    starved = []
    for cls in ELASTIC:
        if result.class_demand.get(cls, 0) > 0 and result.class_used.get(cls, 0) <= 0:
            starved.append(cls)

    remaining_after_prot = max(
        0,
        budget
        - cfg.assembly_reserve
        - sum(
            result.class_used.get(cls, 0)
            for cls in PROTECTED_CLASSES
        ),
    )
    floor_violations = []
    if result.allocator in {"waterfill", "utility"} and not result.failed_closed:
        for cls in ELASTIC:
            demand = result.class_demand.get(cls, 0)
            floor = min(demand, int(cfg.floors[cls] * remaining_after_prot))
            # Packing holes can land slightly under the token floor even when
            # the class was granted that budget. Count a violation only if the
            # granted budget itself is under the floor.
            granted = result.class_budget.get(cls, 0)
            if floor > 0 and granted < floor:
                floor_violations.append(cls)

    overflow = assembled_tokens > budget
    mismatch_overflow = (
        mismatch_tokens is not None and mismatch_tokens > budget
    )

    truncated = [s.id for s in result.selected if s.truncated]
    estimated_cost_usd = (assembled_tokens / 1_000_000.0) * profile.cost_per_mtok_input

    selected_by_class = {}
    for s in result.selected:
        selected_by_class[s.cls] = selected_by_class.get(s.cls, 0) + 1

    return {
        "workload": workload.id,
        "workload_name": workload.name,
        "shape": workload.shape,
        "allocator": result.allocator,
        "allocator_version": result.allocator_version,
        "profile": profile.name,
        "tokenizer": tokenizer_name,
        "context_limit": profile.context_limit,
        "output_reserve": profile.output_reserve,
        "tool_reserve": profile.tool_reserve,
        "input_budget": budget,
        "n_candidates": len(items),
        "n_authorized": len(authorized_items),
        "n_selected": len(result.selected),
        "candidate_tokens": candidate_tokens,
        "authorized_tokens": authorized_tokens,
        "selected_item_tokens": selected_tokens,
        "assembled_tokens": assembled_tokens,
        "unused_tokens": unused,
        "utilization": round(utilization, 4),
        "protected_retention": round(protected_retention, 4),
        "must_survive_retention": round(must_survive_retention, 4),
        "critical_evidence_recall": round(evidence_recall, 4),
        "evidence_kept": ",".join(evidence_kept),
        "evidence_missing": ",".join(i for i in evidence if i not in selected_set),
        "class_starvation": ",".join(starved),
        "n_starved_classes": len(starved),
        "floor_violations": ",".join(floor_violations),
        "unauthorized_leakage": unauthorized_leakage,
        "leaked_ids": ",".join(sorted(set(leaked) | set(tenant_leaks))),
        "overflow": overflow,
        "failed_closed": result.failed_closed,
        "failure_reason": result.failure_reason or "",
        "n_truncated": len(truncated),
        "truncated_ids": ",".join(truncated),
        "tokenize_ms": round(tokenize_ms, 3),
        "allocate_ms": round(allocate_ms, 3),
        "assemble_ms": round(assemble_ms, 3),
        "estimated_cost_usd": round(estimated_cost_usd, 6),
        "mismatch_tokenizer": mismatch_tokenizer_name or "",
        "mismatch_tokens": mismatch_tokens if mismatch_tokens is not None else "",
        "mismatch_overflow": mismatch_overflow,
        "selected_by_class": selected_by_class,
        "class_demand": result.class_demand,
        "class_budget": result.class_budget,
        "class_used": result.class_used,
        "notes": " | ".join(result.notes),
    }


def replay_row(prompt_h: str, selection_h: str, ordered_ids: list[str]) -> dict:
    return {
        "prompt_hash": prompt_h,
        "selection_hash": selection_h,
        "ordered_ids": ",".join(ordered_ids),
    }
