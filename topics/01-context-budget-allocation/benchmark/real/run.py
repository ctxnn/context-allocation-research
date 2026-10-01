from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from benchmark.allocators import get_allocators
from benchmark.assemble import (
    assemble,
    prompt_hash,
    selected_ids_in_assembly_order,
    selection_hash,
)
from benchmark.config import DEFAULT_CONFIG
from benchmark.engine import tokenize_items
from benchmark.metrics import evaluate
from benchmark.real.artifacts import (
    append_jsonl,
    atomic_write_json,
    load_jsonl,
    read_json,
    sha256_json,
    utc_now,
)
from benchmark.real.constants import (
    CAPTURE_PATH,
    COST_STOP_BUFFER_USD,
    DEFAULT_COST_CAP_USD,
    DEFAULT_MODEL,
    LEDGER_PATH,
    MAX_OUTPUT_TOKENS,
    PROFILE_256K_SLICE,
    REAL_PROFILES,
    RUN_PATH,
    TOOL_SLICE_WORKLOADS,
    WORKLOAD_PATH,
)
from benchmark.real.grading import grade
from benchmark.real.http import PublicAPIClient
from benchmark.real.openai_api import OpenAIBackend, estimate_cost
from benchmark.real.security import redact
from benchmark.real.tools import TOOL_SCHEMAS, ToolExecutor
from benchmark.real.workloads import build_workloads, candidate_hash
from benchmark.tokenizers import TiktokenTokenizer


def build_schedule(
    workloads: list, allocators: list
) -> list[tuple[Any, Any, Any, bool]]:
    schedule = []
    for workload in workloads:
        for profile_name in ("32k", "64k", "128k"):
            for allocator in allocators:
                schedule.append(
                    (workload, REAL_PROFILES[profile_name], allocator, False)
                )
        if workload.id in PROFILE_256K_SLICE:
            for allocator in allocators:
                schedule.append((workload, REAL_PROFILES["256k"], allocator, False))
    by_id = {workload.id: workload for workload in workloads}
    for workload_id in TOOL_SLICE_WORKLOADS:
        for allocator in allocators:
            schedule.append((by_id[workload_id], REAL_PROFILES["64k"], allocator, True))
    return schedule


def preflight_cost(schedule: list[tuple[Any, Any, Any, bool]]) -> float:
    total = 0.0
    for _, profile, _, tool_mode in schedule:
        calls = 2 if tool_mode else 1
        total += calls * estimate_cost(profile.input_budget, MAX_OUTPUT_TOKENS)
    return total


def _cell_id(
    workload: Any,
    profile: Any,
    allocator: Any,
    tool_mode: bool,
    model: str,
    capture_hash: str,
) -> str:
    mode = "tools" if tool_mode else "context"
    return f"{capture_hash[:12]}:{model}:{workload.id}:{profile.name}:{allocator.name}:{mode}"


def _allocate(
    workload: Any, profile: Any, allocator: Any, tokenizer: Any
) -> tuple[str, list[str], dict[str, Any]]:
    started = time.perf_counter()
    tokenized_items = tokenize_items(workload.items, tokenizer)
    tokenize_ms = (time.perf_counter() - started) * 1000.0
    tokenized_workload = replace(workload, items=tokenized_items)
    alloc_started = time.perf_counter()
    result = allocator.allocate(
        tokenized_items,
        profile.input_budget - DEFAULT_CONFIG.assembly_reserve,
        workload.tenant_id,
        DEFAULT_CONFIG,
        tokenizer,
    )
    allocate_ms = (time.perf_counter() - alloc_started) * 1000.0
    assemble_started = time.perf_counter()
    prompt = assemble(result.selected)
    assemble_ms = (time.perf_counter() - assemble_started) * 1000.0
    assembled_tokens = tokenizer.count(prompt)
    metrics = evaluate(
        workload=tokenized_workload,
        profile=profile,
        result=result,
        assembled=prompt,
        assembled_tokens=assembled_tokens,
        tokenizer_name=tokenizer.name,
        tokenize_ms=tokenize_ms,
        allocate_ms=allocate_ms,
        assemble_ms=assemble_ms,
        cfg=DEFAULT_CONFIG,
    )
    ordered = selected_ids_in_assembly_order(result.selected)
    metrics.update(
        {
            "prompt_hash": prompt_hash(prompt),
            "selection_hash": selection_hash(
                result.allocator,
                result.allocator_version,
                ordered,
                {
                    item.id: item.token_count
                    for item in result.selected
                    if item.truncated
                },
            ),
            "ordered_ids": ",".join(ordered),
        }
    )
    return prompt, ordered, metrics


