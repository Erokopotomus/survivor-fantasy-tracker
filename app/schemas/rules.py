from pydantic import BaseModel, Field


class RuleCreate(BaseModel):
    rule_key: str = Field(..., max_length=50)
    rule_name: str = Field(..., max_length=100)
    points: float
    multiplier: str
    phase: str = "any"
    description: str | None = None
    is_active: bool = True
    sort_order: int = 0


class RuleUpdate(BaseModel):
    rule_name: str | None = None
    points: float | None = None
    multiplier: str | None = None
    phase: str | None = None
    description: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


class RuleResponse(BaseModel):
    id: int
    season_id: int
    rule_key: str
    rule_name: str
    points: float
    multiplier: str
    phase: str
    description: str | None
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class RescoreResponse(BaseModel):
    episodes_processed: int
    events_recalculated: int
