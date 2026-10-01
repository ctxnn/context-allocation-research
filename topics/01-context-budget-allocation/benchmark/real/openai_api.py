from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from benchmark.real.artifacts import sha256_text
from benchmark.real.constants import (
    EMBEDDING_MODEL,
    INPUT_USD_PER_MTOK,
    LONG_CONTEXT_THRESHOLD,
    LONG_INPUT_MULTIPLIER,
    LONG_OUTPUT_MULTIPLIER,
    MAX_OUTPUT_TOKENS,
    OUTPUT_USD_PER_MTOK,
)
from benchmark.real.security import require_env

ANSWER_FORMAT = {
    "type": "json_schema",
    "name": "benchmark_answer",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "source_ids"],
        "additionalProperties": False,
    },
}


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    long = input_tokens > LONG_CONTEXT_THRESHOLD
    input_rate = INPUT_USD_PER_MTOK * (LONG_INPUT_MULTIPLIER if long else 1.0)
    output_rate = OUTPUT_USD_PER_MTOK * (LONG_OUTPUT_MULTIPLIER if long else 1.0)
    return (
        input_tokens / 1_000_000 * input_rate + output_tokens / 1_000_000 * output_rate
    )


@dataclass
class ModelResult:
    answer: str
    source_ids: list[str]
    response_id: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: float
    tool_calls: list[dict[str, Any]]
    raw_status: str | None = None


class PaidCallError(RuntimeError):
    """Failure after one or more responses, retaining known billable usage."""

    def __init__(self, message: str, input_tokens: int, output_tokens: int):
        super().__init__(message)
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cost_usd = estimate_cost(input_tokens, output_tokens)


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return value
    raise TypeError(f"cannot serialize response item {type(value)!r}")


def _usage(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    return int(getattr(usage, "input_tokens", 0) or 0), int(
        getattr(usage, "output_tokens", 0) or 0
    )


class OpenAIBackend:
    """Thin, mockable wrapper around the official Python SDK."""

    def __init__(self, client: Any | None = None):
        if client is None:
            api_key = require_env("OPENAI_API_KEY")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError(
                    "install dependencies with: pip install -r requirements.txt"
                ) from exc
            client = OpenAI(api_key=api_key, timeout=120.0, max_retries=2)
        self.client = client

    def embed(
        self, texts: list[str], model: str = EMBEDDING_MODEL
    ) -> tuple[list[list[float]], int]:
        response = self.client.embeddings.create(
            model=model,
            input=texts,
            encoding_format="float",
        )
        ordered = sorted(response.data, key=lambda item: int(item.index))
        vectors = [[float(value) for value in item.embedding] for item in ordered]
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "total_tokens", 0) or 0)
        return vectors, input_tokens

    def create_vector_store(self, name: str) -> str:
        return str(self.client.vector_stores.create(name=name).id)

    def upload_text(self, vector_store_id: str, filename: str, content: str) -> str:
        uploaded = self.client.files.create(
            file=(filename, content.encode("utf-8")), purpose="assistants"
        )
        self.client.vector_stores.files.create_and_poll(
            vector_store_id=vector_store_id, file_id=uploaded.id
        )
        return str(uploaded.id)

    def search(
        self, vector_store_id: str, query: str, max_results: int = 50
    ) -> list[dict[str, Any]]:
        page = self.client.vector_stores.search(
            vector_store_id=vector_store_id,
            query=query,
            max_num_results=max(1, min(50, max_results)),
            rewrite_query=False,
        )
        rows = []
        for rank, result in enumerate(page.data, start=1):
            chunks = []
            for chunk in result.content:
                text = getattr(chunk, "text", None)
                if text:
                    chunks.append(text)
            content = "\n".join(chunks)
            rows.append(
                {
                    "rank": rank,
                    "file_id": str(result.file_id),
                    "filename": str(result.filename),
                    "score": float(result.score),
                    "content": content,
                    "content_sha256": sha256_text(content),
                    "attributes": dict(result.attributes or {}),
                }
            )
        return rows

    def answer(
        self,
        *,
        model: str,
        prompt: str,
        tools: list[dict[str, Any]] | None = None,
        execute_tool: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> ModelResult:
        instructions = (
            "Answer only from the supplied context or tool outputs. Return a short exact answer and "
            "the IDs of context items that support it. If evidence is absent, answer NOT_FOUND."
        )
        conversation: list[Any] = [{"role": "user", "content": prompt}]
        observed_calls: list[dict[str, Any]] = []
        total_input = 0
        total_output = 0
        started = time.perf_counter()

        try:
            for _ in range(4):
                kwargs: dict[str, Any] = {
                    "model": model,
                    "instructions": instructions,
                    "input": conversation,
                    "reasoning": {"effort": "none"},
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "store": False,
                    "text": {"format": ANSWER_FORMAT},
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                response = self.client.responses.create(**kwargs)
                input_tokens, output_tokens = _usage(response)
                total_input += input_tokens
                total_output += output_tokens
                calls = [
                    item
                    for item in response.output
                    if getattr(item, "type", None) == "function_call"
                ]
                if not calls:
                    payload = json.loads(response.output_text)
                    elapsed = (time.perf_counter() - started) * 1000.0
                    return ModelResult(
                        answer=str(payload["answer"]),
                        source_ids=[str(item) for item in payload["source_ids"]],
                        response_id=str(response.id),
                        input_tokens=total_input,
                        output_tokens=total_output,
                        cost_usd=estimate_cost(total_input, total_output),
                        latency_ms=elapsed,
                        tool_calls=observed_calls,
                        raw_status=getattr(response, "status", None),
                    )
                if execute_tool is None:
                    raise RuntimeError(
                        "model requested a tool but no executor was configured"
                    )
                conversation.extend(_dump(item) for item in response.output)
                for call in calls:
                    arguments = json.loads(call.arguments)
                    output = execute_tool(call.name, arguments)
                    observed_calls.append({"name": call.name, "arguments": arguments})
                    conversation.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": json.dumps(output, sort_keys=True),
                        }
                    )
            raise RuntimeError("tool loop exceeded four Responses API calls")
        except Exception as exc:
            if isinstance(exc, PaidCallError):
                raise
            raise PaidCallError(str(exc), total_input, total_output) from exc

    def delete_vector_store(self, vector_store_id: str) -> bool:
        result = self.client.vector_stores.delete(vector_store_id=vector_store_id)
        return bool(getattr(result, "deleted", False))

    def delete_file(self, file_id: str) -> bool:
        result = self.client.files.delete(file_id)
        return bool(getattr(result, "deleted", False))
