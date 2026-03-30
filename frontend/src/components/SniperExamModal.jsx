import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { X, Loader2, Crosshair, CheckCircle2, Trophy, TrendingUp, Dumbbell, XCircle, Zap, Target } from 'lucide-react';
import { API, authHeaders } from './utils';

export default function SniperExamModal({ nodes, notebookId, onClose, onQuizCompleted, onAttemptSaved = null }) {
    const redNodes = nodes.filter(n => n.status === 'struggling');
    const [questions, setQuestions] = React.useState([]);
    const [loading, setLoading] = React.useState(true);
    const [qIdx, setQIdx] = React.useState(0);
    const [selected, setSelected] = React.useState(null);
    const [revealed, setRevealed] = React.useState(false);
    const [score, setScore] = React.useState(0);
    const [done, setDone] = React.useState(false);
    const [responses, setResponses] = React.useState([]);
    const rewardsSent = React.useRef(false);
    const persistedRef = React.useRef(false);

    React.useEffect(() => {
        (async () => {
            try {
                const res = await fetch(`${API}/api/sniper-exam`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', ...authHeaders() },
                    body: JSON.stringify({
                        weak_concepts: redNodes.map(n => n.label),
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
        const isCorrect = opt === current.correct;
        setResponses(prev => ([...prev, {
            question_index: qIdx,
            selected: opt,
            correct: current?.correct || '',
            is_correct: isCorrect,
            concept: current?.concept || '',
        }]));
        if (isCorrect) setScore(s => s + 1);
        // Track answer in behaviour store (fire-and-forget)
        if (notebookId) {
            fetch('/api/behaviour/track-quiz', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${localStorage.getItem('ag_token') || ''}` },
                body: JSON.stringify({
                    notebook_id: notebookId,
                    concept: current.concept || '',
                    question: current.question?.slice(0, 200) || '',
                    correct: isCorrect,
                }),
            }).catch(() => {});
        }
    };

    const next = () => {
        if (qIdx + 1 >= total) { setDone(true); return; }
        setQIdx(i => i + 1);
        setSelected(null);
        setRevealed(false);
    };

    React.useEffect(() => {
        if (loading || done || !current) return;

        const onKeyDown = (e) => {
            const target = e.target;
            if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;

            const key = typeof e.key === 'string' ? e.key.toLowerCase() : '';
            const code = e.code || '';
            const optionByKey = {
                '1': 'A',
                '2': 'B',
                '3': 'C',
                '4': 'D',
                a: 'A',
                b: 'B',
                c: 'C',
                d: 'D',
            };
            const fromCode = {
                Digit1: 'A',
                Numpad1: 'A',
                Digit2: 'B',
                Numpad2: 'B',
                Digit3: 'C',
                Numpad3: 'C',
                Digit4: 'D',
                Numpad4: 'D',
            };

            const picked = optionByKey[key] || fromCode[code] || null;
            if (picked && !revealed) {
                e.preventDefault();
                handleSelect(picked);
                return;
            }

            if (e.key === 'Enter' && revealed) {
                e.preventDefault();
                next();
            }
        };

        window.addEventListener('keydown', onKeyDown);
        return () => window.removeEventListener('keydown', onKeyDown);
    }, [loading, done, current, revealed, handleSelect, next]);

    const pct = total > 0 ? Math.round((score / total) * 100) : 0;

    const [xpEarned, setXpEarned] = React.useState(0);
    React.useEffect(() => {
        if (!done || loading || rewardsSent.current || total <= 0) return;
        rewardsSent.current = true;
        const gained = onQuizCompleted?.(score, total);
        if (gained > 0) setXpEarned(gained);
    }, [done, loading, score, total, onQuizCompleted]);

    React.useEffect(() => {
        if (!done || loading || total <= 0 || persistedRef.current || !notebookId) return;
        persistedRef.current = true;

        const conceptsTested = redNodes.map(n => ({ label: n.label, status: n.status || 'struggling' }));

        fetch(`${API}/api/notebooks/${notebookId}/quizzes/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
                quiz_type: 'sniper',
                questions,
                concepts_tested: conceptsTested,
                responses,
                score,
                correct_answers: score,
                total_questions: total,
            }),
        })
            .then(res => res.json().catch(() => ({})))
            .then(data => {
                if (data?.run_id) {
                    onAttemptSaved?.({
                        id: data.run_id,
                        quiz_type: 'sniper',
                        score,
                        correct_answers: score,
                        total_questions: total,
                        questions,
                        concepts_tested: conceptsTested,
                        responses,
                        created_at: new Date().toISOString(),
                        completed_at: new Date().toISOString(),
                    });
                }
            })
            .catch(() => { });
    }, [done, loading, total, notebookId, questions, responses, score, redNodes, onAttemptSaved]);

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()} style={{ maxWidth: 560, width: '96vw', maxHeight: '90vh', overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Crosshair size={22} color="var(--ag-purple)" />
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
                    <DoneScreen score={score} total={total} pct={pct}
                        xpEarned={xpEarned}
                        onClose={onClose}
                    />
                )}

                {!loading && !done && total === 0 && (
                    <div style={{ textAlign: 'center', padding: '30px 0' }}>
                        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}><CheckCircle2 size={44} color="#16A34A" /></div>
                        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: 'var(--text)' }}>No red-zone topics!</div>
                        <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 20 }}>All your concepts are on track. Keep it up!</div>
                        <button className="btn btn-primary" onClick={onClose}>Nice!</button>
                    </div>
                )}

                {!loading && !done && current && (
                    <>
                        <div style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text3)', marginBottom: 5, fontWeight: 600 }}>
                                <span>Question {qIdx + 1} of {total}</span>
                                <span style={{ color: 'var(--ag-emerald)' }}>Score: {score}</span>
                            </div>
                            <div className="progress-bar-track">
                                <div className="progress-bar-fill" style={{ width: `${((qIdx) / total) * 100}%`, background: 'linear-gradient(90deg,var(--ag-purple),var(--ag-purple-vivid))' }} />
                            </div>
                        </div>

                        {current.concept && (
                            <div style={{ marginBottom: 10, display: 'inline-flex', alignItems: 'center', gap: 5, background: 'var(--purple-light)', color: 'var(--purple)', borderRadius: 6, padding: '3px 10px', fontSize: 11, fontWeight: 600 }}>
                                <Crosshair size={13} /> {current.concept}
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
                                    <span style={{ flex: 1 }}><ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}>{current.options?.[opt] || ''}</ReactMarkdown></span>
                                    {revealed && opt === current.correct && <CheckCircle2 size={16} color="#16A34A" style={{ flexShrink: 0 }} />}
                                    {revealed && opt === selected && opt !== current.correct && <XCircle size={16} color="#DC2626" style={{ flexShrink: 0 }} />}
                                </button>
                            ))}
                        </div>

                        <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: -6, marginBottom: 12 }}>
                            Keyboard: 1-4 or A-D to answer, Enter for next question.
                        </div>

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

