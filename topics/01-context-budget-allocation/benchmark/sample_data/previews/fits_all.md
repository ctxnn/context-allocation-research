# fits_all — Everything fits
shape: normal
tenant: acme
items: 17
description: Small authorized set. Every serious allocator should include everything.
critical_evidence: ['rag_billing_retry']
must_survive: ['sec_tenant', 'sec_prod', 'sec_secrets']
must_never: []
notes: Sanity check: no overflow, recall=1, leakage=0 at all profiles.

## item inventory
- system: 2 items, ~317 tokens
- security: 3 items, ~225 tokens
- tool_schema: 5 items, ~141 tokens
- user: 1 items, ~16 tokens
- rag: 1 items, ~139 tokens
- memory: 1 items, ~70 tokens
- history: 2 items, ~23 tokens
- tool_result: 1 items, ~122 tokens
- agent: 1 items, ~44 tokens

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
- user_current cls=user seq=0 rel=None tenant=acme prot=True :: What's the retry policy for the billing exporter, and when is the cutoff?
- rag_billing_retry cls=rag seq=0 rel=0.96 tenant=acme prot=False :: Ledger runbook: billing exporter retries. The billing exporter for tenant-scoped invoices retries failed posts to the ERP with exponential backoff: 30s, 2m, 10m, then 1h, capped at
- mem_csv_monday cls=memory seq=0 rel=0.55 tenant=acme prot=False :: Acme Retail preference, recorded 2026-03-11: Finance wants exception exports as CSV, generated Monday 07:00 local, emailed to finance-ops@acme.example. Do not switch them to parque
- hist_0000 cls=history seq=0 rel=None tenant=acme prot=False :: User: we are debugging Ledger exports for Acme.
- hist_0001 cls=history seq=1 rel=None tenant=acme prot=False :: Assistant: I will look up the billing exporter runbook.
- toolres_inc cls=tool_result seq=2 rel=None tenant=acme prot=False :: get_incident(INC-2044) -> id: INC-2044 tenant: acme status: mitigated severity: P1 commander: warehouse-lead-ord4 summary: same-day handover blocked by label printer firmware misma
- agent_planner cls=agent seq=3 rel=None tenant=acme prot=False :: Planner agent: scope this as a Watchtower P1 review plus Harbor cutoff check. Do not approve production deploys. Ask the researcher for the ORD-4 cutoff and the reviewer for whethe
