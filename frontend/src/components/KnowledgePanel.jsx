import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { Brain, CheckCircle2, AlertCircle, MinusCircle, X, ChevronRight, Loader2 } from 'lucide-react';
import { ExaminerModal } from './ExaminerModals';
import SniperExamModal from './SniperExamModal';
import { KnowledgeGraph, SC } from './Graph';
import { authHeaders, API } from './utils';

// ─── Question Cards ───────────────────────────────────────────────────────────
export function QuestionCards({ questions, level, onAllAssessed }) {
    const [revealed, setRevealed] = useState(new Set());
    const [assessments, setAssessments] = useState({});
    const LC = {
        mastered:  { bg: '#DCFCE7', border: '#BBF7D0', accent: '#10B981', text: '#065F46' },
        partial:   { bg: '#FEF9C3', border: '#FDE68A', accent: '#D97706', text: '#78350F' },
        struggling:{ bg: '#FEF2F2', border: '#FECACA', accent: '#DC2626', text: '#7F1D1D' },
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
export function ConceptDetailPanel({ node, notebookId, onClose, onStatusChange, onJumpToSection, onFullPractice }) {
    const [activeLevel, setActiveLevel] = useState(null);
    const [questions, setQuestions] = useState(null);
    const [loadingQ, setLoadingQ] = useState(false);
    const [promotion, setPromotion] = useState(null);
    const [customInstruction, setCustomInstruction] = useState('');

    const LEVELS = [
        { key: 'struggling', label: 'Easy',   color: '#10B981', icon: <CheckCircle2 size={11} />, desc: 'Definitions & recall' },
        { key: 'partial',   label: 'Medium',  color: '#F59E0B', icon: <MinusCircle size={11} />,  desc: 'Exam-style problems' },
        { key: 'mastered',  label: 'Hard',    color: '#EF4444', icon: <AlertCircle size={11} />,  desc: 'Derivations & edge cases' },
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
        if (correct < Math.ceil(total * 0.67)) return;
        const NEXT = { struggling: 'partial', partial: 'mastered', mastered: null };
        const promoted = NEXT[node.status];
        if (promoted) { onStatusChange(node, promoted); setPromotion(promoted); }
        else setPromotion('top');
    };

    return (
        <div style={{ background: 'var(--bg)', borderRadius: 12, border: '1px solid var(--border)', boxShadow: 'var(--shadow-md)', margin: '0 12px 12px', overflow: 'hidden' }}>
            <div style={{ padding: '12px 14px 10px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                    <div style={{ fontWeight: 700, fontSize: 13 }}>{node.label}</div>
                    <div style={{ fontSize: 10, color: statusColors[node.status] || '#9CA3AF', fontWeight: 600, marginTop: 2, textTransform: 'capitalize' }}>&#9679; {node.status}</div>
                </div>
                <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: 0 }}><X size={14} /></button>
            </div>
            <div style={{ padding: '10px 14px', maxHeight: 520, overflowY: 'auto' }}>
                <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 5, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>Set mastery</div>
                <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
                    {LEVELS.map(l => (
                        <button key={l.key} onClick={() => onStatusChange(node, l.key)} style={{ flex: 1, padding: '5px 3px', borderRadius: 7, border: `1px solid ${node.status === l.key ? l.color : 'var(--border)'}`, background: node.status === l.key ? l.color + '18' : 'transparent', color: node.status === l.key ? l.color : 'var(--text3)', fontSize: 10, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3 }}>
                            {node.status === l.key && l.icon} {l.label}
                        </button>
                    ))}
                </div>
                <button onClick={() => onJumpToSection(node.full_label || node.label)} style={{ width: '100%', padding: '7px 10px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text2)', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginBottom: 12 }}>
                    <ChevronRight size={12} /> Jump to Concept in Notes
                </button>
                <div style={{ fontSize: 10, color: 'var(--text3)', marginBottom: 6, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>🎯 Practice Questions</div>
                <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                    {LEVELS.map(l => (
                        <button key={l.key} onClick={() => fetchLevel(l.key)} style={{ flex: 1, padding: '7px 4px', borderRadius: 8, border: `1px solid ${activeLevel === l.key ? l.color : 'var(--border)'}`, background: activeLevel === l.key ? l.color + '18' : 'var(--surface)', color: activeLevel === l.key ? l.color : 'var(--text3)', fontSize: 10, fontWeight: 600, cursor: 'pointer', textAlign: 'center', transition: 'all 0.15s' }}>
                            <div>{l.label}</div>
                            <div style={{ fontSize: 9, opacity: 0.7, marginTop: 1 }}>{l.desc}</div>
                        </button>
                    ))}
                </div>
                <div style={{ display: 'flex', gap: 5, marginBottom: 10 }}>
                    <input
                        value={customInstruction}
                        onChange={e => setCustomInstruction(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter' && activeLevel) fetchLevel(activeLevel); }}
                        placeholder="Custom focus, e.g. numerical only, derivations…"
                        style={{ flex: 1, fontSize: 11, padding: '5px 9px', borderRadius: 7, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', outline: 'none', fontFamily: 'inherit' }}
                    />
                    {activeLevel && (
                        <button onClick={() => fetchLevel(activeLevel)} disabled={loadingQ} title="Regenerate with this focus"
                            style={{ padding: '5px 9px', borderRadius: 7, border: '1px solid var(--purple)', background: 'var(--purple-light)', color: 'var(--purple)', fontSize: 11, fontWeight: 700, cursor: 'pointer', flexShrink: 0 }}>
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
                <button onClick={() => onFullPractice(node.label)} style={{ width: '100%', marginTop: 14, padding: '8px 0', background: 'transparent', border: '1px solid var(--border)', borderRadius: 8, color: 'var(--text3)', fontSize: 11, fontWeight: 600, cursor: 'pointer', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 5 }}>
                    <Brain size={12} /> Full Practice Paper (5 Qs)
                </button>
            </div>
        </div>
    );
}

// ─── Knowledge Panel ──────────────────────────────────────────────────────────
export default function KnowledgePanel({ nodes, edges, notebookId, onNodeStatusChange, onJumpToSection }) {
    const [selectedNode, setSelectedNode] = useState(null);
    const [examinerConcept, setExaminerConcept] = useState(null);
    const [sniperOpen, setSniperOpen] = useState(false);
    const [nudgeDismissed, setNudgeDismissed] = useState(false);

    const handleNodeClick = n => setSelectedNode(p => p?.id === n.id ? null : n);
    const handleStatusChange = (node, status) => {
        onNodeStatusChange(node, status);
        setSelectedNode(p => p?.id === node.id ? { ...p, status } : p);
    };

    const mc = nodes.filter(n => n.status === 'mastered').length;
    const pc = nodes.filter(n => n.status === 'partial').length;
    const sc = nodes.filter(n => n.status === 'struggling').length;
    const weakCount = sc + pc;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
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
                {selectedNode && (
                    <ConceptDetailPanel node={selectedNode} notebookId={notebookId}
                        onClose={() => setSelectedNode(null)}
                        onStatusChange={handleStatusChange}
                        onJumpToSection={label => { onJumpToSection(label); setSelectedNode(null); }}
                        onFullPractice={label => { setExaminerConcept(label); setSelectedNode(null); }}
                    />
                )}
                {nodes.length > 0 && (
                    <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', marginTop: 8 }}>
                        <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>All Concepts</div>
                        {nodes.map(n => {
                            const c = SC[n.status] || SC.partial;
                            return (
                                <div key={n.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 8px', borderRadius: 7, marginBottom: 3, background: selectedNode?.id === n.id ? 'var(--surface2)' : 'transparent', border: selectedNode?.id === n.id ? '1px solid var(--border)' : '1px solid transparent', transition: 'all 0.1s' }}>
                                    <div style={{ width: 9, height: 9, borderRadius: '50%', background: c.fill, flexShrink: 0, boxShadow: `0 0 5px ${c.fill}88` }} />
                                    <div onClick={() => handleNodeClick(n)} style={{ flex: 1, fontSize: 12, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}>{n.label}</div>
                                    <button onClick={e => { e.stopPropagation(); onJumpToSection(n.full_label || n.label); }} title="Jump to this concept in notes"
                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: '2px 3px', borderRadius: 4, display: 'flex', alignItems: 'center', flexShrink: 0, opacity: 0.6, transition: 'opacity 0.15s' }}
                                        onMouseEnter={e => e.currentTarget.style.opacity = '1'}
                                        onMouseLeave={e => e.currentTarget.style.opacity = '0.6'}>
                                        <ChevronRight size={13} />
                                    </button>
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
