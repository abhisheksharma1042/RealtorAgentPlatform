"""RentCast API adapter - market stats + sold listings."""
import os
from typing import Any, Optional

import httpx

from backend.ingestion import config
from backend.ingestion.budget import get_or_fetch
from backend.ingestion.sources.base import SourceAdapter


class RentCastAdapter(SourceAdapter):
    provider_name = "rentcast"
    BASE_URL = "https://api.rentcast.io/v1"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("RENTCAST_API_KEY", "")

    async def fetch(self, endpoint: str, **params: Any) -> Any:
        ttl = config.get_ttl("rentcast", endpoint)
        ttl_days = ttl.days if ttl else None
        return await get_or_fetch(
            provider="rentcast",
            endpoint=endpoint,
            params={"endpoint": endpoint, **params},
            ttl_days=ttl_days,
            fetcher=lambda p: self._http_get(endpoint, {k: v for k, v in p.items() if k != "endpoint"}),
        )

    async def fetch_market(self, zip_code: str) -> dict[str, Any]:
        return await self.fetch(
            "markets",
            zipCode=zip_code,
            historyRange=12,
            statsType="Sale",
        )

    async def fetch_sold_listings(self, zip_code: str, limit: int = 100) -> list[dict[str, Any]]:
        result = await self.fetch(
            "sale_listings",
            zipCode=zip_code,
            status="Sold",
            limit=limit,
        )
        if isinstance(result, list):
            return result
        return result.get("listings", []) if isinstance(result, dict) else []

    async def _http_get(self, endpoint: str, params: dict[str, Any]) -> Any:
        path = {
            "markets": "/markets",
            "sale_listings": "/listings/sale",
        }[endpoint]
        headers = {"X-Api-Key": self.api_key, "Accept": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{self.BASE_URL}{path}", params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    async def normalize(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        raise NotImplementedError("Use normalize_market or normalize_sold_listings")

    async def normalize_market(self, zip_code: str, raw: dict[str, Any]) -> list[dict[str, Any]]:
        sale = raw.get("saleData") or {}
        history = sale.get("history") or {}
        rows: list[dict[str, Any]] = []
        for period_key, entry in history.items():
            year, month = period_key.split("-")
            period = f"{year}-{month.zfill(2)}-01"
            rows.append({
                "zip_code": zip_code,
                "period": period,
                "property_type": "all",
                "median_price": entry.get("medianPrice"),
                "avg_price": sale.get("averagePrice"),
                "sales_volume": entry.get("newListings"),
                "avg_days_on_market": entry.get("averageDaysOnMarket"),
                "median_price_per_sqft": sale.get("medianPricePerSquareFoot"),
                "active_listings_count": entry.get("totalListings"),
            })
        if not rows:
            period_key = (sale.get("lastUpdatedDate") or "2026-01-01")[:7]
            year, month = period_key.split("-")
            rows.append({
                "zip_code": zip_code,
                "period": f"{year}-{month.zfill(2)}-01",
                "property_type": "all",
                "median_price": sale.get("medianPrice"),
                "avg_price": sale.get("averagePrice"),
                "sales_volume": sale.get("newListings"),
                "avg_days_on_market": sale.get("averageDaysOnMarket"),
                "median_price_per_sqft": sale.get("medianPricePerSquareFoot"),
                "active_listings_count": sale.get("totalListings"),
            })
        return rows

    async def normalize_sold_listings(
        self, listings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for listing in listings:
            lat = listing.get("latitude")
            lon = listing.get("longitude")
            location = f"POINT({lon} {lat})" if lat is not None and lon is not None else None
            row = {
                "source": "rentcast",
                "external_id": listing.get("id"),
                "address": listing.get("formattedAddress") or listing.get("addressLine1"),
                "city": listing.get("city"),
                "zip_code": listing.get("zipCode"),
                "location": location,
                "lat": lat,
                "lon": lon,
                "beds": listing.get("bedrooms"),
                "baths": listing.get("bathrooms"),
                "sqft": listing.get("squareFootage"),
                "year_built": listing.get("yearBuilt"),
                "property_type": (listing.get("propertyType") or "").lower().replace(" ", "_"),
                "status": (listing.get("status") or "").lower(),
                "sold_price": listing.get("price"),
                "sold_date": listing.get("removedDate") or listing.get("lastSeenDate"),
                "days_on_market": listing.get("daysOnMarket"),
                "list_date": listing.get("listedDate"),
                "source_updated_at": listing.get("lastSeenDate"),
            }
            if row["external_id"]:
                rows.append(row)
        return rows
