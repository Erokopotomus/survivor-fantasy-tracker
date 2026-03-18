from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.models import ChatMessage, FantasyPlayer
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/seasons/{season_id}/chat", tags=["Chat"])


class ChatMessageCreate(BaseModel):
    message: str


class ChatMessageResponse(BaseModel):
    id: int
    player_name: str
    player_color: Optional[str] = None
    message: str
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=list[ChatMessageResponse])
async def get_messages(
    season_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: FantasyPlayer = Depends(get_current_user),
):
    result = await db.execute(
        select(ChatMessage, FantasyPlayer.display_name)
        .join(FantasyPlayer, ChatMessage.fantasy_player_id == FantasyPlayer.id)
        .where(ChatMessage.season_id == season_id)
        .order_by(desc(ChatMessage.created_at))
        .limit(limit)
    )
    rows = result.all()
    return [
        ChatMessageResponse(
            id=msg.id,
            player_name=name,
            message=msg.message,
            created_at=msg.created_at.isoformat() if msg.created_at else "",
        )
        for msg, name in reversed(rows)
    ]


@router.post("", response_model=ChatMessageResponse)
async def post_message(
    season_id: int,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: FantasyPlayer = Depends(get_current_user),
):
    msg = ChatMessage(
        season_id=season_id,
        fantasy_player_id=current_user.id,
        message=body.message.strip()[:500],
    )
    db.add(msg)
    await db.flush()
    await db.refresh(msg)
    await db.commit()
    return ChatMessageResponse(
        id=msg.id,
        player_name=current_user.display_name,
        message=msg.message,
        created_at=msg.created_at.isoformat() if msg.created_at else "",
    )
