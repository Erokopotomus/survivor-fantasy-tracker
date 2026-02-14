"""
Seed script — Populates Season 49 with real cast, episodes, rosters, and scoring data.
Run via POST /api/seed-s49 or: python -m app.scripts.seed_s49
"""
import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal, engine, Base
from app.core.security import hash_password
from app.models.models import (
    FantasyPlayer, Season, SeasonStatus, Castaway, CastawayStatus,
    Episode, ScoringRule, CastawayEpisodeEvent, FantasyRoster, PickupType,
)
from app.services.rule_seeder import seed_default_rules
from app.services.scoring_engine import score_episode_event

# ── Season 49 Castaways ──────────────────────────────────────────────────────

CASTAWAYS = [
    # ULI tribe (Red)
    {"name": "Savannah Louie", "age": 31, "occupation": "Former Reporter", "starting_tribe": "Uli", "status": "active", "final_placement": 1},
    {"name": "Sage Ahrens-Nichols", "age": 30, "occupation": "Clinical Social Worker", "starting_tribe": "Uli", "status": "active", "final_placement": 3},
    {"name": "Rizo Velovic", "age": 25, "occupation": "Tech Sales", "starting_tribe": "Uli", "status": "eliminated", "final_placement": 4},
    {"name": "Jawan Pitts", "age": 28, "occupation": "Video Editor", "starting_tribe": "Uli", "status": "eliminated", "final_placement": 8},
    {"name": "Nate Moore", "age": 47, "occupation": "Film Producer", "starting_tribe": "Uli", "status": "eliminated", "final_placement": 11},
    {"name": "Shannon Fairweather", "age": 27, "occupation": "Wellness Specialist", "starting_tribe": "Uli", "status": "eliminated", "final_placement": 12},
    # KELE tribe (Blue)
    {"name": "Sophi Balerdi", "age": 27, "occupation": "Entrepreneur", "starting_tribe": "Kele", "status": "active", "final_placement": 2},
    {"name": "Alex Moore", "age": 26, "occupation": "Political Comms Director", "starting_tribe": "Kele", "status": "eliminated", "final_placement": 9},
    {"name": "Jeremiah Ing", "age": 38, "occupation": "Global Events Manager", "starting_tribe": "Kele", "status": "eliminated", "final_placement": 15},
    {"name": "Jake Latimer", "age": 35, "occupation": "Correctional Officer", "starting_tribe": "Kele", "status": "evacuated", "final_placement": 16},
    {"name": "Annie Davis", "age": 49, "occupation": "Musician", "starting_tribe": "Kele", "status": "eliminated", "final_placement": 17},
    {"name": "Nicole Mazullo", "age": 26, "occupation": "Financial Crime Consultant", "starting_tribe": "Kele", "status": "eliminated", "final_placement": 18},
    # HINA tribe (Yellow)
    {"name": "Kristina Mills", "age": 35, "occupation": "MBA Career Coach", "starting_tribe": "Hina", "status": "eliminated", "final_placement": 5},
    {"name": "Steven Ramm", "age": 35, "occupation": "Rocket Scientist", "starting_tribe": "Hina", "status": "eliminated", "final_placement": 6},
    {"name": "Sophie Segreti", "age": 31, "occupation": "Strategy Associate", "starting_tribe": "Hina", "status": "eliminated", "final_placement": 7},
    {"name": "MC Chukwujekwu", "age": 29, "occupation": "Fitness Trainer", "starting_tribe": "Hina", "status": "eliminated", "final_placement": 10},
    {"name": "Matt Williams", "age": 52, "occupation": "Airport Ramp Agent", "starting_tribe": "Hina", "status": "eliminated", "final_placement": 14},
    {"name": "Jason Treul", "age": 32, "occupation": "Law Clerk", "starting_tribe": "Hina", "status": "eliminated", "final_placement": 13},
]

# ── Episodes ─────────────────────────────────────────────────────────────────

