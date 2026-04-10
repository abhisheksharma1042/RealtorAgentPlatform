"""Tool definitions for the DFW Realtor Agent"""

from typing import Dict, Any, List
import json


# Mock data for development
MOCK_MARKET_DATA = {
    "75201": {
        "zip_code": "75201",
        "area_name": "Downtown Dallas",
        "median_price": 385000,
        "avg_price": 425000,
        "sales_volume": 142,
        "avg_days_on_market": 28,
        "median_price_per_sqft": 285,
        "trend": "up",
        "price_change_1y": 8.5,
    },
    "75205": {
        "zip_code": "75205",
        "area_name": "Highland Park",
        "median_price": 1250000,
        "avg_price": 1450000,
        "sales_volume": 87,
        "avg_days_on_market": 42,
        "median_price_per_sqft": 425,
        "trend": "stable",
        "price_change_1y": 2.1,
    },
    "75219": {
        "zip_code": "75219",
        "area_name": "Uptown Dallas",
        "median_price": 495000,
        "avg_price": 535000,
        "sales_volume": 203,
        "avg_days_on_market": 22,
        "median_price_per_sqft": 315,
        "trend": "up",
        "price_change_1y": 12.3,
    },
}

MOCK_COMPARABLE_SALES = {
    "75201": [
        {
            "id": "prop_001",
            "address": "1234 Main St, Dallas, TX 75201",
            "price": 375000,
            "beds": 2,
            "baths": 2,
            "sqft": 1350,
            "price_per_sqft": 278,
            "sold_date": "2024-03-15",
            "days_on_market": 25,
            "lat": 32.7831,
            "lon": -96.7969,
        },
        {
            "id": "prop_002",
            "address": "5678 Elm St, Dallas, TX 75201",
            "price": 425000,
            "beds": 3,
            "baths": 2.5,
            "sqft": 1650,
            "price_per_sqft": 258,
            "sold_date": "2024-03-20",
            "days_on_market": 18,
            "lat": 32.7856,
            "lon": -96.7989,
        },
        {
            "id": "prop_003",
            "address": "910 Commerce St, Dallas, TX 75201",
            "price": 395000,
            "beds": 2,
            "baths": 2,
            "sqft": 1425,
            "price_per_sqft": 277,
            "sold_date": "2024-03-18",
            "days_on_market": 31,
            "lat": 32.7814,
            "lon": -96.7945,
        },
    ],
    "75205": [
        {
            "id": "prop_004",
            "address": "123 Beverly Dr, Highland Park, TX 75205",
            "price": 1350000,
            "beds": 4,
            "baths": 3.5,
            "sqft": 3200,
            "price_per_sqft": 422,
            "sold_date": "2024-02-28",
            "days_on_market": 45,
            "lat": 32.8336,
            "lon": -96.7880,
        },
        {
            "id": "prop_005",
            "address": "456 Preston Rd, Highland Park, TX 75205",
            "price": 1150000,
            "beds": 3,
            "baths": 3,
            "sqft": 2800,
            "price_per_sqft": 411,
            "sold_date": "2024-03-10",
            "days_on_market": 38,
            "lat": 32.8351,
            "lon": -96.7901,
        },
    ],
}


async def fetch_market_data(
    zip_code: str,
    date_from: str = None,
    date_to: str = None,
    property_type: str = "all"
) -> Dict[str, Any]:
    """
    Fetch market statistics for a DFW ZIP code.

    Args:
        zip_code: ZIP code to query (e.g., "75201")
        date_from: Start date for data range (optional)
        date_to: End date for data range (optional)
        property_type: Type of property (single_family, condo, townhome, all)

    Returns:
        Dictionary with market statistics
    """
    # Mock implementation - returns hardcoded data
    if zip_code in MOCK_MARKET_DATA:
        data = MOCK_MARKET_DATA[zip_code].copy()
        data["type"] = "market_data"
        data["property_type"] = property_type
        return data
    else:
        return {
            "type": "market_data",
            "zip_code": zip_code,
            "error": f"No data available for ZIP code {zip_code}",
            "available_zips": list(MOCK_MARKET_DATA.keys())
        }


