import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ls_getNotebook, ls_saveNote } from '../localNotebooks';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {
    Sparkles, Loader2, ChevronLeft, ChevronRight, Upload, FileText,
    BookOpen, MessageSquare, ArrowLeft, Zap, Brain, CheckCircle2,
    AlertCircle, MinusCircle, RefreshCw, X, ChevronDown, ChevronUp,
    MessageCircle, GitBranch, Copy, Check, PanelRightClose, PanelRightOpen,
    Download
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
    { label: 'Uploading PDFs', icon: '📤' },
    { label: 'Extracting slides text', icon: '📄' },
    { label: 'Extracting textbook content', icon: '📚' },
    { label: 'Running Fusion Agent', icon: '🧠' },
    { label: 'Calibrating to your level', icon: '🎯' },
    { label: 'Building concept map', icon: '🕸️' },
    { label: 'Finalising notes', icon: '✨' },
];

function FuseProgressBar({ active }) {
    const [step, setStep] = useState(0);
    const [dots, setDots] = useState('');
    useEffect(() => {
        if (!active) { setStep(0); setDots(''); return; }
        const st = setInterval(() => setStep(s => Math.min(s + 1, FUSE_STEPS.length - 1)), 3500);
        const dt = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 400);
        return () => { clearInterval(st); clearInterval(dt); };
    }, [active]);
    if (!active) return null;
    return (
        <div style={{ marginBottom: 20, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: 22 }}>{FUSE_STEPS[step].icon}</span>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{FUSE_STEPS[step].label}{dots}</div>
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 2 }}>Step {step + 1} of {FUSE_STEPS.length} — this usually takes 15–30 seconds</div>
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
function FileDrop({ label, icon, files, onFiles }) {
    const ref = useRef();
    const [drag, setDrag] = useState(false);
    const addFiles = (incoming) => {
        const valid = Array.from(incoming).filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
        if (valid.length) onFiles(prev => [...prev, ...valid]);
    };
    const DropIcon = icon || BookOpen;
    const hasFiles = files.length > 0;
    const totalMB = (files.reduce((s, f) => s + f.size, 0) / 1024 / 1024).toFixed(1);
    return (
        <div data-testid={`file-drop-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')}`}
            onDragOver={e => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
            style={{ border: `2px dashed ${drag ? 'var(--text)' : hasFiles ? '#10B981' : 'var(--border2)'}`, borderRadius: 12, padding: 16, background: drag ? 'var(--surface2)' : hasFiles ? '#F0FDF4' : 'var(--surface)', transition: 'all 0.15s', minHeight: 120 }}>
            <input ref={ref} type="file" accept=".pdf" multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
            {!hasFiles ? (
                <div onClick={() => ref.current.click()} style={{ textAlign: 'center', cursor: 'pointer', padding: '12px 0' }}>
                    <DropIcon size={26} color="var(--text3)" style={{ margin: '0 auto 8px', display: 'block' }} />
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text2)' }}>{label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>Drag & drop or click to browse</div>
                </div>
            ) : (
                <>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
                        {files.map((f, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', borderRadius: 6, padding: '6px 10px', border: '1px solid #d1fae5' }}>
                                <FileText size={14} color="#10B981" style={{ flexShrink: 0 }} />
                                <span style={{ fontSize: 12, color: '#065f46', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                                <span style={{ fontSize: 10, color: 'var(--text3)' }}>{(f.size/1024/1024).toFixed(1)}MB</span>
                                <button onClick={e => { e.stopPropagation(); onFiles(prev => prev.filter((_,j) => j !== i)); }} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text3)', display: 'flex' }}><X size={12} /></button>
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

// ─── Mutation Modal ───────────────────────────────────────────────────────────
function MutateModal({ page, onClose, onMutate }) {
    const [doubt, setDoubt] = useState('');
    const [busy, setBusy] = useState(false);
    const go = async () => {
        if (!doubt.trim()) return;
        setBusy(true);
        await onMutate(page, doubt);
        setBusy(false);
        onClose();
    };
    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in" onClick={e => e.stopPropagation()}>
                <h3 style={{ marginBottom: 4 }}>Ask a Doubt</h3>
                <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 16, lineHeight: 1.6 }}>
                    Describe what's confusing. AuraGraph will permanently rewrite this page to resolve it.
                </p>
                <div style={{ background: 'var(--surface)', borderRadius: 8, padding: 12, fontSize: 12, color: 'var(--text2)', lineHeight: 1.7, marginBottom: 14, maxHeight: 80, overflow: 'hidden', border: '1px solid var(--border)' }}>
                    {page ? (page.length > 200 ? page.slice(0, page.lastIndexOf(' ', 200)) + '…' : page) : ''}
                </div>
                <textarea className="input" rows={4} autoFocus value={doubt}
                    onChange={e => setDoubt(e.target.value)}
                    onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') go(); if (e.key === 'Escape') onClose(); }}
                    placeholder="e.g. Why does convolution in time domain become multiplication in frequency domain?"
                    style={{ resize: 'vertical', fontFamily: 'inherit', marginBottom: 8 }}
                />
                <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 14 }}>
                    <kbd style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 5px', fontSize: 10 }}>Ctrl+Enter</kbd> to submit
                </div>
                <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
                    <button className="btn btn-primary btn-sm" onClick={go} disabled={busy || !doubt.trim()} style={{ gap: 6 }}>
                        {busy ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}
                        {busy ? 'Mutating…' : 'Mutate This Page'}
                    </button>
                </div>
            </div>
        </div>
    );
}

// ─── Examiner Modal ───────────────────────────────────────────────────────────
function ExaminerModal({ concept, onClose }) {
    const [questions, setQuestions] = useState('');
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        (async () => {
            try {
                const res = await fetch(`${API}/api/examine`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ concept_name: concept }) });
                const data = await res.json();
                setQuestions(data.practice_questions);
            } catch { setQuestions(`## Practice Questions: ${concept}\n\nBackend not reachable.`); }
            finally { setLoading(false); }
        })();
    }, [concept]);
    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in" onClick={e => e.stopPropagation()} style={{ width: 600, maxWidth: '96vw', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div><h3 style={{ marginBottom: 2 }}>Practice Questions</h3><p style={{ fontSize: 12, color: 'var(--text3)' }}>Generated for: <b>{concept}</b></p></div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={18} /></button>
                </div>
                <div style={{ flex: 1, overflowY: 'auto', background: 'var(--surface)', borderRadius: 10, padding: 16, border: '1px solid var(--border)' }}>
                    {loading ? <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text3)', fontSize: 13 }}><Loader2 className="spin" size={16} /> Generating questions…</div>
                        : <div style={{ fontSize: 13, lineHeight: 1.8 }}><ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{questions}</ReactMarkdown></div>}
                </div>
                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}><button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button></div>
            </div>
        </div>
    );
}

