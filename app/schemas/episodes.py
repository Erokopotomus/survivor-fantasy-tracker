from pydantic import BaseModel, Field
from datetime import datetime


class EpisodeCreate(BaseModel):
    episode_number: int = Field(..., gt=0)
    title: str | None = None
    air_date: datetime | None = None
    is_merge: bool = False
    is_finale: bool = False
    tribes_active: str | None = None
    notes: str | None = None


class EpisodeUpdate(BaseModel):
    title: str | None = None
    air_date: datetime | None = None
    is_merge: bool | None = None
    is_finale: bool | None = None
    tribes_active: str | None = None
    notes: str | None = None


class EpisodeResponse(BaseModel):
    id: int
    season_id: int
    episode_number: int
    title: str | None
    air_date: datetime | None
    is_merge: bool
    is_finale: bool
    tribes_active: str | None
    notes: str | None
    is_scored: bool

    model_config = {"from_attributes": True}


class CastawayEventInput(BaseModel):
    castaway_id: int
    event_data: dict
    notes: str | None = None


class EpisodeScoreSubmit(BaseModel):
    events: list[CastawayEventInput]


class CastawayScoreResult(BaseModel):
    castaway_id: int
    castaway_name: str
    calculated_score: float


class EpisodeScoreResponse(BaseModel):
    episode_id: int
    episode_number: int
    scores: list[CastawayScoreResult]


class TemplateRuleItem(BaseModel):
    rule_key: str
    rule_name: str
    multiplier: str
    phase: str
    points: float


class TemplateCastawayItem(BaseModel):
    castaway_id: int
    castaway_name: str
    status: str


class ScoringTemplateResponse(BaseModel):
    episode_id: int
    episode_number: int
    rules: list[TemplateRuleItem]
    castaways: list[TemplateCastawayItem]