async def get_comparable_sales(
    zip_code: str = None,
    beds_min: int = None,
    beds_max: int = None,
    price_min: float = None,
    price_max: float = None,
    sqft_min: int = None,
    sqft_max: int = None,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Retrieve comparable sold properties.

    Args:
        zip_code: ZIP code to search in
        beds_min: Minimum number of bedrooms
        beds_max: Maximum number of bedrooms
        price_min: Minimum price
        price_max: Maximum price
        sqft_min: Minimum square footage
        sqft_max: Maximum square footage
        limit: Maximum number of results

    Returns:
        Dictionary with comparable sales data
    """
    # Mock implementation
    if zip_code and zip_code in MOCK_COMPARABLE_SALES:
        properties = MOCK_COMPARABLE_SALES[zip_code].copy()

        # Apply filters
        if beds_min is not None:
            properties = [p for p in properties if p["beds"] >= beds_min]
        if beds_max is not None:
            properties = [p for p in properties if p["beds"] <= beds_max]
        if price_min is not None:
            properties = [p for p in properties if p["price"] >= price_min]
        if price_max is not None:
            properties = [p for p in properties if p["price"] <= price_max]
        if sqft_min is not None:
            properties = [p for p in properties if p["sqft"] >= sqft_min]
        if sqft_max is not None:
            properties = [p for p in properties if p["sqft"] <= sqft_max]

        properties = properties[:limit]

        return {
            "type": "comparable_sales",
            "zip_code": zip_code,
            "count": len(properties),
            "properties": properties,
            "visualization_hint": {
                "chart_type": "scatter",
                "x_axis": "sqft",
                "y_axis": "price"
            },
            "map_markers": [
                {"lat": prop["lat"], "lon": prop["lon"], "price": prop["price"]}
                for prop in properties
            ]
        }
    else:
        return {
            "type": "comparable_sales",
            "error": "ZIP code is required",
            "available_zips": list(MOCK_COMPARABLE_SALES.keys())
        }


# Tool definitions for Claude function calling
TOOLS = [
    {
        "name": "fetch_market_data",
        "description": "Fetch aggregate market statistics for a DFW ZIP code including median price, sales volume, days on market, and trends.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {
                    "type": "string",
                    "description": "The ZIP code to query (e.g., '75201' for Downtown Dallas)"
                },
                "date_from": {
                    "type": "string",
                    "description": "Start date for data range (optional, format: YYYY-MM-DD)"
                },
                "date_to": {
                    "type": "string",
                    "description": "End date for data range (optional, format: YYYY-MM-DD)"
                },
                "property_type": {
                    "type": "string",
                    "enum": ["single_family", "condo", "townhome", "all"],
                    "description": "Type of property to filter by"
                }
            },
            "required": ["zip_code"]
        }
    },
    {
        "name": "get_comparable_sales",
        "description": "Retrieve comparable sold properties based on location and filters like bedrooms, price range, and square footage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "zip_code": {
                    "type": "string",
                    "description": "ZIP code to search in"
                },
                "beds_min": {
                    "type": "integer",
                    "description": "Minimum number of bedrooms"
                },
                "beds_max": {
                    "type": "integer",
                    "description": "Maximum number of bedrooms"
                },
                "price_min": {
                    "type": "number",
                    "description": "Minimum price in dollars"
                },
                "price_max": {
                    "type": "number",
                    "description": "Maximum price in dollars"
                },
                "sqft_min": {
                    "type": "integer",
                    "description": "Minimum square footage"
                },
                "sqft_max": {
                    "type": "integer",
                    "description": "Maximum square footage"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 20
                }
            },
            "required": ["zip_code"]
        }
    }
]


# Map tool names to functions
TOOL_FUNCTIONS = {
    "fetch_market_data": fetch_market_data,
    "get_comparable_sales": get_comparable_sales,
}
