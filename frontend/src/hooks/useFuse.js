import { useState, useCallback } from 'react';
import { useDispatch } from 'react-redux';
import { addToast } from '../store';
import { API, apiFetch } from '../components/utils';

/**
 * Manages the FUSE (file upload + note generation) workflow.
 * Handles file state, streaming SSE events, and progress feedback.
 *
 * @param {string} id - Notebook ID
 * @param {{ prof, setNote, setCurrentPage, setMutatedPages, saveNote, extractAndSaveGraph }} deps
 */
export function useFuse(id, deps = {}) {
    const { prof, setNote, setCurrentPage, setMutatedPages, saveNote, extractAndSaveGraph } = deps;
    const dispatch = useDispatch();

    const [slidesFiles, setSlidesFiles] = useState([]);
    const [textbookFiles, setTextbookFiles] = useState([]);
    const [notesFiles, setNotesFiles] = useState([]);
    const [fusing, setFusing] = useState(false);
    const [fuseProgress, setFuseProgress] = useState('');
    const [verifyingStep, setVerifyingStep] = useState(null);
    const [noteSource, setNoteSource] = useState('azure');
    const [fallbackWarning, setFallbackWarning] = useState('');

    const handleFuse = useCallback(async () => {
        if (!slidesFiles.length && !notesFiles.length) return;
        setFusing(true);
        setFuseProgress('Uploading files…');
        setMutatedPages?.(new Set());
        setNote?.('');
        setCurrentPage?.(0);

        try {
            const form = new FormData();
            slidesFiles.forEach(f => form.append('slides_pdfs', f));
            notesFiles.forEach(f => form.append('slides_pdfs', f));
            textbookFiles.forEach(f => form.append('textbook_pdfs', f));
            form.append('proficiency', prof);
            if (id) form.append('notebook_id', id);
            setFuseProgress('Running Fusion Agent…');

            const res = await apiFetch(`${API}/api/upload-fuse-stream`, {
                method: 'POST',
                body: form,
            });

            if (!res.ok) {
                let detail = `Server error (${res.status})`;
                try { const j = await res.json(); detail = j.detail || detail; } catch { }
                throw new Error(detail);
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let streamedNote = '';
            let streamSource = 'azure';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n\n');
                buffer = parts.pop();
                for (const part of parts) {
                    const line = part.trim();
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        if (event.type === 'start') {
                            setFuseProgress(`Generating ${event.total} topic sections…`);
                        } else if (event.type === 'status') {
                            setFuseProgress(event.message || 'Processing…');
                            if ((event.message || '').toLowerCase().includes('verif')) setVerifyingStep(5);
                        } else if (event.type === 'section') {
                            streamedNote += (streamedNote ? '\n\n' : '') + event.content;
                            setFuseProgress(`Building: ${event.topic}…`);
                        } else if (event.type === 'done') {
                            setVerifyingStep(null);
                            streamedNote = event.note;
                            streamSource = event.source || 'azure';
                            setNote?.(event.note);
                            if (event.corrections_made > 0) {
                                setFallbackWarning(`✅ Accuracy check complete — ${event.correction_summary || 'minor corrections applied before showing notes.'}`);
                                setTimeout(() => setFallbackWarning(''), 8000);
                            }
                        }
                    } catch { /* ignore malformed SSE events */ }
                }
            }

            setNoteSource(streamSource);
            setFallbackWarning(streamSource === 'local'
                ? '⚠️ Azure OpenAI was unavailable — notes were generated using the offline summariser.'
                : '');
            await saveNote?.(streamedNote, prof);
            setFuseProgress('Extracting concept map…');
            await extractAndSaveGraph?.(streamedNote);
        } catch (err) {
            const isNetworkError = !err.message || err.message === 'Failed to fetch' || err.message.includes('NetworkError');
            const isFileTooLarge = err.message?.toLowerCase().includes('too large') || err.message?.toLowerCase().includes('exceeds') || err.message?.includes('413');
            const isAuth = err.message?.includes('401') || err.message?.includes('403') || err.message?.toLowerCase().includes('unauthorized');
            const bannerMsg = isNetworkError
                ? '⚠️ Backend unreachable — start the server: cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000'
                : isFileTooLarge
                    ? `⚠️ Upload too large — ${err.message}. Try splitting files across two notebooks or compressing large PDFs.`
                    : isAuth
                        ? '⚠️ Authentication failed — try logging out and back in.'
                        : `⚠️ Generation failed: ${err.message}`;
            setFallbackWarning(bannerMsg);
            // Also surface as a dismissible toast
            dispatch(addToast({
                kind: isAuth ? 'error' : isNetworkError ? 'warning' : 'error',
                title: isAuth ? 'Authentication error' : isNetworkError ? 'Backend unreachable' : 'Generation failed',
                message: isNetworkError
                    ? 'Start the backend server and try again.'
                    : isAuth
                        ? 'Log out and log back in.'
                        : err.message || 'Unknown error',
                duration: isNetworkError ? 10000 : 7000,
            }));
        }
        setFusing(false);
        setFuseProgress('');
        setVerifyingStep(null);
    }, [id, prof, slidesFiles, textbookFiles, notesFiles, setNote, setCurrentPage, setMutatedPages, saveNote, extractAndSaveGraph]);

    return {
        slidesFiles, setSlidesFiles,
        textbookFiles, setTextbookFiles,
        notesFiles, setNotesFiles,
        fusing, setFusing,
        fuseProgress, setFuseProgress,
        verifyingStep, setVerifyingStep,
        noteSource, setNoteSource,
        fallbackWarning, setFallbackWarning,
        handleFuse,
    };
}
