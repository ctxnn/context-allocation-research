import inspect

from benchmark.allocators import get_allocators
from benchmark.allocators.common import weighted_waterfill
from benchmark.schema import ModelProfile
from benchmark.tests.helpers import CFG, PROFILE, tiny_workload, tok, tokenize


def test_no_unauthorized_leakage():
    workload = tiny_workload()
    tokenizer = tok()
    items = tokenize(list(workload.items), tokenizer)
    for allocator in get_allocators():
        result = allocator.allocate(items, PROFILE.input_budget, "acme", CFG, tokenizer)
        ids = {s.id for s in result.selected}
        assert "poison" not in ids, allocator.name
        for s in result.selected:
            assert s.tenant_id in {"acme", "platform"}, allocator.name


def test_protected_policy_survives_when_it_fits():
    workload = tiny_workload()
    tokenizer = tok()
    items = tokenize(list(workload.items), tokenizer)
    for allocator in get_allocators():
        result = allocator.allocate(items, PROFILE.input_budget, "acme", CFG, tokenizer)
        ids = {s.id for s in result.selected}
        assert "sec" in ids, allocator.name
        assert "sys" in ids, allocator.name
        assert not result.failed_closed


def test_stays_within_budget():
    workload = tiny_workload()
    tokenizer = tok()
    items = tokenize(list(workload.items), tokenizer)
    tight = ModelProfile("tiny", 400, output_reserve=50, tool_reserve=20)
    for allocator in get_allocators():
        result = allocator.allocate(items, tight.input_budget, "acme", CFG, tokenizer)
        used = sum(s.token_count + CFG.per_item_overhead for s in result.selected)
        assert used <= tight.input_budget, (allocator.name, used, tight.input_budget)


def test_allocator_signature_has_no_ground_truth():
    for allocator in get_allocators():
        params = inspect.signature(allocator.allocate).parameters
        assert "ground_truth" not in params
        assert "critical_evidence_ids" not in params


def test_waterfill_satisfies_small_demand_first():
    # Scratchpad example: leftover sharing should fully satisfy a small class.
    demands = {"A": 2_000, "B": 100_000, "C": 40_000, "D": 40_000}
    weights = {"A": 8.0, "B": 6.0, "C": 4.0, "D": 2.0}
    alloc = weighted_waterfill(demands, weights, 40_000)
    assert alloc["A"] == 2_000
    assert sum(alloc.values()) == 40_000
    assert alloc["B"] > alloc["D"]


def test_failed_closed_omits_elastic_if_system_cannot_fit():
    from benchmark.tests.helpers import it

    tokenizer = tok()
    huge = "policy " * 5000
    items = tokenize(
        [
            it("sys", "system", huge),
            it("user", "user", "hello"),
            it("rag", "rag", "evidence lives here", relevance=1.0),
        ],
        tokenizer,
    )
    tiny_budget = 50
    for allocator in get_allocators():
        result = allocator.allocate(items, tiny_budget, "acme", CFG, tokenizer)
        ids = {s.id for s in result.selected}
        assert "rag" not in ids, allocator.name
        assert result.failed_closed, allocator.name
