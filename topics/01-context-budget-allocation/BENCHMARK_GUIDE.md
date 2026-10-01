# Context-budget allocation — Benchmark 1

This is **Benchmark 1**: a small, inspectable synthetic first pass. It is
**not** a production allocator, **not** real tenant data, and **not** the
whole research program. Later benchmarks are still to come.

The question:

> Given a finite model-specific context budget and several competing context
> sources, which **deterministic** allocation strategy behaves best under
> representative (synthetic) workloads?

Read this file first. Then inspect `benchmark/sample_data/`, run one command,
and look at `results/`.

---

## Current conclusion

On this synthetic corpus, **no single allocator wins**.

- All four candidates kept required security policy and leaked **zero**
  cross-tenant items. Those invariants are not the differentiator.
- **Recency** (keep the live thread) fills the window the most and misses
  the most evidence under overflow. More tokens were not a better answer.
- **Fixed quota**, **water-fill**, and **utility** are tied on 32k evidence
  recall. At 64k, **fixed quota is perfect** and water-fill/utility miss a
  mid-age tool result because of class ceilings plus newest-first packing
  inside `tool_result`.
- Water-fill is **not** the unique winner of this first pass. The PHTB-WF
  sketch in `scratchpad.md` is still a reasonable candidate, but ceilings
  that idle leftover tokens, and within-class recency, matter as much as
  the water-fill step itself.

Do not ship an allocator from this document. Next experiment: a handful of
real traces, the serving tokenizer, and a check that the model actually
*uses* selected evidence.

---

## The problem in one picture

```
ALL PLATFORM STATE
        |
        v
AUTHORIZATION FILTER          (wrong tenant never enters the prompt)
        |
        v
CONTEXT SHAPING               (out of scope here: summarize, trim, subagents)
        |
        v
CANDIDATE CONTEXT ITEMS       (still too much for the model window)
        |
        v
TOKEN COUNT                   (representative tokenizer)
        |
        v
DETERMINISTIC ALLOCATOR       (this benchmark)
        |
        v
SELECTED CONTEXT + ASSEMBLY
        |
        v
METRICS                       (recall, leakage, starvation, overflow, ...)
```

Two different jobs are easy to mix up:

| Job | What it does |
| --- | --- |
| Context **management** | Shrinks candidates (summaries, tool-log trim, subagents) |
| Context **allocation** | Decides who gets the remaining tokens when candidates still overflow |

This repo only studies allocation. Compaction, RAG retrieval, and subagents
are assumed to have already produced the candidate list.

```
We have 150k of stuff and a 100k window.
How should we allocate the 100k?
```

---

## What an allocator is allowed to see

Each candidate item has:

- stable `id`
- context class (`system`, `security`, `user`, `history`, `tool_schema`,
  `tool_result`, `agent`, `rag`, `memory`)
- `content`
- `sequence` (time for chat/tools/agents; rank for RAG/memory)
- `tenant_id`
- `relevance` when it is a ranked knowledge item
- `protected` / `truncatable`

The benchmark also knows, **separately**:

- which item contains the fact needed to answer
- which policy must survive
- which cross-tenant item must never appear

Those labels live in `ground_truth` inside the JSON files. The runner never
passes that object into `allocate()`. If an allocator keeps the needle, it
is because of class, score, recency, or budget — not because the test
whispered the answer.

---

## Safety invariants (all serious candidates)

Every allocator in this comparison is supposed to:

1. Drop unauthorized / wrong-tenant items
2. Give system/security (and required tool schemas) a protected lane
3. Keep current user input in that protected lane (user may truncate)
4. Stay within the configured input budget
5. Tie-break deterministically (`relevance`, then `sequence`, then `id`)
6. Fail closed on protected overflow: do not spend leftover tokens on RAG
   while a required security rule could not fit

Reserved output and tool-call capacity is **not** allocated. It is subtracted
up front from the model window.

```
physical context window
+----------------------------------------------+
| input budget                                 | output | tool |
|  (allocator plays only here)                 | reserve| rsv  |
+----------------------------------------------+--------+------+
```

---

## The four allocators

None of these is “the production algorithm.” They are reasonable
deterministic policies, implemented to the same interface.

