// === Auth State ===
const AUTH_KEY = 'survivor_auth';

function getAuth() {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch { return null; }
}

function setAuth(data) {
    localStorage.setItem(AUTH_KEY, JSON.stringify(data));
}

function clearAuth() {
    localStorage.removeItem(AUTH_KEY);
}

function logout() {
    clearAuth();
    window.location.href = '/';
}

function requireAuth() {
    const auth = getAuth();
    if (!auth) {
        window.location.href = '/';
        return null;
    }
    return auth;
}

// === API Helpers ===
async function api(path, options = {}) {
    const auth = getAuth();
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (auth) headers['Authorization'] = `Bearer ${auth.access_token}`;

    const resp = await fetch(path, { ...options, headers });

    if (resp.status === 401) {
        clearAuth();
        window.location.href = '/';
        throw new Error('Unauthorized');
    }

    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
    }

    if (resp.status === 204) return null;
    return resp.json();
}

async function apiGet(path) { return api(path); }
async function apiPost(path, body) { return api(path, { method: 'POST', body: JSON.stringify(body) }); }
async function apiPatch(path, body) { return api(path, { method: 'PATCH', body: JSON.stringify(body) }); }
async function apiDelete(path) { return api(path, { method: 'DELETE' }); }

// === Nav Setup ===
function initNav() {
    const auth = getAuth();
    const nav = document.getElementById('main-nav');
    if (!auth || !nav) return;

    nav.style.display = 'flex';
    document.getElementById('nav-username').textContent = auth.display_name;

    // Show commissioner-only links
    if (!auth.is_commissioner) {
        document.querySelectorAll('.commissioner-only').forEach(el => el.style.display = 'none');
    }

    // Highlight active page
    const path = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('href') === path) link.classList.add('active');
    });
}

// === Season Helpers ===
const SEASON_KEY = 'survivor_selected_season';
let _currentSeasonId = null;
let _seasons = null;

async function getSeasons() {
    if (!_seasons) _seasons = await apiGet('/api/seasons');
    return _seasons;
}

async function getCurrentSeasonId() {
    if (_currentSeasonId) return _currentSeasonId;
    const seasons = await getSeasons();
    if (seasons.length === 0) return null;

    // Check localStorage for saved selection
    const saved = localStorage.getItem(SEASON_KEY);
    if (saved && seasons.find(s => s.id === parseInt(saved))) {
        _currentSeasonId = parseInt(saved);
    } else {
        _currentSeasonId = seasons[0].id;
    }
    return _currentSeasonId;
}

function onSeasonChange(seasonId) {
    localStorage.setItem(SEASON_KEY, seasonId);
    _currentSeasonId = parseInt(seasonId);
    _seasons = null;
    window.location.reload();
}

async function populateSeasonSelector() {
    const selector = document.getElementById('season-selector');
    if (!selector) return;
    const seasons = await getSeasons();
    const currentId = await getCurrentSeasonId();
    selector.innerHTML = '';
    for (const s of seasons) {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.name;
        if (s.id === currentId) opt.selected = true;
        selector.appendChild(opt);
    }
}

// === Tribe Helpers ===
const TRIBE_COLORS = {
    'Uli': '#c0392b',
    'Kele': '#2a4a7f',
    'Hina': '#f5b731',
    'Lewatu': '#5c3a6e',
    'Cila': '#e67e22',
    'Kalo': '#14b8a6',
    'Vatu': '#8b5cf6',
};

// === Player Color Helpers ===
const PLAYER_COLORS = {
    'Eric':   { accent: '#2dd4a8', bg: 'rgba(10,35,28,0.9)' },
    'Calvin': { accent: '#e8751a', bg: 'rgba(40,25,12,0.9)' },
    'Jake':   { accent: '#a78bfa', bg: 'rgba(28,18,38,0.9)' },
    'Josh':   { accent: '#f87171', bg: 'rgba(38,14,14,0.9)' },
};

function getPlayerColor(name) {
    return PLAYER_COLORS[name] || { accent: '#c4a265', bg: 'rgba(18,26,11,0.9)' };
}

function getTribeColor(tribe) {
    return TRIBE_COLORS[tribe] || '#6b7280';
}

