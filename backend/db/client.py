"""Supabase database client and query functions"""

import os
import re
import uuid as uuid_mod
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from supabase import create_client, Client


class SupabaseDB:
    """Supabase database client for DFW Realtor Agent"""

    def __init__(self):
        """Initialize Supabase client"""
        self.client: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )

    async def get_market_stats(
        self,
        zip_code: str,
        months: int = 12,
        property_type: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Get market statistics for a ZIP code

        Args:
            zip_code: ZIP code to query
            months: Number of months of historical data
            property_type: Type of property (single_family, condo, townhome, all)

        Returns:
            List of market statistics records
        """
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)

        query = (
            self.client.table("market_stats")
            .select("*")
            .eq("zip_code", zip_code)
            .eq("property_type", property_type)
            .gte("period", start_date.strftime("%Y-%m-%d"))
            .order("period", desc=True)
        )

        response = query.execute()
        return response.data

    async def get_comparable_sales(
        self,
        zip_code: Optional[str] = None,
        center_lat: Optional[float] = None,
        center_lon: Optional[float] = None,
        radius_miles: Optional[float] = None,
        beds_min: Optional[int] = None,
        beds_max: Optional[int] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        sqft_min: Optional[int] = None,
        sqft_max: Optional[int] = None,
        sold_within_days: Optional[int] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """
        Query comparable sold properties

        Args:
            zip_code: ZIP code to search in
            center_lat: Center latitude for radius search
            center_lon: Center longitude for radius search
            radius_miles: Radius in miles
            beds_min: Minimum bedrooms
            beds_max: Maximum bedrooms
            price_min: Minimum price
            price_max: Maximum price
            sqft_min: Minimum square footage
            sqft_max: Maximum square footage
            sold_within_days: Only properties sold within last N days
            limit: Maximum number of results

        Returns:
            Dictionary with properties and metadata
        """
        # Query all properties (county-sourced rows have status=NULL and are
        # still valid comparables via their sold_price/sold_date if present).
        query = (
            self.client.table("properties")
            .select("*")
        )

        # Apply filters
        if zip_code:
            query = query.eq("zip_code", zip_code)

        if beds_min is not None:
            query = query.gte("beds", beds_min)
        if beds_max is not None:
            query = query.lte("beds", beds_max)

        if price_min is not None:
            query = query.gte("sold_price", price_min)
        if price_max is not None:
            query = query.lte("sold_price", price_max)

        if sqft_min is not None:
            query = query.gte("sqft", sqft_min)
        if sqft_max is not None:
            query = query.lte("sqft", sqft_max)

        if sold_within_days is not None:
            cutoff_date = datetime.now() - timedelta(days=sold_within_days)
            query = query.gte("sold_date", cutoff_date.strftime("%Y-%m-%d"))

        query = query.order("sold_date", desc=True).limit(limit)

        response = query.execute()
        properties = response.data

        # Build map markers from the numeric lat/lon columns (populated by
        # migration 005). The GEOGRAPHY 'location' column comes back as hex
        # EWKB over REST and isn't directly usable client-side.
        map_markers = []
        for prop in properties:
            lat = prop.get("lat")
            lon = prop.get("lon")
            if lat is None or lon is None:
                continue
            price = prop.get("sold_price") or prop.get("price")
            appraised = prop.get("appraised_value")
            map_markers.append({
                "lat": float(lat),
                "lon": float(lon),
                "price": float(price) if price is not None else None,
                "appraised_value": float(appraised) if appraised is not None else None,
                "price_kind": "sold" if price else ("appraised" if appraised else None),
                "address": prop.get("address"),
                "beds": prop.get("beds"),
                "baths": float(prop["baths"]) if prop.get("baths") is not None else None,
                "sqft": prop.get("sqft"),
                "year_built": prop.get("year_built"),
                "source": prop.get("source"),
            })

        return {
            "type": "comparable_sales",
            "count": len(properties),
            "properties": properties,
            "map_markers": map_markers,
            "visualization_hint": {
                "chart_type": "scatter",
                "x_axis": "sqft",
                "y_axis": "sold_price"
            }
        }

    async def get_active_listings(
        self,
        zip_code: Optional[str] = None,
        beds_min: Optional[int] = None,
        beds_max: Optional[int] = None,
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get currently active listings"""
        query = (
            self.client.table("properties")
            .select("*")
            .eq("status", "active")
        )

        if zip_code:
            query = query.eq("zip_code", zip_code)
        if beds_min is not None:
            query = query.gte("beds", beds_min)
        if beds_max is not None:
            query = query.lte("beds", beds_max)
        if price_min is not None:
            query = query.gte("price", price_min)
        if price_max is not None:
            query = query.lte("price", price_max)

        query = query.order("list_date", desc=True).limit(limit)

        response = query.execute()
        return {
            "type": "active_listings",
            "count": len(response.data),
            "properties": response.data
        }

    # ---------- API response cache ----------

    async def save_api_response(
        self,
        provider: str,
        endpoint: str,
        cache_key: str,
        params: Dict[str, Any],
        response: Any,
        ttl_days: Optional[int] = None,
    ) -> None:
        expires_at = None
        if ttl_days is not None:
            expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        payload = {
            "provider": provider,
            "endpoint": endpoint,
            "cache_key": cache_key,
            "params": params,
            "response": response,
            "expires_at": expires_at,
        }
        self.client.table("api_responses").upsert(
            payload,
            on_conflict="provider,endpoint,cache_key",
        ).execute()

    async def fetch_api_response(
        self,
        provider: str,
        endpoint: str,
        cache_key: str,
    ) -> Optional[Dict[str, Any]]:
        result = (
            self.client.table("api_responses")
            .select("*")
            .eq("provider", provider)
            .eq("endpoint", endpoint)
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if row.get("expires_at"):
            expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expiry < datetime.now(expiry.tzinfo):
                return None
        return row

    # ---------- Budget accounting ----------

    async def get_or_create_budget_row(
        self,
        provider: str,
        period,
        monthly_limit: int,
    ) -> Dict[str, Any]:
        period_iso = period.isoformat()
        existing = (
            self.client.table("api_budget")
            .select("*")
            .eq("provider", provider)
            .eq("period", period_iso)
            .limit(1)
            .execute()
        )
        if existing.data:
            return existing.data[0]
        inserted = (
            self.client.table("api_budget")
            .insert({
                "provider": provider,
                "period": period_iso,
                "requests_used": 0,
                "monthly_limit": monthly_limit,
            })
            .execute()
        )
        return inserted.data[0]

    async def increment_budget(self, provider: str, period) -> Dict[str, Any]:
        return await self._adjust_budget(provider, period, delta=1)

    async def decrement_budget(self, provider: str, period) -> Dict[str, Any]:
        return await self._adjust_budget(provider, period, delta=-1)

    async def _adjust_budget(self, provider: str, period, delta: int) -> Dict[str, Any]:
        period_iso = period.isoformat()
        current = (
            self.client.table("api_budget")
            .select("*")
            .eq("provider", provider)
            .eq("period", period_iso)
            .limit(1)
            .execute()
        )
        if not current.data:
            raise RuntimeError(f"No budget row for {provider} @ {period_iso}")
        new_used = max(0, current.data[0]["requests_used"] + delta)
        updated = (
            self.client.table("api_budget")
            .update({"requests_used": new_used, "updated_at": datetime.utcnow().isoformat()})
            .eq("provider", provider)
            .eq("period", period_iso)
            .execute()
        )
        return updated.data[0]

    # ---------- Upserts for raw + normalized layers ----------

    async def upsert_county_parcel(self, parcel: Dict[str, Any]) -> None:
        self.client.table("county_parcels").upsert(
            parcel,
            on_conflict="county,account_num",
        ).execute()

    async def upsert_county_parcels(self, parcels: List[Dict[str, Any]]) -> None:
        """Batched version - single HTTP request per call. Preferred for bulk loads."""
        if not parcels:
            return
        self.client.table("county_parcels").upsert(
            parcels,
            on_conflict="county,account_num",
        ).execute()

    async def upsert_county_parcels_asyncpg(self, parcels: List[Dict[str, Any]]) -> None:
        """Direct-Postgres bulk upsert via asyncpg + DATABASE_URL.

        The Supabase REST/PostgREST path hangs on real-DCAD-scale payloads
        (large JSONB `raw` field × 200 rows). This bypasses REST entirely.
        """
        if not parcels:
            return
        import json
        import asyncpg
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL not set - required for asyncpg bulk upsert")
        conn = await asyncpg.connect(db_url)
        try:
            cols = [
                "county", "account_num", "situs_address", "situs_zip", "city",
                "land_use_code", "living_area_sqft", "land_sqft", "year_built",
                "bedrooms", "bathrooms", "total_appraised", "land_value",
                "improvement_value", "tax_year", "raw",
            ]
            placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("county", "account_num"))
            sql = (
                f"INSERT INTO county_parcels ({', '.join(cols)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT (county, account_num) DO UPDATE SET {updates}"
            )
            rows = [
                (
                    p["county"], p["account_num"], p["situs_address"], p["situs_zip"],
                    p["city"], p["land_use_code"], p["living_area_sqft"], p["land_sqft"],
                    p["year_built"], p["bedrooms"], p["bathrooms"],
                    p["total_appraised"], p["land_value"], p["improvement_value"],
                    p["tax_year"], json.dumps(p.get("raw")) if p.get("raw") is not None else None,
                )
                for p in parcels
            ]
            await conn.executemany(sql, rows)
        finally:
            await conn.close()

    async def upsert_property(self, prop: Dict[str, Any]) -> None:
        self.client.table("properties").upsert(
            prop,
            on_conflict="source,external_id",
        ).execute()

    async def upsert_market_stat(self, stat: Dict[str, Any]) -> None:
        self.client.table("market_stats").upsert(
            stat,
            on_conflict="zip_code,period,property_type",
        ).execute()

    # ---------- Enrichment cache ----------

    async def upsert_enrichment(
        self,
        source: str,
        cache_key: str,
        data: Dict[str, Any],
        ttl_days: Optional[int] = None,
    ) -> None:
        expires_at = None
        if ttl_days is not None:
            expires_at = (datetime.utcnow() + timedelta(days=ttl_days)).isoformat()
        self.client.table("enrichment_cache").upsert(
            {
                "source": source,
                "cache_key": cache_key,
                "data": data,
                "expires_at": expires_at,
            },
            on_conflict="source,cache_key",
        ).execute()

    async def fetch_enrichment(
        self,
        source: str,
        cache_key: str,
    ) -> Optional[Dict[str, Any]]:
        result = (
            self.client.table("enrichment_cache")
            .select("*")
            .eq("source", source)
            .eq("cache_key", cache_key)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        row = result.data[0]
        if row.get("expires_at"):
            expiry = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
            if expiry < datetime.now(expiry.tzinfo):
                return None
        return row["data"]

    # ------------------------------------------------------------------
    # Hermes memory (migration 007)
    # ------------------------------------------------------------------

    async def list_pins(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("pinned_properties")
            .select("*, properties(id, address, city, zip_code, beds, baths, sqft, "
                    "year_built, appraised_value, sold_price, price, lat, lon, source)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data

    async def upsert_pin(
        self, user_id: str, property_id: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        response = (
            self.client.table("pinned_properties")
            .upsert(
                {"user_id": user_id, "property_id": property_id, "note": note},
                on_conflict="user_id,property_id",
            )
            .execute()
        )
        return response.data[0]

    async def delete_pin(self, user_id: str, property_id: str) -> bool:
        response = (
            self.client.table("pinned_properties")
            .delete()
            .eq("user_id", user_id)
            .eq("property_id", property_id)
            .execute()
        )
        return len(response.data) > 0

    async def list_saved_searches(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("saved_searches")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return response.data

    async def get_saved_search(self, user_id: str, name: str) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("saved_searches")
            .select("*")
            .eq("user_id", user_id)
            .eq("name", name)
            .execute()
        )
        return response.data[0] if response.data else None

    async def upsert_saved_search(
        self,
        user_id: str,
        name: str,
        criteria: Dict[str, Any],
        client_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        response = (
            self.client.table("saved_searches")
            .upsert(
                {
                    "user_id": user_id,
                    "name": name,
                    "criteria": criteria,
                    "client_note": client_note,
                    "updated_at": datetime.now().isoformat(),
                },
                on_conflict="user_id,name",
            )
            .execute()
        )
        return response.data[0]

    async def touch_saved_search(self, user_id: str, name: str) -> None:
        (
            self.client.table("saved_searches")
            .update({"last_run_at": datetime.now().isoformat()})
            .eq("user_id", user_id)
            .eq("name", name)
            .execute()
        )

    async def delete_saved_search(self, user_id: str, name: str) -> bool:
        response = (
            self.client.table("saved_searches")
            .delete()
            .eq("user_id", user_id)
            .eq("name", name)
            .execute()
        )
        return len(response.data) > 0

    async def list_skills(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("skill_profile")
            .select("*")
            .eq("user_id", user_id)
            .order("concept")
            .execute()
        )
        return response.data

    async def upsert_skill(
        self, user_id: str, concept: str, level: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        """Agent observation: increments evidence; one observation never jumps
        straight to 'familiar' (needs >= 3 observations unless already there)."""
        existing = (
            self.client.table("skill_profile")
            .select("*")
            .eq("user_id", user_id)
            .eq("concept", concept)
            .execute()
        ).data
        evidence = (existing[0]["evidence_count"] + 1) if existing else 1
        prev_level = existing[0]["level"] if existing else None
        if level == "familiar" and prev_level != "familiar" and evidence < 3:
            level = "learning"
        response = (
            self.client.table("skill_profile")
            .upsert(
                {
                    "user_id": user_id,
                    "concept": concept,
                    "level": level,
                    "evidence_count": evidence,
                    "notes": note,
                    "last_observed_at": datetime.now().isoformat(),
                },
                on_conflict="user_id,concept",
            )
            .execute()
        )
        return response.data[0]

    async def set_skill_level(self, user_id: str, concept: str, level: str) -> Dict[str, Any]:
        """User correction from the panel: sets level directly, no evidence math."""
        response = (
            self.client.table("skill_profile")
            .upsert(
                {"user_id": user_id, "concept": concept, "level": level,
                 "notes": "set by user"},
                on_conflict="user_id,concept",
            )
            .execute()
        )
        return response.data[0]

    async def delete_skill(self, user_id: str, concept: str) -> bool:
        response = (
            self.client.table("skill_profile")
            .delete()
            .eq("user_id", user_id)
            .eq("concept", concept)
            .execute()
        )
        return len(response.data) > 0

    async def get_data_coverage(self) -> List[Dict[str, Any]]:
        response = self.client.table("data_coverage").select("*").execute()
        return response.data

    async def get_zip_boundaries(self) -> List[Dict[str, Any]]:
        response = self.client.table("zip_boundaries").select("*").execute()
        return response.data

    async def upsert_zip_boundary(self, zip_code: str, boundary: Dict[str, Any]) -> None:
        (
            self.client.table("zip_boundaries")
            .upsert({"zip": zip_code, "boundary": boundary}, on_conflict="zip")
            .execute()
        )

    async def find_property_by_address(
        self, query: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Resolve a pin target. UUID fast-path, else normalized ILIKE match."""
        try:
            uuid_mod.UUID(query)
            response = (
                self.client.table("properties").select("*").eq("id", query).execute()
            )
            return response.data
        except (ValueError, AttributeError, TypeError):
            pass
        normalized = re.sub(r"[.,#]", "", (query or "").upper())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if not normalized:
            return []
        response = (
            self.client.table("properties")
            .select("*")
            .ilike("address", f"%{normalized}%")
            .limit(limit)
            .execute()
        )
        return response.data

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            response = self.client.table("properties").select("count").limit(1).execute()
            return True
        except Exception as e:
            print(f"Database connection test failed: {e}")
            return False


class _LazyDB:
    """Lazy proxy for the SupabaseDB singleton.

    Defers real client creation until first attribute access, so importing
    this module (e.g. from tests that mock the DB) doesn't require live
    Supabase credentials.
    """

    _instance = None

    def _get(self):
        if self._instance is None:
            self._instance = SupabaseDB()
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get(), name)


# Global database instance (lazy)
db = _LazyDB()
