# Context-Budget Allocation Research

Research and reproducible benchmarks for deciding which context an agentic AI system should retain when its model input budget is limited.

The benchmark compares four deterministic strategies—recency, fixed quota with spillover, water-fill, and utility-based allocation—across system instructions, conversation history, tool results, retrieval, agent messages, and memory. It evaluates evidence retention, budget utilization, protected-item survival, authorization filtering, and deterministic replay.

This repository contains only the context-budget allocation research. It is not a production agent platform or a production-ready allocator.

## Contents

The implementation and research artifacts are in [`topics/01-context-budget-allocation/`](topics/01-context-budget-allocation/).

- [Research brief and setup](topics/01-context-budget-allocation/README.md)
- [Synthetic benchmark summary](topics/01-context-budget-allocation/BENCHMARK.md) and [analysis guide](topics/01-context-budget-allocation/BENCHMARK_GUIDE.md)
- [Real-API Benchmark 2.0](topics/01-context-budget-allocation/BENCHMARK_2.0.md)
- [Allocator implementations](topics/01-context-budget-allocation/benchmark/allocators/), [tests](topics/01-context-budget-allocation/benchmark/tests/), and [synthetic workloads](topics/01-context-budget-allocation/benchmark/sample_data/)
- [Synthetic results and charts](topics/01-context-budget-allocation/results/)
- [Research presentation](topics/01-context-budget-allocation/presentation/context-budget-allocation-ppt.pdf)
- [Exploratory research notes](topics/01-context-budget-allocation/scratchpad.md)

## Run locally

Requires Python 3.11 or later. From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r topics/01-context-budget-allocation/requirements.txt
cd topics/01-context-budget-allocation
python -m pytest
python -m benchmark.run_benchmarks
```

The synthetic suite evaluates 16 workloads, four allocators, and four context-window profiles (32k, 64k, 128k, and 256k), producing 256 evaluation cells. It writes metrics and charts to the topic's `results/` directory. Synthetic execution and tests do not require provider credentials or paid model calls. Checked-in workloads can optionally be regenerated with `python -m benchmark.data.generate`.

## Real-API evaluation

Benchmark 2.0 adds frozen public-source data, OpenAI-backed retrieval, read-only GitHub/PyPI tools, and paid model inference. See its [reproduction guide](topics/01-context-budget-allocation/BENCHMARK_2.0.md) before running capture or evaluation. Credentials belong in your environment, never in committed files. Captured data and per-call results are excluded from Git by default.

The published report describes a historical reference run; its raw capture and usage ledgers are not included here. Live evaluation requires new capture and incurs provider charges. Code-side spending caps are guardrails, not provider-enforced billing limits. The public-source scope tests do not establish confidential tenant isolation.
