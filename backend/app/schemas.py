import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from app.models import MediaType, TransitionType


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MediaOut(BaseModel):
    id: int
    media_type: MediaType
    original_filename: str
    current_filename: str
    thumbnail_filename: Optional[str] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class TrimRequest(BaseModel):
    start_seconds: float
    end_seconds: float


class CropRequest(BaseModel):
    x: int
    y: int
    width: int
    height: int


class FilterRequest(BaseModel):
    filter_name: str  # grayscale | brightness | contrast | blur | sepia | saturation | sharpen
    intensity: Optional[float] = 1.0


class RotateRequest(BaseModel):
    degrees: int  # 90, 180, or 270


class FlipRequest(BaseModel):
    direction: str  # "horizontal" or "vertical"


class ResizeRequest(BaseModel):
    width: int
    height: int


class SpeedRequest(BaseModel):
    factor: float  # e.g. 0.5 = half speed, 2.0 = double speed


class VolumeRequest(BaseModel):
    level: float = 1.0
    mute: bool = False


class WatermarkRequest(BaseModel):
    text: str
    x: int = 10
    y: int = 10
    font_size: int = 32
    color: str = "#FFFFFF"
    opacity: float = 1.0


class VersionOut(BaseModel):
    id: int
    filename: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class GifExportRequest(BaseModel):
    fps: int = 10
    width: int = 480
    start_seconds: float = 0.0
    duration_seconds: Optional[float] = None


class DenoiseRequest(BaseModel):
    strength: float = 10.0


class SegmentRequest(BaseModel):
    mode: str  # "point" or "box"
    points: Optional[List[List[int]]] = None  # [[x, y], ...]
    box: Optional[List[int]] = None  # [x1, y1, x2, y2]


class SegmentResponse(BaseModel):
    mask_id: str
    score: float
    overlay_png_base64: str


class RemoveObjectRequest(BaseModel):
    mask_id: str


class VideoSegmentResponse(BaseModel):
    mask_id: str
    score: float
    overlay_png_base64: str
    first_frame_width: int
    first_frame_height: int


class VideoRemoveObjectResponse(BaseModel):
    job_id: str


class JobStatus(BaseModel):
    status: str  # pending | processing | done | failed
    progress: float
    error: Optional[str] = None


# ---- Projects / timeline ----

class ProjectClipIn(BaseModel):
    media_id: int
    trim_start: Optional[int] = 0
    trim_end: Optional[int] = None
    photo_duration_seconds: Optional[int] = 3
    transition_out: Optional[TransitionType] = TransitionType.none
    transition_duration: Optional[int] = 1


class ProjectClipOut(BaseModel):
    id: int
    media_id: int
    position: int
    trim_start: int
    trim_end: Optional[int] = None
    photo_duration_seconds: int
    transition_out: TransitionType
    transition_duration: int
    media: MediaOut

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    name: Optional[str] = "Untitled project"


class ProjectOut(BaseModel):
    id: int
    name: str
    music_media_id: Optional[int] = None
    music_volume: int
    rendered_filename: Optional[str] = None
    created_at: datetime.datetime
    clips: List[ProjectClipOut] = []

    class Config:
        from_attributes = True


class ReorderRequest(BaseModel):
    clip_ids: List[int]  # full list of this project's clip IDs, in desired order


class MusicRequest(BaseModel):
    media_id: int
    volume: Optional[int] = 100


class RenderJobOut(BaseModel):
    job_id: str