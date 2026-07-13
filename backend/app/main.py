from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth_router, media_router, object_removal_router, video_object_removal_router

Base.metadata.create_all(bind=engine)

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


@app.get("/health")
def health_check():
    return {"status": "ok"}