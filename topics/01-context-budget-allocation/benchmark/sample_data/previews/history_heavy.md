# history_heavy — History-heavy (answer in recent turn)
shape: history-heavy
tenant: acme
items: 134
description: Long debugging thread. The fact needed is in a late history turn.
critical_evidence: ['hist_0118']
must_survive: ['sec_tenant', 'sec_prod', 'sec_secrets']
must_never: ['poison_rag_inject', 'poison_memory']
notes: Recency should do well. Class floors should still keep some history.

## item inventory
- system: 2 items, ~317 tokens
- security: 3 items, ~225 tokens
- tool_schema: 5 items, ~141 tokens
- user: 1 items, ~16 tokens
- history: 120 items, ~84000 tokens
- rag: 2 items, ~157 tokens
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
- user_current cls=user seq=0 rel=None tenant=acme prot=True :: Summarize the root cause we just found for the webhook 401s.
- hist_0000 cls=history seq=0 rel=None tenant=acme prot=False :: User: starting investigation. Customer id is C-8891, but that is not the current question. Checked Harbor logs in syd-1 for p99 latency over the last 5m. Note 0000 on webhook-401: 
- hist_0001 cls=history seq=1 rel=None tenant=acme prot=False :: Assistant: recorded C-8891. We will debug Beacon staging 401s next. Checked Ledger logs in ord-4 for p99 latency over the last 5m. Note 0000 on webhook-401: operators in ord-4 trea
- hist_0002 cls=history seq=2 rel=None tenant=acme prot=False :: User turn 2: still on webhook-401. We are looking at apps/ledger/exporter.py. Can you check ewr-1 again? Checked Harbor logs in ewr-1 for p99 latency over the last 5m. Note 0000 on
- hist_0003 cls=history seq=3 rel=None tenant=acme prot=False :: Assistant turn 3: I checked Relay in ord-4. Current hypothesis is wrong warehouse cutoff. Checked Harbor logs in ord-4 for p99 latency over the last 5m. Note 0000 on webhook-401: o
- hist_0004 cls=history seq=4 rel=None tenant=acme prot=False :: User turn 4: still on webhook-401. We are looking at apps/beacon/webhooks.py. Can you check ewr-1 again? Checked Relay logs in ewr-1 for p99 latency over the last 5m. Note 0000 on 
- hist_0005 cls=history seq=5 rel=None tenant=acme prot=False :: Assistant turn 5: I checked Relay in ord-4. Current hypothesis is deadletter overflow. Checked Relay logs in syd-1 for p99 latency over the last 5m. Note 0000 on webhook-401: opera
- hist_0006 cls=history seq=6 rel=None tenant=acme prot=False :: User turn 6: still on webhook-401. We are looking at runbooks/p1-exceptions.md. Can you check ewr-1 again? Checked Relay logs in lax-9 for p99 latency over the last 5m. Note 0000 o
- hist_0007 cls=history seq=7 rel=None tenant=acme prot=False :: Assistant turn 7: I checked Ledger in ord-4. Current hypothesis is unsigned webhook body. Checked Watchtower logs in syd-1 for p99 latency over the last 5m. Note 0000 on webhook-40
- hist_0008 cls=history seq=8 rel=None tenant=acme prot=False :: User turn 8: still on webhook-401. We are looking at infra/harbor/cutoff.yaml. Can you check dfw-2 again? Checked Beacon logs in ewr-1 for p99 latency over the last 5m. Note 0000 o
- hist_0009 cls=history seq=9 rel=None tenant=acme prot=False :: Assistant turn 9: I checked Ledger in ord-4. Current hypothesis is stale feature flag. Checked Harbor logs in lax-9 for p99 latency over the last 5m. Note 0000 on webhook-401: oper
- hist_0010 cls=history seq=10 rel=None tenant=acme prot=False :: User turn 10: still on webhook-401. We are looking at infra/harbor/cutoff.yaml. Can you check dfw-2 again? Checked Ledger logs in ams-3 for p99 latency over the last 5m. Note 0000 
- hist_0011 cls=history seq=11 rel=None tenant=acme prot=False :: Assistant turn 11: I checked Harbor in syd-1. Current hypothesis is tenant filter omitted in a join. Checked Harbor logs in ams-3 for p99 latency over the last 5m. Note 0000 on web
- hist_0012 cls=history seq=12 rel=None tenant=acme prot=False :: User turn 12: still on webhook-401. We are looking at runbooks/p1-exceptions.md. Can you check ord-4 again? Checked Ledger logs in ams-3 for p99 latency over the last 5m. Note 0000
- hist_0013 cls=history seq=13 rel=None tenant=acme prot=False :: Assistant turn 13: I checked Relay in dfw-2. Current hypothesis is deadletter overflow. Checked Harbor logs in syd-1 for p99 latency over the last 5m. Note 0000 on webhook-401: ope
- hist_0014 cls=history seq=14 rel=None tenant=acme prot=False :: User turn 14: still on webhook-401. We are looking at apps/beacon/webhooks.py. Can you check syd-1 again? Checked Ledger logs in ewr-1 for p99 latency over the last 5m. Note 0000 o
- hist_0015 cls=history seq=15 rel=None tenant=acme prot=False :: Assistant turn 15: I checked Harbor in ewr-1. Current hypothesis is stale feature flag. Checked Ledger logs in lax-9 for p99 latency over the last 5m. Note 0000 on webhook-401: ope
- hist_0016 cls=history seq=16 rel=None tenant=acme prot=False :: User turn 16: still on webhook-401. We are looking at runbooks/p1-exceptions.md. Can you check syd-1 again? Checked Beacon logs in dfw-2 for p99 latency over the last 5m. Note 0000
- hist_0017 cls=history seq=17 rel=None tenant=acme prot=False :: Assistant turn 17: I checked Ledger in dfw-2. Current hypothesis is deadletter overflow. Checked Ledger logs in syd-1 for p99 latency over the last 5m. Note 0000 on webhook-401: op
- hist_0018 cls=history seq=18 rel=None tenant=acme prot=False :: User turn 18: still on webhook-401. We are looking at configs/acme/rate_limits.json. Can you check syd-1 again? Checked Harbor logs in syd-1 for p99 latency over the last 5m. Note 
- hist_0019 cls=history seq=19 rel=None tenant=acme prot=False :: Assistant turn 19: I checked Relay in syd-1. Current hypothesis is unsigned webhook body. Checked Beacon logs in ams-3 for p99 latency over the last 5m. Note 0000 on webhook-401: o
- hist_0020 cls=history seq=20 rel=None tenant=acme prot=False :: User turn 20: still on webhook-401. We are looking at apps/ledger/exporter.py. Can you check lax-9 again? Checked Ledger logs in lax-9 for p99 latency over the last 5m. Note 0000 o
- hist_0021 cls=history seq=21 rel=None tenant=acme prot=False :: Assistant turn 21: I checked Relay in ewr-1. Current hypothesis is rate-limit budget leak. Checked Beacon logs in ord-4 for p99 latency over the last 5m. Note 0000 on webhook-401: 
- hist_0022 cls=history seq=22 rel=None tenant=acme prot=False :: User turn 22: still on webhook-401. We are looking at apps/beacon/webhooks.py. Can you check dfw-2 again? Checked Ledger logs in lax-9 for p99 latency over the last 5m. Note 0000 o
- hist_0023 cls=history seq=23 rel=None tenant=acme prot=False :: Assistant turn 23: I checked Harbor in ewr-1. Current hypothesis is rate-limit budget leak. Checked Watchtower logs in ewr-1 for p99 latency over the last 5m. Note 0000 on webhook-
- hist_0024 cls=history seq=24 rel=None tenant=acme prot=False :: User turn 24: still on webhook-401. We are looking at runbooks/p1-exceptions.md. Can you check syd-1 again? Checked Beacon logs in lax-9 for p99 latency over the last 5m. Note 0000
- hist_0025 cls=history seq=25 rel=None tenant=acme prot=False :: Assistant turn 25: I checked Ledger in ewr-1. Current hypothesis is deadletter overflow. Checked Relay logs in syd-1 for p99 latency over the last 5m. Note 0000 on webhook-401: ope
- hist_0026 cls=history seq=26 rel=None tenant=acme prot=False :: User turn 26: still on webhook-401. We are looking at apps/watchtower/sla.py. Can you check dfw-2 again? Checked Relay logs in syd-1 for p99 latency over the last 5m. Note 0000 on 
- hist_0027 cls=history seq=27 rel=None tenant=acme prot=False :: Assistant turn 27: I checked Watchtower in ams-3. Current hypothesis is wrong warehouse cutoff. Checked Beacon logs in dfw-2 for p99 latency over the last 5m. Note 0000 on webhook-
- hist_0028 cls=history seq=28 rel=None tenant=acme prot=False :: User turn 28: still on webhook-401. We are looking at apps/ledger/exporter.py. Can you check ams-3 again? Checked Harbor logs in lax-9 for p99 latency over the last 5m. Note 0000 o
