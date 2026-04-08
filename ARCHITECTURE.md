# Architecture

## Overview

```
QB Enterprise (Windows 24/7)
    └── QB Web Connector (QBWC)
            ├── YCConnector_NS.qwc  ──► SOAP /qbwc/  ─► natures_storehouse schema
            └── YCConnector_ADK.qwc ──► SOAP /qbwc/  ─► adk_fragrance schema
```

One QBWC application per company. Each `.qwc` file has a distinct username so the
connector can route to the correct Postgres schema.

---

## Supabase Database Layout

### Schema isolation (not column isolation)

Each company's data lives in its own Postgres schema. There is no `company_id` column.

```
Supabase project: vynzrvgoyqorqxogjrgw
│
├── qb_meta                      # Shared metadata (sync state, company registry)
│   ├── companies                # Company registry: company_id → pg_schema
│   ├── sync_state               # Last sync per (company_id, entity_type)
│   └── sync_log                 # Append-only history
│
├── natures_storehouse           # Nature's Storehouse data
│   ├── accounts
│   ├── customers
│   ├── vendors
│   ├── employees
│   ├── items
│   ├── invoices + invoice_lines
│   ├── bills + bill_lines
│   ├── journal_entries + journal_entry_lines
│   └── ... (all 27 entity tables)
│
└── adk_fragrance                # ADK Fragrance Farm data
    └── ... (identical structure)
```

**Why schemas?**
- Queries don't need `WHERE company_id = ...` — just `SELECT * FROM natures_storehouse.invoices`
- Row-level security is simpler (schema-level grants)
- Easy to add a 3rd company without touching existing schemas
- Supabase's PostgREST supports per-schema API routing

---

## QBWC SOAP Protocol

QBWC calls these methods in order each sync cycle:

```
authenticate(username, password)
    → [ticket, ""]      # auth ok, proceed
    → [ticket, "none"]  # nothing to sync
    → [ticket, "nvu"]   # bad credentials

sendRequestXML(ticket, ...)   → qbXML query string | ""
receiveResponseXML(ticket, response_xml, ...)  → progress 0-100
    (QBWC loops sendRequestXML / receiveResponseXML until 100)
closeConnection(ticket)   → "OK"
```

### Session lifecycle

```
authenticate()
    → create SyncSession(company_id, ticket)
    → build_task_queue()  (reads sync_state to decide incremental vs full)
    → return ticket

sendRequestXML()  [called repeatedly]
    → get_next_request() from coordinator
    → returns qbXML for current entity
    → "" when all entities done

receiveResponseXML()  [called after each sendRequestXML]
    → parse_qbxml_response()
    → upsert to company schema
    → update sync_state
    → return progress %

closeConnection()
    → session cleanup
```

---

## Incremental Sync

Each entity tracks `last_synced_at` in `qb_meta.sync_state`.

- **First run:** No `last_synced_at` → full sync (no date filter)
- **Subsequent runs:** `ModifiedDateRangeFilter FromModifiedDate = last_synced_at - 5min`
- The 5-minute lookback buffer catches records modified at the exact boundary

### Iterator pattern

For large datasets (thousands of customers, invoices), QB uses an iterator:

```
Request:  CustomerQueryRq iterator="Start" MaxReturned="100"
Response: CustomerQueryRs iteratorID="{ABC}" iteratorRemainingCount="450"

Request:  CustomerQueryRq iterator="Continue" iteratorID="{ABC}" MaxReturned="100"
Response: CustomerQueryRs iteratorID="{ABC}" iteratorRemainingCount="350"
... (repeat until iteratorRemainingCount="0")
```

The coordinator tracks `iterator_id` and `iterator_remaining` in the `SyncTask` object.

**Critical:** The `Continue` request must NOT include a `ModifiedDateRangeFilter` —
it must be identical to the original request except for `iterator="Continue"`.

---

## Entity Sync Order

Reference data (lists) sync before transactions to satisfy foreign key relationships:

1. accounts, classes, sales_tax_codes, payment_methods, ship_methods, terms
2. customers, vendors, employees, items
3. purchase_orders, bills, bill_payments, vendor_credits
4. estimates, sales_orders, invoices, sales_receipts, credit_memos
5. receive_payments, deposits, checks, credit_card_charges/credits
6. journal_entries, transfers, inventory_adjustments, time_tracking

---

## Multi-company Username Routing

QBWC doesn't pass company context at authentication time. Routing is by username:

| `.qwc` Username   | Routed to          |
|-------------------|--------------------|
| `YCConnector_NS`  | natures_storehouse |
| `YCConnector_ADK` | adk_fragrance      |

Generate `.qwc` files with: `python scripts/generate_qwc.py --host https://your-server.com`

---

## Directory Structure

```
yc-qb-web-connector/
├── src/
│   ├── main.py              # FastAPI app + REST endpoints
│   ├── soap/
│   │   ├── service.py       # spyne SOAP service (QBWC interface)
│   │   └── session.py       # In-memory session store
│   ├── qbxml/
│   │   ├── builders.py      # qbXML request generators
│   │   ├── parsers.py       # qbXML response parsers → Python dicts
│   │   └── entities.py      # Entity definitions + sync order
│   ├── supabase/
│   │   ├── client.py        # Supabase client (service role)
│   │   └── upsert.py        # Schema-aware batch upsert
│   ├── sync/
│   │   ├── coordinator.py   # Drives task queue per session
│   │   └── state.py         # Reads/writes qb_meta.sync_state
│   └── utils/
│       ├── config.py        # Settings + CompanyConfig
│       └── logging.py       # structlog setup
├── migrations/
│   ├── 001_qb_meta.sql      # qb_meta schema + tables
│   └── 002_company_schema_template.sql   # Per-company table set
├── scripts/
│   ├── bootstrap_schemas.py  # Applies migrations to Supabase
│   └── generate_qwc.py       # Generates .qwc files for QBWC
├── config/
│   └── companies.yaml        # Company config (schema names, entities, intervals)
├── tests/
│   ├── test_parsers.py
│   ├── test_builders.py
│   ├── test_config.py
│   └── test_session.py
├── docs/
│   ├── setup-guide.md
│   ├── sync-strategy.md
│   └── qbxml-entities.md
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```
