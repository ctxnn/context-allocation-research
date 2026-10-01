from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from benchmark.real.artifacts import read_json
from benchmark.real.constants import RESULTS_DIR, RUN_PATH


def _csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in fields})


def _percent(value: float) -> str:
    return f"{100 * value:.1f}%"


def build_markdown(payload: dict[str, Any]) -> str:
    summary = sorted(
        payload["summary"],
        key=lambda row: (
            -row["answer_accuracy"],
            -row["source_recall"],
            row["mean_cost_usd"],
        ),
    )
    rag_provider = payload.get("rag_provider", "openai_vector_store")
    rag_boundary = (
        "- RAG ranks and scores came from OpenAI `text-embedding-3-small` vectors "
        "with deterministic local cosine ranking; no query rewriting was used."
        if rag_provider == "openai_embeddings"
        else "- RAG ranks and scores came from explicit OpenAI vector-store search "
        "with query rewriting disabled."
    )
    lines = [
        "# Benchmark 2 — Real-API Context Allocation",
        "",
        f"Model: `{payload['model']}`  ",
        f"Frozen capture: `{payload['capture_sha256']}`  ",
        f"Completed cells: **{len(payload['rows'])}**  ",
        f"Recorded model cost: **${payload['actual_cost_usd']:.4f}**  ",
        f"Recorded RAG cost: **${payload.get('rag_cost_usd', 0.0):.6f}**  ",
        f"Recorded total API cost: **${payload.get('actual_total_api_cost_usd', payload['actual_cost_usd']):.4f}**  ",
        f"Failed cells: **{len(payload.get('failures', []))}**",
        "",
        "## Scorecard",
        "",
        "| Allocator | Profile | Mode | Cells | Exact answer | Required-source recall | Citation validity | Evidence selected | Tool choice | Mean cost |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            "| {allocator} | {profile} | {mode} | {cells} | {answer} | {source} | {citation} | {selection} | {tool} | ${cost:.6f} |".format(
                allocator=row["allocator"],
                profile=row["profile"],
                mode="tool" if row["tool_mode"] else "context",
                cells=row["cells"],
                answer=_percent(row["answer_accuracy"]),
                source=_percent(row["source_recall"]),
                citation=_percent(row["citation_validity"]),
                selection=_percent(row["evidence_selection_recall"]),
                tool=_percent(row["tool_choice_accuracy"]),
                cost=row["mean_cost_usd"],
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundaries",
            "",
            "- The corpus is frozen public technical material, not private production traces.",
            "- `cross_tenant` measures public source-scope filtering; it does not prove confidential tenant isolation.",
            rag_boundary,
            "- Tool outputs were captured live once and identical calls were replayed so every allocator saw the same bytes.",
            "- Answer grading is deterministic; no model judged another model's output.",
            "- The runner's dollar guard is client-side and based on recorded token usage; only provider controls can guarantee an absolute billing ceiling.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render Benchmark 2 JSON into CSV and Markdown"
    )
    parser.add_argument("--input", type=Path, default=RUN_PATH)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    if not args.input.exists():
        raise SystemExit(
            f"missing {args.input}; run python -m benchmark.real.run --live --resume"
        )
    payload = read_json(args.input)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(args.output_dir / "cells.csv", payload["rows"])
    _write_csv(args.output_dir / "summary.csv", payload["summary"])
    report_path = args.output_dir / "REPORT.md"
    report_path.write_text(build_markdown(payload), encoding="utf-8")
    print(f"wrote {report_path}")
    print(f"wrote {args.output_dir / 'cells.csv'}")
    print(f"wrote {args.output_dir / 'summary.csv'}")


if __name__ == "__main__":
    main()
