import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from app.core.config import get_settings
from app.core.database import engine, Base
from app.api import auth, seasons, castaways, episodes, rules, rosters, leaderboard, predictions, uploads
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
            # Idempotent migrations for columns added after initial deploy
            from sqlalchemy import text
            migrations = [
                "ALTER TABLE seasons ADD COLUMN IF NOT EXISTS logo_url TEXT",
                "ALTER TABLE castaways ALTER COLUMN photo_url TYPE TEXT",
                "ALTER TABLE episodes ADD COLUMN IF NOT EXISTS description TEXT",
            ]
            for sql in migrations:
                try:
                    await conn.execute(text(sql))
                except Exception as mig_err:
                    logger.warning(f"Migration skipped: {mig_err}")
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
app.include_router(uploads.router)

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


@app.post("/api/seed-s49-photos")
async def seed_s49_photos():
    """One-time endpoint to populate S49 castaway photo URLs."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.models import Castaway, Season

    # Map of castaway name -> photo URL
    # These are publicly accessible CBS promo images
    S49_PHOTOS = {
        "Savannah Louie": "https://static.wikia.nocookie.net/survivor/images/b/bb/S49_Savannah_Louie.jpg/revision/latest/scale-to-width-down/250",
        "Sage Ahrens-Nichols": "https://static.wikia.nocookie.net/survivor/images/3/3b/S49_Sage_Ahrens-Nichols.jpg/revision/latest/scale-to-width-down/250",
        "Rizo Velovic": "https://static.wikia.nocookie.net/survivor/images/c/cf/S49_Rizo_Velovic.jpg/revision/latest/scale-to-width-down/250",
        "Jawan Pitts": "https://static.wikia.nocookie.net/survivor/images/c/c0/S49_Jawan_Pitts.jpg/revision/latest/scale-to-width-down/250",
        "Nate Moore": "https://static.wikia.nocookie.net/survivor/images/d/d2/S49_Nate_Moore.jpg/revision/latest/scale-to-width-down/250",
        "Shannon Fairweather": "https://static.wikia.nocookie.net/survivor/images/9/96/S49_Shannon_Fairweather.jpg/revision/latest/scale-to-width-down/250",
        "Sophi Balerdi": "https://static.wikia.nocookie.net/survivor/images/6/61/S49_Sophi_Balerdi.jpg/revision/latest/scale-to-width-down/250",
        "Alex Moore": "https://static.wikia.nocookie.net/survivor/images/5/54/S49_Alex_Moore.jpg/revision/latest/scale-to-width-down/250",
        "Jeremiah Ing": "https://static.wikia.nocookie.net/survivor/images/e/e3/S49_Jeremiah_Ing.jpg/revision/latest/scale-to-width-down/250",
        "Jake Latimer": "https://static.wikia.nocookie.net/survivor/images/6/68/S49_Jake_Latimer.jpg/revision/latest/scale-to-width-down/250",
        "Annie Davis": "https://static.wikia.nocookie.net/survivor/images/a/ae/S49_Annie_Davis.jpg/revision/latest/scale-to-width-down/250",
        "Nicole Mazullo": "https://static.wikia.nocookie.net/survivor/images/9/9d/S49_Nicole_Mazullo.jpg/revision/latest/scale-to-width-down/250",
        "Kristina Mills": "https://static.wikia.nocookie.net/survivor/images/1/1e/S49_Kristina_Mills.jpg/revision/latest/scale-to-width-down/250",
        "Steven Ramm": "https://static.wikia.nocookie.net/survivor/images/7/7d/S49_Steven_Ramm.jpg/revision/latest/scale-to-width-down/250",
        "Sophie Segreti": "https://static.wikia.nocookie.net/survivor/images/f/fb/S49_Sophie_Segreti.jpg/revision/latest/scale-to-width-down/250",
        "MC Chukwujekwu": "https://static.wikia.nocookie.net/survivor/images/d/d5/S49_MC_Chukwujekwu.jpg/revision/latest/scale-to-width-down/250",
        "Matt Williams": "https://static.wikia.nocookie.net/survivor/images/a/a8/S49_Matt_Williams.jpg/revision/latest/scale-to-width-down/250",
        "Jason Treul": "https://static.wikia.nocookie.net/survivor/images/0/0a/S49_Jason_Treul.jpg/revision/latest/scale-to-width-down/250",
    }

    results = []
    async with AsyncSessionLocal() as db:
        season_result = await db.execute(
            select(Season).where(Season.season_number == 49)
        )
        season = season_result.scalar_one_or_none()
        if not season:
            return {"status": "error", "details": ["Season 49 not found. Run /api/seed-s49 first."]}

        for name, url in S49_PHOTOS.items():
            castaway_result = await db.execute(
                select(Castaway).where(
                    Castaway.season_id == season.id,
                    Castaway.name == name,
                )
            )
            castaway = castaway_result.scalar_one_or_none()
            if castaway:
                castaway.photo_url = url
                results.append(f"Updated photo for {name}")
            else:
                results.append(f"Castaway not found: {name}")

        await db.commit()

    return {"status": "seeded", "details": results}


@app.post("/api/seed-s50-cast")
async def seed_s50_cast():
    """Seed Season 50 with the full 24-person returning player cast, grouped by tribe."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.models import Castaway, Season, CastawayStatus

    S50_CAST = [
        # ── Cila (Orange) ──
        {"name": "Cirie Fields", "age": 55, "occupation": "Surgical Director", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Ozzy Lusth", "age": 43, "occupation": "Content Creator", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Christian Hubicki", "age": 39, "occupation": "Associate Professor", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Rick Devens", "age": 41, "occupation": "Director of Communications", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Jenna Lewis-Dougherty", "age": 47, "occupation": "Realtor", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Emily Flippen", "age": 30, "occupation": "Financial Analyst", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Savannah Louie", "age": 31, "occupation": "News Reporter", "starting_tribe": "Cila", "current_tribe": "Cila"},
        {"name": "Joe Hunter", "age": 45, "occupation": "Fire Captain", "starting_tribe": "Cila", "current_tribe": "Cila"},
        # ── Kalo (Teal) ──
        {"name": "Benjamin \"Coach\" Wade", "age": 53, "occupation": "Soccer Coach/Musician", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Mike White", "age": 54, "occupation": "Director/Writer", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Chrissy Hofbeck", "age": 54, "occupation": "Actuary", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Charlie Davis", "age": 27, "occupation": "Lawyer", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Tiffany Ervin", "age": 34, "occupation": "Visual Artist", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Jonathan Young", "age": 32, "occupation": "Bodyguard", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Dee Valladares", "age": 28, "occupation": "Entrepreneur", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        {"name": "Kamilla Karthigesu", "age": 31, "occupation": "Senior Software Engineer", "starting_tribe": "Kalo", "current_tribe": "Kalo"},
        # ── Vatu (Purple) ──
        {"name": "Colby Donaldson", "age": 51, "occupation": "Rancher", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Stephenie LaGrossa Kendrick", "age": 45, "occupation": "Territory Sales Representative", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Aubry Bracco", "age": 39, "occupation": "Marketing Director", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Angelina Keeley", "age": 35, "occupation": "Entrepreneur", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Genevieve Mushaluk", "age": 34, "occupation": "Lawyer", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Kyle Fraser", "age": 31, "occupation": "Music Attorney", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Q Burdette", "age": 31, "occupation": "Realtor", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
        {"name": "Rizo Velovic", "age": 25, "occupation": "Content Creator", "starting_tribe": "Vatu", "current_tribe": "Vatu"},
    ]

    results = []
    async with AsyncSessionLocal() as db:
        season_result = await db.execute(
            select(Season).where(Season.season_number == 50)
        )
        season = season_result.scalar_one_or_none()
        if not season:
            return {"status": "error", "details": ["Season 50 not found. Run /api/seed first."]}

        for c in S50_CAST:
            existing = await db.execute(
                select(Castaway).where(
                    Castaway.season_id == season.id,
                    Castaway.name == c["name"],
                )
            )
            if existing.scalar_one_or_none():
                results.append(f"Already exists: {c['name']}")
                continue

            castaway = Castaway(
                season_id=season.id,
                name=c["name"],
                age=c["age"],
                occupation=c["occupation"],
                starting_tribe=c["starting_tribe"],
                current_tribe=c["current_tribe"],
                status=CastawayStatus.ACTIVE,
            )
            db.add(castaway)
            results.append(f"Added: {c['name']} ({c['starting_tribe']})")

        await db.commit()

    return {
        "status": "seeded",
        "cast_count": len(S50_CAST),
        "tribes": {"Cila": 8, "Kalo": 8, "Vatu": 8},
        "details": results,
    }


@app.post("/api/seed-s50-photos-bios")
async def seed_s50_photos_bios():
    """One-time endpoint to populate S50 castaway photo URLs and bios."""
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.models import Castaway, Season

    S50_DATA = {
        "Cirie Fields": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/5/5c/S50_Cirie_Fields.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Cirie Fields has played five previous seasons: Panama (4th), Micronesia (3rd), Heroes vs. Villains (17th), Game Changers (6th), and Australia v The World (4th). Widely regarded as one of the greatest strategic and social players in franchise history, she is the woman who got up off the couch and played Survivor.",
        },
        "Ozzy Lusth": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/f/f6/S50_Ozzy_Lusth.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Ozzy Lusth competed in four seasons: Cook Islands (runner-up), Micronesia (9th), South Pacific (4th), and Game Changers (12th). He is renowned for his exceptional challenge dominance, winning five of six individual immunities in Cook Islands. One of the most dominant physical competitors in Survivor history.",
        },
        "Christian Hubicki": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/8/89/S50_Christian_Hubicki.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Christian Hubicki competed in David vs. Goliath (S37), finishing 7th after becoming a massive target for his strategic acumen and likability. A robotics professor turned fan-favorite, he used Hidden Immunity Idols to extend his game and became one of the most beloved new-era players.",
        },
        "Rick Devens": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/4/47/S50_Rick_Devens.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Rick Devens competed in Edge of Extinction (S38), finishing 4th after being voted out early and returning via the Edge twist. He won four individual immunity challenges and became one of the most dynamic post-merge players in modern Survivor.",
        },
        "Jenna Lewis-Dougherty": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/e/e4/S50_Jenna_Lewis-Dougherty.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Jenna Lewis competed in Borneo (S1, 8th place) and All-Stars (S8, 3rd place), making her one of the original Survivor players. She orchestrated key eliminations of former winners in All-Stars and is one of the earliest-era players to return for S50.",
        },
        "Emily Flippen": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/3/33/S50_Emily_Flippen.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Emily Flippen competed in Survivor 45, finishing 7th after overcoming an early social struggle on her starting tribe. She rehabilitated her image with the help of unlikely ally Kaleb Gebrewold and integrated with the dominant alliance before being blindsided.",
        },
        "Savannah Louie": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/9/91/S50_Savannah_Louie.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Savannah Louie won Survivor 49 as Sole Survivor through dominant individual immunity performance, winning four challenges to tie the female record. She is the first Sole Survivor to compete immediately on the following season, making her S50 appearance historically unique.",
        },
        "Joe Hunter": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/3/3e/S50_Joe_Hunter.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Joe Hunter competed in Survivor 48, finishing as second runner-up (3rd place) with an impressive 11 challenge wins. He was recognized as one of the physically strongest players on S48, known for his loyalty and emotional gameplay.",
        },
        'Benjamin "Coach" Wade': {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/a/a8/S50_Coach_Wade.jpg/revision/latest/scale-to-width-down/250",
            "bio": 'Benjamin "Coach" Wade competed in three seasons: Tocantins (5th), Heroes vs. Villains (12th), and South Pacific (runner-up). Known as the Dragon Slayer, he is one of the franchise\'s most polarizing and entertaining characters, famous for his stories, meditation, and unshakable self-confidence.',
        },
        "Mike White": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/a/ad/S50_Mike_White.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Mike White competed in David vs. Goliath (S37), finishing as runner-up after orchestrating several late-game blindsides. Outside of Survivor, he is a successful Hollywood writer/producer known for School of Rock, Enlightened, and The White Lotus.",
        },
        "Chrissy Hofbeck": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/b/b3/S50_Chrissy_Hofbeck.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Chrissy Hofbeck competed in Heroes vs. Healers vs. Hustlers (S35), finishing as runner-up in a 5-2-1 jury vote. She demonstrated impressive challenge prowess by winning four individual immunity competitions, tying the record for most wins by a female in a single season.",
        },
        "Charlie Davis": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/8/84/S50_Charlie_Davis.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Charlie Davis competed in Survivor 46, forming a dominant strategic partnership with Maria Shrime Gonzalez that controlled the merged tribe. He reached the Final Three but finished as runner-up in a 5-3-0 jury vote.",
        },
        "Tiffany Ervin": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/e/e0/S50_Tiffany_Nicole_Ervin.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Tiffany Nicole Ervin competed in Survivor 46, finishing 8th after being blindsided when she declined to play her Hidden Immunity Idol. She was a key member of the Yanu alliance and voted for ally Kenzie Petty to win in a 5-3-0 jury vote.",
        },
        "Jonathan Young": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/2/2c/S50_Jonathan_Young.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Jonathan Young competed in Survivor 42, finishing 4th after losing a fire-making challenge to eventual winner Mike Turner. He was recognized as one of the series' most dominant physical challenge performers with 9 total challenge wins, becoming an instant fan favorite.",
        },
        "Dee Valladares": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/2/2b/S50_Dee_Valladares.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Dee Valladares won Survivor 45 as Sole Survivor, orchestrating the dominant Reba Four alliance and reaching Final Tribal Council with strong social, strategic, and physical gameplay. She is regarded as one of the most dominant winners in the modern era.",
        },
        "Kamilla Karthigesu": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/e/e9/S50_Kamilla_Karthigesu.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Kamilla Karthigesu competed in Survivor 48, finishing 4th after losing a fire-making challenge. She won two individual immunity challenges and orchestrated several pivotal blindsides through her strategic gameplay and alliance work.",
        },
        "Colby Donaldson": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/8/82/S50_Colby_Donaldson.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Colby Donaldson competed in three seasons: The Australian Outback (runner-up), All-Stars (12th), and Heroes vs. Villains (5th). He is the series' original hero, known for his dominant challenge performance in Season 2 where he won five individual immunity challenges.",
        },
        "Stephenie LaGrossa Kendrick": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/f/f5/S50_Stephenie_LaGrossa_Kendrick.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Stephenie LaGrossa competed in three seasons: Palau (7th), Guatemala (runner-up), and Heroes vs. Villains (19th). She earned iconic status as the last Ulong member standing in Palau, becoming one of the most memorable and beloved players in franchise history.",
        },
        "Aubry Bracco": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/7/73/S50_Aubry_Bracco.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Aubry Bracco competed in three seasons: Kaoh Rong (runner-up), Game Changers (5th), and Edge of Extinction (16th). She emerged as a major strategic force in her debut season and remains regarded as a standout modern Survivor player.",
        },
        "Angelina Keeley": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/0/00/S50_Angelina_Keeley.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Angelina Keeley competed in David vs. Goliath (S37), finishing as second runner-up after lasting all 39 days. She is best known for her iconic moments including negotiating for rice at an immunity challenge and her infamous request for a departing contestant's jacket.",
        },
        "Genevieve Mushaluk": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/8/82/S50_Genevieve_Mushaluk.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Genevieve Mushaluk competed in Survivor 47, finishing 5th after establishing herself as a sharp strategic player who orchestrated several key blindsides. She is notable as the first Canadian resident to compete in multiple Survivor seasons.",
        },
        "Kyle Fraser": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/d/db/S50_Kyle_Fraser.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Kyle Fraser won Survivor 48 as Sole Survivor with a 5-2-1 jury vote. A music attorney from New York, he demonstrated strong strategic and social gameplay throughout his winning season.",
        },
        "Q Burdette": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/f/f9/S50_Q_Burdette.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Q Burdette competed in Survivor 46, finishing 6th after being blindsided while holding a Hidden Immunity Idol. Known for his intense personality, he famously requested elimination at the final ten before becoming a strategic smokescreen for three consecutive blindsides.",
        },
        "Rizo Velovic": {
            "photo_url": "https://static.wikia.nocookie.net/survivor/images/8/8b/S50_Rizo_Velovic.jpg/revision/latest/scale-to-width-down/250",
            "bio": "Rizo Velovic competed in Survivor 49, finishing 4th after losing a fire-making challenge to Savannah Louie. He wielded a Hidden Immunity Idol effectively to navigate the merge and reach the final four. He is the first contestant of Albanian descent to appear on Survivor.",
        },
    }

    results = []
    async with AsyncSessionLocal() as db:
        season_result = await db.execute(
            select(Season).where(Season.season_number == 50)
        )
        season = season_result.scalar_one_or_none()
        if not season:
            return {"status": "error", "details": ["Season 50 not found. Run /api/seed first."]}

        for name, data in S50_DATA.items():
            castaway_result = await db.execute(
                select(Castaway).where(
                    Castaway.season_id == season.id,
                    Castaway.name == name,
                )
            )
            castaway = castaway_result.scalar_one_or_none()
            if castaway:
                castaway.photo_url = data["photo_url"]
                castaway.bio = data["bio"]
                results.append(f"Updated photo + bio for {name}")
            else:
                results.append(f"Castaway not found: {name}")

        await db.commit()

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
