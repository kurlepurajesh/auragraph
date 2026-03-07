import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ls_getNotebook, ls_saveNote } from '../localNotebooks';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import {
    Sparkles, Loader2, ChevronLeft, ChevronRight, Upload, FileText,
    BookOpen, MessageSquare, ArrowLeft, Brain, CheckCircle2,
    AlertCircle, MinusCircle, RefreshCw, X, ChevronDown, ChevronUp,
    MessageCircle, GitBranch, Copy, Check, PanelRightClose, PanelRightOpen,
    Download, PenLine, Columns2, ScrollText, Moon, Sun, Search, Clock,
    Keyboard
} from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ─── Doubts localStorage helpers ─────────────────────────────────────────────
function loadDoubts(notebookId) {
    try { return JSON.parse(localStorage.getItem(`ag_doubts_${notebookId}`) || '[]'); }
    catch { return []; }
}
function saveDoubts(notebookId, doubts) {
    try { localStorage.setItem(`ag_doubts_${notebookId}`, JSON.stringify(doubts)); }
    catch { }
}

function authHeaders() {
    const token = localStorage.getItem('ag_token') || 'demo-token';
    return { Authorization: `Bearer ${token}` };
}

// ─── Animated Fuse Progress ───────────────────────────────────────────────────
const FUSE_STEPS = [
    { label: 'Uploading files', icon: '📤' },
    { label: 'Extracting slides & notes', icon: '📄' },
    { label: 'Extracting textbook content', icon: '📚' },
    { label: 'Running Fusion Agent', icon: '🧠' },
    { label: 'Calibrating to your level', icon: '🎯' },
    { label: 'Building concept map', icon: '🕸️' },
    { label: 'Finalising notes', icon: '✨' },
];

function FuseProgressBar({ active }) {
    const [step, setStep] = useState(0);
    const [dots, setDots] = useState('');
    const [overdue, setOverdue] = useState(false); // true after 45 s — warn student
    useEffect(() => {
        if (!active) { setStep(0); setDots(''); setOverdue(false); return; }
        // Advance through first 5 steps, then hold on step 4 (Fusion Agent) — never bounce back
        const st = setInterval(() => setStep(s => {
            if (s < 4) return s + 1;   // advance up to "Calibrating"
            if (s === 4) return 3;     // loop: Calibrating → Fusion Agent (same phase, stay here)
            return s;                  // steps 5+ only set manually when truly done
        }), 3500);
        const dt = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 400);
        const ot = setTimeout(() => setOverdue(true), 45_000); // 45 s
        return () => { clearInterval(st); clearInterval(dt); clearTimeout(ot); };
    }, [active]);
    if (!active) return null;
    return (
        <div style={{ marginBottom: 20, background: overdue ? '#FFFBEB' : 'var(--surface)', border: `1px solid ${overdue ? '#FDE68A' : 'var(--border)'}`, borderRadius: 12, padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: 22 }}>{FUSE_STEPS[step].icon}</span>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{FUSE_STEPS[step].label}{dots}</div>
                    <div style={{ fontSize: 11, color: overdue ? '#92400E' : 'var(--text3)', marginTop: 2, fontWeight: overdue ? 600 : 400 }}>
                        {overdue
                            ? '⚠️ Large upload detected — AI is still working, please keep this tab open'
                            : `Step ${step + 1} of ${FUSE_STEPS.length} — processing your materials${step >= 3 ? ' (large books may take a few minutes)' : ''}`}
                    </div>
                </div>
            </div>
            <div style={{ height: 4, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: 4, background: 'linear-gradient(90deg, #7C3AED, #2563EB)', width: `${((step + 1) / FUSE_STEPS.length) * 100}%`, transition: 'width 0.6s ease' }} />
            </div>
            <div style={{ display: 'flex', gap: 5, marginTop: 10 }}>
                {FUSE_STEPS.map((s, i) => (
                    <div key={i} title={s.label} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= step ? '#7C3AED' : 'var(--border)', transition: 'background 0.4s' }} />
                ))}
            </div>
        </div>
    );
}

// ─── FileDrop ─────────────────────────────────────────────────────────────────
function FileDrop({ label, icon, files, onFiles, imageOnly = false }) {
    const ref = useRef();
    const [drag, setDrag] = useState(false);
    const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic', '.heif', '.tiff', '.tif']);
    const isImage = (f) => IMAGE_EXTS.has(f.name.slice(f.name.lastIndexOf('.')).toLowerCase());
    const addFiles = (incoming) => {
        const valid = Array.from(incoming).filter(f =>
            imageOnly
                ? isImage(f)
                : (f.type === 'application/pdf' ||
                    f.name.endsWith('.pdf') ||
                    f.name.endsWith('.pptx') ||
                    f.name.endsWith('.ppt') ||
                    isImage(f))
        );
        if (valid.length) onFiles(prev => [...prev, ...valid]);
    };
    const DropIcon = icon || BookOpen;
    const hasFiles = files.length > 0;
    const totalMB = (files.reduce((s, f) => s + f.size, 0) / 1024 / 1024).toFixed(1);
    const fileIcon = (f) => isImage(f) ? '🖼️' : f.name.endsWith('.pptx') || f.name.endsWith('.ppt') ? '📊' : '📄';
    return (
        <div data-testid={`file-drop-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')}`}
            onDragOver={e => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            style={{ border: `2px dashed ${drag ? 'var(--text)' : hasFiles ? '#10B981' : 'var(--border2)'}`, borderRadius: 12, padding: 16, background: drag ? 'var(--surface2)' : hasFiles ? 'var(--zone-files-bg)' : 'var(--surface)', transition: 'all 0.15s', minHeight: 140 }}>
            <input ref={ref} type="file" accept={imageOnly ? ".jpg,.jpeg,.png,.webp,.heic,.heif,.bmp,.tiff,.tif" : ".pdf,.pptx,.ppt,.jpg,.jpeg,.png,.webp,.heic,.heif,.bmp,.tiff,.tif"} multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
            {!hasFiles ? (
                <div onClick={() => ref.current.click()} style={{ textAlign: 'center', cursor: 'pointer', padding: '12px 0' }}>
                    <DropIcon size={26} color="var(--text3)" style={{ margin: '0 auto 8px', display: 'block' }} />
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text2)' }}>{label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>{imageOnly ? 'JPG · PNG · WebP · HEIC · TIFF' : 'PDF · PPTX · JPG · PNG · WebP · HEIC'}</div>
                    <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2 }}>Drag & drop or click to browse</div>
                    <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 1, opacity: 0.65 }}>Up to 500 MB per upload session</div>
                </div>
            ) : (
                <>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
                        {files.map((f, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--file-chip-bg)', borderRadius: 6, padding: '6px 10px', border: '1px solid var(--file-chip-border)' }}>
                                <span style={{ fontSize: 14, flexShrink: 0 }}>{fileIcon(f)}</span>
                                <span style={{ fontSize: 12, color: 'var(--file-chip-text)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                                <span style={{ fontSize: 10, color: 'var(--text3)' }}>{(f.size / 1024 / 1024).toFixed(1)}MB</span>
                                <button onClick={e => { e.stopPropagation(); onFiles(prev => prev.filter((_, j) => j !== i)); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text3)', display: 'flex' }}><X size={12} /></button>
                            </div>
                        ))}
                    </div>
                    <button onClick={() => ref.current.click()} style={{ width: '100%', padding: 6, background: 'transparent', border: '1px dashed #6ee7b7', borderRadius: 6, color: '#10B981', fontSize: 11, cursor: 'pointer', fontWeight: 600 }}>
                        + Add more · {files.length} file{files.length > 1 ? 's' : ''} · {totalMB} MB
                    </button>
                </>
            )}
        </div>
    );
}