// ─── Knowledge Graph ──────────────────────────────────────────────────────────
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
            <defs>{nodes.map(n => { const c = SC[n.status] || SC.partial; return (<radialGradient key={n.id} id={`g-${n.id}`} cx="50%" cy="50%" r="50%"><stop offset="0%" stopColor={c.ring} stopOpacity="0.6"/><stop offset="100%" stopColor={c.fill} stopOpacity="1"/></radialGradient>); })}</defs>
            {edges.map((e, i) => { const s = nodeById[e[0]], d = nodeById[e[1]]; if (!s || !d) return null; const sp = getPos(s), dp = getPos(d); return <line key={i} x1={sp.cx} y1={sp.cy} x2={dp.cx} y2={dp.cy} stroke="var(--border2)" strokeWidth={1.5} strokeDasharray="4,3" opacity={0.7} />; })}
            {nodes.map(n => { const c = SC[n.status] || SC.partial; const { cx, cy } = getPos(n); const sel = n.id === selectedNodeId; const lbl = n.label.length > 16 ? n.label.slice(0, 14) + '…' : n.label; return (
                <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => onNodeClick(n)}>
                    {sel && <circle cx={cx} cy={cy} r={20} fill="none" stroke={c.fill} strokeWidth={2} opacity={0.5} strokeDasharray="3,2" />}
                    <circle cx={cx} cy={cy} r={17} fill={c.ring} opacity={sel ? 0.4 : 0.2} />
                    <circle cx={cx} cy={cy} r={12} fill={`url(#g-${n.id})`} stroke={sel ? c.fill : 'transparent'} strokeWidth={2} />
                    <text x={cx} y={cy + 24} textAnchor="middle" fontSize={9} fill="var(--text2)" fontWeight={sel ? 700 : 500} style={{ pointerEvents: 'none', userSelect: 'none' }}>{lbl}</text>
                </g>
            ); })}
        </svg>
    );
}

