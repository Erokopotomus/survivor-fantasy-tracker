# Prompted Quick Score — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace AI-assisted episode scoring with a step-by-step commissioner prompt wizard that deterministically pre-populates the scoring grid.

**Architecture:** All changes are frontend-only (scoring.html template JS). The prompt wizard collects basic episode facts, then uses client-side logic to map answers → rule_key values in the existing scoring grid. No new backend endpoints. Existing episode create + score endpoints stay identical.

**Tech Stack:** Vanilla JS, Jinja2 template, existing FastAPI endpoints

---

### Task 1: Remove AI scoring UI from scoring.html

**Files:**
- Modify: `app/templates/scoring.html`

**Step 1: Remove AI-related elements from the new episode form**

Replace the entire `new-episode-form` card (lines 18-62) with a simplified version that only has episode number, merge/finale checkboxes, and a single "Create Episode" button. Remove:
- Recap textarea (`new-ep-recap`)
- Confessional screenshot attachment in form (`new-ep-confessional-file`, preview, clear button)
- "Create & Score with AI" button (`ai-create-btn`)
- AI loading spinner
- Keep: episode number input, merge/finale checkboxes, "Create Only (Manual)" button (rename to "Create Episode")

```html
<div id="new-episode-form" class="card hidden">
    <h3 class="card-header">Create New Episode</h3>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem">
        <div class="form-group">
            <label>Episode Number</label>
            <input type="number" id="new-ep-number" min="1">
        </div>
        <div class="form-group">
            <label>Options</label>
            <div style="display:flex;gap:1rem;padding-top:0.25rem">
                <label style="display:flex;align-items:center;gap:0.25rem;font-size:0.8rem">
                    <input type="checkbox" id="new-ep-merge" style="width:auto"> Merge
                </label>
                <label style="display:flex;align-items:center;gap:0.25rem;font-size:0.8rem">
                    <input type="checkbox" id="new-ep-finale" style="width:auto"> Finale
                </label>
            </div>
        </div>
    </div>
    <button class="btn" onclick="submitNewEpisode()" style="padding:0.75rem;font-size:1rem;">Create Episode</button>
</div>
```

**Step 2: Remove AI-related JS functions**

Delete these functions entirely from the `<script>` block in scoring.html:
- `previewConfessionalAttachment()` (lines 156-169)
- `clearConfessionalAttachment()` (lines 171-176)
- `aiCreateEpisode()` (lines 178-260)
- `showAiPanel()` (line 444-446)
- `hideAiPanel()` (lines 448-450)
- `runAiScoring()` (lines 452-479)
- `populateGridFromAi()` (lines 481-520)
- `showAiNotes()` (lines 540-562)
- `renderHighlightsDisplay()` (lines 564-577)
- `toggleEditHighlights()` (lines 579-598)
- `saveHighlights()` (lines 600-616)
- `currentHighlights`, `highlightLabels`, `highlightIcons` variables (lines 522-538)

**Step 3: Simplify renderGrid button panel**

In `renderGrid()`, replace the bottom button panel (lines 404-439) — remove "AI Assist" button, AI recap panel, AI notes card. Keep confessional upload and submit buttons. New panel:

```javascript
// Confessional Upload + Submit buttons
html += `<div style="display:flex;gap:1rem;margin-top:1rem;flex-wrap:wrap;">
    <button class="btn" onclick="document.getElementById('confessional-file').click()" id="confessional-upload-btn" style="flex:1;padding:0.75rem;font-size:1rem;background:linear-gradient(135deg,#d4930d,#b8860b);border:none;">
        &#128247; Upload Confessionals
    </button>
    <input type="file" id="confessional-file" accept="image/jpeg,image/png,image/webp" style="display:none" onchange="uploadConfessionals(this)">
    <span id="confessional-loading" class="hidden"><span class="spinner"></span> Parsing image...</span>
    <button class="btn" onclick="submitScores()" style="flex:2;padding:0.75rem;font-size:1rem">Submit Scores</button>
</div>`;
```

**Step 4: Commit**

```bash
git add app/templates/scoring.html
git commit -m "Remove AI scoring UI from episode scoring page"
```

---

### Task 2: Add prompt wizard UI

**Files:**
- Modify: `app/templates/scoring.html`

**Step 1: Add the prompt wizard container after new-episode-form**

Insert a new hidden div after `new-episode-form` and before `scoring-loading`. This wizard appears after an episode is created and walks the commissioner through prompts.

