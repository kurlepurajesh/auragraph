/**
 * Shared utilities used across multiple components.
 * Import from here instead of redefining in each component.
 */

export const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function authHeaders() {
    const token = localStorage.getItem('ag_token') || 'demo-token';
    return { Authorization: `Bearer ${token}` };
}

export function loadDoubts(notebookId) {
    try { return JSON.parse(localStorage.getItem(`ag_doubts_${notebookId}`) || '[]'); }
    catch { return []; }
}

export function saveDoubts(notebookId, doubts) {
    try { localStorage.setItem(`ag_doubts_${notebookId}`, JSON.stringify(doubts)); }
    catch { }
}
