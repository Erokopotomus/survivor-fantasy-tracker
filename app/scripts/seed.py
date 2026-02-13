"""
Seed script — Creates default players and Season 50.
Run with: python -m app.scripts.seed
"""
import asyncio
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import hash_password
from app.models.models import FantasyPlayer, Season, SeasonStatus
from app.services.rule_seeder import seed_default_rules

DEFAULT_PASSWORD = "survivor50"

PLAYERS = [
    {"username": "eric", "display_name": "Eric", "is_commissioner": True},
    {"username": "calvin", "display_name": "Calvin", "is_commissioner": False},
    {"username": "jake", "display_name": "Jake", "is_commissioner": False},
    {"username": "josh", "display_name": "Josh", "is_commissioner": False},
]


async def seed():
    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Seed players
        for player_data in PLAYERS:
            result = await db.execute(
                select(FantasyPlayer).where(
                    FantasyPlayer.username == player_data["username"]
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  Player '{player_data['username']}' already exists, skipping.")
                continue

            player = FantasyPlayer(
                username=player_data["username"],
                display_name=player_data["display_name"],
                password_hash=hash_password(DEFAULT_PASSWORD),
                is_commissioner=player_data["is_commissioner"],
            )
            db.add(player)
            print(f"  Created player: {player_data['display_name']} ({'commissioner' if player_data['is_commissioner'] else 'player'})")

        await db.flush()

        # Seed Season 50
        result = await db.execute(
            select(Season).where(Season.season_number == 50)
        )
        existing_season = result.scalar_one_or_none()
        if existing_season:
            print("  Season 50 already exists, skipping.")
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

            rules = await seed_default_rules(db, season.id)
            print(f"  Created Season 50 with {len(rules)} default scoring rules.")

        await db.commit()

    print("\nSeed complete!")


if __name__ == "__main__":
    print("Seeding Survivor Fantasy Tracker...\n")
    asyncio.run(seed())
