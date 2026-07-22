"""CORS contract: the production domain must be an allowed origin."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_cors_preflight_allows_production_origin():
    res = client.options(
        "/api/memory/pins",
        headers={
            "Origin": "https://realtor.shergillvps.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert (
        res.headers["access-control-allow-origin"]
        == "https://realtor.shergillvps.com"
    )