def _bounded_tool_output(value: Any, max_chars: int = 100_000) -> Any:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False)
    if len(encoded) <= max_chars:
        return value
    return {
        "truncated": True,
        "original_sha256": sha256_json(value),
        "original_chars": len(encoded),
        "content_prefix": encoded[:max_chars],
    }


def _summarize(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, bool], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (row["allocator"], row["profile"], row["tool_mode"]), []
        ).append(row)
    summary = []
    for (allocator, profile, tool_mode), group in sorted(groups.items()):
        n = len(group)
        summary.append(
            {
                "allocator": allocator,
                "profile": profile,
                "tool_mode": tool_mode,
                "cells": n,
                "answer_accuracy": round(
                    sum(row["answer_exact"] for row in group) / n, 4
                ),
                "source_recall": round(
                    sum(row["required_source_recall"] for row in group) / n, 4
                ),
                "citation_validity": round(
                    sum(row["citation_validity"] for row in group) / n, 4
                ),
                "evidence_selection_recall": round(
                    sum(row["critical_evidence_recall"] for row in group) / n, 4
                ),
                "tool_choice_accuracy": round(
                    sum(row["tool_choice_correct"] for row in group) / n, 4
                ),
                "mean_cost_usd": round(
                    sum(row["model_cost_usd"] for row in group) / n, 6
                ),
                "failures": sum(1 for row in group if row.get("status") != "complete"),
            }
        )
    return summary


