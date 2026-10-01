# Context-budget allocation

This repository currently contains **Benchmark 1** only.

It is a synthetic, deterministic first pass for comparing context-window
allocation strategies. It is **not** a production allocator, **not** real
tenant traffic, and **not** the full research program.

Later benchmarks (real traces, serving tokenizer, model-use of selected
evidence) are not in this repo yet.

Start here: **[BENCHMARK_GUIDE.md](BENCHMARK_GUIDE.md)**
- **Presentation Slide Deck**: [`presentation/context-budget-allocation-ppt.pdf`](presentation/context-budget-allocation-ppt.pdf)
- **Detailed Guide & Artifacts**: [README.md](README.md)

```bash
python -m benchmark.data.generate
python -m benchmark.run_benchmarks
python -m pytest
```

Requires Python 3.11+ and the packages in `requirements.txt`.
This repository uses a local `.venv` with CPython 3.12.