EPISODES = [
    {"episode_number": 1, "title": "Act One of a Horror Film", "air_date": "2025-09-24", "is_merge": False, "is_finale": False, "tribes_active": "Uli,Kele,Hina"},
    {"episode_number": 2, "title": "Cinema", "air_date": "2025-10-01", "is_merge": False, "is_finale": False, "tribes_active": "Uli,Kele,Hina"},
    {"episode_number": 3, "title": "Lovable Losers", "air_date": "2025-10-08", "is_merge": False, "is_finale": False, "tribes_active": "Uli,Kele,Hina"},
    {"episode_number": 4, "title": "Go Kick Rocks, Bro", "air_date": "2025-10-15", "is_merge": False, "is_finale": False, "tribes_active": "Uli,Kele,Hina"},
    {"episode_number": 5, "title": "I'm a Wolf, Baby", "air_date": "2025-10-22", "is_merge": False, "is_finale": False, "tribes_active": "Uli,Kele,Hina"},
    {"episode_number": 6, "title": "The Devil's Shoes", "air_date": "2025-10-29", "is_merge": False, "is_finale": False, "tribes_active": "Uli,Kele,Hina"},
    {"episode_number": 7, "title": "Blood Will Be Drawn", "air_date": "2025-11-05", "is_merge": True, "is_finale": False, "tribes_active": "Lewatu"},
    {"episode_number": 8, "title": "Hot Grim Reaper", "air_date": "2025-11-12", "is_merge": False, "is_finale": False, "tribes_active": "Lewatu"},
    {"episode_number": 9, "title": "If You're Loyal to All...", "air_date": "2025-11-19", "is_merge": False, "is_finale": False, "tribes_active": "Lewatu"},
    {"episode_number": 10, "title": "Huge Dose of Bamboozle", "air_date": "2025-11-26", "is_merge": False, "is_finale": False, "tribes_active": "Lewatu"},
    {"episode_number": 11, "title": "Cherry On Top", "air_date": "2025-12-03", "is_merge": False, "is_finale": False, "tribes_active": "Lewatu"},
    {"episode_number": 12, "title": "The Die Is Cast", "air_date": "2025-12-10", "is_merge": False, "is_finale": False, "tribes_active": "Lewatu"},
    {"episode_number": 13, "title": "A Fever Dream", "air_date": "2025-12-17", "is_merge": False, "is_finale": True, "tribes_active": "Lewatu"},
]

# ── Episode Events (scoring data per castaway per episode) ───────────────────
# Keys match rule_keys from the scoring rules.
# Only active castaways in each episode get events.
# Eliminated castaway gets their final episode but no more after that.

