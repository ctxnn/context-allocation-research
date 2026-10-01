from __future__ import annotations

import argparse
import json
import math
import urllib.parse
from pathlib import Path
from typing import Any

import tiktoken

from benchmark.real.artifacts import (
    atomic_write_json,
    sha256_json,
    sha256_text,
    utc_now,
)
from benchmark.real.constants import (
    CAPTURE_PATH,
    DEFAULT_RAG_COST_CAP_USD,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_CHUNK_TOKENS,
    EMBEDDING_MODEL,
    EMBEDDING_USD_PER_MTOK,
    PYPI_PROJECTS,
    RAG_QUERIES,
    REPOSITORIES,
    RESOURCE_PATH,
)
from benchmark.real.http import PublicAPIClient, github_url
from benchmark.real.openai_api import OpenAIBackend
from benchmark.real.security import redact
from benchmark.real.tools import ToolExecutor


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _rank_embedding_results(
    chunks: list[dict[str, Any]],
    vectors: list[list[float]],
    query_vector: list[float],
    max_results: int = 50,
) -> list[dict[str, Any]]:
    if len(chunks) != len(vectors):
        raise ValueError("embedding count does not match chunk count")
    scored = [
        (_cosine_similarity(vector, query_vector), chunk)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    ranked = []
    for rank, (score, chunk) in enumerate(
        sorted(scored, key=lambda item: (-item[0], item[1]["file_id"]))[
            : max(1, min(50, max_results))
        ],
        start=1,
    ):
        ranked.append({"rank": rank, "score": score, **chunk})
    return ranked


def _embedding_chunks(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = []
    for artifact in (item for item in artifacts if item["kind"] == "document"):
        tokens = encoding.encode(artifact["content"], disallowed_special=())
        base_filename = (
            artifact["metadata"]["repo"].replace("/", "_")
            + "__"
            + sha256_text(artifact["metadata"]["path"])[:8]
            + "__"
            + Path(artifact["metadata"]["path"]).name
        )
        for chunk_index, start in enumerate(
            range(0, len(tokens), EMBEDDING_CHUNK_TOKENS)
        ):
            content = encoding.decode(tokens[start : start + EMBEDDING_CHUNK_TOKENS])
            content_sha256 = sha256_text(content)
            chunks.append(
                {
                    "file_id": f"embed_{content_sha256[:24]}",
                    "filename": f"{base_filename}#chunk-{chunk_index:03d}",
                    "content": content,
                    "content_sha256": content_sha256,
                    "attributes": {
                        "repo": artifact["metadata"]["repo"],
                        "path": artifact["metadata"]["path"],
                        "chunk_index": chunk_index,
                    },
                }
            )
    if not chunks:
        raise ValueError("capture contains no documents to embed")
    return chunks


def _embedding_rag(
    backend: OpenAIBackend,
    artifacts: list[dict[str, Any]],
    max_cost_usd: float,
) -> dict[str, Any]:
    chunks = _embedding_chunks(artifacts)
    encoding = tiktoken.get_encoding("cl100k_base")
    texts = [chunk["content"] for chunk in chunks]
    estimated_tokens = sum(
        len(encoding.encode(text, disallowed_special=())) for text in texts
    ) + sum(len(encoding.encode(query, disallowed_special=())) for query in RAG_QUERIES)
    estimated_cost = estimated_tokens / 1_000_000 * EMBEDDING_USD_PER_MTOK
    if estimated_cost > max_cost_usd:
        raise ValueError(
            f"embedding preflight ${estimated_cost:.6f} exceeds "
            f"RAG cap ${max_cost_usd:.2f}"
        )

    vectors: list[list[float]] = []
    actual_tokens = 0
    for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch_vectors, batch_tokens = backend.embed(
            texts[start : start + EMBEDDING_BATCH_SIZE]
        )
        vectors.extend(batch_vectors)
        actual_tokens += batch_tokens
    query_vectors, query_tokens = backend.embed(list(RAG_QUERIES))
    actual_tokens += query_tokens

    queries = []
    for query, query_vector in zip(RAG_QUERIES, query_vectors, strict=True):
        queries.append(
            {
                "query": query,
                "rewrite_query": False,
                "max_results": 50,
                "results": _rank_embedding_results(chunks, vectors, query_vector),
            }
        )
    return {
        "provider": "openai_embeddings",
        "embedding_model": EMBEDDING_MODEL,
        "embedding_input_tokens": actual_tokens,
        "embedding_cost_usd": round(
            actual_tokens / 1_000_000 * EMBEDDING_USD_PER_MTOK, 8
        ),
        "embedding_preflight_cost_usd": round(estimated_cost, 8),
        "vector_store_id": None,
        "queries": queries,
    }


def _artifact(
    artifact_id: str,
    kind: str,
    content: str,
    *,
    source_url: str,
    revision: str | None,
    license_name: str,
    scope_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": artifact_id,
        "kind": kind,
        "content": content,
        "source_url": source_url,
        "revision": revision,
        "license": license_name,
        "scope_id": scope_id,
        "sha256": sha256_text(content),
        "metadata": metadata or {},
    }


def _select_document_paths(
    tree: dict[str, Any], extensions: tuple[str, ...], limit: int
) -> list[str]:
    candidates = []
    for item in tree["tree"]:
        path = item.get("path") or ""
        size = item.get("size") or 0
        if item.get("type") != "blob" or not path.lower().endswith(extensions):
            continue
        if not 2_000 <= size <= 300_000:
            continue
        lower = path.lower()
        score = sum(
            term in lower
            for term in (
                "docs/",
                "content/en/docs/",
                "library/",
                "rest/",
                "actions/",
                "security",
                "async",
                "issue",
                "workflow",
                "pod",
                "path",
            )
        )
        candidates.append((-score, path))
    return [path for _, path in sorted(candidates)[:limit]]


def _capture_repo(
    client: PublicAPIClient,
    executor: ToolExecutor,
    spec: dict[str, Any],
    max_docs: int,
    max_issues: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    repo = spec["repo"]
    metadata_result = client.get(github_url(f"repos/{repo}"))
    metadata = metadata_result.body
    branch = metadata["default_branch"]
    commit_result = client.get(github_url(f"repos/{repo}/commits/{branch}"))
    revision = commit_result.body["sha"]
    tree_exec = executor.execute(
        "github_get_repository_tree", {"repo": repo, "sha": revision}
    )
    commits_exec = executor.execute(
        "github_list_commits", {"repo": repo, "sha": revision, "per_page": 20}
    )
    try:
        release_exec = executor.execute("github_get_release", {"repo": repo})
        release = release_exec.output
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        release = None

    artifacts: list[dict[str, Any]] = []
    paths = _select_document_paths(
        tree_exec.output, tuple(spec["extensions"]), max_docs
    )
    for index, path in enumerate(paths):
        encoded_path = urllib.parse.quote(path, safe="/")
        raw_url = f"https://raw.githubusercontent.com/{repo}/{revision}/{encoded_path}"
        result = client.get(raw_url, accept="text/plain")
        artifacts.append(
            _artifact(
                f"doc_{repo.replace('/', '_')}_{index:02d}",
                "document",
                result.body,
                source_url=raw_url,
                revision=revision,
                license_name=spec["license"],
                scope_id=repo,
                metadata={"repo": repo, "path": path},
            )
        )

    issues_result = client.get(
        github_url(
            f"repos/{repo}/issues", state="closed", sort="updated", per_page=max_issues
        )
    )
    for issue in issues_result.body[:max_issues]:
        number = int(issue["number"])
        issue_exec = executor.execute(
            "github_get_issue", {"repo": repo, "issue_number": number}
        )
        issue_data = issue_exec.output
        text = (
            f"Repository: {repo}\nIssue: #{number}\nTitle: {issue_data['title']}\n"
            f"State: {issue_data['state']}\nBody:\n{issue_data['body']}"
        )
        artifacts.append(
            _artifact(
                f"issue_{repo.replace('/', '_')}_{number}",
                "issue",
                text,
                source_url=f"https://github.com/{repo}/issues/{number}",
                revision=revision,
                license_name=spec["license"],
                scope_id=repo,
                metadata={
                    "repo": repo,
                    "number": number,
                    "title": issue_data["title"],
                    "state": issue_data["state"],
                    "comments": issue_data["comments"],
                    "is_pull_request": issue_data["is_pull_request"],
                },
            )
        )

        comments_url = github_url(f"repos/{repo}/issues/{number}/comments", per_page=30)
        comments_result = client.get(comments_url)
        captured_comments = []
        for comment_index, comment in enumerate(comments_result.body):
            body = comment.get("body") or ""
            if not body:
                continue
            captured_comments.append(body)
            artifacts.append(
                _artifact(
                    f"comment_{repo.replace('/', '_')}_{number}_{comment_index:02d}",
                    "comment",
                    f"Issue #{number} comment by {comment.get('user', {}).get('login', 'unknown')}:\n{body}",
                    source_url=comment.get("html_url") or comments_url,
                    revision=revision,
                    license_name=spec["license"],
                    scope_id=repo,
                    metadata={
                        "repo": repo,
                        "issue_number": number,
                        "position": comment_index,
                    },
                )
            )
        if captured_comments:
            resolution = (
                f"Resolved public issue summary\nRepository: {repo}\nIssue: #{number}\n"
                f"Title: {issue_data['title']}\nState: {issue_data['state']}\n"
                f"Final captured discussion entry:\n{captured_comments[-1]}"
            )
            artifacts.append(
                _artifact(
                    f"memory_{repo.replace('/', '_')}_{number}",
                    "memory",
                    resolution,
                    source_url=f"https://github.com/{repo}/issues/{number}",
                    revision=revision,
                    license_name=spec["license"],
                    scope_id=repo,
                    metadata={
                        "repo": repo,
                        "issue_number": number,
                        "state": issue_data["state"],
                    },
                )
            )
        if issue_data["is_pull_request"]:
            reviews_url = github_url(
                f"repos/{repo}/pulls/{number}/reviews", per_page=30
            )
            reviews_result = client.get(reviews_url)
            for review_index, review in enumerate(reviews_result.body):
                body = review.get("body") or ""
                if not body:
                    continue
                artifacts.append(
                    _artifact(
                        f"review_{repo.replace('/', '_')}_{number}_{review_index:02d}",
                        "review",
                        (
                            f"Pull request #{number} review by "
                            f"{review.get('user', {}).get('login', 'unknown')} "
                            f"with state {review.get('state', 'unknown')}:\n{body}"
                        ),
                        source_url=review.get("html_url") or reviews_url,
                        revision=revision,
                        license_name=spec["license"],
                        scope_id=repo,
                        metadata={
                            "repo": repo,
                            "pull_number": number,
                            "position": review_index,
                            "state": review.get("state"),
                        },
                    )
                )

    repo_record = {
        "repo": repo,
        "default_branch": branch,
        "revision": revision,
        "license": spec["license"],
        "source_url": metadata.get("html_url"),
        "captured_at": metadata_result.captured_at,
        "metadata_sha256": metadata_result.sha256,
        "document_paths": paths,
        "tree": tree_exec.output,
        "commits": commits_exec.output,
        "release": release,
    }
    return repo_record, artifacts


def capture(
    output: Path,
    max_docs: int = 8,
    max_issues: int = 4,
    *,
    rag_provider: str = "vector-store",
    max_rag_cost_usd: float = DEFAULT_RAG_COST_CAP_USD,
) -> dict[str, Any]:
    # Validate the paid-provider credential before spending time on public capture.
    backend = OpenAIBackend()
    client = PublicAPIClient(max_bytes=64_000_000)
    executor = ToolExecutor(client, live=True)
    repos = []
    artifacts = []
    for spec in REPOSITORIES:
        repo, repo_artifacts = _capture_repo(
            client, executor, spec, max_docs, max_issues
        )
        repos.append(repo)
        artifacts.extend(repo_artifacts)

    pypi = []
    for project in PYPI_PROJECTS:
        execution = executor.execute("pypi_get_project", {"project": project})
        pypi.append(execution.output)
        content = json.dumps(execution.output, indent=2, sort_keys=True)
        artifacts.append(
            _artifact(
                f"pypi_{project}",
                "tool_result",
                content,
                source_url=execution.output["source_url"],
                revision=execution.output["version"],
                license_name="metadata-only",
                scope_id="pypi",
                metadata={"project": project, "version": execution.output["version"]},
            )
        )

    if rag_provider == "embeddings":
        rag = _embedding_rag(backend, artifacts, max_rag_cost_usd)
        resources = {
            "vector_store_id": None,
            "file_ids": [],
            "created_at": utc_now(),
        }
    else:
        vector_store_id = backend.create_vector_store(
            f"context-budget-benchmark-{utc_now()}"
        )
        resources = {
            "vector_store_id": vector_store_id,
            "file_ids": [],
            "created_at": utc_now(),
        }
        atomic_write_json(RESOURCE_PATH, resources)
        for artifact in (item for item in artifacts if item["kind"] == "document"):
            filename = (
                artifact["metadata"]["repo"].replace("/", "_")
                + "__"
                + sha256_text(artifact["metadata"]["path"])[:8]
                + "__"
                + Path(artifact["metadata"]["path"]).name
            )
            file_id = backend.upload_text(
                vector_store_id, filename, artifact["content"]
            )
            resources["file_ids"].append(file_id)
            atomic_write_json(RESOURCE_PATH, resources)

        queries = []
        for query in RAG_QUERIES:
            results = backend.search(vector_store_id, query, max_results=50)
            # Freeze one copy per content hash while preserving hosted rank and score.
            seen = set()
            deduped = []
            for item in results:
                if item["content_sha256"] in seen:
                    continue
                seen.add(item["content_sha256"])
                deduped.append(item)
            queries.append(
                {
                    "query": query,
                    "rewrite_query": False,
                    "max_results": 50,
                    "results": deduped,
                }
            )
        rag = {
            "provider": "openai_vector_store",
            "vector_store_id": vector_store_id,
            "queries": queries,
        }

    payload: dict[str, Any] = {
        "schema_version": 1,
        "benchmark": "real-api-context-allocation",
        "captured_at": utc_now(),
        "sources": repos,
        "pypi": pypi,
        "artifacts": artifacts,
        "tool_cache": executor.cache,
        "rag": rag,
        "resources": resources,
    }
    payload = redact(payload)
    payload["capture_sha256"] = sha256_json(payload)
    atomic_write_json(output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture and freeze real public benchmark data"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="required acknowledgement for network/API calls",
    )
    parser.add_argument("--output", type=Path, default=CAPTURE_PATH)
    parser.add_argument("--max-docs", type=int, default=8)
    parser.add_argument("--max-issues", type=int, default=4)
    parser.add_argument(
        "--rag-provider",
        choices=("vector-store", "embeddings"),
        default="vector-store",
    )
    parser.add_argument(
        "--max-rag-cost-usd", type=float, default=DEFAULT_RAG_COST_CAP_USD
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.live:
        raise SystemExit("capture performs real network/API calls; pass --live")
    if args.output.exists() and not args.force:
        raise SystemExit(
            f"refusing to overwrite {args.output}; pass --force or choose --output"
        )
    if RESOURCE_PATH.exists():
        resources = json.loads(RESOURCE_PATH.read_text(encoding="utf-8"))
        raise SystemExit(
            "existing OpenAI resources are recorded at "
            f"{RESOURCE_PATH}; run cleanup for {resources.get('vector_store_id')} first"
        )
    payload = capture(
        args.output,
        max_docs=max(1, min(20, args.max_docs)),
        max_issues=max(1, min(20, args.max_issues)),
        rag_provider=args.rag_provider,
        max_rag_cost_usd=args.max_rag_cost_usd,
    )
    print(f"captured {len(payload['artifacts'])} public artifacts to {args.output}")
    if payload["rag"]["provider"] == "openai_embeddings":
        print(
            f"OpenAI embedding RAG: {payload['rag']['embedding_input_tokens']} tokens, "
            f"${payload['rag']['embedding_cost_usd']:.6f}"
        )
    else:
        print(
            f"OpenAI vector store: {payload['rag']['vector_store_id']} "
            "(cleanup is explicit)"
        )


if __name__ == "__main__":
    main()
