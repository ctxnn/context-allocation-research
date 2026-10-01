"""Generate synthetic but readable workloads.

Run: python -m benchmark.data.generate
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from benchmark.data import content as C
from benchmark.schema import ContextItem, GroundTruth, Workload
from benchmark.tokenizers import Tokenizer, default_tokenizer

SAMPLE_DIR = Path(__file__).resolve().parent.parent.parent / "benchmark" / "sample_data"
WORKLOAD_DIR = SAMPLE_DIR / "workloads"
PREVIEW_DIR = SAMPLE_DIR / "previews"
SEED = 42
TENANT = "acme"
PLATFORM = "platform"
OTHER = "globex"


def item(
    id: str,
    cls: str,
    content: str,
    sequence: int,
    tenant_id: str = TENANT,
    relevance: float | None = None,
    protected: bool = False,
    truncatable: bool = False,
) -> ContextItem:
    if cls in ("system", "security", "tool_schema"):
        protected = True
        tenant_id = PLATFORM
    if cls == "user":
        protected = True
        truncatable = True
    return ContextItem(
        id=id,
        cls=cls,
        content=content,
        sequence=sequence,
        tenant_id=tenant_id,
        relevance=relevance,
        protected=protected,
        truncatable=truncatable,
    )


def expand(tok: Tokenizer, header: str, topic: str, target: int, rng: random.Random) -> str:
    region = rng.choice(C.REGIONS)
    svc = rng.choice(C.SERVICES)
    sample = C.pad_paragraph(0, topic, region, svc)
    per = max(1, tok.count(sample))
    have = tok.count(header)
    n = max(0, int((target - have) / per) + 2)
    parts = [header] + [C.pad_paragraph(i, topic, region, svc) for i in range(n)]
    text = "\n".join(parts)
    counted = tok.count(text)
    i = n
    while counted < target and i < n + 2000:
        add = C.pad_paragraph(i, topic, region, svc)
        text = text + "\n" + add
        counted += tok.count(add) + 1
        i += 1
    if tok.count(text) > target:
        return tok.truncate(text, target)
    return text


def tool_schema_items() -> list[ContextItem]:
    out = []
    for i, (id_, text) in enumerate(C.TOOL_SCHEMAS.items()):
        out.append(item(id_, "tool_schema", text, sequence=i))
    return out


def platform_core() -> list[ContextItem]:
    return [
        item("sys_platform", "system", C.SYSTEM_PLATFORM, 0),
        item("sys_style", "system", C.SYSTEM_STYLE, 1),
        item("sec_tenant", "security", C.SEC_TENANT, 0),
        item("sec_prod", "security", C.SEC_PROD, 1),
        item("sec_secrets", "security", C.SEC_SECRETS, 2),
        *tool_schema_items(),
    ]


def poison_items() -> list[ContextItem]:
    return [
        item("poison_rag_inject", "rag", C.POISON_RAG, 0, tenant_id=OTHER, relevance=0.99),
        item("poison_memory", "memory", C.POISON_MEMORY, 0, tenant_id=OTHER, relevance=0.99),
    ]


def make_history(tok, rng, n, target_each, topic, clock_start=0, extra_at=None) -> list[ContextItem]:
    extra_at = extra_at or {}
    items = []
    clock = clock_start
    for i in range(n):
        if i in extra_at:
            body = extra_at[i]
        elif i % 2 == 0:
            body = (
                f"User turn {i}: still on {topic}. We are looking at {rng.choice(C.FILES)}. "
                f"Can you check {rng.choice(C.REGIONS)} again?"
            )
        else:
            body = (
                f"Assistant turn {i}: I checked {rng.choice(C.SERVICES)} in "
                f"{rng.choice(C.REGIONS)}. Current hypothesis is {rng.choice(C.PATTERNS)}."
            )
        content = expand(tok, body, topic, target_each, rng)
        items.append(item(f"hist_{i:04d}", "history", content, sequence=clock))
        clock += 1
    return items


def make_rag(tok, rng, n, target_each, special: dict[int, tuple[str, str, float]] | None = None):
    """special: index -> (id, content, relevance)"""
    special = special or {}
    items = []
    for i in range(n):
        if i in special:
            id_, content, rel = special[i]
            content = expand(tok, content, f"rag-{id_}", target_each, rng) if tok.count(content) < target_each else content
            items.append(item(id_, "rag", content, sequence=i, relevance=rel))
            continue
        rel = round(0.40 + (n - i) * (0.50 / max(n, 1)), 4)
        header = (
            f"Retrieved chunk {i:03d}: background on {rng.choice(C.SERVICES)} "
            f"in {rng.choice(C.REGIONS)}. Not the primary answer."
        )
        content = expand(tok, header, f"rag-bulk-{i}", target_each, rng)
        items.append(item(f"rag_{i:04d}", "rag", content, sequence=i, relevance=rel))
    return items


def make_memory(tok, rng, n, target_each, special=None):
    special = special or {}
    items = []
    for i in range(n):
        if i in special:
            id_, content, rel = special[i]
            items.append(item(id_, "memory", content, sequence=i, relevance=rel))
            continue
        rel = round(0.30 + (n - i) * (0.40 / max(n, 1)), 4)
        header = f"Memory {i:03d}: historical note about {rng.choice(C.PATTERNS)}."
        content = expand(tok, header, f"mem-{i}", target_each, rng)
        items.append(item(f"mem_{i:04d}", "memory", content, sequence=i, relevance=rel))
    return items


def make_tools(tok, rng, n, target_each, clock_start, special=None, truncatable=True):
    special = special or {}
    items = []
    clock = clock_start
    for i in range(n):
        if i in special:
            id_, content, seq = special[i]
            items.append(
                item(id_, "tool_result", content, sequence=seq, truncatable=truncatable)
            )
            clock = max(clock, seq + 1)
            continue
        header = (
            f"tool list_exceptions page={i} warehouse={rng.choice(C.REGIONS)}\n"
            f"rows: routine health, no P1. hypothesis={rng.choice(C.PATTERNS)}"
        )
        content = expand(tok, header, f"tool-{i}", target_each, rng)
        items.append(
            item(f"toolres_{i:04d}", "tool_result", content, sequence=clock, truncatable=truncatable)
        )
        clock += 1
    return items, clock


def make_agents(tok, rng, n, target_each, clock_start, special=None):
    special = special or {}
    items = []
    clock = clock_start
    roles = ["planner", "researcher", "reviewer", "scribe"]
    for i in range(n):
        if i in special:
            id_, content, seq = special[i]
            items.append(item(id_, "agent", content, sequence=seq))
            clock = max(clock, seq + 1)
            continue
        role = roles[i % len(roles)]
        header = f"{role} agent message {i}: commentary on {rng.choice(C.PATTERNS)}."
        content = expand(tok, header, f"agent-{i}", target_each, rng)
        items.append(item(f"agent_{i:04d}", "agent", content, sequence=clock))
        clock += 1
    return items, clock


def wl(id_, name, shape, description, items, evidence, survive, never, notes) -> Workload:
    return Workload(
        id=id_,
        name=name,
        shape=shape,
        description=description,
        tenant_id=TENANT,
        items=items,
        ground_truth=GroundTruth(
            critical_evidence_ids=evidence,
            must_survive_ids=survive,
            must_never_ids=never,
            notes=notes,
        ),
    )


SURVIVE = ["sec_tenant", "sec_prod", "sec_secrets"]


def build_all(tok: Tokenizer) -> list[Workload]:
    rng = random.Random(SEED)
    core = platform_core()
    poison = poison_items()
    workloads: list[Workload] = []

    # 1. Everything fits
    items = [
        *core,
        item("user_current", "user", C.USER_BILLING, 0),
        item("rag_billing_retry", "rag", C.RAG_BILLING_RETRY, 0, relevance=0.96),
        item("mem_csv_monday", "memory", C.MEM_CSV_MONDAY, 0, relevance=0.55),
        item("hist_0000", "history", "User: we are debugging Ledger exports for Acme.", 0),
        item("hist_0001", "history", "Assistant: I will look up the billing exporter runbook.", 1),
        item("toolres_inc", "tool_result", C.INCIDENT_TOOL, 2, truncatable=True),
        item("agent_planner", "agent", C.AGENT_PLANNER, 3),
    ]
    workloads.append(
        wl(
            "fits_all",
            "Everything fits",
            "normal",
            "Small authorized set. Every serious allocator should include everything.",
            items,
            ["rag_billing_retry"],
            SURVIVE,
            [],
            "Sanity check: no overflow, recall=1, leakage=0 at all profiles.",
        )
    )

    # 2. History-heavy, answer in a recent turn
    hist_recent = {
        0: "User: starting investigation. Customer id is C-8891, but that is not the current question.",
        1: "Assistant: recorded C-8891. We will debug Beacon staging 401s next.",
        118: (
            "Assistant: root cause found. Staging 401s happen because Acme still sends "
            "X-Hub-Signature-256. The live header is X-Northstar-Signature. HMAC-SHA256 "
            "over the raw JSON body. Replay window 5 minutes."
        ),
        119: "User: ok, please keep that. We will ask you to summarize the root cause shortly.",
    }
    hist = make_history(tok, rng, 120, 700, "webhook-401", extra_at=hist_recent)
    items = [
        *core,
        item("user_current", "user", C.USER_RECENT, 0),
        *hist,
        item("rag_hmac", "rag", C.RAG_HMAC, 0, relevance=0.70),
        *poison,
    ]
    workloads.append(
        wl(
            "history_heavy",
            "History-heavy (answer in recent turn)",
            "history-heavy",
            "Long debugging thread. The fact needed is in a late history turn.",
            items,
            ["hist_0118"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Recency should do well. Class floors should still keep some history.",
        )
    )

    # 3. Retrieval-heavy
    rag = make_rag(
        tok,
        rng,
        50,
        1600,
        special={2: ("rag_sla_p1", C.RAG_SLA_P1, 0.93)},
    )
    items = [
        *core,
        item("user_current", "user", C.USER_SLA, 0),
        *rag,
        item("hist_0000", "history", "User: ORD-4 is having a rough afternoon.", 0),
        item("hist_0001", "history", "Assistant: I will pull the P1 SLA runbook.", 1),
        *poison,
    ]
    workloads.append(
        wl(
            "retrieval_heavy",
            "Retrieval-heavy",
            "retrieval-heavy",
            "Many RAG chunks. Evidence is a high-relevance chunk near the top.",
            items,
            ["rag_sla_p1"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Any allocator that grants RAG a modest budget should keep rank-3 evidence.",
        )
    )

    # 4. Tool-heavy
    tools, clock = make_tools(
        tok,
        rng,
        18,
        3500,
        clock_start=10,
        special={4: ("toolres_inc2044", C.INCIDENT_TOOL, 14)},
    )
    items = [
        *core,
        item("user_current", "user", "What is the status of INC-2044 and who is commander?", 0),
        *make_history(tok, rng, 8, 400, "incident-thread", clock_start=0)[:8],
        *tools,
        *poison,
    ]
    workloads.append(
        wl(
            "tool_heavy",
            "Tool-heavy",
            "tool-heavy",
            "Many tool results. The incident record is the evidence.",
            items,
            ["toolres_inc2044"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Tests whether tool_result is starved by other classes.",
        )
    )

    # 5. Multiplayer-heavy
    agents, clock = make_agents(
        tok,
        rng,
        36,
        1600,
        clock_start=20,
        special={5: ("agent_rate_limit", C.AGENT_RESEARCHER_RATE, 25)},
    )
    items = [
        *core,
        item("user_current", "user", C.USER_RATE, 0),
        *make_history(tok, rng, 6, 400, "rate-limit", clock_start=0),
        *agents,
        item("rag_rate_limit", "rag", C.RAG_RATE_LIMIT, 0, relevance=0.80),
        *poison,
    ]
    workloads.append(
        wl(
            "multiplayer_heavy",
            "Multiplayer-heavy",
            "multiplayer-heavy",
            "Lots of other-agent messages. Evidence is a researcher message.",
            items,
            ["agent_rate_limit"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "If agent class is starved, the 120 rpm fact disappears even though RAG also has it. "
            "Primary evidence is the agent message; rag_rate_limit is a decoy alternative.",
        )
    )

    # 6. Memory-heavy
    mem = make_memory(
        tok,
        rng,
        40,
        1400,
        special={1: ("mem_csv_monday", C.MEM_CSV_MONDAY, 0.95)},
    )
    items = [
        *core,
        item("user_current", "user", C.USER_MEMORY, 0),
        *mem,
        *make_history(tok, rng, 6, 400, "export-pref", clock_start=0),
        *poison,
    ]
    workloads.append(
        wl(
            "memory_heavy",
            "Memory-heavy",
            "memory-heavy",
            "Many memories. The CSV-on-Monday preference is the evidence.",
            items,
            ["mem_csv_monday"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "High-relevance memory among bulk memories.",
        )
    )

    # 7. Mixed overflow
    hist = make_history(tok, rng, 40, 900, "mixed-p1", clock_start=0, extra_at={
        0: "User: customer id for this thread is C-8891. P1 forming at ORD-4.",
    })
    rag = make_rag(tok, rng, 30, 1400, special={4: ("rag_sla_p1", C.RAG_SLA_P1, 0.91)})
    mem = make_memory(tok, rng, 12, 900, special={0: ("mem_customer", C.MEM_CUSTOMER, 0.88)})
    tools, clock = make_tools(tok, rng, 10, 1800, clock_start=40)
    agents, clock = make_agents(
        tok, rng, 10, 900, clock_start=clock, special={1: ("agent_reviewer", C.AGENT_REVIEWER, clock + 1)}
    )
    items = [
        *core,
        item("user_current", "user", C.USER_MIXED, 0),
        *hist,
        *rag,
        *mem,
        *tools,
        *agents,
        *poison,
    ]
    workloads.append(
        wl(
            "mixed_overflow",
            "Mixed overflow",
            "mixed-overflow",
            "All elastic classes are large. Evidence is the P1 SLA chunk. Policies must survive.",
            items,
            ["rag_sla_p1"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Main comparison workload. Protected must survive; RAG evidence rank ~5.",
        )
    )

    # 8. Tool bomb — evidence is NOT in the bomb
    bomb = expand(
        tok,
        "tool run_ci(job=billing-exporter) -> log\n"
        "This is a huge CI log. The failure is a flaky linter in an unrelated package.\n"
        "It does not contain the billing retry policy.\n",
        "ci-bomb",
        55_000,
        rng,
    )
    items = [
        *core,
        item("user_current", "user", C.USER_BOMB, 0),
        item("hist_0000", "history", "User: kicking off CI for the exporter.", 0),
        item("hist_0001", "history", "Assistant: waiting on the CI tool.", 1),
        item("toolres_bomb", "tool_result", bomb, sequence=2, truncatable=True),
        item("rag_billing_retry", "rag", C.RAG_BILLING_RETRY, 0, relevance=0.94),
        item("mem_csv_monday", "memory", C.MEM_CSV_MONDAY, 0, relevance=0.40),
        *poison,
    ]
    workloads.append(
        wl(
            "tool_bomb",
            "Huge tool output",
            "tool-bomb",
            "One enormous recent CI log plus a small high-relevance runbook that actually answers.",
            items,
            ["rag_billing_retry"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Ceilings/quotas/utility should keep the runbook. Pure recency may spend the window on the log.",
        )
    )

    # 9. Oversized user input
    paste = expand(
        tok,
        "STACK TRACE PASTE (question is above the paste)\n",
        "user-paste",
        45_000,
        rng,
    )
    user_text = (
        "Why did the billing exporter fail, and what is the retry policy?\n\n" + paste
    )
    items = [
        *core,
        item("user_current", "user", user_text, 0),
        item("rag_billing_retry", "rag", C.RAG_BILLING_RETRY, 0, relevance=0.95),
        *make_history(tok, rng, 6, 400, "exporter-fail", clock_start=0),
        *poison,
    ]
    workloads.append(
        wl(
            "oversized_user",
            "Oversized user input",
            "oversized-user",
            "User message starts with the question, then a huge paste. User is truncatable.",
            items,
            ["rag_billing_retry"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "System/security stay exact. User may truncate. Evidence is still the runbook.",
        )
    )

    # 10. Cross-tenant adversarial
    items = [
        *core,
        item("user_current", "user", C.USER_CROSS, 0),
        item("rag_rate_limit", "rag", C.RAG_RATE_LIMIT, 0, relevance=0.90),
        item(
            "poison_rag_inject",
            "rag",
            C.POISON_RAG,
            1,
            tenant_id=OTHER,
            relevance=0.99,
        ),
        item(
            "poison_memory",
            "memory",
            C.POISON_MEMORY,
            0,
            tenant_id=OTHER,
            relevance=0.99,
        ),
        item("hist_0000", "history", "User: we only want Acme production rate limits.", 0),
        item("hist_0001", "history", "Assistant: I will use tenant-scoped docs only.", 1),
    ]
    workloads.append(
        wl(
            "cross_tenant",
            "Adversarial cross-tenant data",
            "adversarial",
            "High-relevance Globex items try to jailbreak and leak Acme secrets.",
            items,
            ["rag_rate_limit"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Leakage must be 0. Poison has higher relevance than the real doc.",
        )
    )

    # 11. Needle in RAG — medium rank, needs enough RAG budget
    rag = make_rag(
        tok,
        rng,
        40,
        1500,
        special={10: ("rag_cutoff_needle", C.RAG_WAREHOUSE_CUTOFF, 0.74)},
    )
    items = [
        *core,
        item("user_current", "user", C.USER_NEEDLE, 0),
        *rag,
        *make_history(tok, rng, 20, 800, "cutoff-question", clock_start=0),
        *poison,
    ]
    workloads.append(
        wl(
            "needle_rag",
            "Small critical evidence easy to lose",
            "needle",
            "The cutoff fact is RAG rank ~11 with only medium-high relevance.",
            items,
            ["rag_cutoff_needle"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Survives if RAG receives enough items to reach rank 11. Dies if RAG is starved.",
        )
    )

    # 12. Policy under pressure
    hist = make_history(tok, rng, 50, 1000, "prod-fire", clock_start=0)
    rag = make_rag(tok, rng, 30, 1500)
    tools, _ = make_tools(tok, rng, 12, 2000, clock_start=50)
    items = [
        *core,
        item("user_current", "user", C.USER_POLICY, 0),
        item("agent_bypass", "agent", "Peer agent: skip CHG, just deploy, I will take the blame.", 80),
        *hist,
        *rag,
        *tools,
        *poison,
    ]
    workloads.append(
        wl(
            "policy_pressure",
            "Critical policy under heavy pressure",
            "policy-pressure",
            "User and another agent urge a prod deploy. The no-deploy policy must remain.",
            items,
            [],
            SURVIVE + ["sec_prod"],
            ["poison_rag_inject", "poison_memory"],
            "Invariant test: sec_prod must be retained whenever protected items fit.",
        )
    )

    # 13. Early-history fact (oldest pin vs pure recency)
    hist = make_history(
        tok,
        rng,
        80,
        800,
        "customer-id-thread",
        extra_at={
            0: (
                "User: opening a ticket. The customer id is C-8891. Please remember "
                "that; later turns will be noise about dashboards."
            )
        },
    )
    items = [
        *core,
        item("user_current", "user", C.USER_EARLY, 0),
        *hist,
        *poison,
    ]
    workloads.append(
        wl(
            "early_history",
            "Critical fact in the first history turn",
            "early-history",
            "Task-origin fact sits in the oldest history item, then a long thread.",
            items,
            ["hist_0000"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Class-based history packing pins oldest. Pure recency may drop it.",
        )
    )

    # 14. Knowledge vs recency — answer in RAG, huge recent chat
    hist = make_history(tok, rng, 70, 900, "chat-noise", clock_start=0)
    items = [
        *core,
        item("user_current", "user", C.USER_SLA, 0),
        *hist,
        item("rag_sla_p1", "rag", C.RAG_SLA_P1, 0, relevance=0.97),
        *poison,
    ]
    workloads.append(
        wl(
            "knowledge_vs_recency",
            "Answer in knowledge, pressure from recent chat",
            "knowledge-vs-recency",
            "The SLA lives in a small high-relevance RAG chunk. History is long and recent.",
            items,
            ["rag_sla_p1"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Recency may spend leftover on chat. Floors should keep the RAG item.",
        )
    )

    # 15. Protected overflow at small windows (huge user + large system already)
    huge_user = expand(tok, C.USER_POLICY + "\n\n", "huge-user-protected", 40_000, rng)
    items = [
        *core,
        item("user_current", "user", huge_user, 0),
        *make_rag(tok, rng, 10, 1200),
        *make_history(tok, rng, 10, 800, "protected-overflow", clock_start=0),
    ]
    workloads.append(
        wl(
            "protected_pressure",
            "Protected user competes with huge paste",
            "protected-pressure",
            "Protected lane is large because the user paste is huge. Elastic should still "
            "exist only after user truncation.",
            items,
            [],
            SURVIVE,
            [],
            "User truncates. System/security must remain untruncated. No fail-closed unless system fails.",
        )
    )

    # 16. Huge mixed for 256k
    hist = make_history(tok, rng, 80, 1200, "huge-mixed", clock_start=0)
    rag = make_rag(tok, rng, 60, 1800, special={3: ("rag_sla_p1", C.RAG_SLA_P1, 0.92)})
    mem = make_memory(tok, rng, 20, 1200)
    tools, clock = make_tools(tok, rng, 16, 2500, clock_start=80)
    agents, _ = make_agents(tok, rng, 16, 1200, clock_start=clock)
    items = [
        *core,
        item("user_current", "user", C.USER_MIXED, 0),
        *hist,
        *rag,
        *mem,
        *tools,
        *agents,
        *poison,
    ]
    workloads.append(
        wl(
            "huge_mixed",
            "Huge mixed overflow",
            "huge-mixed",
            "Scaled mixed workload to pressure 128k and 256k windows.",
            items,
            ["rag_sla_p1"],
            SURVIVE,
            ["poison_rag_inject", "poison_memory"],
            "Same story as mixed_overflow with more tokens.",
        )
    )

    return workloads


def preview_text(workload: Workload, tok: Tokenizer, limit: int = 40) -> str:
    lines = [
        f"# {workload.id} — {workload.name}",
        f"shape: {workload.shape}",
        f"tenant: {workload.tenant_id}",
        f"items: {len(workload.items)}",
        f"description: {workload.description}",
        f"critical_evidence: {workload.ground_truth.critical_evidence_ids}",
        f"must_survive: {workload.ground_truth.must_survive_ids}",
        f"must_never: {workload.ground_truth.must_never_ids}",
        f"notes: {workload.ground_truth.notes}",
        "",
        "## item inventory",
    ]
    by_cls: dict[str, list[ContextItem]] = {}
    for it in workload.items:
        by_cls.setdefault(it.cls, []).append(it)
    for cls, group in by_cls.items():
        tokens = sum(tok.count(it.content) for it in group)
        lines.append(f"- {cls}: {len(group)} items, ~{tokens} tokens")
    lines.append("")
    lines.append("## first items (truncated for preview)")
    for it in workload.items[:limit]:
        snippet = it.content.replace("\n", " ")[:180]
        lines.append(
            f"- {it.id} cls={it.cls} seq={it.sequence} rel={it.relevance} "
            f"tenant={it.tenant_id} prot={it.protected} :: {snippet}"
        )
    return "\n".join(lines) + "\n"


def write_workloads(workloads: list[Workload], tok: Tokenizer) -> None:
    WORKLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for wl_obj in workloads:
        path = WORKLOAD_DIR / f"{wl_obj.id}.json"
        path.write_text(json.dumps(wl_obj.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (PREVIEW_DIR / f"{wl_obj.id}.md").write_text(preview_text(wl_obj, tok), encoding="utf-8")
        tokens = sum(tok.count(it.content) for it in wl_obj.items)
        manifest.append(
            {
                "id": wl_obj.id,
                "name": wl_obj.name,
                "shape": wl_obj.shape,
                "n_items": len(wl_obj.items),
                "approx_tokens_cl100k": tokens,
                "evidence": wl_obj.ground_truth.critical_evidence_ids,
            }
        )
    (SAMPLE_DIR / "manifest.json").write_text(
        json.dumps({"seed": SEED, "tokenizer": tok.name, "workloads": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    readme = SAMPLE_DIR / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Sample workloads",
                "",
                "Synthetic Northstar Logistics / Relay agent context.",
                "Generated by `python -m benchmark.data.generate` with seed 42.",
                "",
                "Each `workloads/*.json` has `items` (allocator-visible) and `ground_truth` (benchmark-only).",
                "Allocators are given `items` plus the request `tenant_id`. They never receive `ground_truth`.",
                "",
                "See `previews/` for a short inventory of each workload.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def load_workloads() -> list[Workload]:
    if not WORKLOAD_DIR.exists():
        return []
    out = []
    for path in sorted(WORKLOAD_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out.append(Workload.from_dict(data))
    return out


def main() -> None:
    tok = default_tokenizer()
    print(f"generating workloads with tokenizer={tok.name}")
    workloads = build_all(tok)
    write_workloads(workloads, tok)
    print(f"wrote {len(workloads)} workloads to {WORKLOAD_DIR}")
    for wl_obj in workloads:
        tokens = sum(tok.count(it.content) for it in wl_obj.items)
        print(f"  {wl_obj.id:24s} items={len(wl_obj.items):4d} tokens~{tokens}")


if __name__ == "__main__":
    main()
