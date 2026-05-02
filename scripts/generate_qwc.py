#!/usr/bin/env python3
"""
Generate .qwc files for each company.

QB Web Connector uses these XML files to know:
  - What server URL to connect to
  - What username/password to use
  - How often to sync
  - Which QB company file to open (or empty = currently open file)

Usage:
    python scripts/generate_qwc.py [--host https://your-server.com] [--out-dir .]

Drop the generated .qwc files on the Windows machine running QBWC.
QB Enterprise should already be running.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import yaml

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "companies.yaml"


QWC_TEMPLATE = """\
<?xml version="1.0"?>
<QBWCXML>
  <AppName>{app_name}</AppName>
  <AppID></AppID>
  <AppURL>{app_url}</AppURL>
  <AppDescription>{description}</AppDescription>
  <AppSupport>{support_url}</AppSupport>
  <UserName>{username}</UserName>
  <OwnerID>{{{owner_id}}}</OwnerID>
  <FileID>{{{file_id}}}</FileID>
  <QBType>QBFS</QBType>
  <Style>Document</Style>
  <Scheduler>
    <RunEveryNMinutes>{interval}</RunEveryNMinutes>
  </Scheduler>
  <IsReadOnly>false</IsReadOnly>
  <Notify>false</Notify>
  <!-- Unattended mode: QBWC opens the bound company file in the background,
       runs the sync, and closes QB if QBWC started it. The QB user that owns
       this app must have "Allow this application to login automatically"
       enabled per company file (Edit > Preferences > Integrated Applications).
       umpRequired = the app refuses to run interactively. -->
  <UnattendedModePref>umpRequired</UnattendedModePref>
  <!-- pdpNotNeeded = the app does not need access to personal data
       (SSN, full credit card numbers). The QB dialog's "Allow this
       application to access personal data" checkbox should be left UNCHECKED. -->
  <PersonalDataPref>pdpNotNeeded</PersonalDataPref>
</QBWCXML>
"""

# Per-company usernames — MUST match QBWC_USERNAME variants in .env / companies.yaml
# Convention: use distinct usernames so the server can route to the right company
COMPANY_USERNAMES = {
    "natures_storehouse": "YCConnector_NS",
    "adk_fragrance":      "YCConnector_ADK",
}


def generate_qwc(company_id: str, cfg: dict, host: str, out_dir: Path) -> None:
    username = COMPANY_USERNAMES.get(company_id, f"YCConnector_{company_id[:6].upper()}")
    interval = cfg.get("sync_interval_minutes", 60)
    app_name = cfg.get("qwc_app_name", f"YC QB Connector - {cfg.get('display_name', company_id)}")
    app_url = f"{host.rstrip('/')}/qbwc/"
    support_url = f"{host.rstrip('/')}/"

    content = QWC_TEMPLATE.format(
        app_name=app_name,
        app_url=app_url,
        description=f"Syncs {cfg.get('display_name', company_id)} QuickBooks data to Supabase",
        support_url=support_url,
        username=username,
        owner_id=str(uuid.uuid4()).upper(),
        file_id=str(uuid.uuid4()).upper(),
        interval=interval,
    )

    out_file = out_dir / f"{company_id}.qwc"
    out_file.write_text(content)
    print(f"Generated: {out_file}")
    print(f"  Username: {username}")
    print(f"  URL:      {app_url}")
    print(f"  Interval: every {interval} minutes")
    print()
    print(f"  NOTE: Set QBWC password for user '{username}' to match QBWC_PASSWORD in .env")
    print()


def main():
    parser = argparse.ArgumentParser(description="Generate QBWC .qwc files")
    parser.add_argument(
        "--host",
        default="https://your-server.example.com",
        help="Base URL of the connector server (e.g. https://qb.yourdomain.com)",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        help="Output directory for .qwc files (default: current dir)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE) as f:
        companies = yaml.safe_load(f)["companies"]

    print(f"Generating .qwc files for {len(companies)} companies...")
    print(f"Host: {args.host}\n")

    for company_id, cfg in companies.items():
        generate_qwc(company_id, cfg, args.host, out_dir)

    print("Done. Next steps:")
    print("  1. Copy .qwc files to the Windows machine running QB Enterprise + QBWC")
    print("  2. Open QBWC → Add Application → browse to the .qwc file")
    print("  3. Set the password (must match QBWC_PASSWORD in connector .env)")
    print("  4. Click Update Selected in QBWC to trigger first sync")


if __name__ == "__main__":
    main()
