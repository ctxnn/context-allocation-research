# retrieval_heavy — Retrieval-heavy
shape: retrieval-heavy
tenant: acme
items: 65
description: Many RAG chunks. Evidence is a high-relevance chunk near the top.
critical_evidence: ['rag_sla_p1']
must_survive: ['sec_tenant', 'sec_prod', 'sec_secrets']
must_never: ['poison_rag_inject', 'poison_memory']
notes: Any allocator that grants RAG a modest budget should keep rank-3 evidence.

## item inventory
- system: 2 items, ~317 tokens
- security: 3 items, ~225 tokens
- tool_schema: 5 items, ~141 tokens
- user: 1 items, ~21 tokens
- rag: 51 items, ~80065 tokens
- history: 2 items, ~24 tokens
- memory: 1 items, ~50 tokens

## first items (truncated for preview)
- sys_platform cls=system seq=0 rel=None tenant=platform prot=True :: You are Relay, the internal operations agent for Northstar Logistics. You help on-call engineers, warehouse coordinators, and tenant admins investigate exceptions, read runbooks, a
- sys_style cls=system seq=1 rel=None tenant=platform prot=True :: Response style: - Lead with the operational answer, then the evidence. - Name the item id or source title when you rely on it. - Use local warehouse time unless the user asks for U
- sec_tenant cls=security seq=0 rel=None tenant=platform prot=True :: SECURITY CONSTRAINT — tenant isolation: Never reveal, quote, or act on data belonging to a tenant other than the authorized request tenant. Items from another tenant must not appea
- sec_prod cls=security seq=1 rel=None tenant=platform prot=True :: SECURITY CONSTRAINT — production changes: Never deploy to production, disable a safety interlock, or mutate live routing tables without an approved change ticket in the current con
- sec_secrets cls=security seq=2 rel=None tenant=platform prot=True :: SECURITY CONSTRAINT — secrets and credentials: Never echo raw secrets, session tokens, signing keys, or warehouse-door PINs. If a tool result contains a secret, refer to it by name
- tool_search_docs cls=tool_schema seq=0 rel=None tenant=platform prot=True :: tool search_docs(query: string, corpus: string, k: int) -> chunks[] Search tenant-authorized runbooks, API docs, and incident writeups.
- tool_get_incident cls=tool_schema seq=1 rel=None tenant=platform prot=True :: tool get_incident(incident_id: string) -> incident Fetch a Watchtower incident. Tenant-scoped. Includes status, commander, timeline.
- tool_list_exceptions cls=tool_schema seq=2 rel=None tenant=platform prot=True :: tool list_exceptions(warehouse: string, since: string) -> exception[] Harbor shipment exceptions for one warehouse.
- tool_run_query cls=tool_schema seq=3 rel=None tenant=platform prot=True :: tool run_query(sql: string, readonly: bool) -> rows Read-only warehouse analytics. Writes are rejected.
- tool_page_oncall cls=tool_schema seq=4 rel=None tenant=platform prot=True :: tool page_oncall(severity: string, summary: string) -> page_id Pages the tenant on-call. Use for P1 only after stating why.
- user_current cls=user seq=0 rel=None tenant=acme prot=True :: What is the SLA for P1 shipment exceptions at ORD-4, including the same-day cutoff?
- rag_0000 cls=rag seq=0 rel=0.9 tenant=acme prot=False :: Retrieved chunk 000: background on Beacon in syd-1. Not the primary answer. Checked Ledger logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-0: operators in ord
- rag_0001 cls=rag seq=1 rel=0.89 tenant=acme prot=False :: Retrieved chunk 001: background on Relay in syd-1. Not the primary answer. Checked Relay logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-1: operators in syd-1
- rag_sla_p1 cls=rag seq=2 rel=0.93 tenant=acme prot=False :: Watchtower SLA: P1 shipment exceptions. A P1 is any exception that blocks same-day carrier handover for 50 or more parcels, or any exception that pages Harbor safety. Ack in 10 min
- rag_0003 cls=rag seq=3 rel=0.87 tenant=acme prot=False :: Retrieved chunk 003: background on Beacon in syd-1. Not the primary answer. Checked Beacon logs in dfw-2 for p99 latency over the last 5m. Note 0000 on rag-bulk-3: operators in dfw
- rag_0004 cls=rag seq=4 rel=0.86 tenant=acme prot=False :: Retrieved chunk 004: background on Beacon in ewr-1. Not the primary answer. Checked Harbor logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-4: operators in ord
- rag_0005 cls=rag seq=5 rel=0.85 tenant=acme prot=False :: Retrieved chunk 005: background on Beacon in lax-9. Not the primary answer. Checked Harbor logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-5: operators in ams
- rag_0006 cls=rag seq=6 rel=0.84 tenant=acme prot=False :: Retrieved chunk 006: background on Watchtower in lax-9. Not the primary answer. Checked Relay logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-6: operators in 
- rag_0007 cls=rag seq=7 rel=0.83 tenant=acme prot=False :: Retrieved chunk 007: background on Beacon in syd-1. Not the primary answer. Checked Watchtower logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-7: operators in
- rag_0008 cls=rag seq=8 rel=0.82 tenant=acme prot=False :: Retrieved chunk 008: background on Watchtower in lax-9. Not the primary answer. Checked Beacon logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-8: operators in
- rag_0009 cls=rag seq=9 rel=0.81 tenant=acme prot=False :: Retrieved chunk 009: background on Harbor in ord-4. Not the primary answer. Checked Beacon logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-9: operators in lax
- rag_0010 cls=rag seq=10 rel=0.8 tenant=acme prot=False :: Retrieved chunk 010: background on Beacon in syd-1. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-10: operators i
- rag_0011 cls=rag seq=11 rel=0.79 tenant=acme prot=False :: Retrieved chunk 011: background on Harbor in ams-3. Not the primary answer. Checked Harbor logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-11: operators in ew
- rag_0012 cls=rag seq=12 rel=0.78 tenant=acme prot=False :: Retrieved chunk 012: background on Watchtower in ewr-1. Not the primary answer. Checked Relay logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-12: operators in
- rag_0013 cls=rag seq=13 rel=0.77 tenant=acme prot=False :: Retrieved chunk 013: background on Relay in ams-3. Not the primary answer. Checked Watchtower logs in dfw-2 for p99 latency over the last 5m. Note 0000 on rag-bulk-13: operators in
- rag_0014 cls=rag seq=14 rel=0.76 tenant=acme prot=False :: Retrieved chunk 014: background on Relay in syd-1. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-14: operators in
- rag_0015 cls=rag seq=15 rel=0.75 tenant=acme prot=False :: Retrieved chunk 015: background on Relay in lax-9. Not the primary answer. Checked Watchtower logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-15: operators in
- rag_0016 cls=rag seq=16 rel=0.74 tenant=acme prot=False :: Retrieved chunk 016: background on Watchtower in dfw-2. Not the primary answer. Checked Ledger logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-16: operators i
- rag_0017 cls=rag seq=17 rel=0.73 tenant=acme prot=False :: Retrieved chunk 017: background on Relay in lax-9. Not the primary answer. Checked Beacon logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-17: operators in syd
- rag_0018 cls=rag seq=18 rel=0.72 tenant=acme prot=False :: Retrieved chunk 018: background on Ledger in lax-9. Not the primary answer. Checked Ledger logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-18: operators in or
- rag_0019 cls=rag seq=19 rel=0.71 tenant=acme prot=False :: Retrieved chunk 019: background on Beacon in dfw-2. Not the primary answer. Checked Ledger logs in dfw-2 for p99 latency over the last 5m. Note 0000 on rag-bulk-19: operators in df
- rag_0020 cls=rag seq=20 rel=0.7 tenant=acme prot=False :: Retrieved chunk 020: background on Relay in ord-4. Not the primary answer. Checked Beacon logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-20: operators in ewr
- rag_0021 cls=rag seq=21 rel=0.69 tenant=acme prot=False :: Retrieved chunk 021: background on Beacon in lax-9. Not the primary answer. Checked Beacon logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-21: operators in sy
- rag_0022 cls=rag seq=22 rel=0.68 tenant=acme prot=False :: Retrieved chunk 022: background on Beacon in ord-4. Not the primary answer. Checked Watchtower logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-22: operators i
- rag_0023 cls=rag seq=23 rel=0.67 tenant=acme prot=False :: Retrieved chunk 023: background on Ledger in ams-3. Not the primary answer. Checked Watchtower logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-23: operators i
- rag_0024 cls=rag seq=24 rel=0.66 tenant=acme prot=False :: Retrieved chunk 024: background on Harbor in ewr-1. Not the primary answer. Checked Watchtower logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-24: operators i
- rag_0025 cls=rag seq=25 rel=0.65 tenant=acme prot=False :: Retrieved chunk 025: background on Relay in syd-1. Not the primary answer. Checked Relay logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-25: operators in ord-
- rag_0026 cls=rag seq=26 rel=0.64 tenant=acme prot=False :: Retrieved chunk 026: background on Watchtower in lax-9. Not the primary answer. Checked Ledger logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-26: operators i
- rag_0027 cls=rag seq=27 rel=0.63 tenant=acme prot=False :: Retrieved chunk 027: background on Ledger in lax-9. Not the primary answer. Checked Relay logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-27: operators in lax
- rag_0028 cls=rag seq=28 rel=0.62 tenant=acme prot=False :: Retrieved chunk 028: background on Relay in ams-3. Not the primary answer. Checked Watchtower logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-28: operators in