```html
<div id="quick-score-wizard" class="card hidden">
    <h3 class="card-header">Quick Score</h3>
    <div id="wizard-steps"></div>
    <div style="display:flex;gap:0.75rem;margin-top:1rem;">
        <button class="btn" onclick="submitWizard()" id="wizard-submit-btn">Pre-fill Grid</button>
        <button class="btn btn-outline" onclick="cancelWizard()">Cancel</button>
    </div>
</div>
```

**Step 2: Add wizard rendering function**

This function builds the prompt steps based on whether the episode is pre-merge or post-merge. It reads the template data (castaways + tribes) to populate dropdowns.

```javascript
let wizardEpisodeId = null;
let wizardIsMerge = false;

function showWizard(episodeId, isMerge, template) {
    wizardEpisodeId = episodeId;
    wizardIsMerge = isMerge;
    const container = document.getElementById('wizard-steps');
    const tribes = [...new Set(template.castaways.map(c => c.tribe).filter(Boolean))].sort();
    const activeCastaways = template.castaways.filter(c => !c.status || c.status === 'active');

    let html = '';

    if (!isMerge) {
        // Pre-merge prompts
        html += `<div class="form-group">
            <label>Any tribe changes this episode?</label>
            <input type="text" id="wiz-tribe-changes" placeholder="No" style="width:100%;">
        </div>`;

        html += `<div class="form-group">
            <label>Immunity — 1st Place Tribe</label>
            <select id="wiz-immunity-1st" style="width:auto;min-width:150px;">
                <option value="">Select...</option>
                ${tribes.map(t => `<option value="${t}">${t}</option>`).join('')}
            </select>
        </div>`;

        html += `<div class="form-group">
            <label>Immunity — 2nd Place Tribe</label>
            <select id="wiz-immunity-2nd" style="width:auto;min-width:150px;">
                <option value="">N/A (2-tribe episode)</option>
                ${tribes.map(t => `<option value="${t}">${t}</option>`).join('')}
            </select>
        </div>`;

        html += `<div class="form-group">
            <label>Reward Challenge — Winning Tribe</label>
            <select id="wiz-reward" style="width:auto;min-width:200px;">
                <option value="">No reward challenge</option>
                <option value="same">Same as immunity winner</option>
                ${tribes.map(t => `<option value="${t}">${t}</option>`).join('')}
            </select>
        </div>`;

        html += `<div class="form-group">
            <label>Which tribe went to Tribal Council?</label>
            <select id="wiz-tribal-tribe" style="width:auto;min-width:150px;" onchange="updateVotedOutOptions()">
                <option value="">Select...</option>
                ${tribes.map(t => `<option value="${t}">${t}</option>`).join('')}
            </select>
        </div>`;

        // Voted out dropdown — filtered by selected tribe
        html += `<div class="form-group">
            <label>Who was voted out?</label>
            <select id="wiz-voted-out" style="width:auto;min-width:200px;">
                <option value="">Select tribe first...</option>
            </select>
        </div>`;
    } else {
        // Post-merge prompts
        const castawayOpts = activeCastaways
            .sort((a, b) => a.castaway_name.localeCompare(b.castaway_name))
            .map(c => `<option value="${c.castaway_id}">${c.castaway_name}</option>`)
            .join('');

        html += `<div class="form-group">
            <label>Who won Individual Immunity?</label>
            <select id="wiz-indiv-immunity" style="width:auto;min-width:200px;">
                <option value="">Select...</option>
                ${castawayOpts}
            </select>
        </div>`;

        html += `<div class="form-group">
            <label>Reward Challenge Winner</label>
            <select id="wiz-reward-winner" style="width:auto;min-width:200px;">
                <option value="">No reward challenge</option>
                ${castawayOpts}
            </select>
        </div>`;

        html += `<div class="form-group">
            <label>Who was voted out?</label>
            <select id="wiz-voted-out-merge" style="width:auto;min-width:200px;">
                <option value="">Nobody (no elimination)</option>
                ${castawayOpts}
            </select>
        </div>`;
    }

    // Shared: idols/advantages (both phases)
    html += `<div class="form-group">
        <label>Idols / Advantages found, played, or used?</label>
        <input type="text" id="wiz-idols" placeholder="None" style="width:100%;">
    </div>`;

    container.innerHTML = html;
    document.getElementById('quick-score-wizard').classList.remove('hidden');
}

function cancelWizard() {
    document.getElementById('quick-score-wizard').classList.add('hidden');
    wizardEpisodeId = null;
}
```

