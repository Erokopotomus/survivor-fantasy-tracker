from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.models import Season, SeasonStatus, Castaway, Episode, FantasyRoster
from app.schemas.seasons import (
    SeasonCreate, SeasonUpdate, SeasonStatusUpdate,
    SeasonResponse, SeasonDetailResponse,
)
from app.api.deps import get_current_user, require_commissioner
from app.models.models import FantasyPlayer
from app.services.rule_seeder import seed_default_rules, copy_rules_from_season

router = APIRouter(prefix="/api/seasons", tags=["Seasons"])

VALID_TRANSITIONS = {
    SeasonStatus.SETUP: [SeasonStatus.DRAFTING],
    SeasonStatus.DRAFTING: [SeasonStatus.ACTIVE],
    SeasonStatus.ACTIVE: [SeasonStatus.COMPLETE],
    SeasonStatus.COMPLETE: [SeasonStatus.ACTIVE],
}


@router.post("", response_model=SeasonResponse, status_code=201)
async def create_season(
    body: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    season = Season(
        season_number=body.season_number,
        name=body.name,
        max_roster_size=body.max_roster_size,
        free_agent_pickup_limit=body.free_agent_pickup_limit,
        max_times_castaway_drafted=body.max_times_castaway_drafted,
    )
    db.add(season)
    await db.flush()
    await db.refresh(season)

    # Seed scoring rules
    if body.copy_rules_from_season_id:
        await copy_rules_from_season(db, body.copy_rules_from_season_id, season.id)
    else:
        await seed_default_rules(db, season.id)

    return season


@router.get("", response_model=list[SeasonResponse])
async def list_seasons(
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(select(Season).order_by(Season.season_number.desc()))
    return result.scalars().all()


@router.get("/{season_id}", response_model=SeasonDetailResponse)
async def get_season(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    castaway_count = (await db.execute(
        select(func.count()).select_from(Castaway).where(Castaway.season_id == season_id)
    )).scalar()

    episode_count = (await db.execute(
        select(func.count()).select_from(Episode).where(Episode.season_id == season_id)
    )).scalar()

    player_count = (await db.execute(
        select(func.count(func.distinct(FantasyRoster.fantasy_player_id)))
        .where(FantasyRoster.season_id == season_id)
    )).scalar()

    return SeasonDetailResponse(
        id=season.id,
        season_number=season.season_number,
        name=season.name,
        status=season.status.value if isinstance(season.status, SeasonStatus) else season.status,
        max_roster_size=season.max_roster_size,
        free_agent_pickup_limit=season.free_agent_pickup_limit,
        max_times_castaway_drafted=season.max_times_castaway_drafted,
        created_at=season.created_at,
        castaway_count=castaway_count or 0,
        episode_count=episode_count or 0,
        player_count=player_count or 0,
    )


@router.patch("/{season_id}", response_model=SeasonResponse)
async def update_season(
    season_id: int,
    body: SeasonUpdate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(season, field, value)

    await db.flush()
    await db.refresh(season)
    return season


@router.patch("/{season_id}/status", response_model=SeasonResponse)
async def update_season_status(
    season_id: int,
    body: SeasonStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    try:
        new_status = SeasonStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {[s.value for s in SeasonStatus]}",
        )

    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if new_status not in VALID_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {current.value} to {new_status.value}",
        )

    season.status = new_status
    await db.flush()
    await db.refresh(season)
    return season


@router.delete("/{season_id}", status_code=204)
async def delete_season(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current != SeasonStatus.SETUP:
        raise HTTPException(
            status_code=400, detail="Can only delete seasons in setup status"
        )

    await db.delete(season)
