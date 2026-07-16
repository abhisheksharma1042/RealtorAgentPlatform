import pytest

from backend.hermes import memory


class FakeDB:
    def __init__(self, pins=None, searches=None, skills=None, coverage=None, fail=False):
        self._pins = pins or []
        self._searches = searches or []
        self._skills = skills or []
        self._coverage = coverage if coverage is not None else [
            {"county": "dallas", "zip": "75205", "parcel_count": 5000,
             "appraisal_year": 2025, "geocoded_count": 5000,
             "sold_listing_count": 100, "stats_from": "2021-07-01", "stats_to": "2026-06-01"},
        ]
        self._fail = fail

    async def list_pins(self, user_id):
        if self._fail:
            raise RuntimeError("db down")
        return self._pins

    async def list_saved_searches(self, user_id):
        return self._searches

    async def list_skills(self, user_id):
        return self._skills

    async def get_data_coverage(self):
        return self._coverage


@pytest.mark.asyncio
async def test_block_renders_all_sections(monkeypatch):
    monkeypatch.setattr(memory, "db", FakeDB(
        pins=[{"note": "clients liked it",
               "properties": {"address": "4024 DRUID LN", "zip_code": "75205"}}],
        searches=[{"name": "Johnsons",
                   "criteria": {"zip_code": "75248", "beds_min": 3, "price_max": 800000},
                   "client_note": "first-time buyers"}],
        skills=[{"concept": "dom", "level": "novice"},
                {"concept": "comps", "level": "familiar"}],
    ))
    block = await memory.build_memory_block()
    assert "Johnsons" in block and "75248" in block
    assert "4024 DRUID LN" in block and "clients liked it" in block
    assert "dom" in block and "comps" in block
    assert "75205" in block  # coverage line
    assert "non-disclosure" in block


@pytest.mark.asyncio
async def test_empty_memory_still_has_coverage(monkeypatch):
    monkeypatch.setattr(memory, "db", FakeDB())
    block = await memory.build_memory_block()
    assert "Saved searches" not in block
    assert "Pinned" not in block
    assert "skill profile" not in block
    assert "75205" in block  # coverage always present


@pytest.mark.asyncio
async def test_db_failure_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(memory, "db", FakeDB(fail=True))
    block = await memory.build_memory_block()
    assert "Memory unavailable" in block
