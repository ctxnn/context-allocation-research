"""Shared data types for the benchmark.

Allocator-visible fields live on ContextItem.
Benchmark-only labels live on GroundTruth and must not be passed into allocators.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ALL_CLASSES = (
    "system",
    "security",
    "user",
    "history",
    "tool_schema",
    "tool_result",
    "agent",
    "rag",
    "memory",
)

# Privileged lane. These do not compete with elastic utility classes.
PROTECTED_CLASSES = ("system", "security", "tool_schema", "user")

# Elastic lane. These compete for leftover budget after protected items.
ELASTIC_CLASSES = ("history", "rag", "tool_result", "agent", "memory")

# Fail-closed hierarchy among protected classes.
PROTECTED_ORDER = ("system", "security", "tool_schema", "user")

# Prompt assembly order is independent of selection order.
# Privileged instructions first (primacy), current user last (recency).
ASSEMBLY_ORDER = (
    "system",
    "security",
    "tool_schema",
    "memory",
    "rag",
    "history",
    "tool_result",
    "agent",
    "user",
)


@dataclass
class ContextItem:
    """One candidate piece of context.

    Fields here are the only item metadata allocators may use.
    """

    id: str
    cls: str
    content: str
    sequence: int
    tenant_id: str
    relevance: float | None = None
    protected: bool = False
    truncatable: bool = False
    token_count: int | None = None
    # Optional real-benchmark metadata. Allocators may use provenance and scope,
    # but never see GroundTruth labels.
    provenance: dict[str, Any] = field(default_factory=dict)
    scope_id: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "cls": self.cls,
            "content": self.content,
            "sequence": self.sequence,
            "tenant_id": self.tenant_id,
            "relevance": self.relevance,
            "protected": self.protected,
            "truncatable": self.truncatable,
            "token_count": self.token_count,
            "provenance": self.provenance,
            "scope_id": self.scope_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextItem:
        return cls(
            id=data["id"],
            cls=data["cls"],
            content=data["content"],
            sequence=int(data["sequence"]),
            tenant_id=data["tenant_id"],
            relevance=data.get("relevance"),
            protected=bool(data.get("protected", False)),
            truncatable=bool(data.get("truncatable", False)),
            token_count=data.get("token_count"),
            provenance=dict(data.get("provenance", {})),
            scope_id=data.get("scope_id"),
        )


@dataclass
class GroundTruth:
    """Benchmark-only labels. Never passed to an allocator."""

    critical_evidence_ids: list[str]
    must_survive_ids: list[str]
    must_never_ids: list[str]
    notes: str = ""
    expected_answers: list[str] = field(default_factory=list)
    required_source_ids: list[str] = field(default_factory=list)
    expected_tool_name: str | None = None
    expected_tool_args: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GroundTruth:
        return cls(
            critical_evidence_ids=list(data.get("critical_evidence_ids", [])),
            must_survive_ids=list(data.get("must_survive_ids", [])),
            must_never_ids=list(data.get("must_never_ids", [])),
            notes=data.get("notes", ""),
            expected_answers=list(data.get("expected_answers", [])),
            required_source_ids=list(data.get("required_source_ids", [])),
            expected_tool_name=data.get("expected_tool_name"),
            expected_tool_args=(
                dict(data["expected_tool_args"])
                if data.get("expected_tool_args") is not None
                else None
            ),
        )


@dataclass
class Workload:
    id: str
    name: str
    description: str
    shape: str
    tenant_id: str
    items: list[ContextItem]
    ground_truth: GroundTruth

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "shape": self.shape,
            "tenant_id": self.tenant_id,
            "items": [it.to_public_dict() for it in self.items],
            "ground_truth": self.ground_truth.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Workload:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            shape=data["shape"],
            tenant_id=data["tenant_id"],
            items=[ContextItem.from_dict(it) for it in data["items"]],
            ground_truth=GroundTruth.from_dict(data["ground_truth"]),
        )


@dataclass
class ModelProfile:
    name: str
    context_limit: int
    output_reserve: int
    tool_reserve: int
    # Illustrative list-price only. Not a production cost model.
    cost_per_mtok_input: float = 0.15

    @property
    def input_budget(self) -> int:
        return self.context_limit - self.output_reserve - self.tool_reserve


@dataclass
class SelectedItem:
    id: str
    cls: str
    content: str
    token_count: int
    truncated: bool
    original_token_count: int
    sequence: int
    relevance: float | None = None
    tenant_id: str = ""


@dataclass
class Exclusion:
    id: str
    cls: str
    reason: str
    token_count: int


@dataclass
class AllocationResult:
    allocator: str
    allocator_version: str
    selected: list[SelectedItem]
    excluded: list[Exclusion]
    class_demand: dict[str, int] = field(default_factory=dict)
    class_budget: dict[str, int] = field(default_factory=dict)
    class_used: dict[str, int] = field(default_factory=dict)
    failed_closed: bool = False
    failure_reason: str | None = None
    notes: list[str] = field(default_factory=list)
