"""DCAD parcel bulk-export adapter."""
import csv
import os
from pathlib import Path
from typing import Any, Iterator, Optional

import httpx

from backend.ingestion.sources.base import SourceAdapter


class DCADAdapter(SourceAdapter):
    provider_name = "dcad"
    county = "dallas"
    DEFAULT_URL = os.getenv(
        "DCAD_BULK_URL",
        "https://www.dallascad.org/DataProducts/parcels_current.csv",
    )

    async def fetch(self, dest_path: Optional[str] = None) -> str:
        dest = Path(dest_path or "/tmp/dcad_parcels.csv")
        async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
            resp = await client.get(self.DEFAULT_URL)
            resp.raise_for_status()
            dest.write_bytes(resp.content)
        return str(dest)

    def parse_csv(self, path) -> Iterator[dict[str, Any]]:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for r in reader:
                yield self._row_to_parcel(r)

    def _row_to_parcel(self, r: dict[str, str]) -> dict[str, Any]:
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

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("DCAD uses parse_csv + to_property_row directly")


def _to_int(v: Optional[str]) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_float(v: Optional[str]) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _sqft_to_acres(sqft: Optional[int]) -> Optional[float]:
    if sqft is None:
        return None
    return round(sqft / 43560, 3)