// ─── Mutation / Doubt Modal ───────────────────────────────────────────────────
function MutateModal({ page, notebookId, pageIdx, onClose, onMutate, onDoubtAnswered, initialDoubt = '' }) {
    const [doubt, setDoubt] = useState(initialDoubt);
    const [busy, setBusy] = useState(false);
    const [answer, setAnswer] = useState('');
    const [answerSource, setAnswerSource] = useState('');
    const [answerVerification, setAnswerVerification] = useState('correct');
    const [answerCorrection, setAnswerCorrection] = useState('');
    const [answerFootnote, setAnswerFootnote] = useState('');
    const [mode, setMode] = useState('idle'); // 'idle' | 'answering' | 'answered' | 'mutating'

    const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    function authHeaders() {
        const token = localStorage.getItem('ag_token') || 'demo-token';
        return { Authorization: `Bearer ${token}` };
    }

    const askDoubt = async () => {
        if (!doubt.trim()) return;
        setBusy(true); setMode('answering'); setAnswer('');
        try {
            const res = await fetch(`${API}/api/doubt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ notebook_id: notebookId, doubt, page_idx: pageIdx })
            });
            if (res.ok) {
                const data = await res.json();
                setAnswer(data.answer || '');
                setAnswerSource(data.source || 'local');
                setAnswerVerification(data.verification_status || 'correct');
                setAnswerCorrection(data.correction || '');
                setAnswerFootnote(data.footnote || '');
                // Save to doubts sidebar so the answer persists after modal closes
                if (onDoubtAnswered && data.answer) {
                    onDoubtAnswered({ doubt, answer: data.answer, source: data.source || 'local' });
                }
            } else {
                setAnswer('Could not get an answer. Try again or use Mutate to rewrite this page.');
            }
            setMode('answered');
        } catch {
            setAnswer('Backend unreachable. Your doubt has been logged.');
            setMode('answered');
        }
        setBusy(false);
    };

    const doMutate = async () => {
        if (!doubt.trim()) return;
        setBusy(true); setMode('mutating');
        await onMutate(page, doubt);
        setBusy(false);
        onClose();
    };

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in" onClick={e => e.stopPropagation()} style={{ maxWidth: 560, width: '100%' }}>
                <h3 style={{ marginBottom: 4 }}>Ask a Doubt</h3>
                <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 16, lineHeight: 1.6 }}>
                    Get an instant answer, or permanently rewrite this page to resolve it.
                </p>
                <div style={{ background: 'var(--surface)', borderRadius: 8, padding: 12, fontSize: 12, color: 'var(--text2)', lineHeight: 1.7, marginBottom: 14, maxHeight: 80, overflow: 'hidden', border: '1px solid var(--border)' }}>
                    {page ? (page.length > 200 ? page.slice(0, page.lastIndexOf(' ', 200)) + '…' : page) : ''}
                </div>
                <textarea className="input" rows={3} autoFocus value={doubt}
                    onChange={e => setDoubt(e.target.value)}
                    onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') askDoubt(); if (e.key === 'Escape') onClose(); }}
                    placeholder="e.g. Why does convolution become multiplication in the frequency domain?"
                    style={{ resize: 'vertical', fontFamily: 'inherit', marginBottom: 8 }}
                />
                <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 12 }}>
                    <kbd style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 5px', fontSize: 10 }}>Ctrl+Enter</kbd> to ask
                </div>

                {/* Answer panel */}
                {(mode === 'answering' || mode === 'answered') && (
                    <div style={{ background: '#F0F9FF', border: '1px solid #BAE6FD', borderRadius: 8, padding: 14, marginBottom: 14, maxHeight: 340, overflowY: 'auto' }}>
                        <div style={{ fontSize: 11, color: '#0369A1', fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Brain size={12} /> AuraGraph Answer {answerSource === 'azure' ? '(GPT-4o · verified)' : answerSource === 'groq' ? '(Groq · verified)' : '(offline)'}
                        </div>
                        {mode === 'answering'
                            ? <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#0369A1', fontSize: 13 }}><Loader2 className="spin" size={14} /> Verifying against slides, textbook and model knowledge…</div>
                            : (
                                <>
                                    {/* Main answer */}
                                    <div style={{ fontSize: 13, lineHeight: 1.8, color: '#0C4A6E' }}>
                                        <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{answer}</ReactMarkdown>
                                    </div>

                                    {/* Verification badge */}
                                    {answerVerification === 'correct' && (
                                        <div style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 5, background: '#DCFCE7', border: '1px solid #BBF7D0', borderRadius: 6, padding: '4px 10px', fontSize: 11, color: '#166534', fontWeight: 600 }}>
                                            <CheckCircle2 size={11} /> Notes verified — content is correct
                                        </div>
                                    )}
                                    {answerVerification === 'partially_correct' && (
                                        <div style={{ marginTop: 10, background: '#FFFBEB', border: '1px solid #FDE68A', borderRadius: 8, padding: '10px 12px' }}>
                                            <div style={{ fontSize: 11, fontWeight: 700, color: '#92400E', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 5 }}>
                                                <AlertCircle size={12} /> Notes are partially correct
                                            </div>
                                            <div style={{ fontSize: 12, lineHeight: 1.7, color: '#78350F' }}>
                                                <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{answerCorrection}</ReactMarkdown>
                                            </div>
                                            {answerFootnote && <div style={{ fontSize: 11, color: '#92400E', marginTop: 4, fontStyle: 'italic' }}>{answerFootnote}</div>}
                                        </div>
                                    )}
                                    {answerVerification === 'incorrect' && (
                                        <div style={{ marginTop: 10, background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 8, padding: '10px 12px' }}>
                                            <div style={{ fontSize: 11, fontWeight: 700, color: '#991B1B', marginBottom: 4, display: 'flex', alignItems: 'center', gap: 5 }}>
                                                <MinusCircle size={12} /> Notes contain an error
                                            </div>
                                            <div style={{ fontSize: 12, lineHeight: 1.7, color: '#7F1D1D' }}>
                                                <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{answerCorrection}</ReactMarkdown>
                                            </div>
                                            {answerFootnote && <div style={{ fontSize: 11, color: '#991B1B', marginTop: 4, fontStyle: 'italic' }}>{answerFootnote}</div>}
                                        </div>
                                    )}
                                </>
                            )
                        }
                    </div>
                )}

                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                    <button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
                    <button className="btn btn-ghost btn-sm" onClick={askDoubt} disabled={busy || !doubt.trim()} style={{ gap: 6, borderColor: '#0369A1', color: '#0369A1' }}>
                        {mode === 'answering' ? <Loader2 className="spin" size={14} /> : <MessageCircle size={14} />}
                        {mode === 'answering' ? 'Searching…' : 'Ask (get answer)'}
                    </button>
                    <button className="btn btn-primary btn-sm" onClick={doMutate} disabled={busy || !doubt.trim()} style={{ gap: 6 }} title="Permanently rewrites this page to incorporate your doubt">
                        {mode === 'mutating' ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}
                        {mode === 'mutating' ? 'Rewriting…' : 'Rewrite This Page'}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Practice Questions with per-question Show Answer ───────────────────────
function PracticeQuestions({ text }) {
    const [revealed, setRevealed] = useState(new Set());
    const blocks = text.split(/(?=^Q\d+\.)/m).filter(b => b.trim());
    if (!blocks.length) {
        return <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{text}</ReactMarkdown>;
    }
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {blocks.map((block, i) => {
                const markerIdx = block.search(/✅|Correct:/);
                const hasAnswer = markerIdx !== -1;
                const questionPart = hasAnswer ? block.slice(0, markerIdx).trimEnd() : block;
                const answerPart = hasAnswer ? block.slice(markerIdx) : '';
                const isRevealed = revealed.has(i);
                return (
                    <div key={i} style={{ background: 'var(--bg)', borderRadius: 10, border: '1px solid var(--border)', overflow: 'hidden' }}>
                        <div style={{ padding: '14px 16px', fontSize: 13, lineHeight: 1.8 }}>
                            <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{questionPart}</ReactMarkdown>
                        </div>
                        {hasAnswer && (
                            <div style={{ borderTop: '1px solid var(--border)' }}>
                                {!isRevealed ? (
                                    <button onClick={() => setRevealed(prev => new Set([...prev, i]))} style={{ width: '100%', padding: '9px 16px', background: 'var(--surface)', border: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: '#7C3AED', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                                        <CheckCircle2 size={13} /> Show Answer
                                    </button>
                                ) : (
                                    <div style={{ padding: '12px 16px', background: '#F0FDF4', fontSize: 13, lineHeight: 1.8 }}>
                                        <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{answerPart}</ReactMarkdown>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}

// ─── Examiner Modal ───────────────────────────────────────────────────────────
function ExaminerModal({ concept, notebookId, onClose }) {
    const [questions, setQuestions] = useState('');
    const [loading, setLoading] = useState(true);
    const [customInstruction, setCustomInstruction] = useState('');

    const generate = useCallback(async (ci) => {
        setLoading(true);
        try {
            const res = await fetch(`${API}/api/examine`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({
                    concept_name: concept,
                    ...(notebookId ? { notebook_id: notebookId } : {}),
                    ...(ci.trim() ? { custom_instruction: ci.trim() } : {}),
                }),
            });
            const data = await res.json();
            setQuestions(data.practice_questions);
        } catch { setQuestions(`## Practice Questions: ${concept}\n\nBackend not reachable.`); }
        finally { setLoading(false); }
    }, [concept]);

    useEffect(() => { generate(''); }, [concept]);

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in" onClick={e => e.stopPropagation()} style={{ width: 600, maxWidth: '96vw', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <div><h3 style={{ marginBottom: 2 }}>Practice Questions</h3><p style={{ fontSize: 12, color: 'var(--text3)' }}>Generated for: <b>{concept}</b></p></div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={18} /></button>
                </div>
                {/* Custom instruction row */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                    <input
                        value={customInstruction}
                        onChange={e => setCustomInstruction(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') generate(customInstruction); }}
                        placeholder="Custom focus, e.g. numerical only, proof-based, match exam pattern…"
                        style={{ flex: 1, fontSize: 12, padding: '7px 11px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', outline: 'none', fontFamily: 'inherit' }}
                    />
                    <button
                        onClick={() => generate(customInstruction)}
                        disabled={loading}
                        className="btn btn-secondary btn-sm"
                        style={{ flexShrink: 0, gap: 5 }}
                    >
                        {loading ? <Loader2 className="spin" size={13} /> : <RefreshCw size={13} />}
                        {loading ? 'Generating…' : 'Generate'}
                    </button>
                </div>
                <div style={{ flex: 1, overflowY: 'auto', background: 'var(--surface)', borderRadius: 10, padding: 16, border: '1px solid var(--border)' }}>
                    {loading ? <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text3)', fontSize: 13 }}><Loader2 className="spin" size={16} /> Generating questions…</div>
                        : <PracticeQuestions text={questions} />}
                </div>
                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}><button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button></div>
            </div>
        </div>
    );
}


// ─── Dark Mode hook ────────────────────────────────────────────────────────────
function useDarkMode() {
    const [dark, setDark] = React.useState(() => localStorage.getItem('ag_dark') === '1');
    React.useEffect(() => {
        document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
        localStorage.setItem('ag_dark', dark ? '1' : '0');
    }, [dark]);
    return [dark, setDark];
}

// ─── GalaxyGraph ──────────────────────────────────────────────────────────────
function GalaxyGraph({ nodes, edges, onNodeClick, selectedNodeId }) {
    const canvasRef = React.useRef();
    const animRef   = React.useRef();
    const starsRef  = React.useRef([]);
    const W = 280, H = 360;

    // Init stars once
    React.useEffect(() => {
        starsRef.current = Array.from({ length: 28 }, () => ({
            x: Math.random() * W, y: Math.random() * H,
            r: Math.random() * 1.2 + 0.3,
            alpha: Math.random() * 0.7 + 0.3,
            speed: Math.random() * 0.008 + 0.003,
            phase: Math.random() * Math.PI * 2,
        }));
    }, []);

    React.useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

        let t = 0;
        const getPos = n => ({ x: (n.x / 100) * (W - 60) + 30, y: (n.y / 100) * (H - 60) + 30 });
        const statusColor = { mastered: '#10B981', partial: '#F59E0B', struggling: '#EF4444' };
        const nodeById = Object.fromEntries((nodes || []).map(n => [n.id, n]));

        const draw = () => {
            t += 0.016;
            ctx.clearRect(0, 0, W, H);

            // Background
            const bg = ctx.createRadialGradient(W/2, H/2, 0, W/2, H/2, Math.max(W,H)/1.2);
            bg.addColorStop(0, isDark ? '#08081A' : '#0a0a1e');
            bg.addColorStop(1, isDark ? '#020208' : '#050510');
            ctx.fillStyle = bg;
            ctx.fillRect(0, 0, W, H);

            // Stars
            for (const s of starsRef.current) {
                const a = s.alpha * (0.5 + 0.5 * Math.sin(t * s.speed * 60 + s.phase));
                ctx.beginPath();
                ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
                ctx.fillStyle = `rgba(255,255,255,${a})`;
                ctx.fill();
            }

            // Edges
            for (const e of (edges || [])) {
                const s = nodeById[e[0]], d = nodeById[e[1]];
                if (!s || !d) continue;
                const sp = getPos(s), dp = getPos(d);
                ctx.beginPath();
                ctx.moveTo(sp.x, sp.y);
                ctx.lineTo(dp.x, dp.y);
                const grad = ctx.createLinearGradient(sp.x, sp.y, dp.x, dp.y);
                grad.addColorStop(0, statusColor[s.status] + '66');
                grad.addColorStop(1, statusColor[d.status] + '66');
                ctx.strokeStyle = grad;
                ctx.lineWidth = 1.2;
                ctx.setLineDash([4, 4]);
                ctx.stroke();
                ctx.setLineDash([]);
            }

            // Nodes
            for (const n of (nodes || [])) {
                const { x, y } = getPos(n);
                const c = statusColor[n.status] || '#F59E0B';
                const isSel = n.id === selectedNodeId;
                const pulse = 1 + 0.12 * Math.sin(t * 2 + (n.x + n.y) / 40);

                // Outer glow ring (animated)
                const glowR = (isSel ? 22 : 16) * pulse;
                const glowGrad = ctx.createRadialGradient(x, y, 0, x, y, glowR);
                glowGrad.addColorStop(0, c + '44');
                glowGrad.addColorStop(1, c + '00');
                ctx.beginPath();
                ctx.arc(x, y, glowR, 0, Math.PI * 2);
                ctx.fillStyle = glowGrad;
                ctx.fill();

                // Selection ring
                if (isSel) {
                    ctx.beginPath();
                    ctx.arc(x, y, 18, 0, Math.PI * 2);
                    ctx.strokeStyle = c + 'CC';
                    ctx.lineWidth = 2;
                    ctx.setLineDash([3, 3]);
                    ctx.stroke();
                    ctx.setLineDash([]);
                }

                // Core orb
                const orbGrad = ctx.createRadialGradient(x - 3, y - 3, 1, x, y, 10);
                orbGrad.addColorStop(0, c + 'FF');
                orbGrad.addColorStop(0.6, c + 'CC');
                orbGrad.addColorStop(1, c + '88');
                ctx.beginPath();
                ctx.arc(x, y, 10, 0, Math.PI * 2);
                ctx.fillStyle = orbGrad;
                ctx.fill();

                // Mutation badge
                if ((n.mutation_count || 0) > 0) {
                    ctx.beginPath();
                    ctx.arc(x + 8, y - 8, 5, 0, Math.PI * 2);
                    ctx.fillStyle = '#7C3AED';
                    ctx.fill();
                    ctx.fillStyle = '#fff';
                    ctx.font = 'bold 7px Space Grotesk, sans-serif';
                    ctx.textAlign = 'center';
                    ctx.textBaseline = 'middle';
                    ctx.fillText(n.mutation_count, x + 8, y - 8);
                }

                // Label
                const lbl = n.label.length > 14 ? n.label.slice(0, 12) + '…' : n.label;
                ctx.font = `${isSel ? 'bold ' : ''}9px Space Grotesk, sans-serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'top';
                ctx.fillStyle = isSel ? '#fff' : 'rgba(255,255,255,0.8)';
                ctx.fillText(lbl, x, y + 13);
            }

            animRef.current = requestAnimationFrame(draw);
        };
        draw();
        return () => cancelAnimationFrame(animRef.current);
    }, [nodes, edges, selectedNodeId]);

    const handleClick = (e) => {
        if (!nodes?.length) return;
        const rect = canvasRef.current.getBoundingClientRect();
        const scaleX = W / rect.width, scaleY = H / rect.height;
        const mx = (e.clientX - rect.left) * scaleX;
        const my = (e.clientY - rect.top)  * scaleY;
        const getPos = n => ({ x: (n.x / 100) * (W - 60) + 30, y: (n.y / 100) * (H - 60) + 30 });
        const hit = nodes.find(n => { const p = getPos(n); return Math.hypot(p.x - mx, p.y - my) < 14; });
        if (hit) onNodeClick?.(hit);
    };

    if (!nodes?.length) return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, color: 'var(--text3)', fontSize: 12, textAlign: 'center', padding: '0 16px' }}>
            <Brain size={28} color="var(--border2)" style={{ marginBottom: 10 }} />
            <p>Concept graph appears after generating notes.</p>
        </div>
    );

    return (
        <canvas ref={canvasRef} width={W} height={H}
            className="galaxy-canvas"
            style={{ display: 'block', width: '100%', cursor: 'pointer', borderRadius: 12 }}
            onClick={handleClick}
        />
    );
}

// ─── SniperExamModal ──────────────────────────────────────────────────────────
function SniperExamModal({ nodes, notebookId, onClose }) {
    const weakNodes = nodes.filter(n => n.status === 'struggling' || n.status === 'partial');
    const [questions, setQuestions] = React.useState([]);
    const [loading, setLoading]     = React.useState(true);
    const [qIdx, setQIdx]           = React.useState(0);
    const [selected, setSelected]   = React.useState(null);
    const [revealed, setRevealed]   = React.useState(false);
    const [score, setScore]         = React.useState(0);
    const [done, setDone]           = React.useState(false);

    React.useEffect(() => {
        (async () => {
            try {
                const res = await fetch(`${API}/api/sniper-exam`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', ...authHeaders() },
                    body: JSON.stringify({
                        weak_concepts: weakNodes.map(n => n.label),
                        ...(notebookId ? { notebook_id: notebookId } : {}),
                    }),
                });
                const data = await res.json();
                setQuestions(data.questions || []);
            } catch {
                setQuestions([]);
            } finally {
                setLoading(false);
            }
        })();
    }, []);

    const current = questions[qIdx];
    const total   = questions.length;

    const handleSelect = (opt) => {
        if (revealed) return;
        setSelected(opt);
        setRevealed(true);
        if (opt === current.correct) setScore(s => s + 1);
    };

    const next = () => {
        if (qIdx + 1 >= total) { setDone(true); return; }
        setQIdx(i => i + 1);
        setSelected(null);
        setRevealed(false);
    };

    const pct = total > 0 ? Math.round((score / total) * 100) : 0;

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()} style={{ maxWidth: 560, width: '96vw' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ fontSize: 22 }}>🎯</div>
                        <div>
                            <h3 style={{ marginBottom: 1 }}>Sniper Exam</h3>
                            <p style={{ fontSize: 11, color: 'var(--text3)' }}>Targeted at your weak concepts</p>
                        </div>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={18} /></button>
                </div>

                {loading && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '30px 0', justifyContent: 'center', color: 'var(--text3)', fontSize: 13 }}>
                        <Loader2 className="spin" size={18} /> Generating targeted questions…
                    </div>
                )}

                {!loading && done && (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <div style={{ fontSize: 48, marginBottom: 12 }}>{pct >= 70 ? '🏆' : pct >= 40 ? '📈' : '💪'}</div>
                        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>{score}/{total} correct</div>
                        <div style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 20 }}>
                            {pct >= 70 ? 'Great job! Your weak areas are improving.' : pct >= 40 ? 'Good effort — keep practising these concepts.' : 'Keep going — revisit these topics in your notes.'}
                        </div>
                        <div className="progress-bar-track" style={{ marginBottom: 20 }}>
                            <div className="progress-bar-fill" style={{ width: `${pct}%`, background: pct >= 70 ? 'linear-gradient(90deg,#10B981,#34D399)' : pct >= 40 ? 'linear-gradient(90deg,#F59E0B,#FCD34D)' : 'linear-gradient(90deg,#EF4444,#FCA5A5)' }} />
                        </div>
                        <button className="btn btn-primary" onClick={onClose}>Done</button>
                    </div>
                )}

                {!loading && !done && total === 0 && (
                    <div style={{ padding: '20px 0', textAlign: 'center', color: 'var(--text3)', fontSize: 13 }}>
                        No questions available — make sure the backend is running.
                    </div>
                )}

                {!loading && !done && current && (
                    <>
                        {/* Progress */}
                        <div style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text3)', marginBottom: 5, fontWeight: 600 }}>
                                <span>Question {qIdx + 1} of {total}</span>
                                <span style={{ color: '#10B981' }}>Score: {score}</span>
                            </div>
                            <div className="progress-bar-track">
                                <div className="progress-bar-fill" style={{ width: `${((qIdx) / total) * 100}%`, background: 'linear-gradient(90deg,#7C3AED,#2563EB)' }} />
                            </div>
                        </div>

                        {/* Concept tag */}
                        {current.concept && (
                            <div style={{ marginBottom: 10, display: 'inline-flex', alignItems: 'center', gap: 5, background: 'var(--purple-light)', color: 'var(--purple)', borderRadius: 6, padding: '3px 10px', fontSize: 11, fontWeight: 600 }}>
                                🎯 {current.concept}
                            </div>
                        )}

                        {/* Question */}
                        <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.7, color: 'var(--text)', marginBottom: 16, padding: '12px 14px', background: 'var(--surface)', borderRadius: 10, border: '1px solid var(--border)' }}>
                            <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}>{current.question}</ReactMarkdown>
                        </div>

                        {/* Options */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                            {['A', 'B', 'C', 'D'].map(opt => (
                                <button key={opt}
                                    className={`sniper-option${revealed && opt === current.correct ? ' correct' : revealed && opt === selected && opt !== current.correct ? ' wrong' : ''}`}
                                    onClick={() => handleSelect(opt)}
                                    disabled={revealed}
                                >
                                    <span style={{ fontWeight: 700, marginRight: 8 }}>{opt})</span>
                                    {current.options?.[opt] || ''}
                                    {revealed && opt === current.correct && <span style={{ float: 'right' }}>✅</span>}
                                    {revealed && opt === selected && opt !== current.correct && <span style={{ float: 'right' }}>❌</span>}
                                </button>
                            ))}
                        </div>

                        {/* Explanation */}
                        {revealed && current.explanation && (
                            <div style={{ padding: '10px 12px', borderRadius: 8, background: selected === current.correct ? '#DCFCE7' : '#FEF2F2', border: `1px solid ${selected === current.correct ? '#BBF7D0' : '#FECACA'}`, fontSize: 12, lineHeight: 1.7, marginBottom: 14, color: selected === current.correct ? '#065F46' : '#991B1B' }}>
                                <span style={{ fontWeight: 700 }}>Explanation: </span>{current.explanation}
                            </div>
                        )}

                        {revealed && (
                            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                <button className="btn btn-primary" onClick={next}>
                                    {qIdx + 1 >= total ? 'See Results' : 'Next Question →'}
                                </button>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    );
}

// ─── Study Timer (Pomodoro) ───────────────────────────────────────────────────
function StudyTimer() {
    const MODES = { focus: 25 * 60, short: 5 * 60, long: 15 * 60 };
    const [mode, setMode]       = React.useState('focus');
    const [secs, setSecs]       = React.useState(MODES.focus);
    const [running, setRunning] = React.useState(false);
    const [sessions, setSessions] = React.useState(() => parseInt(localStorage.getItem('ag_sessions') || '0'));
    const [open, setOpen]       = React.useState(false);
    const timerRef = React.useRef();

    React.useEffect(() => {
        if (running) {
            timerRef.current = setInterval(() => {
                setSecs(s => {
                    if (s <= 1) {
                        clearInterval(timerRef.current);
                        setRunning(false);
                        if (mode === 'focus') {
                            const n = sessions + 1;
                            setSessions(n);
                            localStorage.setItem('ag_sessions', n);
                        }
                        try { new Audio('data:audio/wav;base64,//uQRAAAAWMSLwUIYAAsYkXgoQwAEaYLWfkWgAI0wWs/ItAAAGDgYtAgAyN+QWaAAihwMWm4G8QQRDiMcCBcH3Cc+CDv/7xA4Tvh9Rz/y8QADBwMWgQAZG/ILNAARQ4GLTcDeIIIhxGOBAuD7hOfBB3/94gcJ3w+o5/5eIAIAAAVwWgQAVQ2ORaIQwEMAJiDg95G4nQL7mQVWI6GwRcfsZAcsKkJvxgxEjzFUgfHoSQ9Qq7KNwqHwuB13MA4a1q/DmBrHgPcmjiGoh//EwC5nGPEmS4RcfkVKOhJf+WOgoxJclFz3kgn//dBA+ya1GhurNn8zb//9NNutNuhz31f////9vt///z+IdAEAAAK4LQIAKobHItEIYCGAExBwe8jcToF9zIKrEdDYIuP2MgOWFSE34wYiR5iqQPj0JIeoVdlG4VD4XA67mAcNa1fhzA1jwHuTRxDUQ//iYBczjHiTJcIuPyKlHQkv/LHQUYkuSi57yQT//uggfZNajQ3Vmz+Zt//+mm3Wm3Q576v////+32///5/EOgAAADVghQAAAAA//uQZAUAB1WI0PZugAAAAAoQwAAAEk3nRd2qAAAAACiDgAAAAAAAi2BWACAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAAAAAAAAAAAAAAAAAAASVDhqgnAAAA').play(); } catch {}
                        return MODES[mode];
                    }
                    return s - 1;
                });
            }, 1000);
        }
        return () => clearInterval(timerRef.current);
    }, [running, mode]);

    const switchMode = (m) => { setMode(m); setSecs(MODES[m]); setRunning(false); };
    const mm = String(Math.floor(secs / 60)).padStart(2, '0');
    const ss = String(secs % 60).padStart(2, '0');
    const total = MODES[mode];
    const pct = secs / total;
    const R = 18, C = 2 * Math.PI * R;
    const isAlmostDone = secs < 60 && mode === 'focus';

    if (!open) return (
        <button onClick={() => setOpen(true)} className="btn btn-ghost btn-sm" title="Pomodoro timer" style={{ padding: '5px 8px', position: 'relative' }}>
            <Clock size={14} />
            {sessions > 0 && <span style={{ position: 'absolute', top: -2, right: -2, background: '#7C3AED', color: '#fff', fontSize: 8, fontWeight: 700, width: 14, height: 14, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{sessions}</span>}
        </button>
    );

    return (
        <div style={{ position: 'relative' }}>
            <div style={{ position: 'absolute', top: '100%', right: 0, marginTop: 6, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px', boxShadow: 'var(--shadow-md)', zIndex: 100, width: 200, animation: 'fadeIn 0.2s ease' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>⏱ Focus Timer</span>
                    <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={13} /></button>
                </div>
                {/* Mode tabs */}
                <div style={{ display: 'flex', gap: 3, marginBottom: 12, background: 'var(--surface)', borderRadius: 7, padding: 2 }}>
                    {[['focus','25m'],['short','5m'],['long','15m']].map(([m,l]) => (
                        <button key={m} onClick={() => switchMode(m)} style={{ flex: 1, padding: '4px 0', borderRadius: 5, border: 'none', cursor: 'pointer', background: mode === m ? 'var(--text)' : 'transparent', color: mode === m ? '#fff' : 'var(--text3)', fontSize: 10, fontWeight: 600, transition: 'all 0.15s' }}>{l}</button>
                    ))}
                </div>
                {/* SVG ring timer */}
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                    <svg width={80} height={80} viewBox="0 0 50 50">
                        <circle cx={25} cy={25} r={R} fill="none" stroke="var(--border)" strokeWidth={4} />
                        <circle cx={25} cy={25} r={R} fill="none"
                            stroke={isAlmostDone ? '#EF4444' : mode === 'focus' ? '#7C3AED' : '#10B981'}
                            strokeWidth={4}
                            strokeDasharray={`${pct * C} ${C}`}
                            strokeDashoffset={C * 0.25}
                            strokeLinecap="round"
                            style={{ transition: 'stroke-dasharray 0.5s ease, stroke 0.5s ease', transform: 'rotate(-90deg)', transformOrigin: '25px 25px' }}
                        />
                        <text x={25} y={28} textAnchor="middle" fontSize={9} fontWeight={700} fill={isAlmostDone ? '#EF4444' : 'var(--text)'} fontFamily="Space Grotesk, monospace">{mm}:{ss}</text>
                    </svg>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-primary btn-sm" style={{ flex: 1, fontSize: 11 }} onClick={() => setRunning(r => !r)}>
                        {running ? '⏸ Pause' : '▶ Start'}
                    </button>
                    <button className="btn btn-ghost btn-sm" style={{ padding: '6px 8px' }} onClick={() => { setSecs(MODES[mode]); setRunning(false); }} title="Reset">
                        <RefreshCw size={12} />
                    </button>
                </div>
                {sessions > 0 && <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text3)', textAlign: 'center' }}>🍅 {sessions} session{sessions > 1 ? 's' : ''} today</div>}
            </div>
        </div>
    );
}

// ─── NoteSearch ───────────────────────────────────────────────────────────────
function NoteSearch({ pages, onJumpToPage, onClose }) {
    const [query, setQuery] = React.useState('');
    const inputRef = React.useRef();
    React.useEffect(() => { inputRef.current?.focus(); }, []);

    const results = React.useMemo(() => {
        if (!query.trim() || query.length < 2) return [];
        const q = query.toLowerCase();
        return pages.map((page, idx) => {
            const lower = page.toLowerCase();
            const pos = lower.indexOf(q);
            if (pos === -1) return null;
            const start = Math.max(0, pos - 40);
            const end   = Math.min(page.length, pos + query.length + 60);
            const preview = (start > 0 ? '…' : '') + page.slice(start, end) + (end < page.length ? '…' : '');
            return { idx, preview, pos: pos - start + (start > 0 ? 1 : 0) };
        }).filter(Boolean);
    }, [query, pages]);

    const highlight = (text, q) => {
        const idx = text.toLowerCase().indexOf(q.toLowerCase());
        if (idx === -1) return text;
        return <>{text.slice(0, idx)}<mark style={{ background: 'rgba(250,204,21,0.5)', borderRadius: 2, padding: '0 1px' }}>{text.slice(idx, idx + q.length)}</mark>{text.slice(idx + q.length)}</>;
    };

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()} style={{ maxWidth: 500, padding: '16px 16px 10px' }}>
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                    <input ref={inputRef} className="input" placeholder="Search in notes… (e.g. Fourier, gradient)" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Escape' && onClose()} style={{ flex: 1 }} />
                    <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={14} /></button>
                </div>
                <div style={{ maxHeight: 320, overflowY: 'auto' }}>
                    {query.length >= 2 && results.length === 0 && (
                        <div style={{ padding: '16px 0', textAlign: 'center', color: 'var(--text3)', fontSize: 13 }}>No results for "{query}"</div>
                    )}
                    {results.map(r => (
                        <button key={r.idx} onClick={() => { onJumpToPage(r.idx); onClose(); }} style={{ display: 'block', width: '100%', textAlign: 'left', padding: '10px 12px', borderRadius: 8, border: '1px solid transparent', background: 'var(--surface)', marginBottom: 6, cursor: 'pointer', transition: 'all 0.12s' }}
                            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--purple)'; e.currentTarget.style.background = 'var(--purple-light)'; }}
                            onMouseLeave={e => { e.currentTarget.style.borderColor = 'transparent'; e.currentTarget.style.background = 'var(--surface)'; }}>
                            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--purple)', marginBottom: 3 }}>Page {r.idx + 1}</div>
                            <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.6 }}>{highlight(r.preview.replace(/[#*`]/g, ''), query)}</div>
                        </button>
                    ))}
                </div>
                {query.length < 2 && <div style={{ padding: '8px 0', textAlign: 'center', fontSize: 11, color: 'var(--text3)' }}>Type at least 2 characters to search</div>}
            </div>
        </div>
    );
}

