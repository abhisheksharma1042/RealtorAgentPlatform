"""Per-turn memory + coverage block injected into the system prompt.

All memory loads whole every turn - it is dozens of rows for a single
user, so there is no retrieval step and behavior is deterministic. The
scale-up path (episodic user_memory + pgvector) is additive and touches
none of this.
"""
import logging

from backend.db.client import db
from backend.hermes import HERMES_USER_ID

logger = logging.getLogger(__name__)


async def build_memory_block(user_id: str = HERMES_USER_ID) -> str:
    try:
        pins = await db.list_pins(user_id)
        searches = await db.list_saved_searches(user_id)
        skills = await db.list_skills(user_id)
        coverage = await db.get_data_coverage()

        lines: list[str] = [
            "", "",
            "# Hermes context (loaded from memory - trust this over inference)",
        ]

        # MVP(multi-user): collapse newlines + cap length of user-authored strings
        # (notes, search names) before interpolation - they land in the system prompt.
        if searches:
            lines.append("## Saved searches (rerun with run_saved_search)")
            for s in searches:
                crit = ", ".join(f"{k}={v}" for k, v in (s.get("criteria") or {}).items())
                note = f" - client note: {s['client_note']}" if s.get("client_note") else ""
                lines.append(f'- "{s["name"]}": {crit}{note}')

        if pins:
            lines.append("## Pinned properties")
            for p in pins:
                prop = p.get("properties") or {}
                note = f' - note: "{p["note"]}"' if p.get("note") else ""
                lines.append(f"- {prop.get('address')} ({prop.get('zip_code')}){note}")

        if skills:
            plain = [s["concept"] for s in skills if s["level"] in ("novice", "learning")]
            terse = [s["concept"] for s in skills if s["level"] == "familiar"]
            lines.append("## User skill profile (user-corrected levels are authoritative)")
            if plain:
                lines.append(f"- Explain plainly on first use: {', '.join(plain)}")
            if terse:
                lines.append(f"- Familiar - do NOT re-explain: {', '.join(terse)}")

        lines.append("## Data coverage (hard bounds - never claim data outside this)")
        if coverage:
            counties = sorted({c["county"] for c in coverage if c.get("county")})
            zips = sorted({c["zip"] for c in coverage if c.get("zip")})
            total = sum(c.get("parcel_count") or 0 for c in coverage)
            year = max((c.get("appraisal_year") or 0) for c in coverage)
            lines.append(
                f"- Counties: {', '.join(counties)} | Zips: {', '.join(zips)} | "
                f"{total:,} parcels | {year} appraisal roll"
            )
        else:
            lines.append("- No coverage rows found - treat all data claims cautiously")
        lines.append(
            "- Texas is a non-disclosure state: sold prices exist only for a small "
            "RentCast-sourced subset; DCAD appraised values are the public fallback signal."
        )
        return "\n".join(lines)
    except Exception:
        logger.warning("Hermes memory load failed; running without memory", exc_info=True)
        return (
            "\n\n[Memory unavailable this turn - do not reference pins, saved "
            "searches, or the user's skill profile. Data coverage is unknown "
            "this turn - do not assert what data exists. Texas is a "
            "non-disclosure state: sold prices exist only for a small "
            "RentCast-sourced subset; DCAD appraised values are the public "
            "fallback signal.]"
        )
