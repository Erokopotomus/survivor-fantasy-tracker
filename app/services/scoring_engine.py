"""
Scoring Engine — The brain of the fantasy tracker.

Reads scoring rules from the DB, applies them to castaway episode events,
and calculates scores dynamically. Adding/modifying rules in the scoring_rules
table automatically changes how scores are calculated. No code changes needed.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.models import (
    ScoringRule, CastawayEpisodeEvent, Episode, Castaway,
    FantasyRoster, FantasyPlayer, Prediction, Season,
    RuleMultiplier, RulePhase
)


async def get_active_rules(db: AsyncSession, season_id: int) -> list[ScoringRule]:
    """Fetch all active scoring rules for a season, ordered for display."""
    result = await db.execute(
        select(ScoringRule)
        .where(ScoringRule.season_id == season_id, ScoringRule.is_active == True)
        .order_by(ScoringRule.sort_order, ScoringRule.id)
    )
    return result.scalars().all()


def calculate_event_score(event_data: dict, rules: list[ScoringRule], is_post_merge: bool = False) -> float:
    """
    Calculate the score for a single castaway's episode events.

    Args:
        event_data: Dict keyed by rule_key with counts/flags as values
        rules: Active scoring rules for the season
        is_post_merge: Whether this episode is post-merge (for phase filtering)

    Returns:
        Total score as a float
    """
    total = 0.0

    for rule in rules:
        # Skip rules that don't apply to this phase
        if rule.phase == RulePhase.PRE_MERGE and is_post_merge:
            continue
        if rule.phase == RulePhase.POST_MERGE and not is_post_merge:
            continue

        value = event_data.get(rule.rule_key, 0)
        if value is None:
            value = 0

        if rule.multiplier == RuleMultiplier.BINARY:
            # Binary: points awarded if value is truthy (1 = yes, 0 = no)
            if value:
                total += rule.points
        elif rule.multiplier == RuleMultiplier.PER_INSTANCE:
            # Per instance: points * count
            total += rule.points * float(value)

    return round(total, 2)


async def score_episode_event(
    db: AsyncSession,
    event: CastawayEpisodeEvent,
    rules: list[ScoringRule] | None = None,
    episode: Episode | None = None,
) -> float:
    """
    Calculate and cache the score for a single castaway episode event.
    Persists the calculated_score back to the event record.
    """
    if rules is None:
        # Fetch the episode to get the season_id
        if episode is None:
            ep_result = await db.execute(select(Episode).where(Episode.id == event.episode_id))
            episode = ep_result.scalar_one()
        rules = await get_active_rules(db, episode.season_id)

    if episode is None:
        ep_result = await db.execute(select(Episode).where(Episode.id == event.episode_id))
        episode = ep_result.scalar_one()

    # Determine merge status - check if this episode or any prior episode is the merge
    merge_result = await db.execute(
        select(Episode)
        .where(
            Episode.season_id == episode.season_id,
            Episode.is_merge == True,
            Episode.episode_number <= episode.episode_number,
        )
    )
    is_post_merge = merge_result.scalar_one_or_none() is not None

    score = calculate_event_score(event.event_data, rules, is_post_merge)
    event.calculated_score = score
    return score


async def score_full_episode(db: AsyncSession, episode_id: int) -> dict[int, float]:
    """
    (Re)calculate scores for ALL castaways in an episode.
    Returns dict of {castaway_id: score}.
    """
    ep_result = await db.execute(select(Episode).where(Episode.id == episode_id))
    episode = ep_result.scalar_one()

    rules = await get_active_rules(db, episode.season_id)

    events_result = await db.execute(
        select(CastawayEpisodeEvent).where(CastawayEpisodeEvent.episode_id == episode_id)
    )
    events = events_result.scalars().all()

    scores = {}
    for event in events:
        score = await score_episode_event(db, event, rules=rules, episode=episode)
        scores[event.castaway_id] = score

    episode.is_scored = True
    await db.flush()
    return scores


async def get_castaway_season_total(db: AsyncSession, castaway_id: int, season_id: int) -> float:
    """Sum all episode scores for a castaway across the season."""
    result = await db.execute(
        select(CastawayEpisodeEvent)
        .join(Episode)
        .where(
            CastawayEpisodeEvent.castaway_id == castaway_id,
            Episode.season_id == season_id,
        )
    )
    events = result.scalars().all()
    return round(sum(e.calculated_score or 0 for e in events), 2)


async def get_fantasy_player_total(
    db: AsyncSession,
    fantasy_player_id: int,
    season_id: int,
) -> dict:
    """
    Calculate a fantasy player's total score across all their rostered castaways.
    Returns breakdown by castaway + grand total.
    """
    # Get their roster
    roster_result = await db.execute(
        select(FantasyRoster)
        .where(
            FantasyRoster.fantasy_player_id == fantasy_player_id,
            FantasyRoster.season_id == season_id,
            FantasyRoster.is_active == True,
        )
    )
    roster_entries = roster_result.scalars().all()

    breakdown = []
    grand_total = 0.0

    for entry in roster_entries:
        castaway_total = await get_castaway_season_total(db, entry.castaway_id, season_id)

        # Get castaway name
        castaway_result = await db.execute(select(Castaway).where(Castaway.id == entry.castaway_id))
        castaway = castaway_result.scalar_one()

        breakdown.append({
            "castaway_id": entry.castaway_id,
            "castaway_name": castaway.name,
            "pickup_type": entry.pickup_type.value,
            "total_score": castaway_total,
        })
        grand_total += castaway_total

    # Add prediction bonus points
    pred_result = await db.execute(
        select(Prediction)
        .where(
            Prediction.fantasy_player_id == fantasy_player_id,
            Prediction.season_id == season_id,
            Prediction.is_correct == True,
        )
    )
    predictions = pred_result.scalars().all()
    prediction_bonus = sum(p.bonus_points or 0 for p in predictions)
    grand_total += prediction_bonus

    return {
        "fantasy_player_id": fantasy_player_id,
        "roster_breakdown": breakdown,
        "prediction_bonus": prediction_bonus,
        "grand_total": round(grand_total, 2),
    }


async def get_leaderboard(db: AsyncSession, season_id: int) -> list[dict]:
    """
    Full fantasy leaderboard for a season.
    Returns list sorted by total score descending.
    """
    # Get all fantasy players with rosters in this season
    player_result = await db.execute(
        select(FantasyPlayer)
        .join(FantasyRoster)
        .where(FantasyRoster.season_id == season_id)
        .distinct()
    )
    players = player_result.scalars().all()

    leaderboard = []
    for player in players:
        totals = await get_fantasy_player_total(db, player.id, season_id)
        leaderboard.append({
            "rank": 0,  # Set after sorting
            "player_id": player.id,
            "player_name": player.display_name,
            "is_commissioner": player.is_commissioner,
            **totals,
        })

    # Sort by grand_total descending
    leaderboard.sort(key=lambda x: x["grand_total"], reverse=True)

    # Assign ranks
    for i, entry in enumerate(leaderboard, 1):
        entry["rank"] = i

    return leaderboard


async def recalculate_season(db: AsyncSession, season_id: int) -> dict:
    """
    Nuclear option: recalculate ALL scores for an entire season.
    Use after rule changes to recompute everything.
    """
    rules = await get_active_rules(db, season_id)

    episodes_result = await db.execute(
        select(Episode)
        .where(Episode.season_id == season_id)
        .order_by(Episode.episode_number)
    )
    episodes = episodes_result.scalars().all()

    total_recalculated = 0
    for episode in episodes:
        events_result = await db.execute(
            select(CastawayEpisodeEvent).where(CastawayEpisodeEvent.episode_id == episode.id)
        )
        events = events_result.scalars().all()
        for event in events:
            await score_episode_event(db, event, rules=rules, episode=episode)
            total_recalculated += 1

    await db.flush()
    return {"episodes_processed": len(episodes), "events_recalculated": total_recalculated}
