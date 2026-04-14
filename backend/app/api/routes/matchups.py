"""
matchups.py — Champion matchup data import and query routes.

Endpoints
---------
POST /matchups/import/csv
    Upload a CSV file of manually-researched champion vs. champion win rates.
    Validates champion names against DDragon, deduplicates by (a, b, role),
    and stores results in the champion_matchups table.

GET /matchups/
    Query stored matchups with optional filters (champion_a_id, role, source).

GET /matchups/{champion_id}/counters
    Return the top-N champions that beat this champion, per role.

GET /matchups/{champion_id}/favors
    Return the top-N champions that this champion beats, per role.
"""

import csv
import io
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import desc, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.champion_matchups import ChampionMatchup
from app.services.ddragon import get_champion_map, get_champion_full_map

_MIGRATION_HINT = (
    "The champion_matchups table does not exist yet. "
    "Run the migration first: "
    "psql $PRISMA_DATABASE_URL -f backend/prisma/migrations/0002_champion_matchups/migration.sql"
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/matchups", tags=["matchups"])

_VALID_ROLES = {"TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"}
_VALID_SOURCES = {"lolalytics", "opgg", "ugg"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _confidence(games: int) -> str:
    """Tier label based on sample size."""
    if games >= 30:
        return "high"
    if games >= 10:
        return "medium"
    return "low"


def _bayesian_smooth(win_rate: float, games: int, prior: float = 0.5, weight: int = 20) -> float:
    """
    Bayesian shrinkage toward a neutral 50% prior.
    The effective sample weight is 20 games — small samples are pulled strongly
    toward 0.5; large samples are barely affected.
    """
    return (win_rate * games + prior * weight) / (games + weight)


# ---------------------------------------------------------------------------
# POST /matchups/import/csv
# ---------------------------------------------------------------------------

@router.post("/import/csv", summary="Import champion matchup data from a CSV file")
async def import_matchup_csv(
    file: UploadFile = File(..., description="CSV file with champion matchup rows"),
    overwrite: bool = Query(False, description="Replace existing rows for the same champion pair + role"),
    dry_run:   bool = Query(False, description="Validate and preview without saving"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Upload a CSV of manually-researched champion matchup data.

    Expected columns (header row required):
        champion_a, champion_b, role, win_rate_a_vs_b, games_played,
        patch (optional), source (optional), notes (optional)

    champion_a / champion_b must exactly match DDragon display names
    (e.g. "Wukong", "Nunu & Willump", "Renata Glasc").

    win_rate_a_vs_b must be a decimal fraction (0.0 – 1.0), NOT a percentage.

    Returns a summary of imported, skipped, and invalid rows.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Uploaded file must be a .csv file.")

    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")  # strip BOM if present
    except UnicodeDecodeError:
        raise HTTPException(status_code=422, detail="Could not decode file as UTF-8. Save your CSV as UTF-8 and re-upload.")

    # Build name → id lookup from DDragon
    champ_full_map = await get_champion_full_map()     # {id_int: ChampionMeta}
    name_to_id: Dict[str, int] = {
        meta["name"]: meta["id"]
        for meta in champ_full_map.values()
    }

    reader = csv.DictReader(io.StringIO(text))
    required_cols = {"champion_a", "champion_b", "role", "win_rate_a_vs_b", "games_played"}
    if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
        missing = required_cols - set(reader.fieldnames or [])
        raise HTTPException(
            status_code=422,
            detail=f"CSV is missing required columns: {', '.join(sorted(missing))}. "
                   f"Expected: champion_a, champion_b, role, win_rate_a_vs_b, games_played "
                   f"(plus optional: patch, source, notes)",
        )

    imported = 0
    skipped_duplicates = 0
    invalid_rows: List[Dict[str, Any]] = []
    to_upsert: List[Dict[str, Any]] = []

    for i, raw_row in enumerate(reader, start=2):  # start=2 because row 1 is header
        row_num = i
        errors = []

        # --- Validate champion names ---
        name_a = (raw_row.get("champion_a") or "").strip()
        name_b = (raw_row.get("champion_b") or "").strip()
        id_a = name_to_id.get(name_a)
        id_b = name_to_id.get(name_b)

        if not name_a:
            errors.append("champion_a is empty")
        elif id_a is None:
            errors.append(f"champion_a '{name_a}' not found in DDragon — check spelling and capitalisation")

        if not name_b:
            errors.append("champion_b is empty")
        elif id_b is None:
            errors.append(f"champion_b '{name_b}' not found in DDragon — check spelling and capitalisation")

        # --- Validate role ---
        role_raw = (raw_row.get("role") or "").strip().upper()
        if role_raw not in _VALID_ROLES:
            errors.append(f"role '{role_raw}' is invalid — must be one of: {', '.join(sorted(_VALID_ROLES))}")

        # --- Validate win_rate_a_vs_b ---
        wr_raw = (raw_row.get("win_rate_a_vs_b") or "").strip()
        win_rate: Optional[float] = None
        try:
            win_rate = float(wr_raw)
            if not (0.0 <= win_rate <= 1.0):
                errors.append(
                    f"win_rate_a_vs_b {win_rate} is out of range (0.0 – 1.0). "
                    "If you entered a percentage (e.g. 52.4), divide by 100."
                )
        except (ValueError, TypeError):
            errors.append(f"win_rate_a_vs_b '{wr_raw}' is not a valid number")

        # --- Validate games_played ---
        gp_raw = (raw_row.get("games_played") or "").strip()
        games_played: Optional[int] = None
        try:
            games_played = int(float(gp_raw))
            if games_played < 0:
                errors.append("games_played must be a non-negative integer")
        except (ValueError, TypeError):
            errors.append(f"games_played '{gp_raw}' is not a valid integer")

        # --- Validate optional fields ---
        source_raw = (raw_row.get("source") or "").strip().lower() or None
        if source_raw and source_raw not in _VALID_SOURCES:
            # Warn but don't reject — just store as-is
            logger.warning("Row %d: unknown source '%s' (expected lolalytics|opgg|ugg)", row_num, source_raw)

        patch_raw = (raw_row.get("patch") or "").strip() or None
        notes_raw = (raw_row.get("notes") or "").strip() or None

        if errors:
            invalid_rows.append({"row": row_num, "error": "; ".join(errors)})
            continue

        # All validations passed
        assert id_a is not None and id_b is not None
        assert win_rate is not None and games_played is not None

        to_upsert.append({
            "champion_a_id":    id_a,
            "champion_b_id":    id_b,
            "champion_a_name":  name_a,
            "champion_b_name":  name_b,
            "role":             role_raw,
            "win_rate_a_vs_b":  win_rate,
            "games_played":     games_played,
            "confidence":       _confidence(games_played),
            "patch":            patch_raw,
            "source":           source_raw,
            "notes":            notes_raw,
        })

    # --- Dry run: return preview without persisting ---
    if dry_run:
        return {
            "dry_run":               True,
            "rows_valid":            len(to_upsert),
            "rows_invalid":          len(invalid_rows),
            "invalid_details":       invalid_rows,
            "preview": [
                {
                    "champion_a": r["champion_a_name"],
                    "champion_b": r["champion_b_name"],
                    "role":       r["role"],
                    "win_rate":   r["win_rate_a_vs_b"],
                    "games":      r["games_played"],
                    "confidence": r["confidence"],
                }
                for r in to_upsert[:20]  # cap preview at 20 rows
            ],
        }

    # --- Persist: single bulk upsert — avoids N round-trips to Supabase ---
    # One INSERT ... ON CONFLICT statement handles all rows in one DB call,
    # which is critical for large CSVs (860 rows × ~100ms Supabase RTT = timeout).
    confidence_breakdown: Dict[str, int] = {"high": 0, "medium": 0, "low": 0}

    if to_upsert:
        stmt = pg_insert(ChampionMatchup).values(to_upsert)

        # Use index_elements (column names) instead of constraint name —
        # avoids relying on Supabase preserving the exact constraint name.
        _conflict_cols = ["champion_a_id", "champion_b_id", "role"]

        if overwrite:
            # ON CONFLICT DO UPDATE — replace every field except the PK
            stmt = stmt.on_conflict_do_update(
                index_elements=_conflict_cols,
                set_={
                    "champion_a_name":  stmt.excluded.champion_a_name,
                    "champion_b_name":  stmt.excluded.champion_b_name,
                    "win_rate_a_vs_b":  stmt.excluded.win_rate_a_vs_b,
                    "games_played":     stmt.excluded.games_played,
                    "confidence":       stmt.excluded.confidence,
                    "patch":            stmt.excluded.patch,
                    "source":           stmt.excluded.source,
                    "notes":            stmt.excluded.notes,
                },
            )
            imported = len(to_upsert)
        else:
            # ON CONFLICT DO NOTHING — skip existing pairs silently
            stmt = stmt.on_conflict_do_nothing(
                index_elements=_conflict_cols,
            )
            # Count actual inserts by checking what existed before
            existing_keys = {
                (r.champion_a_id, r.champion_b_id, r.role)
                for r in db.query(
                    ChampionMatchup.champion_a_id,
                    ChampionMatchup.champion_b_id,
                    ChampionMatchup.role,
                ).all()
            }
            imported = sum(
                1 for r in to_upsert
                if (r["champion_a_id"], r["champion_b_id"], r["role"]) not in existing_keys
            )
            skipped_duplicates = len(to_upsert) - imported

        db.execute(stmt)
        db.commit()

        for r in to_upsert:
            confidence_breakdown[r["confidence"]] = confidence_breakdown.get(r["confidence"], 0) + 1

    logger.info(
        "Matchup CSV import: %d imported, %d skipped duplicates, %d invalid",
        imported, skipped_duplicates, len(invalid_rows),
    )

    return {
        "imported":             imported,
        "skipped_duplicates":   skipped_duplicates,
        "invalid_rows":         len(invalid_rows),
        "invalid_details":      invalid_rows,
        "confidence_breakdown": confidence_breakdown,
        "overwrite_mode":       overwrite,
    }


# ---------------------------------------------------------------------------
# GET /matchups/
# ---------------------------------------------------------------------------

@router.get("/", summary="Query stored champion matchup rows")
async def list_matchups(
    champion_a_id: Optional[int]  = Query(None, description="Filter by champion A's Riot numeric ID"),
    champion_b_id: Optional[int]  = Query(None, description="Filter by champion B's Riot numeric ID"),
    role:          Optional[str]  = Query(None, description="Filter by role (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY)"),
    source:        Optional[str]  = Query(None, description="Filter by data source (lolalytics/opgg/ugg)"),
    confidence:    Optional[str]  = Query(None, description="Filter by confidence tier (high/medium/low)"),
    limit:         int            = Query(50,   ge=1, le=500),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return stored matchup rows with optional filters."""
    query = db.query(ChampionMatchup)

    if champion_a_id is not None:
        query = query.filter(ChampionMatchup.champion_a_id == champion_a_id)
    if champion_b_id is not None:
        query = query.filter(ChampionMatchup.champion_b_id == champion_b_id)
    if role:
        query = query.filter(ChampionMatchup.role == role.upper())
    if source:
        query = query.filter(ChampionMatchup.source == source.lower())
    if confidence:
        query = query.filter(ChampionMatchup.confidence == confidence.lower())

    total = query.count()
    rows = query.order_by(desc(ChampionMatchup.games_played)).limit(limit).all()

    return {
        "total":  total,
        "limit":  limit,
        "rows": [
            {
                "id":               r.id,
                "champion_a_id":    r.champion_a_id,
                "champion_a_name":  r.champion_a_name,
                "champion_b_id":    r.champion_b_id,
                "champion_b_name":  r.champion_b_name,
                "role":             r.role,
                "win_rate_a_vs_b":  r.win_rate_a_vs_b,
                "win_rate_b_vs_a":  round(1.0 - r.win_rate_a_vs_b, 4),
                "games_played":     r.games_played,
                "confidence":       r.confidence,
                "patch":            r.patch,
                "source":           r.source,
                "notes":            r.notes,
            }
            for r in rows
        ],
    }


# ---------------------------------------------------------------------------
# GET /matchups/{champion_id}/counters
# ---------------------------------------------------------------------------

@router.get("/{champion_id}/counters", summary="Champions that beat this champion")
async def get_counters(
    champion_id: int,
    role:  Optional[str] = Query(None, description="Scope to a specific role"),
    limit: int           = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return the top-N champions that have the highest win rate AGAINST
    the given champion (i.e., champion_b = champion_id, sorted by
    win_rate_a_vs_b descending — A beats B).

    Also returns the reverse view: rows where champion_a = champion_id
    that have low win rates (champion_id is losing that matchup).
    """
    champ_map = await get_champion_map()
    if champion_id not in champ_map:
        raise HTTPException(status_code=404, detail=f"Champion id {champion_id} not found in DDragon.")

    # Rows where this champion is champion_b and is LOSING (win_rate_a_vs_b > 0.5)
    q = db.query(ChampionMatchup).filter(ChampionMatchup.champion_b_id == champion_id)
    if role:
        q = q.filter(ChampionMatchup.role == role.upper())
    counters_as_b = q.order_by(desc(ChampionMatchup.win_rate_a_vs_b)).limit(limit).all()

    # Rows where this champion IS champion_a but is losing (win_rate_a_vs_b < 0.5)
    q2 = db.query(ChampionMatchup).filter(
        ChampionMatchup.champion_a_id == champion_id,
        ChampionMatchup.win_rate_a_vs_b < 0.50,
    )
    if role:
        q2 = q2.filter(ChampionMatchup.role == role.upper())
    losing_as_a = q2.order_by(ChampionMatchup.win_rate_a_vs_b).limit(limit).all()

    def _row_from_b(r: ChampionMatchup) -> dict:
        """Row where r.champion_a beats our champion (= r.champion_b)."""
        raw_wr = r.win_rate_a_vs_b
        smoothed = _bayesian_smooth(raw_wr, r.games_played)
        return {
            "counter_champion_id":   r.champion_a_id,
            "counter_champion_name": r.champion_a_name,
            "role":                  r.role,
            "counter_win_rate":      round(raw_wr, 4),
            "smoothed_win_rate":     round(smoothed, 4),
            "games_played":          r.games_played,
            "confidence":            r.confidence,
            "source":                r.source,
            "patch":                 r.patch,
        }

    def _row_from_a(r: ChampionMatchup) -> dict:
        """Row where our champion (= r.champion_a) is losing to r.champion_b."""
        raw_wr = 1.0 - r.win_rate_a_vs_b   # opponent's win rate
        smoothed = _bayesian_smooth(raw_wr, r.games_played)
        return {
            "counter_champion_id":   r.champion_b_id,
            "counter_champion_name": r.champion_b_name,
            "role":                  r.role,
            "counter_win_rate":      round(raw_wr, 4),
            "smoothed_win_rate":     round(smoothed, 4),
            "games_played":          r.games_played,
            "confidence":            r.confidence,
            "source":                r.source,
            "patch":                 r.patch,
        }

    all_counters = [_row_from_b(r) for r in counters_as_b] + [_row_from_a(r) for r in losing_as_a]
    # Deduplicate by (counter_champion_id, role), prefer highest games_played
    seen: set = set()
    deduped = []
    for c in sorted(all_counters, key=lambda x: x["games_played"], reverse=True):
        key = (c["counter_champion_id"], c["role"])
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    # Final sort: strongest counters first (highest counter win rate)
    deduped.sort(key=lambda x: x["counter_win_rate"], reverse=True)

    return {
        "champion_id":   champion_id,
        "champion_name": champ_map.get(champion_id),
        "role_scope":    role.upper() if role else None,
        "counters":      deduped[:limit],
        "total_found":   len(deduped),
    }


# ---------------------------------------------------------------------------
# GET /matchups/{champion_id}/favors
# ---------------------------------------------------------------------------

@router.get("/{champion_id}/favors", summary="Champions this champion beats")
async def get_favors(
    champion_id: int,
    role:  Optional[str] = Query(None, description="Scope to a specific role"),
    limit: int           = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return the top-N champions that this champion has the highest win rate
    against (favorable matchups).
    """
    champ_map = await get_champion_map()
    if champion_id not in champ_map:
        raise HTTPException(status_code=404, detail=f"Champion id {champion_id} not found in DDragon.")

    # Rows where this champion is A and winning (win_rate_a_vs_b > 0.5)
    q = db.query(ChampionMatchup).filter(
        ChampionMatchup.champion_a_id == champion_id,
        ChampionMatchup.win_rate_a_vs_b > 0.50,
    )
    if role:
        q = q.filter(ChampionMatchup.role == role.upper())
    favors_as_a = q.order_by(desc(ChampionMatchup.win_rate_a_vs_b)).limit(limit).all()

    # Rows where this champion is B and the A side is LOSING (champ_id is winning)
    q2 = db.query(ChampionMatchup).filter(
        ChampionMatchup.champion_b_id == champion_id,
        ChampionMatchup.win_rate_a_vs_b < 0.50,
    )
    if role:
        q2 = q2.filter(ChampionMatchup.role == role.upper())
    favors_as_b = q2.order_by(ChampionMatchup.win_rate_a_vs_b).limit(limit).all()

    def _fav_from_a(r: ChampionMatchup) -> dict:
        raw_wr = r.win_rate_a_vs_b
        smoothed = _bayesian_smooth(raw_wr, r.games_played)
        return {
            "weak_champion_id":   r.champion_b_id,
            "weak_champion_name": r.champion_b_name,
            "role":               r.role,
            "our_win_rate":       round(raw_wr, 4),
            "smoothed_win_rate":  round(smoothed, 4),
            "games_played":       r.games_played,
            "confidence":         r.confidence,
            "source":             r.source,
            "patch":              r.patch,
        }

    def _fav_from_b(r: ChampionMatchup) -> dict:
        raw_wr = 1.0 - r.win_rate_a_vs_b   # our win rate (we are B)
        smoothed = _bayesian_smooth(raw_wr, r.games_played)
        return {
            "weak_champion_id":   r.champion_a_id,
            "weak_champion_name": r.champion_a_name,
            "role":               r.role,
            "our_win_rate":       round(raw_wr, 4),
            "smoothed_win_rate":  round(smoothed, 4),
            "games_played":       r.games_played,
            "confidence":         r.confidence,
            "source":             r.source,
            "patch":              r.patch,
        }

    all_favors = [_fav_from_a(r) for r in favors_as_a] + [_fav_from_b(r) for r in favors_as_b]
    seen: set = set()
    deduped = []
    for f in sorted(all_favors, key=lambda x: x["games_played"], reverse=True):
        key = (f["weak_champion_id"], f["role"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)

    deduped.sort(key=lambda x: x["our_win_rate"], reverse=True)

    return {
        "champion_id":   champion_id,
        "champion_name": champ_map.get(champion_id),
        "role_scope":    role.upper() if role else None,
        "favors":        deduped[:limit],
        "total_found":   len(deduped),
    }
