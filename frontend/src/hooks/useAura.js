/**
 * useAura — AuraGraph gamification engine
 *
 * XP earned:
 *   +10  per correct quiz answer  (×multiplier)
 *   +50  completing a quiz        (flat, no count multiplier)
 *   +25  bonus for ≥80% score     (flat)
 *   +5   per text highlight added (×multiplier)
 *   +15  per doubt asked          (×multiplier)
 *
 * Badges (6 tiers) unlock note themes and XP multipliers.
 */

import { useState, useCallback, useEffect } from 'react';
import { API, authHeaders } from '../components/utils';

const LEGACY_STORAGE_KEY = 'ag_aura_v2';

// ── Badge definitions ─────────────────────────────────────────────────────────

export const BADGES = [
    {
        id: 'seeker',
        name: 'Seeker',
        emoji: '✨',
        minXp: 0,
        color: '#4F46E5',
        bg: '#EEF2FF',
        border: '#C7D2FE',
        desc: 'Your journey begins.',
        perk: 'Default note theme',
        theme: null,
    },
    {
        id: 'scholar',
        name: 'Scholar',
        emoji: '📚',
        minXp: 1500,
        color: '#cfa4bd',
        bg: '#EFF6FF',
        border: '#BFDBFE',
        desc: 'Knowledge is taking root.',
        perk: 'Unlocks Parchment note theme',
        theme: 'ember',
    },
    {
        id: 'voyager',
        name: 'Voyager',
        emoji: '🧭',
        minXp: 5000,
        color: '#7caeef',
        bg: '#F5F3FF',
        border: '#DDD6FE',
        desc: 'Charting unknown territory.',
        perk: 'Unlocks Midnight note theme',
        theme: 'sky',
    },
    {
        id: 'luminary',
        name: 'Luminary',
        emoji: '✨',
        minXp: 12000,
        color: '#dfed8d',
        bg: '#FFFBEB',
        border: '#FDE68A',
        desc: 'Your understanding shines.',
        perk: 'Unlocks Aurora note theme',
        theme: 'lumen',
    },
    {
        id: 'oracle',
        name: 'Oracle',
        emoji: '🔮',
        minXp: 25000,
        color: '#c589b8',
        bg: '#F0FDF4',
        border: '#BBF7D0',
        desc: 'You see what others miss.',
        perk: 'Unlocks Forest theme + XP ×1.5',
        theme: 'aurora',
        multiplier: 1.5,
    },
    {
        id: 'sage',
        name: 'Sage',
        emoji: '🌟',
        minXp: 50000,
        color: '#98e4c3',
        bg: '#FDF2F8',
        border: '#FBCFE8',
        desc: 'Mastery beyond measure.',
        perk: 'All themes + XP ×2 + Gold border',
        theme: 'sage',
        multiplier: 2,
    },
];

// ── Note theme definitions ────────────────────────────────────────────────────

export const NOTE_THEMES = {
      default: {
        name: 'Default',
        cardBg: '#FEFDF9',
        cardBorder: '#E8E0F0',
        rings: 'linear-gradient(180deg,#F5F0FF,#EDE9FE)',
        ringBorder: '#DDD6FE',
        ringDot: '#C4B5FD',
        marginLine: 'linear-gradient(180deg,#C4B5FD 0%,#A78BFA 50%,#C4B5FD 100%)',
        scrollBg: 'linear-gradient(160deg,#EEE8F8 0%,#F0EDF8 40%,#EBE5F5 100%)',
    },
  
  
        ember: {
    name: 'Ember',
    cardBg: '#FFFFFF',
    cardBorder: '#F5C4B8',
    rings: 'linear-gradient(180deg,#FDEDE9,#F8D2C9)',
    ringBorder: '#F2A08F',
    ringDot: '#E76F51',
    marginLine: 'linear-gradient(180deg,#F2A08F 0%,#E76F51 50%,#F2A08F 100%)',
    scrollBg: 'linear-gradient(160deg,#FDEDE9 0%,#F8D2C9 40%,#F3BFB3 100%)',
},
  
      sky: {
    name: 'Sky',
    cardBg: '#FFFFFF',
    cardBorder: '#BFE4FA',
    rings: 'linear-gradient(180deg,#EAF6FD,#D8EEFB)',
    ringBorder: '#A6DBF8',
    ringDot: '#7CC9F5',
    marginLine: 'linear-gradient(180deg,#A6DBF8 0%,#7CC9F5 50%,#A6DBF8 100%)',
    scrollBg: 'linear-gradient(160deg,#EAF6FD 0%,#D8EEFB 40%,#CFE9FA 100%)',
},


   lumen: {
        name: 'Lumen',
        cardBg: '#ffffff',
        cardBorder: '#F0F2C2',
        rings: 'linear-gradient(180deg,#FBFBEA,#F5F6D6)',
        ringBorder: '#F2F4B8',
        ringDot: '#E6E8A3',
        marginLine: 'linear-gradient(180deg,#F2F4B8 0%,#E6E8A3 50%,#F2F4B8 100%)',
        scrollBg: 'linear-gradient(160deg,#FBFBEA 0%,#F5F6D6 40%,#EEF0C8 100%)',
    },
  aurora: {
        name: 'Aurora',
        cardBg: '#FFFFFF',
        cardBorder: '#F5C2C5',
        rings: 'linear-gradient(180deg,#FCEDEE,#F8D7D9)',
        ringBorder: '#F3B1B5',
        ringDot: '#E5979B',
        marginLine: 'linear-gradient(180deg,#F3B1B5 0%,#E5979B 50%,#F3B1B5 100%)',
        scrollBg: 'linear-gradient(160deg,#FCEDEE 0%,#F8D7D9 40%,#F3C6C9 100%)',
    },

 
    sage: {
    name: 'Sage',
    cardBg: '#FFFFFF',
    cardBorder: '#B7EACB',
    rings: 'linear-gradient(180deg,#EAFBF1,#D7F5E4)',
    ringBorder: '#9FE3B8',
    ringDot: '#6FCF97',
    marginLine: 'linear-gradient(180deg,#9FE3B8 0%,#6FCF97 50%,#9FE3B8 100%)',
    scrollBg: 'linear-gradient(160deg,#EAFBF1 0%,#D7F5E4 40%,#CFF3DC 100%)',
},
  


   
};