```
                     Fixed quota   Water-fill   Utility   Recency
Protected lane           yes          yes         yes       yes
Auth / tenant filter     yes          yes         yes       yes
Elastic floors           via quota    yes         yes       no
Weighted leftover        no           yes         no        no
Item-level scores        no           no          yes       no
Live-thread first        no           no          no        yes
Oldest-history pin       yes          yes         yes       no
Class ceilings           no           yes         yes       no
Deterministic            yes          yes         yes       yes
```

### A. Fixed quotas + spillover (`fixed_quota`)

After protected items, leftover budget is sliced by class:

```
history 30% | rag 25% | tool_result 20% | agent 15% | memory 10%
```

If a class does not use its slice, unused tokens spill in that same order.

**Intuition:** simple, auditable. A quiet class’s unused quota becomes extra
room for a noisy class. There is no per-class ceiling after spillover, so a
single class can still grow large if everyone else is quiet.

### B. Protected floors + weighted water-fill (`waterfill`)

This is the PHTB-WF idea from `scratchpad.md`:

```
protected items
    -> elastic floors (8% each of leftover, so ~40% reserved)
        -> weighted water-fill of the rest
            -> per-class ceilings
                -> pack items inside each class budget
```

Weights (**ASSUMED**): history 8, rag 6, tool_result 5, agent 4, memory 3.

Water-fill means: a class that only needs 2k of its fair share keeps 2k, and
the rest is redistributed to classes that still have demand.

Ceilings (**ASSUMED**): history 50%, rag 45%, tool_result 40%, agent 30%,
memory 25% of post-protected leftover.

**Intuition:** nobody starves below a floor; leftover tracks demand; one
source cannot eat the window. The first run showed the last part also
**idles tokens** when only one class has demand.

### C. Constrained utility packing (`utility`)

Same protected lane and same floors/ceilings. After floors, remaining items
compete **globally** by

```
score = relevance * class_weight
```

History/tool/agent items with no relevance use recency inside their class as
a stand-in (0.35–1.0).

**Intuition:** a single high-value RAG chunk can beat a pile of mediocre
history, without abandoning floors.

### D. Recency / harness-style (`recency`)

Protected lane, then newest-first over history + tool results + agent
messages as one live stream. It keeps a prefix of that stream (no backfill
of older small messages into packing holes). RAG and memory only get what
is left, ranked by relevance. No floors, no ceilings, no oldest-history pin.

**Intuition:** this is closer to “keep the current thread.” It is a real
harness instinct, not a dummy baseline.

---

## How selected context is laid out

Selection policy and prompt order are separate. All allocators share one
assembler so “lost in the middle” does not confound the comparison.

```
[SYSTEM]                 privileged, primacy
[SECURITY]
[TOOL SCHEMAS]
[MEMORY]
[RETRIEVED KNOWLEDGE]    middle of the prompt
[CONVERSATION HISTORY]   chronological, even if packed by recency
[TOOL RESULTS]
[AGENT MESSAGES]
[CURRENT USER]           recency
```

**HYPOTHESIS (not tested with a model):** putting knowledge in the middle
may hurt utilization of those tokens even when they were selected. This
benchmark measures *whether the tokens were present*, not whether a model
would have used them.

---

## Workloads

Fictional world: **Northstar Logistics** runs an internal agent called
**Relay**. The authorized tenant is **Acme Retail**. Poison items belong to
**Globex Wholesale**.

| id | Shape | What it is testing |
| --- | --- | --- |
| `fits_all` | normal | Everything should fit. Sanity check. |
| `history_heavy` | history-heavy | Answer is in a late chat turn. |
| `retrieval_heavy` | retrieval-heavy | Answer is a high-relevance RAG chunk. |
| `tool_heavy` | tool-heavy | Answer is a specific tool result among many. |
| `multiplayer_heavy` | multiplayer-heavy | Answer is a researcher-agent message. |
| `memory_heavy` | memory-heavy | Answer is a high-relevance memory. |
| `mixed_overflow` | mixed-overflow | All classes compete. |
| `tool_bomb` | tool-bomb | Huge recent CI log; answer is a small runbook. |
| `oversized_user` | oversized-user | User paste is enormous; question is at the start. |
| `cross_tenant` | adversarial | High-relevance Globex jailbreak / key leak. |
| `needle_rag` | needle | Medium-rank RAG fact, easy to drop. |
| `policy_pressure` | policy-pressure | User + peer agent urge a no-ticket prod deploy. |
| `early_history` | early-history | Task-origin fact is the first history item. |
| `knowledge_vs_recency` | knowledge-vs-recency | Answer in RAG, pressure from a long live thread. |
| `protected_pressure` | protected-pressure | Huge user paste in the protected lane. |
| `huge_mixed` | huge-mixed | Same story as mixed, scaled toward 128k/256k. |

