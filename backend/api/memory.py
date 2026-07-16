"""REST CRUD backing the Hermes Knows panel + coverage endpoint.

Panel actions hit these directly (no LLM round-trip); Hermes sees the
changes on the next turn's memory load.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.client import db
from backend.hermes import HERMES_USER_ID

router = APIRouter(prefix="/api", tags=["memory"])


class PinCreate(BaseModel):
    property_id: str
    note: Optional[str] = None


class SearchUpsert(BaseModel):
    name: str
    criteria: Dict[str, Any]
    client_note: Optional[str] = None


class SkillPut(BaseModel):
    level: str  # novice | learning | familiar


@router.get("/memory/pins")
async def get_pins():
    return await db.list_pins(HERMES_USER_ID)


@router.post("/memory/pins")
async def create_pin(body: PinCreate):
    return await db.upsert_pin(HERMES_USER_ID, body.property_id, body.note)


@router.delete("/memory/pins/{property_id}")
async def remove_pin(property_id: str):
    if not await db.delete_pin(HERMES_USER_ID, property_id):
        raise HTTPException(status_code=404, detail="pin not found")
    return {"deleted": property_id}


@router.get("/memory/searches")
async def get_searches():
    return await db.list_saved_searches(HERMES_USER_ID)


@router.post("/memory/searches")
async def upsert_search(body: SearchUpsert):
    return await db.upsert_saved_search(
        HERMES_USER_ID, body.name, body.criteria, body.client_note
    )


@router.delete("/memory/searches/{name:path}")
async def remove_search(name: str):
    # `:path` converter so names containing "/" survive routing. Frontend must
    # URI-encode the name (encodeURIComponent / quote(name, safe="")) before
    # interpolating into the URL -- the encoded %2F form is decoded correctly
    # here, whereas a raw unescaped "/" would be split into extra segments.
    if not await db.delete_saved_search(HERMES_USER_ID, name):
        raise HTTPException(status_code=404, detail="saved search not found")
    return {"deleted": name}


@router.get("/memory/skills")
async def get_skills():
    return await db.list_skills(HERMES_USER_ID)


@router.put("/memory/skills/{concept:path}")
async def put_skill(concept: str, body: SkillPut):
    if body.level not in ("novice", "learning", "familiar"):
        raise HTTPException(status_code=422, detail="level must be novice|learning|familiar")
    return await db.set_skill_level(HERMES_USER_ID, concept, body.level)


@router.delete("/memory/skills/{concept:path}")
async def remove_skill(concept: str):
    if not await db.delete_skill(HERMES_USER_ID, concept):
        raise HTTPException(status_code=404, detail="skill not found")
    return {"deleted": concept}


@router.get("/coverage")
async def get_coverage():
    coverage = await db.get_data_coverage()
    boundaries = await db.get_zip_boundaries()
    return {"coverage": coverage, "boundaries": [b["boundary"] for b in boundaries]}
