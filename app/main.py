import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import auth, seasons, castaways, episodes, rules, rosters, leaderboard, predictions
from app.api import pages

settings = get_settings()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.debug:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description="Fantasy Survivor scoring engine with dynamic rules, commissioner tools, and leaderboards.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — open for now, lock down in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# API routers
app.include_router(auth.router)
app.include_router(seasons.router)
app.include_router(castaways.router)
app.include_router(episodes.router)
app.include_router(rules.router)
app.include_router(rosters.router)
app.include_router(leaderboard.router)
app.include_router(predictions.router)

# Page routes (frontend)
app.include_router(pages.router)


@app.get("/health")
async def health():
    return {"status": "healthy"}
