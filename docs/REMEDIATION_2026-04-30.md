# YC QB Connector — Remediation Notes (2026-04-30)

In response to `YC_QB_Connector_Error_Report.md`. Covers all four issues
from the report plus a note about a fresh issue surfaced during
investigation.

---

## TL;DR

| # | Issue | Verdict | What changed |
|---|---|---|---|
| 1 | Feb-Mar 2024 invoice gap | Could be QB-side or sync-side; cannot fully prove from Supabase alone | Added on-demand date-windowed backfill (new `qb_meta.backfill_jobs` table + `POST /backfill/...` endpoint + windowed qbXML builder). Run the backfill against QB to definitively answer. |
| 2 | Bills table empty since 2024 | Almost certainly a workflow change (bills tapered cleanly: 43→42→41→44/qtr in 2023 → 21→2→1→0 in 2024). Not a connector bug. | Built `<schema>.expenses_unified` view (bills + checks + credit cards + vendor credits + JE expense lines, with a sign-aware amount). Drafted Yen/Sandy confirmation note. |
| 3 | Bills sync staleness | Real silent-failure issue — `qb_meta.sync_log` had **0 rows** despite the table existing. | Coordinator now writes start/done/error rows to `sync_log` per entity per cycle. `/status` flags entities not synced in >6h. |
| 4 | Forward-dated 2026-05-01 invoice | Probably benign (scheduled invoice). | Upsert now logs a warning whenever a transaction is dated more than 1 day in the future. |
| 5 | (NEW) `accounts` entity in `error` state | Connection error 0x80040408 ("Could not start QuickBooks") on the most recent run for `adk_fragrance` | Not a code issue — QB Desktop wasn't running on the Windows host at sync time. Make sure QB is open before QBWC fires. |
| 6 | (NEW) Cross-schema contamination risk | QBWC routes by username, but does NOT verify which QB Desktop file is actually open. If the wrong file is open when a connector fires, that company's data lands in the wrong Supabase schema. | Built a CompanyQueryRq probe that runs as the FIRST request of every session. Compares observed `<CompanyName>` to expected name; on mismatch the entire session is aborted before any data flows. Strict mode opt-in via `POST /identity/{company_id}/lock-in`. |

---

## Addendum: cross-schema contamination safeguards (Issue 6)

**What triggered this:** The QBWC dashboard shows "YC Works LLC" as the
description for both the YC Works connector AND the ADK connector. Tracing
the auth path: username `YCConnector_ADK` always routes to the
`adk_fragrance` schema, regardless of which QB file is actually open. So if
ADKFF's connector fires while YC Works is the open QB file, YC Works data
gets written into the `adk_fragrance` schema — silently.

**Live data check:** No QB TxnIDs are currently shared across schemas (so
no obvious smoking gun in the data right now), and only `adk_fragrance`
has data — the other four schemas are empty. But that doesn't prove no
contamination has happened: it's possible the data currently in
`adk_fragrance` is YC Works data, since QB TxnIDs are unique per file but
the schemas don't have a "QB CompanyName" column to compare against.

**What changed (defense in depth):**

- New migration `012_company_identity_check.sql`:
  - `qb_meta.companies.observed_company_name`, `observed_company_file`,
    `observed_at`
  - `qb_meta.companies.expected_company_name`, `expected_company_file`
  - New table `qb_meta.company_identity_log` — append-only audit of every
    verification attempt, with `matched` and `action_taken`
- New module `src/sync/identity.py` — `CompanyIdentityChecker`. Records
  observations to `qb_meta.companies`, logs every check, and decides
  whether to allow / observe-only / abort.
- `CompanyQueryRq` now runs as the first request of every QBWC session.
  The response sets `session.identity_aborted = True` if the QB-reported
  company name doesn't match the expected name. When that flag is set,
  every subsequent task in the session — backfills, regular incremental
  syncs — is skipped without dispatching a single qbXML query, so no
  data ever lands in the schema.
- New API endpoints:
  - `GET /identity` — every company's expected vs. observed identity
  - `GET /identity/log?company_id=&only_mismatches=true` — audit log
  - `POST /identity/{company_id}/lock-in` — promote the most recent
    observation into `expected_company_name`. After this, future sessions
    that observe a different name are aborted.
  - `POST /identity/{company_id}/clear` — revert to observe-only mode

**How to use it (after deploy):**

1. Deploy the new code. The first sync cycle for each company will
   auto-record the observed company name to `qb_meta.companies`.
2. Inspect: `GET /identity` — confirm `observed_company_name` matches
   what each company SHOULD be reporting.
