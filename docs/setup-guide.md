# Setup Guide

Step-by-step guide to deploying the YC QuickBooks Web Connector integration.

## Prerequisites

### On the Windows Machine (where QuickBooks runs)
- QuickBooks Desktop (Pro, Premier, or Enterprise) — 2013 or later recommended
- QuickBooks Web Connector 2.2.0.34 or later
  - Download from: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started/get-started-with-quickbooks-web-connector
- The QB company file must be open when syncing

### On the Linux Server (where this service runs)
- Docker 24+
- Docker Compose 2+
- A domain name pointing to the server (for SSL)
- Port 443 open in firewall

### Supabase
- A Supabase project (create at supabase.com)
- Service role key (from Settings → API)

---

## Part 1: Server Setup

### 1.1 Clone the Repository
```bash
git clone https://github.com/DataHippo93/yc-qb-web-connector.git
cd yc-qb-web-connector
```

### 1.2 Configure Environment
```bash
cp .env.example .env
nano .env
```

Fill in:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-role-key
SECRET_KEY=generate-a-random-32-char-string

# Credentials for QBWC connections (one per company)
# These are the username/password QBWC will send to authenticate()
QBWC_USER_NS=ns_sync
QBWC_PASS_NS=your-secure-password-here

QBWC_USER_ADF=adf_sync
QBWC_PASS_ADF=your-secure-password-here
```

### 1.3 Apply Database Migrations

Option A: Supabase Dashboard
1. Open Supabase → SQL Editor
2. Paste and run `migrations/001_initial_schema.sql`

Option B: psql
```bash
psql "$SUPABASE_DB_URL" < migrations/001_initial_schema.sql
```

### 1.4 Configure SSL with Caddy (Recommended)

Caddy handles HTTPS automatically with Let's Encrypt.

```bash
# Caddyfile already included in docker-compose.yml
# Just make sure your domain points to this server's IP
```

Edit `docker-compose.yml` and set your domain:
```yaml
environment:
  - DOMAIN=qb.yourdomain.com
```

### 1.5 Start the Service
```bash
docker compose up -d
docker compose logs -f  # watch logs
```

Verify it's up:
```bash
curl https://qb.yourdomain.com/health
# Should return: {"status": "ok", "version": "1.0.0"}
```

Verify WSDL is accessible:
```bash
curl https://qb.yourdomain.com/soap?wsdl
# Should return XML WSDL document
```

---

## Part 2: Generate .qwc Files

On the Linux server (or locally):

```bash
# Nature's Storehouse
python scripts/generate_qwc.py \
  --company natures-storehouse \
  --url https://qb.yourdomain.com/soap \
  --output natures-storehouse.qwc

# ADK Fragrance Farm
python scripts/generate_qwc.py \
  --company adk-fragrance-farm \
  --url https://qb.yourdomain.com/soap \
  --output adk-fragrance-farm.qwc
```

This creates `.qwc` files like:
```xml
<?xml version="1.0"?>
<QBWCXML>
  <AppName>YC Sync - Nature's Storehouse</AppName>
  <AppID></AppID>
  <AppURL>https://qb.yourdomain.com/soap</AppURL>
  <AppDescription>Syncs QuickBooks data to Supabase</AppDescription>
  <AppSupport>https://qb.yourdomain.com/health</AppSupport>
  <UserName>ns_sync</UserName>
  <OwnerID>{generated-guid}</OwnerID>
  <FileID>{generated-guid}</FileID>
  <QBType>QBFS</QBType>
  <Scheduler>
    <RunEveryNMinutes>15</RunEveryNMinutes>
  </Scheduler>
  <IsReadOnly>true</IsReadOnly>
