"""Hermes memory tools: pins, saved searches, skill observations, canvas, coverage.

Every tool returns a dict with a 'type' key - the frontend widget reducer
maps types to widgets. Errors come back as strings for the agent to relay;
tools never raise into the graph.
"""
import re
from typing import Any, Dict, Optional

from backend.db.client import db
from backend.hermes import HERMES_USER_ID

# get_comparable_sales kwargs a saved search may carry
_SEARCH_KEYS = {
    "zip_code", "beds_min", "beds_max", "price_min", "price_max",
    "sqft_min", "sqft_max", "limit",
}


def _normalize_concept(concept: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (concept or "").lower())
    return s.strip("_")


async def pin_property(address_or_id: str, note: Optional[str] = None) -> Dict[str, Any]:
    try:
        matches = await db.find_property_by_address(address_or_id)
        if not matches:
            return {
                "type": "pin_update",
                "error": f"No property found matching '{address_or_id}'. "
                         "Ask the user to clarify the address.",
            }
        if len(matches) > 1:
            return {
                "type": "pin_update",
                "error": "Multiple properties match - ask the user which one.",
                "candidates": [
                    {"id": m["id"], "address": m["address"], "zip_code": m.get("zip_code")}
                    for m in matches
                ],
            }
        prop = matches[0]
        await db.upsert_pin(HERMES_USER_ID, prop["id"], note)
        return {"type": "pin_update", "action": "pinned", "property": prop, "note": note}
    except Exception as exc:
        return {"type": "pin_update", "error": str(exc)}


async def unpin_property(address_or_id: str) -> Dict[str, Any]:
    try:
        matches = await db.find_property_by_address(address_or_id)
        if len(matches) != 1:
            return {
                "type": "pin_update",
                "error": f"Could not uniquely resolve '{address_or_id}' "
                         f"({len(matches)} matches).",
            }
        removed = await db.delete_pin(HERMES_USER_ID, matches[0]["id"])
        if not removed:
            return {"type": "pin_update", "error": "That property was not pinned."}
        return {"type": "pin_update", "action": "unpinned", "property": matches[0]}
    except Exception as exc:
        return {"type": "pin_update", "error": str(exc)}


async def save_search(
    name: str, criteria: Dict[str, Any], client_note: Optional[str] = None
) -> Dict[str, Any]:
    try:
        coverage = await db.get_data_coverage()
        covered = {c["zip"] for c in coverage}
        warning = None
        zip_code = (criteria or {}).get("zip_code")
        if zip_code and zip_code not in covered:
            warning = (
                f"zip {zip_code} is outside current coverage "
                f"({', '.join(sorted(covered))}) - the search will return no rows"
            )
        row = await db.upsert_saved_search(HERMES_USER_ID, name, criteria, client_note)
        return {"type": "saved_search_update", "action": "saved",
                "search": row, "warning": warning}
    except Exception as exc:
        return {"type": "saved_search_update", "error": str(exc)}


async def run_saved_search(name: str) -> Dict[str, Any]:
    try:
        search = await db.get_saved_search(HERMES_USER_ID, name)
        if not search:
            names = [s["name"] for s in await db.list_saved_searches(HERMES_USER_ID)]
            return {
                "type": "saved_search_update",
                "error": f"No saved search named '{name}'. Saved searches: {names}",
            }
        kwargs = {k: v for k, v in (search.get("criteria") or {}).items()
                  if k in _SEARCH_KEYS}
        result = await db.get_comparable_sales(**kwargs)
        await db.touch_saved_search(HERMES_USER_ID, name)
        result["saved_search_name"] = name
        return result
    except Exception as exc:
        return {"type": "saved_search_update", "error": str(exc)}