// ── DoneScreen — separate component so useEffect runs correctly ───────────────
function DoneScreen({ score, total, pct, xpEarned, onClose }) {
    const performanceBand = pct >= 75 ? 'good' : pct >= 40 ? 'mid' : 'bad';
    const sniperFeedback = {
        good: {
            headline: 'You rocked it in your weak areas!',
            message: 'Great recovery. You are turning struggling concepts into strengths.',
        },
        mid: {
            headline: 'Good recovery!',
            message: 'You are improving the weak concepts. One more focused round can push this higher.',
        },
        bad: {
            headline: 'Keep targeting these concepts.',
            message: 'Spend more time on these topics using Study Hub and concept practice, then retry Sniper Test.',
        },
    }[performanceBand];

    return (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}>
                {pct >= 70 ? <Trophy size={44} color="#EAB308" /> : pct >= 40 ? <TrendingUp size={44} color="#F59E0B" /> : <Dumbbell size={44} color="#A855F7" />}
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>{score}/{total} correct</div>
            <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 8 }}>Score: {pct}%</div>
            <div style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 8 }}>
                <div style={{ fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>{sniperFeedback.headline}</div>
                <div>{sniperFeedback.message}</div>
            </div>
            {xpEarned > 0 && (
                <div style={{ fontSize: 12, color: 'var(--ag-purple)', fontWeight: 700, marginBottom: 16, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                    <Zap size={14} /> +{xpEarned} Aura XP earned!{pct >= 80 ? ' (includes accuracy bonus)' : ''}
                    {pct >= 80 && <Target size={13} />}
                </div>
            )}
            <div className="progress-bar-track" style={{ marginBottom: 20 }}>
                <div className="progress-bar-fill" style={{ width: `${pct}%`, background: pct >= 70 ? 'linear-gradient(90deg,#10B981,#34D399)' : pct >= 40 ? 'linear-gradient(90deg,#F59E0B,#FCD34D)' : 'linear-gradient(90deg,#EF4444,#FCA5A5)' }} />
            </div>
            <button className="btn btn-primary" onClick={onClose}>Done</button>
        </div>
    );
}
