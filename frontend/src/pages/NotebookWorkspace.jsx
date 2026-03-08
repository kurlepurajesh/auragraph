import React, { useState, useCallback, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ls_getNotebook, ls_saveNote } from '../localNotebooks';
import {
    Sparkles, Loader2, ChevronLeft, ChevronRight, Upload, FileText,
    BookOpen, MessageSquare, ArrowLeft, Brain, CheckCircle2,
    AlertCircle, MinusCircle, RefreshCw, X, ChevronDown, ChevronUp,
    MessageCircle, GitBranch, Copy, Check, PanelRightClose, PanelRightOpen,
    Download, PenLine, Columns2, ScrollText, Moon, Sun, Search, Clock,
    Keyboard, Printer, Undo2, Plus, Trash2, Zap, List
} from 'lucide-react';
import { API, authHeaders, loadDoubts, saveDoubts } from '../components/utils';
import { useDarkMode } from '../hooks/useDarkMode';
import FuseProgressBar from '../components/FuseProgressBar';
import FileDrop from '../components/FileDrop';
import MutateModal from '../components/MutateModal';
import { ExaminerModal } from '../components/ExaminerModals';
import { GalaxyGraph } from '../components/Graph';
import SniperExamModal from '../components/SniperExamModal';
import { StudyTimer, NoteSearch, ShortcutsModal } from '../components/StudyTools';
import KnowledgePanel from '../components/KnowledgePanel';
import NoteRenderer from '../components/NoteRenderer';
import DoubtsPanel from '../components/DoubtsPanel';
import { CopyNoteButton, DownloadNoteButton, PrintNoteButton, UndoToast } from '../components/NoteToolbar';
import { useNotebookData } from '../hooks/useNotebookData';
import { useSections } from '../hooks/useSections';
import { useDoubtsLog } from '../hooks/useDoubtsLog';
import { useKnowledgeGraph } from '../hooks/useKnowledgeGraph';
import { usePagination } from '../hooks/usePagination';
import { useUndoStack } from '../hooks/useUndoStack';
import { useFuse } from '../hooks/useFuse';
import { useSidebar } from '../hooks/useSidebar';

