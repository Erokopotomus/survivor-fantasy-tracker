from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    Episode, Season, SeasonStatus, Castaway, CastawayStatus,
    CastawayEpisodeEvent, ScoringRule,
)
from app.schemas.episodes import (
    EpisodeCreate, EpisodeUpdate, EpisodeResponse,
    EpisodeScoreSubmit, EpisodeScoreResponse, CastawayScoreResult,
    ScoringTemplateResponse, TemplateRuleItem, TemplateCastawayItem,
)
from app.api.deps import get_current_user, require_commissioner
from app.models.models import FantasyPlayer
from app.services.scoring_engine import score_episode_event, get_active_rules

router = APIRouter(prefix="/api/seasons/{season_id}/episodes", tags=["Episodes"])


async def _get_season_or_404(db: AsyncSession, season_id: int) -> Season:
    result = await db.execute(select(Season).where(Season.id == season_id))
    season = result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    return season


async def _get_episode_or_404(
    db: AsyncSession, season_id: int, episode_id: int
) -> Episode:
    result = await db.execute(
        select(Episode).where(
            Episode.id == episode_id, Episode.season_id == season_id
        )
    )
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


@router.post("", response_model=EpisodeResponse, status_code=201)
async def create_episode(
    season_id: int,
    body: EpisodeCreate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    season = await _get_season_or_404(db, season_id)
    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current != SeasonStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Season must be active to add episodes")

    episode = Episode(
        season_id=season_id,
        episode_number=body.episode_number,
        title=body.title,
        air_date=body.air_date,
        is_merge=body.is_merge,
        is_finale=body.is_finale,
        tribes_active=body.tribes_active,
        notes=body.notes,
    )
    db.add(episode)
    await db.flush()
    await db.refresh(episode)
    return episode


@router.get("", response_model=list[EpisodeResponse])
async def list_episodes(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    await _get_season_or_404(db, season_id)
    result = await db.execute(
        select(Episode)
        .where(Episode.season_id == season_id)
        .order_by(Episode.episode_number)
    )
    return result.scalars().all()


@router.get("/{episode_id}", response_model=EpisodeResponse)
async def get_episode(
    season_id: int,
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    return await _get_episode_or_404(db, season_id, episode_id)


@router.patch("/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    season_id: int,
    episode_id: int,
    body: EpisodeUpdate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    episode = await _get_episode_or_404(db, season_id, episode_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(episode, field, value)
    await db.flush()
    await db.refresh(episode)
    return episode


@router.get("/{episode_id}/template", response_model=ScoringTemplateResponse)
async def get_scoring_template(
    season_id: int,
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    episode = await _get_episode_or_404(db, season_id, episode_id)

    # Active rules
    rules = await get_active_rules(db, season_id)
    rule_items = [
        TemplateRuleItem(
            rule_key=r.rule_key,
            rule_name=r.rule_name,
            multiplier=r.multiplier.value if hasattr(r.multiplier, "value") else r.multiplier,
            phase=r.phase.value if hasattr(r.phase, "value") else r.phase,
            points=r.points,
        )
        for r in rules
    ]

    # Active castaways
    castaways_result = await db.execute(
        select(Castaway)
        .where(Castaway.season_id == season_id, Castaway.status == CastawayStatus.ACTIVE)
        .order_by(Castaway.name)
    )
    castaway_items = [
        TemplateCastawayItem(
            castaway_id=c.id,
            castaway_name=c.name,
            status=c.status.value if isinstance(c.status, CastawayStatus) else c.status,
        )
        for c in castaways_result.scalars().all()
    ]

    return ScoringTemplateResponse(
        episode_id=episode.id,
        episode_number=episode.episode_number,
        rules=rule_items,
        castaways=castaway_items,
    )


@router.post("/{episode_id}/score", response_model=EpisodeScoreResponse)
async def submit_episode_scores(
    season_id: int,
    episode_id: int,
    body: EpisodeScoreSubmit,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    episode = await _get_episode_or_404(db, season_id, episode_id)
    rules = await get_active_rules(db, season_id)

    scores = []
    for event_input in body.events:
        # Upsert: check if event already exists
        existing_result = await db.execute(
            select(CastawayEpisodeEvent).where(
                CastawayEpisodeEvent.castaway_id == event_input.castaway_id,
                CastawayEpisodeEvent.episode_id == episode_id,
            )
        )
        event = existing_result.scalar_one_or_none()

        if event:
            event.event_data = event_input.event_data
            event.notes = event_input.notes
        else:
            event = CastawayEpisodeEvent(
                castaway_id=event_input.castaway_id,
                episode_id=episode_id,
                event_data=event_input.event_data,
                notes=event_input.notes,
            )
            db.add(event)
            await db.flush()

        score = await score_episode_event(db, event, rules=rules, episode=episode)

        # Get castaway name
        castaway_result = await db.execute(
            select(Castaway).where(Castaway.id == event_input.castaway_id)
        )
        castaway = castaway_result.scalar_one()

        scores.append(CastawayScoreResult(
            castaway_id=castaway.id,
            castaway_name=castaway.name,
            calculated_score=score,
        ))

    episode.is_scored = True
    await db.flush()

    return EpisodeScoreResponse(
        episode_id=episode.id,
        episode_number=episode.episode_number,
        scores=scores,
    )


@router.delete("/{episode_id}", status_code=204)
async def delete_episode(
    season_id: int,
    episode_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    episode = await _get_episode_or_404(db, season_id, episode_id)
    await db.delete(episode)
