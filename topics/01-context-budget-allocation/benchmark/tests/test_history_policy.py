from benchmark.allocators import ALLOCATORS
from benchmark.schema import ModelProfile
from benchmark.tests.helpers import CFG, it, tok, tokenize


def test_class_based_history_keeps_oldest_under_pressure():
    tokenizer = tok()
    oldest = it("hist_0000", "history", "Customer id is C-8891.", sequence=0)
    recent = [
        it(f"hist_{i:04d}", "history", f"Recent dashboard chatter {i} " + ("noise " * 40), sequence=i)
        for i in range(1, 30)
    ]
    items = tokenize(
        [
            it("sys", "system", "sys"),
            it("sec", "security", "sec"),
            it("schema", "tool_schema", "tool x()"),
            it("user", "user", "What customer id?"),
            oldest,
            *recent,
        ],
        tokenizer,
    )
    # Tight enough that not all history fits.
    profile = ModelProfile("tight", 2_000, output_reserve=200, tool_reserve=50)
    for name in ("fixed_quota", "waterfill", "utility"):
        result = ALLOCATORS[name]().allocate(items, profile.input_budget, "acme", CFG, tokenizer)
        ids = {s.id for s in result.selected}
        assert "hist_0000" in ids, name


def test_recency_may_drop_oldest_history_under_pressure():
    tokenizer = tok()
    oldest = it("hist_0000", "history", "Customer id is C-8891.", sequence=0)
    recent = [
        it(f"hist_{i:04d}", "history", f"Recent dashboard chatter {i} " + ("noise " * 80), sequence=i)
        for i in range(1, 40)
    ]
    items = tokenize(
        [
            it("sys", "system", "sys"),
            it("sec", "security", "sec"),
            it("schema", "tool_schema", "tool x()"),
            it("user", "user", "What customer id?"),
            oldest,
            *recent,
        ],
        tokenizer,
    )
    profile = ModelProfile("tight", 1_800, output_reserve=200, tool_reserve=50)
    result = ALLOCATORS["recency"]().allocate(items, profile.input_budget, "acme", CFG, tokenizer)
    ids = {s.id for s in result.selected}
    assert "hist_0000" not in ids
    assert any(i.startswith("hist_") and i != "hist_0000" for i in ids)