// ─── KeyboardShortcutsModal ───────────────────────────────────────────────────
function ShortcutsModal({ onClose }) {
    const shorts = [
        ['← / →', 'Previous / Next page'],
        ['Click page counter', 'Jump to any page number'],
        ['Ctrl+D', 'Ask a doubt / Rewrite page'],
        ['Ctrl+F', 'Search in notes'],
        ['Ctrl+Enter', 'Submit doubt in modal'],
        ['Esc', 'Close modal / selection'],
    ];
    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()} style={{ maxWidth: 360 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <h3>⌨️ Keyboard Shortcuts</h3>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={16} /></button>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {shorts.map(([k, d]) => (
                        <div key={k} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 10px', borderRadius: 8, background: 'var(--surface)', border: '1px solid var(--border)' }}>
                            <kbd>{k}</kbd>
                            <span style={{ fontSize: 12, color: 'var(--text2)' }}>{d}</span>
                        </div>
                    ))}
                </div>
                <div style={{ marginTop: 14, fontSize: 11, color: 'var(--text3)', textAlign: 'center' }}>Press <kbd>Esc</kbd> to close</div>
            </div>
        </div>
    );
}


// ─── Knowledge Graph (fallback SVG) ─────────────────────────────────────────
const SC = { mastered: { fill: '#10B981', ring: '#6EE7B7' }, partial: { fill: '#F59E0B', ring: '#FCD34D' }, struggling: { fill: '#EF4444', ring: '#FCA5A5' } };

