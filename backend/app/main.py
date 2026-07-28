import traceback

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text

from app.config import settings
from app.database import Base, engine
from app.routers import auth_router, media_router, object_removal_router, project_router, video_object_removal_router

Base.metadata.create_all(bind=engine)


def _run_startup_migrations():
    """Base.metadata.create_all only creates missing TABLES, not new
    columns on tables that already exist — so a column added to a model
    after someone already has a database file needs a manual ALTER TABLE
    here. This project has no migration framework (Alembic etc.) since
    it's a small dev app, so this lightweight check is the pragmatic
    equivalent for the columns that have been added so far."""
    inspector = inspect(engine)
    if "media_files" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("media_files")]
        if "thumbnail_filename" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE media_files ADD COLUMN thumbnail_filename VARCHAR"))
                conn.commit()
        if "duration_seconds" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE media_files ADD COLUMN duration_seconds FLOAT"))
                conn.commit()
    if "project_clips" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("project_clips")]
        if "speed_factor" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE project_clips ADD COLUMN speed_factor FLOAT DEFAULT 1.0"))
                conn.commit()


_run_startup_migrations()

app = FastAPI(title="Media Editor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(media_router.router)
app.include_router(object_removal_router.router)
app.include_router(video_object_removal_router.router)
app.include_router(project_router.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """By default, FastAPI returns a bare 500 with no JSON body for
    unhandled exceptions — so the frontend has nothing to show the person
    beyond a generic fallback message. This surfaces the real exception
    type/message in the response (still printing the full traceback to the
    backend terminal too), so errors are diagnosable from the UI directly."""
    traceback.print_exc()
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.get("/health")
def health_check():
    return {"status": "ok"}