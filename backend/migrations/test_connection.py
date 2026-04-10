#!/usr/bin/env python3
"""Test Supabase connection and verify setup"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

def main():
    print("🔍 Testing Supabase connection...")
    print(f"   URL: {os.getenv('SUPABASE_URL')}")

    try:
        client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )

        print("\n✅ Connection successful!")

        # Test tables exist
        print("\n📊 Checking tables...")

        tables_to_check = ["properties", "market_stats", "chat_sessions", "chat_messages"]

        for table in tables_to_check:
            try:
                response = client.table(table).select("count").limit(1).execute()
                count_response = client.table(table).select("*", count="exact").limit(0).execute()
                count = count_response.count if hasattr(count_response, 'count') else 0
                print(f"   ✅ {table}: {count} records")
            except Exception as e:
                print(f"   ❌ {table}: Not found or error - {str(e)[:50]}")

        print("\n✨ Setup verification complete!")

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