function KnowledgeGraph({ nodes, edges, onNodeClick, selectedNodeId }) {
    const W = 280, H = 400;
    if (!nodes?.length) return (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, color: 'var(--text3)', fontSize: 12, textAlign: 'center', padding: '0 16px' }}>
            <Brain size={28} color="var(--border2)" style={{ marginBottom: 10 }} />
            <p>Concept graph appears after generating notes.</p>
        </div>
    );
    const getPos = n => ({ cx: (n.x / 100) * (W - 60) + 30, cy: (n.y / 100) * (H - 60) + 30 });
    const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
    return (
        <svg width={W} height={H} style={{ display: 'block', width: '100%' }} viewBox={`0 0 ${W} ${H}`}>
            <defs>{nodes.map(n => { const c = SC[n.status] || SC.partial; return (<radialGradient key={n.id} id={`g-${n.id}`} cx="50%" cy="50%" r="50%"><stop offset="0%" stopColor={c.ring} stopOpacity="0.6" /><stop offset="100%" stopColor={c.fill} stopOpacity="1" /></radialGradient>); })}</defs>
            {edges.map((e, i) => { const s = nodeById[e[0]], d = nodeById[e[1]]; if (!s || !d) return null; const sp = getPos(s), dp = getPos(d); return <line key={i} x1={sp.cx} y1={sp.cy} x2={dp.cx} y2={dp.cy} stroke="var(--border2)" strokeWidth={1.5} strokeDasharray="4,3" opacity={0.7} />; })}
            {nodes.map(n => {
                const c = SC[n.status] || SC.partial; const { cx, cy } = getPos(n); const sel = n.id === selectedNodeId; const lbl = n.label.length > 16 ? n.label.slice(0, 14) + '…' : n.label; return (
                    <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => onNodeClick(n)}>
                        {sel && <circle cx={cx} cy={cy} r={20} fill="none" stroke={c.fill} strokeWidth={2} opacity={0.5} strokeDasharray="3,2" />}
                        <circle cx={cx} cy={cy} r={17} fill={c.ring} opacity={sel ? 0.4 : 0.2} />
                        <circle cx={cx} cy={cy} r={12} fill={`url(#g-${n.id})`} stroke={sel ? c.fill : 'transparent'} strokeWidth={2} />
                        <text x={cx} y={cy + 24} textAnchor="middle" fontSize={9} fill="var(--text2)" fontWeight={sel ? 700 : 500} style={{ pointerEvents: 'none', userSelect: 'none' }}>{lbl}</text>
                        {(n.mutation_count || 0) > 0 && <g>
                            <circle cx={cx + 9} cy={cy - 9} r={5.5} fill="#7C3AED" />
                            <text x={cx + 9} y={cy - 9 + 4} textAnchor="middle" fontSize={7} fill="#fff" fontWeight={700} style={{ pointerEvents: 'none', userSelect: 'none' }}>{n.mutation_count}</text>
                        </g>}
                    </g>
                );
            })}
        </svg>
    );
}

