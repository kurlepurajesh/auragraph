import { useState, useEffect, useCallback, useRef } from 'react';
import { API, authHeaders, loadDoubts, saveDoubts } from '../components/utils';

/**
 * Manages the doubts/Q&A log for a notebook.
 *
 * Persistence fix: doubts are now synced to the backend DB, so they survive
 * across devices and browser storage clears. localStorage is kept as an
 * offline cache/fallback.
 *
 * @param {string} id - Notebook ID
 */
export function useDoubtsLog(id) {
    const [doubtsLog, setDoubtsLogRaw] = useState(() => loadDoubts(id));
    const activeNotebookRef = useRef(id);

    // On notebook change: reset state from notebook-scoped local cache immediately.
    useEffect(() => {
        activeNotebookRef.current = id;
        setDoubtsLogRaw(loadDoubts(id));
    }, [id]);

    // Sync from backend (authoritative source) for each notebook id.
    useEffect(() => {
        if (!id) return;
        let cancelled = false;
        fetch(`${API}/api/notebooks/${id}/doubts`, { headers: authHeaders() })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (cancelled || activeNotebookRef.current !== id) return;
                const next = Array.isArray(data?.doubts) ? data.doubts : [];
                setDoubtsLogRaw(next);
                saveDoubts(id, next);
            })
            .catch(() => {/* offline — localStorage already loaded */});
        return () => { cancelled = true; };
    }, [id]);

    /** Persist one entry to backend + local cache. */
    const addDoubt = useCallback((entry) => {
        setDoubtsLogRaw(prev => {
            const updated = [entry, ...prev.filter(d => d.id !== entry.id)];
            saveDoubts(id, updated);
            return updated;
        });
        fetch(`${API}/api/notebooks/${id}/doubts`, {
            method: 'POST',
            headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify(entry),
        }).catch(() => {});
    }, [id]);

    /**
     * Drop-in replacement for plain setDoubtsLog.
     * Syncs any newly-added entries to the backend.
     */
    const setDoubtsLog = useCallback((updater) => {
        setDoubtsLogRaw(prev => {
            const next = typeof updater === 'function' ? updater(prev) : updater;
            saveDoubts(id, next);
            const prevIds = new Set(prev.map(d => d.id));
            next.filter(d => !prevIds.has(d.id)).forEach(entry => {
                fetch(`${API}/api/notebooks/${id}/doubts`, {
                    method: 'POST',
                    headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                    body: JSON.stringify(entry),
                }).catch(() => {});
            });
            return next;
        });
    }, [id]);

    return { doubtsLog, setDoubtsLog, addDoubt };
}
