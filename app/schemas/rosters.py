from pydantic import BaseModel
from datetime import datetime


class DraftPickCreate(BaseModel):
    fantasy_player_id: int
    castaway_id: int
    draft_position: int


class FreeAgentPickup(BaseModel):
    fantasy_player_id: int
    castaway_id: int
    picked_up_after_episode: int


class RosterDropRequest(BaseModel):
    pass


class RosterEntryResponse(BaseModel):
    id: int
    season_id: int
    fantasy_player_id: int
    castaway_id: int
    castaway_name: str = ""
    player_name: str = ""
    pickup_type: str
    draft_position: int | None
    picked_up_after_episode: int | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlayerRosterResponse(BaseModel):
    fantasy_player_id: int
    player_name: str
    castaways: list[RosterEntryResponse]
