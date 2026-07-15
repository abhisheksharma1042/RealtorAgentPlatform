import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from backend.ingestion.sources.walkscore import WalkScoreAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_scores_parses_all_three_scores(monkeypatch):
    monkeypatch.setenv("WALKSCORE_API_KEY", "test_key")
    fixture = json.loads((FIXTURES / "walkscore_sample.json").read_text())

    fake_db = AsyncMock()
    fake_db.fetch_enrichment.return_value = None

    with patch("backend.ingestion.sources.walkscore.db", fake_db):
        adapter = WalkScoreAdapter()
        with respx.mock(assert_all_called=False) as router:
            router.route(host="api.walkscore.com").mock(
                return_value=httpx.Response(200, json=fixture)
            )
            result = await adapter.fetch_scores(
                "4712 Beverly Dr, Highland Park, TX", 32.8336, -96.7880
            )

    assert result["walk_score"] == 72
    assert result["transit_score"] == 45
    assert result["bike_score"] == 60
