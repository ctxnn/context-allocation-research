from benchmark.schema import ContextItem, GroundTruth, Workload


def test_real_schema_fields_round_trip_without_breaking_old_payloads() -> None:
    old = ContextItem.from_dict(
        {"id": "x", "cls": "rag", "content": "data", "sequence": 1, "tenant_id": "t"}
    )
    assert old.provenance == {}
    assert old.scope_id is None

    workload = Workload(
        id="real",
        name="real",
        description="real",
        shape="rag",
        tenant_id="t",
        items=[
            ContextItem(
                id="x",
                cls="rag",
                content="data",
                sequence=1,
                tenant_id="t",
                provenance={"source_url": "https://example.invalid", "sha256": "abc"},
                scope_id="scope-a",
            )
        ],
        ground_truth=GroundTruth(
            critical_evidence_ids=["x"],
            must_survive_ids=[],
            must_never_ids=[],
            expected_answers=["data"],
            required_source_ids=["x"],
            expected_tool_name="demo",
            expected_tool_args={"x": 1},
        ),
    )
    restored = Workload.from_dict(workload.to_dict())
    assert restored == workload
