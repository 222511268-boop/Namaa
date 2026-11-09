"""Serve stored photos and image chips to signed-in users."""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.deps import any_user
from app.models import User
from app.services.media import media_path

router = APIRouter(tags=["media"])
NAME = re.compile(r"^[0-9a-f]{32}(_t)?\.(jpg|png)$")


@router.get("/api/media/{kind}/{name}")
def get_media(kind: str, name: str, _: User = Depends(any_user)):
    if kind not in ("photos", "chips", "heat") or not NAME.match(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    path = media_path(kind, name)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return FileResponse(
        path,
        media_type="image/png" if name.endswith(".png") else "image/jpeg",
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )
