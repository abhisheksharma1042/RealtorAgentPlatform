"""US Census batch geocoder - backfill county_parcels.location.

Free, no API key. Accepts up to 10,000 addresses per POST. Uses TIGER/Line.
Endpoint: https://geocoding.geo.census.gov/geocoder/locations/addressbatch
Response is a CSV per-row with match status and lon,lat coordinates.
"""
import asyncio
import csv
import io
import os
from typing import Any, Iterable, Optional

import asyncpg
import httpx


BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
BATCH_SIZE = 5_000   # Census max is 10K but 10K often times out; 5K completes reliably
MAX_RETRIES = 2


class CensusGeocoder:
    """Batch geocoder against the US Census bureau's public endpoint."""

    def __init__(self, benchmark: str = "Public_AR_Current"):
        self.benchmark = benchmark

    async def geocode_batch(
        self,
        rows: list[tuple[str, str, str, str, str]],
    ) -> dict[str, tuple[float, float]]:
        """Geocode a batch of ``(unique_id, street, city, state, zip)`` tuples.

        Returns a dict of ``unique_id -> (lon, lat)`` for matched rows. Unmatched
        rows are absent from the result.
        """
        if not rows:
            return {}
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        for r in rows:
            writer.writerow(r)
        csv_bytes = buf.getvalue().encode()

        files = {"addressFile": ("addresses.csv", csv_bytes, "text/csv")}
        data = {"benchmark": self.benchmark}

        last_err: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                async with httpx.AsyncClient(timeout=1200) as client:
                    resp = await client.post(BATCH_URL, files=files, data=data)
                    resp.raise_for_status()
                    return _parse_batch_response(resp.text)
            except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ReadError) as exc:
                last_err = exc
                if attempt <= MAX_RETRIES:
                    await asyncio.sleep(2 ** attempt)  # 2s, 4s
                    continue
                raise
        raise last_err if last_err else RuntimeError("unreachable")


def _parse_batch_response(body: str) -> dict[str, tuple[float, float]]:
    """Parse the Census batch geocoder response CSV.

    Columns (no header): id, input_address, match_status, tie, matched_address,
    coordinates ('lon,lat'), tigerline_id, tigerline_side.
    """
    out: dict[str, tuple[float, float]] = {}
    reader = csv.reader(io.StringIO(body))
    for row in reader:
        if len(row) < 6:
            continue
        uid, _input, match, _tie, _matched, coords = row[:6]
        if match != "Match":
            continue
        if not coords or "," not in coords:
            continue
        try:
            lon, lat = (float(x) for x in coords.split(","))
        except ValueError:
            continue
        out[uid] = (lon, lat)
    return out


async def backfill_county_parcels(
    zips: Optional[list[str]] = None,
    only_missing: bool = True,
    limit: Optional[int] = None,
    verbose: bool = True,
) -> tuple[int, int]:
    """Backfill ``county_parcels.location`` via the Census geocoder.

    Returns ``(matched_count, requested_count)``.
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    where_clauses = ["county = 'dallas'", "situs_address IS NOT NULL", "situs_address <> ''"]
    if only_missing:
        where_clauses.append("location IS NULL")
    if zips:
        where_clauses.append(f"situs_zip = ANY(${{Z}})")
    where = " AND ".join(where_clauses).replace("${Z}", "$1")

    sql = f"SELECT account_num, situs_address, city, situs_zip FROM county_parcels WHERE {where}"
    if limit:
        sql += f" LIMIT {int(limit)}"

    conn = await asyncpg.connect(db_url)
    try:
        params: list[Any] = [zips] if zips else []
        rows = await conn.fetch(sql, *params)
        if verbose:
            print(f"To geocode: {len(rows)} parcels")

        geocoder = CensusGeocoder()
        total_matched = 0
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]
            payload = [
                (
                    r["account_num"],
                    (r["situs_address"] or "").strip(),
                    (r["city"] or "").strip(),
                    "TX",
                    (r["situs_zip"] or "").strip(),
                )
                for r in batch
            ]
            if verbose:
                print(f"  batch {start // BATCH_SIZE + 1}: sending {len(payload)} addresses...")
            matches = await geocoder.geocode_batch(payload)
            total_matched += len(matches)
            if verbose:
                print(f"    matched {len(matches)}/{len(payload)}")
            if matches:
                await _write_batch_locations(conn, matches)
        return total_matched, len(rows)
    finally:
        await conn.close()


async def _write_batch_locations(
    conn: asyncpg.Connection,
    matches: dict[str, tuple[float, float]],
) -> None:
    """UPDATE county_parcels.location via PostGIS ST_SetSRID(ST_MakePoint(...))."""
    sql = (
        "UPDATE county_parcels "
        "SET location = ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography "
        "WHERE county = 'dallas' AND account_num = $1"
    )
    rows = [(uid, lon, lat) for uid, (lon, lat) in matches.items()]
    await conn.executemany(sql, rows)


def _iter_chunks(seq: Iterable, n: int):
    chunk: list = []
    for item in seq:
        chunk.append(item)
        if len(chunk) >= n:
            yield chunk
            chunk = []
    if chunk:
        yield chunk
