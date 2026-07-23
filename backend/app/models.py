import datetime
import enum

from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, event
from sqlalchemy.orm import relationship, object_session
from sqlalchemy.orm.attributes import NO_VALUE

from app.database import Base


class MediaType(str, enum.Enum):
    photo = "photo"
    video = "video"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    media_files = relationship("MediaFile", back_populates="owner", cascade="all, delete-orphan")


class MediaFile(Base):
    __tablename__ = "media_files"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    media_type = Column(Enum(MediaType), nullable=False)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False)
    current_filename = Column(String, nullable=False)  # points to latest edited version
    thumbnail_filename = Column(String, nullable=True)  # video only; photos are their own thumbnail
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="media_files")
    versions = relationship(
        "MediaVersion", back_populates="media", cascade="all, delete-orphan",
        order_by="MediaVersion.created_at",
    )


class MediaVersion(Base):
    __tablename__ = "media_versions"

    id = Column(Integer, primary_key=True, index=True)
    media_id = Column(Integer, ForeignKey("media_files.id"), nullable=False)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    media = relationship("MediaFile", back_populates="versions")


@event.listens_for(MediaFile.current_filename, "set")
def _record_version_on_change(target, value, oldvalue, initiator):
    """Every time current_filename changes (i.e. any edit is applied), stash
    the filename it's about to stop pointing at as a restorable version.
    This runs centrally here rather than in every router endpoint, so no
    edit endpoint needs to remember to call it. The very first time
    current_filename is set (on upload), oldvalue is NO_VALUE, so nothing
    is recorded — there's nothing to restore to yet."""
    if oldvalue in (None, NO_VALUE) or oldvalue == value:
        return
    session = object_session(target)
    if session is None or target.id is None:
        return
    session.add(MediaVersion(media_id=target.id, filename=oldvalue))