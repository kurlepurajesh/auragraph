import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { setGraphData, updateNodeStatus } from '../store';
import { ls_getNotebook, ls_saveNote } from '../localNotebooks';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import {
    Sparkles, Loader2, ChevronLeft, ChevronRight, Upload, FileText,
    BookOpen, MessageSquare, ArrowLeft, Zap, Brain, CheckCircle2,
    AlertCircle, MinusCircle, RefreshCw, X, ChevronDown, ChevronUp,
    MessageCircle, GitBranch
} from 'lucide-react';

const API = 'http://localhost:8000';

// ─── Helpers ──────────────────────────────────────────────────────────────────
function authHeaders() {
    const token = localStorage.getItem('ag_token') || 'demo-token';
    return { Authorization: `Bearer ${token}` };
}

// ─── FileDrop (supports multiple PDFs) ───────────────────────────────────────
function FileDrop({ label, icon, files, onFiles }) {
    const ref = useRef();
    const [drag, setDrag] = useState(false);

    const addFiles = (incoming) => {
        const valid = Array.from(incoming).filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
        if (valid.length) onFiles(prev => [...prev, ...valid]);
    };

    const onDrop = (e) => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); };
    const removeFile = (e, idx) => { e.stopPropagation(); onFiles(prev => prev.filter((_, i) => i !== idx)); };

    const hasFiles = files.length > 0;
    const totalMB = (files.reduce((s, f) => s + f.size, 0) / 1024 / 1024).toFixed(1);

    return (
        <div
            onDragOver={e => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
            style={{
                border: `2px dashed ${drag ? 'var(--text)' : hasFiles ? '#10B981' : 'var(--border2)'}`,
                borderRadius: 12, padding: '16px', cursor: 'default',
                background: drag ? 'var(--surface2)' : hasFiles ? '#F0FDF4' : 'var(--surface)',
                transition: 'all 0.15s', minHeight: 120,
            }}
        >
            <input ref={ref} type="file" accept=".pdf" multiple style={{ display: 'none' }}
                onChange={e => addFiles(e.target.files)} />
            {!hasFiles ? (
                <div onClick={() => ref.current.click()} style={{ textAlign: 'center', cursor: 'pointer', padding: '12px 0' }}>
                    <div style={{ fontSize: 26, marginBottom: 8 }}>{icon}</div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text2)' }}>{label}</div>
                    <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 4 }}>Drag & drop multiple files or click</div>
                </div>
            ) : (
                <>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 8 }}>
                        {files.map((f, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#fff', borderRadius: 6, padding: '6px 10px', border: '1px solid #d1fae5' }}>
                                <FileText size={14} color="#10B981" style={{ flexShrink: 0 }} />
                                <span style={{ fontSize: 12, color: '#065f46', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                                <span style={{ fontSize: 10, color: 'var(--text3)', flexShrink: 0 }}>{(f.size / 1024 / 1024).toFixed(1)}MB</span>
                                <button onClick={e => removeFile(e, i)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text3)', lineHeight: 1 }}>✕</button>
                            </div>
                        ))}
                    </div>
                    <button onClick={() => ref.current.click()} style={{ width: '100%', padding: '6px', background: 'transparent', border: '1px dashed #6ee7b7', borderRadius: 6, color: '#10B981', fontSize: 11, cursor: 'pointer', fontWeight: 600 }}>
                        + Add more PDFs · {files.length} file{files.length > 1 ? 's' : ''} · {totalMB} MB total
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
                    Describe what's confusing. AuraGraph will permanently rewrite this page to pre-empt the confusion.
                </p>
                <div style={{ background: 'var(--surface)', borderRadius: 8, padding: '12px', fontSize: 12, color: 'var(--text2)', lineHeight: 1.7, marginBottom: 14, maxHeight: 80, overflow: 'hidden', border: '1px solid var(--border)' }}>
                    {page?.slice(0, 200)}…
                </div>
                <textarea
                    className="input" rows={4} autoFocus
                    value={doubt} onChange={e => setDoubt(e.target.value)}
                    placeholder="e.g. Why does convolution in time domain become multiplication in frequency domain?"
                    style={{ resize: 'vertical', fontFamily: 'inherit', marginBottom: 16 }}
                />
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
                const res = await fetch(`${API}/api/examine`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ concept_name: concept })
                });
                const data = await res.json();
                setQuestions(data.practice_questions);
            } catch {
                setQuestions(`## Practice Questions: ${concept}\n\nBackend not reachable. Start the backend to get AI-generated questions.`);
            } finally {
                setLoading(false);
            }
        })();
    }, [concept]);

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in" onClick={e => e.stopPropagation()} style={{ width: 600, maxWidth: '96vw', maxHeight: '80vh', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div>
                        <h3 style={{ marginBottom: 2 }}>Practice Questions</h3>
                        <p style={{ fontSize: 12, color: 'var(--text3)' }}>Generated for: <b>{concept}</b></p>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}>
                        <X size={18} />
                    </button>
                </div>
                <div style={{ flex: 1, overflowY: 'auto', background: 'var(--surface)', borderRadius: 10, padding: '16px', border: '1px solid var(--border)' }}>
                    {loading
                        ? <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--text3)', fontSize: 13 }}><Loader2 className="spin" size={16} /> Generating questions…</div>
                        : <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'inherit', fontSize: 13, lineHeight: 1.8, color: 'var(--text)' }}>{questions}</pre>
                    }
                </div>
                <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
                    <button className="btn btn-secondary btn-sm" onClick={onClose}>Close</button>
                </div>
            </div>
        </div>
    );
}

