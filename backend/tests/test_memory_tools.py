import pytest

from backend.agent import memory_tools


class FakeDB:
    def __init__(self):
        self.pins = {}
        self.searches = {}
        self.skills = {}
        self.matches = []
        self.coverage = [{"county": "dallas", "zip": "75248", "parcel_count": 9000,
                          "appraisal_year": 2025, "geocoded_count": 9000,
                          "sold_listing_count": 50, "stats_from": None, "stats_to": None}]
        self.boundaries = [{"zip": "75248", "boundary": {"type": "Feature"}}]
        self.comps_calls = []

    async def find_property_by_address(self, query, limit=5):
        return self.matches

    async def upsert_pin(self, user_id, property_id, note=None):
        self.pins[property_id] = note
        return {"property_id": property_id, "note": note}

    async def delete_pin(self, user_id, property_id):
        return self.pins.pop(property_id, "absent") != "absent"

    async def get_saved_search(self, user_id, name):
        return self.searches.get(name)

    async def list_saved_searches(self, user_id):
        return list(self.searches.values())

    async def upsert_saved_search(self, user_id, name, criteria, client_note=None):
        row = {"name": name, "criteria": criteria, "client_note": client_note}
        self.searches[name] = row
        return row

    async def touch_saved_search(self, user_id, name):
        self.searches[name]["last_run_at"] = "now"

    async def upsert_skill(self, user_id, concept, level, note=None):
        self.skills[concept] = level
        return {"concept": concept, "level": level, "evidence_count": 1}

    async def get_data_coverage(self):
        return self.coverage

    async def get_zip_boundaries(self):
        return self.boundaries

    async def get_comparable_sales(self, **kwargs):
        self.comps_calls.append(kwargs)
        return {"type": "comparable_sales", "zip_code": kwargs.get("zip_code"),
                "count": 1, "properties": [], "map_markers": []}


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(memory_tools, "db", fake)
    return fake


@pytest.mark.asyncio
async def test_pin_property_single_match(fake_db):
    fake_db.matches = [{"id": "abc-123", "address": "4024 DRUID LN", "zip_code": "75205"}]
    result = await memory_tools.pin_property("4024 Druid Ln", note="clients liked it")
    assert result["type"] == "pin_update" and result["action"] == "pinned"
    assert fake_db.pins["abc-123"] == "clients liked it"


@pytest.mark.asyncio
async def test_pin_property_ambiguous_returns_candidates(fake_db):
    fake_db.matches = [
        {"id": "a", "address": "1 DRUID LN", "zip_code": "75205"},
        {"id": "b", "address": "2 DRUID LN", "zip_code": "75205"},
    ]
    result = await memory_tools.pin_property("Druid Ln")
    assert "error" in result and len(result["candidates"]) == 2
    assert fake_db.pins == {}  # never pin a guess


@pytest.mark.asyncio
async def test_pin_property_no_match(fake_db):
    fake_db.matches = []
    result = await memory_tools.pin_property("999 Nowhere St")
    assert "error" in result and "candidates" not in result


@pytest.mark.asyncio
async def test_save_search_warns_out_of_coverage(fake_db):
    result = await memory_tools.save_search("FortWorth", {"zip_code": "76102"})
    assert result["action"] == "saved"
    assert "76102" in result["warning"]
    ok = await memory_tools.save_search("Johnsons", {"zip_code": "75248", "beds_min": 3})
    assert ok["warning"] is None


@pytest.mark.asyncio
async def test_run_saved_search_delegates_and_touches(fake_db):
    fake_db.searches["Johnsons"] = {
        "name": "Johnsons",
        "criteria": {"zip_code": "75248", "beds_min": 3, "bogus_key": True},
    }
    result = await memory_tools.run_saved_search("Johnsons")
    assert result["type"] == "comparable_sales"
    assert result["saved_search_name"] == "Johnsons"
    assert fake_db.comps_calls == [{"zip_code": "75248", "beds_min": 3}]  # bogus_key filtered
    assert fake_db.searches["Johnsons"]["last_run_at"] == "now"


@pytest.mark.asyncio
async def test_run_saved_search_unknown_name(fake_db):
    result = await memory_tools.run_saved_search("Nope")
    assert "error" in result


@pytest.mark.asyncio
async def test_record_skill_observation_normalizes_concept(fake_db):
    result = await memory_tools.record_skill_observation("Days On Market", "novice")
    assert result["type"] == "skill_update"
    assert "days_on_market" in fake_db.skills


@pytest.mark.asyncio
async def test_dismiss_widget_shape():
    result = await memory_tools.dismiss_widget("map:75248")
    assert result == {"type": "widget_dismiss", "widget_key": "map:75248"}


@pytest.mark.asyncio
async def test_get_data_coverage_shape(fake_db):
    result = await memory_tools.get_data_coverage()
    assert result["type"] == "data_coverage"
    assert result["coverage"][0]["zip"] == "75248"
    assert result["boundaries"] == [{"type": "Feature"}]
