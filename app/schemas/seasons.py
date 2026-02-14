from pydantic import BaseModel, Field
from datetime import datetime


class SeasonCreate(BaseModel):
    season_number: int = Field(..., gt=0)
    name: str = Field(..., max_length=100)
    max_roster_size: int = Field(default=4, gt=0)
    free_agent_pickup_limit: int = Field(default=1, ge=0)
    max_times_castaway_drafted: int = Field(default=2, gt=0)
    copy_rules_from_season_id: int | None = None


class SeasonUpdate(BaseModel):
    name: str | None = None
    max_roster_size: int | None = None
    free_agent_pickup_limit: int | None = None
    max_times_castaway_drafted: int | None = None


class SeasonStatusUpdate(BaseModel):
    status: str


class SeasonResponse(BaseModel):
    id: int
    season_number: int
    name: str
    status: str
    max_roster_size: int
    free_agent_pickup_limit: int
    max_times_castaway_drafted: int
    logo_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SeasonDetailResponse(SeasonResponse):
    castaway_count: int = 0
    episode_count: int = 0
    player_count: int = 0