// ─── Interactive SVG Knowledge Graph ─────────────────────────────────────────
const STATUS_COLOR = {
    mastered: { fill: '#10B981', ring: '#6EE7B7', text: '#064E3B' },
    partial: { fill: '#F59E0B', ring: '#FCD34D', text: '#78350F' },
    struggling: { fill: '#EF4444', ring: '#FCA5A5', text: '#7F1D1D' },
};

function KnowledgeGraph({ nodes, edges, onNodeClick, onStatusChange, notebookId }) {
    const svgRef = useRef();
    const W = 280, H = 400;

    if (!nodes || nodes.length === 0) {
        return (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 200, color: 'var(--text3)', fontSize: 12, textAlign: 'center', padding: '0 16px' }}>
                <Brain size={28} color="var(--border2)" style={{ marginBottom: 10 }} />
                <p>Concept graph will appear here<br />after generating notes.</p>
            </div>
        );
    }

    // Map node ids to canvas positions (nodes have x,y as % values)
    const getPos = (n) => ({
        cx: (n.x / 100) * (W - 60) + 30,
        cy: (n.y / 100) * (H - 60) + 30,
    });

    const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));

    return (
        <div>
            <svg ref={svgRef} width={W} height={H} style={{ display: 'block', width: '100%' }}
                viewBox={`0 0 ${W} ${H}`}>
                <defs>
                    {nodes.map(n => {
                        const c = STATUS_COLOR[n.status] || STATUS_COLOR.partial;
                        return (
                            <radialGradient key={n.id} id={`grd-${n.id}`} cx="50%" cy="50%" r="50%">
                                <stop offset="0%" stopColor={c.ring} stopOpacity="0.6" />
                                <stop offset="100%" stopColor={c.fill} stopOpacity="1" />
                            </radialGradient>
                        );
                    })}
                </defs>

                {/* Edges */}
                {edges.map((e, i) => {
                    const src = nodeById[e[0]], dst = nodeById[e[1]];
                    if (!src || !dst) return null;
                    const sp = getPos(src), dp = getPos(dst);
                    return (
                        <line key={i} x1={sp.cx} y1={sp.cy} x2={dp.cx} y2={dp.cy}
                            stroke="var(--border2)" strokeWidth={1.5} strokeDasharray="4,3" opacity={0.7} />
                    );
                })}

                {/* Nodes */}
                {nodes.map(n => {
                    const c = STATUS_COLOR[n.status] || STATUS_COLOR.partial;
                    const { cx, cy } = getPos(n);
                    const r = 12;
                    const label = n.label.length > 16 ? n.label.slice(0, 14) + '…' : n.label;
                    return (
                        <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => onNodeClick(n)}>
                            {/* Glow ring */}
                            <circle cx={cx} cy={cy} r={r + 5} fill={c.ring} opacity={0.25} />
                            {/* Main node */}
                            <circle cx={cx} cy={cy} r={r} fill={`url(#grd-${n.id})`}
                                stroke={c.fill} strokeWidth={1.5} />
                            {/* Label below */}
                            <text x={cx} y={cy + r + 12} textAnchor="middle"
                                fontSize={9} fill="var(--text2)" fontWeight={500}
                                style={{ pointerEvents: 'none', userSelect: 'none' }}>
                                {label}
                            </text>
                        </g>
                    );
                })}
            </svg>
        </div>
    );
}

// ─── Node Detail Popover ──────────────────────────────────────────────────────
function NodePopover({ node, onClose, onExamine, onStatusChange }) {
    const statusOptions = ['mastered', 'partial', 'struggling'];
    const icons = { mastered: <CheckCircle2 size={13} />, partial: <MinusCircle size={13} />, struggling: <AlertCircle size={13} /> };
    const colors = { mastered: '#10B981', partial: '#F59E0B', struggling: '#EF4444' };

    return (
        <div style={{ background: 'var(--bg)', borderRadius: 12, border: '1px solid var(--border)', boxShadow: 'var(--shadow-md)', padding: '14px 16px', margin: '0 12px 12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>{node.label}</div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: 0 }}><X size={14} /></button>
            </div>

            <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 10 }}>Set mastery level:</div>
            <div style={{ display: 'flex', gap: 6, marginBottom: 12 }}>
                {statusOptions.map(s => (
                    <button key={s} onClick={() => onStatusChange(node, s)} style={{
                        flex: 1, padding: '6px 4px', borderRadius: 7, border: `1px solid ${node.status === s ? colors[s] : 'var(--border)'}`,
                        background: node.status === s ? colors[s] + '22' : 'transparent',
                        color: node.status === s ? colors[s] : 'var(--text3)',
                        fontSize: 10, fontWeight: 600, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4
                    }}>
                        {icons[s]} {s}
                    </button>
                ))}
            </div>

            <button onClick={() => onExamine(node.label)} style={{
                width: '100%', padding: '8px', borderRadius: 8, border: 'none',
                background: node.status === 'struggling' ? '#EF4444' : 'var(--text)',
                color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6
            }}>
                <Brain size={13} /> Generate Practice Questions
            </button>
        </div>
    );
}