// ─── Node Popover ─────────────────────────────────────────────────────────────
function NodePopover({ node, onClose, onExamine, onStatusChange, onJumpToSection }) {
    const opts = ['mastered', 'partial', 'struggling'];
    const icons = { mastered: <CheckCircle2 size={13}/>, partial: <MinusCircle size={13}/>, struggling: <AlertCircle size={13}/> };
    const colors = { mastered: '#10B981', partial: '#F59E0B', struggling: '#EF4444' };
    return (
        <div style={{ background: 'var(--bg)', borderRadius: 12, border: '1px solid var(--border)', boxShadow: 'var(--shadow-md)', padding: '14px 16px', margin: '0 12px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>{node.label}</div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: 0 }}><X size={14} /></button>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 8 }}>Set mastery level:</div>
            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                {opts.map(s => (
                    <button key={s} onClick={() => onStatusChange(node, s)} style={{ flex: 1, padding: '6px 4px', borderRadius: 7, border: `1px solid ${node.status === s ? colors[s] : 'var(--border)'}`, background: node.status === s ? colors[s] + '22' : 'transparent', color: node.status === s ? colors[s] : 'var(--text3)', fontSize: 10, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4 }}>
                        {icons[s]} {s}
                    </button>
                ))}
            </div>
            <button onClick={() => onJumpToSection(node.label)} style={{ width: '100%', padding: 7, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text2)', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginBottom: 8 }}>
                <ChevronRight size={11} /> Jump to this section in notes
            </button>
            <button onClick={() => onExamine(node.label)} style={{ width: '100%', padding: 8, borderRadius: 8, border: 'none', background: node.status === 'struggling' ? '#EF4444' : 'var(--text)', color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <Brain size={13} /> Generate Practice Questions
            </button>
        </div>
    );
}

// ─── Knowledge Panel ──────────────────────────────────────────────────────────
function KnowledgePanel({ nodes, edges, notebookId, onNodeStatusChange, onJumpToSection }) {
    const [selectedNode, setSelectedNode] = useState(null);
    const [examinerConcept, setExaminerConcept] = useState(null);
    const handleNodeClick = n => setSelectedNode(p => p?.id === n.id ? null : n);
    const handleStatusChange = (node, status) => { onNodeStatusChange(node, status); setSelectedNode(p => p?.id === node.id ? { ...p, status } : p); };
    const mc = nodes.filter(n => n.status === 'mastered').length;
    const pc = nodes.filter(n => n.status === 'partial').length;
    const sc = nodes.filter(n => n.status === 'struggling').length;
    return (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8 }}>Cognitive Knowledge Map</div>
                {nodes.length > 0 && (
                    <div style={{ display: 'flex', gap: 6 }}>
                        {[['mastered','#10B981',mc],['partial','#F59E0B',pc],['struggling','#EF4444',sc]].map(([k,c,count]) => (
                            <div key={k} style={{ flex: 1, textAlign: 'center', background: c+'15', borderRadius: 6, padding: 4, border: `1px solid ${c}33` }}>
                                <div style={{ fontSize: 16, fontWeight: 800, color: c }}>{count}</div>
                                <div style={{ fontSize: 9, color: c, textTransform: 'uppercase', fontWeight: 600 }}>{k}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0 0' }}>
                <KnowledgeGraph nodes={nodes} edges={edges} onNodeClick={handleNodeClick} selectedNodeId={selectedNode?.id} />
                {selectedNode && <NodePopover node={selectedNode} onClose={() => setSelectedNode(null)} onExamine={label => { setExaminerConcept(label); setSelectedNode(null); }} onStatusChange={handleStatusChange} onJumpToSection={label => { onJumpToSection(label); setSelectedNode(null); }} />}
                {nodes.length > 0 && (
                    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', marginTop: 8 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>All Concepts</div>
                        {nodes.map(n => { const c = SC[n.status] || SC.partial; return (
                            <div key={n.id} onClick={() => handleNodeClick(n)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 7, marginBottom: 3, background: selectedNode?.id === n.id ? 'var(--surface2)' : 'transparent', cursor: 'pointer', border: selectedNode?.id === n.id ? '1px solid var(--border)' : '1px solid transparent', transition: 'all 0.1s' }}>
                                <div style={{ width: 9, height: 9, borderRadius: '50%', background: c.fill, flexShrink: 0, boxShadow: `0 0 5px ${c.fill}88` }} />
                                <div style={{ flex: 1, fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.label}</div>
                                <div style={{ fontSize: 10, color: c.fill, textTransform: 'capitalize', fontWeight: 600 }}>{n.status}</div>
                            </div>
                        ); })}
                    </div>
                )}
            </div>
            <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 14 }}>
                {[['mastered','#10B981'],['partial','#F59E0B'],['struggling','#EF4444']].map(([k,c]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text3)' }}><div style={{ width: 7, height: 7, borderRadius: '50%', background: c }} /> {k}</div>
                ))}
            </div>
            {examinerConcept && <ExaminerModal concept={examinerConcept} onClose={() => setExaminerConcept(null)} />}
        </div>
    );
}

// ─── Note Renderer ────────────────────────────────────────────────────────────
function NoteRenderer({ content }) {
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
            const isWarning = flat.includes('⚠️') || flat.includes('offline mode') || flat.includes('Offline');
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
    };
    return <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]} components={mk}>{content || ''}</ReactMarkdown>;
}

// ─── Doubts Panel ─────────────────────────────────────────────────────────────
function DoubtsPanel({ doubts, currentPage }) {
    const [expanded, setExpanded] = useState({});
    const toggle = id => setExpanded(p => ({ ...p, [id]: !p[id] }));
    const pageDiagnostics = doubts.filter(d => d.pageIdx === currentPage);
    const otherPages = [...new Set(doubts.filter(d => d.pageIdx !== currentPage).map(d => d.pageIdx))];
    const IM = ({ text }) => (
        <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]} components={{ p: ({ children }) => <span style={{ display: 'block', marginBottom: 4 }}>{children}</span>, strong: ({ children }) => <strong style={{ color: '#5B21B6', fontWeight: 700 }}>{children}</strong>, em: ({ children }) => <em style={{ color: '#6D28D9' }}>{children}</em>, code: ({ children }) => <code style={{ background: '#EDE9FE', color: '#5B21B6', borderRadius: 3, padding: '1px 4px', fontSize: 11, fontFamily: 'monospace' }}>{children}</code>, a: ({ children }) => <span>{children}</span> }}>{text || ''}</ReactMarkdown>
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
                    const pl = 130;
                    const needsExp = d.insight.length > pl;
                    const preview = needsExp && !isExp ? d.insight.slice(0, pl).replace(/\*\*[^*]*$/, '').replace(/\$[^$]*$/, '') + '…' : d.insight;
                    return (
                        <div key={d.id}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6, marginBottom: 4 }}>
                                {d.success ? <span style={{ fontSize: 9, color: '#7C3AED', fontWeight: 700 }}>✨ mutated</span> : <span style={{ fontSize: 9, color: '#EF4444', fontWeight: 600 }}>⚠ failed</span>}
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
                                        {needsExp && <button onClick={() => toggle(d.id)} style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#7C3AED', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontWeight: 600 }}>{isExp ? <><ChevronUp size={11}/> Show less</> : <><ChevronDown size={11}/> Read more</>}</button>}
                                    </div>
                                ) : (
                                    <div style={{ maxWidth: '90%', background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: '3px 14px 14px 14px', padding: '9px 13px', fontSize: 12, lineHeight: 1.7, color: '#991B1B' }}>
                                        <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 4 }}>⚠ Not delivered</div>
                                        <div style={{ color: '#7F1D1D' }}>Backend was unreachable. Your doubt is saved — try re-submitting when the server is running.</div>
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
    const copy = async () => { try { await navigator.clipboard.writeText(note); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch {} };
    return <button className="btn btn-ghost btn-sm" onClick={copy} title="Copy full note as Markdown" style={{ fontSize: 12, gap: 5 }}>{copied ? <Check size={12} color="#10B981"/> : <Copy size={12}/>}{copied ? 'Copied!' : 'Copy MD'}</button>;
}

