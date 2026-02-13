from pydantic import BaseModel, Field


class CastawayCreate(BaseModel):
    name: str = Field(..., max_length=100)
    age: int | None = None
    occupation: str | None = None
    starting_tribe: str | None = None
    current_tribe: str | None = None
    bio: str | None = None
    photo_url: str | None = None


class CastawayBulkCreate(BaseModel):
    castaways: list[CastawayCreate]


class CastawayUpdate(BaseModel):
    name: str | None = None
    age: int | None = None
    occupation: str | None = None
    starting_tribe: str | None = None
    current_tribe: str | None = None
    bio: str | None = None
    photo_url: str | None = None
    status: str | None = None
    final_placement: int | None = None


class CastawayResponse(BaseModel):
    id: int
    season_id: int
    name: str
    age: int | None
    occupation: str | None
    starting_tribe: str | None
    current_tribe: str | None
    bio: str | None
    photo_url: str | None
    status: str
    final_placement: int | None

    model_config = {"from_attributes": True}


class CastawayEpisodeScoreItem(BaseModel):
    episode_number: int
    episode_title: str | None
    event_data: dict
    calculated_score: float | None


class CastawayDetailResponse(CastawayResponse):
    total_score: float
    episode_scores: list[CastawayEpisodeScoreItem]
    drafted_by: list[str]