def _build_episode_events():
    """
    Build realistic scoring events for each episode.
    Returns dict: { episode_number: { castaway_name: {event_data} } }
    """
    events = {}

    # ── Episode 1: "Act One of a Horror Film" ──
    # Nicole voted out (Kele loses). Uli wins reward+immunity, Hina 2nd.
    events[1] = {
        "Savannah Louie":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
        "Sage Ahrens-Nichols":  {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Jawan Pitts":          {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Nate Moore":           {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 5},
        "Shannon Fairweather":  {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Sophi Balerdi":        {"survive_tribal": 1, "tribe_reward_2nd": 0, "tribe_immunity_2nd": 0, "confessional_count": 4},
        "Alex Moore":           {"survive_tribal": 1, "tribe_reward_2nd": 0, "tribe_immunity_2nd": 0, "confessional_count": 3},
        "Jeremiah Ing":         {"survive_tribal": 1, "tribe_reward_2nd": 0, "tribe_immunity_2nd": 0, "confessional_count": 2},
        "Jake Latimer":         {"survive_tribal": 1, "tribe_reward_2nd": 0, "tribe_immunity_2nd": 0, "confessional_count": 3},
        "Annie Davis":          {"survive_tribal": 1, "tribe_reward_2nd": 0, "tribe_immunity_2nd": 0, "confessional_count": 2},
        "Nicole Mazullo":       {"survive_tribal": 0, "tribe_reward_2nd": 0, "tribe_immunity_2nd": 0, "confessional_count": 5},
        "Kristina Mills":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 4},
        "Sophie Segreti":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "MC Chukwujekwu":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Matt Williams":        {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 4},
        "Jason Treul":          {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
    }

    # ── Episode 2: "Cinema" ──
    # Annie voted out (Kele loses again). Hina wins immunity, Uli 2nd.
    events[2] = {
        "Savannah Louie":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Sage Ahrens-Nichols":  {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Rizo Velovic":         {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Jawan Pitts":          {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Nate Moore":           {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 4},
        "Shannon Fairweather":  {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 1},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 5},
        "Alex Moore":           {"survive_tribal": 1, "confessional_count": 3},
        "Jeremiah Ing":         {"survive_tribal": 1, "confessional_count": 2},
        "Jake Latimer":         {"survive_tribal": 1, "confessional_count": 2},
        "Annie Davis":          {"survive_tribal": 0, "confessional_count": 4},
        "Kristina Mills":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Steven Ramm":          {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 5},
        "Sophie Segreti":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "MC Chukwujekwu":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
        "Matt Williams":        {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Jason Treul":          {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
    }

    # ── Episode 3: "Lovable Losers" ──
    # Jake evacuated (Kele). Jeremiah plays idol. Uli wins immunity, Hina 2nd.
    events[3] = {
        "Savannah Louie":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Sage Ahrens-Nichols":  {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Rizo Velovic":         {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
        "Jawan Pitts":          {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3, "go_on_journey": 1},
        "Nate Moore":           {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Shannon Fairweather":  {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Sophi Balerdi":        {"survive_tribal": 0, "confessional_count": 4},
        "Alex Moore":           {"survive_tribal": 0, "confessional_count": 3},
        "Jeremiah Ing":         {"survive_tribal": 0, "confessional_count": 3, "obtain_immunity_idol": 1, "play_idol_correctly": 1},
        "Jake Latimer":         {"survive_tribal": 0, "confessional_count": 2, "evacuated": 1},
        "Kristina Mills":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Steven Ramm":          {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Sophie Segreti":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "MC Chukwujekwu":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Matt Williams":        {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 4},
        "Jason Treul":          {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
    }

    # ── Episode 4: "Go Kick Rocks, Bro" ──
    # Matt voted out (Hina loses). Kele wins immunity, Uli 2nd. Jawan wins advantage on journey.
    events[4] = {
        "Savannah Louie":       {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Sage Ahrens-Nichols":  {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Jawan Pitts":          {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 4, "obtain_advantage": 1, "go_on_journey": 1},
        "Nate Moore":           {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Shannon Fairweather":  {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Sophi Balerdi":        {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 5},
        "Alex Moore":           {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Jeremiah Ing":         {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 4},
        "Steven Ramm":          {"survive_tribal": 1, "confessional_count": 5},
        "Sophie Segreti":       {"survive_tribal": 1, "confessional_count": 3},
        "MC Chukwujekwu":       {"survive_tribal": 1, "confessional_count": 4},
        "Matt Williams":        {"survive_tribal": 0, "confessional_count": 5},
        "Jason Treul":          {"survive_tribal": 1, "confessional_count": 2},
    }

    # ── Episode 5: "I'm a Wolf, Baby" ──
    # Jason voted out (Hina loses). Uli wins immunity, Kele 2nd.
    events[5] = {
        "Savannah Louie":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
        "Sage Ahrens-Nichols":  {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Jawan Pitts":          {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Nate Moore":           {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
        "Shannon Fairweather":  {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "Sophi Balerdi":        {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 4},
        "Alex Moore":           {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Jeremiah Ing":         {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 1, "confessional_count": 5},
        "Sophie Segreti":       {"survive_tribal": 1, "confessional_count": 3},
        "MC Chukwujekwu":       {"survive_tribal": 1, "confessional_count": 4},
        "Jason Treul":          {"survive_tribal": 0, "confessional_count": 3},
    }

    # ── Episode 6: "The Devil's Shoes" ──
    # Shannon voted out (Uli loses). Hina wins immunity, Kele 2nd.
    events[6] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 5},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 1, "confessional_count": 3},
        "Jawan Pitts":          {"survive_tribal": 1, "confessional_count": 3},
        "Nate Moore":           {"survive_tribal": 1, "confessional_count": 5, "obtain_immunity_idol": 1},
        "Shannon Fairweather":  {"survive_tribal": 0, "confessional_count": 3},
        "Sophi Balerdi":        {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 3},
        "Alex Moore":           {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Jeremiah Ing":         {"survive_tribal": 0, "tribe_reward_2nd": 1, "tribe_immunity_2nd": 1, "confessional_count": 2},
        "Kristina Mills":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
        "Sophie Segreti":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 2},
        "MC Chukwujekwu":       {"survive_tribal": 0, "tribe_reward_win": 1, "tribe_immunity_1st": 1, "confessional_count": 4},
    }

    # ── Episode 7: "Blood Will Be Drawn" (MERGE into Lewatu) ──
    # Nate voted out. He plays idol (no votes negated). Merge episode.
    events[7] = {
        "Savannah Louie":       {"survive_tribal": 1, "make_merge": 1, "confessional_count": 5},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "make_merge": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 1, "make_merge": 1, "confessional_count": 4},
        "Jawan Pitts":          {"survive_tribal": 1, "make_merge": 1, "confessional_count": 3},
        "Nate Moore":           {"survive_tribal": 0, "make_merge": 1, "confessional_count": 6, "play_idol_correctly": 0, "played_idol_incorrectly": 1},
        "Sophi Balerdi":        {"survive_tribal": 1, "make_merge": 1, "confessional_count": 5, "individual_immunity_win": 0},
        "Alex Moore":           {"survive_tribal": 1, "make_merge": 1, "confessional_count": 3},
        "Kristina Mills":       {"survive_tribal": 1, "make_merge": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 1, "make_merge": 1, "confessional_count": 5},
        "Sophie Segreti":       {"survive_tribal": 1, "make_merge": 1, "confessional_count": 2},
        "MC Chukwujekwu":       {"survive_tribal": 1, "make_merge": 1, "confessional_count": 4},
    }

    # ── Episode 8: "Hot Grim Reaper" ──
    # MC voted out. Savannah wins immunity.
    events[8] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 6, "individual_immunity_win": 1},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 1, "confessional_count": 3},
        "Jawan Pitts":          {"survive_tribal": 1, "confessional_count": 4},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 5},
        "Alex Moore":           {"survive_tribal": 1, "confessional_count": 3},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 1, "confessional_count": 4, "go_on_journey": 1},
        "Sophie Segreti":       {"survive_tribal": 1, "confessional_count": 3},
        "MC Chukwujekwu":       {"survive_tribal": 0, "confessional_count": 5},
    }

    # ── Episode 9: "If You're Loyal to All..." ──
    # Alex voted out. Steven wins immunity.
    events[9] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 4},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 3},
        "Rizo Velovic":         {"survive_tribal": 1, "confessional_count": 4},
        "Jawan Pitts":          {"survive_tribal": 1, "confessional_count": 3},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 5, "solo_reward_win": 1, "picked_for_reward": 0},
        "Alex Moore":           {"survive_tribal": 0, "confessional_count": 5},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 3, "picked_for_reward": 1},
        "Steven Ramm":          {"survive_tribal": 1, "confessional_count": 5, "individual_immunity_win": 1},
        "Sophie Segreti":       {"survive_tribal": 1, "confessional_count": 3},
    }

    # ── Episode 10: "Huge Dose of Bamboozle" ──
    # Jawan voted out. Sophi wins immunity.
    events[10] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 5},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 4},
        "Rizo Velovic":         {"survive_tribal": 1, "confessional_count": 3},
        "Jawan Pitts":          {"survive_tribal": 0, "confessional_count": 5, "used_advantage_correctly": 0},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 6, "individual_immunity_win": 1},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 1, "confessional_count": 4, "go_on_journey": 1},
        "Sophie Segreti":       {"survive_tribal": 1, "confessional_count": 3},
    }

    # ── Episode 11: "Cherry On Top" ──
    # Sophie Segreti voted out. Savannah wins immunity. Steven gets vote blocker on journey.
    events[11] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 5, "individual_immunity_win": 1},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 4},
        "Rizo Velovic":         {"survive_tribal": 1, "confessional_count": 3},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 5},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 3},
        "Steven Ramm":          {"survive_tribal": 1, "confessional_count": 5, "obtain_advantage": 1, "go_on_journey": 1},
        "Sophie Segreti":       {"survive_tribal": 0, "confessional_count": 4},
    }

    # ── Episode 12: "The Die Is Cast" ──
    # Steven voted out. Sophi wins immunity.
    events[12] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 5},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 4},
        "Rizo Velovic":         {"survive_tribal": 1, "confessional_count": 3},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 6, "individual_immunity_win": 1},
        "Kristina Mills":       {"survive_tribal": 1, "confessional_count": 4},
        "Steven Ramm":          {"survive_tribal": 0, "confessional_count": 6, "used_advantage_correctly": 1},
    }

    # ── Episode 13: "A Fever Dream" (FINALE) ──
    # Kristina voted out at F5. Rizo eliminated at fire. Savannah wins fire.
    # Final 3: Savannah (winner), Sophi (2nd), Sage (3rd).
    # Sophi wins final immunity.
    events[13] = {
        "Savannah Louie":       {"survive_tribal": 1, "confessional_count": 8, "overall_winner": 1, "win_fire_making": 1},
        "Sage Ahrens-Nichols":  {"survive_tribal": 1, "confessional_count": 5, "third_place": 1},
        "Rizo Velovic":         {"survive_tribal": 0, "confessional_count": 4, "fourth_place": 1},
        "Sophi Balerdi":        {"survive_tribal": 1, "confessional_count": 7, "runner_up": 1, "individual_immunity_win": 1},
        "Kristina Mills":       {"survive_tribal": 0, "confessional_count": 5, "fifth_place": 1},
    }

    return events


