"""Assemble selected items into a final prompt string.

Selection policy and presentation order are deliberately separate.
All allocators share this assembler so position effects do not confound
the allocator comparison.
"""

from __future__ import annotations

import hashlib
import json

from benchmark.schema import ASSEMBLY_ORDER, SelectedItem

HEADERS = {
    "system": "[SYSTEM]",
    "security": "[SECURITY]",
    "tool_schema": "[TOOL SCHEMAS]",
    "memory": "[MEMORY]",
    "rag": "[RETRIEVED KNOWLEDGE]",
    "history": "[CONVERSATION HISTORY]",
    "tool_result": "[TOOL RESULTS]",
    "agent": "[AGENT MESSAGES]",
    "user": "[CURRENT USER]",
}


def _within_class_sort(items: list[SelectedItem], cls: str) -> list[SelectedItem]:
    if cls in ("rag", "memory"):
        return sorted(items, key=lambda x: (-(x.relevance or 0.0), x.sequence, x.id))
    return sorted(items, key=lambda x: (x.sequence, x.id))


def assemble(selected: list[SelectedItem]) -> str:
    by_cls: dict[str, list[SelectedItem]] = {}
    for item in selected:
        by_cls.setdefault(item.cls, []).append(item)

    parts: list[str] = []
    for cls in ASSEMBLY_ORDER:
        group = by_cls.get(cls)
        if not group:
            continue
        parts.append(HEADERS[cls])
        for item in _within_class_sort(group, cls):
            flag = " [truncated]" if item.truncated else ""
            parts.append(f"<{item.id}{flag}>\n{item.content}\n</{item.id}>")
    return "\n\n".join(parts) + "\n"


def selected_ids_in_assembly_order(selected: list[SelectedItem]) -> list[str]:
    by_cls: dict[str, list[SelectedItem]] = {}
    for item in selected:
        by_cls.setdefault(item.cls, []).append(item)
    ids: list[str] = []
    for cls in ASSEMBLY_ORDER:
        group = by_cls.get(cls)
        if not group:
            continue
        ids.extend(item.id for item in _within_class_sort(group, cls))
    return ids


def prompt_hash(assembled: str) -> str:
    return hashlib.sha256(assembled.encode("utf-8")).hexdigest()


def selection_hash(allocator: str, version: str, ids: list[str], truncated: dict[str, int]) -> str:
    payload = json.dumps(
        {
            "allocator": allocator,
            "version": version,
            "ids": ids,
            "truncated": truncated,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