**Step 3: Add the voted-out dropdown filter for pre-merge**

When the commissioner selects which tribe went to tribal, filter the voted-out dropdown to only show castaways from that tribe.

```javascript
function updateVotedOutOptions() {
    const tribe = document.getElementById('wiz-tribal-tribe').value;
    const sel = document.getElementById('wiz-voted-out');
    sel.innerHTML = '<option value="">Nobody (no elimination)</option>';

    if (!tribe || !currentTemplate) return;

    const tribeCastaways = currentTemplate.castaways
        .filter(c => c.tribe === tribe && (!c.status || c.status === 'active'))
        .sort((a, b) => a.castaway_name.localeCompare(b.castaway_name));

    for (const c of tribeCastaways) {
        sel.innerHTML += `<option value="${c.castaway_id}">${c.castaway_name}</option>`;
    }
}
```

**Step 4: Commit**

```bash
git add app/templates/scoring.html
git commit -m "Add prompt wizard UI for quick episode scoring"
```

---

### Task 3: Implement wizard → grid pre-population logic

**Files:**
- Modify: `app/templates/scoring.html`

**Step 1: Write the submitWizard function**

This reads all wizard inputs and deterministically fills the scoring grid. It also generates the bullet-list episode description.

```javascript
async function submitWizard() {
    if (!wizardEpisodeId || !currentTemplate) return;
    const alertBox = document.getElementById('scoring-alert');

    // Load the template and render grid first
    document.getElementById('episode-select').value = wizardEpisodeId;
    await loadTemplate();

    const castaways = currentTemplate.castaways;
    const descLines = [];

    if (!wizardIsMerge) {
        // === PRE-MERGE LOGIC ===
        const imm1st = document.getElementById('wiz-immunity-1st').value;
        const imm2nd = document.getElementById('wiz-immunity-2nd').value;
        const rewardVal = document.getElementById('wiz-reward').value;
        const tribalTribe = document.getElementById('wiz-tribal-tribe').value;
        const votedOutId = document.getElementById('wiz-voted-out').value;

        // Determine reward tribe
        const rewardTribe = rewardVal === 'same' ? imm1st : (rewardVal || null);

        // Build description
        let immDesc = imm1st || '?';
        if (imm2nd) immDesc += ` (1st), ${imm2nd} (2nd)`;
        descLines.push(`Immunity: ${immDesc}`);
        if (rewardTribe) descLines.push(`Reward: ${rewardTribe}`);
        else descLines.push('Reward: None');
        if (tribalTribe) descLines.push(`Tribal Council: ${tribalTribe}`);

        // Find voted out castaway name
        const votedOutCastaway = votedOutId ? castaways.find(c => c.castaway_id === parseInt(votedOutId)) : null;
        if (votedOutCastaway) descLines.push(`Voted Out: ${votedOutCastaway.castaway_name}`);

        // Pre-fill grid
        for (const c of castaways) {
            if (c.status && c.status !== 'active') continue;
            const row = document.querySelector(`tr[data-castaway-id="${c.castaway_id}"]`);
            if (!row) continue;

            const tribe = c.tribe;

            // Immunity
            if (tribe === imm1st) setRule(row, 'tribe_immunity_1st', 1);
            if (tribe === imm2nd) setRule(row, 'tribe_immunity_2nd', 1);

            // Reward
            if (rewardTribe && tribe === rewardTribe) setRule(row, 'tribe_reward_win', 1);
            // 2nd place reward: if 3 tribes, immunity 2nd also gets reward 2nd
            // (This is a simplification — commissioner can adjust)

            // Survive tribal
            if (tribe === tribalTribe) {
                if (votedOutId && c.castaway_id === parseInt(votedOutId)) {
                    // Voted out
                    setRule(row, 'survive_tribal', 0);
                    const statusSel = row.querySelector('[data-status]');
                    if (statusSel) statusSel.value = 'eliminated';
                } else {
                    // Survived tribal
                    setRule(row, 'survive_tribal', 1);
                }
            }
        }
    } else {
        // === POST-MERGE LOGIC ===
        const immWinnerId = document.getElementById('wiz-indiv-immunity').value;
        const rewardWinnerId = document.getElementById('wiz-reward-winner').value;
        const votedOutId = document.getElementById('wiz-voted-out-merge').value;

        // Everyone goes to tribal post-merge
        const immWinner = immWinnerId ? castaways.find(c => c.castaway_id === parseInt(immWinnerId)) : null;
        const rewardWinner = rewardWinnerId ? castaways.find(c => c.castaway_id === parseInt(rewardWinnerId)) : null;
        const votedOut = votedOutId ? castaways.find(c => c.castaway_id === parseInt(votedOutId)) : null;

        if (immWinner) descLines.push(`Individual Immunity: ${immWinner.castaway_name}`);
        if (rewardWinner) descLines.push(`Reward: ${rewardWinner.castaway_name}`);
        else descLines.push('Reward: None');
        if (votedOut) descLines.push(`Voted Out: ${votedOut.castaway_name}`);

        for (const c of castaways) {
            if (c.status && c.status !== 'active') continue;
            const row = document.querySelector(`tr[data-castaway-id="${c.castaway_id}"]`);
            if (!row) continue;

            // Individual immunity
            if (immWinnerId && c.castaway_id === parseInt(immWinnerId)) {
                setRule(row, 'individual_immunity_win', 1);
            }

            // Reward
            if (rewardWinnerId && c.castaway_id === parseInt(rewardWinnerId)) {
                setRule(row, 'solo_reward_win', 1);
            }

            // Survive tribal — everyone post-merge goes to tribal
            if (votedOutId && c.castaway_id === parseInt(votedOutId)) {
                setRule(row, 'survive_tribal', 0);
                const statusSel = row.querySelector('[data-status]');
                if (statusSel) statusSel.value = 'eliminated';
            } else {
                setRule(row, 'survive_tribal', 1);
            }
        }
    }

    // Idols/advantages note
    const idolsNote = document.getElementById('wiz-idols').value.trim();
    descLines.push(`Notes: ${idolsNote || 'No idols or advantages played'}`);

    // Save description to episode
    const description = descLines.map(l => `• ${l}`).join('\n');
    try {
        await apiPatch(`/api/seasons/${currentSeasonId}/episodes/${wizardEpisodeId}`, {
            description: description,
        });
    } catch (e) {
        // Non-critical — grid is already filled
        console.warn('Could not save episode description:', e);
    }

    // Show highlights card with the facts
    showQuickScoreHighlights(descLines);

    // Hide wizard
    document.getElementById('quick-score-wizard').classList.add('hidden');
    showAlert(alertBox, 'Grid pre-filled! Add confessionals and review before submitting.', 'success');
}

// Helper to set a rule value in a grid row
function setRule(row, ruleKey, value) {
    const input = row.querySelector(`[data-rule="${ruleKey}"]`);
    if (!input) return;
    if (input.tagName === 'SELECT') {
        input.value = value ? '1' : '0';
    } else {
        input.value = value;
    }
}

// Show a simple highlights card with the wizard facts
function showQuickScoreHighlights(lines) {
    const container = document.getElementById('scoring-grid-container');
    // Remove any existing highlights card
    const existing = document.getElementById('quick-score-highlights');
    if (existing) existing.remove();

    const card = document.createElement('div');
    card.id = 'quick-score-highlights';
    card.className = 'card';
    card.style.marginTop = '1rem';
    card.innerHTML = `<h3 class="card-header">Episode Summary</h3>
        <div style="font-size:0.9rem;line-height:1.8;">
            ${lines.map(l => `<div>${escapeHtml('• ' + l)}</div>`).join('')}
        </div>`;
    container.appendChild(card);
}
```

