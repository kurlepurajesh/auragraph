/**
 * Shared utilities used across multiple components.
 * Import from here instead of redefining in each component.
 */
import { store } from '../store';
import { setUser, addToast } from '../store';

export const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export function authHeaders() {
    const token = localStorage.getItem('ag_token') || 'demo-token';
    return { Authorization: `Bearer ${token}` };
}

/**
 * Drop-in replacement for fetch() that:
 *  - Attaches the Bearer token automatically
 *  - On 401: clears local auth, shows a toast, and redirects to login
 *  - Returns the raw Response so callers can handle other status codes themselves
 */
export async function apiFetch(url, options = {}) {
    const headers = { ...authHeaders(), ...(options.headers || {}) };
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
        localStorage.removeItem('ag_token');
        localStorage.removeItem('ag_user');
        localStorage.removeItem('ag_demo_issued_at');
        store.dispatch(setUser(null));
        store.dispatch(addToast({
            kind: 'error',
            title: 'Session expired',
            message: 'Your session has expired. Please log in again.',
            duration: 8000,
        }));
        // Redirect after a short delay so the toast is readable
        setTimeout(() => { window.location.href = '/'; }, 1800);
    }
    return res;
}

export function loadDoubts(notebookId) {
    try { return JSON.parse(localStorage.getItem(`ag_doubts_${notebookId}`) || '[]'); }
    catch { return []; }
}

export function saveDoubts(notebookId, doubts) {
    try { localStorage.setItem(`ag_doubts_${notebookId}`, JSON.stringify(doubts)); }
    catch { }
}