// ─── Question Cards (level-aware per-question Show Answer) ───────────────────
function QuestionCards({ questions, level, onAllAssessed }) {
    const [revealed, setRevealed] = useState(new Set());
    const [assessments, setAssessments] = useState({});  // idx → true/false
    const LC = {
        mastered: { bg: '#DCFCE7', border: '#BBF7D0', accent: '#10B981', text: '#065F46' },
        partial: { bg: '#FEF9C3', border: '#FDE68A', accent: '#D97706', text: '#78350F' },
        struggling: { bg: '#FEF2F2', border: '#FECACA', accent: '#DC2626', text: '#7F1D1D' },
    };
    const lc = LC[level] || LC.partial;

    const markAssessment = (i, gotIt) => {
        const next = { ...assessments, [i]: gotIt };
        setAssessments(next);
        const total = (questions || []).length;
        const assessed = Object.keys(next).length;
        const correct = Object.values(next).filter(Boolean).length;
        if (assessed === total && total > 0) onAllAssessed?.(correct, total);
    };
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(questions || []).map((q, i) => {
                const isRev = revealed.has(i);
                const wasAssessed = assessments[i] !== undefined;
                return (
                    <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
                        <div style={{ padding: '10px 12px', fontSize: 12.5, lineHeight: 1.65, color: 'var(--text)' }}>
                            <span style={{ fontWeight: 700, color: '#7C3AED', marginRight: 5 }}>{i + 1})</span>
                            <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]} components={{ p: ({ children }) => <span>{children}</span> }}>{q.question || ''}</ReactMarkdown>
                        </div>
                        <div style={{ padding: '4px 12px 8px', display: 'flex', flexDirection: 'column', gap: 4, borderTop: '1px solid var(--border)' }}>
                            {['A', 'B', 'C', 'D'].map(opt => {
                                const isCorrect = isRev && opt === q.correct;
                                return (
                                    <div key={opt} style={{ display: 'flex', gap: 7, padding: '5px 9px', borderRadius: 7, background: isCorrect ? lc.bg : 'transparent', border: `1px solid ${isCorrect ? lc.border : 'transparent'}`, fontSize: 12, lineHeight: 1.5, transition: 'background 0.2s' }}>
                                        <span style={{ fontWeight: 700, color: isCorrect ? lc.accent : '#9CA3AF', minWidth: 16, flexShrink: 0 }}>{opt})</span>
                                        <span style={{ color: isCorrect ? lc.text : 'var(--text2)', flex: 1 }}>
                                            <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]} components={{ p: ({ children }) => <span>{children}</span> }}>{q.options?.[opt] || ''}</ReactMarkdown>
                                        </span>
                                        {isCorrect && <CheckCircle2 size={11} color={lc.accent} style={{ flexShrink: 0, marginTop: 2 }} />}
                                    </div>
                                );
                            })}
                        </div>
                        <div style={{ borderTop: '1px solid var(--border)' }}>
                            {!isRev ? (
                                <button onClick={() => setRevealed(p => new Set([...p, i]))} style={{ width: '100%', padding: '8px 12px', background: 'var(--bg)', border: 'none', cursor: 'pointer', fontSize: 11, fontWeight: 600, color: '#7C3AED', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
                                    <CheckCircle2 size={12} /> Show Answer
                                </button>
                            ) : (
                                <>
                                    <div style={{ padding: '10px 12px', background: lc.bg }}>
                                        <div style={{ fontSize: 11, fontWeight: 700, color: lc.accent, marginBottom: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                                            <CheckCircle2 size={11} /> Answer: {q.correct}
                                        </div>
                                        <div style={{ fontSize: 11, lineHeight: 1.65, color: lc.text }}>
                                            <span style={{ fontWeight: 600 }}>Explanation: </span>{q.explanation || ''}
                                        </div>
                                    </div>
                                    {!wasAssessed ? (
                                        <div style={{ display: 'flex', borderTop: '1px solid var(--border)' }}>
                                            <button onClick={() => markAssessment(i, true)} style={{ flex: 1, padding: '6px 0', background: '#DCFCE7', border: 'none', borderRight: '1px solid #BBF7D0', cursor: 'pointer', fontSize: 10, fontWeight: 700, color: '#065F46', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                                                <CheckCircle2 size={10} /> Got it
                                            </button>
                                            <button onClick={() => markAssessment(i, false)} style={{ flex: 1, padding: '6px 0', background: '#FEF2F2', border: 'none', cursor: 'pointer', fontSize: 10, fontWeight: 700, color: '#991B1B', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                                                <X size={10} /> Missed it
                                            </button>
                                        </div>
                                    ) : (
                                        <div style={{ padding: '4px 12px', fontSize: 10, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 4, color: assessments[i] ? '#059669' : '#DC2626' }}>
                                            {assessments[i] ? <><CheckCircle2 size={10} /> Marked correct</> : <><X size={10} /> Marked incorrect</>}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// ─── Concept Detail Panel ─────────────────────────────────────────────────────
function ConceptDetailPanel({ node, notebookId, onClose, onStatusChange, onJumpToSection, onFullPractice }) {
    const [activeLevel, setActiveLevel] = useState(null);
    const [questions, setQuestions] = useState(null);
    const [loadingQ, setLoadingQ] = useState(false);
    const [promotion, setPromotion] = useState(null); // null | 'partial' | 'mastered' | 'top'
    const [customInstruction, setCustomInstruction] = useState('');

    const LEVELS = [
        { key: 'struggling', label: 'Easy', color: '#10B981', icon: <CheckCircle2 size={11} />, desc: 'Definitions & recall' },
        { key: 'partial',    label: 'Medium', color: '#F59E0B', icon: <MinusCircle size={11} />, desc: 'Exam-style problems' },
        { key: 'mastered',   label: 'Hard', color: '#EF4444', icon: <AlertCircle size={11} />, desc: 'Derivations & edge cases' },
    ];
    const statusColors = { mastered: '#10B981', partial: '#F59E0B', struggling: '#EF4444' };

    const fetchLevel = async (lk) => {
        if (activeLevel === lk && !customInstruction) { setActiveLevel(null); setQuestions(null); setPromotion(null); return; }
        setActiveLevel(lk); setLoadingQ(true); setQuestions(null); setPromotion(null);
        try {
            const res = await fetch(`${API}/api/concept-practice`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({
                    concept_name: node.label,
                    level: lk,
                    ...(notebookId ? { notebook_id: notebookId } : {}),
                    ...(customInstruction.trim() ? { custom_instruction: customInstruction.trim() } : {}),
                }),
            });
            const data = await res.json();
            setQuestions(data.questions || []);
        } catch { setQuestions([]); }
        setLoadingQ(false);
    };

    const handleAllAssessed = (correct, total) => {
        if (correct < Math.ceil(total * 0.67)) return;     // < 2/3 correct — no upgrade
        const NEXT = { struggling: 'partial', partial: 'mastered', mastered: null };
        const promoted = NEXT[node.status];
        if (promoted) { onStatusChange(node, promoted); setPromotion(promoted); }
        else setPromotion('top');
    };

    return (
        <div style={{ background: 'var(--bg)', borderRadius: 12, border: '1px solid var(--border)', boxShadow: 'var(--shadow-md)', margin: '0 12px 12px', overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{node.label}</div>
                    <div style={{ fontSize: 10, color: statusColors[node.status] || '#9CA3AF', fontWeight: 600, marginTop: 2, textTransform: 'capitalize' }}>&#9679; {node.status}</div>
                </div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: 0 }}><X size={14} /></button>
            </div>
            <div style={{ padding: '10px 14px', maxHeight: 520, overflowY: 'auto' }}>
                {/* Set mastery */}
                <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>Set mastery</div>
                <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
                    {LEVELS.map(l => (
                        <button key={l.key} onClick={() => onStatusChange(node, l.key)} style={{ flex: 1, padding: '5px 3px', borderRadius: 7, border: `1px solid ${node.status === l.key ? l.color : 'var(--border)'}`, background: node.status === l.key ? l.color + '18' : 'transparent', color: node.status === l.key ? l.color : 'var(--text3)', fontSize: 10, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
                            {node.status === l.key && l.icon} {l.label}
                        </button>
                    ))}
                </div>
                {/* Jump to notes */}
                <button onClick={() => onJumpToSection(node.full_label || node.label)} style={{ width: '100%', padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text2)', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginBottom: 12 }}>
                    <ChevronRight size={12} /> Jump to Concept in Notes
                </button>
                {/* Practice level picker */}
                <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>🎯 Practice Questions</div>
                <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                    {LEVELS.map(l => (
                        <button key={l.key} onClick={() => fetchLevel(l.key)} style={{ flex: 1, padding: '7px 4px', borderRadius: 8, border: `1px solid ${activeLevel === l.key ? l.color : 'var(--border)'}`, background: activeLevel === l.key ? l.color + '18' : 'var(--surface)', color: activeLevel === l.key ? l.color : 'var(--text3)', fontSize: 10, fontWeight: 600, cursor: 'pointer', textAlign: 'center', transition: 'all 0.15s' }}>
                            <div>{l.label}</div>
                            <div style={{ fontSize: 9, opacity: 0.7, marginTop: 1 }}>{l.desc}</div>
                        </button>
                    ))}
                </div>
                {/* Custom instruction input */}
                <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
                    <input
                        value={customInstruction}
                        onChange={e => setCustomInstruction(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && activeLevel) fetchLevel(activeLevel); }}
                        placeholder="Custom focus, e.g. numerical only, derivations…"
                        style={{ flex: 1, fontSize: 11, padding: '5px 9px', borderRadius: 7, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', outline: 'none', fontFamily: 'inherit' }}
                    />
                    {activeLevel && (
                        <button
                            onClick={() => fetchLevel(activeLevel)}
                            disabled={loadingQ}
                            title="Regenerate with this focus"
                            style={{ padding: '5px 9px', borderRadius: 7, border: '1px solid var(--purple)', background: 'var(--purple-light)', color: 'var(--purple)', fontSize: 11, fontWeight: 700, cursor: 'pointer', flexShrink: 0 }}
                        >
                            {loadingQ ? <Loader2 className="spin" size={11} /> : '↺'}
                        </button>
                    )}
                </div>
                {loadingQ && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '10px 0', fontSize: 12, color: 'var(--text3)' }}>
                        <Loader2 className="spin" size={13} /> Generating {activeLevel} questions…
                    </div>
                )}
                {questions && !loadingQ && (
                    questions.length === 0
                        ? <div style={{ fontSize: 12, color: 'var(--text3)', padding: '8px 0' }}>No questions returned — try again.</div>
                        : <QuestionCards questions={questions} level={activeLevel} onAllAssessed={handleAllAssessed} />
                )}
                {!loadingQ && promotion && (
                    <div style={{ margin: '10px 0 4px', padding: '9px 12px', borderRadius: 8, background: promotion === 'top' ? '#DCFCE7' : '#EDE9FE', border: `1px solid ${promotion === 'top' ? '#86EFAC' : '#C4B5FD'}`, fontSize: 11, fontWeight: 600, color: promotion === 'top' ? '#065F46' : '#5B21B6', display: 'flex', alignItems: 'center', gap: 6 }}>
                        <CheckCircle2 size={12} /> {promotion === 'top' ? '🏆 Already at peak mastery — well done!' : `⬆️ Level upgraded to ${promotion}! Graph updated.`}
                    </div>
                )}
                {/* Full practice paper */}
                <button onClick={() => onFullPractice(node.label)} style={{ width: '100%', marginTop: 14, padding: '8px 0', background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text3)', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 5 }}>
                    <Brain size={12} /> Full Practice Paper (5 Qs)
                </button>
            </div>
        </div>
    );
}

// ─── Knowledge Panel ──────────────────────────────────────────────────────────
function KnowledgePanel({ nodes, edges, notebookId, onNodeStatusChange, onJumpToSection }) {
    const [selectedNode, setSelectedNode] = useState(null);
    const [examinerConcept, setExaminerConcept] = useState(null);
    const [sniperOpen, setSniperOpen] = useState(false);
    const [nudgeDismissed, setNudgeDismissed] = useState(false);
    const handleNodeClick = n => setSelectedNode(p => p?.id === n.id ? null : n);
    const handleStatusChange = (node, status) => { onNodeStatusChange(node, status); setSelectedNode(p => p?.id === node.id ? { ...p, status } : p); };
    const mc = nodes.filter(n => n.status === 'mastered').length;
    const pc = nodes.filter(n => n.status === 'partial').length;
    const sc = nodes.filter(n => n.status === 'struggling').length;
    const weakCount = sc + pc;
    return (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
            {/* Sniper exam nudge — shown once when there are weak/struggling concepts */}
            {weakCount > 0 && !nudgeDismissed && nodes.length > 0 && (
                <div style={{ margin: '10px 12px 0', padding: '10px 12px', borderRadius: 9, background: sc > 0 ? '#FEF2F2' : '#FFFBEB', border: `1px solid ${sc > 0 ? '#FECACA' : '#FDE68A'}`, display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 18, flexShrink: 0 }}>🎯</span>
                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: sc > 0 ? '#991B1B' : '#92400E' }}>
                            {sc > 0 ? `${sc} concept${sc > 1 ? 's' : ''} in the red zone` : `${pc} concept${pc > 1 ? 's' : ''} need practice`}
                        </div>
                        <button onClick={() => setSniperOpen(true)} style={{ fontSize: 11, fontWeight: 600, color: sc > 0 ? '#DC2626' : '#D97706', background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline', marginTop: 1 }}>
                            Take Sniper Exam →
                        </button>
                    </div>
                    <button onClick={() => setNudgeDismissed(true)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: 2, flexShrink: 0 }}><X size={12} /></button>
                </div>
            )}
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8 }}>Cognitive Knowledge Map</div>
                {nodes.length > 0 && (
                    <div style={{ display: 'flex', gap: 6 }}>
                        {[['mastered', '#10B981', mc], ['partial', '#F59E0B', pc], ['struggling', '#EF4444', sc]].map(([k, c, count]) => (
                            <div key={k} style={{ flex: 1, textAlign: 'center', background: c + '15', borderRadius: 6, padding: 4, border: `1px solid ${c}33` }}>
                                <div style={{ fontSize: 16, fontWeight: 800, color: c }}>{count}</div>
                                <div style={{ fontSize: 9, color: c, textTransform: 'uppercase', fontWeight: 600 }}>{k}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0 0' }}>
                <KnowledgeGraph nodes={nodes} edges={edges} onNodeClick={handleNodeClick} selectedNodeId={selectedNode?.id} />
                {selectedNode && <ConceptDetailPanel node={selectedNode} notebookId={notebookId} onClose={() => setSelectedNode(null)} onStatusChange={handleStatusChange} onJumpToSection={label => { onJumpToSection(label); setSelectedNode(null); }} onFullPractice={label => { setExaminerConcept(label); setSelectedNode(null); }} />}
                {nodes.length > 0 && (
                    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', marginTop: 8 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>All Concepts</div>
                        {nodes.map(n => {
                            const c = SC[n.status] || SC.partial; return (
                                <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 7, marginBottom: 3, background: selectedNode?.id === n.id ? 'var(--surface2)' : 'transparent', border: selectedNode?.id === n.id ? '1px solid var(--border)' : '1px solid transparent', transition: 'all 0.1s' }}>
                                    <div style={{ width: 9, height: 9, borderRadius: '50%', background: c.fill, flexShrink: 0, boxShadow: `0 0 5px ${c.fill}88` }} />
                                    <div onClick={() => handleNodeClick(n)} style={{ flex: 1, fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}>{n.label}</div>
                                    <button
                                        onClick={e => { e.stopPropagation(); onJumpToSection(n.full_label || n.label); }}
                                        title="Jump to this concept in notes"
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: '2px 3px', borderRadius: 4, display: 'flex', alignItems: 'center', flexShrink: 0, opacity: 0.6, transition: 'opacity 0.15s' }}
                                        onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                                        onMouseLeave={e => e.currentTarget.style.opacity = '0.6'}
                                    ><ChevronRight size={13} /></button>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
            <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)' }}>
                <div style={{ display: 'flex', gap: 14, marginBottom: sc > 0 || pc > 0 ? 8 : 0 }}>
                    {[['mastered', '#10B981'], ['partial', '#F59E0B'], ['struggling', '#EF4444']].map(([k, c]) => (
                        <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text3)' }}><div style={{ width: 7, height: 7, borderRadius: '50%', background: c }} /> {k}</div>
                    ))}
                </div>
                {(sc > 0 || pc > 0) && (
                    <button onClick={() => setSniperOpen(true)} style={{ width: '100%', padding: '8px 0', borderRadius: 8, border: 'none', background: sc > 0 ? 'linear-gradient(90deg,#EF4444,#F59E0B)' : '#F59E0B', color: '#fff', fontSize: 11.5, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, boxShadow: '0 2px 8px rgba(239,68,68,0.25)', letterSpacing: 0.2 }}>
                        🎯 Sniper Test — {sc} red zone{sc !== 1 ? 's' : ''} targeted
                    </button>
                )}
            </div>
            {examinerConcept && <ExaminerModal concept={examinerConcept} notebookId={notebookId} onClose={() => setExaminerConcept(null)} />}
            {sniperOpen && <SniperExamModal nodes={nodes} notebookId={notebookId} onClose={() => setSniperOpen(false)} />}
        </div>
    );
}

// ─── Note Renderer ────────────────────────────────────────────────────────────
function NoteRenderer({ content, onDoubtLink }) {
    const mk = {
        h1({ children }) { return <div style={{ marginBottom: 28 }}><div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em', color: '#71717A', marginBottom: 6, fontFamily: '"DM Sans",sans-serif', fontWeight: 600 }}>AuraGraph · Study Notes</div><div style={{ fontSize: 22, fontWeight: 800, color: '#000', lineHeight: 1.25, fontFamily: '"Sora",sans-serif' }}>{children}</div></div>; },
        h2({ children }) { return <div style={{ marginTop: 36, marginBottom: 14 }}><div style={{ fontSize: 17, fontWeight: 700, color: '#000', lineHeight: 1.3, fontFamily: '"Sora",sans-serif' }}>{children}</div><div style={{ height: 1.5, background: '#E4E4E7', marginTop: 8 }} /></div>; },
        h3({ children }) { return <div style={{ marginTop: 20, marginBottom: 8 }}><span style={{ fontSize: 11, fontWeight: 600, color: '#71717A', textTransform: 'uppercase', letterSpacing: '0.09em', fontFamily: '"DM Sans",sans-serif' }}>{children}</span></div>; },
        code({ className, children }) {
            if (!className) return <code style={{ background: '#F4F4F5', color: '#18181B', borderRadius: 4, padding: '1px 6px', fontSize: 13, fontFamily: '"JetBrains Mono","Courier New",monospace', fontWeight: 500 }}>{children}</code>;
            return <pre style={{ background: '#F4F4F5', border: '1px solid #E4E4E7', borderRadius: 8, padding: '14px 18px', margin: '14px 0', fontFamily: '"JetBrains Mono","Courier New",monospace', fontSize: 13, lineHeight: 1.75, color: '#18181B', overflowX: 'auto', whiteSpace: 'pre-wrap' }}><code>{children}</code></pre>;
        },
        pre({ children }) { return <>{children}</>; },
        blockquote({ children }) {
            const extract = n => { if (!n) return ''; if (typeof n === 'string') return n; if (Array.isArray(n)) return n.map(extract).join(''); if (n?.props?.children) return extract(n.props.children); return ''; };
            const flat = extract(children);
            const isExamTip = flat.includes('Exam Tip');
            const isFormula = flat.includes('Formulas for this topic');
            const isIntuition = flat.includes('💡') || flat.includes('Intuition') || flat.includes('Think of it') || flat.includes('mutation');
            const isWarning = flat.includes('⚠️') || flat.includes('⚠') || flat.includes('offline mode') || flat.includes('Offline') || flat.includes('Unresolved Doubt');
            if (isExamTip) return <div style={{ background: '#F4F4F5', border: '1px solid #E4E4E7', borderLeft: '4px solid #000', borderRadius: 8, padding: '12px 16px', margin: '14px 0', display: 'flex', gap: 10, alignItems: 'flex-start' }}><span style={{ fontSize: 15, flexShrink: 0, marginTop: 1 }}>🎯</span><div style={{ fontSize: 13.5, color: '#18181B', lineHeight: 1.75, fontFamily: '"DM Sans",sans-serif' }}>{children}</div></div>;
            if (isFormula) return <div style={{ background: '#EFF6FF', border: '1px solid #BFDBFE', borderLeft: '4px solid #2563EB', borderRadius: 8, padding: '12px 16px', margin: '14px 0', display: 'flex', gap: 10, alignItems: 'flex-start' }}><span style={{ fontSize: 15, flexShrink: 0, marginTop: 1 }}>🔢</span><div style={{ fontSize: 13, color: '#1E3A8A', lineHeight: 1.75, fontFamily: '"DM Sans",sans-serif' }}>{children}</div></div>;
            if (isIntuition) return <div style={{ background: '#fff', border: '1px solid #E4E4E7', borderLeft: '4px solid #000', borderRadius: 8, padding: '12px 16px', margin: '14px 0', display: 'flex', gap: 10, alignItems: 'flex-start' }}><span style={{ fontSize: 15, flexShrink: 0, marginTop: 1 }}>✨</span><div style={{ fontSize: 13.5, color: '#18181B', lineHeight: 1.75, fontFamily: '"DM Sans",sans-serif' }}>{children}</div></div>;
            if (isWarning) return <div style={{ background: '#FFF7ED', border: '1px solid #FED7AA', borderLeft: '4px solid #F97316', borderRadius: 8, padding: '12px 16px', margin: '10px 0', fontSize: 13, color: '#7C2D12', lineHeight: 1.65, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>;
            return <div style={{ background: '#F4F4F5', border: '1px solid #E4E4E7', borderLeft: '4px solid #000', borderRadius: 8, padding: '12px 16px', margin: '12px 0', fontSize: 13.5, color: '#18181B', lineHeight: 1.7, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>;
        },
        strong({ children }) { return <strong style={{ fontWeight: 700, color: '#000' }}>{children}</strong>; },
        em({ children }) { return <span style={{ fontStyle: 'italic', color: '#3F3F46' }}>{children}</span>; },
        hr() { return <div style={{ border: 'none', borderTop: '1.5px solid #E4E4E7', margin: '28px 0' }} />; },
        p({ children }) { return <p style={{ marginBottom: 12, lineHeight: 1.9, color: '#18181B', fontFamily: '"Source Serif 4",Georgia,serif', fontSize: 16 }}>{children}</p>; },
        ul({ children }) { return <ul style={{ paddingLeft: 22, margin: '8px 0 14px', lineHeight: 1.9, fontFamily: '"Source Serif 4",Georgia,serif', fontSize: 16, color: '#18181B' }}>{children}</ul>; },
        ol({ children }) { return <ol style={{ paddingLeft: 22, margin: '8px 0 14px', lineHeight: 1.9, fontFamily: '"Source Serif 4",Georgia,serif', fontSize: 16, color: '#18181B' }}>{children}</ol>; },
        li({ children }) { return <li style={{ marginBottom: 5 }}>{children}</li>; },
        img({ src, alt }) {
            const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';
            const isApiImage = src && (src.startsWith('/api/images/') || src.startsWith('http'));
            const fullSrc = src && src.startsWith('/api/') ? `${API}${src}` : src;
            if (isApiImage) {
                return (
                    <figure style={{ margin: '20px 0', textAlign: 'center' }}>
                        <img
                            src={fullSrc}
                            alt={alt || 'Figure'}
                            style={{ maxWidth: '100%', maxHeight: 420, borderRadius: 8, border: '1px solid #E4E4E7', boxShadow: '0 2px 8px rgba(0,0,0,0.08)', display: 'inline-block' }}
                            onError={e => { e.currentTarget.style.display = 'none'; e.currentTarget.nextSibling.style.display = 'flex'; }}
                        />
                        <div style={{ display: 'none', alignItems: 'center', gap: 10, background: '#F4F4F5', border: '1px solid #E4E4E7', borderRadius: 8, padding: '12px 16px', margin: '14px 0', color: '#71717A', fontSize: 13, fontStyle: 'italic', fontFamily: '"DM Sans",sans-serif' }}>
                            <span style={{ fontSize: 18 }}>🖼</span>
                            <span>{alt ? `Figure: ${alt}` : 'Figure'}</span>
                        </div>
                        {alt && <figcaption style={{ fontSize: 12, color: '#71717A', marginTop: 6, fontFamily: '"DM Sans",sans-serif', fontStyle: 'italic' }}>{alt}</figcaption>}
                    </figure>
                );
            }
            // Non-served images (e.g. external URLs or data URIs) — plain render
            return (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#F4F4F5', border: '1px solid #E4E4E7', borderRadius: 8, padding: '12px 16px', margin: '14px 0', color: '#71717A', fontSize: 13, fontStyle: 'italic', fontFamily: '"DM Sans",sans-serif' }}>
                    <span style={{ fontSize: 18 }}>🖼</span>
                    <span>{alt ? `Figure: ${alt}` : 'Figure'}</span>
                </div>
            );
        },
        a({ href, children }) {
            if (href?.startsWith('#doubt-')) {
                const doubtId = href.slice(1);
                return (
                    <span
                        onClick={() => onDoubtLink?.(doubtId)}
                        style={{ color: '#7C3AED', cursor: 'pointer', textDecoration: 'underline', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 3 }}
                    >{children}</span>
                );
            }
            return <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: '#2563EB', textDecoration: 'underline' }}>{children}</a>;
        },
        table({ children }) {
            return (
                <div style={{ overflowX: 'auto', margin: '16px 0' }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 14, fontFamily: '"DM Sans",sans-serif' }}>{children}</table>
                </div>
            );
        },
        thead({ children }) { return <thead style={{ background: '#F4F4F5' }}>{children}</thead>; },
        tbody({ children }) { return <tbody>{children}</tbody>; },
        tr({ children }) { return <tr style={{ borderBottom: '1px solid #E4E4E7' }}>{children}</tr>; },
        th({ children }) { return <th style={{ padding: '8px 14px', textAlign: 'left', fontWeight: 700, color: '#18181B', borderBottom: '2px solid #D4D4D8', whiteSpace: 'nowrap' }}>{children}</th>; },
        td({ children }) { return <td style={{ padding: '7px 14px', color: '#3F3F46', verticalAlign: 'top', lineHeight: 1.6 }}>{children}</td>; },
    };
    return <div style={{ color: '#18181B' }}><ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]} components={mk}>{content || ''}</ReactMarkdown></div>;
}

// ─── Doubts Panel ─────────────────────────────────────────────────────────────
function DoubtsPanel({ doubts, currentPage }) {
    const [expanded, setExpanded] = useState({});
    const toggle = id => setExpanded(p => ({ ...p, [id]: !p[id] }));
    const pageDiagnostics = doubts.filter(d => d.pageIdx === currentPage);
    const otherPages = [...new Set(doubts.filter(d => d.pageIdx !== currentPage).map(d => d.pageIdx))];
    const IM = ({ text }) => (
        <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]} components={{ p: ({ children }) => <span style={{ display: 'block', marginBottom: 4 }}>{children}</span>, strong: ({ children }) => <strong style={{ color: '#5B21B6', fontWeight: 700 }}>{children}</strong>, em: ({ children }) => <em style={{ color: '#6D28D9' }}>{children}</em>, code: ({ children }) => <code style={{ background: '#EDE9FE', color: '#5B21B6', borderRadius: 3, padding: '1px 4px', fontSize: 11, fontFamily: 'monospace' }}>{children}</code>, a: ({ children }) => <span>{children}</span>, table: ({ children }) => <table style={{ borderCollapse: 'collapse', fontSize: 12, margin: '6px 0' }}>{children}</table>, th: ({ children }) => <th style={{ padding: '4px 10px', borderBottom: '1px solid #C4B5FD', textAlign: 'left', fontWeight: 700, color: '#5B21B6' }}>{children}</th>, td: ({ children }) => <td style={{ padding: '4px 10px', borderBottom: '1px solid #EDE9FE', color: '#3F3F46' }}>{children}</td> }}>{text || ''}</ReactMarkdown>
    );
    if (pageDiagnostics.length === 0) return (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 }}>
                <MessageCircle size={26} color="#C4B5FD" />
                <div style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', lineHeight: 1.7 }}>No doubts on <b>page {currentPage + 1}</b> yet.<br /><span style={{ fontSize: 11 }}>Click <b>Ask a Doubt</b> to add one.</span></div>
            </div>
            {otherPages.length > 0 && <div style={{ padding: '10px 14px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text3)', lineHeight: 1.6 }}>Doubts on page{otherPages.length > 1 ? 's' : ''} <span style={{ color: '#7C3AED', fontWeight: 600 }}>{otherPages.map(p => p + 1).join(', ')}</span></div>}
        </div>
    );
    return (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: '#7C3AED', background: '#EDE9FE', border: '1px solid #C4B5FD', borderRadius: 10, padding: '2px 8px' }}>Page {currentPage + 1}</span>
                <span style={{ fontSize: 11, color: 'var(--text3)' }}>{pageDiagnostics.length} doubt{pageDiagnostics.length > 1 ? 's' : ''}</span>
                {otherPages.length > 0 && <span style={{ fontSize: 10, color: '#9CA3AF', marginLeft: 'auto' }}>+{doubts.length - pageDiagnostics.length} on other pages</span>}
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 10px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                {pageDiagnostics.map(d => {
                    const isExp = !!expanded[d.id];
                    const pl = 380;
                    const needsExp = d.insight.length > pl;
                    const preview = needsExp && !isExp ? d.insight.slice(0, pl).replace(/\*\*[^*]*$/, '').replace(/\$[^$]*$/, '') + '…' : d.insight;
                    return (
                        <div key={d.id} id={'doubt-' + d.id}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6, marginBottom: 4 }}>
                                {d.success ? <span style={{ fontSize: 9, color: '#7C3AED', fontWeight: 700 }}>✨ mutated</span> : d.unresolved ? <span style={{ fontSize: 9, color: '#D97706', fontWeight: 600 }}>⏳ pending</span> : <span style={{ fontSize: 9, color: '#EF4444', fontWeight: 600 }}>⚠ failed</span>}
                                {d.success && d.source && <span style={{ fontSize: 8, fontWeight: 600, padding: '1px 5px', borderRadius: 6, background: d.source === 'azure' ? '#EFF6FF' : d.source === 'groq' ? '#ECFDF5' : '#F5F5F5', color: d.source === 'azure' ? '#1D4ED8' : d.source === 'groq' ? '#065F46' : '#52525B', border: `1px solid ${d.source === 'azure' ? '#BFDBFE' : d.source === 'groq' ? '#A7F3D0' : '#D4D4D8'}` }}>{d.source}</span>}
                                <span style={{ fontSize: 9, color: '#D1D5DB' }}>{d.time}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
                                <div style={{ maxWidth: '84%', background: '#7C3AED', color: '#fff', borderRadius: '14px 14px 3px 14px', padding: '9px 13px', fontSize: 12.5, lineHeight: 1.55 }}>{d.doubt}</div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                                {d.success ? (
                                    <div style={{ maxWidth: '90%', background: '#F5F3FF', border: '1px solid #DDD6FE', borderRadius: '3px 14px 14px 14px', padding: '9px 13px', fontSize: 12, lineHeight: 1.7, color: '#3B0764' }}>
                                        <div style={{ fontSize: 10, fontWeight: 700, color: '#7C3AED', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 4 }}><GitBranch size={10} /> AuraGraph</div>
                                        <div style={{ color: '#4C1D95' }}><IM text={preview} /></div>
                                        {d.gap && isExp && <div style={{ marginTop: 7, paddingTop: 7, borderTop: '1px solid #DDD6FE', fontSize: 11, color: '#7C3AED', fontStyle: 'italic' }}>🔍 {d.gap}</div>}
                                        {needsExp && <button onClick={() => toggle(d.id)} style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#7C3AED', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontWeight: 600 }}>{isExp ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> Read more</>}</button>}
                                    </div>
                                ) : (
                                    <div style={{ maxWidth: '90%', background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: '3px 14px 14px 14px', padding: '9px 13px', fontSize: 12, lineHeight: 1.7, color: '#991B1B' }}>
                                        <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 4 }}>{d.unresolved ? '⏳ Not yet resolved' : '⚠ Not delivered'}</div>
                                        <div style={{ color: d.unresolved ? '#92400E' : '#7F1D1D' }}>{d.unresolved ? (d.insight || 'AI unavailable — doubt saved. Retry when online.') : 'Backend was unreachable. Your doubt is saved — try re-submitting when the server is running.'}</div>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ─── Export buttons ───────────────────────────────────────────────────────────
function CopyNoteButton({ note }) {
    const [copied, setCopied] = useState(false);
    const copy = async () => { try { await navigator.clipboard.writeText(note); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { } };
    return <button className="btn btn-ghost btn-sm" onClick={copy} title="Copy full note as Markdown" style={{ fontSize: 12, gap: 5 }}>{copied ? <Check size={12} color="#10B981" /> : <Copy size={12} />}{copied ? 'Copied!' : 'Copy MD'}</button>;
}

function DownloadNoteButton({ note, name }) {
    const dl = () => { const b = new Blob([note], { type: 'text/markdown' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `${name || 'notes'}.md`; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(u); };
    return <button className="btn btn-ghost btn-sm" onClick={dl} title="Download as .md" style={{ fontSize: 12, gap: 5 }}><Download size={12} /> Export</button>;
}

// ─── Main Workspace ───────────────────────────────────────────────────────────
export default function NotebookWorkspace() {
    const { id } = useParams();
    const navigate = useNavigate();

    const [notebook, setNotebook] = useState(null);
    const [note, setNote] = useState('');
    const [prof, setProf] = useState('Practitioner');
    const [slidesFiles, setSlidesFiles] = useState([]);
    const [textbookFiles, setTextbookFiles] = useState([]);
    const [notesFiles, setNotesFiles] = useState([]); // handwritten / photographed notes
    const [fusing, setFusing] = useState(false);
    const [fuseProgress, setFuseProgress] = useState('');
    const [mutating, setMutating] = useState(false);
    const [currentPage, setCurrentPage] = useState(0);
    const [gapText, setGapText] = useState('');
    const [mutatedPages, setMutatedPages] = useState(new Set());
    const [doubtsLog, setDoubtsLog] = useState([]);
    const [rightTab, setRightTab] = useState('map');
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [sidebarWidth, setSidebarWidth] = useState(310);
    const [graphNodes, setGraphNodes] = useState([]);
    const [graphEdges, setGraphEdges] = useState([]);
    const [noteSource, setNoteSource] = useState('azure');      // 'azure' | 'local'
    const [fallbackWarning, setFallbackWarning] = useState(''); // non-empty = show banner
    const [viewMode, setViewMode] = useState('single');         // 'single' | 'two' | 'scroll'
    const [jumpHighlightSet, setJumpHighlightSet] = useState(new Set()); // page indices to pulse
    const [textSelection, setTextSelection] = useState(null);       // { text, x, y } | null
    const [pendingSelectionText, setPendingSelectionText] = useState(''); // pre-fills MutateModal
    const [showSearch, setShowSearch] = useState(false);       // note search overlay
    const [showShortcuts, setShowShortcuts] = useState(false); // keyboard shortcuts modal
    const [darkMode, setDarkMode] = useDarkMode();             // dark mode toggle
    const [editingPage, setEditingPage] = useState(false);     // page-jump input active
    const [pageInputVal, setPageInputVal] = useState('');      // page-jump input value
    const noteScrollRef = useRef();

    const startResizeSidebar = useCallback((e) => {
        e.preventDefault();
        const startX  = e.clientX;
        const startW  = sidebarWidth;
        const handle  = e.currentTarget;
        handle.classList.add('dragging');
        document.body.style.cursor     = 'col-resize';
        document.body.style.userSelect = 'none';
        const onMove = (ev) => {
            // dragging left (negative delta) → wider sidebar
            const delta = startX - ev.clientX;
            setSidebarWidth(Math.max(220, Math.min(640, startW + delta)));
        };
        const onUp = () => {
            handle.classList.remove('dragging');
            document.body.style.cursor     = '';
            document.body.style.userSelect = '';
            window.removeEventListener('mousemove', onMove);
            window.removeEventListener('mouseup',   onUp);
        };
        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup',   onUp);
    }, [sidebarWidth]);

    const pages = useMemo(() => {
        if (!note) return [];
        const byH2 = note.split(/(?=^## )/m).map(s => s.trim()).filter(Boolean);
        if (byH2.length > 0) {
            // Group sections together targeting ~3000 chars per page
            const TARGET = 3000;
            const merged = []; let buf = '';
            for (const s of byH2) {
                if (buf && buf.length + s.length + 2 > TARGET && buf.length > 200) {
                    merged.push(buf.trim());
                    buf = s;
                } else {
                    buf = buf ? buf + '\n\n' + s : s;
                }
            }
            if (buf) merged.push(buf.trim());
            return merged.filter(Boolean);
        }
        const byH3 = note.split(/(?=^### )/m).map(s => s.trim()).filter(Boolean);
        if (byH3.length > 1) return byH3;
        // Math-aware paragraph split — never cuts inside a $$ block
        const mathAwareSplit = (text) => {
            const segments = []; let inMath = false; let buf = [];
            for (const line of text.split('\n')) {
                if (line.trim() === '$$') inMath = !inMath;
                if (!inMath && line === '' && buf.length > 0) {
                    const seg = buf.join('\n').trim();
                    if (seg.length > 40) segments.push(seg);
                    buf = [];
                } else { buf.push(line); }
            }
            if (buf.length > 0) { const seg = buf.join('\n').trim(); if (seg.length > 40) segments.push(seg); }
            return segments;
        };
        const paras = mathAwareSplit(note);
        const chunks = []; let cur = '';
        for (const p of paras) {
            if (cur.length + p.length > 700 && cur.length > 150) { chunks.push(cur.trim()); cur = p; }
            else { cur += (cur ? '\n\n' : '') + p; }
        }
        if (cur) chunks.push(cur.trim());
        return chunks.length ? chunks : [note];
    }, [note]);

    // Scroll to top on page change
    useEffect(() => {
        noteScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    }, [currentPage]);

    // Keyboard navigation
    useEffect(() => {
        const h = (e) => {
            if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
            if (mutating) return;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); setCurrentPage(p => Math.min(pages.length - 1, p + 1)); }
            else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); setCurrentPage(p => Math.max(0, p - 1)); }
            else if (e.key === 'd' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setMutating(true); }
            else if (e.key === 'f' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setShowSearch(true); }
            else if (e.key === '?' || (e.key === '/' && e.shiftKey)) { setShowShortcuts(true); }
        };
        window.addEventListener('keydown', h);
        return () => window.removeEventListener('keydown', h);
    }, [pages.length, mutating]);

    // Load notebook + restore doubts
    useEffect(() => {
        setDoubtsLog(loadDoubts(id));
        fetch(`${API}/notebooks/${id}`, { headers: authHeaders() })
            .then(r => { if (!r.ok) throw new Error(); return r.json(); })
            .then(nb => { setNotebook(nb); setNote(nb.note || ''); setProf(nb.proficiency || 'Practitioner'); if (nb.graph?.nodes?.length) { setGraphNodes(nb.graph.nodes); setGraphEdges(nb.graph.edges || []); } })
            .catch(() => { const l = ls_getNotebook(id); if (l) { setNotebook(l); setNote(l.note || ''); setProf(l.proficiency || 'Practitioner'); if (l.graph?.nodes?.length) { setGraphNodes(l.graph.nodes); setGraphEdges(l.graph.edges || []); } } else { setNotebook({ id, name: 'Untitled', course: '' }); } });
    }, [id]);

    const saveNote = async (newNote, newProf) => {
        ls_saveNote(id, newNote, newProf);
        try { await fetch(`${API}/notebooks/${id}/note`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ note: newNote, proficiency: newProf }) }); } catch { }
    };

    const extractAndSaveGraph = async (text) => {
        // FIX: include authHeaders so the request is authenticated (backend requires Bearer token)
        try { const r = await fetch(`${API}/api/extract-concepts`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ note: text, notebook_id: id }) }); const g = await r.json(); if (g.nodes?.length) { setGraphNodes(g.nodes); setGraphEdges(g.edges || []); } } catch { }
    };

    const handleFuse = async () => {
        if (!slidesFiles.length && !notesFiles.length) return;
        setFusing(true); setFuseProgress('Uploading files…');
        setMutatedPages(new Set()); setGraphNodes([]); setGraphEdges([]);
        try {
            const form = new FormData();
            slidesFiles.forEach(f => form.append('slides_pdfs', f));
            // Handwritten notes images are OCR'd by the backend and merged with slide content
            notesFiles.forEach(f => form.append('slides_pdfs', f));
            textbookFiles.forEach(f => form.append('textbook_pdfs', f));
            form.append('proficiency', prof);
            if (id) form.append('notebook_id', id);
            setFuseProgress('Running Fusion Agent…');
            const res = await fetch(`${API}/api/upload-fuse-multi`, { method: 'POST', headers: authHeaders(), body: form });
            if (!res.ok) {
                let detail = `Server error (${res.status})`;
                try { const j = await res.json(); detail = j.detail || detail; } catch { }
                throw new Error(detail);
            }
            const data = await res.json();
            setNote(data.fused_note); setCurrentPage(0);
            setNoteSource(data.source || 'azure');
            setFallbackWarning(data.source === 'local'
                ? (data.fallback_reason
                    ? `⚠️ Azure OpenAI was unavailable — notes were generated using the offline summariser. (${data.fallback_reason})`
                    : '⚠️ Azure OpenAI is not configured — notes were generated using the offline summariser.')
                : ''
            );
            if (data.chunks_stored) {
                console.info(`📚 Knowledge store: ${data.chunks_stored.slides} slide chunks + ${data.chunks_stored.textbook} textbook chunks stored`);
            }
            await saveNote(data.fused_note, prof);
            setFuseProgress('Extracting concept map…');
            await extractAndSaveGraph(data.fused_note);
        } catch (err) {
            const isNetworkError = !err.message || err.message === 'Failed to fetch' || err.message.includes('NetworkError');
            const isFileTooLarge = err.message?.toLowerCase().includes('too large') || err.message?.toLowerCase().includes('exceeds') || err.message?.includes('413');
            const errMsg = isNetworkError
                ? `## ⚠️ Backend Not Running\n\nNotes could not be generated because the backend server is not reachable.\n\n**To fix this, start the backend:**\n\n\`\`\`bash\ncd backend\nsource venv/bin/activate\nuvicorn main:app --reload --port 8000\n\`\`\`\n\n> The local summarizer generates notes from your PDFs even without Azure OpenAI keys.`
                : isFileTooLarge
                    ? `## ⚠️ Upload Too Large\n\n**${err.message}**\n\n**What you can do:**\n- Split into two requests: upload half the slides + textbooks now, generate notes, then upload the remaining slides in a second notebook\n- Compress large PDFs (smallpdf.com or Adobe Acrobat → Reduce File Size)\n- For very large textbooks, upload only the relevant chapters`
                    : `## ⚠️ Generation Failed\n\n**Error:** ${err.message}\n\nPlease try again.`;
            setNote(errMsg); setCurrentPage(0); await saveNote(errMsg, prof);
        }
        setFusing(false); setFuseProgress('');
    };

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
                setNote(newNote); setGapText(data.concept_gap);
                setMutatedPages(prev => new Set([...prev, currentPage]));
                await saveNote(newNote, prof);
                extractAndSaveGraph(newNote).catch(() => { });
                // Use the full answer/explanation from the backend as insight shown in doubts sidebar.
                // Prefer data.answer (full explanation), fall back to concept_gap, then generic message.
                // Never extract a 2-word 💡 snippet — the student needs a real answer.
                const insight = data.answer || data.concept_gap || 'Your note was rewritten to address this doubt.';
                const entry = { id: lid, pageIdx: currentPage, doubt, insight, gap: data.concept_gap, source: data.source || 'azure', time: ts, success: true };
                setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
                setRightTab('doubts');
            }
        } catch {
            const entry = { id: lid, pageIdx: currentPage, doubt, insight: 'Could not reach backend. Your doubt has been recorded.', gap: 'Backend unreachable', time: ts, success: false };
            setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
            setRightTab('doubts');
        }
    }, [note, prof, id, currentPage, pages]);

    const handleNodeStatusChange = async (node, status) => {
        setGraphNodes(prev => prev.map(n => n.id === node.id ? { ...n, status } : n));
        try { await fetch(`${API}/notebooks/${id}/graph/update`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ concept_name: node.label, status }) }); } catch { }
    };

    const handleJumpToSection = useCallback((label) => {
        if (!label || !pages.length) return;

        const normalise = s => s.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
        const searchWords = normalise(label).split(' ').filter(w => w.length > 2);
        const ll = normalise(label);

        // 1. Exact substring match
        let idx = pages.findIndex(p => normalise(p).includes(ll));

        // 2. Strip ## prefix if present
        if (idx === -1 && ll.startsWith('##')) {
            idx = pages.findIndex(p => normalise(p).includes(ll.replace(/^#+\s*/, '')));
        }

        // 3. Word-overlap on heading area (first 200 chars)
        if (idx === -1 && searchWords.length > 0) {
            let bestScore = 0;
            pages.forEach((p, i) => {
                const headingArea = normalise(p.slice(0, 200));
                const score = searchWords.filter(w => headingArea.includes(w)).length;
                const fraction = score / searchWords.length;
                if (fraction > 0.5 && score > bestScore) { bestScore = score; idx = i; }
            });
        }

        // 4. Any significant word (>4 chars) in heading area
        if (idx === -1 && searchWords.length > 0) {
            const significant = searchWords.filter(w => w.length > 4);
            if (significant.length > 0)
                idx = pages.findIndex(p => significant.some(w => normalise(p.slice(0, 300)).includes(w)));
        }

        if (idx !== -1) {
            setCurrentPage(idx);
            setJumpHighlightSet(new Set([idx]));
            setTimeout(() => setJumpHighlightSet(new Set()), 1800);
        }
    }, [pages]);

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
                            <button data-testid="next-page" onClick={() => setCurrentPage(Math.min(pages.length - 1, currentPage + (viewMode === 'two' ? 2 : 1)))} disabled={currentPage >= pages.length - 1} title="Next (→)" style={{ background: 'none', border: 'none', color: currentPage >= pages.length - 1 ? 'var(--border2)' : 'var(--text2)', cursor: currentPage >= pages.length - 1 ? 'not-allowed' : 'pointer', padding: 0, display: 'flex' }}><ChevronRight size={14} /></button>
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
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                {!hasNote ? (
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
                        <div style={{ maxWidth: 760, width: '100%' }}>
                            <div style={{ textAlign: 'center', marginBottom: 36 }}>
                                <div style={{ display: 'inline-block', background: '#fff', borderRadius: 12, padding: '8px 18px', margin: '0 auto 14px', border: '1px solid var(--border)' }}><img src="/logo.jpeg" alt="AuraGraph" style={{ height: 44, width: 'auto', display: 'block' }} /></div>
                                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>Generate Fused Notes</h2>
                                <p style={{ fontSize: 14, color: 'var(--text3)', lineHeight: 1.7 }}>Upload your course materials and AuraGraph will generate a personalised digital study note calibrated to your level.</p>
                            </div>
                            <FuseProgressBar active={fusing} />
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
                    <div ref={noteScrollRef} onMouseUp={handleNoteMouseUp} style={{ flex: 1, overflowY: 'auto', background: '#F0F2F5', padding: viewMode === 'two' ? '28px 16px' : '28px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        {(() => {
                            const onDoubtLink = (doubtId) => { setRightTab('doubts'); setTimeout(() => { document.getElementById(doubtId)?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 150); };
                            const renderPage = (idx) => {
                                if (idx < 0 || idx >= pages.length) return <div key={`empty-${idx}`} style={{ flex: 1, minWidth: 0 }} />;
                                const isHighlighted = jumpHighlightSet.has(idx);
                                return (
                                    <div key={idx} className="note-page-card" style={{ display: 'flex', background: '#fff', borderRadius: 4, boxShadow: isHighlighted ? '0 0 0 3px #7C3AED, 0 2px 8px rgba(0,0,0,0.08), 0 12px 40px rgba(0,0,0,0.10)' : '0 2px 8px rgba(0,0,0,0.08), 0 12px 40px rgba(0,0,0,0.10)', border: isHighlighted ? '1px solid #7C3AED' : '1px solid #d0d0d0', overflow: 'hidden', flex: 1, minWidth: 0, transition: 'box-shadow 0.4s, border-color 0.4s' }}>
                                        <div style={{ width: 38, background: '#F8FAFC', borderRight: '2px solid #E5E7EB', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-evenly', padding: '32px 0', alignSelf: 'stretch', minHeight: 560 }}>
                                            {[0, 1, 2, 3, 4, 5].map(i => <div key={i} style={{ width: 16, height: 16, borderRadius: '50%', background: '#fff', border: '2px solid #CBD5E1', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.15)' }} />)}
                                        </div>
                                        <div style={{ width: 1.5, background: '#FCA5A5', flexShrink: 0 }} />
                                        <div style={{ flex: 1, padding: '40px 48px 48px 36px', minWidth: 0 }}>
                                            <div className="note-header-bar" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, paddingBottom: 10, borderBottom: '1px solid #E5E7EB' }}>
                                                <span style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Inter,sans-serif' }}>{notebook?.name || 'Study Notes'}</span>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                                    {mutatedPages.has(idx) && <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: '#EDE9FE', color: '#7C3AED', border: '1px solid #C4B5FD', letterSpacing: '0.05em' }}>✨ Mutated</span>}
                                                    <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>Page {idx + 1} of {pages.length}</span>
                                                </div>
                                            </div>
                                            <NoteRenderer content={pages[idx]} onDoubtLink={onDoubtLink} />
                                            <div className="note-footer-bar" style={{ marginTop: 32, paddingTop: 10, borderTop: '1px solid #E5E7EB', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
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
                                    {gapText && (
                                        <div style={{ marginBottom: 14, padding: '10px 14px', background: '#FEF3C7', border: '1px solid #FDE68A', borderRadius: 8, fontSize: 12, color: '#92400E', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                            <Brain size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                                            <div><b>Concept gap identified:</b> {gapText}</div>
                                            <button onClick={() => setGapText('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#92400E', padding: 0, marginLeft: 'auto' }}><X size={13} /></button>
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
                                                <button key={i} className="page-dot" data-label={`Page ${i + 1}`} onClick={() => setCurrentPage(i)} title={`Page ${i + 1}`} style={{ width: i === currentPage ? 20 : 6, height: 6, borderRadius: 3, border: 'none', cursor: 'pointer', background: i === currentPage ? '#7C3AED' : mutatedPages.has(i) ? '#C4B5FD' : 'var(--border2)', transition: 'all 0.2s', padding: 0 }} />
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
                            if (viewMode === 'two') return (
                                <div style={{ maxWidth: 1480, width: '100%' }}>
                                    {banners}
                                    <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                                        {renderPage(currentPage)}
                                        {renderPage(currentPage + 1)}
                                    </div>
                                    {bottomBar}
                                </div>
                            );
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
                        {[{ key: 'map', label: 'Concept Map', icon: <Brain size={12} /> }, { key: 'doubts', label: (() => { const onPage = doubtsLog.filter(d => d.pageIdx === currentPage).length; const total = doubtsLog.length; if (!total) return 'Doubts'; if (onPage) return `Doubts (${onPage}/${total})`; return `Doubts (${total})`; })(), icon: <MessageCircle size={12} /> }].map(tab => (
                            <button key={tab.key} data-testid={`tab-${tab.key}`} onClick={() => setRightTab(tab.key)} style={{ flex: 1, padding: '10px 6px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none', transition: 'all 0.15s', borderBottom: rightTab === tab.key ? '2px solid #7C3AED' : '2px solid transparent', background: 'transparent', color: rightTab === tab.key ? '#7C3AED' : 'var(--text3)' }}>
                                {tab.icon} {tab.label}
                            </button>
                        ))}
                    </div>
                    {rightTab === 'map'
                        ? <KnowledgePanel nodes={graphNodes} edges={graphEdges} notebookId={id} onNodeStatusChange={handleNodeStatusChange} onJumpToSection={handleJumpToSection} />
                        : <DoubtsPanel doubts={doubtsLog} currentPage={currentPage} />}
                </aside>
            </div>

            {textSelection && (
                <div style={{ position: 'fixed', left: textSelection.x, top: textSelection.y - 8, transform: 'translateX(-50%) translateY(-100%)', zIndex: 9999, background: '#1E1B4B', borderRadius: 8, padding: '6px 10px', display: 'flex', gap: 6, boxShadow: '0 4px 24px rgba(0,0,0,0.35)', alignItems: 'center', pointerEvents: 'auto' }}>
                    <MessageCircle size={11} color="#C4B5FD" />
                    <span style={{ color: '#C4B5FD', fontSize: 10, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{textSelection.text.length > 45 ? textSelection.text.slice(0, 45) + '…' : textSelection.text}</span>
                    <button onClick={() => { setPendingSelectionText(textSelection.text); setTextSelection(null); setMutating(true); }} style={{ background: '#7C3AED', border: 'none', color: '#fff', borderRadius: 6, padding: '4px 10px', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>Ask about this</button>
                    <button onClick={() => setTextSelection(null)} style={{ background: 'none', border: '1px solid #4C1D95', color: '#A78BFA', borderRadius: 5, padding: '3px 7px', fontSize: 11, cursor: 'pointer' }}>&#x2715;</button>
                </div>
            )}
            {mutating && pages.length > 0 && <MutateModal page={pages[currentPage]} notebookId={id} pageIdx={currentPage} onClose={() => { setMutating(false); setPendingSelectionText(''); }} onMutate={handleMutate} onDoubtAnswered={({ doubt: q, answer: a, source: s }) => { const entry = { id: Date.now(), pageIdx: currentPage, doubt: q, insight: a, gap: '', source: s || 'azure', time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }), success: true }; setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; }); setRightTab('doubts'); }} initialDoubt={pendingSelectionText} />}
            {showSearch && pages.length > 0 && <NoteSearch pages={pages} onJumpToPage={(idx) => { setCurrentPage(idx); }} onClose={() => setShowSearch(false)} />}
            {showShortcuts && <ShortcutsModal onClose={() => setShowShortcuts(false)} />}
        </div>
    );
}
