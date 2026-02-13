from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import (
    Prediction, FantasyPlayer, Castaway, Season, SeasonStatus,
)
from app.schemas.predictions import (
    PredictionCreate, PredictionResolve, PredictionResponse,
)
from app.api.deps import get_current_user, require_commissioner

router = APIRouter(prefix="/api/seasons/{season_id}/predictions", tags=["Predictions"])


async def _build_prediction_response(
    db: AsyncSession, pred: Prediction
) -> PredictionResponse:
    player_result = await db.execute(
        select(FantasyPlayer).where(FantasyPlayer.id == pred.fantasy_player_id)
    )
    player = player_result.scalar_one()

    castaway_result = await db.execute(
        select(Castaway).where(Castaway.id == pred.castaway_id)
    )
    castaway = castaway_result.scalar_one()

    return PredictionResponse(
        id=pred.id,
        season_id=pred.season_id,
        fantasy_player_id=pred.fantasy_player_id,
        player_name=player.display_name,
        prediction_type=pred.prediction_type,
        castaway_id=pred.castaway_id,
        castaway_name=castaway.name,
        is_correct=pred.is_correct,
        bonus_points=pred.bonus_points or 0,
        created_at=pred.created_at,
    )


@router.post("", response_model=PredictionResponse, status_code=201)
async def create_prediction(
    season_id: int,
    body: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: FantasyPlayer = Depends(get_current_user),
):
    # Validate season status
    season_result = await db.execute(select(Season).where(Season.id == season_id))
    season = season_result.scalar_one_or_none()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")

    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current not in (SeasonStatus.SETUP, SeasonStatus.DRAFTING):
        raise HTTPException(
            status_code=400, detail="Predictions can only be made during setup or drafting"
        )

    # Check unique prediction
    existing = await db.execute(
        select(Prediction).where(
            Prediction.season_id == season_id,
            Prediction.fantasy_player_id == current_user.id,
            Prediction.prediction_type == body.prediction_type,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail="You already have a prediction of this type"
        )

    pred = Prediction(
        season_id=season_id,
        fantasy_player_id=current_user.id,
        prediction_type=body.prediction_type,
        castaway_id=body.castaway_id,
    )
    db.add(pred)
    await db.flush()
    await db.refresh(pred)
    return await _build_prediction_response(db, pred)


@router.get("", response_model=list[PredictionResponse])
async def list_predictions(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(Prediction)
        .where(Prediction.season_id == season_id)
        .order_by(Prediction.prediction_type, Prediction.id)
    )
    predictions = result.scalars().all()
    return [await _build_prediction_response(db, p) for p in predictions]


@router.get("/mine", response_model=list[PredictionResponse])
async def my_predictions(
    season_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(Prediction).where(
            Prediction.season_id == season_id,
            Prediction.fantasy_player_id == current_user.id,
        )
    )
    predictions = result.scalars().all()
    return [await _build_prediction_response(db, p) for p in predictions]


@router.patch("/{prediction_id}", response_model=PredictionResponse)
async def update_prediction(
    season_id: int,
    prediction_id: int,
    body: PredictionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(Prediction).where(
            Prediction.id == prediction_id, Prediction.season_id == season_id
        )
    )
    pred = result.scalar_one_or_none()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")

    if pred.fantasy_player_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only update your own predictions")

    # Validate season status
    season_result = await db.execute(select(Season).where(Season.id == season_id))
    season = season_result.scalar_one()
    current = season.status if isinstance(season.status, SeasonStatus) else SeasonStatus(season.status)
    if current not in (SeasonStatus.SETUP, SeasonStatus.DRAFTING):
        raise HTTPException(status_code=400, detail="Can only update predictions during setup or drafting")

    pred.castaway_id = body.castaway_id
    pred.prediction_type = body.prediction_type
    await db.flush()
    await db.refresh(pred)
    return await _build_prediction_response(db, pred)


@router.post("/{prediction_id}/resolve", response_model=PredictionResponse)
async def resolve_prediction(
    season_id: int,
    prediction_id: int,
    body: PredictionResolve,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    result = await db.execute(
        select(Prediction).where(
            Prediction.id == prediction_id, Prediction.season_id == season_id
        )
    )
    pred = result.scalar_one_or_none()
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")

    pred.is_correct = body.is_correct
    pred.bonus_points = body.bonus_points
    await db.flush()
    await db.refresh(pred)
    return await _build_prediction_response(db, pred)
