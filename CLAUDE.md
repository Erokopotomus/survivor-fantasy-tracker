# SurvivorTracker — CLAUDE.md

Fantasy Survivor scoring engine with dynamic rules, commissioner tools, and leaderboards.

## Stack
- **FastAPI** (async Python) + **Uvicorn**
- **PostgreSQL** (Railway) + **SQLAlchemy** async ORM + **Alembic** migrations
- **JWT auth** (commissioner vs player roles)
- **Jinja2** server-rendered templates + vanilla JS frontend

## Project Structure
```
SurvivorTracker/
├── app/
│   ├── main.py              # FastAPI app, lifespan, seed endpoints
│   ├── core/
│   │   ├── config.py        # Settings from .env (DB_URL, SECRET_KEY, COMMISSIONER_KEY)
│   │   ├── database.py      # AsyncSessionLocal, engine, Base, get_db()
│   │   └── security.py      # bcrypt hashing, JWT create/decode (HS256, 24h expiry)
│   ├── api/
│   │   ├── deps.py          # get_current_user, require_commissioner (DI deps)
│   │   ├── auth.py          # /api/auth/* — register, login, me, players
│   │   ├── seasons.py       # /api/seasons/* — CRUD + status transitions
│   │   ├── castaways.py     # /api/seasons/{id}/castaways/* — CRUD + detail
│   │   ├── episodes.py      # /api/seasons/{id}/episodes/* — CRUD + template + score + PATCH
│   │   ├── rules.py         # /api/seasons/{id}/rules/* — CRUD + rescore
│   │   ├── rosters.py       # /api/seasons/{id}/rosters/* — draft + free-agent
│   │   ├── leaderboard.py   # /api/seasons/{id}/leaderboard, castaway-rankings, weekly-recap
│   │   ├── predictions.py   # /api/seasons/{id}/predictions/* — CRUD + resolve
│   │   ├── uploads.py       # /api/uploads/image-to-base64 (commissioner, 2MB max)
│   │   └── pages.py         # HTML page routes (/, /dashboard, /cast, /scoring, etc.)
│   ├── models/
│   │   └── models.py        # All 9 SQLAlchemy models + enums
│   ├── schemas/              # Pydantic schemas (auth, seasons, castaways, episodes, rules, rosters, leaderboard, predictions)
│   ├── services/
│   │   ├── ai_scoring.py    # Claude Vision: confessional count parsing only (AI scoring removed)
│   │   ├── scoring_engine.py # Core scoring logic, leaderboard, recalculate
│   │   └── rule_seeder.py   # 30 default rules + seed/copy functions
│   ├── scripts/
│   │   └── seed_s49.py      # Complete S49 seed (18 castaways, 13 episodes, all events)
│   ├── templates/            # Jinja2 HTML (login, dashboard, cast, scoring, draft, etc.)
│   └── static/               # css/style.css, js/app.js
├── alembic/                  # Migration config (currently uses create_all on startup)
├── docs/plans/               # Design docs and implementation plans
├── tests/                    # Empty, ready for pytest
├── run.py                    # Entry point: uvicorn app.main:app
├── Dockerfile                # Python 3.12-slim
├── Procfile                  # web: python run.py
└── railway.toml              # Healthcheck, restart policy
```

## Database Models (9 tables)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `seasons` | One per Survivor season | `season_number` (unique), `status` (setup/drafting/active/complete), `max_roster_size`, `logo_url` |
| `fantasy_players` | User accounts | `username` (unique), `display_name`, `password_hash`, `is_commissioner` |
| `castaways` | Contestants per season | `season_id` FK, `name`, `starting_tribe`, `current_tribe`, `status` (active/eliminated/evacuated/quit), `final_placement` |
| `episodes` | Episodes per season | `season_id` FK, `episode_number`, `title`, `description`, `is_merge`, `is_finale`, `is_scored` |
| `scoring_rules` | Dynamic rules per season | `season_id` FK, `rule_key`, `points`, `multiplier` (binary/per_instance), `phase` (pre_merge/post_merge/any), `is_active` |
| `castaway_episode_events` | Scoring data | `castaway_id` + `episode_id` FKs, `event_data` (JSON dict keyed by rule_key), `calculated_score` |
| `fantasy_rosters` | Draft picks / free agents | `season_id` + `fantasy_player_id` + `castaway_id` FKs, `pickup_type` (draft/free_agent), `is_active` |
| `predictions` | Pre-season predictions | `prediction_type` (first_boot/winner/etc.), `castaway_id` FK, `is_correct`, `bonus_points` |
| `chat_messages` | League chat | `season_id` FK, `fantasy_player_id` FK, `message`, `created_at` |

## Scoring Engine

Rules live in the database, not code. The engine reads active rules per season:
- **Binary rules**: truthy value = full points (e.g., `survive_tribal` = 1pt)
- **Per-instance rules**: count * points (e.g., `confessional_count` * 0.25 = variable pts)
- **Phase filtering**: rules can be pre-merge only, post-merge only, or any
- **Rescore**: `POST /api/seasons/{id}/rules/rescore-season` recalculates everything after rule changes

30 default rules seeded on season creation (see `rule_seeder.py`), including:
- Tribal/immunity/reward wins, confessionals, idol plays, merge bonus
- Placement points (winner 25pts down to 5th place 1.5pts)
- Penalties (quit -15, evacuated -7, go home with idol -4)

## Season State Machine
```
setup → drafting → active ⇄ complete
```
- **setup**: Add castaways, tweak rules, make predictions
- **drafting**: Process draft picks
- **active**: Weekly scoring, free agent pickups
- **complete**: Resolve predictions, final standings (can reopen to active)