export default function NotebookWorkspace() {
    const { id } = useParams();
    const navigate = useNavigate();

    // ── UI state (not owned by any single hook) ─────────────────────────────
    const [darkMode, setDarkMode] = useDarkMode();
    const [mutating, setMutating] = useState(false);
    const [gapText, setGapText] = useState('');
    const [mutatedPages, setMutatedPages] = useState(new Set());
    const [rightTab, setRightTab] = useState('map');
    const [textSelection, setTextSelection] = useState(null);
    const [pendingSelectionText, setPendingSelectionText] = useState('');
    const [showSearch, setShowSearch] = useState(false);
    const [showShortcuts, setShowShortcuts] = useState(false);
    const [editingPage, setEditingPage] = useState(false);
    const [pageInputVal, setPageInputVal] = useState('');
    const [regenLoadingPages, setRegenLoadingPages] = useState(new Set());

    // ── Custom hooks ─────────────────────────────────────────────────────────
    const { graphNodes, setGraphNodes, graphEdges, setGraphEdges, handleNodeStatusChange } = useKnowledgeGraph(id);
    const {
        notebook, setNotebook, note, setNote, prof, setProf,
        saveNote, extractAndSaveGraph, loadNotebook, reloadNote, autoExtractRef,
    } = useNotebookData(id, { setGraphNodes, setGraphEdges });
    const { doubtsLog, setDoubtsLog } = useDoubtsLog(id);
    const {
        sections, setSections,
        sectionInput, setSectionInput,
        sectionInputType, setSectionInputType,
        generatingSection,
        handleAddSection, handleDeleteSection, handleGenerateSection,
        handleMoveSectionUp, handleMoveSectionDown, loadSections,
    } = useSections(id, notebook?.proficiency || prof, reloadNote);
    const {
        pages, currentPage, setCurrentPage, viewMode, setViewMode,
        fontSize, setFontSize, jumpHighlightSet, noteScrollRef, handleJumpToSection,
    } = usePagination(note, { mutating, setMutating, setShowSearch, setShowShortcuts });
    const { undoToast, pushUndo, handleUndoCommit, dismissUndo } = useUndoStack({ saveNote, setNote, setProf });
    const {
        slidesFiles, setSlidesFiles, textbookFiles, setTextbookFiles,
        notesFiles, setNotesFiles, fusing, fuseProgress, verifyingStep,
        noteSource, fallbackWarning, setFallbackWarning, handleFuse,
    } = useFuse(id, { prof, setNote, setCurrentPage, setMutatedPages, saveNote, extractAndSaveGraph });
    const { sidebarOpen, setSidebarOpen, sidebarWidth, startResizeSidebar } = useSidebar();

    // ── On mount ─────────────────────────────────────────────────────────────
    useEffect(() => {
        autoExtractRef.current = false;
        loadNotebook();
    }, [loadNotebook]);
    useEffect(() => { loadSections(); }, [loadSections]);

    const handlePrint = useCallback(() => { window.print(); }, []);




    const handleMutate = useCallback(async (page, doubt) => {
        const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const lid = Date.now();
        try {
            // New API: send notebook_id + page_idx so backend can retrieve full context
            const res = await fetch(`${API}/api/mutate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({
                    notebook_id: id,
                    doubt,
                    page_idx: currentPage,
                    original_paragraph: page,  // kept as fallback
                })
            });
            const data = await res.json();

            if (data.can_mutate === false) {
                // LLM unavailable — don't clobber the original notes with a local fallback.
                // Instead, inject a visible unresolved-doubt anchor into the current page.
                const anchorMd = `\n\n> ⚠ **Unresolved Doubt** *(AI unavailable — will resolve automatically when online)*: "${doubt}" — [→ View in Doubts panel](#doubt-${lid})\n`;
                const trimmedPage = (pages[currentPage] || page).trim();
                const noteIdx = note.indexOf(trimmedPage);
                const newNote = noteIdx !== -1
                    ? note.slice(0, noteIdx) + trimmedPage + anchorMd + note.slice(noteIdx + trimmedPage.length)
                    : note + anchorMd;
                setNote(newNote);
                await saveNote(newNote, prof);
                const entry = { id: lid, pageIdx: currentPage, doubt, insight: 'AI unavailable — doubt saved. Your note has a reminder link. Retry when back online.', gap: data.concept_gap || '', source: 'local', time: ts, success: false, unresolved: true };
                setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
                setRightTab('doubts');
            } else {
                // LLM succeeded — replace the page with the rewritten version
                const trimmedPage = (pages[currentPage] || page).trim();
                const noteIdx = note.indexOf(trimmedPage);
                let newNote;
                if (noteIdx !== -1) {
                    newNote = note.slice(0, noteIdx) + data.mutated_paragraph + note.slice(noteIdx + trimmedPage.length);
                } else {
                    newNote = note + '\n\n---\n\n**Amendment (page ' + (currentPage + 1) + '):**\n\n' + data.mutated_paragraph;
                }
                pushUndo(note, prof, `Page ${currentPage + 1} mutated`);
                setNote(newNote); setGapText(data.concept_gap);
                setMutatedPages(prev => new Set([...prev, currentPage]));
                await saveNote(newNote, prof);
                extractAndSaveGraph(newNote).catch(() => { });
                // Use the full answer/explanation from the backend as insight shown in doubts sidebar.
                // Prefer data.answer (full explanation), fall back to concept_gap, then generic message.
                // Never extract a 2-word 💡 snippet — the student needs a real answer.
                const insight = data.answer || data.concept_gap || 'Your note was rewritten to address this doubt.';
                const entry = { id: lid, pageIdx: currentPage, doubt, insight, gap: data.concept_gap, source: data.source || 'azure', time: ts, success: true, kind: 'mutated' };
                setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
                setRightTab('doubts');
            }
        } catch {
            const entry = { id: lid, pageIdx: currentPage, doubt, insight: 'Could not reach backend. Your doubt has been recorded.', gap: 'Backend unreachable', time: ts, success: false };
            setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
            setRightTab('doubts');
        }
    }, [note, prof, id, currentPage, pages]);

    const handleRegenSection = useCallback(async (pageIdx) => {
        setRegenLoadingPages(prev => new Set([...prev, pageIdx]));
        try {
            const res = await fetch(`${API}/api/regenerate-section`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ notebook_id: id, page_idx: pageIdx, proficiency: prof }),
            });
            if (!res.ok) {
                let detail = `Server error (${res.status})`;
                try { const j = await res.json(); detail = j.detail || detail; } catch { }
                throw new Error(detail);
            }
            const data = await res.json();
            if (!data.new_section?.trim()) throw new Error('Empty response from server');

            // The backend already rebuilt and saved the full note after regenerating.
            // Re-fetch it so we display exactly what the backend stored — no client-side
            // string surgery that can misplace headings or leave raw markdown.
            pushUndo(note, prof, `Page ${pageIdx + 1} regenerated`);
            const nbRes = await fetch(`${API}/notebooks/${id}`, { headers: authHeaders() });
            if (nbRes.ok) {
                const nb = await nbRes.json();
                const freshNote = nb.note || '';
                setNote(freshNote);
                await saveNote(freshNote, prof);
            }
            setCurrentPage(pageIdx);
            setMutatedPages(prev => new Set([...prev, pageIdx]));
        } catch (err) {
            console.error('Re-generate section failed:', err);
        }
        setRegenLoadingPages(prev => { const s = new Set(prev); s.delete(pageIdx); return s; });
    }, [note, prof, id]);

    const handleNoteMouseUp = useCallback(() => {
        const sel = window.getSelection();
        const selText = sel?.toString().trim();
        if (selText && selText.length > 4) {
            try {
                const range = sel.getRangeAt(0);
                const rect = range.getBoundingClientRect();
                setTextSelection({ text: selText, x: rect.left + rect.width / 2, y: rect.top });
            } catch { }
        } else {
            setTextSelection(null);
        }
    }, []);

    if (!notebook) return <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)' }}><Loader2 className="spin" size={28} color="var(--text3)" /></div>;

    const hasNote = note.trim().length > 0;

    return (
        <div style={{ height: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Header */}
            <header style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: '0 16px 0 20px', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0, minWidth: 0, gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flexShrink: 1 }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate('/dashboard')} style={{ gap: 4, flexShrink: 0 }}><ArrowLeft size={14} /> Notebooks</button>
                    <div style={{ width: 1, height: 20, background: 'var(--border)', flexShrink: 0 }} />
                    <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {notebook.name}
                            {localStorage.getItem('ag_token') === 'demo-token' && (
                                <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 600, background: '#FEF3C7', color: '#92400E', border: '1px solid #FDE68A', borderRadius: 10, padding: '1px 7px', verticalAlign: 'middle' }}>DEMO</span>
                            )}
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text3)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{notebook.course}</div>
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    {hasNote && (<>
                        {/* Proficiency — current level shown; click to switch (requires re-upload) */}
                        <div style={{ display: 'flex', gap: 2, background: 'var(--surface)', padding: 2, borderRadius: 8, border: '1px solid var(--border)' }}>
                            {['Foundations', 'Practitioner', 'Expert'].map(p => (
                                <button key={p} onClick={() => {
                                    if (p === prof) return;
                                    if (window.confirm(`Switch to ${p} level?\n\nThis will take you back to the upload screen. Re-upload your materials to regenerate notes at the new level.`)) {
                                        setProf(p);
                                        setNote('');
                                    }
                                }} title={p === prof ? `Current: ${p}` : `Re-generate at ${p} level`} style={{ padding: '3px 8px', borderRadius: 5, border: 'none', cursor: p === prof ? 'default' : 'pointer', background: prof === p ? 'var(--text)' : 'transparent', color: prof === p ? '#fff' : 'var(--text3)', fontSize: 10, fontWeight: 600, transition: 'all 0.15s', whiteSpace: 'nowrap' }}>{p}</button>
                            ))}
                        </div>
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        {/* Page nav */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--surface)', padding: '4px 10px', borderRadius: 20, border: '1px solid var(--border)' }}>
                            <button data-testid="prev-page" onClick={() => setCurrentPage(Math.max(0, currentPage - (viewMode === 'two' ? 2 : 1)))} disabled={currentPage === 0} title="Previous (←)" style={{ background: 'none', border: 'none', color: currentPage === 0 ? 'var(--border2)' : 'var(--text2)', cursor: currentPage === 0 ? 'not-allowed' : 'pointer', padding: 0, display: 'flex' }}><ChevronLeft size={14} /></button>
                            {editingPage ? (
                                <input
                                    autoFocus
                                    type="number" min={1} max={pages.length}
                                    value={pageInputVal}
                                    onChange={e => setPageInputVal(e.target.value)}
                                    onKeyDown={e => {
                                        if (e.key === 'Enter') {
                                            const n = parseInt(pageInputVal, 10);
                                            if (!isNaN(n)) setCurrentPage(Math.max(0, Math.min(pages.length - 1, n - 1)));
                                            setEditingPage(false); setPageInputVal('');
                                        } else if (e.key === 'Escape') { setEditingPage(false); setPageInputVal(''); }
                                    }}
                                    onBlur={() => { setEditingPage(false); setPageInputVal(''); }}
                                    style={{ width: 46, textAlign: 'center', fontSize: 12, border: '1px solid var(--purple)', borderRadius: 4, padding: '1px 4px', background: 'var(--bg)', color: 'var(--text)', outline: 'none' }}
                                />
                            ) : (
                                <span
                                    onClick={() => { setEditingPage(true); setPageInputVal(String(currentPage + 1)); }}
                                    title="Click to jump to a page"
                                    style={{ fontSize: 12, color: 'var(--text2)', minWidth: 48, textAlign: 'center', cursor: 'pointer', borderRadius: 4, padding: '1px 3px' }}
                                    onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
                                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                                >{currentPage + 1}{viewMode === 'two' && pages[currentPage + 1] ? `–${currentPage + 2}` : ''} / {pages.length}</span>
                            )}
                            <button data-testid="next-page" onClick={() => setCurrentPage(p => {
                                if (viewMode === 'two') { const maxLeft = Math.floor((pages.length - 1) / 2) * 2; return Math.min(maxLeft, p + 2); }
                                return Math.min(pages.length - 1, p + 1);
                            })} disabled={viewMode === 'two' ? currentPage >= Math.floor((pages.length - 1) / 2) * 2 : currentPage >= pages.length - 1} title="Next (→)" style={{ background: 'none', border: 'none', color: (viewMode === 'two' ? currentPage >= Math.floor((pages.length - 1) / 2) * 2 : currentPage >= pages.length - 1) ? 'var(--border2)' : 'var(--text2)', cursor: (viewMode === 'two' ? currentPage >= Math.floor((pages.length - 1) / 2) * 2 : currentPage >= pages.length - 1) ? 'not-allowed' : 'pointer', padding: 0, display: 'flex' }}><ChevronRight size={14} /></button>
                        </div>
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        {/* View mode toggle */}
                        <div style={{ display: 'flex', gap: 1, background: 'var(--surface)', padding: 2, borderRadius: 7, border: '1px solid var(--border)' }}>
                            {[['single', <BookOpen size={12} />, 'Single page'], ['two', <Columns2 size={12} />, 'Two pages side-by-side'], ['scroll', <ScrollText size={12} />, 'Continuous scroll']].map(([mode, icon, title]) => (
                                <button key={mode} title={title} onClick={() => setViewMode(mode)} style={{ padding: '4px 8px', borderRadius: 5, border: 'none', cursor: 'pointer', background: viewMode === mode ? 'var(--text)' : 'transparent', color: viewMode === mode ? '#fff' : 'var(--text3)', display: 'flex', alignItems: 'center', transition: 'all 0.15s' }}>{icon}</button>
                            ))}
                        </div>
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        {/* Export (compact) */}
                        <CopyNoteButton note={note} />
                        <DownloadNoteButton note={note} name={notebook.name} />
                        <PrintNoteButton onPrint={handlePrint} />
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        {/* Font size controls */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: 1, background: 'var(--surface)', padding: 2, borderRadius: 7, border: '1px solid var(--border)' }}>
                            <button className="btn btn-ghost btn-sm" onClick={() => setFontSize(f => Math.max(12, f - 1))} title="Decrease font size (A−)" style={{ padding: '3px 7px', fontSize: 10, fontWeight: 700, lineHeight: 1 }}>A−</button>
                            <span style={{ fontSize: 10, color: 'var(--text3)', minWidth: 28, textAlign: 'center', fontFamily: 'Inter,sans-serif' }}>{fontSize}px</span>
                            <button className="btn btn-ghost btn-sm" onClick={() => setFontSize(f => Math.min(24, f + 1))} title="Increase font size (A+)" style={{ padding: '3px 7px', fontSize: 12, fontWeight: 700, lineHeight: 1 }}>A+</button>
                        </div>
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        {/* Search */}
                        <button className="btn btn-ghost btn-sm" style={{ padding: '5px 8px' }} onClick={() => setShowSearch(true)} title="Search in notes (Ctrl+F)"><Search size={14} /></button>
                        {/* Timer */}
                        <StudyTimer />
                        {/* Shortcuts */}
                        <button className="btn btn-ghost btn-sm" style={{ padding: '5px 8px' }} onClick={() => setShowShortcuts(true)} title="Keyboard shortcuts (?)" ><Keyboard size={14} /></button>
                        {/* Dark mode */}
                        <button className="btn btn-ghost btn-sm" style={{ padding: '5px 8px' }} onClick={() => setDarkMode(d => !d)} title="Toggle dark mode">{darkMode ? <Sun size={14} /> : <Moon size={14} />}</button>
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        <button data-testid="ask-doubt-btn" className="btn btn-primary btn-sm" style={{ gap: 5 }} onClick={() => setMutating(true)} title="Ask a doubt (Ctrl+D)"><MessageSquare size={13} /> Ask a Doubt</button>
                        <button className="btn btn-ghost btn-sm" onClick={() => setSidebarOpen(o => !o)} title={sidebarOpen ? 'Hide sidebar' : 'Show sidebar'} style={{ padding: '6px 8px' }}>
                            {sidebarOpen ? <PanelRightClose size={15} /> : <PanelRightOpen size={15} />}
                        </button>
                    </>)}
                </div>
            </header>

            {/* Body */}
            <div data-print-body style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                {!hasNote ? (
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
                        <div style={{ maxWidth: 760, width: '100%' }}>
                            <div style={{ textAlign: 'center', marginBottom: 36 }}>
                                <div style={{ display: 'inline-block', background: '#fff', borderRadius: 12, padding: '8px 18px', margin: '0 auto 14px', border: '1px solid var(--border)' }}><img src="/logo.jpeg" alt="AuraGraph" style={{ height: 44, width: 'auto', display: 'block' }} /></div>
                                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>Generate Fused Notes</h2>
                                <p style={{ fontSize: 14, color: 'var(--text3)', lineHeight: 1.7 }}>Upload your course materials and AuraGraph will generate a personalised digital study note calibrated to your level.</p>
                            </div>
                            <FuseProgressBar active={fusing} forceStep={verifyingStep} />
                            {!fusing && (<>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 14, marginBottom: 24 }}>
                                    <FileDrop label="Professor's Slides" icon={BookOpen} files={slidesFiles} onFiles={setSlidesFiles} />
                                    <FileDrop label="Handwritten Notes" icon={PenLine} files={notesFiles} onFiles={setNotesFiles} />
                                    <FileDrop label="Textbook / Reference" icon={FileText} files={textbookFiles} onFiles={setTextbookFiles} />
                                </div>
                                <div style={{ marginBottom: 24 }}>
                                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text2)', marginBottom: 10 }}>Proficiency Level</label>
                                    <div style={{ display: 'flex', gap: 10 }}>
                                        {[['Foundations', 'Concepts first — analogies & plain English'], ['Practitioner', 'Balanced depth — formulas with intuition'], ['Expert', 'Full rigour — derivations & edge cases']].map(([p, d]) => (
                                            <button key={p} onClick={() => setProf(p)} style={{ flex: 1, padding: '10px 8px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${prof === p ? 'var(--text)' : 'var(--border)'}`, background: prof === p ? 'var(--text)' : 'var(--bg)', color: prof === p ? '#fff' : 'var(--text2)', textAlign: 'center', transition: 'all 0.15s' }}>
                                                <div style={{ fontWeight: 600, fontSize: 13 }}>{p}</div>
                                                <div style={{ fontSize: 11, marginTop: 2, opacity: 0.7 }}>{d}</div>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <button data-testid="generate-notes-btn" className="btn btn-primary btn-lg" style={{ width: '100%', gap: 8 }} onClick={handleFuse} disabled={fusing || (!slidesFiles.length && !notesFiles.length)}>
                                    <Sparkles size={16} /> Generate Digital Notes
                                </button>
                                <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text3)', marginTop: 12 }}>← → to navigate · <kbd>Ctrl+D</kbd> ask/rewrite · <kbd>Ctrl+F</kbd> search · click page counter to jump · <kbd>?</kbd> shortcuts</p>
                            </>)}
                        </div>
                    </div>
                ) : (
                    <div ref={noteScrollRef} onMouseUp={handleNoteMouseUp} data-print-scroll style={{ flex: 1, overflowY: 'auto', background: 'linear-gradient(160deg,#EEE8F8 0%,#F0EDF8 40%,#EBE5F5 100%)', padding: viewMode === 'two' ? '28px 16px' : '28px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        {(() => {
                            const onDoubtLink = (doubtId) => { setRightTab('doubts'); setTimeout(() => { document.getElementById(doubtId)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 150); };
                            const renderPage = (idx) => {
                                if (idx < 0 || idx >= pages.length) return <div key={`empty-${idx}`} style={{ flex: 1, minWidth: 0 }} />;
                                const isHighlighted = jumpHighlightSet.has(idx);
                                return (
                                    <div key={idx} className="note-page-card" style={{ display: 'flex', background: '#FEFDF9', borderRadius: 6, boxShadow: isHighlighted ? '0 0 0 3px #7C3AED, 0 2px 12px rgba(124,58,237,0.12), 0 16px 48px rgba(0,0,0,0.10)' : '0 2px 8px rgba(0,0,0,0.06), 0 8px 24px rgba(124,58,237,0.06), 0 20px 64px rgba(0,0,0,0.09)', border: isHighlighted ? '1px solid #7C3AED' : '1px solid #E8E0F0', overflow: 'hidden', flex: 1, minWidth: 0, transition: 'box-shadow 0.4s, border-color 0.4s' }}>
                                        <div className="note-binder-rings" style={{ width: 40, background: 'linear-gradient(180deg,#F5F0FF,#EDE9FE)', borderRight: '2px solid #DDD6FE', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-evenly', padding: '32px 0', alignSelf: 'stretch', minHeight: 560 }}>
                                            {[0, 1, 2, 3, 4, 5].map(i => <div key={i} style={{ width: 16, height: 16, borderRadius: '50%', background: '#fff', border: '2px solid #C4B5FD', boxShadow: 'inset 0 1px 3px rgba(124,58,237,0.18), 0 1px 2px rgba(124,58,237,0.12)' }} />)}
                                        </div>
                                        <div className="note-margin-line" style={{ width: 1.5, background: 'linear-gradient(180deg,#C4B5FD 0%,#A78BFA 50%,#C4B5FD 100%)', flexShrink: 0 }} />
                                        <div style={{ flex: 1, padding: '40px 48px 48px 36px', minWidth: 0 }}>
                                            <div className="note-header-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, paddingBottom: 10, borderBottom: '1px solid #DDD6FE' }}>
                                                <span style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Inter,sans-serif' }}>{notebook?.name || 'Study Notes'}</span>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                    {mutatedPages.has(idx) && <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: 'var(--ag-purple-soft)', color: 'var(--ag-purple)', border: '1px solid #C4B5FD', letterSpacing: '0.05em' }}>✨ Mutated</span>}
                                                    <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>Page {idx + 1} of {pages.length}</span>
                                                    <button
                                                        onClick={() => handleRegenSection(idx)}
                                                        disabled={regenLoadingPages.has(idx)}
                                                        title="Re-generate this section with fresh AI output"
                                                        className="no-print"
                                                        style={{ background: 'none', border: '1px solid #E5E7EB', borderRadius: 6, padding: '3px 8px', cursor: regenLoadingPages.has(idx) ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, fontWeight: 600, color: '#9CA3AF', transition: 'all 0.15s' }}
                                                        onMouseEnter={e => { if (!regenLoadingPages.has(idx)) { e.currentTarget.style.borderColor = 'var(--ag-purple)'; e.currentTarget.style.color = 'var(--ag-purple)'; } }}
                                                        onMouseLeave={e => { e.currentTarget.style.borderColor = '#E5E7EB'; e.currentTarget.style.color = '#9CA3AF'; }}
                                                    >
                                                        {regenLoadingPages.has(idx)
                                                            ? <><Loader2 size={10} className="spin" /> Regenerating…</>
                                                            : <><RefreshCw size={10} /> Regenerate</>}
                                                    </button>
                                                </div>
                                            </div>
                                            <NoteRenderer content={pages[idx]} onDoubtLink={onDoubtLink} fontSize={fontSize} />
                                            <div className="note-footer-bar" style={{ marginTop: 36, paddingTop: 10, borderTop: '1px solid #DDD6FE', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <span style={{ fontSize: 10, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>{notebook?.course || ''}</span>
                                                <span style={{ fontSize: 10, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>AuraGraph · {prof}</span>
                                            </div>
                                        </div>
                                    </div>
                                );
                            };
                            const banners = (
                                <>
                                    {fallbackWarning && (
                                        <div style={{ marginBottom: 14, padding: '10px 14px', background: '#FEF3C7', border: '1px solid #FDE68A', borderRadius: 8, fontSize: 12, color: '#92400E', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                            <span style={{ flexShrink: 0 }}>⚠️</span>
                                            <div style={{ flex: 1 }}><b>Offline notes:</b> {fallbackWarning.replace(/^⚠️\s*/, '')}</div>
                                            <button onClick={() => setFallbackWarning('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#92400E', padding: 0, marginLeft: 'auto', flexShrink: 0 }}><X size={13} /></button>
                                        </div>
                                    )}

                                </>
                            );
                            const bottomBar = (
                                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                                    <button data-testid="re-upload-btn" className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => setNote('')}><Upload size={12} /> Re-upload materials</button>
                                    <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => extractAndSaveGraph(note)}><RefreshCw size={12} /> Refresh Concept Map</button>
                                    {viewMode !== 'scroll' && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                            {pages.slice(0, Math.min(pages.length, 20)).map((_, i) => (
                                                <button key={i} className="page-dot" data-label={`Page ${i + 1}`} onClick={() => setCurrentPage(i)} title={`Page ${i + 1}`} style={{ width: i === currentPage ? 20 : 6, height: 6, borderRadius: 3, border: 'none', cursor: 'pointer', background: i === currentPage ? 'var(--ag-purple)' : mutatedPages.has(i) ? 'var(--ag-ring-left)' : 'var(--border2)', transition: 'all 0.2s', padding: 0 }} />
                                            ))}
                                            {pages.length > 20 && <span style={{ fontSize: 10, color: 'var(--text3)' }}>+{pages.length - 20}</span>}
                                        </div>
                                    )}
                                </div>
                            );
                            if (viewMode === 'scroll') return (
                                <div style={{ maxWidth: 760, width: '100%' }}>
                                    {banners}
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                                        {pages.map((_, idx) => renderPage(idx))}
                                    </div>
                                    {bottomBar}
                                </div>
                            );
                            if (viewMode === 'two') {
                                const hasRight = currentPage + 1 < pages.length;
                                return (
                                    <div style={{ maxWidth: 1480, width: '100%' }}>
                                        {banners}
                                        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                                            {renderPage(currentPage)}
                                            {hasRight ? renderPage(currentPage + 1) : <div style={{ flex: 1, minWidth: 0 }} />}
                                        </div>
                                        {bottomBar}
                                    </div>
                                );
                            }
                            return (
                                <div style={{ maxWidth: 760, width: '100%' }}>
                                    {banners}
                                    {renderPage(currentPage)}
                                    {bottomBar}
                                </div>
                            );
                        })()}
                    </div>
                )}

                {/* Right Sidebar */}
                <aside
                    className={sidebarOpen ? 'sidebar-panel' : 'sidebar-panel collapsed'}
                    style={{ width: sidebarOpen ? sidebarWidth : 0, minWidth: sidebarOpen ? sidebarWidth : 0 }}
                >
                    {/* Drag-to-resize handle on the left edge */}
                    {sidebarOpen && (
                        <div
                            className="sidebar-resize-handle"
                            onMouseDown={startResizeSidebar}
                            title="Drag to resize panel"
                        />
                    )}
                    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
                        {[
                            { key: 'map', label: 'Concept Map', icon: <Brain size={12} /> },
                            { key: 'doubts', label: (() => { const onPage = doubtsLog.filter(d => d.pageIdx === currentPage).length; const total = doubtsLog.length; if (!total) return 'Doubts'; if (onPage) return `Doubts (${onPage}/${total})`; return `Doubts (${total})`; })(), icon: <MessageCircle size={12} /> },
                            { key: 'contents', label: `Contents${sections.length ? ` (${sections.length})` : ''}`, icon: <List size={12} /> },
                        ].map(tab => (
                            <button key={tab.key} data-testid={`tab-${tab.key}`} onClick={() => setRightTab(tab.key)} style={{ flex: 1, padding: '10px 4px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, fontSize: 10, fontWeight: 600, cursor: 'pointer', border: 'none', transition: 'all 0.15s', borderBottom: rightTab === tab.key ? '2px solid #7C3AED' : '2px solid transparent', background: 'transparent', color: rightTab === tab.key ? 'var(--ag-purple)' : 'var(--text3)' }}>
                                {tab.icon} {tab.label}
                            </button>
                        ))}
                    </div>
                    {rightTab === 'contents' ? (
                        <div style={{ flex: 1, overflowY: 'auto', padding: '12px 10px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {/* Add section form */}
                            <form onSubmit={handleAddSection} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '10px', background: 'var(--surface)', borderRadius: 8, border: '1px solid var(--border)', marginBottom: 4 }}>
                                <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text2)', marginBottom: 2 }}>Add Topic / Chapter</div>
                                <input
                                    className="input"
                                    style={{ fontSize: 12, padding: '6px 8px' }}
                                    placeholder="e.g. Fourier Transform"
                                    value={sectionInput}
                                    onChange={e => setSectionInput(e.target.value)}
                                />
                                <div style={{ display: 'flex', gap: 6 }}>
                                    <select
                                        className="input"
                                        style={{ fontSize: 11, padding: '4px 6px', flex: 1 }}
                                        value={sectionInputType}
                                        onChange={e => setSectionInputType(e.target.value)}
                                    >
                                        <option value="topic">Topic</option>
                                        <option value="chapter">Chapter</option>
                                    </select>
                                    <button type="submit" className="btn btn-primary" style={{ fontSize: 11, padding: '4px 10px', gap: 4 }} disabled={!sectionInput.trim()}>
                                        <Plus size={12} /> Add
                                    </button>
                                </div>
                            </form>

                            {sections.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '24px 0', color: 'var(--text3)', fontSize: 12 }}>
                                    No sections yet. Add a topic or chapter above.
                                </div>
                            ) : sections.map((sec, idx) => (
                                <div key={sec.id} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px' }}>
                                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                                        {/* Reorder arrows */}
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 1, flexShrink: 0, marginTop: 1 }}>
                                            <button onClick={() => handleMoveSectionUp(idx)} disabled={idx === 0}
                                                style={{ background: 'none', border: 'none', cursor: idx === 0 ? 'default' : 'pointer', opacity: idx === 0 ? 0.25 : 0.7, padding: 1, lineHeight: 1 }}>
                                                <ChevronUp size={12} color="var(--text3)" />
                                            </button>
                                            <button onClick={() => handleMoveSectionDown(idx)} disabled={idx === sections.length - 1}
                                                style={{ background: 'none', border: 'none', cursor: idx === sections.length - 1 ? 'default' : 'pointer', opacity: idx === sections.length - 1 ? 0.25 : 0.7, padding: 1, lineHeight: 1 }}>
                                                <ChevronDown size={12} color="var(--text3)" />
                                            </button>
                                        </div>
                                        {/* Title + type */}
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', lineHeight: 1.35, wordBreak: 'break-word' }}>{sec.title}</div>
                                            <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2, textTransform: 'capitalize' }}>{sec.note_type} · {sec.content?.length ? `${sec.content.length} chars` : 'empty'}</div>
                                        </div>
                                        {/* Actions */}
                                        <div style={{ display: 'flex', gap: 2, flexShrink: 0 }}>
                                            <button
                                                onClick={() => handleGenerateSection(sec)}
                                                disabled={generatingSection === sec.id}
                                                title="Generate note for this section"
                                                style={{ background: 'none', border: '1px solid #7C3AED33', borderRadius: 5, cursor: 'pointer', padding: '3px 6px', color: 'var(--ag-purple)', opacity: generatingSection === sec.id ? 0.5 : 1 }}
                                            >
                                                {generatingSection === sec.id
                                                    ? <Loader2 className="spin" size={11} />
                                                    : <Zap size={11} />}
                                            </button>
                                            <button
                                                onClick={() => handleDeleteSection(sec.id)}
                                                title="Delete section"
                                                style={{ background: 'none', border: '1px solid #EF444433', borderRadius: 5, cursor: 'pointer', padding: '3px 6px', color: 'var(--ag-red)' }}
                                            >
                                                <Trash2 size={11} />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : rightTab === 'map'
                        ? <KnowledgePanel nodes={graphNodes} edges={graphEdges} notebookId={id} onNodeStatusChange={handleNodeStatusChange} onJumpToSection={handleJumpToSection} />
                        : <DoubtsPanel doubts={doubtsLog} currentPage={currentPage} />}
                </aside>
            </div>

            {textSelection && (
                <div style={{ position: 'fixed', left: textSelection.x, top: textSelection.y - 8, transform: 'translateX(-50%) translateY(-100%)', zIndex: 9999, background: '#1E1B4B', borderRadius: 8, padding: '6px 10px', display: 'flex', gap: 6, boxShadow: '0 4px 24px rgba(0,0,0,0.35)', alignItems: 'center', pointerEvents: 'auto' }}>
                    <MessageCircle size={11} color="#C4B5FD" />
                    <span style={{ color: 'var(--ag-ring-left)', fontSize: 10, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{textSelection.text.length > 45 ? textSelection.text.slice(0, 45) + '…' : textSelection.text}</span>
                    <button onClick={() => { setPendingSelectionText(textSelection.text); setTextSelection(null); setMutating(true); }} style={{ background: 'var(--ag-purple)', border: 'none', color: '#fff', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>Ask about this</button>
                    <button onClick={() => setTextSelection(null)} style={{ background: 'none', border: '1px solid #4C1D95', color: 'var(--ag-ring-right)', borderRadius: 5, padding: '3px 7px', fontSize: 11, cursor: 'pointer' }}>&#x2715;</button>
                </div>
            )}
            {undoToast && <UndoToast toast={undoToast} onUndo={handleUndoCommit} onDismiss={dismissUndo} />}

            {/* ── Dedicated print container — hidden on screen, visible in @media print ── */}
            {pages.length > 0 && (
                <div id="ag-print-root">
                    {pages.map((pageContent, idx) => (
                        <div key={idx} className="ag-print-page">
                            <div style={{ fontSize: 10, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Inter,sans-serif', marginBottom: 16, paddingBottom: 10, borderBottom: '1px solid #E5E7EB', display: 'flex', justifyContent: 'space-between' }}>
                                <span>{notebook?.name || 'Study Notes'}</span>
                                <span>Page {idx + 1} of {pages.length} · AuraGraph · {prof}</span>
                            </div>
                            <NoteRenderer content={pageContent} fontSize={fontSize} />
                        </div>
                    ))}
                </div>
            )}

            {mutating && pages.length > 0 && <MutateModal page={pages[currentPage]} notebookId={id} pageIdx={currentPage} onClose={() => { setMutating(false); setPendingSelectionText(''); }} onMutate={handleMutate} onDoubtAnswered={({ doubt: q, answer: a, source: s }) => { const entry = { id: Date.now(), pageIdx: currentPage, doubt: q, insight: a, gap: '', source: s || 'azure', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), success: true, kind: 'answered' }; setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; }); setRightTab('doubts'); }} initialDoubt={pendingSelectionText} />}
            {showSearch && pages.length > 0 && <NoteSearch pages={pages} onJumpToPage={(idx) => { setCurrentPage(idx); }} onClose={() => setShowSearch(false)} />}
            {showShortcuts && <ShortcutsModal onClose={() => setShowShortcuts(false)} />}
        </div>
    );
}
