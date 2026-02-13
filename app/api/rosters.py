from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.models.models import (
    FantasyRoster, FantasyPlayer, Castaway, Season, SeasonStatus, PickupType,
)
from app.schemas.rosters import (
    DraftPickCreate, FreeAgentPickup, RosterEntryResponse, PlayerRosterResponse,
)
from app.api.deps import get_current_user, require_commissioner

router = APIRouter(prefix="/api/seasons/{season_id}/rosters", tags=["Rosters"])


async def _get_season_or_404(db: AsyncSession, season_id: int) -> Season:
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    return season


async def _build_roster_response(db: AsyncSession, entry: FantasyRoster) -> RosterEntryResponse:
    player_result = await db.execute(
        select(FantasyPlayer).where(FantasyPlayer.id == entry.fantasy_player_id)
    )
    player = player_result.scalar_one()

    castaway_result = await db.execute(
        select(Castaway).where(Castaway.id == entry.castaway_id)
    )
    castaway = castaway_result.scalar_one()

    return RosterEntryResponse(
        id=entry.id,
        season_id=entry.season_id,
        fantasy_player_id=entry.fantasy_player_id,
        castaway_id=entry.castaway_id,
        castaway_name=castaway.name,
        player_name=player.display_name,
        pickup_type=entry.pickup_type.value if isinstance(entry.pickup_type, PickupType) else entry.pickup_type,
        draft_position=entry.draft_position,
        picked_up_after_episode=entry.picked_up_after_episode,
        is_active=entry.is_active,
        created_at=entry.created_at,
    )


@router.post("/draft", response_model=RosterEntryResponse, status_code=201)
async def draft_pick(
    season_id: int,
    body: DraftPickCreate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    season = await _get_season_or_404(db, season_id)
    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current != SeasonStatus.DRAFTING:
        raise HTTPException(status_code=400, detail="Season must be in drafting status")

    # Check roster size
    roster_count = (await db.execute(
        select(func.count()).select_from(FantasyRoster).where(
            FantasyRoster.fantasy_player_id == body.fantasy_player_id,
            FantasyRoster.season_id == season_id,
        )
    )).scalar()
    if roster_count >= season.max_roster_size:
        raise HTTPException(status_code=400, detail="Player roster is full")

    # Check castaway draft limit
    castaway_draft_count = (await db.execute(
        select(func.count()).select_from(FantasyRoster).where(
            FantasyRoster.castaway_id == body.castaway_id,
            FantasyRoster.season_id == season_id,
        )
    )).scalar()
    if castaway_draft_count >= season.max_times_castaway_drafted:
        raise HTTPException(
            status_code=400,
            detail=f"Castaway already drafted {castaway_draft_count} time(s) (max {season.max_times_castaway_drafted})",
        )

    entry = FantasyRoster(
        season_id=season_id,
        fantasy_player_id=body.fantasy_player_id,
        castaway_id=body.castaway_id,
        pickup_type=PickupType.DRAFT,
        draft_position=body.draft_position,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return await _build_roster_response(db, entry)


@router.post("/free-agent", response_model=RosterEntryResponse, status_code=201)
async def free_agent_pickup(
    season_id: int,
    body: FreeAgentPickup,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    season = await _get_season_or_404(db, season_id)
    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current != SeasonStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Season must be active for free agent pickups")

    # Check free agent limit
    fa_count = (await db.execute(
        select(func.count()).select_from(FantasyRoster).where(
            FantasyRoster.fantasy_player_id == body.fantasy_player_id,
            FantasyRoster.season_id == season_id,
            FantasyRoster.pickup_type == PickupType.FREE_AGENT,
        )
    )).scalar()
    if fa_count >= season.free_agent_pickup_limit:
        raise HTTPException(status_code=400, detail="Free agent pickup limit reached")

    # Check castaway draft limit
    castaway_draft_count = (await db.execute(
        select(func.count()).select_from(FantasyRoster).where(
            FantasyRoster.castaway_id == body.castaway_id,
            FantasyRoster.season_id == season_id,
        )
    )).scalar()
    if castaway_draft_count >= season.max_times_castaway_drafted:
        raise HTTPException(status_code=400, detail="Castaway already at max roster appearances")

    entry = FantasyRoster(
        season_id=season_id,
        fantasy_player_id=body.fantasy_player_id,
        castaway_id=body.castaway_id,
        pickup_type=PickupType.FREE_AGENT,
        picked_up_after_episode=body.picked_up_after_episode,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return await _build_roster_response(db, entry)


@router.get("", response_model=list[PlayerRosterResponse])
async def list_rosters(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    # Get all players with rosters in this season
    player_ids_result = await db.execute(
        select(func.distinct(FantasyRoster.fantasy_player_id))
        .where(FantasyRoster.season_id == season_id)
    )
    player_ids = [row[0] for row in player_ids_result.all()]

    rosters = []
    for pid in player_ids:
        player_result = await db.execute(
            select(FantasyPlayer).where(FantasyPlayer.id == pid)
        )
        player = player_result.scalar_one()

        entries_result = await db.execute(
            select(FantasyRoster)
            .where(FantasyRoster.season_id == season_id, FantasyRoster.fantasy_player_id == pid)
            .order_by(FantasyRoster.draft_position)
        )
        entries = entries_result.scalars().all()

        entry_responses = []
        for entry in entries:
            entry_responses.append(await _build_roster_response(db, entry))

        rosters.append(PlayerRosterResponse(
            fantasy_player_id=pid,
            player_name=player.display_name,
            castaways=entry_responses,
        ))
    return rosters


@router.get("/player/{player_id}", response_model=PlayerRosterResponse)
async def get_player_roster(
    season_id: int,
    player_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    player_result = await db.execute(
        select(FantasyPlayer).where(FantasyPlayer.id == player_id)
    )
    player = player_result.scalar_one_or_none()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    entries_result = await db.execute(
        select(FantasyRoster)
        .where(FantasyRoster.season_id == season_id, FantasyRoster.fantasy_player_id == player_id)
        .order_by(FantasyRoster.draft_position)
    )
    entries = entries_result.scalars().all()

    entry_responses = []
    for entry in entries:
        entry_responses.append(await _build_roster_response(db, entry))

    return PlayerRosterResponse(
        fantasy_player_id=player_id,
        player_name=player.display_name,
        castaways=entry_responses,
    )


@router.patch("/{roster_id}", response_model=RosterEntryResponse)
async def update_roster_entry(
    season_id: int,
    roster_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(
        select(FantasyRoster).where(
            FantasyRoster.id == roster_id, FantasyRoster.season_id == season_id
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Roster entry not found")

    entry.is_active = not entry.is_active
    await db.flush()
    await db.refresh(entry)
    return await _build_roster_response(db, entry)