// ─── Knowledge Panel ──────────────────────────────────────────────────────────
function KnowledgePanel({ nodes, edges, notebookId, onNodeStatusChange }) {
    const [selectedNode, setSelectedNode] = useState(null);
    const [examinerConcept, setExaminerConcept] = useState(null);

    const handleNodeClick = (node) => {
        setSelectedNode(prev => prev?.id === node.id ? null : node);
    };

    const handleStatusChange = (node, newStatus) => {
        onNodeStatusChange(node, newStatus);
        setSelectedNode(prev => prev?.id === node.id ? { ...prev, status: newStatus } : prev);
    };

    const masterCount = nodes.filter(n => n.status === 'mastered').length;
    const partialCount = nodes.filter(n => n.status === 'partial').length;
    const strugCount = nodes.filter(n => n.status === 'struggling').length;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
            {/* Header */}
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)' }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8 }}>Cognitive Knowledge Map</div>
                {nodes.length > 0 && (
                    <div style={{ display: 'flex', gap: 6 }}>
                        {[['mastered', '#10B981', masterCount], ['partial', '#F59E0B', partialCount], ['struggling', '#EF4444', strugCount]].map(([k, c, count]) => (
                            <div key={k} style={{ flex: 1, textAlign: 'center', background: c + '15', borderRadius: 6, padding: '4px', border: `1px solid ${c}33` }}>
                                <div style={{ fontSize: 16, fontWeight: 800, color: c }}>{count}</div>
                                <div style={{ fontSize: 9, color: c, textTransform: 'uppercase', fontWeight: 600 }}>{k}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Graph area */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 0 0' }}>
                <KnowledgeGraph
                    nodes={nodes}
                    edges={edges}
                    onNodeClick={handleNodeClick}
                    onStatusChange={handleStatusChange}
                    notebookId={notebookId}
                />

                {/* Node popover */}
                {selectedNode && (
                    <NodePopover
                        node={selectedNode}
                        onClose={() => setSelectedNode(null)}
                        onExamine={(label) => { setExaminerConcept(label); setSelectedNode(null); }}
                        onStatusChange={handleStatusChange}
                    />
                )}

                {/* Concept list */}
                {nodes.length > 0 && (
                    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', marginTop: 8 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>All Concepts</div>
                        {nodes.map(n => {
                            const c = STATUS_COLOR[n.status] || STATUS_COLOR.partial;
                            return (
                                <div key={n.id} onClick={() => handleNodeClick(n)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 7, marginBottom: 3, background: selectedNode?.id === n.id ? 'var(--surface2)' : 'transparent', cursor: 'pointer', border: selectedNode?.id === n.id ? '1px solid var(--border)' : '1px solid transparent', transition: 'all 0.1s' }}>
                                    <div style={{ width: 9, height: 9, borderRadius: '50%', background: c.fill, flexShrink: 0, boxShadow: `0 0 5px ${c.fill}88` }} />
                                    <div style={{ flex: 1, fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.label}</div>
                                    <div style={{ fontSize: 10, color: c.fill, textTransform: 'capitalize', fontWeight: 600 }}>{n.status}</div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Legend */}
            <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)', display: 'flex', gap: 14 }}>
                {[['mastered', '#10B981'], ['partial', '#F59E0B'], ['struggling', '#EF4444']].map(([k, c]) => (
                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: 'var(--text3)' }}>
                        <div style={{ width: 7, height: 7, borderRadius: '50%', background: c }} /> {k}
                    </div>
                ))}
            </div>

            {examinerConcept && (
                <ExaminerModal concept={examinerConcept} onClose={() => setExaminerConcept(null)} />
            )}
        </div>
    );
}

// ─── PDF Notebook Renderer ──────────────────────────────────────────────────
function NoteRenderer({ content }) {
    const mkComponents = {
        h1({ children }) {
            return (
                <div style={{ background: 'linear-gradient(135deg, #1e3a5f 0%, #0f2240 100%)', color: '#fff', padding: '22px 28px', borderRadius: 10, marginBottom: 28, boxShadow: '0 4px 18px rgba(15,34,64,0.22)' }}>
                    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.14em', opacity: 0.65, marginBottom: 6, fontFamily: 'Inter, sans-serif', fontWeight: 600 }}>AuraGraph · Study Notes</div>
                    <div style={{ fontSize: 20, fontWeight: 800, lineHeight: 1.3, fontFamily: 'Inter, sans-serif' }}>{children}</div>
                </div>
            );
        },
        h2({ children }) {
            return (
                <div style={{ display: 'flex', alignItems: 'stretch', gap: 0, marginTop: 34, marginBottom: 14 }}>
                    <div style={{ width: 5, borderRadius: 3, background: 'linear-gradient(180deg, #3B82F6, #6366F1)', flexShrink: 0, marginRight: 14 }} />
                    <div>
                        <div style={{ fontSize: 17, fontWeight: 800, color: '#1e3a5f', lineHeight: 1.3, fontFamily: 'Inter, sans-serif' }}>{children}</div>
                        <div style={{ height: 1, background: 'linear-gradient(90deg, #DBEAFE, transparent)', marginTop: 6 }} />
                    </div>
                </div>
            );
        },
        h3({ children }) {
            return (
                <div style={{ borderLeft: '3px solid #10B981', paddingLeft: 11, marginTop: 20, marginBottom: 8 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#065f46', textTransform: 'uppercase', letterSpacing: '0.06em', fontFamily: 'Inter, sans-serif' }}>{children}</span>
                </div>
            );
        },
        code({ className, children }) {
            const isBlock = !!className;
            if (!isBlock) return (
                <code style={{ background: '#EFF6FF', color: '#1D4ED8', borderRadius: 4, padding: '1px 5px', fontSize: 13, fontFamily: '"Courier New", monospace', fontWeight: 600 }}>{children}</code>
            );
            return (
                <pre style={{ background: '#F8FAFC', border: '1.5px solid #E2E8F0', borderRadius: 8, padding: '14px 18px', margin: '14px 0', fontFamily: '"Courier New", Courier, monospace', fontSize: 13.5, lineHeight: 1.75, color: '#334155', overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
                    <code>{children}</code>
                </pre>
            );
        },
        pre({ children }) { return <>{children}</>; },
        blockquote({ children }) {
            // Safely extract text without serialising React fibers
            const extractText = (node) => {
                if (!node) return '';
                if (typeof node === 'string') return node;
                if (Array.isArray(node)) return node.map(extractText).join('');
                if (node?.props?.children) return extractText(node.props.children);
                return '';
            };
            const flat = extractText(children);
            const isExamTip = flat.includes('Exam Tip');
            const isIntuition = flat.includes('💡') || flat.includes('Intuition');
            const isWarning = flat.includes('⚠️') || flat.includes('warning') || flat.includes('offline mode');
            if (isIntuition) return (
                <div style={{ background: '#F5F3FF', border: '1.5px solid #C4B5FD', borderLeft: '5px solid #7C3AED', borderRadius: 8, padding: '12px 16px', margin: '14px 0', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>💡</span>
                    <div style={{ fontSize: 13.5, color: '#4C1D95', lineHeight: 1.75, fontFamily: 'Inter, sans-serif' }}>{children}</div>
                </div>
            );
            if (isExamTip) return (
                <div style={{ background: '#FFFBEB', border: '1.5px solid #FCD34D', borderLeft: '5px solid #F59E0B', borderRadius: 8, padding: '12px 16px', margin: '12px 0', display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>📝</span>
                    <div style={{ fontSize: 13.5, color: '#78350F', lineHeight: 1.7, fontFamily: 'Inter, sans-serif' }}>{children}</div>
                </div>
            );
            if (isWarning) return (
                <div style={{ background: '#FFF7ED', border: '1.5px solid #FDBA74', borderLeft: '5px solid #F97316', borderRadius: 8, padding: '12px 16px', margin: '10px 0', fontSize: 13, color: '#7C2D12', lineHeight: 1.65, fontFamily: 'Inter, sans-serif' }}>{children}</div>
            );
            return (
                <div style={{ background: '#F0FDF4', border: '1.5px solid #86EFAC', borderLeft: '5px solid #22C55E', borderRadius: 8, padding: '12px 16px', margin: '12px 0', fontSize: 13.5, color: '#14532D', lineHeight: 1.7, fontFamily: 'Inter, sans-serif' }}>{children}</div>
            );
        },
        strong({ children }) {
            return <strong style={{ color: '#1e3a5f', background: '#EFF6FF', borderRadius: 3, padding: '0 3px', fontWeight: 700 }}>{children}</strong>;
        },
        em({ children }) {
            return <span style={{ color: '#6D28D9', fontStyle: 'italic' }}>{children}</span>;
        },
        hr() {
            return <div style={{ border: 'none', borderTop: '2px dashed #E5E7EB', margin: '28px 0' }} />;
        },
        p({ children }) {
            return <p style={{ marginBottom: 11, lineHeight: 1.95, color: '#1F2937', fontFamily: '"Computer Modern", "CMU Serif", Georgia, serif', fontSize: 15 }}>{children}</p>;
        },
        ul({ children }) {
            return <ul style={{ paddingLeft: 22, margin: '8px 0 14px', lineHeight: 1.9, fontFamily: '"Computer Modern", "CMU Serif", Georgia, serif', fontSize: 15, color: '#1F2937' }}>{children}</ul>;
        },
        ol({ children }) {
            return <ol style={{ paddingLeft: 22, margin: '8px 0 14px', lineHeight: 1.9, fontFamily: '"Computer Modern", "CMU Serif", Georgia, serif', fontSize: 15, color: '#1F2937' }}>{children}</ol>;
        },
        li({ children }) {
            return <li style={{ marginBottom: 5 }}>{children}</li>;
        },
    };
    return <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={mkComponents}
    >{content || ''}</ReactMarkdown>;
}

// ─── Doubts Panel ────────────────────────────────────────────────────────────
function DoubtsPanel({ doubts, currentPage }) {
    const [expanded, setExpanded] = useState({});
    const toggle = (id) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }));

    // Only show doubts for the current page
    const pageDiagnostics = doubts.filter(d => d.pageIdx === currentPage);
    // All other pages that have doubts (for the footer hint)
    const otherPages = [...new Set(doubts.filter(d => d.pageIdx !== currentPage).map(d => d.pageIdx))];

    // Compact markdown renderer for insight bubbles (math + bold + italic only)
    const InsightMarkdown = ({ text }) => (
        <ReactMarkdown
            remarkPlugins={[remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={{
                p: ({ children }) => <span style={{ display: 'block', marginBottom: 4 }}>{children}</span>,
                strong: ({ children }) => <strong style={{ color: '#5B21B6', fontWeight: 700 }}>{children}</strong>,
                em: ({ children }) => <em style={{ color: '#6D28D9' }}>{children}</em>,
                code: ({ children }) => <code style={{ background: '#EDE9FE', color: '#5B21B6', borderRadius: 3, padding: '1px 4px', fontSize: 11, fontFamily: 'monospace' }}>{children}</code>,
                a: ({ children }) => <span>{children}</span>,
            }}
        >{text || ''}</ReactMarkdown>
    );

    if (pageDiagnostics.length === 0) {
        return (
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 }}>
                    <MessageCircle size={26} color="#C4B5FD" />
                    <div style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', lineHeight: 1.7 }}>
                        No doubts on <b>page {currentPage + 1}</b> yet.<br />
                        <span style={{ fontSize: 11 }}>Click <b>Ask a Doubt</b> to add one.</span>
                    </div>
                </div>
                {otherPages.length > 0 && (
                    <div style={{ padding: '10px 14px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text3)', lineHeight: 1.6 }}>
                        Doubts exist on page{otherPages.length > 1 ? 's' : ''}{' '}
                        <span style={{ color: '#7C3AED', fontWeight: 600 }}>
                            {otherPages.map(p => p + 1).join(', ')}
                        </span>
                        {' '}— navigate there to view them.
                    </div>
                )}
            </div>
        );
    }

    return (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Page indicator */}
            <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: '#7C3AED', background: '#EDE9FE', border: '1px solid #C4B5FD', borderRadius: 10, padding: '2px 8px' }}>
                    Page {currentPage + 1}
                </span>
                <span style={{ fontSize: 11, color: 'var(--text3)' }}>
                    {pageDiagnostics.length} doubt{pageDiagnostics.length > 1 ? 's' : ''}
                </span>
                {otherPages.length > 0 && (
                    <span style={{ fontSize: 10, color: '#9CA3AF', marginLeft: 'auto' }}>
                        +{doubts.length - pageDiagnostics.length} on other pages
                    </span>
                )}
            </div>

            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 10px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                {pageDiagnostics.map((d) => {
                    const isExpanded = !!expanded[d.id];
                    const previewLen = 130;
                    const needsExpand = d.insight.length > previewLen;
                    const previewText = needsExpand && !isExpanded
                        ? d.insight.slice(0, previewLen).replace(/\*\*[^*]*$/, '').replace(/\$[^$]*$/, '') + '…'
                        : d.insight;

                    return (
                        <div key={d.id}>
                            {/* Timestamp + status row */}
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6, marginBottom: 4 }}>
                                {d.success
                                    ? <span style={{ fontSize: 9, color: '#7C3AED', fontWeight: 700 }}>✨ mutated</span>
                                    : <span style={{ fontSize: 9, color: '#9CA3AF' }}>logged</span>}
                                <span style={{ fontSize: 9, color: '#D1D5DB' }}>{d.time}</span>
                            </div>

                            {/* Student bubble — right aligned */}
                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
                                <div style={{ maxWidth: '84%', background: '#7C3AED', color: '#fff', borderRadius: '14px 14px 3px 14px', padding: '9px 13px', fontSize: 12.5, lineHeight: 1.55, boxShadow: '0 1px 4px rgba(124,58,237,0.3)' }}>
                                    {d.doubt}
                                </div>
                            </div>

                            {/* AuraGraph bubble — left aligned */}
                            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                                <div style={{ maxWidth: '90%', background: '#F5F3FF', border: '1px solid #DDD6FE', borderRadius: '3px 14px 14px 14px', padding: '9px 13px', fontSize: 12, lineHeight: 1.7, color: '#3B0764' }}>
                                    <div style={{ fontSize: 10, fontWeight: 700, color: '#7C3AED', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 4 }}>
                                        <GitBranch size={10} /> AuraGraph
                                    </div>
                                    <div style={{ color: '#4C1D95' }}>
                                        <InsightMarkdown text={previewText} />
                                    </div>
                                    {d.gap && isExpanded && (
                                        <div style={{ marginTop: 7, paddingTop: 7, borderTop: '1px solid #DDD6FE', fontSize: 11, color: '#7C3AED', fontStyle: 'italic' }}>
                                            🔍 {d.gap}
                                        </div>
                                    )}
                                    {needsExpand && (
                                        <button onClick={() => toggle(d.id)} style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: '#7C3AED', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontWeight: 600 }}>
                                            {isExpanded ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> Read more</>}
                                        </button>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

// ─── Main Notebook Workspace ──────────────────────────────────────────────────
export default function NotebookWorkspace() {
    const { id } = useParams();
    const navigate = useNavigate();
    const dispatch = useDispatch();

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
    const [rightTab, setRightTab] = useState('map'); // 'map' | 'doubts'

    // Per-notebook graph state
    const [graphNodes, setGraphNodes] = useState([]);
    const [graphEdges, setGraphEdges] = useState([]);

    const pages = useMemo(() => {
        if (!note) return [];

        // Split on level-2 Markdown headings (## Title)
        const byH2 = note.split(/(?=^## )/m).map(s => s.trim()).filter(Boolean);

        if (byH2.length > 1) {
            // Merge sections whose body (after heading) is too short (< 100 chars)
            const merged = [];
            let buffer = '';
            for (const section of byH2) {
                const body = section.replace(/^## .+$/m, '').trim();
                if (body.length < 100) {
                    buffer = buffer ? buffer + '\n\n' + section : section;
                } else {
                    merged.push(buffer ? buffer + '\n\n' + section : section);
                    buffer = '';
                }
            }
            if (buffer) merged.push(buffer);
            return merged.filter(Boolean);
        }

        // Fallback: split on ### headings
        const byH3 = note.split(/(?=^### )/m).map(s => s.trim()).filter(Boolean);
        if (byH3.length > 1) return byH3;

        // Last fallback: group paragraphs into ~600-char chunks
        const paras = note.split(/\n\n+/).filter(p => p.trim().length > 40);
        const chunks = [];
        let current = '';
        for (const para of paras) {
            if (current.length + para.length > 700 && current.length > 150) {
                chunks.push(current.trim());
                current = para;
            } else {
                current += (current ? '\n\n' : '') + para;
            }
        }
        if (current) chunks.push(current.trim());
        return chunks.length ? chunks : [note];
    }, [note]);

    // Load notebook + graph
    useEffect(() => {
        fetch(`${API}/notebooks/${id}`, { headers: authHeaders() })
            .then(r => { if (!r.ok) throw new Error('backend_' + r.status); return r.json(); })
            .then(nb => {
                if (!nb || !nb.id) throw new Error('invalid_response');
                setNotebook(nb);
                setNote(nb.note || '');
                setProf(nb.proficiency || 'Intermediate');
                if (nb.graph?.nodes?.length) {
                    setGraphNodes(nb.graph.nodes);
                    setGraphEdges(nb.graph.edges || []);
                }
            })
            .catch(() => {
                const local = ls_getNotebook(id);
                if (local) {
                    setNotebook(local);
                    setNote(local.note || '');
                    setProf(local.proficiency || 'Intermediate');
                    if (local.graph?.nodes?.length) {
                        setGraphNodes(local.graph.nodes);
                        setGraphEdges(local.graph.edges || []);
                    }
                } else {
                    setNotebook({ id, name: 'Untitled', course: '' });
                }
            });
    }, [id]);

    const saveNote = async (newNote, newProf) => {
        ls_saveNote(id, newNote, newProf);
        try {
            await fetch(`${API}/notebooks/${id}/note`, {
                method: 'PATCH',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: newNote, proficiency: newProf })
            });
        } catch { }
    };

    const extractAndSaveGraph = async (noteText) => {
        try {
            const res = await fetch(`${API}/api/extract-concepts`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ note: noteText, notebook_id: id })
            });
            const graph = await res.json();
            if (graph.nodes?.length) {
                setGraphNodes(graph.nodes);
                setGraphEdges(graph.edges || []);
            }
        } catch { /* non-critical */ }
    };

    const handleFuse = async () => {
        if (!slidesFiles.length || !textbookFiles.length) return;
        setFusing(true);
        setFuseProgress(`Uploading ${slidesFiles.length + textbookFiles.length} PDFs…`);
        try {
            const form = new FormData();
            slidesFiles.forEach(f => form.append('slides_pdfs', f));
            textbookFiles.forEach(f => form.append('textbook_pdfs', f));
            form.append('proficiency', prof);
            setFuseProgress('Running Fusion Agent… (may take 15–30s)');
            const res = await fetch(`${API}/api/upload-fuse-multi`, { method: 'POST', body: form });
            const data = await res.json();
            setNote(data.fused_note);
            setCurrentPage(0);
            await saveNote(data.fused_note, prof);
            setFuseProgress('Extracting concept map…');
            await extractAndSaveGraph(data.fused_note);
        } catch {
            const errNote = `## ⚠️ Backend Not Running\n\nNotes could not be generated because the AuraGraph backend server is not reachable at \`http://localhost:8000\`.\n\n**To fix this, start the backend:**\n\n\`\`\`bash\ncd backend\nsource venv/bin/activate\nuvicorn main:app --reload --port 8000\n\`\`\`\n\nOnce the server is running, come back here and click **Re-upload materials** to try again.\n\n> The local summarizer generates real notes from your PDFs even without Azure OpenAI keys.`;
            setNote(errNote);
            setCurrentPage(0);
            await saveNote(errNote, prof);
        }
        setFusing(false);
        setFuseProgress('');
    };

    const handleMutate = useCallback(async (page, doubt) => {
        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        const logId = Date.now();
        try {
            const res = await fetch(`${API}/api/mutate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ original_paragraph: page, student_doubt: doubt })
            });
            const data = await res.json();
            const newNote = note.replace(page, data.mutated_paragraph);
            setNote(newNote);
            setGapText(data.concept_gap);
            setMutatedPages(prev => new Set([...prev, currentPage]));
            await saveNote(newNote, prof);
            extractAndSaveGraph(newNote);
            // Log to doubts sidebar — extract the 💡 intuition line, keeping markdown for rendering
            const intuitionLine = data.mutated_paragraph
                .split('\n')
                .find(l => l.includes('💡') || l.startsWith('> '));
            const insightText = intuitionLine
                ? intuitionLine.replace(/^>\s*/, '').trim()   // strip only the "> " blockquote prefix
                : data.concept_gap || 'Page updated with your clarification.';
            setDoubtsLog(prev => [{ id: logId, pageIdx: currentPage, doubt, insight: insightText, gap: data.concept_gap, time: timestamp, success: true }, ...prev]);
            setRightTab('doubts');
        } catch {
            // Even on failure, log the doubt
            setDoubtsLog(prev => [{ id: logId, pageIdx: currentPage, doubt,
                insight: 'Could not reach the backend to mutate this page. Your doubt has been recorded — reconnect to get an AI rewrite.',
                gap: 'Backend unreachable', time: timestamp, success: false }, ...prev]);
            setRightTab('doubts');
        }
    }, [note, prof, id, currentPage]);

    const handleNodeStatusChange = async (node, newStatus) => {
        // Update local state
        setGraphNodes(prev => prev.map(n => n.id === node.id ? { ...n, status: newStatus } : n));
        // Persist to backend
        try {
            await fetch(`${API}/notebooks/${id}/graph/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({ concept_name: node.label, status: newStatus })
            });
        } catch { /* non-critical */ }
    };

    if (!notebook) {
        return (
            <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)' }}>
                <Loader2 className="spin" size={28} color="var(--text3)" />
            </div>
        );
    }

    const hasNote = note.trim().length > 0;

    return (
        <div style={{ height: '100vh', background: 'var(--bg)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {/* Header */}
            <header style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: '0 24px', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <button className="btn btn-ghost btn-sm" onClick={() => navigate('/dashboard')} style={{ gap: 5 }}>
                        <ArrowLeft size={14} /> Notebooks
                    </button>
                    <div style={{ width: 1, height: 20, background: 'var(--border)' }} />
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 14 }}>{notebook.name}</div>
                        <div style={{ fontSize: 11, color: 'var(--text3)' }}>{notebook.course}</div>
                    </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    {hasNote && (
                        <>
                            {/* Proficiency badge */}
                            <span style={{ fontSize: 11, padding: '3px 10px', borderRadius: 20, background: 'var(--surface2)', border: '1px solid var(--border)', color: 'var(--text2)', fontWeight: 600 }}>{prof}</span>
                            {/* Page nav */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--surface)', padding: '4px 12px', borderRadius: 20, border: '1px solid var(--border)' }}>
                                <button onClick={() => setCurrentPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0} style={{ background: 'none', border: 'none', color: currentPage === 0 ? 'var(--border2)' : 'var(--text2)', cursor: currentPage === 0 ? 'not-allowed' : 'pointer' }}>
                                    <ChevronLeft size={14} />
                                </button>
                                <span style={{ fontSize: 12, color: 'var(--text2)', minWidth: 60, textAlign: 'center' }}>
                                    {currentPage + 1} / {pages.length}
                                </span>
                                <button onClick={() => setCurrentPage(Math.min(pages.length - 1, currentPage + 1))} disabled={currentPage >= pages.length - 1} style={{ background: 'none', border: 'none', color: currentPage >= pages.length - 1 ? 'var(--border2)' : 'var(--text2)', cursor: currentPage >= pages.length - 1 ? 'not-allowed' : 'pointer' }}>
                                    <ChevronRight size={14} />
                                </button>
                            </div>
                            {/* Mutate button */}
                            <button className="btn btn-primary btn-sm" style={{ gap: 5 }} onClick={() => setMutating(true)}>
                                <MessageSquare size={13} /> Ask a Doubt
                            </button>
                        </>
                    )}
                </div>
            </header>

            {/* Body */}
            <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
                {!hasNote ? (
                    /* ── UPLOAD PANE ── */
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 24px' }}>
                        <div style={{ maxWidth: 620, width: '100%' }}>
                            <div style={{ textAlign: 'center', marginBottom: 36 }}>
                                <div style={{ width: 52, height: 52, borderRadius: 14, background: 'var(--text)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 14px' }}>
                                    <Zap size={24} color="white" />
                                </div>
                                <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>Generate Fused Notes</h2>
                                <p style={{ fontSize: 14, color: 'var(--text3)', lineHeight: 1.7 }}>
                                    Upload your course materials and AuraGraph will generate a personalised digital study note calibrated to your level.
                                </p>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
                                <FileDrop label="Professor's Slides" icon="🎓" files={slidesFiles} onFiles={setSlidesFiles} />
                                <FileDrop label="Textbook" icon="📚" files={textbookFiles} onFiles={setTextbookFiles} />
                            </div>

                            <div style={{ marginBottom: 24 }}>
                                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: 'var(--text2)', marginBottom: 10 }}>Proficiency Level</label>
                                <div style={{ display: 'flex', gap: 10 }}>
                                    {[['Beginner', 'Simpler, analogies-first'], ['Intermediate', 'Balanced depth'], ['Advanced', 'Dense, technical']].map(([p, d]) => (
                                        <button key={p} onClick={() => setProf(p)} style={{ flex: 1, padding: '10px 8px', borderRadius: 8, cursor: 'pointer', border: `1px solid ${prof === p ? 'var(--text)' : 'var(--border)'}`, background: prof === p ? 'var(--text)' : 'var(--bg)', color: prof === p ? '#fff' : 'var(--text2)', textAlign: 'center', transition: 'all 0.15s' }}>
                                            <div style={{ fontWeight: 600, fontSize: 13 }}>{p}</div>
                                            <div style={{ fontSize: 11, marginTop: 2, opacity: 0.7 }}>{d}</div>
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <button className="btn btn-primary btn-lg" style={{ width: '100%', gap: 8 }} onClick={handleFuse} disabled={fusing || !slidesFiles.length || !textbookFiles.length}>
                                {fusing ? <><Loader2 className="spin" size={16} /> {fuseProgress}</> : <><Sparkles size={16} /> Generate Digital Notes</>}
                            </button>
                        </div>
                    </div>
                ) : (
                    /* ── NOTE VIEWER ── */
                    <div style={{ flex: 1, overflowY: 'auto', display: 'flex', justifyContent: 'center', background: '#F0F2F5', padding: '28px 24px' }}>
                        <div style={{ maxWidth: 760, width: '100%' }}>
                            {gapText && (
                                <div style={{ marginBottom: 14, padding: '10px 14px', background: '#FEF3C7', border: '1px solid #FDE68A', borderRadius: 8, fontSize: 12, color: '#92400E', display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                    <Brain size={14} style={{ flexShrink: 0, marginTop: 1 }} />
                                    <div><b>Concept gap identified:</b> {gapText}</div>
                                    <button onClick={() => setGapText('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#92400E', padding: 0, marginLeft: 'auto' }}><X size={13} /></button>
                                </div>
                            )}
                            {/* ── Notebook page ── */}
                            <div style={{ display: 'flex', background: '#fff', borderRadius: 4, boxShadow: '0 2px 8px rgba(0,0,0,0.08), 0 12px 40px rgba(0,0,0,0.10)', border: '1px solid #d0d0d0', overflow: 'hidden' }}>
                                {/* Spine holes */}
                                <div style={{ width: 38, background: '#F8FAFC', borderRight: '2px solid #E5E7EB', flexShrink: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'space-evenly', padding: '32px 0', alignSelf: 'stretch', minHeight: 560 }}>
                                    {[0,1,2,3,4,5].map(i => (
                                        <div key={i} style={{ width: 16, height: 16, borderRadius: '50%', background: '#fff', border: '2px solid #CBD5E1', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.15)' }} />
                                    ))}
                                </div>
                                {/* Red margin line */}
                                <div style={{ width: 1.5, background: '#FCA5A5', flexShrink: 0 }} />
                                {/* Page content */}
                                <div style={{ flex: 1, padding: '40px 48px 48px 36px', minWidth: 0 }}>
                                    {/* Page header strip */}
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28, paddingBottom: 10, borderBottom: '1px solid #E5E7EB' }}>
                                        <span style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: 'Inter, sans-serif' }}>{notebook?.name || 'Study Notes'}</span>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                            {mutatedPages.has(currentPage) && (
                                                <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 20, background: '#EDE9FE', color: '#7C3AED', border: '1px solid #C4B5FD', letterSpacing: '0.05em' }}>✨ Mutated</span>
                                            )}
                                            <span style={{ fontSize: 11, color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>Page {currentPage + 1} of {pages.length}</span>
                                        </div>
                                    </div>
                                    <NoteRenderer content={pages[currentPage]} />
                                    {/* Page footer */}
                                    <div style={{ marginTop: 32, paddingTop: 10, borderTop: '1px solid #E5E7EB', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: 10, color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>{notebook?.course || ''}</span>
                                        <span style={{ fontSize: 10, color: '#9CA3AF', fontFamily: 'Inter, sans-serif' }}>AuraGraph · {prof}</span>
                                    </div>
                                </div>
                            </div>
                            {/* Re-upload link */}
                            <div style={{ marginTop: 16, textAlign: 'center', display: 'flex', justifyContent: 'center', gap: 10 }}>
                                <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => setNote('')}>
                                    <Upload size={12} /> Re-upload materials
                                </button>
                                <button className="btn btn-ghost btn-sm" style={{ fontSize: 12 }} onClick={() => extractAndSaveGraph(note)}>
                                    <RefreshCw size={12} /> Refresh Concept Map
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Right: Tab-switched sidebar — Knowledge Map or Doubts Log */}
                <aside style={{ width: 310, minWidth: 310, borderLeft: '1px solid var(--border)', display: 'flex', flexDirection: 'column', background: 'var(--surface)', overflow: 'hidden' }}>
                    {/* Tab header */}
                    <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', flexShrink: 0 }}>
                        {[
                            { key: 'map', label: 'Concept Map', icon: <Brain size={12} /> },
                            { key: 'doubts', label: `Doubts${doubtsLog.length ? ` (${doubtsLog.length})` : ''}`, icon: <MessageCircle size={12} /> },
                        ].map(tab => (
                            <button key={tab.key} onClick={() => setRightTab(tab.key)} style={{
                                flex: 1, padding: '10px 6px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5,
                                fontSize: 11, fontWeight: 600, cursor: 'pointer', border: 'none', transition: 'all 0.15s',
                                borderBottom: rightTab === tab.key ? '2px solid #7C3AED' : '2px solid transparent',
                                background: 'transparent',
                                color: rightTab === tab.key ? '#7C3AED' : 'var(--text3)',
                            }}>
                                {tab.icon} {tab.label}
                            </button>
                        ))}
                    </div>

                    {rightTab === 'map' ? (
                        <KnowledgePanel
                            nodes={graphNodes}
                            edges={graphEdges}
                            notebookId={id}
                            onNodeStatusChange={handleNodeStatusChange}
                        />
                    ) : (
                        <DoubtsPanel doubts={doubtsLog} currentPage={currentPage} />
                    )}
                </aside>
            </div>

            {mutating && pages.length > 0 && (
                <MutateModal page={pages[currentPage]} onClose={() => setMutating(false)} onMutate={handleMutate} />
            )}
        </div>
    );
}