// Accent palette used by notebook/studyhub/quiz surfaces.
export const NOTE_THEME_ACCENTS = {
    default: {
        primary: '#7C3AED',
        soft: '#EDE9FE',
        border: '#DDD6FE',
        deep: '#4C1D95',
        medium: '#5B21B6',
        vivid: '#6D28D9',
        ring: '#C4B5FD',
        rgb: '124,58,237',
    },
     lumen: {
       primary: '#E6E8A3',
        soft: '#FBFBEA',
        border: '#F0F2C2',
        deep: '#A6A85A',
        medium: '#C6C86E',
        vivid: '#DCDD85',
        ring: '#F2F4B8',
        rgb: '230,232,163',
    },
   
   ember: {
    primary: '#E76F51',
    soft: '#FDEDE9',
    border: '#F5C4B8',
    deep: '#8C2F1C',
    medium: '#C8553D',
    vivid: '#D9482B',
    ring: '#F2A08F',
    rgb: '231,111,81',
},
    aurora: {
          primary: '#E5979B',
        soft: '#FCEDEE',
        border: '#F5C2C5',
        deep: '#A9444A',
        medium: '#C76C72',
        vivid: '#E06A70',
        ring: '#F3B1B5',
        rgb: '229,151,155',
    },
    
    sage: {
    primary: '#6FCF97',
    soft: '#EAFBF1',
    border: '#B7EACB',
    deep: '#2F7A4F',
    medium: '#4FBF7A',
    vivid: '#57D68D',
    ring: '#9FE3B8',
    rgb: '111,207,151',
},
 sky: {
    primary: '#7CC9F5',
    soft: '#EAF6FD',
    border: '#BFE4FA',
    deep: '#2F6F94',
    medium: '#5BB6E6',
    vivid: '#4FC3F7',
    ring: '#A6DBF8',
    rgb: '124,201,245',
},
};



// ── Helpers ───────────────────────────────────────────────────────────────────

function load() {
    const key = _storageKey();
    try {
        const current = JSON.parse(localStorage.getItem(key) || 'null');
        if (current) return { ...defaultData(), ...current };

        // IMPORTANT: Do not migrate legacy global Aura data into a user-scoped key.
        // Otherwise, a brand-new account can incorrectly inherit previous user's XP.
        if (key !== LEGACY_STORAGE_KEY) {
            return defaultData();
        }

        const legacy = JSON.parse(localStorage.getItem(LEGACY_STORAGE_KEY) || 'null');
        if (legacy) {
            const merged = { ...defaultData(), ...legacy };
            localStorage.setItem(key, JSON.stringify(merged));
            return merged;
        }
        return defaultData();
    } catch { return defaultData(); }
}

function defaultData() {
    return { xp: 0, quizzesCompleted: 0, correctAnswers: 0, totalAnswers: 0, doubtsAsked: 0, highlightsAdded: 0, activeTheme: 'default' };
}

function save(data) {
    try { localStorage.setItem(_storageKey(), JSON.stringify(data)); } catch { }
}

function _storageKey() {
    try {
        const raw = localStorage.getItem('ag_user');
        const user = raw ? JSON.parse(raw) : null;
        if (user?.id) return `${LEGACY_STORAGE_KEY}_${user.id}`;
    } catch { }
    return LEGACY_STORAGE_KEY;
}

function _hasMeaningfulProgress(d) {
    if (!d) return false;
    return (
        (Number(d.xp) || 0) > 0 ||
        (Number(d.quizzesCompleted) || 0) > 0 ||
        (Number(d.correctAnswers) || 0) > 0 ||
        (Number(d.totalAnswers) || 0) > 0 ||
        (Number(d.doubtsAsked) || 0) > 0 ||
        (Number(d.highlightsAdded) || 0) > 0 ||
        (d.activeTheme && d.activeTheme !== 'default')
    );
}

