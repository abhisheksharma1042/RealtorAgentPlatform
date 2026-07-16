import httpx
import pytest

from backend.ingestion import boundaries


FAKE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"ZCTA5": "75205"},
            "geometry": {"type": "Polygon",
                         "coordinates": [[[-96.8, 32.8], [-96.79, 32.8], [-96.79, 32.84], [-96.8, 32.8]]]},
        }
    ],
}


@pytest.mark.asyncio
async def test_fetch_boundary_returns_feature(mock_http):
    mock_http.route(host="tigerweb.geo.census.gov").mock(
        return_value=httpx.Response(200, json=FAKE_GEOJSON)
    )
    feature = await boundaries.fetch_boundary("75205")
    assert feature["properties"]["ZCTA5"] == "75205"
    assert feature["geometry"]["type"] == "Polygon"


@pytest.mark.asyncio
async def test_fetch_boundary_no_match_returns_none(mock_http):
    mock_http.route(host="tigerweb.geo.census.gov").mock(
        return_value=httpx.Response(200, json={"type": "FeatureCollection", "features": []})
    )
    assert await boundaries.fetch_boundary("00000") is None


@pytest.mark.asyncio
async def test_backfill_boundaries_upserts(mock_http, monkeypatch):
    mock_http.route(host="tigerweb.geo.census.gov").mock(
        return_value=httpx.Response(200, json=FAKE_GEOJSON)
    )
    saved = []

    class FakeDB:
        async def upsert_zip_boundary(self, zip_code, boundary):
            saved.append((zip_code, boundary))

    monkeypatch.setattr(boundaries, "db", FakeDB())
    count = await boundaries.backfill_boundaries(["75205", "75201"])
    assert count == 2
    assert saved[0][0] == "75205"