</QBWCXML>
```

Copy the `.qwc` file(s) to the Windows machine (email, USB, shared drive).

---

## Part 3: Configure QuickBooks Web Connector

### 3.1 Install QBWC
1. Download from Intuit developer portal
2. Run installer as Administrator
3. Accept all defaults

### 3.2 Open QuickBooks Desktop
1. Open the company file you want to sync
2. You must be logged in as an Admin user
3. Keep QuickBooks open

### 3.3 Add the .qwc File
1. Open **QuickBooks Web Connector** (Start menu → QuickBooks → Web Connector)
2. Click **File → Add an Application**
3. Navigate to and select `natures-storehouse.qwc`
4. QuickBooks will ask to grant access — click **Yes, Always**
5. A dialog will ask you to set a password — enter the password you configured in `.env` for `QBWC_PASS_NS`
6. The application appears in the QBWC list

### 3.4 Verify Connection
1. In QBWC, check the checkbox next to the new application
2. Click **Update Selected**
3. Watch the progress bar — it should complete and show "Last Status: OK"

If you see an error:
- `QBWC1012: Authentication failed` → check username/password match `.env`
- `QBWC1048: Cannot verify certificate` → SSL issue, check your cert is valid
- `QBWC1042: ReceiveResponseXML failed` → check service logs: `docker compose logs`

### 3.5 Repeat for Second Company
Repeat steps 3.2–3.4 for the ADK Fragrance Farm company file using `adk-fragrance-farm.qwc`.

---

## Part 4: First Full Sync

The first sync will pull ALL data from QuickBooks. This can take 10–60 minutes.

### Watch Progress

On the Windows machine, QBWC shows a progress bar for the current session.

On the server:
```bash
docker compose logs -f | grep -E "SYNC|INFO|ERROR"
```

Check Supabase:
```sql
SELECT entity_type, records_synced, status, last_synced_at
FROM qb.sync_state
WHERE company_id = 'natures-storehouse'
ORDER BY entity_type;
```

### What to Expect
- Phase 1 (reference data): 5–15 minutes
- Phase 2 (transactions): 10–45 minutes depending on transaction history
- Phase 3 (metadata): < 1 minute

### After First Sync
- Subsequent runs will only pull changed records (incremental)
- Typical sync time after first: 30 seconds to 5 minutes

---

## Part 5: Automating QBWC

QBWC can run automatically on a schedule, but the Windows user must be logged in.

### Option A: Auto-start with Windows
1. Open Task Scheduler
2. Create a task that runs QBWC at startup
3. Configure to run whether user is logged in or not (requires storing credentials)

### Option B: Dedicated Sync Machine
For reliable 24/7 syncing:
1. Use a dedicated Windows VM/machine running QB
2. Set Windows to auto-login
3. Set QBWC to start with Windows
4. Keep QuickBooks open to the company file (no screensaver lock)

### Option C: Manual Sync
For infrequent needs:
1. Open QBWC manually
2. Check checkbox next to desired company
3. Click "Update Selected"

---

## Part 6: Monitoring & Alerts

### Health Check Endpoint
```
GET https://qb.yourdomain.com/health
```

Set up uptime monitoring (UptimeRobot, Better Uptime, etc.) on this endpoint.

### Sync Status API
```
GET https://qb.yourdomain.com/api/sync-status
```

Returns JSON with last sync time per company per entity.

### Force Full Re-sync
If data looks stale or you restored a QB backup:
```bash
curl -X POST https://qb.yourdomain.com/api/force-full-sync \
  -H "Authorization: Bearer $SECRET_KEY" \
  -d '{"company_id": "natures-storehouse"}'
```

---

## Troubleshooting

### "QBWC1048: Cannot verify certificate"
- Your SSL cert is invalid or self-signed
- Use Let's Encrypt (Caddy handles this automatically)
- Make sure your domain resolves correctly

### "QBWC1012: Authentication failed"
- Username/password mismatch between `.qwc` file and `.env`
- Check `QBWC_USER_NS` / `QBWC_PASS_NS` in `.env`

### "QBWC1042: ReceiveResponseXML failed"
- Usually a timeout or network issue
- Check server logs: `docker compose logs app`
- Check if service is running: `docker compose ps`

### Sync stopped mid-way
- Iterator expired (QB was closed)
- On next QBWC poll, the sync will restart for the interrupted entity
- No data loss — we track per-entity progress

### QuickBooks prompts for access every time
- Reinstall QBWC and re-add the `.qwc` file
- Make sure to run QBWC as the same Windows user as QuickBooks

### Data not appearing in Supabase
- Check `qb.sync_state` table for error status
- Check service logs for upsert errors
- Verify `SUPABASE_SERVICE_KEY` has full access to `qb` schema

---

## Development Setup

For local development without a public domain:

### Option A: Cloudflare Tunnel (Recommended)
```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared

# Create tunnel
./cloudflared tunnel login
./cloudflared tunnel create qb-sync
./cloudflared tunnel route dns qb-sync qb-dev.yourdomain.com
./cloudflared tunnel run --url http://localhost:8080 qb-sync
```

### Option B: ngrok
```bash
ngrok http 8080
# Use the https URL in your .qwc file
# Note: URL changes on each restart
```

### Running Locally
```bash
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8080
```

Generate a dev `.qwc` with your tunnel URL:
```bash
python scripts/generate_qwc.py \
  --company natures-storehouse \
  --url https://your-tunnel-url/soap \
  --output dev-natures.qwc
```
