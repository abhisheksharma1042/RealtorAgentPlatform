#!/usr/bin/env python3
"""Apply a SQL migration file against Supabase via direct Postgres.

Usage:
    python -m backend.migrations.apply 003_ingestion_schema.sql

Requires DATABASE_URL in the environment (or in backend/.env). Grab this
from Supabase dashboard -> Project Settings -> Database -> Connection string
(URI). It looks like:

    postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres

Or the pooler URI:

    postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv


async def apply(sql_path: Path) -> None:
    load_dotenv(Path(__file__).parent.parent / ".env")
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set. Add to backend/.env.", file=sys.stderr)
        sys.exit(2)
    sql = sql_path.read_text()
    print(f"Applying {sql_path.name} ({len(sql)} chars)...")
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(sql)
        print("OK.")
    finally:
        await conn.close()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python -m backend.migrations.apply <migration.sql>", file=sys.stderr)
        sys.exit(2)
    sql_path = Path(__file__).parent / sys.argv[1]
    if not sql_path.exists():
        print(f"ERROR: {sql_path} does not exist", file=sys.stderr)
        sys.exit(2)
    asyncio.run(apply(sql_path))


if __name__ == "__main__":
    main()
