from __future__ import annotations

import json
import re
from typing import Any

from benchmark.schema import GroundTruth


def normalize_answer(value: str) -> str:
    return " ".join(value.casefold().strip().split())


def grade(
    *,
    answer: str,
    source_ids: list[str],
    selected_ids: list[str],
    ground_truth: GroundTruth,
    tool_calls: list[dict[str, Any]],
    tool_execution_ok: bool,
) -> dict[str, Any]:
    expected = {normalize_answer(item) for item in ground_truth.expected_answers}
    exact = normalize_answer(answer) in expected if expected else True
    cited = set(source_ids)
    selected = set(selected_ids)
    required = set(ground_truth.required_source_ids)
    source_recall = len(cited & required) / len(required) if required else 1.0
    citation_validity = (
        len(cited & selected) / len(cited) if cited else (1.0 if not required else 0.0)
    )
    evidence_attribution = required.issubset(cited) if required else True

    expected_tool = ground_truth.expected_tool_name
    chosen = [call for call in tool_calls if call.get("name") == expected_tool]
    tool_choice = bool(chosen) if expected_tool else True
    tool_args = True
    if expected_tool and ground_truth.expected_tool_args is not None:
        expected_args = json.dumps(
            ground_truth.expected_tool_args, sort_keys=True, separators=(",", ":")
        )
        tool_args = any(
            json.dumps(call.get("arguments", {}), sort_keys=True, separators=(",", ":"))
            == expected_args
            for call in chosen
        )
    duplicate_calls = max(
        0,
        len(tool_calls)
        - len(
            {
                (
                    call.get("name"),
                    json.dumps(call.get("arguments", {}), sort_keys=True),
                )
                for call in tool_calls
            }
        ),
    )
    return {
        "answer_exact": bool(exact),
        "required_source_recall": round(source_recall, 4),
        "evidence_attribution": bool(evidence_attribution),
        "citation_validity": round(citation_validity, 4),
        "tool_choice_correct": bool(tool_choice),
        "tool_args_correct": bool(tool_args),
        "tool_execution_ok": bool(tool_execution_ok),
        "tool_duplicate_calls": duplicate_calls,
        "answer": re.sub(r"[\r\n]+", " ", answer).strip(),
        "cited_source_ids": source_ids,
    }