3. If `adk_fragrance` shows `observed_company_name = "YC Works LLC"` —
   that's the smoking gun. The data already in `adk_fragrance` is wrong
   and needs cleanup. **Don't lock-in.** Stop the connector, fix the
   QBWC file binding (re-add the .qwc file in QBWC while the correct
   file is open), then truncate the wrong-data schema and re-sync.
4. If observations match expectations, call:
   ```
   POST /identity/adk_fragrance/lock-in
   POST /identity/natures_storehouse/lock-in
   POST /identity/yc_works/lock-in
   POST /identity/maine_and_maine/lock-in
   POST /identity/yc_consulting/lock-in
   ```
   From this point on, any session for company X that observes a different
   `<CompanyName>` is aborted before a single row is upserted.

**Important:** the strict mode is OFF until you call `lock-in`. This is
intentional — we don't want to break existing setups on deploy. The
observation step runs immediately and unconditionally, so you can
diagnose. The blocking step only happens after you opt in.

All code changes compile clean (`py_compile` on every modified file). Schema
changes already applied to the live `vynzrvgoyqorqxogjrgw` Supabase project.

---

## What was investigated

Live data check confirmed:

- **Issue 1 confirmed.** Feb 2024 = 0 invoices, Mar 2024 = 0. Jan = 33,
  Apr = 59. The `time_modified` pattern is interesting — Jan 2024
  invoices were last QB-modified by 2024-01-17, and April invoices were
  first modified on 2024-05-13 (back-entered). So either: (a) Feb-Mar
  2024 invoices truly don't exist in QB (slow Q1 wholesale plus catch-up
  entry in April-May), or (b) they exist but a sync window swallowed them
  during initial load. Cannot tell without asking QB directly.

- **Issue 2 (bills) is a workflow change, not a connector bug.** Bills
  declined cleanly from ~40/quarter in 2023 to ~0 by Q4 2024. Checks were
  always the dominant payment vehicle (1500–4200/quarter). Connector
  continues to query QB for bills successfully — QB just returns
  zero matching records.