Bulk text is generated from readable ops notes, not random bytes. Important
facts are hand-authored (cutoff 14:30, HMAC header `X-Northstar-Signature`,
120 rpm, CSV-on-Monday, no prod deploy without `CHG-#####`).

Open `benchmark/sample_data/previews/` before the full JSON. The JSON
includes `ground_truth` for humans and the runner; allocators never see it.

---

## Token budgets and tokenizers

| Profile | Window | Output reserve | Tool reserve | Input budget |
| --- | ---: | ---: | ---: | ---: |
| 32k | 32,768 | 4,096 | 512 | 28,160 |
| 64k | 65,536 | 8,192 | 1,024 | 56,320 |
| 128k | 131,072 | 8,192 | 2,048 | 120,832 |
| 256k | 262,144 | 16,384 | 2,048 | 243,712 |

**ASSUMED:** those reserves. They are not a production serving table.

Tokenizer:

- Allocate with `tiktoken` **cl100k_base** (GPT-4 / GPT-3.5 family)
- Recount with **o200k_base** (GPT-4o family) and record mismatch overflow

These are representative OpenAI-family encodings, **not** an exact serving
tokenizer for an arbitrary hosted model.

Each packed item is charged `token_count + 16` for XML-ish wrappers. 64
tokens are reserved for section headers. Both numbers are conservative
stand-ins so “stayed in budget” refers to the assembled prompt, not just
naked item text.

---

## Metrics

| Metric | Why it exists |
| --- | --- |
| `critical_evidence_recall` | Did the fact needed to answer survive? |
| `must_survive_retention` | Did the required policy survive? |
| `protected_retention` | Protected items that were authorized and kept |
| `unauthorized_leakage` | Wrong-tenant or `must_never` items in the prompt |
| `class_starvation` | Elastic class with demand and zero tokens |
| `floor_violations` | Granted class budget below its floor |
| `overflow` | Assembled prompt exceeds input budget |
| `mismatch_overflow` | Overflow when recounted with tokenizer B |
| `utilization` / `unused_tokens` | Recorded, **not** the objective |
| `failed_closed` | Protected lane could not fit |
| `allocate_ms` / `tokenize_ms` | Rough cost of the policy |
| `prompt_hash` / `selection_hash` | Deterministic replay |
| `estimated_cost_usd` | Illustrative: $0.15 / M input tokens |

More tokens are not automatically better. A prompt that keeps a 55k CI log
and drops the runbook can score high utilization and still fail the task.

---

## How to run

Python 3.12, packages from `requirements.txt`. This checkout already has
`.venv`.

```bash
source .venv/bin/activate
python -m benchmark.data.generate
python -m benchmark.run_benchmarks
python -m pytest
```

Generate is seed `42` and is skipped automatically if
`benchmark/sample_data/workloads/` already exists. Force regeneration by
deleting that folder, or run `python -m benchmark.data.generate` again.

Outputs:

| Path | What |
| --- | --- |
| `benchmark/sample_data/workloads/*.json` | Full synthetic prompts + hidden ground truth |
| `benchmark/sample_data/previews/*.md` | Short inventory per workload |
| `benchmark/sample_data/manifest.json` | Item counts and token totals |
| `results/benchmark.csv` | One row per (workload, profile, allocator) |
| `results/benchmark.json` | Same, plus config snapshot |
| `results/summary.csv` | Means by allocator × profile |
| `results/evidence.csv` | Compact recall/leakage table |
| `results/evidence_recall_64k.png` | Bar chart |

---

## Files

```
scratchpad.md                 research notes (do not treat as proven)
BENCHMARK_GUIDE.md            this file
README.md                     pointer here
benchmark/schema.py           item / workload / result types
benchmark/config.py           experimental knobs (ASSUMED)
benchmark/tokenizers.py       tiktoken adapter + approx fallback
benchmark/profiles.py         32k/64k/128k/256k windows
benchmark/assemble.py         shared prompt layout + hashes
benchmark/allocators/         four strategies + shared primitives
benchmark/data/content.py     hand-authored policies and facts
benchmark/data/generate.py    synthetic Northstar/Relay corpus
benchmark/engine.py           tokenize -> allocate -> assemble -> metrics
benchmark/run_benchmarks.py   matrix runner
benchmark/tests/              determinism + invariants
benchmark/sample_data/        generated workloads (inspect these)
results/                      machine-readable first-run output
```

