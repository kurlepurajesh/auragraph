import { useState, useCallback, useRef } from 'react';
import { useDispatch } from 'react-redux';
import { addToast } from '../store';
import { API, authHeaders } from '../components/utils';
import { ls_getNotebook, ls_saveNote } from '../localNotebooks';

/**
 * Manages core notebook data: notebook metadata, note text, proficiency level.
 * Also provides saveNote and extractAndSaveGraph utilities used across other hooks.
 *
 * @param {string} id - Notebook ID from URL params
 * @param {{ setGraphNodes, setGraphEdges, setDoubtsLog, loadDoubts }} deps
 */
export function useNotebookData(id, deps = {}) {
    const { setGraphNodes, setGraphEdges } = deps;
    const dispatch = useDispatch();

    const [notebook, setNotebook] = useState(null);
    const [note, setNote] = useState('');
    const [prof, setProf] = useState('Practitioner');

    const autoExtractRef = useRef(false);

    const saveNote = useCallback(async (newNote, newProf) => {
        const isErrorNote =
            typeof newNote === 'string' && (
                newNote.includes('Backend Not Running') ||
                newNote.includes('Failed to fetch')
            );
        if (isErrorNote) return;
        ls_saveNote(id, newNote, newProf);
        try {
            await fetch(`${API}/notebooks/${id}/note`, {
                method: 'PATCH',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: newNote, proficiency: newProf }),
            });
        } catch { /* silently ignore network errors */ }
    }, [id]);

    const extractAndSaveGraph = useCallback(async (text) => {
        try {
            const r = await fetch(`${API}/api/extract-concepts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ note: text, notebook_id: id }),
            });
            const g = await r.json();
            if (g.nodes?.length) {
                setGraphNodes?.(g.nodes);
                setGraphEdges?.(g.edges || []);
            }
        } catch { /* non-critical */ }
    }, [id, setGraphNodes, setGraphEdges]);

    const loadNotebook = useCallback(async () => {
        const isErrorNote = (n) =>
            typeof n === 'string' && (
                n.includes('Backend Not Running') ||
                n.includes('Failed to fetch') ||
                n.includes('⚠️ Generation Failed') ||
                n.includes('⚠️ Backend') ||
                n.includes('⚠️ Upload')
            );

        fetch(`${API}/notebooks/${id}`, { headers: authHeaders() })
            .then(r => { if (!r.ok) throw new Error(); return r.json(); })
            .then(nb => {
                setNotebook(nb);
                const loadedNote = nb.note || '';
                const cleanNote = isErrorNote(loadedNote) ? '' : loadedNote;
                setNote(cleanNote);
                setProf(nb.proficiency || 'Practitioner');
                if (nb.graph?.nodes?.length) {
                    setGraphNodes?.(nb.graph.nodes);
                    setGraphEdges?.(nb.graph.edges || []);
                } else if (cleanNote && !autoExtractRef.current) {
                    autoExtractRef.current = true;
                    setTimeout(() => extractAndSaveGraph(cleanNote), 800);
                }
            })
            .catch(() => {
                const l = ls_getNotebook(id);
                if (l) {
                    setNotebook(l);
                    const loadedNote = l.note || '';
                    const cleanNote = isErrorNote(loadedNote) ? '' : loadedNote;
                    setNote(cleanNote);
                    setProf(l.proficiency || 'Practitioner');
                    if (l.graph?.nodes?.length) {
                        setGraphNodes?.(l.graph.nodes);
                        setGraphEdges?.(l.graph.edges || []);
                    } else if (cleanNote && !autoExtractRef.current) {
                        autoExtractRef.current = true;
                        setTimeout(() => extractAndSaveGraph(cleanNote), 800);
                    }
                } else {
                    setNotebook({ id, name: 'Untitled', course: '' });
                    dispatch(addToast({
                        kind: 'warning',
                        title: 'Working offline',
                        message: 'Could not reach the backend and no local copy was found. Changes will be saved locally.',
                    }));
                }
            });
    }, [id, extractAndSaveGraph, setGraphNodes, setGraphEdges]);

    // Lighter reload used after section generation
    const reloadNote = useCallback(async () => {
        try {
            const res = await fetch(`${API}/notebooks/${id}`, { headers: authHeaders() });
            if (!res.ok) return;
            const nb = await res.json();
            setNote(nb.note || '');
            setProf(nb.proficiency || 'Practitioner');
        } catch { }
    }, [id]);

    return {
        notebook, setNotebook,
        note, setNote,
        prof, setProf,
        autoExtractRef,
        saveNote,
        extractAndSaveGraph,
        loadNotebook,
        reloadNote,
    };
}
