from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.config import get_settings
from app.models.models import FantasyPlayer
from app.schemas.auth import PlayerRegister, PlayerLogin, TokenResponse, PlayerResponse
from app.api.deps import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Auth"])
settings = get_settings()


@router.post("/register", response_model=TokenResponse)
async def register(body: PlayerRegister, db: AsyncSession = Depends(get_db)):
    # Check duplicate username
    existing = await db.execute(
        select(FantasyPlayer).where(FantasyPlayer.username == body.username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    is_commissioner = (
        body.commissioner_key is not None
        and body.commissioner_key == settings.commissioner_key
    )

    player = FantasyPlayer(
        username=body.username,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
        is_commissioner=is_commissioner,
    )
    db.add(player)
    await db.flush()
    await db.refresh(player)

    token = create_access_token(
        {"sub": str(player.id), "is_commissioner": player.is_commissioner}
    )
    return TokenResponse(
        access_token=token,
        player_id=player.id,
        display_name=player.display_name,
        is_commissioner=player.is_commissioner,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(FantasyPlayer).where(FantasyPlayer.username == form_data.username)
    )
    player = result.scalar_one_or_none()
    if not player or not verify_password(form_data.password, player.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(
        {"sub": str(player.id), "is_commissioner": player.is_commissioner}
    )
    return TokenResponse(
        access_token=token,
        player_id=player.id,
        display_name=player.display_name,
        is_commissioner=player.is_commissioner,
    )


@router.post("/login/json", response_model=TokenResponse)
async def login_json(body: PlayerLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(FantasyPlayer).where(FantasyPlayer.username == body.username)
    )
    player = result.scalar_one_or_none()
    if not player or not verify_password(body.password, player.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )

    token = create_access_token(
        {"sub": str(player.id), "is_commissioner": player.is_commissioner}
    )
    return TokenResponse(
        access_token=token,
        player_id=player.id,
        display_name=player.display_name,
        is_commissioner=player.is_commissioner,
    )


@router.get("/me", response_model=PlayerResponse)
async def me(current_user: FantasyPlayer = Depends(get_current_user)):
    return current_user


@router.get("/players", response_model=list[PlayerResponse])
async def list_players(
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(select(FantasyPlayer).order_by(FantasyPlayer.id))
    return result.scalars().all()
