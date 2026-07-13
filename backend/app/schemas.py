import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr

from app.models import MediaType


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
    filter_name: str  # grayscale | brightness | contrast | blur | sepia
    intensity: Optional[float] = 1.0


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