`scratchpad.md` was not overwritten. It remains the idea log.

---

## First-run results

Matrix: **16 workloads × 4 profiles × 4 allocators = 256 rows**, plus a
full replay pass. Replay hashes matched (`replay ok=True`, 0 mismatches).
Shuffled-input unit tests also passed.

### Invariants (all 256 cells)

| Check | Result |
| --- | --- |
| Unauthorized leakage | **0** |
| Assembled overflow vs cl100k_base | **0** |
| Overflow after o200k_base recount | **0** |
| Required policy retention | **1.00** |
| Protected-item retention | **1.00** |
| Fail-closed (system could not fit) | **0** (user was truncatable) |
| Floor violations | **0** |
| Deterministic replay | **pass** |

Poison RAG/memory is scored at 0.99 relevance, higher than the real Acme
docs, and still never appears. Auth is not “whoever has the best score.”

### Mean evidence recall

```
profile   fixed_quota   waterfill   utility   recency
32k            0.812       0.812     0.812     0.500
64k            1.000       0.938     0.938     0.812
128k           1.000       1.000     1.000     0.938
256k           1.000       1.000     1.000     1.000
```

Mean utilization at 32k: recency 0.86, fixed quota 0.82, water-fill 0.60,
utility 0.58. Recency used the most tokens and kept the least evidence.

### 32k evidence (1 = kept the fact, 0 = dropped it)

```
workload               quota  water  util  recency
fits_all                  1      1     1      1
cross_tenant              1      1     1      1
policy_pressure           1      1     1      1
history_heavy             1      1     1      1
retrieval_heavy           1      1     1      1
memory_heavy              1      1     1      1
knowledge_vs_recency      1      1     1      1
early_history             1      1     1      0
mixed_overflow            1      1     1      0
huge_mixed                1      1     1      0
multiplayer_heavy         1      1     1      0
tool_bomb                 1      1     1      0
needle_rag                0      0     0      0
oversized_user            0      0     0      0
tool_heavy                0      0     0      0
```

At 64k the remaining misses are:

- recency: `early_history`, `huge_mixed`, `mixed_overflow`
- water-fill and utility: `tool_heavy`
- fixed quota: none

---

## Before / after: the tool bomb

Candidate list (32k window, ~28k input budget):

```
system + security + schemas     ~0.7k   protected
current user                    tiny    protected
history                         tiny
toolres_bomb                    55k     recent CI log, truncatable
rag_billing_retry               ~0.2k   THE ANSWER (relevance 0.94)
mem_csv_monday                  tiny
poison_*                        high relevance, wrong tenant
```

**Recency** spends the live-stream budget on the truncated log:

```
[SYSTEM] [SECURITY] [TOOL SCHEMAS]
[TOOL RESULTS]  <toolres_bomb truncated to ~27k>
[CURRENT USER]
                                rag_billing_retry  EXCLUDED
utilization 0.996   recall 0.00
```

**Utility** keeps the runbook and barely keeps a prefix of the log
(the floor). It looks “wasteful” on utilization and is the one that
answers the question:

```
[SYSTEM] [SECURITY] [TOOL SCHEMAS]
[MEMORY]            mem_csv_monday
[RETRIEVED KNOWLEDGE] rag_billing_retry     <--- answer
[CONVERSATION HISTORY]
[TOOL RESULTS]      toolres_bomb truncated to the floor
[CURRENT USER]
utilization 0.12    recall 1.00
```

Water-fill and fixed quota also keep the runbook. They keep a larger slice
of the log because of quota/ceiling, not because the log is useful.

This is the Lost-in-the-Middle lesson in allocator clothing:

```
more information available  ≠  more information useful
maximum utilization         ≠  maximum agent quality
```

---

## Surprising results (not hidden)

### 1. Water-fill is not uniformly better than frozen quotas

On `tool_heavy` at 64k, the evidence is a mid-age incident record
(`toolres_inc2044`). Within-class packing is newest-first.

- Fixed quota: other classes are small, so spillover dumps leftover into
  `tool_result`. ~17 tool items survive, including the incident. Recall 1.0.
