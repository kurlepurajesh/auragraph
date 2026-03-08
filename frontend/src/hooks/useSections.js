import { useState, useCallback } from 'react';
import { useDispatch } from 'react-redux';
import { addToast } from '../store';
import { API, apiFetch } from '../components/utils';

/**
 * Manages notebook TOC sections — CRUD and reordering.
 *
 * @param {string} id - Notebook ID
 * @param {string} notebookProficiency - e.g. 'Practitioner', used when generating content
 * @param {Function} reloadNote - called after section generation to refresh the main note
 * @param {Function} onSectionGenerated - called with (sectionTitle) after a section is generated so the
 *   caller can navigate to the newly-created page. Called after reloadNote resolves.
 */
export function useSections(id, notebookProficiency = 'Intermediate', reloadNote, onSectionGenerated) {
    const [sections, setSections] = useState([]);
    const [sectionInput, setSectionInput] = useState('');
    const [sectionInputType, setSectionInputType] = useState('topic');
    const [generatingSection, setGeneratingSection] = useState(null);
    const dispatch = useDispatch();

    const loadSections = useCallback(async () => {
        try {
            const res = await apiFetch(`${API}/notebooks/${id}/sections`);
            if (res.ok) setSections(await res.json());
        } catch { }
    }, [id]);

    const handleAddSection = async (e) => {
        e.preventDefault();
        const title = sectionInput.trim();
        if (!title) return;
        try {
            const res = await apiFetch(`${API}/notebooks/${id}/sections`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, note_type: sectionInputType }),
            });
            if (res.ok) {
                const sec = await res.json();
                setSections(prev => [...prev, sec]);
                setSectionInput('');
            } else {
                dispatch(addToast({ kind: 'error', title: 'Section not saved', message: `Server returned ${res.status}. Check your connection.` }));
            }
        } catch (err) {
            dispatch(addToast({ kind: 'error', title: 'Section not saved', message: err?.message || 'Network error.' }));
        }
    };

    const handleDeleteSection = async (secId) => {
        try {
            const res = await apiFetch(`${API}/notebooks/${id}/sections/${secId}`, {
                method: 'DELETE',
            });
            if (res.ok) setSections(prev => prev.filter(s => s.id !== secId));
        } catch { }
    };

    const handleGenerateSection = async (sec) => {
        setGeneratingSection(sec.id);
        try {
            const res = await apiFetch(`${API}/notebooks/${id}/sections/${sec.id}/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ proficiency: notebookProficiency }),
            });
            if (res.ok) {
                const updated = await res.json();
                setSections(prev => prev.map(s => s.id === sec.id ? updated : s));
                await reloadNote?.();
                onSectionGenerated?.(sec.title);
            } else {
                const body = await res.json().catch(() => ({}));
                dispatch(addToast({ kind: 'error', title: 'AI generation failed', message: body.detail || `Server error ${res.status}` }));
            }
        } catch (err) {
            dispatch(addToast({ kind: 'error', title: 'AI generation failed', message: err?.message || 'Network error — is the backend running?' }));
        }
        setGeneratingSection(null);
    };

    const handleMoveSectionUp = async (idx) => {
        if (idx === 0) return;
        const next = [...sections];
        [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
        setSections(next);
        try {
            await apiFetch(`${API}/notebooks/${id}/sections/reorder`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order: next.map((s, i) => ({ id: s.id, order_idx: i })) }),
            });
        } catch { }
    };

    const handleMoveSectionDown = async (idx) => {
        if (idx === sections.length - 1) return;
        const next = [...sections];
        [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
        setSections(next);
        try {
            await apiFetch(`${API}/notebooks/${id}/sections/reorder`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order: next.map((s, i) => ({ id: s.id, order_idx: i })) }),
            });
        } catch { }
    };

    return {
        sections, setSections,
        sectionInput, setSectionInput,
        sectionInputType, setSectionInputType,
        generatingSection, setGeneratingSection,
        loadSections,
        handleAddSection,
        handleDeleteSection,
        handleGenerateSection,
        handleMoveSectionUp,
        handleMoveSectionDown,
    };
}