function getInitials(name) {
    if (!name) return '?';
    return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2);
}

function renderPhoto(photoUrl, name, size = 64) {
    if (photoUrl) {
        return `<img src="${photoUrl}" alt="${name}" referrerpolicy="no-referrer" style="width:${size}px;height:${size}px;object-fit:cover;border-radius:50%;">`;
    }
    const initials = getInitials(name);
    return `<div class="photo-initials" style="width:${size}px;height:${size}px;font-size:${Math.round(size * 0.38)}px;">${initials}</div>`;
}

async function uploadPhotoModal(castawayId, seasonId, onSuccess) {
    // Remove existing modal
    const existing = document.getElementById('photo-upload-modal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.id = 'photo-upload-modal';
    modal.className = 'upload-modal-overlay';
    modal.innerHTML = `
        <div class="upload-modal">
            <div class="upload-modal-header">
                <h3>Upload Photo</h3>
                <button class="btn btn-sm btn-outline" onclick="this.closest('.upload-modal-overlay').remove()">X</button>
            </div>
            <div class="upload-modal-body">
                <input type="file" id="photo-file-input" accept="image/jpeg,image/png,image/webp">
                <p class="text-muted" style="font-size:0.75rem;margin-top:0.5rem;">Max 2 MB. JPEG, PNG, or WebP.</p>
                <div id="upload-preview" class="hidden" style="margin-top:1rem;text-align:center;"></div>
                <div id="upload-error" class="hidden alert alert-error" style="margin-top:0.5rem;"></div>
            </div>
            <div class="upload-modal-footer">
                <button class="btn btn-outline" onclick="this.closest('.upload-modal-overlay').remove()">Cancel</button>
                <button class="btn" id="upload-save-btn" disabled>Save Photo</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });

    let dataUri = null;
    const fileInput = modal.querySelector('#photo-file-input');
    const saveBtn = modal.querySelector('#upload-save-btn');
    const preview = modal.querySelector('#upload-preview');
    const errorDiv = modal.querySelector('#upload-error');

    fileInput.addEventListener('change', async () => {
        const file = fileInput.files[0];
        if (!file) return;
        errorDiv.classList.add('hidden');

        const formData = new FormData();
        formData.append('file', file);

        try {
            const auth = getAuth();
            const resp = await fetch('/api/uploads/image-to-base64', {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${auth.access_token}` },
                body: formData,
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: 'Upload failed' }));
                throw new Error(err.detail);
            }
            const result = await resp.json();
            dataUri = result.data_uri;
            preview.innerHTML = `<img src="${dataUri}" style="max-width:150px;max-height:150px;border-radius:8px;">`;
            preview.classList.remove('hidden');
            saveBtn.disabled = false;
        } catch (err) {
            errorDiv.textContent = err.message;
            errorDiv.classList.remove('hidden');
            saveBtn.disabled = true;
        }
    });

    saveBtn.addEventListener('click', async () => {
        if (!dataUri) return;
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';
        try {
            await apiPatch(`/api/seasons/${seasonId}/castaways/${castawayId}`, { photo_url: dataUri });
            modal.remove();
            if (onSuccess) onSuccess();
        } catch (err) {
            errorDiv.textContent = err.message;
            errorDiv.classList.remove('hidden');
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save Photo';
        }
    });
}

// === UI Helpers ===
function showAlert(container, message, type = 'error') {
    const div = document.createElement('div');
    div.className = `alert alert-${type}`;
    div.textContent = message;
    container.prepend(div);
    setTimeout(() => div.remove(), 5000);
}

function formatScore(score) {
    if (score === null || score === undefined) return '0';
    const num = parseFloat(score);
    const cls = num > 0 ? 'score-positive' : num < 0 ? 'score-negative' : '';
    return `<span class="score ${cls}">${num.toFixed(2)}</span>`;
}

function rankClass(rank) {
    if (rank === 1) return 'rank-1';
    if (rank === 2) return 'rank-2';
    if (rank === 3) return 'rank-3';
    return '';
}

function statusBadge(status) {
    const cls = status === 'active' ? 'badge-active' : 'badge-eliminated';
    return `<span class="badge ${cls}">${status}</span>`;
}

// === On Load ===
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    if (getAuth()) populateSeasonSelector();
});
