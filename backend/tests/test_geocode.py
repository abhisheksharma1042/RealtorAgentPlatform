"""Unit tests for the Census batch-geocoder response parser."""
from backend.ingestion.geocode import _parse_batch_response


def test_parse_response_extracts_matches():
    body = (
        '"1","4712 BEVERLY DR, HIGHLAND PARK, TX, 75205","Match","No Match",'
        '"4712 BEVERLY DR, DALLAS, TX, 75205","-96.788,32.8336","76287923","L"\n'
        '"2","BAD ADDRESS","No_Match","",,,,\n'
        '"3","3010 MOCKINGBIRD LN, DALLAS, TX, 75205","Match","",'
        '"3010 MOCKINGBIRD LN, DALLAS, TX, 75205","-96.7855,32.8360","76287924","R"\n'
    )
    matches = _parse_batch_response(body)
    assert set(matches.keys()) == {"1", "3"}
    assert matches["1"] == (-96.788, 32.8336)
    assert matches["3"] == (-96.7855, 32.8360)


def test_parse_response_skips_missing_coords():
    body = (
        '"1","addr","Match","","","","",""\n'
        '"2","addr","Match","","matched","not_a_number,also_not","",""\n'
    )
    assert _parse_batch_response(body) == {}
