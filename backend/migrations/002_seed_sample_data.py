#!/usr/bin/env python3
"""
Generate realistic sample data for DFW real estate properties
Run this after creating the schema
"""

import os
import sys
import random
from datetime import datetime, timedelta
from decimal import Decimal

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

# DFW ZIP codes with realistic data
DFW_AREAS = {
    "75201": {  # Downtown Dallas
        "city": "Dallas",
        "area_name": "Downtown Dallas",
        "lat_center": 32.7831,
        "lon_center": -96.7969,
        "price_range": (250000, 600000),
        "sqft_range": (800, 2200),
        "property_types": ["condo", "townhome"],
    },
    "75205": {  # Highland Park
        "city": "Highland Park",
        "area_name": "Highland Park",
        "lat_center": 32.8336,
        "lon_center": -96.7880,
        "price_range": (800000, 2500000),
        "sqft_range": (2500, 5000),
        "property_types": ["single_family"],
    },
    "75219": {  # Uptown Dallas
        "city": "Dallas",
        "area_name": "Uptown Dallas",
        "lat_center": 32.8067,
        "lon_center": -96.8014,
        "price_range": (300000, 800000),
        "sqft_range": (900, 2500),
        "property_types": ["condo", "townhome"],
    },
    "75024": {  # Plano
        "city": "Plano",
        "area_name": "Plano",
        "lat_center": 33.0198,
        "lon_center": -96.6989,
        "price_range": (350000, 650000),
        "sqft_range": (1800, 3500),
        "property_types": ["single_family"],
    },
    "75025": {  # Plano West
        "city": "Plano",
        "area_name": "West Plano",
        "lat_center": 33.0390,
        "lon_center": -96.8236,
        "price_range": (400000, 850000),
        "sqft_range": (2200, 4200),
        "property_types": ["single_family"],
    },
    "75034": {  # Frisco
        "city": "Frisco",
        "area_name": "Frisco",
        "lat_center": 33.1507,
        "lon_center": -96.8236,
        "price_range": (400000, 750000),
        "sqft_range": (2000, 4000),
        "property_types": ["single_family"],
    },
}

STREET_NAMES = [
    "Main St", "Elm St", "Oak Ave", "Maple Dr", "Cedar Ln", "Pine Ct",
    "Commerce St", "McKinney Ave", "Ross Ave", "Live Oak St", "Pecan Dr",
    "Mockingbird Ln", "Preston Rd", "Hillcrest Ave", "University Blvd"
]


def generate_properties(count_per_zip=30):
    """Generate sample properties"""
    properties = []

    for zip_code, area in DFW_AREAS.items():
        for i in range(count_per_zip):
            # Random location near center (±0.02 degrees ~2km)
            lat = area["lat_center"] + random.uniform(-0.02, 0.02)
            lon = area["lon_center"] + random.uniform(-0.02, 0.02)

            # Property details
            sqft = random.randint(*area["sqft_range"])
            price = random.randint(*area["price_range"])
            price_per_sqft = round(price / sqft, 2)

            beds = random.choice([2, 2, 3, 3, 3, 4, 4, 5])
            baths = random.choice([1.5, 2, 2, 2.5, 3, 3.5, 4])
            year_built = random.randint(1990, 2024)

            property_type = random.choice(area["property_types"])

            # Random sold date in last 12 months
            days_ago = random.randint(0, 365)
            sold_date = datetime.now() - timedelta(days=days_ago)
            list_date = sold_date - timedelta(days=random.randint(15, 60))

            days_on_market = (sold_date - list_date).days

            # Some properties are still active
            status = "sold" if random.random() > 0.15 else "active"

            property_data = {
                "mls_id": f"DFW{zip_code}{i:03d}",
                "address": f"{random.randint(100, 9999)} {random.choice(STREET_NAMES)}",
                "city": area["city"],
                "zip_code": zip_code,
                "location": f"POINT({lon} {lat})",
                "price": price if status == "active" else None,
                "sold_price": price if status == "sold" else None,
                "beds": beds,
                "baths": float(baths),
                "sqft": sqft,
                "lot_size_acres": round(random.uniform(0.1, 0.5), 3),
                "year_built": year_built,
                "property_type": property_type,
                "status": status,
                "list_date": list_date.strftime("%Y-%m-%d"),
                "sold_date": sold_date.strftime("%Y-%m-%d") if status == "sold" else None,
                "days_on_market": days_on_market if status == "sold" else None,
                "price_per_sqft": float(price_per_sqft),
                "description": f"Beautiful {beds}BR/{baths}BA {property_type} in {area['area_name']}"
            }

            properties.append(property_data)

    return properties


def generate_market_stats():
    """Generate monthly market statistics"""
    stats = []

    # Last 12 months of data
    for zip_code, area in DFW_AREAS.items():
        for months_ago in range(12):
            period = datetime.now() - timedelta(days=months_ago * 30)
            period_date = period.replace(day=1).strftime("%Y-%m-%d")

            # Simulate price trends (slight growth over time)
            base_price = (area["price_range"][0] + area["price_range"][1]) / 2
            trend_multiplier = 1 + (months_ago * -0.005)  # Older = slightly cheaper

            median_price = int(base_price * trend_multiplier)
            avg_price = int(median_price * 1.15)

            stat = {
                "zip_code": zip_code,
                "period": period_date,
                "property_type": "all",
                "median_price": float(median_price),
                "avg_price": float(avg_price),
                "sales_volume": random.randint(15, 50),
                "avg_days_on_market": float(random.randint(20, 45)),
                "median_list_to_sale_ratio": float(round(random.uniform(0.96, 1.02), 4)),
                "median_price_per_sqft": float(round(median_price / 2000, 2)),
                "active_listings_count": random.randint(40, 120)
            }
            stats.append(stat)

    return stats


def main():
    """Main seeding function"""
    print("🌱 Seeding DFW real estate data...")

    try:
        # Generate data
        print("\n📊 Generating properties...")
        properties = generate_properties(count_per_zip=30)
        print(f"   Generated {len(properties)} properties")

        print("\n📈 Generating market statistics...")
        market_stats = generate_market_stats()
        print(f"   Generated {len(market_stats)} market stat records")

        # Insert properties
        print("\n💾 Inserting properties into database...")
        batch_size = 50
        for i in range(0, len(properties), batch_size):
            batch = properties[i:i + batch_size]
            response = supabase.table("properties").insert(batch).execute()
            print(f"   Inserted batch {i//batch_size + 1}/{(len(properties)-1)//batch_size + 1}")

        # Insert market stats
        print("\n💾 Inserting market statistics...")
        for i in range(0, len(market_stats), batch_size):
            batch = market_stats[i:i + batch_size]
            response = supabase.table("market_stats").insert(batch).execute()
            print(f"   Inserted batch {i//batch_size + 1}/{(len(market_stats)-1)//batch_size + 1}")

        print("\n✅ Sample data seeded successfully!")
        print(f"\n📍 Available ZIP codes: {', '.join(DFW_AREAS.keys())}")
        print(f"   Total properties: {len(properties)}")
        print(f"   Total market stats: {len(market_stats)}")

    except Exception as e:
        print(f"\n❌ Error seeding data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
