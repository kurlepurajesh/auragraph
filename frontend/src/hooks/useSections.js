import { useState, useCallback } from 'react';
import { API, authHeaders } from '../components/utils';

/**
 * Manages notebook TOC sections — CRUD and reordering.
 *
 * @param {string} id - Notebook ID
 * @param {string} notebookProficiency - e.g. 'Practitioner', used when generating content
 * @param {Function} reloadNote - called after section generation to refresh the main note
 */
export function useSections(id, notebookProficiency = 'Intermediate', reloadNote) {
    const [sections, setSections] = useState([]);
    const [sectionInput, setSectionInput] = useState('');
    const [sectionInputType, setSectionInputType] = useState('topic');
    const [generatingSection, setGeneratingSection] = useState(null);

    const loadSections = useCallback(async () => {
        try {
            const res = await fetch(`${API}/notebooks/${id}/sections`, { headers: authHeaders() });
            if (res.ok) setSections(await res.json());
        } catch { }
    }, [id]);

    const handleAddSection = async (e) => {
        e.preventDefault();
        const title = sectionInput.trim();
        if (!title) return;
        try {
            const res = await fetch(`${API}/notebooks/${id}/sections`, {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({ title, note_type: sectionInputType }),
            });
            if (res.ok) {
                const sec = await res.json();
                setSections(prev => [...prev, sec]);
                setSectionInput('');
            }
        } catch { }
    };

    const handleDeleteSection = async (secId) => {
        try {
            const res = await fetch(`${API}/notebooks/${id}/sections/${secId}`, {
                method: 'DELETE',
                headers: authHeaders(),
            });
            if (res.ok) setSections(prev => prev.filter(s => s.id !== secId));
        } catch { }
    };

    const handleGenerateSection = async (sec) => {
        setGeneratingSection(sec.id);
        try {
            const res = await fetch(`${API}/notebooks/${id}/sections/${sec.id}/generate`, {
                method: 'POST',
                headers: authHeaders(),
                body: JSON.stringify({ proficiency: notebookProficiency }),
            });
            if (res.ok) {
                const updated = await res.json();
                setSections(prev => prev.map(s => s.id === sec.id ? updated : s));
                reloadNote?.();
            }
        } catch { }
        setGeneratingSection(null);
    };

    const handleMoveSectionUp = async (idx) => {
        if (idx === 0) return;
        const next = [...sections];
        [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
        setSections(next);
        try {
            await fetch(`${API}/notebooks/${id}/sections/reorder`, {
                method: 'PUT',
                headers: authHeaders(),
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
            await fetch(`${API}/notebooks/${id}/sections/reorder`, {
                method: 'PUT',
                headers: authHeaders(),
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
