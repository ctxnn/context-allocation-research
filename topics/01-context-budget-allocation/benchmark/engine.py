"""Run one workload through tokenize -> allocate -> assemble -> metrics."""

from __future__ import annotations

import time
from copy import deepcopy

from benchmark.assemble import assemble, prompt_hash, selected_ids_in_assembly_order, selection_hash
from benchmark.config import AllocConfig
from benchmark.metrics import evaluate, replay_row
from benchmark.schema import ContextItem, ModelProfile, Workload
from benchmark.tokenizers import Tokenizer


def tokenize_items(items: list[ContextItem], tokenizer: Tokenizer) -> list[ContextItem]:
    out = []
    for item in items:
        cloned = deepcopy(item)
        cloned.token_count = tokenizer.count(cloned.content)
        out.append(cloned)
    return out


def run_case(
    workload: Workload,
    profile: ModelProfile,
    allocator,
    tokenizer: Tokenizer,
    cfg: AllocConfig,
    mismatch_tokenizer: Tokenizer | None = None,
) -> dict:
    t0 = time.perf_counter()
    items = tokenize_items(workload.items, tokenizer)
    tokenize_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    alloc_budget = profile.input_budget - cfg.assembly_reserve
    result = allocator.allocate(items, alloc_budget, workload.tenant_id, cfg, tokenizer)
    allocate_ms = (time.perf_counter() - t1) * 1000.0

    t2 = time.perf_counter()
    assembled = assemble(result.selected)
    assemble_ms = (time.perf_counter() - t2) * 1000.0
    assembled_tokens = tokenizer.count(assembled)

    mismatch_tokens = None
    mismatch_name = None
    if mismatch_tokenizer is not None:
        mismatch_name = mismatch_tokenizer.name
        mismatch_tokens = mismatch_tokenizer.count(assembled)

    metrics = evaluate(
        workload=workload,
        profile=profile,
        result=result,
        assembled=assembled,
        assembled_tokens=assembled_tokens,
        tokenizer_name=tokenizer.name,
        tokenize_ms=tokenize_ms,
        allocate_ms=allocate_ms,
        assemble_ms=assemble_ms,
        cfg=cfg,
        mismatch_tokens=mismatch_tokens,
        mismatch_tokenizer_name=mismatch_name,
    )
    ordered = selected_ids_in_assembly_order(result.selected)
    truncated = {s.id: s.token_count for s in result.selected if s.truncated}
    hashes = replay_row(
        prompt_hash(assembled),
        selection_hash(result.allocator, result.allocator_version, ordered, truncated),
        ordered,
    )
    metrics.update(hashes)
    metrics["failed_closed"] = result.failed_closed
    return metrics