**Step 2: Wire up submitNewEpisode to launch the wizard**

Modify `submitNewEpisode()` so after creating the episode, it loads the template and shows the wizard instead of just loading the grid.

```javascript
async function submitNewEpisode() {
    const alertBox = document.getElementById('scoring-alert');
    const epNum = document.getElementById('new-ep-number').value;
    if (!epNum) {
        showAlert(alertBox, 'Enter an episode number.');
        return;
    }

    try {
        const isMerge = document.getElementById('new-ep-merge').checked;
        const ep = await apiPost(`/api/seasons/${currentSeasonId}/episodes`, {
            episode_number: parseInt(epNum),
            is_merge: isMerge,
            is_finale: document.getElementById('new-ep-finale').checked,
        });
        showAlert(alertBox, `Episode ${ep.episode_number} created!`, 'success');
        document.getElementById('new-episode-form').classList.add('hidden');
        await loadEpisodes();

        // Load template data for wizard dropdowns
        document.getElementById('episode-select').value = ep.id;
        currentTemplate = await apiGet(`/api/seasons/${currentSeasonId}/episodes/${ep.id}/template`);

        // Show wizard
        showWizard(ep.id, isMerge, currentTemplate);
    } catch (err) {
        showAlert(alertBox, err.message);
    }
}
```