- **Issue 3 root cause.** `qb_meta.sync_log` table existed but never
  received writes. State manager only updated `sync_state` (a "current
  state" view), so we had no audit trail to diagnose past staleness.

- **Bonus finding:** `accounts` entity for ADKFF currently shows status
  `error` with `0x80040408 Could not start QuickBooks` from the
  19:28:45 UTC run today. QB Desktop must be open on the Windows
  machine for QBWC to authenticate — make sure QB is running before
  the next scheduled cycle.

---

## What changed in the code

### New files
- `migrations/010_backfill_jobs.sql` — `qb_meta.backfill_jobs` queue table.
- `migrations/011_expenses_unified_view.sql` — five `expenses_unified`
  views, one per company schema.
- `src/sync/backfill.py` — `BackfillJobManager` (enqueue / claim / mark
  done / mark error).
- `docs/bills-workflow-question-yen-sandy.md` — drafted message for
  confirming the bills workflow.

### Modified files
- `src/qbxml/builders.py` — added `to_modified_date`, `from_txn_date`,
  `to_txn_date` to both `build_generic_query` and `build_invoice_query`.
  Date filters are still suppressed on iterator Continue (required by
  qbXML — adding a filter to a Continue throws QB error 3120). New
  `BACKFILL_AWARE` set tracks which specialized builders accept the full
  windowed-args signature; others degrade gracefully to from-only.
- `src/soap/session.py` — `SyncTask` got `to_date`, `txn_from_date`,
  `txn_to_date`, `backfill_job_id`, `log_id` fields plus an
  `is_backfill` property.
- `src/sync/coordinator.py` — claims pending backfill jobs at task-queue
  build time and inserts them at the front; routes done / error / no-data
  paths to `BackfillJobManager` for backfill tasks (so they don't
  corrupt the entity's normal incremental cursor); writes per-entity
  start / done / error rows to `qb_meta.sync_log`.
- `src/sync/state.py` — three new helpers: `log_run_started`,
  `log_run_done`, `log_run_error`.
- `src/main.py` — three new endpoints:
  - `POST /backfill/{company_id}/{entity_type}` with
    `{from_date, to_date, filter_type, requested_by, reason}` body
  - `GET /backfill/{company_id}` (list jobs, optional `?status=` filter)
  - `GET /backfill/job/{job_id}` (inspect one)
  - `/status` now flags `stale_entities` and `errored_entities` per company
- `src/soap/service.py` — passes the new `BackfillJobManager` into
  `SyncCoordinator`.
- `src/supabase/upsert.py` — warns at upsert time on any transaction
  dated more than 1 day in the future, with sample TxnIDs in the log.

### Already deployed to Supabase project `vynzrvgoyqorqxogjrgw`
- `qb_meta.backfill_jobs` table + indexes + RLS policy
- `<schema>.expenses_unified` views in all five company schemas

### Still to deploy (when you push code)
- Vercel deployment of the new endpoints + coordinator changes. The Vercel
  build picks up the repo; standard `git push` should ship it.
- No QBWC client-side changes needed — same `.qwc` files, same SOAP wire
  protocol. The connector adds a backfill task at the front of the queue
  the next time QBWC connects.

---

## How to actually fix Issue 1 (Feb-Mar 2024 invoices)

After deploying:

```bash
# Use TxnDate (not TimeModified) — we don't know when those invoices were
# modified, but we know what window they SHOULD have transaction dates in.
curl -X POST https://yc-qb-web-connector.vercel.app/backfill/adk_fragrance/invoices \
  -H 'Content-Type: application/json' \
  -d '{
    "from_date": "2024-01-01",
    "to_date":   "2024-04-30",
    "filter_type": "txn",
    "requested_by": "clark",
    "reason": "Q1 P&L analysis surfaced 0 invoices for Feb-Mar 2024"
  }'
```

On the next QBWC cycle (or trigger one manually via QB Web Connector's
"Update Selected"), the connector pulls invoices with transaction dates
in `[2024-01-01, 2024-04-30]` and upserts them. Then re-run the
verification query:

```sql
SELECT date_trunc('month', txn_date)::date AS m, COUNT(*) AS invoice_count
FROM adk_fragrance.invoices
WHERE txn_date >= '2024-01-01' AND txn_date < '2024-05-01'
GROUP BY 1 ORDER BY 1;
```

If Feb-Mar 2024 still show zero, the invoices truly don't exist in QB
for those months — slow wholesale period + late entry pattern. If they
appear, the original sync had a window gap (now fixed for future runs
because we always use a 5-min lookback buffer on incremental syncs, and
operators can trigger backfills for any past window).

## How to fix Issue 2 (bills)

1. Send the message in `docs/bills-workflow-question-yen-sandy.md` to
   Yen / Sandy.
2. While waiting: switch any OpEx analysis from `bill_lines` joins to
   `<schema>.expenses_unified`. Quick sanity check:

   ```sql
   SELECT source, COUNT(*), SUM(amount)::numeric(14,2)
   FROM adk_fragrance.expenses_unified
   WHERE txn_date >= '2025-01-01' AND txn_date < '2026-04-30'
   GROUP BY 1 ORDER BY 1;
   ```

3. If they confirm the workflow change, we're done — `expenses_unified`
   replaces the bills-only path permanently. If they say bills are still
   in use, run the same backfill mechanism on bills:

   ```bash
   curl -X POST https://yc-qb-web-connector.vercel.app/backfill/adk_fragrance/bills \
     -H 'Content-Type: application/json' \
     -d '{"from_date":"2024-07-01","to_date":"2026-04-30","filter_type":"txn",
          "reason":"Confirm bills still entered after mid-2024 cliff"}'
   ```

## How to fix Issue 3 (silent staleness)

Already fixed in code. After the next deploy, every QBWC cycle will write
one row to `qb_meta.sync_log` per entity. To check for silent failures:

```sql
SELECT company_id, entity_type, status, error_message,
       started_at, completed_at, records_synced
FROM qb_meta.sync_log
WHERE company_id = 'adk_fragrance'
  AND started_at >= now() - interval '7 days'
ORDER BY started_at DESC;
```

`/status` now also flags any entity not synced in the last 6 hours.

## How to fix Issue 4 (forward-dated invoice)

Already fixed in code. The next sync that touches a future-dated record
emits a `future_dated_transactions` warning with the txn_id and date.
Search structured logs for that event name.

## How to fix the bonus finding (accounts in error state)

Open QuickBooks Desktop on the Windows host before the next QBWC cycle.
The current error `0x80040408 Could not start QuickBooks` means QBWC
launched successfully but QB itself wasn't running. If this keeps
happening, schedule QB to auto-launch at sync time (or before).

---

## Files referenced

- Error report (input): `uploads/YC_QB_Connector_Error_Report.md`
- Migrations:
  - [010_backfill_jobs.sql](computer://C:\git\Clark\yc-qb-web-connector\migrations\010_backfill_jobs.sql)
  - [011_expenses_unified_view.sql](computer://C:\git\Clark\yc-qb-web-connector\migrations\011_expenses_unified_view.sql)
- New code: [src/sync/backfill.py](computer://C:\git\Clark\yc-qb-web-connector\src\sync\backfill.py)
- Yen/Sandy message: [docs/bills-workflow-question-yen-sandy.md](computer://C:\git\Clark\yc-qb-web-connector\docs\bills-workflow-question-yen-sandy.md)
