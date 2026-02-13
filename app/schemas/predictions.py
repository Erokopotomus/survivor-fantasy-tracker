from pydantic import BaseModel
from datetime import datetime


class PredictionCreate(BaseModel):
    prediction_type: str
    castaway_id: int


class PredictionResolve(BaseModel):
    is_correct: bool
    bonus_points: float = 0


class PredictionResponse(BaseModel):
    id: int
    season_id: int
    fantasy_player_id: int
    player_name: str = ""
    prediction_type: str
    castaway_id: int
    castaway_name: str = ""
    is_correct: bool | None
    bonus_points: float
    created_at: datetime

    model_config = {"from_attributes": True}
