"""
Default scoring rules seeder.
Creates the standard rule set for a new season. Commissioner can then
modify individual rules via the API without touching code.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import ScoringRule, RuleMultiplier, RulePhase


# The canonical rule set from S49 ScoringRules tab
DEFAULT_RULES = [
    {"rule_key": "survive_tribal", "rule_name": "Survive Tribal Council", "points": 1.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 1},
    {"rule_key": "tribe_reward_win", "rule_name": "Tribe Reward Win", "points": 1.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.PRE_MERGE, "sort_order": 2},
    {"rule_key": "tribe_reward_2nd", "rule_name": "Tribe 2nd Place Reward", "points": 0.5, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.PRE_MERGE, "sort_order": 3},
    {"rule_key": "tribe_immunity_1st", "rule_name": "Tribe Win Immunity (1st Place)", "points": 2.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.PRE_MERGE, "sort_order": 4},
    {"rule_key": "tribe_immunity_2nd", "rule_name": "Tribe Win Immunity (2nd Place)", "points": 1.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.PRE_MERGE, "sort_order": 5},
    {"rule_key": "confessional_count", "rule_name": "Confessional Count", "points": 0.25, "multiplier": RuleMultiplier.PER_INSTANCE, "phase": RulePhase.ANY, "sort_order": 6},
    {"rule_key": "obtain_advantage", "rule_name": "Obtain Advantage", "points": 2.0, "multiplier": RuleMultiplier.PER_INSTANCE, "phase": RulePhase.ANY, "sort_order": 7},
    {"rule_key": "used_advantage_correctly", "rule_name": "Used Advantage Correctly", "points": 2.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 8},
    {"rule_key": "go_home_with_advantage", "rule_name": "Go Home with Advantage", "points": -1.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 9},
    {"rule_key": "played_advantage_incorrectly", "rule_name": "Played Advantage Incorrectly", "points": -0.5, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 10},
    {"rule_key": "obtain_immunity_idol", "rule_name": "Obtain Immunity Idol", "points": 5.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 11, "description": "Can't get duplicate points for the same idol"},
    {"rule_key": "play_idol_correctly", "rule_name": "Play Immunity Idol Correctly", "points": 5.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 12},
    {"rule_key": "go_home_with_immunity", "rule_name": "Go Home with Immunity Idol", "points": -4.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 13},
    {"rule_key": "played_idol_incorrectly", "rule_name": "Played Idol Incorrectly", "points": -2.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 14},
    {"rule_key": "played_sitd", "rule_name": "Played Shot in the Dark", "points": 1.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 15},
    {"rule_key": "successful_sitd", "rule_name": "Successful SITD", "points": 5.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 16},
    {"rule_key": "make_merge", "rule_name": "Make Merge", "points": 2.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 17},
    {"rule_key": "picked_for_reward", "rule_name": "Picked for Post-Merge Reward", "points": 0.5, "multiplier": RuleMultiplier.PER_INSTANCE, "phase": RulePhase.POST_MERGE, "sort_order": 18},
    {"rule_key": "solo_reward_win", "rule_name": "Post-Merge Solo Reward Win", "points": 2.0, "multiplier": RuleMultiplier.PER_INSTANCE, "phase": RulePhase.POST_MERGE, "sort_order": 19},
    {"rule_key": "individual_immunity_win", "rule_name": "Post-Merge Immunity Win", "points": 5.0, "multiplier": RuleMultiplier.PER_INSTANCE, "phase": RulePhase.POST_MERGE, "sort_order": 20},
    {"rule_key": "overall_winner", "rule_name": "Overall Winner", "points": 25.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.POST_MERGE, "sort_order": 21},
    {"rule_key": "runner_up", "rule_name": "Runner-Up", "points": 12.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.POST_MERGE, "sort_order": 22},
    {"rule_key": "third_place", "rule_name": "3rd Place", "points": 6.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.POST_MERGE, "sort_order": 23},
    {"rule_key": "fourth_place", "rule_name": "4th Place", "points": 3.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.POST_MERGE, "sort_order": 24},
    {"rule_key": "fifth_place", "rule_name": "5th Place", "points": 1.5, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.POST_MERGE, "sort_order": 25},
    {"rule_key": "first_boot_pick_correct", "rule_name": "Pre-season First Boot Pick Right", "points": 5.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.PRE_MERGE, "sort_order": 26},
    {"rule_key": "evacuated", "rule_name": "Evacuated", "points": -7.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 27},
    {"rule_key": "quit", "rule_name": "Voluntarily Leave (Quit)", "points": -15.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.ANY, "sort_order": 28},
    {"rule_key": "win_fire_making", "rule_name": "Win End of Season Fire Making", "points": 5.0, "multiplier": RuleMultiplier.BINARY, "phase": RulePhase.POST_MERGE, "sort_order": 29},
    {"rule_key": "go_on_journey", "rule_name": "Go on a Journey", "points": 1.0, "multiplier": RuleMultiplier.PER_INSTANCE, "phase": RulePhase.ANY, "sort_order": 30},
]


async def seed_default_rules(db: AsyncSession, season_id: int) -> list[ScoringRule]:
    """Create default scoring rules for a new season. Returns created rules."""
    created = []
    for rule_data in DEFAULT_RULES:
        rule = ScoringRule(season_id=season_id, **rule_data)
        db.add(rule)
        created.append(rule)
    await db.flush()
    return created


async def copy_rules_from_season(db: AsyncSession, source_season_id: int, target_season_id: int) -> list[ScoringRule]:
    """
    Copy all rules from a previous season to a new one.
    Perfect for 'use last season's rules as a starting point, then tweak'.
    """
    from sqlalchemy import select as sa_select
    result = await db.execute(
        sa_select(ScoringRule).where(ScoringRule.season_id == source_season_id).order_by(ScoringRule.sort_order)
    )
    source_rules = result.scalars().all()

    created = []
    for source in source_rules:
        new_rule = ScoringRule(
            season_id=target_season_id,
            rule_key=source.rule_key,
            rule_name=source.rule_name,
            points=source.points,
            multiplier=source.multiplier,
            phase=source.phase,
            description=source.description,
            is_active=source.is_active,
            sort_order=source.sort_order,
        )
        db.add(new_rule)
        created.append(new_rule)
    await db.flush()
    return created
