from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    Castaway, CastawayStatus, Season, CastawayEpisodeEvent,
    Episode, FantasyRoster, FantasyPlayer,
)
from app.schemas.castaways import (
    CastawayCreate, CastawayBulkCreate, CastawayUpdate,
    CastawayResponse, CastawayDetailResponse, CastawayEpisodeScoreItem,
)
from app.api.deps import get_current_user, require_commissioner
from app.services.scoring_engine import get_castaway_season_total

router = APIRouter(prefix="/api/seasons/{season_id}/castaways", tags=["Castaways"])


async def _get_season_or_404(db: AsyncSession, season_id: int) -> Season:
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    return season


@router.post("/bulk", response_model=list[CastawayResponse], status_code=201)
async def bulk_add_castaways(
    season_id: int,
    body: CastawayBulkCreate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    await _get_season_or_404(db, season_id)
    created = []
    for c in body.castaways:
        castaway = Castaway(
            season_id=season_id,
            name=c.name,
            age=c.age,
            occupation=c.occupation,
            starting_tribe=c.starting_tribe,
            current_tribe=c.current_tribe or c.starting_tribe,
            bio=c.bio,
            photo_url=c.photo_url,
        )
        db.add(castaway)
        created.append(castaway)
    await db.flush()
    for c in created:
        await db.refresh(c)
    return created


@router.post("", response_model=CastawayResponse, status_code=201)
async def add_castaway(
    season_id: int,
    body: CastawayCreate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    await _get_season_or_404(db, season_id)
    castaway = Castaway(
        season_id=season_id,
        name=body.name,
        age=body.age,
        occupation=body.occupation,
        starting_tribe=body.starting_tribe,
        current_tribe=body.current_tribe or body.starting_tribe,
        bio=body.bio,
        photo_url=body.photo_url,
    )
    db.add(castaway)
    await db.flush()
    await db.refresh(castaway)
    return castaway


@router.get("", response_model=list[CastawayResponse])
async def list_castaways(
    season_id: int,
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    await _get_season_or_404(db, season_id)
    query = select(Castaway).where(Castaway.season_id == season_id)
    if status:
        try:
            castaway_status = CastawayStatus(status)
            query = query.where(Castaway.status == castaway_status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status filter")
    query = query.order_by(Castaway.name)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{castaway_id}", response_model=CastawayResponse)
async def get_castaway(
    season_id: int,
    castaway_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(Castaway).where(
            Castaway.id == castaway_id, Castaway.season_id == season_id
        )
    )
    castaway = result.scalar_one_or_none()
    if not castaway:
        raise HTTPException(status_code=404, detail="Castaway not found")
    return castaway


@router.get("/{castaway_id}/detail", response_model=CastawayDetailResponse)
async def get_castaway_detail(
    season_id: int,
    castaway_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(Castaway).where(
            Castaway.id == castaway_id, Castaway.season_id == season_id
        )
    )
    castaway = result.scalar_one_or_none()
    if not castaway:
        raise HTTPException(status_code=404, detail="Castaway not found")

    # Episode-by-episode scores
    events_result = await db.execute(
        select(CastawayEpisodeEvent, Episode)
        .join(Episode, CastawayEpisodeEvent.episode_id == Episode.id)
        .where(CastawayEpisodeEvent.castaway_id == castaway_id)
        .order_by(Episode.episode_number)
    )
    episode_scores = []
    for event, episode in events_result.all():
        episode_scores.append(CastawayEpisodeScoreItem(
            episode_number=episode.episode_number,
            episode_title=episode.title,
            event_data=event.event_data or {},
            calculated_score=event.calculated_score or 0,
        ))

    total_score = await get_castaway_season_total(db, castaway_id, season_id)

    # Who drafted this castaway
    roster_result = await db.execute(
        select(FantasyPlayer.display_name)
        .join(FantasyRoster, FantasyPlayer.id == FantasyRoster.fantasy_player_id)
        .where(
            FantasyRoster.castaway_id == castaway_id,
            FantasyRoster.season_id == season_id,
        )
    )
    drafted_by = [row[0] for row in roster_result.all()]

    return CastawayDetailResponse(
        id=castaway.id,
        season_id=castaway.season_id,
        name=castaway.name,
        age=castaway.age,
        occupation=castaway.occupation,
        starting_tribe=castaway.starting_tribe,
        current_tribe=castaway.current_tribe,
        bio=castaway.bio,
        photo_url=castaway.photo_url,
        status=castaway.status.value if isinstance(castaway.status, CastawayStatus) else castaway.status,
        final_placement=castaway.final_placement,
        total_score=total_score,
        episode_scores=episode_scores,
        drafted_by=drafted_by,
    )


@router.patch("/{castaway_id}", response_model=CastawayResponse)
async def update_castaway(
    season_id: int,
    castaway_id: int,
    body: CastawayUpdate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(
        select(Castaway).where(
            Castaway.id == castaway_id, Castaway.season_id == season_id
        )
    )
    castaway = result.scalar_one_or_none()
    if not castaway:
        raise HTTPException(status_code=404, detail="Castaway not found")

    update_data = body.model_dump(exclude_unset=True)
    if "status" in update_data:
        try:
            update_data["status"] = CastawayStatus(update_data["status"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")

    for field, value in update_data.items():
        setattr(castaway, field, value)

    await db.flush()
    await db.refresh(castaway)
    return castaway


@router.delete("/{castaway_id}", status_code=204)
async def delete_castaway(
    season_id: int,
    castaway_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    season = await _get_season_or_404(db, season_id)
    from app.models.models import SeasonStatus
    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current != SeasonStatus.SETUP:
        raise HTTPException(
            status_code=400, detail="Can only delete castaways during setup"
        )

    result = await db.execute(
        select(Castaway).where(
            Castaway.id == castaway_id, Castaway.season_id == season_id
        )
    )
    castaway = result.scalar_one_or_none()
    if not castaway:
        raise HTTPException(status_code=404, detail="Castaway not found")
    await db.delete(castaway)
