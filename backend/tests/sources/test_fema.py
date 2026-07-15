import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from backend.ingestion.sources.fema import FemaAdapter

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_flood_zone_returns_normalized_result():
    fixture = json.loads((FIXTURES / "fema_nfhl_sample.json").read_text())

    fake_db = AsyncMock()
    fake_db.fetch_enrichment.return_value = None

    with patch("backend.ingestion.sources.fema.db", fake_db):
        adapter = FemaAdapter()
        with respx.mock(assert_all_called=False) as router:
            router.get(url__startswith="https://hazards.fema.gov").mock(
                return_value=httpx.Response(200, json=fixture)
            )
            result = await adapter.fetch_flood_zone(lat=32.8336, lon=-96.7880)

    assert result["fld_zone"] == "X"
    assert result["is_sfha"] is False
