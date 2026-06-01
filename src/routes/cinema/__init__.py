from fastapi import APIRouter
from src.routes.cinema.movies import router as movies_router
from src.routes.cinema.interactions import router as interactions_router
from src.routes.cinema.genres import router as genres_router
from src.routes.cinema.stars import router as stars_router
from src.routes.cinema.directors import router as directors_router

cinema_router = APIRouter()

cinema_router.include_router(movies_router)
cinema_router.include_router(interactions_router)
cinema_router.include_router(genres_router)
cinema_router.include_router(stars_router)
cinema_router.include_router(directors_router)

