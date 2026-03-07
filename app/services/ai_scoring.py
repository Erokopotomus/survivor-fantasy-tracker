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
        "In addition to scoring, you generate an engaging episode title and a 2-4 paragraph "
        "description that all fantasy players can read as a recap. "
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
- For "confessional_count": always set to 0. The commissioner will upload a screenshot to fill real counts.
- If no recap is provided, make your best guess based on typical Survivor episode patterns and flag uncertain values.
- "survive_tribal" = 1 for everyone who was NOT voted out/eliminated this episode.
- Only the eliminated castaway(s) get survive_tribal = 0.

OUTPUT FORMAT (valid JSON, no markdown):
{{
  "episode_title": "Short catchy episode title (4-8 words)",
  "episode_description": "2-4 paragraph engaging recap of the episode written for fantasy players. Cover key moments, tribal dynamics, challenge results, and strategic plays. Write in an entertaining narrator voice.",
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
  "episode_highlights": {{
    "reward_challenge": "Which tribe(s) won reward, and what the reward was. e.g. 'Tuku won 1st, Gata won 2nd'",
    "immunity_challenge": "Which tribe(s) won immunity. e.g. 'Lavo won 1st, Tuku won 2nd'",
    "went_to_tribal": "Which tribe(s) went to tribal council",
    "voted_out": "Who was voted out and by what vote (if known). e.g. 'Jon voted out 4-2'",
    "idols_advantages": "Any idols found, played, or advantages used. 'None' if nothing happened",
    "tribe_compositions": "Current tribe rosters after any swaps/changes. e.g. 'Tuku: Alice, Bob, Carol | Gata: Dan, Eve, Frank'"
  }},
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

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 16384,
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

        # Always flag confessional_count — real counts come from image upload
        if "confessional_count" in clean_events:
            confidence_notes["confessional_count"] = "Upload confessional screenshot to fill"

        results.append({
            "castaway_id": castaway.id,
            "castaway_name": castaway.name,
            "event_data": clean_events,
            "confidence_notes": confidence_notes,
        })

    return results


async def fetch_episode_recap(season_number: int, episode_number: int) -> str | None:
    """Search the web for an episode recap and return text summary.

    Uses Google search to find recap info, then fetches the top result.
    Returns None if anything fails (non-critical — scoring still works without it).
    """
    query = f"Survivor season {season_number} episode {episode_number} recap who was voted out"
    search_url = "https://www.google.com/search"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                search_url,
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0 (compatible; SurvivorFantasyBot/1.0)"},
            )
            resp.raise_for_status()

            # Extract text snippets from search results HTML
            import re
            html = resp.text
            # Pull snippet text from search result divs
            snippets = re.findall(r'<span[^>]*>(.*?)</span>', html)
            # Clean HTML tags and collect useful text
            text_parts = []
            for s in snippets:
                clean = re.sub(r'<[^>]+>', '', s).strip()
                if len(clean) > 40 and any(
                    kw in clean.lower()
                    for kw in ['voted', 'eliminated', 'immunity', 'tribal', 'reward',
                               'challenge', 'idol', 'survivor', 'episode', 'tribe']
                ):
                    text_parts.append(clean)

            if text_parts:
                recap = "\n".join(text_parts[:15])  # Top 15 relevant snippets
                logger.info("Auto-fetched web recap (%d snippets) for S%dE%d",
                           len(text_parts[:15]), season_number, episode_number)
                return recap

    except Exception as e:
        logger.warning("Web recap fetch failed (non-critical): %s", e)

    return None


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

    # Auto-fetch web recap if user didn't provide one
    if not recap_text or not recap_text.strip():
        web_recap = await fetch_episode_recap(season.season_number, episode.episode_number)
        if web_recap:
            recap_text = f"[Auto-fetched from web search results]\n{web_recap}"

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
        "episode_title": ai_response.get("episode_title", ""),
        "episode_description": ai_response.get("episode_description", ""),
        "episode_summary": ai_response.get("episode_summary", ""),
        "episode_highlights": ai_response.get("episode_highlights", {}),
        "eliminated": ai_response.get("eliminated", []),
        "notes": ai_response.get("notes", ""),
    }


async def parse_confessional_image(
    image_base64: str,
    media_type: str,
    castaway_names: list[str],
    episode_number: int,
) -> dict[str, int]:
    """Send a confessional count screenshot to Claude Vision and extract counts.

    Args:
        image_base64: Base64-encoded image data (no data: prefix).
        media_type: MIME type (image/jpeg, image/png, image/webp).
        castaway_names: List of active castaway names to match against.
        episode_number: Episode number for context in the prompt.

    Returns:
        Dict mapping castaway name (as returned by Claude) to confessional count.
    """
    settings = get_settings()
    names_list = "\n".join(f"  - {name}" for name in castaway_names)

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
                "max_tokens": 2048,
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                f"Extract confessional counts from this table for Episode {episode_number}.\n\n"
                                f"Match each person to one of these castaway names:\n{names_list}\n\n"
                                "Return ONLY valid JSON (no markdown fences) in this format:\n"
                                '{"confessionals": [{"name": "Castaway Name", "count": 5}, ...]}\n\n'
                                "Use the exact castaway names from the list above when possible. "
                                "If the table has a column for the specific episode, use that column. "
                                "If it shows cumulative totals, extract the episode-specific count if visible."
                            ),
                        },
                    ],
                }],
            },
        )
        resp.raise_for_status()

    data = resp.json()
    text = ""
    for block in data.get("content", []):
        if block.get("type") == "text":
            text += block["text"]

    # Strip markdown fences if present
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Vision parse failed: %s", text[:500])
        raise ValueError(f"Could not parse confessional image: {e}") from e

    # Build result dict: name -> count
    result = {}
    for entry in parsed.get("confessionals", []):
        name = entry.get("name", "")
        try:
            count = int(entry.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        if name and count >= 0:
            result[name] = count

    return result
