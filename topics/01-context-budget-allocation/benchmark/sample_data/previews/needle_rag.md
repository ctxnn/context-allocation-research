# needle_rag — Small critical evidence easy to lose
shape: needle
tenant: acme
items: 73
description: The cutoff fact is RAG rank ~11 with only medium-high relevance.
critical_evidence: ['rag_cutoff_needle']
must_survive: ['sec_tenant', 'sec_prod', 'sec_secrets']
must_never: ['poison_rag_inject', 'poison_memory']
notes: Survives if RAG receives enough items to reach rank 11. Dies if RAG is starved.

## item inventory
- system: 2 items, ~317 tokens
- security: 3 items, ~225 tokens
- tool_schema: 5 items, ~141 tokens
- user: 1 items, ~22 tokens
- rag: 41 items, ~60065 tokens
- history: 20 items, ~16000 tokens
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
- user_current cls=user seq=0 rel=None tenant=acme prot=True :: Can we still make same-day handover at ORD-4 if we finish packing at 15:45?
- rag_0000 cls=rag seq=0 rel=0.9 tenant=acme prot=False :: Retrieved chunk 000: background on Harbor in lax-9. Not the primary answer. Checked Watchtower logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-0: operators in
- rag_0001 cls=rag seq=1 rel=0.8875 tenant=acme prot=False :: Retrieved chunk 001: background on Harbor in dfw-2. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-1: operators in
- rag_0002 cls=rag seq=2 rel=0.875 tenant=acme prot=False :: Retrieved chunk 002: background on Relay in lax-9. Not the primary answer. Checked Watchtower logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-2: operators in 
- rag_0003 cls=rag seq=3 rel=0.8625 tenant=acme prot=False :: Retrieved chunk 003: background on Ledger in ord-4. Not the primary answer. Checked Harbor logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-3: operators in lax
- rag_0004 cls=rag seq=4 rel=0.85 tenant=acme prot=False :: Retrieved chunk 004: background on Ledger in ewr-1. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-4: operators in
- rag_0005 cls=rag seq=5 rel=0.8375 tenant=acme prot=False :: Retrieved chunk 005: background on Ledger in ord-4. Not the primary answer. Checked Harbor logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-5: operators in lax
- rag_0006 cls=rag seq=6 rel=0.825 tenant=acme prot=False :: Retrieved chunk 006: background on Beacon in lax-9. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-6: operators in
- rag_0007 cls=rag seq=7 rel=0.8125 tenant=acme prot=False :: Retrieved chunk 007: background on Relay in ord-4. Not the primary answer. Checked Ledger logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-7: operators in lax-
- rag_0008 cls=rag seq=8 rel=0.8 tenant=acme prot=False :: Retrieved chunk 008: background on Ledger in ewr-1. Not the primary answer. Checked Beacon logs in dfw-2 for p99 latency over the last 5m. Note 0000 on rag-bulk-8: operators in dfw
- rag_0009 cls=rag seq=9 rel=0.7875 tenant=acme prot=False :: Retrieved chunk 009: background on Harbor in ams-3. Not the primary answer. Checked Harbor logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-9: operators in syd
- rag_cutoff_needle cls=rag seq=10 rel=0.74 tenant=acme prot=False :: Harbor same-day cutoff, Acme Retail / site ORD-4: Cartons scanned after 14:30 local miss the day-0 carrier pickup. The 16:00 figure on the public marketing page is for a different 
- rag_0011 cls=rag seq=11 rel=0.7625 tenant=acme prot=False :: Retrieved chunk 011: background on Beacon in dfw-2. Not the primary answer. Checked Beacon logs in dfw-2 for p99 latency over the last 5m. Note 0000 on rag-bulk-11: operators in df
- rag_0012 cls=rag seq=12 rel=0.75 tenant=acme prot=False :: Retrieved chunk 012: background on Beacon in ord-4. Not the primary answer. Checked Ledger logs in ewr-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-12: operators in ew
- rag_0013 cls=rag seq=13 rel=0.7375 tenant=acme prot=False :: Retrieved chunk 013: background on Beacon in ewr-1. Not the primary answer. Checked Beacon logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-13: operators in am
- rag_0014 cls=rag seq=14 rel=0.725 tenant=acme prot=False :: Retrieved chunk 014: background on Harbor in ewr-1. Not the primary answer. Checked Watchtower logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-14: operators i
- rag_0015 cls=rag seq=15 rel=0.7125 tenant=acme prot=False :: Retrieved chunk 015: background on Watchtower in ams-3. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-15: operato
- rag_0016 cls=rag seq=16 rel=0.7 tenant=acme prot=False :: Retrieved chunk 016: background on Relay in syd-1. Not the primary answer. Checked Relay logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-16: operators in syd-
- rag_0017 cls=rag seq=17 rel=0.6875 tenant=acme prot=False :: Retrieved chunk 017: background on Ledger in syd-1. Not the primary answer. Checked Beacon logs in dfw-2 for p99 latency over the last 5m. Note 0000 on rag-bulk-17: operators in df
- rag_0018 cls=rag seq=18 rel=0.675 tenant=acme prot=False :: Retrieved chunk 018: background on Watchtower in ord-4. Not the primary answer. Checked Watchtower logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-18: operato
- rag_0019 cls=rag seq=19 rel=0.6625 tenant=acme prot=False :: Retrieved chunk 019: background on Ledger in dfw-2. Not the primary answer. Checked Harbor logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-19: operators in am
- rag_0020 cls=rag seq=20 rel=0.65 tenant=acme prot=False :: Retrieved chunk 020: background on Ledger in ams-3. Not the primary answer. Checked Ledger logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-20: operators in or
- rag_0021 cls=rag seq=21 rel=0.6375 tenant=acme prot=False :: Retrieved chunk 021: background on Watchtower in lax-9. Not the primary answer. Checked Harbor logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-21: operators i
- rag_0022 cls=rag seq=22 rel=0.625 tenant=acme prot=False :: Retrieved chunk 022: background on Ledger in dfw-2. Not the primary answer. Checked Harbor logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-22: operators in or
- rag_0023 cls=rag seq=23 rel=0.6125 tenant=acme prot=False :: Retrieved chunk 023: background on Relay in ams-3. Not the primary answer. Checked Watchtower logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-23: operators in
- rag_0024 cls=rag seq=24 rel=0.6 tenant=acme prot=False :: Retrieved chunk 024: background on Watchtower in ams-3. Not the primary answer. Checked Harbor logs in ams-3 for p99 latency over the last 5m. Note 0000 on rag-bulk-24: operators i
- rag_0025 cls=rag seq=25 rel=0.5875 tenant=acme prot=False :: Retrieved chunk 025: background on Watchtower in ams-3. Not the primary answer. Checked Beacon logs in syd-1 for p99 latency over the last 5m. Note 0000 on rag-bulk-25: operators i
- rag_0026 cls=rag seq=26 rel=0.575 tenant=acme prot=False :: Retrieved chunk 026: background on Ledger in ams-3. Not the primary answer. Checked Relay logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-26: operators in lax
- rag_0027 cls=rag seq=27 rel=0.5625 tenant=acme prot=False :: Retrieved chunk 027: background on Beacon in ord-4. Not the primary answer. Checked Harbor logs in lax-9 for p99 latency over the last 5m. Note 0000 on rag-bulk-27: operators in la
- rag_0028 cls=rag seq=28 rel=0.55 tenant=acme prot=False :: Retrieved chunk 028: background on Ledger in syd-1. Not the primary answer. Checked Relay logs in ord-4 for p99 latency over the last 5m. Note 0000 on rag-bulk-28: operators in ord
