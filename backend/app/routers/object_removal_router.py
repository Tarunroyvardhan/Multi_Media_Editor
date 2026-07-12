import base64
import os
import uuid

import cv2
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai import inpainting, segmentation
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import MediaFile, MediaType, User
from app.schemas import MediaOut, RemoveObjectRequest, SegmentRequest, SegmentResponse
from app.routers.media_router import _get_owned_media, _resolve_current_path

router = APIRouter(prefix="/media", tags=["object-removal"])


@router.post("/{media_id}/segment", response_model=SegmentResponse)
def segment_object(
    media_id: int,
    payload: SegmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.photo:
        raise HTTPException(status_code=400, detail="Object removal currently supports photos only")

    input_path = _resolve_current_path(media)

    points = [tuple(p) for p in payload.points] if payload.points else None
    box = tuple(payload.box) if payload.box else None
    if not points and not box:
        raise HTTPException(status_code=400, detail="Provide either points or a box")

    try:
        mask, score = segmentation.generate_mask(input_path, points=points, box=box)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    mask_id = uuid.uuid4().hex
    mask_filename = f"{current_user.id}_{media_id}_{mask_id}.png"
    mask_path = os.path.join(settings.masks_dir, mask_filename)
    cv2.imwrite(mask_path, mask)

    overlay_bytes = segmentation.mask_to_overlay_png_bytes(mask)
    overlay_b64 = base64.b64encode(overlay_bytes).decode("utf-8")

    return SegmentResponse(mask_id=mask_id, score=score, overlay_png_base64=overlay_b64)


@router.post("/{media_id}/remove-object", response_model=MediaOut)
def remove_object(
    media_id: int,
    payload: RemoveObjectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.photo:
        raise HTTPException(status_code=400, detail="Object removal currently supports photos only")

    mask_filename = f"{current_user.id}_{media_id}_{payload.mask_id}.png"
    mask_path = os.path.join(settings.masks_dir, mask_filename)
    if not os.path.exists(mask_path):
        raise HTTPException(status_code=404, detail="Mask not found or expired — generate it again")

    mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    input_path = _resolve_current_path(media)

    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    inpainting.remove_object(input_path, mask, output_path)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)

    os.remove(mask_path)
    return media
