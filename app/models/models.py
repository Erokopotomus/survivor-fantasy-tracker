from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text,
    UniqueConstraint, CheckConstraint, Enum as SAEnum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum


# --- Enums ---

class SeasonStatus(str, enum.Enum):
    SETUP = "setup"           # Pre-draft, configuring
    DRAFTING = "drafting"     # Draft in progress
    ACTIVE = "active"         # Season airing, scoring weekly
    COMPLETE = "complete"     # Season finished


class CastawayStatus(str, enum.Enum):
    ACTIVE = "active"
    ELIMINATED = "eliminated"
    EVACUATED = "evacuated"
    QUIT = "quit"


class RuleMultiplier(str, enum.Enum):
    BINARY = "binary"              # 0 or 1 — did it happen?
    PER_INSTANCE = "per_instance"  # Count * points (confessionals, etc.)


class RulePhase(str, enum.Enum):
    PRE_MERGE = "pre_merge"
    POST_MERGE = "post_merge"
    ANY = "any"


class PickupType(str, enum.Enum):
    DRAFT = "draft"
    FREE_AGENT = "free_agent"


# --- Models ---

class Season(Base):
    __tablename__ = "seasons"

    id = Column(Integer, primary_key=True, index=True)
    season_number = Column(Integer, unique=True, nullable=False)
    name = Column(String(100), nullable=False)  # e.g. "Survivor 50"
    status = Column(SAEnum(SeasonStatus), default=SeasonStatus.SETUP, nullable=False)
    max_roster_size = Column(Integer, default=4)
    free_agent_pickup_limit = Column(Integer, default=1)  # picks after first boot
    max_times_castaway_drafted = Column(Integer, default=2)  # can't be on more than X rosters
    logo_url = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    castaways = relationship("Castaway", back_populates="season", cascade="all, delete-orphan")
    episodes = relationship("Episode", back_populates="season", cascade="all, delete-orphan", order_by="Episode.episode_number")
    scoring_rules = relationship("ScoringRule", back_populates="season", cascade="all, delete-orphan")
    rosters = relationship("FantasyRoster", back_populates="season", cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="season", cascade="all, delete-orphan")


class Castaway(Base):
    __tablename__ = "castaways"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    name = Column(String(100), nullable=False)
    age = Column(Integer)
    occupation = Column(String(200))
    starting_tribe = Column(String(100))
    current_tribe = Column(String(100))
    bio = Column(Text)
    photo_url = Column(Text)
    status = Column(SAEnum(CastawayStatus), default=CastawayStatus.ACTIVE, nullable=False)
    final_placement = Column(Integer)  # 1 = winner, 2 = runner-up, etc.

    # Relationships
    season = relationship("Season", back_populates="castaways")
    events = relationship("CastawayEpisodeEvent", back_populates="castaway", cascade="all, delete-orphan")
    roster_entries = relationship("FantasyRoster", back_populates="castaway")

    __table_args__ = (
        UniqueConstraint("season_id", "name", name="uq_castaway_season_name"),
    )


class Episode(Base):
    __tablename__ = "episodes"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    episode_number = Column(Integer, nullable=False)
    title = Column(String(200))
    air_date = Column(DateTime)
    is_merge = Column(Boolean, default=False)
    is_finale = Column(Boolean, default=False)
    tribes_active = Column(String(500))  # Comma-separated tribe names
    notes = Column(Text)
    is_scored = Column(Boolean, default=False)  # Has commissioner entered events?

    # Relationships
    season = relationship("Season", back_populates="episodes")
    events = relationship("CastawayEpisodeEvent", back_populates="episode", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("season_id", "episode_number", name="uq_episode_season_number"),
    )


