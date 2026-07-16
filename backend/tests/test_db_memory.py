"""Integration tests for Hermes memory db methods (live Supabase, migration 007)."""
import pytest

TEST_USER = "00000000-0000-0000-0000-000000009999"


@pytest.mark.asyncio
async def test_pin_roundtrip(db):
    prop = db.client.table("properties").select("id, address").limit(1).execute().data[0]
    try:
        pin = await db.upsert_pin(TEST_USER, prop["id"], note="integration test")
        assert pin["property_id"] == prop["id"]
        pins = await db.list_pins(TEST_USER)
        assert any(p["property_id"] == prop["id"] for p in pins)
        # joined property payload present for display
        joined = next(p for p in pins if p["property_id"] == prop["id"])
        assert joined["properties"]["address"] == prop["address"]
        assert await db.delete_pin(TEST_USER, prop["id"]) is True
    finally:
        await db.delete_pin(TEST_USER, prop["id"])
    assert all(p["property_id"] != prop["id"] for p in await db.list_pins(TEST_USER))


@pytest.mark.asyncio
async def test_saved_search_roundtrip(db):
    await db.delete_saved_search(TEST_USER, "itest-johnsons")  # pre-clean leftover from crashed runs
    try:
        row = await db.upsert_saved_search(
            TEST_USER, "itest-johnsons",
            {"zip_code": "75248", "beds_min": 3, "price_max": 800000},
            client_note="integration",
        )
        assert row["name"] == "itest-johnsons"
        fetched = await db.get_saved_search(TEST_USER, "itest-johnsons")
        assert fetched["criteria"]["zip_code"] == "75248"
        await db.touch_saved_search(TEST_USER, "itest-johnsons")
        assert (await db.get_saved_search(TEST_USER, "itest-johnsons"))["last_run_at"] is not None
        # upsert by name updates, not duplicates
        await db.upsert_saved_search(TEST_USER, "itest-johnsons", {"zip_code": "75205"})
        rows = [s for s in await db.list_saved_searches(TEST_USER) if s["name"] == "itest-johnsons"]
        assert len(rows) == 1 and rows[0]["criteria"]["zip_code"] == "75205"
        # omitting client_note on re-upsert preserves the original value
        assert rows[0]["client_note"] == "integration"
        assert await db.delete_saved_search(TEST_USER, "itest-johnsons") is True
    finally:
        await db.delete_saved_search(TEST_USER, "itest-johnsons")


@pytest.mark.asyncio
async def test_skill_evidence_and_familiar_guard(db):
    await db.delete_skill(TEST_USER, "itest_dom")  # pre-clean leftover from crashed runs
    try:
        first = await db.upsert_skill(TEST_USER, "itest_dom", "novice", note="asked what DOM means")
        assert first["evidence_count"] == 1 and first["level"] == "novice"
        # One observation never jumps straight to familiar
        second = await db.upsert_skill(TEST_USER, "itest_dom", "familiar")
        assert second["evidence_count"] == 2 and second["level"] == "learning"
        third = await db.upsert_skill(TEST_USER, "itest_dom", "familiar")
        assert third["evidence_count"] == 3 and third["level"] == "familiar"
        # User correction via set_skill_level sticks
        corrected = await db.set_skill_level(TEST_USER, "itest_dom", "novice")
        assert corrected["level"] == "novice"
        assert await db.delete_skill(TEST_USER, "itest_dom") is True
    finally:
        await db.delete_skill(TEST_USER, "itest_dom")


@pytest.mark.asyncio
async def test_skill_note_preserved_on_omission(db):
    await db.delete_skill(TEST_USER, "itest_note")
    try:
        await db.upsert_skill(TEST_USER, "itest_note", "novice", note="asked about it")
        row = await db.upsert_skill(TEST_USER, "itest_note", "learning")  # no note
        assert row["notes"] == "asked about it"
    finally:
        await db.delete_skill(TEST_USER, "itest_note")


@pytest.mark.asyncio
async def test_user_set_level_resists_agent_downgrade(db):
    await db.delete_skill(TEST_USER, "itest_auth")
    try:
        await db.set_skill_level(TEST_USER, "itest_auth", "familiar")
        row = await db.upsert_skill(TEST_USER, "itest_auth", "novice")  # agent observation
        assert row["level"] == "familiar"  # user correction is authoritative
    finally:
        await db.delete_skill(TEST_USER, "itest_auth")


@pytest.mark.asyncio
async def test_data_coverage_and_boundaries(db):
    rows = await db.get_data_coverage()
    assert len(rows) >= 5
    zips = {r["zip"] for r in rows}
    assert {"75201", "75204", "75205", "75225", "75248"} <= zips
    assert all(r["parcel_count"] > 0 for r in rows)
    # boundaries table exists (may be empty until Task 3's CLI runs)
    boundaries = await db.get_zip_boundaries()
    assert isinstance(boundaries, list)


@pytest.mark.asyncio
async def test_find_property_by_address(db):
    sample = db.client.table("properties").select("id, address").limit(1).execute().data[0]
    matches = await db.find_property_by_address(sample["address"])
    assert any(m["id"] == sample["id"] for m in matches)
    # UUID fast-path
    by_id = await db.find_property_by_address(sample["id"])
    assert len(by_id) == 1 and by_id[0]["id"] == sample["id"]


@pytest.mark.asyncio
async def test_comparable_sales_includes_zip_code(db):
    result = await db.get_comparable_sales(zip_code="75205", limit=3)
    assert result["type"] == "comparable_sales"
    assert result["zip_code"] == "75205"
