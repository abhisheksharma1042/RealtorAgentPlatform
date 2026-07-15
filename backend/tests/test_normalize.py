from backend.ingestion.normalize import (
    normalize_address,
    merge_property_records,
)


def test_normalize_address_uppercases_and_strips_suffixes():
    assert (
        normalize_address("4712 Beverly Dr, Highland Park, TX 75205")
        == "4712 BEVERLY DR HIGHLAND PARK TX 75205"
    )


def test_normalize_address_removes_punctuation():
    assert (
        normalize_address("123 Main St., Apt. 4B, Dallas, TX")
        == "123 MAIN ST APT 4B DALLAS TX"
    )


def test_normalize_address_collapses_whitespace():
    assert normalize_address("  4712   Beverly    Dr  ") == "4712 BEVERLY DR"


def test_merge_favors_county_for_attributes_and_rentcast_for_price():
    county_row = {
        "source": "county",
        "external_id": "dallas:00000012345",
        "address": "4712 BEVERLY DR",
        "zip_code": "75205",
        "beds": 4,
        "baths": 3.5,
        "sqft": 3200,
        "year_built": 1998,
        "sold_price": None,
        "sold_date": None,
    }
    rentcast_row = {
        "source": "rentcast",
        "external_id": "rc_abc123",
        "address": "4712 BEVERLY DR",
        "zip_code": "75205",
        "beds": 4,
        "baths": 4.0,
        "sqft": 3250,
        "year_built": None,
        "sold_price": 1350000,
        "sold_date": "2026-02-28",
    }
    merged = merge_property_records(county_row, rentcast_row)
    assert merged["source"] == "merged"
    assert merged["external_id"] == "merged:dallas:00000012345"
    assert merged["beds"] == 4
    assert merged["baths"] == 3.5
    assert merged["sqft"] == 3200
    assert merged["year_built"] == 1998
    assert merged["sold_price"] == 1350000
    assert merged["sold_date"] == "2026-02-28"


def test_merge_handles_missing_county_fields():
    county_row = {
        "source": "county",
        "external_id": "dallas:00000067890",
        "address": "3010 MOCKINGBIRD LN",
        "zip_code": "75205",
        "beds": None,
        "sqft": None,
    }
    rentcast_row = {
        "source": "rentcast",
        "external_id": "rc_xyz",
        "beds": 3,
        "sqft": 2400,
        "sold_price": 895000,
    }
    merged = merge_property_records(county_row, rentcast_row)
    assert merged["beds"] == 3
    assert merged["sqft"] == 2400
    assert merged["sold_price"] == 895000
