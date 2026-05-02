# Deploy commands — run these from your Windows shell

**Repo root:** `C:\git\Clark\yc-qb-web-connector`

All file changes are already on disk and verified compiling. The 7 new
endpoints (`/identity/*`, `/backfill/*`) are wired up. Schemas already live
in Supabase. This is just the commit + push step.

## Step 1 — sanity check

```bash
git status --short
```

You should see ~10 modified files plus several new (`??`) files. Among the
modified files, some show as changed because of CRLF/LF line-ending
differences only (no real code change). Don't worry — we'll only stage
the files with real changes.

## Step 2 — stage exactly the files you want to commit

```bash
# Real Python changes (deploy-critical)
git add src/main.py
git add src/qbxml/builders.py
git add src/qbxml/parsers.py
git add src/soap/service.py
git add src/soap/session.py
git add src/supabase/upsert.py
git add src/sync/coordinator.py
git add src/sync/state.py
git add src/utils/config.py

# Unattended-mode flag in the .qwc generator template
git add scripts/generate_qwc.py

# New modules
git add src/sync/backfill.py
git add src/sync/identity.py

# Migrations (already applied to Supabase, but commit for record)
git add migrations/010_backfill_jobs.sql
git add migrations/011_expenses_unified_view.sql
git add migrations/012_company_identity_check.sql

# Documentation
git add docs/REMEDIATION_2026-04-30.md
git add docs/bills-workflow-question-yen-sandy.md
git add docs/unattended-mode-setup.md
git add docs/DEPLOY_COMMANDS.md
```

Files I'm intentionally NOT staging (you can decide later if they need
their own commit):

- `migrations/008_*.sql`, `migrations/009_*.sql`, `tests/test_build_assembly_del.py`,
  `tests/test_cascade_deps.py`, `src/qbxml/entities.py`, `config/companies.yaml` —
  CRLF line-ending churn only, no real code change
- `.claude/`, `.fix-cascade-deps.py`, `.open-pr.py`, `.pr-body.md`, `image.png`,
  `src/main.py.test` — local dev artifacts
- `node_modules/`, `package.json`, `package-lock.json`, `scripts/dedup_report.*`,
  `reports/`, `supabase/`, `uv.lock` — separate work (the dedup report stuff)

## Step 3 — verify the staged set looks right

```bash
git diff --cached --stat
```

Expected: ~12 modified/new src files, 3 migrations, 4 docs. ~700+ insertions.

## Step 4 — commit

```bash
git commit -m "feat(connector): identity guard + windowed backfill + sync log + future-date warning

- Adds CompanyQueryRq probe at the start of every QBWC session. Compares
  observed <CompanyName> against expected_company_name (qb_meta.companies);
  on mismatch, aborts the session before any data is upserted. Defends
  against the cross-schema contamination scenario where QBWC fires the
  ADK connector while the YC Works file happens to be open.

- Adds qb_meta.backfill_jobs and POST /backfill/{company}/{entity} for
  date-windowed re-syncs (uses TxnDateRangeFilter or ModifiedDateRangeFilter).
  Replaces the all-or-nothing 'reset' workflow for repairing data gaps
  like the Feb-Mar 2024 invoice blackout.

- Wires writes to qb_meta.sync_log on every entity start/done/error. Was
  silently empty before (0 rows) — fixes audit blind spot for stale entities.

- Builds <schema>.expenses_unified view across bills+checks+credit cards+
  vendor credits+JE expense lines so OpEx analysis has one source of truth
  even when bills aren't actively used.

- Adds future-dated transaction warning in upsert path (>1 day grace).

- Adds unattended-mode flags to .qwc generator template (UnattendedModePref,
  PersonalDataPref).

- Three new endpoints to manage the identity guard: GET /identity (status
  per company), GET /identity/log (audit history), POST /identity/{cid}/lock-in
  (promote observed -> expected), POST /identity/{cid}/clear (revert).

Schemas (010_backfill_jobs, 011_expenses_unified_view, 012_company_identity_check)
already applied to live Supabase project vynzrvgoyqorqxogjrgw."
```

## Step 5 — push (this triggers the Vercel deploy)

```bash
git push origin main
```

If your terminal asks for GitHub credentials, that's normal — provide
them. After the push, watch Vercel for the build. It usually takes 1–2
minutes.

## Step 6 — post-deploy verification

```bash
# Health
curl https://yc-qb-web-connector.vercel.app/health

# All routes should now register — these will return JSON, not 404
curl https://yc-qb-web-connector.vercel.app/identity
curl https://yc-qb-web-connector.vercel.app/backfill/adk_fragrance
```

After the next QBWC scheduled cycle (or click Update Selected in QBWC),
hit `GET /identity` again. The `observed_company_name` field should be
populated for each company that ran a session. If `adk_fragrance.observed_company_name`
matches "Sandy Maine Inc" or whatever ADKFF actually reports, lock it in:

```bash
curl -X POST https://yc-qb-web-connector.vercel.app/identity/adk_fragrance/lock-in
```

If it instead says "YC Works LLC" — that's the smoking gun: the ADK
connector has been syncing the YC Works file all along. Do **not** lock-in.
Stop QBWC, fix the binding (remove the .qwc app from QBWC, open the
correct QB file, re-add the .qwc), then truncate `adk_fragrance` and let
the next sync rebuild it.

---

## What's left for you to do manually (one-time per company)

1. **In QB**, repeat the Properties dialog you already did for ADK on each
   of the other 4 companies (YC Works, YC Consulting, Maine & Maine,
   Nature's Storehouse): Edit > Preferences > Integrated Applications >
   Company Preferences > select the connector app > Properties. Check
   "Allow access even when QuickBooks isn't running" and leave personal
   data unchecked.

2. **In QBWC**, optionally remove + re-add each .qwc file so the new
   `<UnattendedModePref>` and `<PersonalDataPref>` flags take effect.
   This is only required if you want the regenerated flags applied —
   the existing bindings still work.

3. **After one successful sync per company**, call `/identity/{cid}/lock-in`
   for each. That arms the safeguard.
