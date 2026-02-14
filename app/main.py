import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import auth, seasons, castaways, episodes, rules, rosters, leaderboard, predictions
from app.api import pages

# Import all models so Base.metadata is populated for create_all
import app.models.models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Always create tables on startup (idempotent — skips existing tables)
    logger.info("Starting up — creating database tables...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully.")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        # Don't re-raise — let the app start so we can at least see /health
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


@app.post("/api/seed")
async def run_seed():
    """One-time seed endpoint — creates players and Season 50."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.core.security import hash_password
    from app.models.models import FantasyPlayer, Season, SeasonStatus
    from app.services.rule_seeder import seed_default_rules

    results = []

    async with AsyncSessionLocal() as db:
        # Seed players
        players_data = [
            {"username": "eric", "display_name": "Eric", "is_commissioner": True},
            {"username": "calvin", "display_name": "Calvin", "is_commissioner": False},
            {"username": "jake", "display_name": "Jake", "is_commissioner": False},
            {"username": "josh", "display_name": "Josh", "is_commissioner": False},
        ]

        for pd in players_data:
            existing = await db.execute(
                select(FantasyPlayer).where(FantasyPlayer.username == pd["username"])
            )
            if existing.scalar_one_or_none():
                results.append(f"Player '{pd['username']}' already exists")
                continue
            player = FantasyPlayer(
                username=pd["username"],
                display_name=pd["display_name"],
                password_hash=hash_password("survivor50"),
                is_commissioner=pd["is_commissioner"],
            )
            db.add(player)
            results.append(f"Created player: {pd['display_name']}")

        await db.flush()

        # Seed Season 50
        existing_season = await db.execute(
            select(Season).where(Season.season_number == 50)
        )
        if existing_season.scalar_one_or_none():
            results.append("Season 50 already exists")
        else:
            season = Season(
                season_number=50,
                name="Survivor 50",
                status=SeasonStatus.SETUP,
                max_roster_size=4,
                free_agent_pickup_limit=1,
                max_times_castaway_drafted=2,
            )
            db.add(season)
            await db.flush()
            await db.refresh(season)
            rules_created = await seed_default_rules(db, season.id)
            results.append(f"Created Season 50 with {len(rules_created)} scoring rules")

        await db.commit()

    return {"status": "seeded", "details": results}


@app.post("/api/seed-s49")
async def run_seed_s49():
    """Seed Season 49 with complete cast, episodes, scores, and fantasy rosters."""
    from app.scripts.seed_s49 import seed_s49
    results = await seed_s49()
    return {"status": "seeded", "details": results}


@app.get("/api/debug/tables")
async def debug_tables():
    """Debug endpoint — list tables in the database."""
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        tables = [row[0] for row in result.fetchall()]
    return {"tables": tables, "count": len(tables)}
