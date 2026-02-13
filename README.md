# Survivor Fantasy Tracker

Fantasy Survivor scoring engine with dynamic rules, commissioner tools, and leaderboards.

## Stack
- **FastAPI** — async Python API
- **PostgreSQL** — via Railway
- **SQLAlchemy** — async ORM with Alembic migrations
- **JWT Auth** — commissioner vs. player access levels

## Quick Start (Local)

```bash
# Create venv and install
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set up your .env
cp .env.example .env
# Edit .env with your Postgres connection string

# Run
uvicorn app.main:app --reload
```

API docs at `http://localhost:8000/docs`

## Deploy to Railway

1. Push to GitHub
2. Create new Railway project → Deploy from GitHub
3. Add PostgreSQL plugin
4. Set env vars:
   - `DATABASE_URL` — auto-set by Railway Postgres plugin
   - `SECRET_KEY` — generate a random string
5. Deploy

## Commissioner Workflow (Weekly)

1. **POST** `/api/seasons/{id}/episodes` — Create the episode
2. **GET** `/api/seasons/{id}/episodes/{id}/template` — Get blank scoring form with all castaways
3. **POST** `/api/seasons/{id}/episodes/{id}/score` — Submit events, scores auto-calculate
4. **GET** `/api/seasons/{id}/leaderboard` — Check standings

## Season Setup

1. Register commissioner account: `POST /api/auth/register`
2. Create season: `POST /api/seasons` (auto-seeds default scoring rules)
3. Add castaways: `POST /api/seasons/{id}/castaways/bulk`
4. Run draft: `POST /api/seasons/{id}/rosters` for each pick
5. Record first boot predictions: `POST /api/seasons/{id}/predictions`
6. Set season to active: `PATCH /api/seasons/{id}/status`

## Dynamic Scoring Rules

Rules live in the database, not in code. To modify:
- **Add rule**: `POST /api/seasons/{id}/rules`
- **Update rule**: `PATCH /api/seasons/{id}/rules/{rule_id}`
- **Delete rule**: `DELETE /api/seasons/{id}/rules/{rule_id}`
- **Rescore everything**: `POST /api/seasons/{id}/rules/rescore-season`

New seasons can copy rules from a previous season via `copy_rules_from_season_id` when creating.

## Key Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/seasons/{id}/leaderboard` | Fantasy player standings |
| `GET /api/seasons/{id}/castaway-rankings` | All castaways by score |
| `GET /api/seasons/{id}/castaways/{id}/detail` | Episode-by-episode breakdown |
| `GET /api/seasons/{id}/weekly-recap/{ep}` | Episode recap + standings |
| `GET /api/seasons/{id}/episodes/{id}/template` | Blank scoring form |
| `POST /api/seasons/{id}/episodes/{id}/score` | Submit episode scores |
| `POST /api/seasons/{id}/rules/rescore-season` | Recalculate after rule changes |