def _write_run(
    rows: list[dict[str, Any]], capture: dict[str, Any], model: str, preflight: float
) -> None:
    complete = [row for row in rows if row.get("status") == "complete"]
    model_cost = sum(row.get("model_cost_usd", 0.0) for row in rows)
    rag_cost = float(capture["rag"].get("embedding_cost_usd", 0.0))
    payload = {
        "schema_version": 1,
        "benchmark": "real-api-context-allocation",
        "generated_at": utc_now(),
        "model": model,
        "capture_sha256": capture["capture_sha256"],
        "vector_store_id": capture["rag"]["vector_store_id"],
        "rag_provider": capture["rag"].get("provider"),
        "rag_model": capture["rag"].get("embedding_model"),
        "rag_input_tokens": capture["rag"].get("embedding_input_tokens", 0),
        "rag_cost_usd": round(rag_cost, 8),
        "preflight_max_cost_usd": round(preflight, 6),
        "actual_cost_usd": round(model_cost, 6),
        "actual_total_api_cost_usd": round(model_cost + rag_cost, 8),
        "rows": complete,
        "failures": [row for row in rows if row.get("status") == "error"],
        "summary": _summarize(complete),
    }
    atomic_write_json(RUN_PATH, redact(payload))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Benchmark 2 with real OpenAI Responses API calls"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="required acknowledgement for paid API calls",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-cost-usd", type=float, default=DEFAULT_COST_CAP_USD)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--capture", type=Path, default=CAPTURE_PATH)
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("runner makes paid OpenAI API calls; pass --live")
    if args.max_cost_usd <= COST_STOP_BUFFER_USD:
        raise SystemExit("max cost must be larger than the $0.50 safety buffer")
    if not args.capture.exists():
        raise SystemExit(
            f"missing {args.capture}; run python -m benchmark.real.capture --live"
        )
    if args.ledger.exists() and not args.resume:
        raise SystemExit(
            f"ledger already exists at {args.ledger}; pass --resume or move it"
        )

    capture = read_json(args.capture)
    tokenizer = TiktokenTokenizer(name="o200k_base", encoding_name="o200k_base")
    workloads = build_workloads(capture, tokenizer)
    allocators = get_allocators()
    schedule = build_schedule(workloads, allocators)
    preflight = preflight_cost(schedule)
    stop_at = args.max_cost_usd - COST_STOP_BUFFER_USD
    if preflight > stop_at:
        raise SystemExit(
            f"preflight worst case ${preflight:.4f} exceeds scheduling cap ${stop_at:.2f}; "
            "reduce the matrix or raise the explicit cap"
        )

    workload_manifest = {
        "capture_sha256": capture["capture_sha256"],
        "tokenizer": tokenizer.name,
        "workloads": [
            {
                "id": workload.id,
                "candidate_hash": candidate_hash(workload),
                "candidate_tokens": sum(
                    tokenizer.count(item.content) + 16 for item in workload.items
                ),
                "required_source_ids": workload.ground_truth.required_source_ids,
            }
            for workload in workloads
        ],
    }
    atomic_write_json(WORKLOAD_PATH, workload_manifest)

    prior = load_jsonl(args.ledger)
    completed = {row["cell_id"] for row in prior if row.get("status") == "complete"}
    spent = sum(float(row.get("model_cost_usd", 0.0)) for row in prior)
    backend = OpenAIBackend()
    tool_executor = ToolExecutor(
        PublicAPIClient(), cache=dict(capture["tool_cache"]), live=False
    )

    print(
        f"schedule={len(schedule)} preflight=${preflight:.4f} stop_at=${stop_at:.2f} resume={len(completed)}"
    )
    for workload, profile, allocator, tool_mode in schedule:
        cell_id = _cell_id(
            workload,
            profile,
            allocator,
            tool_mode,
            args.model,
            capture["capture_sha256"],
        )
        if cell_id in completed:
            continue
        prompt, selected_ids, structural = _allocate(
            workload, profile, allocator, tokenizer
        )
        calls = 2 if tool_mode else 1
        projected = estimate_cost(tokenizer.count(prompt), MAX_OUTPUT_TOKENS) * calls
        if spent + projected > stop_at:
            print(
                f"stopping before {cell_id}: projected spend would exceed ${stop_at:.2f}"
            )
            break

        if tool_mode:
            expected_name = workload.ground_truth.expected_tool_name
            expected_args = workload.ground_truth.expected_tool_args
            prompt += (
                "\n[TOOL EVALUATION]\n"
                f"Call {expected_name} exactly once with canonical arguments "
                f"{json.dumps(expected_args, sort_keys=True)} before answering.\n"
            )
        tool_execution_ok = True

        def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
            nonlocal tool_execution_ok
            try:
                return _bounded_tool_output(
                    tool_executor.execute(name, arguments).output
                )
            except Exception:
                tool_execution_ok = False
                raise

        try:
            model_result = backend.answer(
                model=args.model,
                prompt=prompt,
                tools=TOOL_SCHEMAS if tool_mode else None,
                execute_tool=execute_tool if tool_mode else None,
            )
            grades = grade(
                answer=model_result.answer,
                source_ids=model_result.source_ids,
                selected_ids=selected_ids,
                ground_truth=workload.ground_truth,
                tool_calls=model_result.tool_calls,
                tool_execution_ok=tool_execution_ok,
            )
            row = {
                "cell_id": cell_id,
                "status": "complete",
                "tool_mode": tool_mode,
                "candidate_hash": candidate_hash(workload),
                **structural,
                **grades,
                "response_id": model_result.response_id,
                "model_input_tokens": model_result.input_tokens,
                "model_output_tokens": model_result.output_tokens,
                "model_cost_usd": round(model_result.cost_usd, 8),
                "model_latency_ms": round(model_result.latency_ms, 3),
                "provider_status": model_result.raw_status,
                "tool_calls": model_result.tool_calls,
                "recorded_at": utc_now(),
            }
            spent += model_result.cost_usd
            append_jsonl(args.ledger, redact(row))
            prior.append(row)
            print(
                f"{workload.id:22s} {profile.name:4s} {allocator.name:12s} "
                f"tools={tool_mode!s:5s} answer={int(grades['answer_exact'])} "
                f"evidence={structural['critical_evidence_recall']:.2f} spent=${spent:.4f}"
            )
        # Provider/transport/parse failures all become resumable ledger rows.
        except Exception as exc:  # noqa: BLE001
            known_cost = float(getattr(exc, "cost_usd", 0.0))
            spent += known_cost
            row = {
                "cell_id": cell_id,
                "status": "error",
                "workload": workload.id,
                "profile": profile.name,
                "allocator": allocator.name,
                "tool_mode": tool_mode,
                "model_input_tokens": int(getattr(exc, "input_tokens", 0)),
                "model_output_tokens": int(getattr(exc, "output_tokens", 0)),
                "model_cost_usd": round(known_cost, 8),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "recorded_at": utc_now(),
            }
            append_jsonl(args.ledger, redact(row))
            prior.append(row)
            print(f"ERROR {cell_id}: {type(exc).__name__}: {exc}")

    _write_run(prior, capture, args.model, preflight)
    print(f"wrote checkpointed results to {RUN_PATH}; recorded cost=${spent:.4f}")


if __name__ == "__main__":
    main()
