from app.scripts.seed import seed
import asyncio

if __name__ == "__main__":
    print("Seeding Survivor Fantasy Tracker...\n")
    asyncio.run(seed())
