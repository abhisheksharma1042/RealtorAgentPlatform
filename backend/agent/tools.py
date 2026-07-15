"""Tool definitions for the DFW Realtor Agent (live Supabase-backed)."""
from typing import Any, Dict, Optional

from backend.db.client import db


async def fetch_market_data(
    zip_code: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    property_type: str = "all",
) -> Dict[str, Any]:
    """Fetch aggregate market statistics for a DFW ZIP code."""
    stats = await db.get_market_stats(
        zip_code=zip_code, months=12, property_type=property_type
    )
    if not stats:
        # Lazy fetch via RentCast, budget permitting
        try:
            from backend.ingestion.sources.rentcast import RentCastAdapter
            from backend.ingestion import normalize
            raw = await RentCastAdapter().fetch_market(zip_code)
            await normalize.normalize_rentcast_market_to_stats(zip_code, raw)
            stats = await db.get_market_stats(
                zip_code=zip_code, months=12, property_type=property_type
            )
        except Exception as exc:
            return {
                "type": "market_data",
                "zip_code": zip_code,
                "error": f"No cached data and live fetch failed: {exc}",
            }
    if not stats:
        return {"type": "market_data", "zip_code": zip_code, "error": "No data available"}

    latest = stats[0]
    return {
        "type": "market_data",
        "zip_code": zip_code,
        "property_type": property_type,
        "median_price": latest.get("median_price"),
        "avg_price": latest.get("avg_price"),
        "sales_volume": latest.get("sales_volume"),
        "avg_days_on_market": latest.get("avg_days_on_market"),
        "median_price_per_sqft": latest.get("median_price_per_sqft"),
        "active_listings_count": latest.get("active_listings_count"),
        "history": stats,
    }


async def get_comparable_sales(
    zip_code: Optional[str] = None,
    beds_min: Optional[int] = None,
    beds_max: Optional[int] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    sqft_min: Optional[int] = None,
    sqft_max: Optional[int] = None,
    limit: int = 20,
) -> Dict[str, Any]:
    """Retrieve comparable properties from the normalized layer."""
    return await db.get_comparable_sales(
        zip_code=zip_code,
        beds_min=beds_min,
        beds_max=beds_max,
        price_min=price_min,
        price_max=price_max,
        sqft_min=sqft_min,
        sqft_max=sqft_max,
        limit=limit,
    )


TOOLS = [
    {
        "name": "fetch_market_data",
        "description": (
            "Fetch aggregate market statistics for a DFW ZIP code including median price, "
            "sales volume, days on market, and trends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {
                    "type": "string",
                    "description": "The ZIP code to query (e.g., '75205' for Highland Park)",
                },
                "date_from": {
                    "type": "string",
                    "description": "Start date for data range (optional, format: YYYY-MM-DD)",
                },
                "date_to": {
                    "type": "string",
                    "description": "End date for data range (optional, format: YYYY-MM-DD)",
                },
                "property_type": {
                    "type": "string",
                    "enum": ["single_family", "condo", "townhome", "all"],
                    "description": "Type of property to filter by",
                },
            },
            "required": ["zip_code"],
        },
    },
    {
        "name": "get_comparable_sales",
        "description": (
            "Retrieve comparable properties from the normalized data layer, filtered by "
            "location and attributes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {"type": "string", "description": "ZIP code to search in"},
                "beds_min": {"type": "integer", "description": "Minimum number of bedrooms"},
                "beds_max": {"type": "integer", "description": "Maximum number of bedrooms"},
                "price_min": {"type": "number", "description": "Minimum price in dollars"},
                "price_max": {"type": "number", "description": "Maximum price in dollars"},
                "sqft_min": {"type": "integer", "description": "Minimum square footage"},
                "sqft_max": {"type": "integer", "description": "Maximum square footage"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 20,
                },
            },
            "required": ["zip_code"],
        },
    },
]

TOOL_FUNCTIONS = {
    "fetch_market_data": fetch_market_data,
    "get_comparable_sales": get_comparable_sales,
}
