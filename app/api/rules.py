from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import ScoringRule, Season, RuleMultiplier, RulePhase, FantasyPlayer
from app.schemas.rules import RuleCreate, RuleUpdate, RuleResponse, RescoreResponse
from app.api.deps import get_current_user, require_commissioner
from app.services.scoring_engine import recalculate_season

router = APIRouter(prefix="/api/seasons/{season_id}/rules", tags=["Scoring Rules"])


@router.get("", response_model=list[RuleResponse])
async def list_rules(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(ScoringRule)
        .where(ScoringRule.season_id == season_id)
        .order_by(ScoringRule.sort_order, ScoringRule.id)
    )
    return result.scalars().all()


# Must be defined BEFORE /{rule_id} to prevent path conflict
@router.post("/rescore-season", response_model=RescoreResponse)
async def rescore_season(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await recalculate_season(db, season_id)
    return RescoreResponse(**result)


@router.post("", response_model=RuleResponse, status_code=201)
async def create_rule(
    season_id: int,
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    # Validate season exists
    season_result = await db.execute(select(Season).where(Season.id == season_id))
    if not season_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Season not found")

    # Check unique rule_key per season
    existing = await db.execute(
        select(ScoringRule).where(
            ScoringRule.season_id == season_id,
            ScoringRule.rule_key == body.rule_key,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Rule key already exists for this season")

    try:
        multiplier = RuleMultiplier(body.multiplier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid multiplier: {body.multiplier}")

    try:
        phase = RulePhase(body.phase)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase: {body.phase}")

    rule = ScoringRule(
        season_id=season_id,
        rule_key=body.rule_key,
        rule_name=body.rule_name,
        points=body.points,
        multiplier=multiplier,
        phase=phase,
        description=body.description,
        is_active=body.is_active,
        sort_order=body.sort_order,
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    return rule


@router.patch("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    season_id: int,
    rule_id: int,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(
        select(ScoringRule).where(
            ScoringRule.id == rule_id, ScoringRule.season_id == season_id
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    update_data = body.model_dump(exclude_unset=True)

    if "multiplier" in update_data:
        try:
            update_data["multiplier"] = RuleMultiplier(update_data["multiplier"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid multiplier")

    if "phase" in update_data:
        try:
            update_data["phase"] = RulePhase(update_data["phase"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid phase")

    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    season_id: int,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(
        select(ScoringRule).where(
            ScoringRule.id == rule_id, ScoringRule.season_id == season_id
        )
    )
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
