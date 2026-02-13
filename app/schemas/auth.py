from pydantic import BaseModel, Field


class PlayerRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=6)
    commissioner_key: str | None = None


class PlayerLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    player_id: int
    display_name: str
    is_commissioner: bool


class PlayerResponse(BaseModel):
    id: int
    username: str
    display_name: str
    is_commissioner: bool

    model_config = {"from_attributes": True}
