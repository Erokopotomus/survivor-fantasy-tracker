"""
AI-Assisted Episode Scoring — Claude Vision for confessional count extraction.
"""

import json
import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


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