function DownloadNoteButton({ note, name }) {
    const dl = () => { const b = new Blob([note], { type: 'text/markdown' }); const u = URL.createObjectURL(b); const a = document.createElement('a'); a.href = u; a.download = `${name||'notes'}.md`; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(u); };
    return <button className="btn btn-ghost btn-sm" onClick={dl} title="Download as .md" style={{ fontSize: 12, gap: 5 }}><Download size={12}/> Export</button>;
}

// ─── Main Workspace ───────────────────────────────────────────────────────────
export default function NotebookWorkspace() {
    const { id } = useParams();
    const navigate = useNavigate();

    const [notebook, setNotebook] = useState(null);
    const [note, setNote] = useState('');
    const [prof, setProf] = useState('Intermediate');
    const [slidesFiles, setSlidesFiles] = useState([]);
    const [textbookFiles, setTextbookFiles] = useState([]);
    const [fusing, setFusing] = useState(false);
    const [fuseProgress, setFuseProgress] = useState('');
    const [mutating, setMutating] = useState(false);
    const [currentPage, setCurrentPage] = useState(0);
    const [gapText, setGapText] = useState('');
    const [mutatedPages, setMutatedPages] = useState(new Set());
    const [doubtsLog, setDoubtsLog] = useState([]);
    const [rightTab, setRightTab] = useState('map');
    const [sidebarOpen, setSidebarOpen] = useState(true);
    const [graphNodes, setGraphNodes] = useState([]);
    const [graphEdges, setGraphEdges] = useState([]);
    const noteScrollRef = useRef();

    const pages = useMemo(() => {
        if (!note) return [];
        const byH2 = note.split(/(?=^## )/m).map(s => s.trim()).filter(Boolean);
        if (byH2.length > 0) {
            // Group sections together targeting ~2200 chars per page
            const TARGET = 2200;
            const merged = []; let buf = '';
            for (const s of byH2) {
                if (buf && buf.length + s.length + 2 > TARGET && buf.length > 500) {
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
            if (['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
            if (mutating) return;
            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); setCurrentPage(p => Math.min(pages.length - 1, p + 1)); }
            else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); setCurrentPage(p => Math.max(0, p - 1)); }
            else if (e.key === 'd' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); setMutating(true); }
        };
        window.addEventListener('keydown', h);
        return () => window.removeEventListener('keydown', h);
    }, [pages.length, mutating]);

    // Load notebook + restore doubts
    useEffect(() => {
        setDoubtsLog(loadDoubts(id));
        fetch(`${API}/notebooks/${id}`, { headers: authHeaders() })
            .then(r => { if (!r.ok) throw new Error(); return r.json(); })
            .then(nb => { setNotebook(nb); setNote(nb.note || ''); setProf(nb.proficiency || 'Intermediate'); if (nb.graph?.nodes?.length) { setGraphNodes(nb.graph.nodes); setGraphEdges(nb.graph.edges || []); } })
            .catch(() => { const l = ls_getNotebook(id); if (l) { setNotebook(l); setNote(l.note || ''); setProf(l.proficiency || 'Intermediate'); if (l.graph?.nodes?.length) { setGraphNodes(l.graph.nodes); setGraphEdges(l.graph.edges || []); } } else { setNotebook({ id, name: 'Untitled', course: '' }); } });
    }, [id]);

    const saveNote = async (newNote, newProf) => {
        ls_saveNote(id, newNote, newProf);
        try { await fetch(`${API}/notebooks/${id}/note`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ note: newNote, proficiency: newProf }) }); } catch {}
    };

    const extractAndSaveGraph = async (text) => {
        try { const r = await fetch(`${API}/api/extract-concepts`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: text, notebook_id: id }) }); const g = await r.json(); if (g.nodes?.length) { setGraphNodes(g.nodes); setGraphEdges(g.edges || []); } } catch {}
    };

    const handleFuse = async () => {
        if (!slidesFiles.length || !textbookFiles.length) return;
        setFusing(true); setFuseProgress('Uploading PDFs…');
        setMutatedPages(new Set()); setGraphNodes([]); setGraphEdges([]);
        try {
            const form = new FormData();
            slidesFiles.forEach(f => form.append('slides_pdfs', f));
            textbookFiles.forEach(f => form.append('textbook_pdfs', f));
            form.append('proficiency', prof);
            setFuseProgress('Running Fusion Agent…');
            const res = await fetch(`${API}/api/upload-fuse-multi`, { method: 'POST', headers: authHeaders(), body: form });
            if (!res.ok) {
                let detail = `Server error (${res.status})`;
                try { const j = await res.json(); detail = j.detail || detail; } catch {}
                throw new Error(detail);
            }
            const data = await res.json();
            setNote(data.fused_note); setCurrentPage(0);
            await saveNote(data.fused_note, prof);
            setFuseProgress('Extracting concept map…');
            await extractAndSaveGraph(data.fused_note);
        } catch (err) {
            const isNetworkError = !err.message || err.message === 'Failed to fetch' || err.message.includes('NetworkError');
            const errMsg = isNetworkError
                ? `## ⚠️ Backend Not Running\n\nNotes could not be generated because the backend server is not reachable.\n\n**To fix this, start the backend:**\n\n\`\`\`bash\ncd backend\nsource venv/bin/activate\nuvicorn main:app --reload --port 8000\n\`\`\`\n\n> The local summarizer generates notes from your PDFs even without Azure OpenAI keys.`
                : `## ⚠️ Generation Failed\n\n**Error:** ${err.message}\n\nPlease check the backend logs and try again.`;
            setNote(errMsg); setCurrentPage(0); await saveNote(errMsg, prof);
        }
        setFusing(false); setFuseProgress('');
    };

    const handleMutate = useCallback(async (page, doubt) => {
        const ts = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const lid = Date.now();
        try {
            const res = await fetch(`${API}/api/mutate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_paragraph: page, student_doubt: doubt }) });
            const data = await res.json();

            // ── Safe splice: replace the current page text in the full note ──────
            // Strategy: find the verbatim page text inside the full note and replace it.
            // This works regardless of how pages were split (H2/H3/paragraph chunks),
            // and avoids the destructive idx=-1 fallback that wiped the entire note.
            const pageText = pages[currentPage];
            // Find the page's leading heading (if any) to anchor the search position,
            // then do a trimmed substring replacement.
            const trimmedPage = pageText.trim();
            const noteIdx = note.indexOf(trimmedPage);
            let newNote;
            if (noteIdx !== -1) {
                // Replace exactly this page's content in the note
                newNote = note.slice(0, noteIdx) + data.mutated_paragraph + note.slice(noteIdx + trimmedPage.length);
            } else {
                // Fallback: page content not found verbatim (can happen if note was
                // modified between page split and mutation). Append as a note amendment.
                newNote = note + '\n\n---\n\n**Amendment (page ' + (currentPage + 1) + '):**\n\n' + data.mutated_paragraph;
            }

            setNote(newNote); setGapText(data.concept_gap);
            setMutatedPages(prev => new Set([...prev, currentPage]));
            await saveNote(newNote, prof);
            // Use .then() to avoid setState-after-unmount; don't block UI on this
            extractAndSaveGraph(newNote).catch(() => {});

            const pl = data.mutated_paragraph.split('\n');
            const bqs = pl.findIndex(l => l.includes('💡') || l.trimStart().startsWith('> '));
            let insight = data.concept_gap || 'Page updated.';
            if (bqs !== -1) { const bl = []; for (let i = bqs; i < pl.length; i++) { if (pl[i].startsWith('> ') || pl[i] === '>') bl.push(pl[i].replace(/^>\s?/, '')); else if (bl.length > 0) break; } if (bl.length) insight = bl.join(' ').trim(); }
            const entry = { id: lid, pageIdx: currentPage, doubt, insight, gap: data.concept_gap, time: ts, success: true };
            setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
            setRightTab('doubts');
        } catch {
            const entry = { id: lid, pageIdx: currentPage, doubt, insight: 'Could not reach backend. Your doubt has been recorded.', gap: 'Backend unreachable', time: ts, success: false };
            setDoubtsLog(prev => { const u = [entry, ...prev]; saveDoubts(id, u); return u; });
            setRightTab('doubts');
        }
    }, [note, prof, id, currentPage, pages]);

    const handleNodeStatusChange = async (node, status) => {
        setGraphNodes(prev => prev.map(n => n.id === node.id ? { ...n, status } : n));
        try { await fetch(`${API}/notebooks/${id}/graph/update`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ concept_name: node.label, status }) }); } catch {}
    };

    const handleJumpToSection = useCallback((label) => {
        const ll = label.toLowerCase();
        const idx = pages.findIndex(p => p.toLowerCase().includes(ll));
        if (idx !== -1) setCurrentPage(idx);
    }, [pages]);

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
                            {['Beginner','Intermediate','Advanced'].map(p => (
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
                            <button data-testid="prev-page" onClick={() => setCurrentPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0} title="Previous (←)" style={{ background: 'none', border: 'none', color: currentPage === 0 ? 'var(--border2)' : 'var(--text2)', cursor: currentPage === 0 ? 'not-allowed' : 'pointer', padding: 0, display: 'flex' }}><ChevronLeft size={14} /></button>
                            <span style={{ fontSize: 12, color: 'var(--text2)', minWidth: 48, textAlign: 'center' }}>{currentPage + 1} / {pages.length}</span>
                            <button data-testid="next-page" onClick={() => setCurrentPage(Math.min(pages.length - 1, currentPage + 1))} disabled={currentPage >= pages.length - 1} title="Next (→)" style={{ background: 'none', border: 'none', color: currentPage >= pages.length - 1 ? 'var(--border2)' : 'var(--text2)', cursor: currentPage >= pages.length - 1 ? 'not-allowed' : 'pointer', padding: 0, display: 'flex' }}><ChevronRight size={14} /></button>
                        </div>
                        <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                        {/* Export (compact) */}
                        <CopyNoteButton note={note} />
                        <DownloadNoteButton note={note} name={notebook.name} />
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
                        <div style={{ maxWidth: 620, width: '100%' }}>
                            <div style={{ textAlign: 'center', marginBottom: 36 }}>
                                <div style={{ width: 52, height: 52, borderRadius: 14, background: 'var(--text)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 14px' }}><Zap size={24} color="white" /></div>
                                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>Generate Fused Notes</h2>
                                <p style={{ fontSize: 14, color: 'var(--text3)', lineHeight: 1.7 }}>Upload your course materials and AuraGraph will generate a personalised digital study note calibrated to your level.</p>
                            </div>
                            <FuseProgressBar active={fusing} />
                            {!fusing && (<>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
                                    <FileDrop label="Professor's Slides" icon={BookOpen} files={slidesFiles} onFiles={setSlidesFiles} />
                                    <FileDrop label="Textbook" icon={FileText} files={textbookFiles} onFiles={setTextbookFiles} />
                                </div>
                                <div style={{ marginBottom: 24 }}>
                                    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text2)', marginBottom: 10 }}>Proficiency Level</label>
                                    <div style={{ display: 'flex', gap: 10 }}>
                                        {[['Beginner','Simpler, analogies-first'],['Intermediate','Balanced depth'],['Advanced','Dense, technical']].map(([p,d]) => (
                                            <button key={p} onClick={() => setProf(p)} style={{ flex: 1, padding: '10px 8px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${prof === p ? 'var(--text)' : 'var(--border)'}`, background: prof === p ? 'var(--text)' : 'var(--bg)', color: prof === p ? '#fff' : 'var(--text2)', textAlign: 'center', transition: 'all 0.15s' }}>
                                                <div style={{ fontWeight: 600, fontSize: 13 }}>{p}</div>
                                                <div style={{ fontSize: 11, marginTop: 2, opacity: 0.7 }}>{d}</div>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                                <button data-testid="generate-notes-btn" className="btn btn-primary btn-lg" style={{ width: '100%', gap: 8 }} onClick={handleFuse} disabled={fusing || !slidesFiles.length || !textbookFiles.length}>
                                    <Sparkles size={16} /> Generate Digital Notes
                                </button>
                                <p style={{ textAlign: 'center', fontSize: 11, color: 'var(--text3)', marginTop: 12 }}>← → arrow keys to navigate pages · Ctrl+D to ask a doubt</p>
                            </>)}
                        </div>
                    </div>
                ) : (
                    <div ref={noteScrollRef} style={{ flex: 1, overflowY: 'auto', display: 'flex', justifyContent: 'center', background: '#F0F2F5', padding: '28px 24px' }}>
                        <div style={{ maxWidth: 760, width: '100%' }}>
                            {gapText && (
                                <div style={{ marginBottom: 14, padding: '10px 14px', background: '#FEF3C7', border: '1px solid #FDE68A', borderRadius: 8, fontSize: 12, color: '#92400E', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                    <Brain size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                                    <div><b>Concept gap identified:</b> {gapText}</div>
                                    <button onClick={() => setGapText('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#92400E', padding: 0, marginLeft: 'auto' }}><X size={13} /></button>
                                </div>
                            )}
                            {/* Notebook page */}
                            <div style={{ display: 'flex', background: '#fff', borderRadius: 4, boxShadow: '0 2px 8px rgba(0,0,0,0.08), 0 12px 40px rgba(0,0,0,0.10)', border: '1px solid #d0d0d0', overflow: 'hidden' }}>
                                <div style={{ width: 38, background: '#F8FAFC', borderRight: '2px solid #E5E7EB', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-evenly', padding: '32px 0', alignSelf: 'stretch', minHeight: 560 }}>
                                    {[0,1,2,3,4,5].map(i => <div key={i} style={{ width: 16, height: 16, borderRadius: '50%', background: '#fff', border: '2px solid #CBD5E1', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.15)' }} />)}
                                </div>
                                <div style={{ width: 1.5, background: '#FCA5A5', flexShrink: 0 }} />
                                <div style={{ flex: 1, padding: '40px 48px 48px 36px', minWidth: 0 }}>
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, paddingBottom: 10, borderBottom: '1px solid #E5E7EB' }}>
                                        <span style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Inter,sans-serif' }}>{notebook?.name || 'Study Notes'}</span>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                            {mutatedPages.has(currentPage) && <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: '#EDE9FE', color: '#7C3AED', border: '1px solid #C4B5FD', letterSpacing: '0.05em' }}>✨ Mutated</span>}
                                            <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>Page {currentPage + 1} of {pages.length}</span>
                                        </div>
                                    </div>
                                    <NoteRenderer content={pages[currentPage]} />
                                    <div style={{ marginTop: 32, paddingTop: 10, borderTop: '1px solid #E5E7EB', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: 10, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>{notebook?.course || ''}</span>
                                        <span style={{ fontSize: 10, color: '#9CA3AF', fontFamily: 'Inter,sans-serif' }}>AuraGraph · {prof}</span>
                                    </div>
                                </div>
                            </div>
                            {/* Bottom bar */}
                            <div style={{ marginTop: 16, display: 'flex', justifyContent: 'center', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                                <button data-testid="re-upload-btn" className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => setNote('')}><Upload size={12} /> Re-upload materials</button>
                                <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => extractAndSaveGraph(note)}><RefreshCw size={12} /> Refresh Concept Map</button>
                                {/* Page dots */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                                    {pages.slice(0, Math.min(pages.length, 20)).map((_, i) => (
                                        <button key={i} className="page-dot" data-label={`Page ${i + 1}`} onClick={() => setCurrentPage(i)} title={`Page ${i + 1}`} style={{ width: i === currentPage ? 20 : 6, height: 6, borderRadius: 3, border: 'none', cursor: 'pointer', background: i === currentPage ? '#7C3AED' : mutatedPages.has(i) ? '#C4B5FD' : 'var(--border2)', transition: 'all 0.2s', padding: 0 }} />
                                    ))}
                                    {pages.length > 20 && <span style={{ fontSize: 10, color: 'var(--text3)' }}>+{pages.length - 20}</span>}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* Right Sidebar */}
                <aside className={sidebarOpen ? 'sidebar-panel' : 'sidebar-panel collapsed'}>
                        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
                            {[{ key: 'map', label: 'Concept Map', icon: <Brain size={12}/> }, { key: 'doubts', label: (() => { const onPage = doubtsLog.filter(d => d.pageIdx === currentPage).length; const total = doubtsLog.length; if (!total) return 'Doubts'; if (onPage) return `Doubts (${onPage}/${total})`; return `Doubts (${total})`; })(), icon: <MessageCircle size={12}/> }].map(tab => (
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

            {mutating && pages.length > 0 && <MutateModal page={pages[currentPage]} onClose={() => setMutating(false)} onMutate={handleMutate} />}
        </div>
    );
}
