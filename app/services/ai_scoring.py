"""
AI-Assisted Episode Scoring — Uses Claude API to pre-fill the scoring grid.

Commissioner pastes an episode recap (optional), Claude returns structured
scoring suggestions. The commissioner reviews and adjusts before submitting.
"""

import json
import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.models.models import (
    Season, Episode, Castaway, CastawayStatus, ScoringRule,
    RuleMultiplier, RulePhase,
)
from app.services.scoring_engine import get_active_rules

logger = logging.getLogger(__name__)


def build_scoring_prompt(
    season: Season,
    episode: Episode,
    castaways: list[Castaway],
    rules: list[ScoringRule],
    recap_text: str | None = None,
) -> tuple[str, str]:
    """Build system + user prompts for Claude scoring assistant.

    Returns (system_prompt, user_prompt).
    """
    system_prompt = (
        "You are a Survivor episode scoring assistant for a fantasy league. "
        "You will be given a list of castaways, scoring rules, and episode context. "
        "Respond with valid JSON only — no markdown fences, no commentary outside the JSON."
    )

    # Build castaway list
    castaway_lines = []
    for c in castaways:
        tribe = c.current_tribe or c.starting_tribe or "Unknown"
        castaway_lines.append(f"  - {c.name} (tribe: {tribe}, status: {c.status.value})")
    castaway_block = "\n".join(castaway_lines)

    # Build rules list
    rule_lines = []
    for r in rules:
        phase = r.phase.value if hasattr(r.phase, "value") else r.phase
        mult = r.multiplier.value if hasattr(r.multiplier, "value") else r.multiplier
        pts = f"+{r.points}" if r.points > 0 else str(r.points)
        desc = f" — {r.description}" if r.description else ""
        rule_lines.append(
            f"  - rule_key: \"{r.rule_key}\", name: \"{r.rule_name}\", "
            f"type: {mult}, phase: {phase}, points: {pts}{desc}"
        )
    rules_block = "\n".join(rule_lines)

    # Episode context
    ep_context_parts = [f"Season {season.season_number}, Episode {episode.episode_number}"]
    if episode.title:
        ep_context_parts.append(f'Title: "{episode.title}"')
    if episode.is_merge:
        ep_context_parts.append("This is the MERGE episode")
    if episode.is_finale:
        ep_context_parts.append("This is the FINALE episode")
    if episode.tribes_active:
        ep_context_parts.append(f"Active tribes: {episode.tribes_active}")
    ep_context = ". ".join(ep_context_parts) + "."

    # Recap
    recap_section = ""
    if recap_text and recap_text.strip():
        recap_section = f"""
EPISODE RECAP (use this as your primary source):
{recap_text.strip()}
"""

    user_prompt = f"""Score the following Survivor episode.

EPISODE: {ep_context}

CASTAWAYS (active this episode):
{castaway_block}

SCORING RULES (use these exact rule_key values):
{rules_block}
{recap_section}
INSTRUCTIONS:
- For each castaway, provide values for ALL rule_keys.
- Binary rules: use 1 (happened) or 0 (did not happen). Do NOT omit rules — output 0 if it didn't happen.
- Per-instance rules: use the count (0 if none).
- For "confessional_count": estimate based on the recap if available, and flag it as low-confidence.
- If no recap is provided, make your best guess based on typical Survivor episode patterns and flag uncertain values.
- "survive_tribal" = 1 for everyone who was NOT voted out/eliminated this episode.
- Only the eliminated castaway(s) get survive_tribal = 0.

OUTPUT FORMAT (valid JSON, no markdown):
{{
  "suggestions": [
    {{
      "castaway_name": "Name",
      "events": {{
        "rule_key": value,
        ...
      }},
      "confidence_notes": {{
        "rule_key": "reason this is uncertain"
      }}
    }}
  ],
  "episode_summary": "Brief 1-2 sentence summary of the episode",
  "eliminated": ["Name of eliminated castaway(s)"],
  "notes": "Any caveats about the scoring suggestions"
}}"""

    return system_prompt, user_prompt