**Step 3: Commit**

```bash
git add app/templates/scoring.html
git commit -m "Implement wizard-to-grid pre-population logic"
```

---

### Task 4: Add PATCH endpoint for episode description (if missing)

**Files:**
- Check: `app/api/episodes.py` — verify the existing PATCH/update endpoint accepts `description`
- Check: `app/schemas/episodes.py` — verify `EpisodeUpdate` schema has `description` field

**Step 1: Verify the endpoint exists**

Read `app/api/episodes.py` and `app/schemas/episodes.py` to confirm:
- There's a PATCH endpoint for episodes
- The `EpisodeUpdate` schema includes `description: Optional[str]`

If missing, add a PATCH endpoint:

```python
@router.patch("/{episode_id}", response_model=EpisodeResponse)
async def update_episode(
    season_id: int,
    episode_id: int,
    body: EpisodeUpdate,
    db: AsyncSession = Depends(get_db),
    _: FantasyPlayer = Depends(require_commissioner),
):
    episode = await _get_episode_or_404(db, season_id, episode_id)
    for field, value in body.dict(exclude_unset=True).items():
        setattr(episode, field, value)
    await db.flush()
    await db.refresh(episode)
    return episode
```

And ensure the schema:
```python
class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_merge: Optional[bool] = None
    is_finale: Optional[bool] = None
```

**Step 2: Commit if changes were needed**

```bash
git add app/api/episodes.py app/schemas/episodes.py
git commit -m "Add PATCH endpoint for episode description"
```

---

### Task 5: Clean up unused backend AI code (optional, low priority)

**Files:**
- Modify: `app/api/episodes.py` — remove `/ai-create` and `/ai-suggest` endpoints
- Keep: `app/services/ai_scoring.py` — keep `parse_confessional_image()` (still used), can remove `generate_scoring_suggestions()`, `build_scoring_prompt()`, `parse_ai_suggestions()`, `fetch_episode_recap()`
- Modify: `app/schemas/episodes.py` — remove `AiScoringRequest`, `AiScoringResponse`, `AiCreateRequest` if no longer referenced

**Note:** This is cleanup. The frontend changes already make these endpoints unreachable from the UI. Can be done later if preferred.

**Step 1: Remove AI endpoints from episodes.py**

Delete the `ai-create` endpoint (POST `/api/seasons/{id}/episodes/ai-create`) and `ai-suggest` endpoint (POST `/api/seasons/{id}/episodes/{id}/ai-suggest`).

**Step 2: Remove unused AI service functions from ai_scoring.py**

Delete: `generate_scoring_suggestions()`, `build_scoring_prompt()`, `parse_ai_suggestions()`, `fetch_episode_recap()`.
Keep: `parse_confessional_image()` (used by confessional upload).

**Step 3: Remove unused schemas**

Delete `AiScoringRequest`, `AiScoringResponse`, `AiCreateRequest` from `app/schemas/episodes.py`.

**Step 4: Commit**

```bash
git add app/api/episodes.py app/services/ai_scoring.py app/schemas/episodes.py
git commit -m "Remove unused AI scoring endpoints and service code"
```

---

### Task 6: Bump cache version and deploy

**Files:**
- Modify: `app/templates/base.html` — bump `style.css?v=` and `app.js?v=`

**Step 1: Bump versions**

Update cache buster in base.html.

**Step 2: Final commit and push**

```bash
git add -A
git commit -m "Prompted quick score: replace AI scoring with commissioner wizard"
git push origin main
```

**Step 3: Verify on production**

1. Go to scoring page
2. Click "+ New Episode"
3. Enter episode number, check/uncheck merge
4. Click "Create Episode"
5. Wizard appears with dropdowns for tribes/castaways
6. Fill in answers, click "Pre-fill Grid"
7. Grid should be pre-populated with correct rule values
8. Add confessionals manually or via screenshot upload
9. Submit scores
