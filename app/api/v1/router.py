from fastapi import APIRouter

from app.api.v1.endpoints import analyze, auth, library, user

api_router = APIRouter(prefix="/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
api_router.include_router(library.router, prefix="/library", tags=["library"])
api_router.include_router(user.router, prefix="/user", tags=["user"])
