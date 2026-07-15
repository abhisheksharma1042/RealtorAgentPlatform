"""DCAD parcel bulk-export adapter.

The DCAD current-year zip is a relational dump — one CSV per table, joined by
ACCOUNT_NUM. This adapter downloads the zip, filters ACCOUNT_INFO to the zips
we care about, then joins RES_DETAIL (beds/baths/sqft/year), ACCOUNT_APPRL_YEAR
(appraised value), and LAND (lot size) for those accounts.
"""
import csv
import io
import os
import zipfile
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx

from backend.ingestion.sources.base import SourceAdapter


class DCADAdapter(SourceAdapter):
    provider_name = "dcad"
    county = "dallas"
    DEFAULT_URL = os.getenv(
        "DCAD_BULK_URL",
        # DCAD 2025 Certified Data Files with Supplemental Changes (Comma Delimited).
        # ~196MB zip, ~1.5GB extracted, 18 CSVs joined by ACCOUNT_NUM.
        "https://www.dallascad.org/ViewPDFs.aspx"
        "?type=3&id=%5C%5CDCAD.ORG%5CWEB%5CWEBDATA%5CWEBFORMS%5CDATA%20PRODUCTS"
        "%5CDCAD2025_CURRENT.ZIP",
    )

    # ---------- Download ----------

    async def fetch(self, dest_path: Optional[str] = None) -> str:
        """Download the DCAD bulk zip. Returns local file path."""
        dest = Path(dest_path or "/tmp/dcad_current.zip")
        async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
            resp = await client.get(self.DEFAULT_URL)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return str(dest)

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("DCAD uses parse_zip/parse_csv + to_property_row directly")

    # ---------- Real DCAD ZIP parser ----------

    def parse_zip(
        self,
        zip_path: str | Path,
        seeded_zips: Optional[list[str]] = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield joined parcel dicts from a DCAD current-year zip.

        If ``seeded_zips`` is provided, filter to accounts whose PROPERTY_ZIPCODE
        (first 5 digits) is in the list. Yields ~5-10K rows for a handful of zips
        vs. ~860K if unfiltered.
        """
        with zipfile.ZipFile(zip_path) as z:
            addresses = self._read_account_info(z, seeded_zips)
            wanted = set(addresses.keys())
            res_details = self._read_indexed(z, "RES_DETAIL.CSV", wanted)
            values = self._read_indexed(z, "ACCOUNT_APPRL_YEAR.CSV", wanted)
            lands_sqft = self._read_land_totals(z, wanted)

            for acc, addr in addresses.items():
                res = res_details.get(acc, {})
                val = values.get(acc, {})
                land_sqft = lands_sqft.get(acc)

                full_b = _to_int(res.get("NUM_FULL_BATHS")) or 0
                half_b = _to_int(res.get("NUM_HALF_BATHS")) or 0
                baths = (full_b + 0.5 * half_b) if (full_b or half_b) else None

                yield {
                    "county": self.county,
                    "account_num": acc.strip(),
                    "situs_address": addr["situs_address"],
                    "situs_zip": addr["situs_zip"],
                    "city": addr["city"],
                    "land_use_code": (res.get("BLDG_CLASS_DESC") or "").strip() or None,
                    "living_area_sqft": _to_int(res.get("TOT_LIVING_AREA_SF")),
                    "land_sqft": int(land_sqft) if land_sqft else None,
                    "year_built": _to_int(res.get("YR_BUILT")),
                    "bedrooms": _to_int(res.get("NUM_BEDROOMS")),
                    "bathrooms": baths,
                    "total_appraised": _to_float(val.get("TOT_VAL")),
                    "land_value": _to_float(val.get("LAND_VAL")),
                    "improvement_value": _to_float(val.get("IMPR_VAL")),
                    "tax_year": _to_int(val.get("APPRAISAL_YR")) or _to_int(
                        res.get("APPRAISAL_YR")
                    ),
                    "location": None,  # DCAD ships no lat/lon; needs geocoding
                    "raw": {
                        "account_info": addr["raw_account_info"],
                        "res_detail": res,
                        "appraisal": val,
                    },
                    "source_updated_at": None,
                }

    def _read_account_info(
        self,
        z: zipfile.ZipFile,
        seeded_zips: Optional[list[str]],
    ) -> dict[str, dict[str, Any]]:
        want = set(seeded_zips) if seeded_zips else None
        out: dict[str, dict[str, Any]] = {}
        with z.open("ACCOUNT_INFO.CSV") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
            for r in reader:
                zip_ = (r.get("PROPERTY_ZIPCODE") or "").strip()[:5]
                if want is not None and zip_ not in want:
                    continue
                out[r["ACCOUNT_NUM"]] = {
                    "situs_zip": zip_,
                    "city": (r.get("PROPERTY_CITY") or "").strip() or None,
                    "situs_address": self._build_address(r),
                    "raw_account_info": dict(r),
                }
        return out

    def _read_indexed(
        self,
        z: zipfile.ZipFile,
        member: str,
        wanted: set[str],
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        with z.open(member) as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
            for r in reader:
                acc = r.get("ACCOUNT_NUM")
                if acc in wanted:
                    out[acc] = r
        return out

    def _read_land_totals(
        self,
        z: zipfile.ZipFile,
        wanted: set[str],
    ) -> dict[str, float]:
        """Sum LAND.AREA_SIZE across sections for each account, converted to sqft."""
        out: dict[str, float] = {}
        with z.open("LAND.CSV") as f:
            reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
            for r in reader:
                acc = r.get("ACCOUNT_NUM")
                if acc not in wanted:
                    continue
                area = _to_float(r.get("AREA_SIZE")) or 0
                uom = (r.get("AREA_UOM_DESC") or "").upper()
                sqft = area * 43560 if "ACRE" in uom else area
                out[acc] = out.get(acc, 0.0) + sqft
        return out

    def _build_address(self, r: dict[str, str]) -> str:
        parts = [
            (r.get("STREET_NUM") or "").strip(),
            (r.get("STREET_HALF_NUM") or "").strip(),
            (r.get("FULL_STREET_NAME") or "").strip(),
        ]
        addr = " ".join(p for p in parts if p)
        unit = (r.get("UNIT_ID") or "").strip()
        if unit:
            addr += f" #{unit}"
        return addr

    # ---------- Legacy single-CSV parser (kept for the flat test fixture) ----------

    def parse_csv(self, path) -> Iterator[dict[str, Any]]:
        """Parse the flat single-CSV test fixture format.

        Not used against real DCAD data - real DCAD comes as a zip of related
        tables, parsed via parse_zip(). This method exists so the fast test
        fixture (backend/tests/fixtures/dcad_parcel_sample.csv) keeps working.
        """
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                yield self._flat_row_to_parcel(r)

    def _flat_row_to_parcel(self, r: dict[str, str]) -> dict[str, Any]:
        lat = _to_float(r.get("LATITUDE"))
        lon = _to_float(r.get("LONGITUDE"))
        location = f"POINT({lon} {lat})" if lat is not None and lon is not None else None
        return {
            "county": self.county,
            "account_num": (r.get("ACCOUNT_NUM") or "").strip(),
            "situs_address": (r.get("SITUS_ADDRESS") or "").strip(),
            "situs_zip": (r.get("SITUS_ZIP") or "").strip() or None,
            "city": (r.get("SITUS_CITY") or "").strip() or None,
            "land_use_code": (r.get("LAND_USE_CODE") or "").strip() or None,
            "living_area_sqft": _to_int(r.get("LIVING_AREA_SQFT")),
            "land_sqft": _to_int(r.get("LAND_SQFT")),
            "year_built": _to_int(r.get("YEAR_BUILT")),
            "bedrooms": _to_int(r.get("BEDROOMS")),
            "bathrooms": _to_float(r.get("BATHROOMS")),
            "total_appraised": _to_float(r.get("TOTAL_APPRAISED")),
            "land_value": _to_float(r.get("LAND_VALUE")),
            "improvement_value": _to_float(r.get("IMPROVEMENT_VALUE")),
            "tax_year": _to_int(r.get("TAX_YEAR")),
            "location": location,
            "raw": dict(r),
        }

    # ---------- Normalization to properties row ----------

    def to_property_row(self, parcel: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "county",
            "external_id": f"{parcel['county']}:{parcel['account_num']}",
            "address": parcel["situs_address"],
            "city": parcel.get("city"),
            "zip_code": parcel.get("situs_zip"),
            "location": parcel.get("location"),
            "beds": parcel.get("bedrooms"),
            "baths": parcel.get("bathrooms"),
            "sqft": parcel.get("living_area_sqft"),
            "lot_size_acres": _sqft_to_acres(parcel.get("land_sqft")),
            "year_built": parcel.get("year_built"),
            "property_type": None,
            "status": None,
        }


def _to_int(v: Optional[str]) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _to_float(v: Optional[str]) -> Optional[float]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _sqft_to_acres(sqft: Optional[int]) -> Optional[float]:
    if sqft is None:
        return None
    return round(sqft / 43560, 3)