- Water-fill / utility: the 40% tool ceiling stops at ~7 newest dumps.
  The incident is older than that. Recall 0.0.
- Recency: almost the whole window is tools, so it also reaches the
  incident. Recall 1.0.

The water-fill *class budget* was doing what it was told. The miss is
**ceiling + within-class recency**, not a math bug in water-fill.

Scratchpad hypothesis “weighted sharing of leftover is the grown-up
policy” is only half of the story. Item order inside a class is the other
half. OpenHands-style “keep first N + recent” is used for history here,
but **not** for tool results. That choice is load-bearing.

### 2. Ceilings idle ~50% of the window when one class dominates

`early_history` / `history_heavy` / `retrieval_heavy` at 32k and 64k:

- Water-fill and utility sit near 0.49–0.51 utilization.
- Fixed quota and recency sit near 0.98.

History’s ceiling is 50% of leftover. Nobody else wants the rest, and the
implementation does **not** donate idle ceiling-blocked tokens back to the
only demanding class.

That is a real product fork, not just a bug:

```
Option A  Fill leftover with more history anyway
          (higher utilization, more middle-of-prompt sludge)

Option B  Leave headroom
          (Lost in the Middle: extra tokens may not help)
```

This first pass recorded Option B as coded. Evidence recall was still 1.0
on those workloads because the pinned oldest item / top RAG chunk already
fit in the capped budget. High utilization was unnecessary.

### 3. A protected oversized user starves everyone equally

`oversized_user` at 32k: every allocator truncates `user_current` until
the protected lane fills the window. Elastic recall is 0 for all of them.
This is not an allocator comparison. It is a warning that **“user is
strongly protected” can hide the runbook that answers the user.**

At 64k the paste fits with room to spare and everyone keeps the runbook.

### 4. The needle is below every class budget at 32k

`needle_rag` evidence is RAG rank ~11, ~1.5k tokens per chunk. Even
water-fill’s RAG slice at 32k is ~12k tokens (~8 chunks). Rank 11 dies
for everyone.

Allocation cannot save evidence that ranking + budget cannot surface.
At 64k, all four keep it.

### 5. `knowledge_vs_recency` did not punish recency

The RAG answer is tiny. Recency’s live stream uses stop-on-miss, so a
few leftover tokens remain; the small RAG chunk fits. Recency *does*
drop RAG on `huge_mixed` / `mixed_overflow`, where a truncated recent
tool result seals the hole.

The discriminating workload for “live thread vs knowledge” is mixed
overflow with large recent tools, not “long chat + one small doc.”

### 6. Tokenizer mismatch did not overflow here

Recounting with o200k_base used **fewer** tokens on this English corpus
(largest delta about −1.1k on `huge_mixed` 256k). Combined with the 16+64
overhead slack, mismatch overflow is 0.

That does **not** prove serving-tokenizer mismatch is safe. It proves this
pair, on this corpus, with this slack, did not blow up.

### 7. Water-fill and utility never disagreed on evidence

Same floors, same ceilings, same within-class order. Item-level scoring
only changed how much of a truncated bomb to keep (`tool_bomb`
utilization 0.43 vs 0.12), not which fact survived.

To tell them apart on recall, the corpus would need a high-score item
that class-level water-fill would not reach (or the reverse).

---

## Hypothesis scorecard

From `scratchpad.md` and the plan for this benchmark.

| Claim | Status on this corpus |
| --- | --- |
| Protected policy must not compete with RAG/history | **CONFIRMED** (retention 1.0 under `policy_pressure`) |
| Wrong-tenant data must never appear | **CONFIRMED** (leakage 0, even at relevance 0.99) |
| Output/tool headroom is reserved; final prompt fits | **CONFIRMED** for cl100k_base |
| Identical versioned inputs → identical hashes | **CONFIRMED** |
| Max utilization ≠ quality | **CONFIRMED** (`tool_bomb` recency, `early_history` recency) |
| Recency drops oldest task-origin facts | **CONFIRMED** (`early_history` 32k/64k) |
| Recency is eaten by a huge recent tool dump | **CONFIRMED** at 32k `tool_bomb` |
| Water-fill starves fewer classes than frozen quotas | **NOT SUPPORTED** as a recall win; both starve the same 32k cells, and quotas *win* `tool_heavy` 64k |
| Water-fill uniquely keeps a medium-rank needle | **NOT SUPPORTED** at 32k (everyone misses); everyone hits at 64k |
| Utility uniquely saves high-rel knowledge next to a bomb | **PARTIALLY**: utility, water-fill, and quotas all save it; only recency drops it at 32k |
| Tokenizer A vs B can overflow | **NOT OBSERVED** here |
| Lost in the Middle hurts selected knowledge | **UNKNOWN** (no model) |

