# Prompted Quick Score — Design

## Problem

The AI scoring feature tries to guess episode events from web recaps via Claude API. It's unreliable — the commissioner already knows what happened and just needs a fast way to input it.

## Solution

Replace the AI-create flow with a step-by-step prompt wizard that asks basic questions, then deterministically pre-populates the scoring grid. No Claude API call needed for scoring.

## Prompt Flow

### Pre-merge prompts (episode.is_merge = false)

1. Any tribe changes this episode? (text input or "No")
2. Immunity challenge — 1st place tribe? (dropdown of active tribes)
3. Immunity challenge — 2nd place tribe? (dropdown or "N/A")
4. Reward challenge — winning tribe? (dropdown or "Same as immunity" / "No reward")
5. Which tribe went to tribal? (dropdown)
6. Who was voted out? (dropdown of castaways on that tribe)
7. Any idols found, played, or advantages used? (text input or "None")

### Post-merge prompts (episode.is_merge = true OR previous episode was merge)

1. Who won individual immunity? (dropdown of active castaways)
2. Was there a reward challenge? If so, who won? (dropdown or "No")
3. Who was voted out? (dropdown of active castaways)
4. Any idols found, played, or advantages used? (text input or "None")

## Grid Pre-population Logic (deterministic, no AI)

From the prompted answers, fill the scoring grid:

- **Winning tribe members**: `tribal_immunity_win = 1`, `tribal_reward_win = 1` (if same tribe won reward)
- **2nd place tribe members**: `tribal_immunity_win = 1` (they also didn't go to tribal)
- **Losing tribe / tribal attendees**: `survive_tribal = 1` for everyone except voted-out castaway
- **Voted out castaway**: status = "eliminated", `survive_tribal = 0`
- **Individual immunity winner** (post-merge): `individual_immunity_win = 1`
- **Reward winner** (post-merge): `reward_win = 1`
- **Confessionals**: all left at 0 (commissioner fills manually or via screenshot upload)
- **Idol/advantage fields**: left at 0 (commissioner fills manually, text note stored for reference)

## Episode Description (no AI)

Bullet-list format generated from the prompted facts:

```
- Immunity: Kalo (1st), Cila (2nd)
- Reward: Kalo
- Tribal Council: Vatu
- Voted Out: Mike White
- Notes: No idols or advantages played
```

## What Gets Removed

- "Create & Score with AI" button and flow
- Recap textarea
- Web recap auto-fetch (fetch_episode_recap)
- AI scoring prompt/response (generate_scoring_suggestions, build_scoring_prompt, parse_ai_suggestions)
- AI suggest endpoint (/ai-suggest)
- AI recap panel in scoring UI

## What Stays

- Scoring engine, rule system, grid UI, submit flow — unchanged
- `/score` endpoint — identical
- Confessional screenshot upload + Claude Vision parsing
- Manual grid editing
- Episode highlights display (populated from prompted answers instead of AI)

## Architecture

- **Frontend only** for the prompt wizard — no new backend endpoint needed
- Frontend collects answers → applies rule logic → populates grid cells
- Existing `/episodes` POST creates the episode (manual create)
- Existing `/episodes/{id}/score` POST submits the final scores
- Episode description set via existing PATCH or included in create body
