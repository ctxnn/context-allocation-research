from __future__ import annotations

from pathlib import Path

from benchmark.schema import ModelProfile

TOPIC_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = TOPIC_ROOT / "benchmark" / "real_data"
RESULTS_DIR = TOPIC_ROOT / "results" / "real"
CAPTURE_PATH = DATA_DIR / "capture.json"
WORKLOAD_PATH = DATA_DIR / "workloads.json"
LEDGER_PATH = RESULTS_DIR / "ledger.jsonl"
RUN_PATH = RESULTS_DIR / "benchmark.json"
RESOURCE_PATH = DATA_DIR / "openai_resources.json"

DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_COST_CAP_USD = 5.0
COST_STOP_BUFFER_USD = 0.50
MAX_OUTPUT_TOKENS = 256
INPUT_USD_PER_MTOK = 0.20
OUTPUT_USD_PER_MTOK = 1.20
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_USD_PER_MTOK = 0.02
DEFAULT_RAG_COST_CAP_USD = 0.10
EMBEDDING_CHUNK_TOKENS = 6_000
EMBEDDING_BATCH_SIZE = 32
LONG_CONTEXT_THRESHOLD = 272_000
LONG_INPUT_MULTIPLIER = 2.0
LONG_OUTPUT_MULTIPLIER = 1.5

REAL_PROFILES: dict[str, ModelProfile] = {
    "32k": ModelProfile("32k", 32_768, 4_096, 512, INPUT_USD_PER_MTOK),
    "64k": ModelProfile("64k", 65_536, 8_192, 1_024, INPUT_USD_PER_MTOK),
    "128k": ModelProfile("128k", 131_072, 8_192, 2_048, INPUT_USD_PER_MTOK),
    "256k": ModelProfile("256k", 262_144, 16_384, 2_048, INPUT_USD_PER_MTOK),
}

WORKLOAD_IDS = (
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

PROFILE_256K_SLICE = {"tool_bomb", "needle_rag", "oversized_user", "huge_mixed"}
TOOL_SLICE_WORKLOADS = ("tool_heavy", "tool_bomb", "mixed_overflow", "huge_mixed")

# Public, mixed technical corpus. Capture resolves each repo to an immutable SHA.
REPOSITORIES = (
    {"repo": "kubernetes/website", "license": "CC-BY-4.0", "extensions": (".md",)},
    {"repo": "python/cpython", "license": "PSF-2.0", "extensions": (".rst", ".md")},
    {"repo": "github/docs", "license": "CC-BY-4.0", "extensions": (".md", ".yml")},
)
PYPI_PROJECTS = ("openai", "tiktoken", "pytest", "kubernetes", "requests")

RAG_QUERIES = (
    "Kubernetes pod lifecycle and termination",
    "Kubernetes secrets configuration",
    "Python asyncio task cancellation",
    "Python pathlib filesystem paths",
    "GitHub REST API issue endpoints",
    "GitHub Actions workflow permissions",
)

ALLOWED_HOSTS = {"api.github.com", "raw.githubusercontent.com", "pypi.org"}