---

## Research status

### CONFIRMED

- Deterministic shuffle-independence for all four allocators
- Allocators do not take `ground_truth` as an argument
- Auth filter drops `globex` items
- Water-fill integer routine fully satisfies a small demand first
  (unit test of the scratchpad 40k example)
- First-run invariant table above
- Class-based history packing keeps the oldest turn under pressure;
  pure recency does not

### ASSUMED (experimental defaults, not production values)

- class quotas, floors (8%), weights, ceilings
- output/tool reserves
- $0.15 / MTok
- `per_item_overhead = 16`, `assembly_reserve = 64`
- pin-oldest-history for class-based packers
- relevance scores on synthetic RAG/memory
- tenant rule: `item.tenant_id in {request_tenant, "platform"}`
- tool results pack newest-first with no “first N” pin

### UNKNOWN

- Whether any of this matches production traffic
- Whether the model would actually *use* selected evidence
- Exact serving tokenizer, real cost, real floors/weights
- Compaction quality (TypeCompact, Claude Code `/compact`, etc.)
- Latency at production candidate counts
- What to do with idle tokens under a ceiling

---

## Challenge notes (things that could still be unfair)

Looked at before calling the first pass done:

| Risk | What we did |
| --- | --- |
| Benchmark whispering the answer | `ground_truth` is not an allocator argument; tests check the signature |
| Weak strawman baseline | Recency is a real harness policy and *wins* some cells (`tool_heavy` 64k, high util) |
| Corpus built so water-fill wins | It does not uniquely win. Quotas win 64k recall. Recency wins some tool-age cases. |
| Hidden utilization-as-quality | Recency’s 32k util is highest and recall is worst; called out above |
| Unstable ordering | Shuffle tests + replay hashes |
| Token accounting vs assembled prompt | 16-token wrap + 64-token header reserve; 0 overflows |
| Insertion order meaningful for history | Documented: class-based packers pin oldest, then recency; assembler emits chronological |
| Arbitrary knobs presented as facts | All in `benchmark/config.py`, labeled ASSUMED |

What is still a real limitation: synthetic needles, one weight/floor point,
no model, OpenAI-family tokenizers only, and within-class tool packing
shared across the “serious” allocators so they cannot disagree there.

---

## What to test next

1. **A few real traces**, even messy ones. Synthetic needles sit at known
   ranks. Production evidence may not.
2. **Serving-model tokenizer**, not just cl100k vs o200k.
3. **Does the model use the selected span?** Lost in the Middle is still
   unmeasured. Presence ≠ use.
4. **Within-class tool policy:** first+recent vs newest-only vs score.
   `tool_heavy` says this may matter more than water-fill vs quotas.
5. **Ceiling idle-token policy.** Donate leftover to the only demanding
   class, or keep headroom on purpose?
6. **Protected-user truncation.** Cap the user paste so elastic evidence
   can survive a 32k window.
7. **Pre-allocation shaping** as a factor (trim the CI log *before*
   allocate). Scratchpad says that is a different layer; the bomb is what
   happens if that layer fails.
8. Sensitivity sweep on floors/weights — currently a single point.

---

## Current conclusion

Synthetic evidence **supports**:

- a privileged lane for system/security, plus a tenant filter, as
  non-negotiable and cheap (every candidate already does this)
- not using “fill the window” as the success metric
- not relying on pure recency when knowledge, old task state, or
  mid-age tool results can be the answer
- treating **within-class packing and ceilings** as first-class design,
  not footnotes under water-fill

Synthetic evidence **does not support**:

- “ship PHTB-WF, it is strictly better than quotas”
- any particular floor, weight, or ceiling as a production value
- claims about model quality, cost at scale, or serving-tokenizer safety

**Next experiment:** take 5–10 anonymized production candidate lists,
freeze tokenizer + allocator version, and score the same metrics without
retuning. If water-fill and quotas still trade blows on tool-age vs
spillover, the product decision is probably “pick the within-class rule,”
not “pick the leftover-sharing rule.”
