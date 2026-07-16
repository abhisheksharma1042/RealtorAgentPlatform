"""Integration tests for the Hermes Knows CRUD API (live Supabase)."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
API_TEST_SEARCH = "apitest-search"
API_TEST_CONCEPT = "apitest_concept"


def test_saved_search_crud_roundtrip():
    try:
        created = client.post("/api/memory/searches", json={
            "name": API_TEST_SEARCH,
            "criteria": {"zip_code": "75205", "beds_min": 2},
            "client_note": "api test",
        })
        assert created.status_code == 200
        listed = client.get("/api/memory/searches").json()
        assert any(s["name"] == API_TEST_SEARCH for s in listed)
    finally:
        deleted = client.delete(f"/api/memory/searches/{API_TEST_SEARCH}")
        assert deleted.status_code == 200
    assert all(s["name"] != API_TEST_SEARCH
               for s in client.get("/api/memory/searches").json())


def test_skill_put_and_delete():
    try:
        put = client.put(f"/api/memory/skills/{API_TEST_CONCEPT}", json={"level": "familiar"})
        assert put.status_code == 200 and put.json()["level"] == "familiar"
        listed = client.get("/api/memory/skills").json()
        assert any(s["concept"] == API_TEST_CONCEPT for s in listed)
    finally:
        assert client.delete(f"/api/memory/skills/{API_TEST_CONCEPT}").status_code == 200


def test_pins_and_coverage_endpoints_respond():
    assert isinstance(client.get("/api/memory/pins").json(), list)
    cov = client.get("/api/coverage").json()
    assert "coverage" in cov and "boundaries" in cov
    assert any(row["zip"] == "75205" for row in cov["coverage"])


def test_delete_missing_search_404s():
    assert client.delete("/api/memory/searches/does-not-exist-xyz").status_code == 404


def test_saved_search_with_slash_in_name_deletable():
    name = "apitest/slash"
    created = client.post("/api/memory/searches", json={
        "name": name, "criteria": {"zip_code": "75205"},
    })
    assert created.status_code == 200
    from urllib.parse import quote
    deleted = client.delete(f"/api/memory/searches/{quote(name, safe='')}")
    assert deleted.status_code == 200
    assert all(s["name"] != name for s in client.get("/api/memory/searches").json())


def test_skill_level_correction_preserves_evidence_count():
    import asyncio
    from backend.db.client import db

    concept = "apitest_evidence"

    async def scenario():
        await db.delete_skill("00000000-0000-0000-0000-000000000001", concept)
        await db.upsert_skill("00000000-0000-0000-0000-000000000001", concept, "novice")
        await db.upsert_skill("00000000-0000-0000-0000-000000000001", concept, "learning")
        row = await db.set_skill_level("00000000-0000-0000-0000-000000000001", concept, "familiar")
        count = row["evidence_count"]
        await db.delete_skill("00000000-0000-0000-0000-000000000001", concept)
        return count

    assert asyncio.run(scenario()) == 2  # preserved, not reset to 1