class ScoringRule(Base):
    """
    Fully dynamic scoring rules. Add/modify/delete rules per season
    without touching any code. The scoring engine reads from this table.
    """
    __tablename__ = "scoring_rules"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    rule_key = Column(String(50), nullable=False)  # Machine-readable key, e.g. "survive_tribal"
    rule_name = Column(String(100), nullable=False)  # Display name, e.g. "Survive Tribal Council"
    points = Column(Float, nullable=False)
    multiplier = Column(SAEnum(RuleMultiplier), nullable=False)
    phase = Column(SAEnum(RulePhase), default=RulePhase.ANY, nullable=False)
    description = Column(Text)  # Optional notes, e.g. "can't get duplicate points for same idol"
    is_active = Column(Boolean, default=True)  # Soft-disable rules mid-season if needed
    sort_order = Column(Integer, default=0)  # For display ordering

    # Relationships
    season = relationship("Season", back_populates="scoring_rules")

    __table_args__ = (
        UniqueConstraint("season_id", "rule_key", name="uq_rule_season_key"),
    )


class CastawayEpisodeEvent(Base):
    """
    The core scoring table. Each row = one castaway's events for one episode.
    Instead of hardcoded columns per rule, we store events as a JSON dict
    keyed by rule_key. This means adding a new rule doesn't require a schema migration.

    Example event_data:
    {
        "survive_tribal": 1,
        "tribe_reward_win": 0,
        "tribe_immunity_1st": 1,
        "confessional_count": 7,
        "obtain_advantage": 0,
        ...
    }
    """
    __tablename__ = "castaway_episode_events"

    id = Column(Integer, primary_key=True, index=True)
    castaway_id = Column(Integer, ForeignKey("castaways.id"), nullable=False)
    episode_id = Column(Integer, ForeignKey("episodes.id"), nullable=False)
    event_data = Column(JSON, nullable=False, default=dict)  # Dynamic — keyed by rule_key
    calculated_score = Column(Float)  # Cached score, recalculated on save
    notes = Column(Text)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    castaway = relationship("Castaway", back_populates="events")
    episode = relationship("Episode", back_populates="events")

    __table_args__ = (
        UniqueConstraint("castaway_id", "episode_id", name="uq_castaway_episode"),
    )


class FantasyPlayer(Base):
    __tablename__ = "fantasy_players"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    password_hash = Column(String(200), nullable=False)
    is_commissioner = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    rosters = relationship("FantasyRoster", back_populates="fantasy_player")
    predictions = relationship("Prediction", back_populates="fantasy_player")


class FantasyRoster(Base):
    __tablename__ = "fantasy_rosters"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    fantasy_player_id = Column(Integer, ForeignKey("fantasy_players.id"), nullable=False)
    castaway_id = Column(Integer, ForeignKey("castaways.id"), nullable=False)
    pickup_type = Column(SAEnum(PickupType), default=PickupType.DRAFT, nullable=False)
    draft_position = Column(Integer)  # What pick # was this
    picked_up_after_episode = Column(Integer)  # For free agents, which episode triggered it
    is_active = Column(Boolean, default=True)  # In case you want to allow drops later
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    season = relationship("Season", back_populates="rosters")
    fantasy_player = relationship("FantasyPlayer", back_populates="rosters")
    castaway = relationship("Castaway", back_populates="roster_entries")

    __table_args__ = (
        UniqueConstraint("season_id", "fantasy_player_id", "castaway_id", name="uq_roster_entry"),
    )


class Prediction(Base):
    """Pre-season predictions (first boot, winner, etc.). Extensible via prediction_type."""
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    season_id = Column(Integer, ForeignKey("seasons.id"), nullable=False)
    fantasy_player_id = Column(Integer, ForeignKey("fantasy_players.id"), nullable=False)
    prediction_type = Column(String(50), nullable=False)  # "first_boot", "winner", etc.
    castaway_id = Column(Integer, ForeignKey("castaways.id"), nullable=False)
    is_correct = Column(Boolean)  # Null until resolved
    bonus_points = Column(Float, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    season = relationship("Season", back_populates="predictions")
    fantasy_player = relationship("FantasyPlayer", back_populates="predictions")
    castaway = relationship("Castaway")

    __table_args__ = (
        UniqueConstraint("season_id", "fantasy_player_id", "prediction_type", name="uq_prediction"),
    )