async function _fetchServerAura() {
    try {
        const res = await fetch(`${API}/api/aura`, { headers: authHeaders() });
        if (!res.ok) return null;
        const data = await res.json();
        return data?.aura || null;
    } catch {
        return null;
    }
}

async function _pushServerAura(auraData) {
    try {
        await fetch(`${API}/api/aura`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify(auraData),
        });
    } catch {
        // offline-safe: local persistence remains source-of-truth fallback
    }
}

export function getAuraData() { return load(); }

export function getBadge(xp) {
    // BADGES are in ascending order — walk until we find the highest earned
    let badge = BADGES[0];
    for (const b of BADGES) {
        if (xp >= b.minXp) badge = b;
        else break;
    }
    return badge;
}

export function getNextBadge(xp) {
    return BADGES.find(b => b.minXp > xp) || null;
}

export function getMultiplier(xp) {
    return getBadge(xp).multiplier || 1;
}

export function getUnlockedThemes(xp) {
    const themes = ['default'];
    for (const b of BADGES) {
        if (xp >= b.minXp && b.theme) themes.push(b.theme);
    }
    return themes;
}

export function getActiveTheme() {
    const data = load();
    const unlocked = getUnlockedThemes(data.xp);
    const theme = data.activeTheme || 'default';
    return unlocked.includes(theme) ? theme : 'default';
}

export function setActiveTheme(themeId) {
    const data = load();
    save({ ...data, activeTheme: themeId });
}

/**
 * Award XP for a given action.
 * 
 * IMPORTANT: For quiz_complete and high_score_bonus, `count` is ignored —
 * these are flat bonuses regardless of quiz length. For correct_answer,
 * count = number of correct answers to batch.
 */
export function awardXP(reason, count = 1) {
    const data = load();
    const multiplier = getMultiplier(data.xp);

    // Flat bonuses: never multiply by count
    const flatReasons = ['quiz_complete', 'high_score_bonus'];
    const baseXp = {
        correct_answer: 10,
        quiz_complete: 50,
        high_score_bonus: 25,
        highlight: 5,
        doubt: 15,
    }[reason] || 0;

    const effectiveCount = flatReasons.includes(reason) ? 1 : count;
    const gained = Math.round(baseXp * effectiveCount * multiplier);

    if (gained === 0) return { newXp: data.xp, gained: 0, badgeUp: null };

    const oldBadge = getBadge(data.xp);
    const newXp = data.xp + gained;
    const newBadge = getBadge(newXp);

    const updates = { xp: newXp };
    if (reason === 'correct_answer') {
        updates.correctAnswers = (data.correctAnswers || 0) + count;
        updates.totalAnswers = (data.totalAnswers || 0) + count;
    }
    if (reason === 'quiz_complete') updates.quizzesCompleted = (data.quizzesCompleted || 0) + 1;
    if (reason === 'highlight')     updates.highlightsAdded  = (data.highlightsAdded  || 0) + 1;
    if (reason === 'doubt')         updates.doubtsAsked      = (data.doubtsAsked      || 0) + 1;

    save({ ...data, ...updates });

    const badgeUp = newBadge.id !== oldBadge.id ? newBadge : null;
    return { newXp, gained, badgeUp };
}

// ── React hook ────────────────────────────────────────────────────────────────

export function useAura() {
    const [data, setData] = useState(load);

    useEffect(() => {
        let cancelled = false;
        (async () => {
            const local = load();
            const remote = await _fetchServerAura();
            if (!remote) return;

            const remoteData = { ...defaultData(), ...remote };
            const remoteHas = _hasMeaningfulProgress(remoteData);
            const localHas = _hasMeaningfulProgress(local);

            if (!remoteHas && localHas) {
                await _pushServerAura(local);
                if (!cancelled) setData(local);
                return;
            }

            save(remoteData);
            if (!cancelled) setData(remoteData);
        })();
        return () => { cancelled = true; };
    }, []);

    const refresh = useCallback(() => setData(load()), []);

    const award = useCallback((reason, count = 1) => {
        const result = awardXP(reason, count);
        const latest = load();
        setData(latest);
        _pushServerAura(latest);
        return result;
    }, []);

    const badge         = getBadge(data.xp);
    const nextBadge     = getNextBadge(data.xp);
    const unlockedThemes = getUnlockedThemes(data.xp);
    const progressToNext = nextBadge
        ? Math.min(100, Math.round(((data.xp - badge.minXp) / (nextBadge.minXp - badge.minXp)) * 100))
        : 100;

    return {
        data,
        badge,
        nextBadge,
        unlockedThemes,
        progressToNext,
        award,
        refresh,
        setTheme: (t) => {
            setActiveTheme(t);
            const latest = load();
            setData(latest);
            _pushServerAura(latest);
        },
        activeTheme: getActiveTheme(),
    };
}
