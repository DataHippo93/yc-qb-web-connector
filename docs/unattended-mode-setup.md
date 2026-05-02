# Running QB Sync With No QuickBooks File Open

## What "unattended mode" actually buys you

Yes — the connector can run when no QB company file is open and nobody is
logged into QuickBooks. It can even open the right file, sync, and close
QB again, all by itself. This requires three things to line up:

1. **Each `.qwc` file declares unattended mode** (already done — see
   `<UnattendedModePref>umpRequired</UnattendedModePref>` in the .qwc
   files in `accounting/`).
2. **Each QB company file has been told "this app may log in automatically"**
   for the corresponding QB user.
3. **The Windows host is on**, with QB Desktop installed, QBWC installed
   and running, and a Windows session with file access available.

The Windows host requirement isn't optional — QB Desktop is a desktop app
that talks to QBWC over COM. There's no cloud-side equivalent for QB
Desktop sync. But QB itself does NOT need to be open or have a file
loaded; QBWC opens the right file on demand.

---

## What "the QB file is not open" actually means in QB-land

QuickBooks Desktop can only have ONE company file open at a time per QB
process (without enabling Multi-User hosting). With unattended mode,
QBWC opens the right file just-in-time:

- **Connector for ADK fires:** QBWC tells QB Desktop "open the ADK
  Fragrance Farm file in unattended mode, run my queries, close it."
- **Connector for YC Works fires next:** QBWC tells QB "now open YC
  Works LLC, run those queries, close it."
- Between cycles, QB can be entirely closed.

This eliminates the cross-schema contamination problem at the source:
QBWC binds each .qwc app to a specific QB company file at the moment
the app is added. When the schedule fires, QBWC opens THAT file, not
whatever the user happened to have open.

---

## One-time setup (per company file)

Do this on the Windows host, once per QB company file the connector
should be allowed to read.

### Step 1 — make sure each .qwc app has been added to QBWC

Open QuickBooks Web Connector. For each company you want to sync, click
"Add an Application" and select the matching `.qwc` file from
`accounting/`:

| Connector app           | .qwc file                              | QB company to bind |
|-------------------------|----------------------------------------|-------------------|
| YC QB Connector - ADK   | `accounting/adk_fragrance.qwc`         | Sandy Maine Inc / Adirondack Fragrance Farm |
| YC QB Connector - YCC   | `accounting/yc_consulting.qwc`         | YC Consulting |
| YC QB Connector - MM    | `accounting/maine_and_maine.qwc`       | Maine & Maine, LLC |
| YC QB Connector - NS    | (regenerate via `scripts/generate_qwc.py`) | Nature's Storehouse |
| YC QB Connector - YCW   | (regenerate via `scripts/generate_qwc.py`) | YC Works LLC |

**CRITICAL: open the correct QB company file BEFORE adding each .qwc app.**
QBWC binds the application to whichever file is open at "Add Application"
time. If you add `adk_fragrance.qwc` while YC Works is the open file,
QBWC will bind ADK's app to the YC Works file — exactly the bug we're
fixing.

If you have any old bindings that were set up while the wrong file was
open, **remove the app from QBWC** (Remove button), open the correct QB
file, and re-add the .qwc.

### Step 2 — enable unattended login for each QB user

In each QB company file:

1. Sign in as Admin in QB Desktop.
2. **Edit > Preferences > Integrated Applications > Company Preferences.**
3. Find "YC QB Connector - ADK" (or the app name for this file) in the
   list and click **Properties**.
4. Check **"Allow this application to login automatically"**.
5. From the dropdown, pick the QB user that should "own" this auto-login.
   Recommended: create a dedicated QB user named `ConnectorService` with
   read-only-ish permissions and use it for all auto-login. Don't use
   Admin if you can avoid it.
6. Click **OK** through the warning dialogs.
7. Repeat for each QB company file.

### Step 3 — make sure Windows can run QBWC unattended

QBWC is a Windows app, not a service. It needs a Windows session. Two
options:

- **Auto-login Windows user.** A dedicated Windows account (e.g.
  `qbsync`) configured to auto-login on boot. Add QBWC to that user's
  Startup folder so it launches with Windows. The host can be left
  logged in indefinitely.
- **Task Scheduler with "Run whether user is logged on or not".**
  Schedule QBWC to start on boot. Note: this requires storing the
  Windows account password in Task Scheduler's credential store.

Either way: **the host machine has to stay powered on** (or wake on
schedule). QBWC running as a true Windows Service is not supported by
Intuit.

### Step 4 — test the end-to-end loop

1. Close QuickBooks Desktop entirely.
2. Confirm no `.QBW` file is open.
3. Wait for QBWC's next scheduled run (or click "Update Selected").
4. Watch QBWC: it should briefly start QB, sync, and stop.
5. In Supabase, run:
   ```sql
   SELECT entity_type, last_synced_at, records_synced, error_message
   FROM qb_meta.sync_state
   WHERE company_id = 'adk_fragrance'
   ORDER BY last_synced_at DESC LIMIT 5;
   ```
6. Confirm records were synced AND no `error_message` shows
   `0x80040408 Could not start QuickBooks`.
7. After a successful run, check the identity guard:
   ```
   GET /identity
   ```
   The `observed_company_name` for `adk_fragrance` should be the actual
   ADKFF company name as displayed in QB. If it is, lock it in:
   ```
   POST /identity/adk_fragrance/lock-in
   ```

---

## Why this is now safer than before

Even with unattended mode correctly set up, there are still ways for the
binding to drift (e.g. a QB file rename, a tech accidentally re-binding
during a manual fix, or the QBWC database getting corrupted). The
identity-check guard added earlier catches those:

- Every session starts with a `CompanyQueryRq` to QB.
- The returned `<CompanyName>` is compared against the locked-in expected
  name.
- On mismatch, the session is aborted **before** any data is upserted,
  and the mismatch is recorded in `qb_meta.company_identity_log`.

Unattended mode eliminates the "wrong file was open" path. The identity
guard catches everything else. Together they're defense in depth.

---

## What unattended mode does NOT solve

- **Network outage between Windows host and Supabase.** The connector
  will fail and retry on the next QBWC cycle; the existing sync_state /
  sync_log machinery handles this.
- **QB Desktop license issues.** Unattended login still requires a
  valid QB license seat for the user that's logging in.
- **QB upgrades.** A pending QB Desktop update can require interactive
  acceptance and will block automation until handled.
- **Cloud-only setups.** If Clark wants to eventually retire the
  Windows host, the path forward is QuickBooks Online — different API,
  different connector. Out of scope for this remediation.

---

## Quick reference: regenerating .qwc files

If you need to regenerate the .qwc files (e.g. you change the host URL
or add a new company), run:

```bash
python scripts/generate_qwc.py --host https://yc-qb-web-connector.vercel.app --out-dir accounting/
```

The generator now emits `<UnattendedModePref>umpRequired</UnattendedModePref>`
by default. Drop the new files on the Windows host, remove the old
QBWC entries, and re-add — making sure the correct QB company file is
open during each "Add Application" step.
