from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from benchmark.allocators import get_allocators
from benchmark.real.artifacts import sha256_json
from benchmark.real.capture import _rank_embedding_results, _select_document_paths
from benchmark.real.constants import REAL_PROFILES
from benchmark.real.grading import grade, normalize_answer
from benchmark.real.http import PublicAPIClient
from benchmark.real.openai_api import OpenAIBackend, PaidCallError, estimate_cost
from benchmark.real.run import (
    _allocate,
    _bounded_tool_output,
    build_schedule,
    preflight_cost,
)
from benchmark.real.security import redact
from benchmark.real.tools import ToolExecutor, cache_key
from benchmark.real.workloads import TARGET_TOKENS, build_workloads
from benchmark.schema import GroundTruth
from benchmark.tokenizers import ApproxTokenizer


def test_secret_redaction_is_recursive() -> None:
    value = {
        "Authorization": "Bearer " + "a" * 26,
        "nested": ["sk-" + "a" * 30, {"token": "ghp_" + "a" * 24}],
    }
    redacted = redact(value)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["nested"][0] == "[REDACTED]"
    assert redacted["nested"][1]["token"] == "[REDACTED]"


def test_public_client_rejects_non_allowlisted_urls() -> None:
    with pytest.raises(ValueError, match="allowlist"):
        PublicAPIClient().get("https://example.com/private")


def test_tool_executor_replays_identical_call() -> None:
    payload = {
        "info": {
            "name": "demo",
            "version": "1.2.3",
            "summary": "x",
            "requires_python": ">=3.11",
            "project_urls": {},
        }
    }

    class FakeHTTP:
        calls = 0

        def get(self, url: str):
            self.calls += 1
            return SimpleNamespace(
                url=url, captured_at="now", sha256="abc", body=payload
            )

    client = FakeHTTP()
    executor = ToolExecutor(client, live=True)
    first = executor.execute("pypi_get_project", {"project": "Demo"})
    second = executor.execute("pypi_get_project", {"project": "demo"})
    assert client.calls == 1
    assert first.replayed is False
    assert second.replayed is True
    assert first.cache_key == second.cache_key
    assert executor.duplicate_count == 1


def test_tool_cache_key_is_canonical() -> None:
    assert cache_key("x", {"b": 2, "a": 1}) == cache_key("x", {"a": 1, "b": 2})


def test_grade_is_deterministic_and_checks_sources_and_tools() -> None:
    truth = GroundTruth(
        critical_evidence_ids=["source-1"],
        must_survive_ids=[],
        must_never_ids=[],
        expected_answers=["Version 1.2.3"],
        required_source_ids=["source-1"],
        expected_tool_name="pypi_get_project",
        expected_tool_args={"project": "demo"},
    )
    result = grade(
        answer="  version   1.2.3 ",
        source_ids=["source-1"],
        selected_ids=["source-1", "source-2"],
        ground_truth=truth,
        tool_calls=[{"name": "pypi_get_project", "arguments": {"project": "demo"}}],
        tool_execution_ok=True,
    )
    assert normalize_answer(" A  B ") == "a b"
    assert result["answer_exact"] is True
    assert result["required_source_recall"] == 1.0
    assert result["citation_validity"] == 1.0
    assert result["tool_choice_correct"] is True
    assert result["tool_args_correct"] is True


def test_schema_cost_and_long_context_surcharge() -> None:
    short = estimate_cost(100_000, 1_000)
    long = estimate_cost(300_000, 1_000)
    assert short == pytest.approx(0.0212)
    assert long == pytest.approx(0.1218)


def test_full_real_schedule_has_224_cells_and_fits_buffer() -> None:
    workloads = [
        SimpleNamespace(id=name)
        for name in (
            "fits_all",
            "history_heavy",
            "retrieval_heavy",
            "tool_heavy",
            "multiplayer_heavy",
            "memory_heavy",
            "mixed_overflow",
            "tool_bomb",
            "oversized_user",
            "cross_tenant",
            "needle_rag",
            "policy_pressure",
            "early_history",
            "knowledge_vs_recency",
            "protected_pressure",
            "huge_mixed",
        )
    ]
    allocators = [SimpleNamespace(name=f"a{i}") for i in range(4)]
    schedule = build_schedule(workloads, allocators)
    assert len(schedule) == 224
    assert preflight_cost(schedule) < 4.5


def test_bounded_tool_output_preserves_auditable_hash() -> None:
    value = {"tree": ["x" * 1000 for _ in range(200)]}
    bounded = _bounded_tool_output(value, max_chars=500)
    assert bounded["truncated"] is True
    assert bounded["original_sha256"] == sha256_json(value)
    assert len(bounded["content_prefix"]) == 500


def test_document_path_selection_is_deterministic() -> None:
    tree = {
        "tree": [
            {"path": "misc/z.md", "type": "blob", "size": 3000},
            {"path": "content/en/docs/pod.md", "type": "blob", "size": 4000},
            {"path": "content/en/docs/security.md", "type": "blob", "size": 5000},
        ]
    }
    assert _select_document_paths(tree, (".md",), 2) == [
        "content/en/docs/pod.md",
        "content/en/docs/security.md",
    ]


def test_embedding_ranking_is_deterministic() -> None:
    chunks = [
        {
            "file_id": "b",
            "filename": "b.md",
            "content": "beta",
            "content_sha256": "b-hash",
            "attributes": {},
        },
        {
            "file_id": "a",
            "filename": "a.md",
            "content": "alpha",
            "content_sha256": "a-hash",
            "attributes": {},
        },
    ]
    ranked = _rank_embedding_results(
        chunks,
        [[0.0, 1.0], [1.0, 0.0]],
        [1.0, 0.0],
    )
    assert [item["file_id"] for item in ranked] == ["a", "b"]
    assert ranked[0]["score"] == pytest.approx(1.0)


