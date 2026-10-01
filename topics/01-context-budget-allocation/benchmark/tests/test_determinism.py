import random

from benchmark.allocators import get_allocators
from benchmark.assemble import assemble, prompt_hash, selected_ids_in_assembly_order
from benchmark.engine import run_case
from benchmark.tests.helpers import CFG, PROFILE, tiny_workload, tok, tokenize


def test_shuffle_does_not_change_selection():
    workload = tiny_workload()
    tokenizer = tok()
    items = tokenize(list(workload.items), tokenizer)
    for allocator in get_allocators():
        baseline = allocator.allocate(items, PROFILE.input_budget, "acme", CFG, tokenizer)
        base_ids = selected_ids_in_assembly_order(baseline.selected)
        base_hash = prompt_hash(assemble(baseline.selected))
        rng = random.Random(0)
        for _ in range(20):
            shuffled = list(items)
            rng.shuffle(shuffled)
            result = allocator.allocate(shuffled, PROFILE.input_budget, "acme", CFG, tokenizer)
            ids = selected_ids_in_assembly_order(result.selected)
            assert ids == base_ids, allocator.name
            assert prompt_hash(assemble(result.selected)) == base_hash, allocator.name


def test_engine_replay_hashes_match():
    workload = tiny_workload()
    tokenizer = tok()
    for allocator in get_allocators():
        a = run_case(workload, PROFILE, allocator, tokenizer, CFG)
        b = run_case(workload, PROFILE, allocator, tokenizer, CFG)
        assert a["prompt_hash"] == b["prompt_hash"]
        assert a["selection_hash"] == b["selection_hash"]
        assert a["ordered_ids"] == b["ordered_ids"]
