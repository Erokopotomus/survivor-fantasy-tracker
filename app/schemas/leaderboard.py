from pydantic import BaseModel


class CastawayBreakdownItem(BaseModel):
    castaway_id: int
    castaway_name: str
    pickup_type: str
    total_score: float
    photo_url: str | None = None
    status: str = "active"


class LeaderboardEntry(BaseModel):
    rank: int
    player_id: int
    player_name: str
    is_commissioner: bool
    roster_breakdown: list[CastawayBreakdownItem]
    prediction_bonus: float
    grand_total: float


class LeaderboardResponse(BaseModel):
    season_id: int
    entries: list[LeaderboardEntry]


class CastawayRankingItem(BaseModel):
    rank: int
    castaway_id: int
    castaway_name: str
    status: str
    total_score: float


class CastawayRankingsResponse(BaseModel):
    season_id: int
    rankings: list[CastawayRankingItem]


class WeeklyRecapCastawayItem(BaseModel):
    castaway_name: str
    episode_score: float
    drafted_by: list[str]


class WeeklyRecapPlayerItem(BaseModel):
    player_name: str
    episode_score: float
    season_total: float


class WeeklyRecapResponse(BaseModel):
    season_id: int
    episode_number: int
    episode_title: str | None
    episode_description: str | None = None
    castaway_scores: list[WeeklyRecapCastawayItem]
    player_standings: list[WeeklyRecapPlayerItem]
