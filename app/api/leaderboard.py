from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    FantasyPlayer, Season, Castaway, CastawayStatus, Episode,
    CastawayEpisodeEvent, FantasyRoster, PickupType,
)
from app.schemas.leaderboard import (
    LeaderboardResponse, LeaderboardEntry, CastawayBreakdownItem,
    CastawayRankingsResponse, CastawayRankingItem,
    WeeklyRecapResponse, WeeklyRecapCastawayItem, WeeklyRecapPlayerItem,
)
from app.api.deps import get_current_user
from app.services.scoring_engine import get_leaderboard, get_castaway_season_total, get_rostered_castaway_total

router = APIRouter(prefix="/api/seasons/{season_id}", tags=["Leaderboard"])


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def leaderboard(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    raw = await get_leaderboard(db, season_id)
    entries = [
        LeaderboardEntry(
            rank=e["rank"],
            player_id=e["player_id"],
            player_name=e["player_name"],
            is_commissioner=e["is_commissioner"],
            roster_breakdown=[
                CastawayBreakdownItem(**c) for c in e["roster_breakdown"]
            ],
            prediction_bonus=e["prediction_bonus"],
            grand_total=e["grand_total"],
        )
        for e in raw
    ]
    return LeaderboardResponse(season_id=season_id, entries=entries)


@router.get("/castaway-rankings", response_model=CastawayRankingsResponse)
async def castaway_rankings(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(Castaway).where(Castaway.season_id == season_id).order_by(Castaway.name)
    )
    castaways = result.scalars().all()

    rankings = []
    for c in castaways:
        total = await get_castaway_season_total(db, c.id, season_id)
        rankings.append(CastawayRankingItem(
            rank=0,
            castaway_id=c.id,
            castaway_name=c.name,
            status=c.status.value if isinstance(c.status, CastawayStatus) else c.status,
            total_score=total,
        ))

    rankings.sort(key=lambda x: x.total_score, reverse=True)
    for i, r in enumerate(rankings, 1):
        r.rank = i

    return CastawayRankingsResponse(season_id=season_id, rankings=rankings)


@router.get("/weekly-recap/{episode_number}", response_model=WeeklyRecapResponse)
async def weekly_recap(
    season_id: int,
    episode_number: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    # Find the episode
    ep_result = await db.execute(
        select(Episode).where(
            Episode.season_id == season_id,
            Episode.episode_number == episode_number,
        )
    )
    episode = ep_result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")

    # Get all events for this episode
    events_result = await db.execute(
        select(CastawayEpisodeEvent, Castaway)
        .join(Castaway, CastawayEpisodeEvent.castaway_id == Castaway.id)
        .where(CastawayEpisodeEvent.episode_id == episode.id)
        .order_by(CastawayEpisodeEvent.calculated_score.desc())
    )
    events = events_result.all()

    # Build castaway scores with drafted_by info
    castaway_scores = []
    for event, castaway in events:
        roster_result = await db.execute(
            select(FantasyPlayer.display_name)
            .join(FantasyRoster, FantasyPlayer.id == FantasyRoster.fantasy_player_id)
            .where(
                FantasyRoster.castaway_id == castaway.id,
                FantasyRoster.season_id == season_id,
                FantasyRoster.is_active == True,
            )
        )
        drafted_by = [row[0] for row in roster_result.all()]

        castaway_scores.append(WeeklyRecapCastawayItem(
            castaway_name=castaway.name,
            episode_score=event.calculated_score or 0,
            drafted_by=drafted_by,
        ))

    # Build player standings for this episode
    # Get all players with rosters
    players_result = await db.execute(
        select(FantasyPlayer)
        .join(FantasyRoster)
        .where(FantasyRoster.season_id == season_id)
        .distinct()
    )
    players = players_result.scalars().all()

    player_standings = []
    for player in players:
        # Get player's roster entries (need pickup info for free agent filtering)
        roster_result = await db.execute(
            select(FantasyRoster).where(
                FantasyRoster.fantasy_player_id == player.id,
                FantasyRoster.season_id == season_id,
                FantasyRoster.is_active == True,
            )
        )
        roster_entries = roster_result.scalars().all()

        # Sum this episode's scores for the player's castaways
        # (only if the pickup happened before this episode)
        ep_score = 0.0
        for entry in roster_entries:
            # Skip free agents picked up after this episode
            if (entry.pickup_type == PickupType.FREE_AGENT
                    and entry.picked_up_after_episode is not None
                    and entry.picked_up_after_episode >= episode_number):
                continue
            ev_result = await db.execute(
                select(CastawayEpisodeEvent).where(
                    CastawayEpisodeEvent.castaway_id == entry.castaway_id,
                    CastawayEpisodeEvent.episode_id == episode.id,
                )
            )
            ev = ev_result.scalar_one_or_none()
            if ev:
                ep_score += ev.calculated_score or 0

        # Season total (respects pickup timing for free agents)
        season_total = 0.0
        for entry in roster_entries:
            pickup_ep = entry.picked_up_after_episode if entry.pickup_type == PickupType.FREE_AGENT else None
            total = await get_rostered_castaway_total(db, entry.castaway_id, season_id, pickup_ep)
            season_total += total

        player_standings.append(WeeklyRecapPlayerItem(
            player_name=player.display_name,
            episode_score=round(ep_score, 2),
            season_total=round(season_total, 2),
        ))

    player_standings.sort(key=lambda x: x.season_total, reverse=True)

    return WeeklyRecapResponse(
        season_id=season_id,
        episode_id=episode.id,
        episode_number=episode_number,
        episode_title=episode.title,
        episode_description=episode.description,
        castaway_scores=castaway_scores,
        player_standings=player_standings,
    )