## Commissioner Weekly Workflow (Quick Score Wizard)
1. Go to Score Episode page → click "+ New Episode"
2. Enter episode number, title, merge/finale flags → click "Create Episode"
3. **Quick Score Wizard** appears with prompts based on pre/post merge:
   - **Pre-merge**: immunity 1st/2nd tribe, reward tribe, tribal tribe, voted out (filtered by tribe)
   - **Post-merge**: individual immunity winner, reward winner, voted out
   - Both: idols/advantages text note
4. Click "Pre-fill Grid" → wizard deterministically populates scoring grid
5. Upload confessional screenshot → Claude Vision fills confessional counts
6. Edit any values manually, write/edit episode summary (supports Markdown formatting)
7. Click "Submit Scores"
8. `DELETE /api/seasons/{id}/episodes/{id}` — Delete episode + cascade all scoring data (red button on scoring page)

## Confessional Count Vision
- **Endpoint**: `POST /api/seasons/{id}/episodes/{id}/parse-confessionals`
- Upload PNG/JPEG/WebP screenshot (max 2MB) of confessional count table
- Claude Vision extracts counts, fuzzy-matches names to active castaways
- Only remaining AI feature (AI episode scoring was removed in favor of Quick Score Wizard)

## Dashboard
- **Leaderboard** (left) + **League Chat** (right) — 2-column grid, stacks on mobile
- **Rosters** — full width, player-colored cards with tribe color-coded castaways
- **Latest Episode Recap** — split layout: rich-text recap (left) + tribe-grouped score table (right)
  - Recap supports Markdown: `**bold**`, `## Header`, ALL CAPS headers, `- bullets`, blank line spacing
  - Score table grouped by tribe with color-coded headers, "Drafted By" column

## Theme
- **Tribal Council Light** — warm parchment background, burned-edge parchment cards
- Tribal geometric diamond watermark pattern (3.5% opacity)
- Torch silhouettes flanking content (HTML divs, hidden on mobile)
- Flame gradient left border on cards (ember-red → orange → yellow)
- Twisted rope texture border under nav
- Firelight flicker animation on edge vignettes
- Cinzel + Almendra + Source Sans Pro fonts
- Tribe colors: `TRIBE_COLORS` in `app.js` — do NOT redeclare in page scripts

## Environment Variables
```bash
DATABASE_URL=postgresql://...          # Railway provides this (auto-transformed to +asyncpg)
SECRET_KEY=<random-string>             # JWT signing key
COMMISSIONER_KEY=<random-string>       # Required to register as commissioner
ANTHROPIC_API_KEY=<api-key>            # Required for confessional vision parsing
DEBUG=False                            # SQLAlchemy echo (optional)
```

## Dev Quick Start
```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit with your Postgres URL
uvicorn app.main:app --reload
# API docs: http://localhost:8000/docs
```

## Deploy (Railway)
- Push to GitHub → Railway project → add PostgreSQL plugin
- Set `SECRET_KEY` and `COMMISSIONER_KEY` env vars
- `railway.toml` configures healthcheck at `/health`, restart on failure
- Railway App: `https://web-production-72cf1.up.railway.app`

## Auth
- **Register**: `POST /api/auth/register` (pass `commissioner_key` to get commissioner role)
- **Login**: `POST /api/auth/login` (form) or `/login/json` (JSON) → JWT token (24h)
- **Dependencies**: `get_current_user` (any authed user), `require_commissioner` (403 if not)

## Seed Data
- `POST /api/seed` — Creates 4 players (eric/calvin/jake/josh) + Season 50 + default rules
- `POST /api/seed-s49` — Full Season 49: 18 castaways, 13 episodes, all event data
- `POST /api/seed-s49-photos` — Populates S49 castaway photo URLs

## Key Patterns
- All DB access is async (`AsyncSession`, `await db.execute(...)`)
- Upsert pattern for episode scoring (check existing → update or insert → flush)
- `Base.metadata.create_all()` on startup (idempotent) + inline `ALTER TABLE IF NOT EXISTS` for schema evolution
- CORS wide open (all origins) — tighten for production
- Enums: `SeasonStatus`, `CastawayStatus`, `RuleMultiplier`, `RulePhase`, `PickupType`
- CSS cache busting via `?v=N` query params on static assets in `base.html`

## Gotchas
- `DATABASE_URL` gets `postgresql://` swapped to `postgresql+asyncpg://` automatically in config
- No Alembic migration files yet — schema managed via `create_all` + inline ALTERs in `main.py` lifespan
- `event_data` is a JSON column keyed by `rule_key` strings — must match `scoring_rules.rule_key` exactly
- Season delete only allowed in `setup` status
- Predictions only allowed during `setup` or `drafting`
- Free agent pickups enforce `free_agent_pickup_limit` and `max_times_castaway_drafted` per season
- Free agent scoring only counts episodes AFTER `picked_up_after_episode` — no retroactive points
- `survive_tribal` rule: only awarded to castaways who attended tribal and survived (not everyone who wasn't voted out)
- Scoring grid is tribe-grouped and color-coded; colors come from `TRIBE_COLORS` in `app.js` — do NOT redeclare that const in page scripts
- Scoring template for scored episodes includes eliminated castaways (for re-editing); unscored episodes show only active castaways
- `border-image` CSS kills `border-radius` — flame gradient card borders use `::before` pseudo-element instead
- Card `::before`/`::after` pseudo-elements must NOT have z-index or overflow:hidden — causes content clipping
