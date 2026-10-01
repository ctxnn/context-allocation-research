# Research Task: Select the Deterministic Context-Budget Allocation Algorithm

## Current work

**Benchmark 1** is the synthetic first-pass experiment. **Benchmark 2** reuses the same allocators with frozen public data, OpenAI vector-store or embedding RAG, read-only GitHub/PyPI tools, and real model calls. Neither is a production allocator.

- **Presentation Slide Deck**: [`presentation/context-budget-allocation-ppt.pdf`](presentation/context-budget-allocation-ppt.pdf)
- **Benchmark 2.0 — Real APIs, RAG, Tools, Results, and Reproduction**: [BENCHMARK_2.0.md](BENCHMARK_2.0.md)
- **In-Depth Benchmark Analysis**: [BENCHMARK_GUIDE.md](BENCHMARK_GUIDE.md)
- **Quick Benchmark Summary**: [BENCHMARK.md](BENCHMARK.md)

---

## How to Run the Code

The benchmark suite is self-contained in Python 3.11+ using the repository virtual environment.

### 1. Environment Setup

From the repository root or the topic directory:

```bash
cd topics/01-context-budget-allocation
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

*(Dependencies: `tiktoken`, `openai`, `pytest`, `matplotlib`)*

### Benchmark 2: real APIs and real RAG

Set secrets in your shell; do not put them in source files:

```bash
export OPENAI_API_KEY="..."
export GITHUB_TOKEN="..."  # optional, but recommended for capture rate limits
```

Capture public Kubernetes, CPython, and GitHub documentation at immutable commits; capture real read-only GitHub/PyPI tool results; then freeze OpenAI-backed retrieval results. Use the embedding backend when a restricted key lacks `vector_store.write`; it embeds the real document chunks with `text-embedding-3-small`, ranks them locally by cosine similarity, and enforces a separate RAG cost preflight:

```bash
python -m benchmark.real.capture --live
# Restricted-key alternative used by this run:
python -m benchmark.real.capture --live --rag-provider embeddings --max-rag-cost-usd 0.10
```

Run the real 224-cell matrix using paid Responses API calls. The runner refuses a worst-case preflight above $4.50 when the explicit cap is $5, stops scheduling at $4.50, and checkpoints every cell:

```bash
python -m benchmark.real.run --live --model gpt-5.6-luna --max-cost-usd 5 --resume
python -m benchmark.real.report
```

The code-side cap is a guardrail, not a provider-enforced billing limit. When project controls are unavailable, use `--max-cost-usd 4.5`; the fixed $0.50 scheduler buffer then stops new calls at $4.00 and leaves additional room below a $5 target for capture or ambiguous provider-side accounting. Generated artifacts are isolated under `results/real/`.

Remote cleanup is deliberately explicit for vector-store capture. By default this deletes the vector store and the uploaded files recorded for it. Embedding capture creates no persistent OpenAI resources and needs no remote cleanup:

```bash
python -m benchmark.real.cleanup --live --vector-store-id vs_...
```

Benchmark 2 uses public-source scope filtering for `cross_tenant`; it does not claim to validate confidential tenant isolation. Identical tool calls are executed live once during capture and replayed byte-for-byte across allocator cells for fairness.

### 2. Regenerate Synthetic Workloads (Optional)

All sample workloads are already checked into `benchmark/sample_data/`. To re-generate them deterministically from scratch:

```bash
python -m benchmark.data.generate
```

This populates 16 synthetic workloads across 4 classes (`standard`, `adversarial`, `multiplayer`, `asymmetric`) along with markdown visual previews in `benchmark/sample_data/previews/`.

### 3. Execute the Full Benchmark Suite

Run the 256-cell benchmark suite (16 workloads × 4 allocators × 4 context window profiles: 32k, 64k, 128k, 256k):

```bash
python -m benchmark.run_benchmarks
```

During execution, it runs cell-by-cell allocations across all combinations, executes a deterministic replay pass verifying zero mismatch across identical seeds, and writes updated summary files and charts to `results/`.

### 4. Run the Invariant & Determinism Tests

Execute the unit and invariant test suite to verify hard invariants (zero cross-tenant leakage, 100% policy retention, fail-closed handling on oversized items, and determinism):

```bash
python -m pytest
```

---

## What Artifacts It Generates

Running the benchmark generates structured datasets, validation tables, and analytical visualizations inside `results/` and `benchmark/sample_data/`:

### 1. Structured Datasets & Metrics (`results/`)

| Artifact | Format | Description |
|---|---|---|
| [`results/benchmark.json`](results/benchmark.json) | JSON | Complete trace of all 256 evaluation cells, including per-item selection, token budgets, execution latency, and verification checks. |
| [`results/benchmark.csv`](results/benchmark.csv) | CSV | Granular metrics per run: token counts (`tok_allocated`, `tok_limit`), budget utilization (`utilization`), evidence recall, survival rate, and runtime latency. |
| [`results/evidence.csv`](results/evidence.csv) | CSV | Item-level audit tracking ground-truth evidence survival across allocators, identifying exactly which items were preserved or dropped. |
| [`results/summary.csv`](results/summary.csv) | CSV | Aggregated scorecard grouped by `(allocator, profile)` measuring mean evidence recall, must-survive retention, protected retention, starved classes, and leakage. |

### 2. Analytical Visualizations (`results/`)

Running the benchmark suite and plotting utilities produces high-resolution charts in `results/`:

| Artifact | Chart | Purpose |
|---|---|---|
| [`results/invariants.png`](results/invariants.png) | Invariants Audit | Validates that all allocators satisfy non-negotiable hard invariants (0 cross-tenant leaks, 100% system policy survival). |
| [`results/heatmap_32k.png`](results/heatmap_32k.png) | Class Allocation Heatmap | Illustrates token allocation distribution across context classes (`system`, `history`, `tools`, `retrieval`, `memory`) under 32k limits. |
| [`results/tool_bomb_32k.png`](results/tool_bomb_32k.png) | Tool Bomb Resilience | Demonstrates allocator behavior under an adversarial flood of tool results (shows recency failure vs. quota/water-fill resilience). |
| [`results/util_vs_recall_32k.png`](results/util_vs_recall_32k.png) | Utilization vs. Recall | Demonstrates the trade-off between packing the context window to 100% vs. preserving high-value evidence. |
| [`results/recall_by_profile.png`](results/recall_by_profile.png) | Recall by Profile | Compares evidence recall curves across 32k, 64k, 128k, and 256k window profiles. |
| [`results/evidence_recall_64k.png`](results/evidence_recall_64k.png) | 64k Evidence Recall | Visualizes head-to-head evidence retention on 64k windows where class ceilings impact water-fill and utility allocators. |

### 3. Workload Data & Previews (`benchmark/sample_data/`)

| Artifact | Description |
|---|---|
| `benchmark/sample_data/workloads/*.json` | 16 versioned synthetic workload JSON files defining candidate context items across priorities and classes. |
| `benchmark/sample_data/previews/*.md` | Human-readable markdown representations of each workload showing item contents, token lengths, and ground-truth tags. |
| `benchmark/sample_data/manifest.json` | Master catalog of synthetic test cases categorizing scenarios by stress type. |

---

## 1. Goal

Determine which single deterministic algorithm an agentic AI platform should use to allocate a finite, model-specific context window among system and policy instructions, tenant and user input, active turn history, tool schemas and results, multiplayer or agent messages, retrieved knowledge, long-term memories, and reserved output and tool-call capacity. Recommend one approach with fully specified ordering, quotas or priorities, tie-breakers, truncation and compaction rules, overflow behavior, and starvation safeguards, and explain with evidence why it is superior to credible alternatives for correctness, security, reproducibility, latency, and cost under representative workloads.

## 2. Context and Constraints

The target platform is assumed to be a multi-tenant agent system that constructs model requests from several independently sized context sources; the supported models, tokenizers, workload distributions, context-assembly architecture, and service-level cost and latency targets are unknown baselines that must be validated. This decision is important because allocation affects instruction integrity, answer quality, tool reliability, reproducible replay, and resource usage, while malformed or adversarial oversized inputs can cause policy loss, cross-source starvation, or context overflow.

Inspect the available architecture and code evidence for request assembly, model and tokenizer adapters, policy injection, tool registration and results, retrieval and memory boundaries, multiplayer or agent messaging, tenant and authorization propagation, audit or event persistence, retry and idempotency handling, replay, observability, and representative workloads. Do not assume those components or their locations exist: establish the implementation baseline first. Non-negotiable constraints are tenant isolation; authorization-aware inclusion of every context item; privacy and security controls; auditable evidence of source, ordering, inclusion, exclusion, compaction, and token counts; idempotent reconstruction; deterministic behavior and replay for identical versioned inputs; explicit model-specific tokenization; safe fail-closed overflow handling; starvation prevention; and bounded latency and cost.

**Out of scope:** Implementing the production allocator, selecting models or providers, redesigning retrieval or long-term-memory quality, changing authorization policy, or defining general prompt content beyond what is necessary to evaluate allocation behavior.

## 3. Questions to Answer

1. Which one deterministic allocation algorithm should an agentic AI platform adopt—such as fixed hierarchical quotas, weighted-priority or water-filling allocation, optimization or knapsack-style packing, or another credible design—and what exact ordering, budget calculation, stable tie-breaking, reserved-capacity, starvation-prevention, and reproducible truncation or compaction rules define it?
2. How does each candidate behave under adversarial oversized inputs, tokenizer drift or mismatch, malformed metadata, missing authorization, context overflow, retries, and partial failures; how are tenant isolation, privacy, fail-closed recovery, idempotency, replay, and audit evidence preserved?
3. What are the measured or estimated effects on allocation and end-to-end latency, model-token cost, implementation complexity, memory or CPU use, context utilization, and output or tool-call headroom across representative models and workload shapes?
4. How do at least two credible alternatives compare on determinism, instruction protection, fairness and starvation, quality retention, explainability, operational tuning, and worst-case behavior, and why should the rejected options not be selected?
5. What implementation changes would the recommendation require in context assembly, tokenization and model adapters, authorization and tenant boundaries, retrieval and memory interfaces, tool and agent-message handling, audit schemas, idempotency or replay paths, observability, testing, configuration versioning, and rollout or rollback controls?

## 4. Expected Deliverables

- A concise report answering all five questions.
- A comparison of at least two credible options using explicit decision criteria.
- One recommended algorithm, specified precisely enough to implement and justified against the alternatives.
- Evidence from authoritative documentation, focused experiments, benchmarks, or a small prototype using representative workloads and model-specific tokenizers.
- Risks, trade-offs, unknowns, and implementation implications, including rollout and rollback considerations.
- Relevant papers.
- Relevant blogs.
- Relevant open-source projects.
- Proof of context.

## 5. Completion Criteria

- Every question is answered with traceable evidence.
- At least two credible options are evaluated consistently.
- The most important assumption is identified and tested with evidence.
- Exactly one implementable algorithm is recommended and its deterministic rules are explicit.
- Rejected options are explained against the decision criteria.
- Remaining unknowns and risks are identified, bounded where possible, and assigned validation steps.
