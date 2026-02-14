import base64
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from app.api.deps import require_commissioner
from app.models.models import FantasyPlayer

router = APIRouter(prefix="/api/uploads", tags=["Uploads"])

MAX_SIZE = 2 * 1024 * 1024  # 2 MB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/image-to-base64")
async def image_to_base64(
    file: UploadFile = File(...),
    _: FantasyPlayer = Depends(require_commissioner),
):
    """Accept an image upload and return a base64 data URI string."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' not allowed. Use JPEG, PNG, or WebP.",
        )

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 2 MB.",
        )

    b64 = base64.b64encode(data).decode("utf-8")
    data_uri = f"data:{file.content_type};base64,{b64}"
    return {"data_uri": data_uri}