# ── Fantasy Rosters (assign castaways to the 4 players) ─────────────────────
# Each player gets 4 castaways (draft style)

FANTASY_ROSTERS = {
    "eric": [
        {"castaway": "Savannah Louie", "draft_position": 1},
        {"castaway": "Steven Ramm", "draft_position": 5},
        {"castaway": "Alex Moore", "draft_position": 9},
        {"castaway": "Nicole Mazullo", "draft_position": 13},
    ],
    "calvin": [
        {"castaway": "Sophi Balerdi", "draft_position": 2},
        {"castaway": "Kristina Mills", "draft_position": 6},
        {"castaway": "Jawan Pitts", "draft_position": 10},
        {"castaway": "Matt Williams", "draft_position": 14},
    ],
    "jake": [
        {"castaway": "Rizo Velovic", "draft_position": 3},
        {"castaway": "Nate Moore", "draft_position": 7},
        {"castaway": "Sophie Segreti", "draft_position": 11},
        {"castaway": "Annie Davis", "draft_position": 15},
    ],
    "josh": [
        {"castaway": "Sage Ahrens-Nichols", "draft_position": 4},
        {"castaway": "MC Chukwujekwu", "draft_position": 8},
        {"castaway": "Shannon Fairweather", "draft_position": 12},
        {"castaway": "Jason Treul", "draft_position": 16},
    ],
}


