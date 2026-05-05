# YC QuickBooks Web Connector

Syncs QuickBooks Desktop Enterprise data to Supabase for:
- **YC Works LLC dba Nature's Storehouse** (Canton, NY) — `yc_works` schema
- **Sandy Maine Inc dba Adirondack Fragrance Farm** — `adk_fragrance` schema
- **Maine & Maine, LLC** — `maine_and_maine` schema
- **YC Consulting** — `yc_consulting` schema

> **Schema consolidation 2026-05-05:** The legacy `natures_storehouse`
> schema was dropped — Nature's Storehouse is the same legal entity as
> YC Works LLC. All Canton/Nature's Storehouse data now lives in
> `yc_works`. The connector still recognizes legacy NS-style usernames
> (e.g. `YCConnector_NS`) and routes them to `yc_works`.

> **PII policy:** see [`docs/PII_POLICY.md`](docs/PII_POLICY.md). Personal
> identifying fields (home address, personal phone/email, SSN, bank account,
> DOB) are dropped at the parser layer and never reach Postgres. Vendor
> `TaxIdent` is also dropped because 8/13 adk_fragrance vendors had
> SSN-shaped values (1099 sole proprietors).

Each company gets its own isolated Postgres schema in Supabase (`natures_storehouse`, `adk_fragrance`).
Shared sync metadata lives in `qb_meta`.

## Quick Start

### 1. Clone and configure

```bash
git clone <repo>
cd yc-qb-web-connector
cp .env.example .env
# Edit .env — add Supabase keys and set QBWC_PASSWORD
```

### 2. Bootstrap Supabase schemas

```bash
pip install psycopg2-binary pyyaml python-dotenv
python scripts/bootstrap_schemas.py
```

This creates:
- `qb_meta` schema (sync state, company registry)
- `natures_storehouse` schema (all QB tables)
- `adk_fragrance` schema (all QB tables)

### 3. Run the connector

```bash
# Local dev
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8080

# Docker
docker compose up -d
```

### 4. Generate .qwc files

```bash
python scripts/generate_qwc.py --host https://your-server.com
```

Drop the generated `.qwc` files on the Windows machine:
1. Open QB Web Connector
2. Add Application → select the `.qwc` file
3. Enter the password (matches `QBWC_PASSWORD` in `.env`)
4. Click **Update Selected** to trigger first sync

---

## Supabase Project

- **Project:** `vynzrvgoyqorqxogjrgw`
- **URL:** `https://vynzrvgoyqorqxogjrgw.supabase.co`
- **Credentials:** in Bitwarden (`QB_SUPABASE_*`)

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /health` | Health check |
| `GET /status` | Sync status for all companies |
| `GET /status/{company_id}` | Status for one company |
| `POST /reset/{company_id}` | Force full re-sync of all entities |
| `POST /reset/{company_id}/{entity}` | Force full re-sync of one entity |
| `POST /qbwc/` | SOAP endpoint (QBWC connects here) |
| `GET /qbwc?wsdl` | WSDL |

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Configuration

Edit `config/companies.yaml` to:
- Add/remove entities per company
- Change sync intervals
- Add a new company (create new schema, add entry)

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full design details including:
- Schema isolation approach
- QBWC SOAP protocol
- Iterator pattern
- Incremental sync strategy
- Multi-company routing by username
