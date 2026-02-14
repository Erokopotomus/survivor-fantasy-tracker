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
