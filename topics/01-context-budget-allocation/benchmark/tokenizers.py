"""Tokenizer adapters.

Primary allocator counts use tiktoken cl100k_base (GPT-4 / GPT-3.5 family).
The mismatch experiment recounts with o200k_base (GPT-4o family).

These are representative OpenAI-family tokenizers, not the exact serving
tokenizer of an arbitrary production model. That gap is documented, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass


class Tokenizer:
    name: str

    def count(self, text: str) -> int:
        raise NotImplementedError

    def truncate(self, text: str, n_tokens: int) -> str:
        raise NotImplementedError


@dataclass
class TiktokenTokenizer(Tokenizer):
    name: str
    encoding_name: str

    def __post_init__(self) -> None:
        import tiktoken

        self._enc = tiktoken.get_encoding(self.encoding_name)

    def count(self, text: str) -> int:
        return len(self._enc.encode(text))

    def truncate(self, text: str, n_tokens: int) -> str:
        if n_tokens <= 0:
            return ""
        ids = self._enc.encode(text)
        if len(ids) <= n_tokens:
            return text
        n = n_tokens
        while n > 0:
            out = self._enc.decode(ids[:n])
            if len(self._enc.encode(out)) <= n_tokens:
                return out
            n -= 1
        return ""


@dataclass
class ApproxTokenizer(Tokenizer):
    """Fallback: ~4 characters per token. Used only if tiktoken is missing."""

    name: str = "approx_char4"
    chars_per_token: int = 4

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + self.chars_per_token - 1) // self.chars_per_token)

    def truncate(self, text: str, n_tokens: int) -> str:
        if n_tokens <= 0:
            return ""
        return text[: n_tokens * self.chars_per_token]


def load_tokenizer(name: str) -> Tokenizer:
    mapping = {
        "cl100k_base": "cl100k_base",
        "o200k_base": "o200k_base",
        "approx": None,
    }
    if name not in mapping:
        raise ValueError(f"unknown tokenizer {name!r}")
    if name == "approx":
        return ApproxTokenizer()
    try:
        return TiktokenTokenizer(name=name, encoding_name=mapping[name])
    except Exception:
        return ApproxTokenizer(name=f"approx_fallback_from_{name}")


def default_tokenizer() -> Tokenizer:
    return load_tokenizer("cl100k_base")


def mismatch_tokenizer() -> Tokenizer:
    return load_tokenizer("o200k_base")
