from pathlib import Path
import pytest

from backend.ingestion.sources.dcad import DCADAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_parse_csv_yields_normalized_rows():
    adapter = DCADAdapter()
    rows = list(adapter.parse_csv(FIXTURES / "dcad_parcel_sample.csv"))
    assert len(rows) == 3
    r0 = rows[0]
    assert r0["county"] == "dallas"
    assert r0["account_num"] == "00000012345"
    assert r0["situs_address"] == "4712 BEVERLY DR"
    assert r0["situs_zip"] == "75205"
    assert r0["living_area_sqft"] == 3200
    assert r0["bedrooms"] == 4
    assert r0["bathrooms"] == 3.5
    assert r0["total_appraised"] == 1450000
    assert r0["location"] == "POINT(-96.788 32.8336)"


def test_parse_csv_handles_missing_numerics():
    adapter = DCADAdapter()
    rows = list(adapter.parse_csv(FIXTURES / "dcad_parcel_sample.csv"))
    r2 = rows[2]
    assert r2["living_area_sqft"] is None
    assert r2["bedrooms"] is None
    assert r2["location"] is None


def test_to_property_row_from_parcel():
    adapter = DCADAdapter()
    parcel = {
        "county": "dallas",
        "account_num": "00000012345",
        "situs_address": "4712 BEVERLY DR",
        "situs_zip": "75205",
        "city": "HIGHLAND PARK",
        "living_area_sqft": 3200,
        "land_sqft": 8500,
        "year_built": 1998,
        "bedrooms": 4,
        "bathrooms": 3.5,
        "location": "POINT(-96.788 32.8336)",
    }
    row = adapter.to_property_row(parcel)
    assert row["source"] == "county"
    assert row["external_id"] == "dallas:00000012345"
    assert row["zip_code"] == "75205"
    assert row["beds"] == 4
    assert row["sqft"] == 3200
