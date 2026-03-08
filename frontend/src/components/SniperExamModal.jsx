import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { X, Loader2 } from 'lucide-react';
import { API, authHeaders } from './utils';

export default function SniperExamModal({ nodes, notebookId, onClose }) {
    const weakNodes = nodes.filter(n => n.status === 'struggling' || n.status === 'partial');
    const [questions, setQuestions] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [qIdx, setQIdx] = React.useState(0);
    const [selected, setSelected] = React.useState(null);
    const [revealed, setRevealed] = React.useState(false);
    const [score, setScore] = React.useState(0);
    const [done, setDone] = React.useState(false);

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
    const total = questions.length;

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
                        <div style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text3)', marginBottom: 5, fontWeight: 600 }}>
                                <span>Question {qIdx + 1} of {total}</span>
                                <span style={{ color: '#10B981' }}>Score: {score}</span>
                            </div>
                            <div className="progress-bar-track">
                                <div className="progress-bar-fill" style={{ width: `${((qIdx) / total) * 100}%`, background: 'linear-gradient(90deg,#7C3AED,#2563EB)' }} />
                            </div>
                        </div>

                        {current.concept && (
                            <div style={{ marginBottom: 10, display: 'inline-flex', alignItems: 'center', gap: 5, background: 'var(--purple-light)', color: 'var(--purple)', borderRadius: 6, padding: '3px 10px', fontSize: 11, fontWeight: 600 }}>
                                🎯 {current.concept}
                            </div>
                        )}

                        <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.7, color: 'var(--text)', marginBottom: 16, padding: '12px 14px', background: 'var(--surface)', borderRadius: 10, border: '1px solid var(--border)' }}>
                            <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}>{current.question}</ReactMarkdown>
                        </div>

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
