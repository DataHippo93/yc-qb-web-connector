#!/usr/bin/env python3
"""
Bootstrap script — applies Supabase migrations for all companies.

Usage:
    python scripts/bootstrap_schemas.py [--dry-run]

What it does:
  1. Runs migrations/001_qb_meta.sql (creates qb_meta schema + tables)
  2. For each company in companies.yaml, runs 002_company_schema_template.sql
     with :schema substituted to the company's pg_schema

Requires:
    pip install psycopg2-binary pyyaml python-dotenv
    QB_SUPABASE_DB_PASS and QB_SUPABASE_URL in .env or environment
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import psycopg2
    from psycopg2 import sql
    from dotenv import load_dotenv
    import yaml
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install psycopg2-binary python-dotenv pyyaml")
    sys.exit(1)

load_dotenv()

# ============================================================================
# Configuration
# ============================================================================

PROJECT_ROOT = Path(__file__).parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
CONFIG_FILE = PROJECT_ROOT / "config" / "companies.yaml"


def get_db_url() -> str:
    """Build PostgreSQL connection URL from environment."""
    supabase_url = os.environ.get("QB_SUPABASE_URL", "")
    db_pass = os.environ.get("QB_SUPABASE_DB_PASS", "")

    if not supabase_url or not db_pass:
        print("ERROR: QB_SUPABASE_URL and QB_SUPABASE_DB_PASS must be set")
        sys.exit(1)

    # Extract project ref from URL: https://<ref>.supabase.co
    match = re.match(r"https://([^.]+)\.supabase\.co", supabase_url)
    if not match:
        print(f"ERROR: Cannot parse project ref from {supabase_url}")
        sys.exit(1)

    project_ref = match.group(1)
    # Supabase Transaction Pooler (port 6543) or direct (port 5432)
    host = f"db.{project_ref}.supabase.co"
    return f"postgresql://postgres:{db_pass}@{host}:5432/postgres"


def load_companies() -> dict:
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)["companies"]


# ============================================================================
# Migration execution
# ============================================================================

def apply_sql(conn, sql_text: str, description: str, dry_run: bool = False) -> None:
    """Execute a SQL statement block."""
    if dry_run:
        print(f"  [DRY RUN] Would apply: {description}")
        return

    with conn.cursor() as cur:
        cur.execute(sql_text)
    conn.commit()
    print(f"  ✓ Applied: {description}")


def apply_migration_001(conn, dry_run: bool) -> None:
    """Apply qb_meta schema migration."""
    print("\n=== Migration 001: qb_meta schema ===")
    sql_text = (MIGRATIONS_DIR / "001_qb_meta.sql").read_text()
    apply_sql(conn, sql_text, "001_qb_meta.sql", dry_run)


def apply_migration_002_for_schema(conn, pg_schema: str, dry_run: bool) -> None:
    """Apply company schema template for one schema, substituting :schema."""
    print(f"\n=== Migration 002: schema '{pg_schema}' ===")

    template = (MIGRATIONS_DIR / "002_company_schema_template.sql").read_text()

    # Create schema first
    create_schema_sql = f"CREATE SCHEMA IF NOT EXISTS {pg_schema};"
    apply_sql(conn, create_schema_sql, f"CREATE SCHEMA {pg_schema}", dry_run)

    # Substitute :schema variable — both quoted and unquoted forms
    # psql uses :schema as a variable, but we run Python directly
    # Replace :schema with literal schema name, handle quoted form :'schema' too
    populated = template.replace(":'schema'", f"'{pg_schema}'")
    populated = populated.replace(":schema", pg_schema)

    # Remove the psql SET variable comment line (not valid SQL)
    populated = re.sub(r"--.*?\\set.*?\n", "", populated, flags=re.IGNORECASE)

    # The DO $$ block for RLS uses :'schema' — already substituted above
    apply_sql(conn, populated, f"002_company_schema_template.sql [{pg_schema}]", dry_run)


def check_connection(conn) -> None:
    """Quick connectivity check."""
    with conn.cursor() as cur:
        cur.execute("SELECT version(), current_database()")
        version, dbname = cur.fetchone()
    print(f"Connected to: {dbname}")
    print(f"PostgreSQL: {version[:50]}...")


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Bootstrap QB Supabase schemas")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    parser.add_argument("--skip-meta", action="store_true", help="Skip migration 001 (qb_meta)")
    parser.add_argument("--schema", help="Apply 002 for one specific schema only")
    args = parser.parse_args()

    db_url = get_db_url()
    companies = load_companies()

    print(f"Connecting to Supabase...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
    except Exception as e:
        print(f"ERROR: Cannot connect: {e}")
        print("\nTroubleshooting:")
        print("  1. Verify QB_SUPABASE_DB_PASS is correct")
        print("  2. Check Supabase dashboard → Settings → Database → Connection string")
        print("  3. Ensure your IP is in Supabase allow-list (or use Transaction Pooler port 6543)")
        sys.exit(1)

    check_connection(conn)

    # Migration 001
    if not args.skip_meta:
        apply_migration_001(conn, args.dry_run)

    # Migration 002 — per company
    if args.schema:
        apply_migration_002_for_schema(conn, args.schema, args.dry_run)
    else:
        for company_id, cfg in companies.items():
            pg_schema = cfg["pg_schema"]
            apply_migration_002_for_schema(conn, pg_schema, args.dry_run)

    conn.close()
    print("\n✓ Bootstrap complete.")
    if args.dry_run:
        print("  (Dry run — no changes made)")


if __name__ == "__main__":
    main()
