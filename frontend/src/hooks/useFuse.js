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
        // Save the existing note so we can restore it if generation fails
        // (instead of leaving the user on a blank upload screen)
        let previousNote = '';
        setNote?.(prev => { previousNote = prev || ''; return ''; });
        setCurrentPage?.(0);

        try {
            const form = new FormData();
            slidesFiles.forEach(f => form.append('slides_pdfs', f));
            notesFiles.forEach(f => form.append('slides_pdfs', f));
            textbookFiles.forEach(f => form.append('textbook_pdfs', f));
            form.append('proficiency', prof);
            if (id) form.append('notebook_id', id);
            setFuseProgress('Running Fusion Agent…');

            // Hard abort: 15 minutes — generous enough for 3 slides (30+ topics) at any proficiency
            const abortCtrl = new AbortController();
            const streamTimeout = setTimeout(() => abortCtrl.abort(), 15 * 60 * 1000);

            const res = await apiFetch(`${API}/api/upload-fuse-stream`, {
                method: 'POST',
                body: form,
                signal: abortCtrl.signal,
            });

            if (!res.ok) {
                clearTimeout(streamTimeout);
                let detail = `Server error (${res.status})`;
                try {
                    const j = await res.json();
                    const raw = j.detail;
                    if (typeof raw === 'string') detail = raw;
                    else if (Array.isArray(raw)) detail = raw.map(e => e?.msg || JSON.stringify(e)).join(' · ');
                } catch { }
                throw new Error(detail);
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let streamedNote = '';
            let streamSource = 'azure';
            let lastChunkAt = Date.now();
            // Per-chunk stall detection: 300 s (5 min) with no data → abort
            // A single Beginner-level topic with sub-chunks can legitimately take 2-3 min
            const stallCheck = setInterval(() => {
                if (Date.now() - lastChunkAt > 300_000) {
                    abortCtrl.abort();
                    clearInterval(stallCheck);
                }
            }, 5_000);

            try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                lastChunkAt = Date.now();
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
                            // Show partial notes progressively so the user isn’t staring at a blank
                            // screen the whole time — AND so they see something useful if it
                            // fails before the final ‘done’ event.
                            setNote?.(streamedNote);
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

            } finally {
                clearTimeout(streamTimeout);
                clearInterval(stallCheck);
            }

            setNoteSource(streamSource);
            setFallbackWarning(streamSource === 'local'
                ? '⚠️ Azure OpenAI was unavailable — notes were generated using the offline summariser.'
                : '');
            await saveNote?.(streamedNote, prof);
            setFuseProgress('Extracting concept map…');
            await extractAndSaveGraph?.(streamedNote);
        } catch (err) {
            // Restore the previous note if generation failed (don’t leave the
            // user on a blank upload screen after waiting several minutes)
            if (previousNote) setNote?.(previousNote);
            const message = err.name === 'AbortError'
                ? 'Generation timed out — the backend took too long to respond. Try again or use a smaller file.'
                : (err.message || '');
            const isNetworkError = !message || message === 'Failed to fetch' || message.includes('NetworkError');
            const isFileTooLarge = message.toLowerCase().includes('too large') || message.toLowerCase().includes('exceeds') || message.includes('413');
            const isAuth = message.includes('401') || message.includes('403') || message.toLowerCase().includes('unauthorized');
            const isTimeout = err.name === 'AbortError';
            const bannerMsg = isTimeout
                ? `⚠️ ${message}`
                : isNetworkError
                ? '⚠️ Backend unreachable — start the server: cd backend && source venv/bin/activate && uvicorn main:app --reload --port 8000'
                : isFileTooLarge
                    ? `⚠️ Upload too large — ${message}. Try splitting files across two notebooks or compressing large PDFs.`
                    : isAuth
                        ? '⚠️ Authentication failed — try logging out and back in.'
                        : `⚠️ Generation failed: ${message}`;
            setFallbackWarning(bannerMsg);
            // Also surface as a dismissible toast
            dispatch(addToast({
                kind: isAuth ? 'error' : isNetworkError ? 'warning' : 'error',
                title: isTimeout ? 'Request timed out' : isAuth ? 'Authentication error' : isNetworkError ? 'Backend unreachable' : 'Generation failed',
                message: isTimeout
                    ? message
                    : isNetworkError
                        ? 'Start the backend server and try again.'
                        : isAuth
                            ? 'Log out and log back in.'
                            : message || 'Unknown error',
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
