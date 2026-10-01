"""Run the allocator comparison matrix.

    python -m benchmark.data.generate
    python -m benchmark.run_benchmarks
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from benchmark.allocators import get_allocators
from benchmark.config import DEFAULT_CONFIG
from benchmark.data.generate import build_all, load_workloads, write_workloads
from benchmark.engine import run_case
from benchmark.profiles import PROFILES
from benchmark.tokenizers import default_tokenizer, mismatch_tokenizer

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def ensure_workloads(tok):
    workloads = load_workloads()
    if workloads:
        return workloads
    print("sample_data missing; generating...")
    workloads = build_all(tok)
    write_workloads(workloads, tok)
    return workloads


def flatten(row: dict) -> dict:
    flat = {}
    for k, v in row.items():
        if isinstance(v, dict):
            flat[k] = json.dumps(v, sort_keys=True)
        elif isinstance(v, bool):
            flat[k] = v
        else:
            flat[k] = v
    return flat


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in rows:
            w.writerow(flatten(row))


def summarize(rows: list[dict]) -> list[dict]:
    """Mean metrics by allocator x profile, plus per-workload evidence recall."""
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["allocator"], row["profile"])].append(row)
    out = []
    for (allocator, profile), items in sorted(groups.items()):
        n = len(items)
        def avg(key):
            return round(sum(float(r[key]) for r in items) / n, 4)

        out.append(
            {
                "allocator": allocator,
                "profile": profile,
                "n": n,
                "mean_evidence_recall": avg("critical_evidence_recall"),
                "mean_must_survive": avg("must_survive_retention"),
                "mean_protected_retention": avg("protected_retention"),
                "mean_utilization": avg("utilization"),
                "mean_starved_classes": avg("n_starved_classes"),
                "sum_leakage": sum(int(r["unauthorized_leakage"]) for r in items),
                "overflow_count": sum(1 for r in items if r["overflow"]),
                "mismatch_overflow_count": sum(1 for r in items if r["mismatch_overflow"]),
                "failed_closed_count": sum(1 for r in items if r["failed_closed"]),
                "mean_allocate_ms": avg("allocate_ms"),
                "mean_cost_usd": round(sum(float(r["estimated_cost_usd"]) for r in items) / n, 6),
            }
        )
    return out


def evidence_table(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        out.append(
            {
                "workload": row["workload"],
                "profile": row["profile"],
                "allocator": row["allocator"],
                "evidence_recall": row["critical_evidence_recall"],
                "evidence_missing": row["evidence_missing"],
                "must_survive_retention": row["must_survive_retention"],
                "starvation": row["class_starvation"],
                "utilization": row["utilization"],
                "leakage": row["unauthorized_leakage"],
                "overflow": row["overflow"],
                "mismatch_overflow": row["mismatch_overflow"],
                "failed_closed": row["failed_closed"],
            }
        )
    return out


def maybe_plot(rows: list[dict], path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:
        print(f"skipping plots: {exc}")
        return

    workloads = sorted({r["workload"] for r in rows})
    allocators = sorted({r["allocator"] for r in rows})
    # Use 64k as the representative chart if present, else first profile.
    profiles = [p for p in ("64k", "32k", "128k", "256k") if any(r["profile"] == p for r in rows)]
    profile = profiles[0] if profiles else rows[0]["profile"]
    subset = [r for r in rows if r["profile"] == profile]

    x = np.arange(len(workloads))
    width = 0.2
    fig, ax = plt.subplots(figsize=(16, 6))
    for i, allocator in enumerate(allocators):
        ys = []
        for wl in workloads:
            hit = [r["critical_evidence_recall"] for r in subset if r["workload"] == wl and r["allocator"] == allocator]
            ys.append(hit[0] if hit else 0.0)
        ax.bar(x + i * width, ys, width, label=allocator)
    ax.set_xticks(x + width * (len(allocators) - 1) / 2)
    ax.set_xticklabels(workloads, rotation=40, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("critical evidence recall")
    ax.set_title(f"Evidence recall by allocator ({profile} window)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"wrote {path}")


def replay_check(rows_a: list[dict], rows_b: list[dict]) -> dict:
    mism = []
    index_b = {(r["workload"], r["profile"], r["allocator"]): r for r in rows_b}
    for r in rows_a:
        key = (r["workload"], r["profile"], r["allocator"])
        other = index_b[key]
        if r["prompt_hash"] != other["prompt_hash"] or r["selection_hash"] != other["selection_hash"]:
            mism.append(key)
    return {"pairs": len(rows_a), "mismatches": mism, "ok": not mism}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="*", default=list(PROFILES.keys()))
    parser.add_argument("--workloads", nargs="*", default=None)
    parser.add_argument("--skip-generate", action="store_true")
    args = parser.parse_args()

    RESULTS.mkdir(parents=True, exist_ok=True)
    tok = default_tokenizer()
    other = mismatch_tokenizer()
    cfg = DEFAULT_CONFIG
    if args.skip_generate:
        workloads = load_workloads()
        if not workloads:
            raise SystemExit("no workloads on disk; rerun without --skip-generate")
    else:
        workloads = ensure_workloads(tok)
    if args.workloads:
        workloads = [w for w in workloads if w.id in set(args.workloads)]
    profiles = [PROFILES[name] for name in args.profiles if name in PROFILES]
    allocators = get_allocators()

    print(
        f"matrix: {len(workloads)} workloads x {len(profiles)} profiles x {len(allocators)} allocators"
    )
    rows = []
    for workload in workloads:
        for profile in profiles:
            for allocator in allocators:
                row = run_case(workload, profile, allocator, tok, cfg, mismatch_tokenizer=other)
                rows.append(row)
                flag = ""
                if row["overflow"]:
                    flag += " OVERFLOW"
                if row["unauthorized_leakage"]:
                    flag += " LEAK"
                if row["critical_evidence_recall"] < 1 and row["evidence_missing"]:
                    flag += " MISS"
                print(
                    f"  {workload.id:22s} {profile.name:5s} {allocator.name:12s} "
                    f"tok={row['assembled_tokens']:6d}/{row['input_budget']:<6d} "
                    f"recall={row['critical_evidence_recall']:.2f} "
                    f"surv={row['must_survive_retention']:.2f} "
                    f"util={row['utilization']:.2f}{flag}"
                )

    # Deterministic replay: run the full matrix a second time, compare hashes.
    print("replay pass...")
    rows2 = []
    for workload in workloads:
        for profile in profiles:
            for allocator in allocators:
                rows2.append(run_case(workload, profile, allocator, tok, cfg, mismatch_tokenizer=other))
    replay = replay_check(rows, rows2)
    print(f"replay ok={replay['ok']} pairs={replay['pairs']} mismatches={len(replay['mismatches'])}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "generated_at": stamp,
        "tokenizer": tok.name,
        "mismatch_tokenizer": other.name,
        "config": {
            "quotas": cfg.quotas,
            "floors": cfg.floors,
            "weights": cfg.weights,
            "ceilings": cfg.ceilings,
            "per_item_overhead": cfg.per_item_overhead,
            "assembly_reserve": cfg.assembly_reserve,
            "pin_oldest_history": cfg.pin_oldest_history,
        },
        "replay": {"ok": replay["ok"], "n_mismatches": len(replay["mismatches"])},
        "rows": rows,
        "summary": summarize(rows),
        "evidence": evidence_table(rows),
    }
    json_path = RESULTS / "benchmark.json"
    csv_path = RESULTS / "benchmark.csv"
    summary_path = RESULTS / "summary.csv"
    evidence_path = RESULTS / "evidence.csv"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_csv(csv_path, rows)
    write_csv(summary_path, payload["summary"])
    write_csv(evidence_path, payload["evidence"])
    maybe_plot(rows, RESULTS / "evidence_recall_64k.png")
    print(f"wrote {json_path}")
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")
    print(f"wrote {evidence_path}")


if __name__ == "__main__":
    main()