async def record_skill_observation(
    concept: str, level: str, note: Optional[str] = None
) -> Dict[str, Any]:
    try:
        normalized = _normalize_concept(concept)
        if not normalized or level not in ("novice", "learning", "familiar"):
            return {"type": "skill_update",
                    "error": f"invalid concept/level: {concept!r}/{level!r}"}
        row = await db.upsert_skill(HERMES_USER_ID, normalized, level, note)
        return {"type": "skill_update", "skill": row}
    except Exception as exc:
        return {"type": "skill_update", "error": str(exc)}


async def dismiss_widget(widget_key: str) -> Dict[str, Any]:
    return {"type": "widget_dismiss", "widget_key": widget_key}


async def get_data_coverage() -> Dict[str, Any]:
    try:
        coverage = await db.get_data_coverage()
        boundaries = await db.get_zip_boundaries()
        return {
            "type": "data_coverage",
            "coverage": coverage,
            "boundaries": [b["boundary"] for b in boundaries],
            "notes": (
                "Texas is a non-disclosure state: sold prices exist only for the "
                "RentCast-sourced subset; DCAD appraised values are public."
            ),
        }
    except Exception as exc:
        return {"type": "data_coverage", "error": str(exc)}


MEMORY_TOOLS = [
    {
        "name": "pin_property",
        "description": (
            "Pin a property to the user's persistent workspace. Resolves the address "
            "first; if it is ambiguous or unmatched you get an error to relay - never guess."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "address_or_id": {"type": "string",
                                  "description": "Street address or property UUID"},
                "note": {"type": "string",
                         "description": "Optional note, e.g. 'the Johnsons liked this one'"},
            },
            "required": ["address_or_id"],
        },
    },
    {
        "name": "unpin_property",
        "description": "Remove a pinned property from the user's workspace.",
        "input_schema": {
            "type": "object",
            "properties": {
                "address_or_id": {"type": "string",
                                  "description": "Street address or property UUID"},
            },
            "required": ["address_or_id"],
        },
    },
    {
        "name": "save_search",
        "description": (
            "Save/update a named search (criteria = get_comparable_sales filters). "
            "OFFER to save when the user repeats criteria - never save silently. "
            "A search named for a client ('Johnsons') acts as their profile."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short unique name, e.g. 'Johnsons'"},
                "criteria": {
                    "type": "object",
                    "description": "Filter keys: zip_code, beds_min, beds_max, price_min, "
                                   "price_max, sqft_min, sqft_max, limit",
                },
                "client_note": {"type": "string",
                                "description": "Optional client context"},
            },
            "required": ["name", "criteria"],
        },
    },
    {
        "name": "run_saved_search",
        "description": "Run a saved search by name and return comparable sales.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "record_skill_observation",
        "description": (
            "Record what the user knows. Call when they ask what a concept means "
            "(novice), engage with an explanation (learning), or use a term correctly "
            "unprompted (familiar). Concepts: comps, days_on_market, absorption_rate, "
            "price_per_sqft, appraised_vs_market, contingency, escrow - or others you observe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "concept": {"type": "string"},
                "level": {"type": "string", "enum": ["novice", "learning", "familiar"]},
                "note": {"type": "string", "description": "What you observed"},
            },
            "required": ["concept", "level"],
        },
    },
    {
        "name": "dismiss_widget",
        "description": (
            "Remove a stale widget from the user's canvas when the conversation moves on. "
            "Keys are content-derived: map:<zip>, table:<zip>, trend:<zip>, "
            "card:<property_id>, coverage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"widget_key": {"type": "string"}},
            "required": ["widget_key"],
        },
    },
    {
        "name": "get_data_coverage",
        "description": (
            "Return the live bounds of available data (counties, zips, parcel counts, "
            "freshness) with zip boundary polygons. Call when the user asks what data "
            "you have, or when their question falls outside coverage - show, don't apologize."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

MEMORY_TOOL_FUNCTIONS = {
    "pin_property": pin_property,
    "unpin_property": unpin_property,
    "save_search": save_search,
    "run_saved_search": run_saved_search,
    "record_skill_observation": record_skill_observation,
    "dismiss_widget": dismiss_widget,
    "get_data_coverage": get_data_coverage,
}