async def seed_s49():
    """Seed Season 49 with complete data."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    results = []

    async with AsyncSessionLocal() as db:
        # ── 1. Ensure fantasy players exist ──
        for pdata in [
            {"username": "eric", "display_name": "Eric", "is_commissioner": True},
            {"username": "calvin", "display_name": "Calvin", "is_commissioner": False},
            {"username": "jake", "display_name": "Jake", "is_commissioner": False},
            {"username": "josh", "display_name": "Josh", "is_commissioner": False},
        ]:
            existing = await db.execute(
                select(FantasyPlayer).where(FantasyPlayer.username == pdata["username"])
            )
            if not existing.scalar_one_or_none():
                db.add(FantasyPlayer(
                    username=pdata["username"],
                    display_name=pdata["display_name"],
                    password_hash=hash_password("survivor50"),
                    is_commissioner=pdata["is_commissioner"],
                ))
                results.append(f"Created player: {pdata['display_name']}")
            else:
                results.append(f"Player '{pdata['username']}' already exists")
        await db.flush()

        # ── 2. Create Season 49 ──
        existing_season = await db.execute(
            select(Season).where(Season.season_number == 49)
        )
        season = existing_season.scalar_one_or_none()
        if season:
            results.append("Season 49 already exists — skipping all season data")
            await db.commit()
            return results

        season = Season(
            season_number=49,
            name="Survivor 49",
            status=SeasonStatus.COMPLETE,
            max_roster_size=4,
            free_agent_pickup_limit=1,
            max_times_castaway_drafted=2,
        )
        db.add(season)
        await db.flush()
        await db.refresh(season)
        results.append(f"Created Season 49 (id={season.id})")

        # ── 3. Scoring rules ──
        rules = await seed_default_rules(db, season.id)
        results.append(f"Created {len(rules)} scoring rules")

        # ── 4. Castaways ──
        castaway_map = {}  # name -> Castaway object
        for cdata in CASTAWAYS:
            status_enum = CastawayStatus(cdata["status"])
            castaway = Castaway(
                season_id=season.id,
                name=cdata["name"],
                age=cdata["age"],
                occupation=cdata["occupation"],
                starting_tribe=cdata["starting_tribe"],
                current_tribe="Lewatu" if cdata["final_placement"] <= 11 else cdata["starting_tribe"],
                status=status_enum,
                final_placement=cdata["final_placement"],
            )
            db.add(castaway)
            castaway_map[cdata["name"]] = castaway
        await db.flush()
        for c in castaway_map.values():
            await db.refresh(c)
        results.append(f"Created {len(castaway_map)} castaways")

        # ── 5. Episodes ──
        episode_map = {}  # episode_number -> Episode object
        for edata in EPISODES:
            episode = Episode(
                season_id=season.id,
                episode_number=edata["episode_number"],
                title=edata["title"],
                air_date=datetime.strptime(edata["air_date"], "%Y-%m-%d"),
                is_merge=edata["is_merge"],
                is_finale=edata["is_finale"],
                tribes_active=edata["tribes_active"],
                is_scored=True,
            )
            db.add(episode)
            episode_map[edata["episode_number"]] = episode
        await db.flush()
        for ep in episode_map.values():
            await db.refresh(ep)
        results.append(f"Created {len(episode_map)} episodes")

        # ── 6. Episode events (scoring) ──
        all_events = _build_episode_events()
        event_count = 0
        for ep_num, castaway_events in all_events.items():
            episode = episode_map[ep_num]
            for castaway_name, event_data in castaway_events.items():
                if castaway_name not in castaway_map:
                    continue
                castaway = castaway_map[castaway_name]
                event = CastawayEpisodeEvent(
                    castaway_id=castaway.id,
                    episode_id=episode.id,
                    event_data=event_data,
                )
                db.add(event)
                event_count += 1
        await db.flush()

        # Score all events
        for ep_num in sorted(all_events.keys()):
            episode = episode_map[ep_num]
            events_result = await db.execute(
                select(CastawayEpisodeEvent).where(
                    CastawayEpisodeEvent.episode_id == episode.id
                )
            )
            for event in events_result.scalars().all():
                await score_episode_event(db, event, rules=rules, episode=episode)

        results.append(f"Created and scored {event_count} castaway episode events")

        # ── 7. Fantasy rosters ──
        roster_count = 0
        for username, picks in FANTASY_ROSTERS.items():
            player_result = await db.execute(
                select(FantasyPlayer).where(FantasyPlayer.username == username)
            )
            player = player_result.scalar_one()
            for pick in picks:
                castaway = castaway_map[pick["castaway"]]
                roster = FantasyRoster(
                    season_id=season.id,
                    fantasy_player_id=player.id,
                    castaway_id=castaway.id,
                    pickup_type=PickupType.DRAFT,
                    draft_position=pick["draft_position"],
                    is_active=True,
                )
                db.add(roster)
                roster_count += 1
        await db.flush()
        results.append(f"Created {roster_count} fantasy roster entries")

        await db.commit()

    results.append("Season 49 seed complete!")
    return results


if __name__ == "__main__":
    print("Seeding Survivor 49...\n")
    results = asyncio.run(seed_s49())
    for r in results:
        print(f"  {r}")