def test_openai_backend_embeds_in_response_index_order() -> None:
    response = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.0, 1.0]),
            SimpleNamespace(index=0, embedding=[1.0, 0.0]),
        ],
        usage=SimpleNamespace(total_tokens=7),
    )
    embeddings = SimpleNamespace(create=lambda **_: response)
    backend = OpenAIBackend(client=SimpleNamespace(embeddings=embeddings))
    vectors, tokens = backend.embed(["alpha", "beta"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert tokens == 7


def test_openai_backend_uses_stateless_structured_responses() -> None:
    response = SimpleNamespace(
        id="resp_1",
        output=[],
        output_text=json.dumps({"answer": "ok", "source_ids": ["s1"]}),
        usage=SimpleNamespace(input_tokens=10, output_tokens=4),
        status="completed",
    )

    class Responses:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return response

    responses = Responses()
    backend = OpenAIBackend(client=SimpleNamespace(responses=responses))
    result = backend.answer(model="gpt-test", prompt="hello")
    assert result.answer == "ok"
    assert responses.kwargs["store"] is False
    assert responses.kwargs["reasoning"] == {"effort": "none"}
    assert responses.kwargs["text"]["format"]["type"] == "json_schema"


def test_openai_backend_retains_usage_when_parsing_fails() -> None:
    response = SimpleNamespace(
        id="resp_bad",
        output=[],
        output_text="not-json",
        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
        status="completed",
    )
    backend = OpenAIBackend(
        client=SimpleNamespace(responses=SimpleNamespace(create=lambda **_: response))
    )
    with pytest.raises(PaidCallError) as caught:
        backend.answer(model="gpt-test", prompt="hello")
    assert caught.value.input_tokens == 100
    assert caught.value.output_tokens == 10
    assert caught.value.cost_usd > 0


def test_real_workloads_build_from_frozen_capture(monkeypatch) -> None:
    for key in TARGET_TOKENS:
        monkeypatch.setitem(TARGET_TOKENS, key, 1)
    repo = "owner/repo"
    revision = "a" * 40
    artifacts = [
        {
            "id": "doc_owner_repo_00",
            "kind": "document",
            "content": "real documentation",
            "source_url": "https://example.invalid/doc",
            "revision": revision,
            "license": "MIT",
            "scope_id": repo,
            "sha256": "doc",
            "metadata": {"repo": repo, "path": "docs/a.md"},
        },
        {
            "id": "issue_owner_repo_1",
            "kind": "issue",
            "content": "Issue: #1\nTitle: Real issue title\nState: closed",
            "source_url": "https://example.invalid/issue",
            "revision": revision,
            "license": "MIT",
            "scope_id": repo,
            "sha256": "issue",
            "metadata": {
                "repo": repo,
                "number": 1,
                "title": "Real issue title",
                "state": "closed",
            },
        },
        {
            "id": "pypi_openai",
            "kind": "tool_result",
            "content": '{"version":"1.2.3"}',
            "source_url": "https://pypi.org/pypi/openai/json",
            "revision": "1.2.3",
            "license": "metadata-only",
            "scope_id": "pypi",
            "sha256": "pypi",
            "metadata": {"project": "openai", "version": "1.2.3"},
        },
    ]
    capture = {
        "artifacts": artifacts,
        "pypi": [{"project": "openai", "version": "1.2.3"}],
        "sources": [
            {
                "repo": repo,
                "revision": revision,
                "source_url": "https://example.invalid/repo",
                "tree": {"repo": repo, "revision": revision, "tree": []},
                "commits": [{"sha": "b" * 40}],
                "release": {"tag_name": "v1.0.0"},
            }
        ],
        "rag": {
            "provider": "openai_embeddings",
            "embedding_model": "text-embedding-3-small",
            "vector_store_id": None,
            "queries": [
                {
                    "query": "real query",
                    "results": [
                        {
                            "rank": 1,
                            "file_id": "file_1",
                            "filename": "a.md",
                            "score": 0.9,
                            "content": "real result",
                            "content_sha256": "rag",
                            "attributes": {},
                        }
                    ],
                }
            ],
        },
    }
    capture["capture_sha256"] = sha256_json(capture)
    workloads = build_workloads(capture, ApproxTokenizer())
    assert len(workloads) == 16
    assert all(workload.ground_truth.required_source_ids for workload in workloads)
    scoped = next(workload for workload in workloads if workload.id == "cross_tenant")
    assert scoped.ground_truth.must_never_ids
    assert {item.id for item in scoped.items}.issuperset(
        scoped.ground_truth.required_source_ids
    )
    early = next(workload for workload in workloads if workload.id == "early_history")
    early_target = next(
        item
        for item in early.items
        if item.id in early.ground_truth.required_source_ids
    )
    assert early_target.sequence == 0
    needle = next(workload for workload in workloads if workload.id == "needle_rag")
    needle_target = next(
        item
        for item in needle.items
        if item.id in needle.ground_truth.required_source_ids
    )
    assert needle_target.relevance == 0.001
    for allocator in get_allocators():
        prompt, selected_ids, metrics = _allocate(
            workloads[0], REAL_PROFILES["32k"], allocator, ApproxTokenizer()
        )
        assert prompt
        assert selected_ids
        assert metrics["overflow"] is False
