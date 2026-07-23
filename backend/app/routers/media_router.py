import os
import shutil
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_from_query
from app.config import settings
from app.database import get_db
from app.models import MediaFile, MediaType, User
from app.schemas import (
    CropRequest,
    FilterRequest,
    FlipRequest,
    MediaOut,
    ResizeRequest,
    RotateRequest,
    SpeedRequest,
    TrimRequest,
    VolumeRequest,
    WatermarkRequest,
)
from app.utils.ffmpeg_utils import (
    add_text_overlay_video,
    change_speed_video,
    crop_video,
    flip_video,
    resize_video,
    rotate_video,
    set_volume_video,
    trim_video,
)
from app.utils.image_utils import (
    add_text_overlay_image,
    apply_filter,
    crop_image,
    flip_image,
    resize_image,
    rotate_image,
)

router = APIRouter(prefix="/media", tags=["media"])

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _detect_media_type(filename: str) -> MediaType:
    ext = os.path.splitext(filename)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return MediaType.video
    if ext in IMAGE_EXTENSIONS:
        return MediaType.photo
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")


def _get_owned_media(media_id: int, db: Session, user: User) -> MediaFile:
    media = db.query(MediaFile).filter(MediaFile.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    if media.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Not your file")
    return media


@router.post("/upload", response_model=MediaOut)
def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media_type = _detect_media_type(file.filename)
    ext = os.path.splitext(file.filename)[1].lower()
    stored_name = f"{uuid.uuid4().hex}{ext}"
    stored_path = os.path.join(settings.upload_dir, stored_name)

    with open(stored_path, "wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

    media = MediaFile(
        owner_id=current_user.id,
        media_type=media_type,
        original_filename=file.filename,
        stored_filename=stored_name,
        current_filename=stored_name,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return media


@router.get("/list", response_model=List[MediaOut])
def list_media(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(MediaFile).filter(MediaFile.owner_id == current_user.id).order_by(MediaFile.created_at.desc()).all()


@router.get("/{media_id}/file")
def get_media_file(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_query),
):
    media = _get_owned_media(media_id, db, current_user)
    path = os.path.join(settings.upload_dir, media.current_filename)
    if not os.path.exists(path):
        path = os.path.join(settings.processed_dir, media.current_filename)
    return FileResponse(path, headers={"Cache-Control": "no-store, must-revalidate"})


def _resolve_current_path(media: MediaFile) -> str:
    for directory in (settings.processed_dir, settings.upload_dir):
        candidate = os.path.join(directory, media.current_filename)
        if os.path.exists(candidate):
            return candidate
    raise HTTPException(status_code=404, detail="Underlying file missing on disk")


@router.post("/{media_id}/trim", response_model=MediaOut)
def trim_media(
    media_id: int,
    payload: TrimRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="Trim only applies to video files")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    trim_video(input_path, output_path, payload.start_seconds, payload.end_seconds)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/crop", response_model=MediaOut)
def crop_media(
    media_id: int,
    payload: CropRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    if media.media_type == MediaType.video:
        crop_video(input_path, output_path, payload.x, payload.y, payload.width, payload.height)
    else:
        crop_image(input_path, output_path, payload.x, payload.y, payload.width, payload.height)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/rotate", response_model=MediaOut)
def rotate_media(
    media_id: int,
    payload: RotateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    if payload.degrees % 90 != 0:
        raise HTTPException(status_code=400, detail="degrees must be a multiple of 90")

    if media.media_type == MediaType.video:
        rotate_video(input_path, output_path, payload.degrees)
    else:
        rotate_image(input_path, output_path, payload.degrees)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/flip", response_model=MediaOut)
def flip_media(
    media_id: int,
    payload: FlipRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if payload.direction not in ("horizontal", "vertical"):
        raise HTTPException(status_code=400, detail="direction must be 'horizontal' or 'vertical'")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    if media.media_type == MediaType.video:
        flip_video(input_path, output_path, payload.direction)
    else:
        flip_image(input_path, output_path, payload.direction)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/resize", response_model=MediaOut)
def resize_media(
    media_id: int,
    payload: ResizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if payload.width <= 0 or payload.height <= 0:
        raise HTTPException(status_code=400, detail="width and height must be positive")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    if media.media_type == MediaType.video:
        resize_video(input_path, output_path, payload.width, payload.height)
    else:
        resize_image(input_path, output_path, payload.width, payload.height)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/speed", response_model=MediaOut)
def speed_media(
    media_id: int,
    payload: SpeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="Speed change only applies to video files")
    if payload.factor <= 0:
        raise HTTPException(status_code=400, detail="factor must be positive")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    change_speed_video(input_path, output_path, payload.factor)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/volume", response_model=MediaOut)
def volume_media(
    media_id: int,
    payload: VolumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.video:
        raise HTTPException(status_code=400, detail="Volume control only applies to video files")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    try:
        set_volume_video(input_path, output_path, payload.level, payload.mute)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/watermark", response_model=MediaOut)
def watermark_media(
    media_id: int,
    payload: WatermarkRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="text must not be empty")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    if media.media_type == MediaType.video:
        add_text_overlay_video(
            input_path, output_path, payload.text, payload.x, payload.y, payload.font_size
        )
    else:
        add_text_overlay_image(
            input_path, output_path, payload.text, payload.x, payload.y,
            payload.font_size, payload.color, payload.opacity,
        )

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.post("/{media_id}/filter", response_model=MediaOut)
def filter_media(
    media_id: int,
    payload: FilterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media = _get_owned_media(media_id, db, current_user)
    if media.media_type != MediaType.photo:
        raise HTTPException(status_code=400, detail="Filters currently apply to photos only")

    input_path = _resolve_current_path(media)
    ext = os.path.splitext(media.stored_filename)[1]
    output_name = f"{uuid.uuid4().hex}{ext}"
    output_path = os.path.join(settings.processed_dir, output_name)

    apply_filter(input_path, output_path, payload.filter_name, payload.intensity)

    media.current_filename = output_name
    db.commit()
    db.refresh(media)
    return media


@router.delete("/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    media = _get_owned_media(media_id, db, current_user)
    db.delete(media)
    db.commit()
    return {"detail": "Deleted"}