async def call_claude_api(system_prompt: str, user_prompt: str) -> dict:
    """POST to Anthropic Messages API and parse JSON response.

    Raises:
        httpx.TimeoutException: on timeout
        ValueError: on unparseable response
        httpx.HTTPStatusError: on API error
    """
    settings = get_settings()

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )
        resp.raise_for_status()

    data = resp.json()
    # Extract text from content blocks
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    # Strip markdown code fences if present
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse AI response as JSON: %s", text[:500])
        raise ValueError(f"AI returned invalid JSON: {e}") from e


def parse_ai_suggestions(
    ai_response: dict,
    castaways: list[Castaway],
    rules: list[ScoringRule],
) -> list[dict]:
    """Validate and map AI response to castaway IDs and known rule_keys.

    Returns list of dicts with castaway_id, castaway_name, event_data, confidence_notes.
    """
    # Build lookup maps
    name_to_castaway: dict[str, Castaway] = {}
    for c in castaways:
        name_to_castaway[c.name.lower()] = c

    valid_rule_keys = {r.rule_key for r in rules}
    binary_keys = {r.rule_key for r in rules if r.multiplier == RuleMultiplier.BINARY}

    results = []
    for suggestion in ai_response.get("suggestions", []):
        raw_name = suggestion.get("castaway_name", "")

        # Try exact match (case-insensitive)
        castaway = name_to_castaway.get(raw_name.lower())

        # Substring fallback — match if the AI used a first name or partial
        if not castaway:
            for key, c in name_to_castaway.items():
                if raw_name.lower() in key or key in raw_name.lower():
                    castaway = c
                    break

        if not castaway:
            logger.warning("AI suggested unknown castaway: %s", raw_name)
            continue

        # Filter and validate events
        events = suggestion.get("events", {})
        clean_events = {}
        for rule_key, value in events.items():
            if rule_key not in valid_rule_keys:
                continue
            try:
                val = float(value)
            except (TypeError, ValueError):
                val = 0
            # Clamp binary to 0/1
            if rule_key in binary_keys:
                val = 1 if val else 0
            else:
                val = max(0, int(val))
            clean_events[rule_key] = val

        # Confidence notes
        confidence_notes = {}
        for rule_key, note in suggestion.get("confidence_notes", {}).items():
            if rule_key in valid_rule_keys:
                confidence_notes[rule_key] = str(note)

        # Always flag confessional_count as low-confidence if not already flagged
        if "confessional_count" in clean_events and "confessional_count" not in confidence_notes:
            confidence_notes["confessional_count"] = "Estimated — verify manually"

        results.append({
            "castaway_id": castaway.id,
            "castaway_name": castaway.name,
            "event_data": clean_events,
            "confidence_notes": confidence_notes,
        })

    return results


async def generate_scoring_suggestions(
    db: AsyncSession,
    season_id: int,
    episode_id: int,
    recap_text: str | None = None,
) -> dict:
    """Full orchestrator: load data -> prompt -> call API -> parse -> return.

    Returns dict matching AiScoringResponse schema.
    """
    # Load season
    season_result = await db.execute(select(Season).where(Season.id == season_id))
    season = season_result.scalar_one()

    # Load episode
    ep_result = await db.execute(
        select(Episode).where(Episode.id == episode_id, Episode.season_id == season_id)
    )
    episode = ep_result.scalar_one()

    # Load active castaways
    cast_result = await db.execute(
        select(Castaway)
        .where(Castaway.season_id == season_id, Castaway.status == CastawayStatus.ACTIVE)
        .order_by(Castaway.name)
    )
    castaways = list(cast_result.scalars().all())

    # Load active rules
    rules = await get_active_rules(db, season_id)

    # Build prompt
    system_prompt, user_prompt = build_scoring_prompt(
        season, episode, castaways, rules, recap_text
    )

    # Call Claude
    ai_response = await call_claude_api(system_prompt, user_prompt)

    # Parse and validate
    suggestions = parse_ai_suggestions(ai_response, castaways, rules)

    return {
        "episode_id": episode.id,
        "episode_number": episode.episode_number,
        "suggestions": suggestions,
        "episode_summary": ai_response.get("episode_summary", ""),
        "eliminated": ai_response.get("eliminated", []),
        "notes": ai_response.get("notes", ""),
    }
