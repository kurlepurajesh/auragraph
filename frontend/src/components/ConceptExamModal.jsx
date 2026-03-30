import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { X, Loader2, CheckCircle2, AlertTriangle, Target, BookOpen, Brain, Trophy, TrendingUp, Dumbbell, Zap, RotateCcw, XCircle } from 'lucide-react';
import { API, authHeaders } from './utils';

export default function ConceptExamModal({ nodes, notebookId, onClose, onQuizCompleted, onAttemptSaved = null, onNavigateToConcept = null }) {
    const conceptOptions = React.useMemo(
        () => (nodes || [])
            .filter(n => (n?.label || '').trim())
            .map(n => ({
                label: (n?.label || '').trim(),
                full_label: (n?.full_label || n?.label || '').trim(),
                status: n?.status || 'learning',
            }))
            .filter((item, index, self) => self.findIndex(i => i.label === item.label) === index),
        [nodes],
    );

    const getStatusIcon = (status) => {
        switch (status) {
            case 'mastered': return <CheckCircle2 size={16} color="#16A34A" />;
            case 'struggling': return <AlertTriangle size={16} color="#D97706" />;
            case 'focused': return <Target size={16} color="var(--ag-purple)" />;
            default: return <BookOpen size={16} color="var(--text2)" />;
        }
    };

    const [selectedConcept, setSelectedConcept] = React.useState('');
    const [selectedConceptFullLabel, setSelectedConceptFullLabel] = React.useState('');
    const [started, setStarted] = React.useState(false);
    const [questions, setQuestions] = React.useState([]);
    const [loading, setLoading] = React.useState(false);
    const [qIdx, setQIdx] = React.useState(0);
    const [selected, setSelected] = React.useState(null);
    const [revealed, setRevealed] = React.useState(false);
    const [score, setScore] = React.useState(0);
    const [done, setDone] = React.useState(false);
    const [responses, setResponses] = React.useState([]);
    const rewardsSent = React.useRef(false);
    const persistedRef = React.useRef(false);

    const startConceptQuiz = async () => {
        if (!selectedConcept) return;
        setStarted(true);
        setLoading(true);
        try {
            const res = await fetch(`${API}/api/concept-exam`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...authHeaders() },
                body: JSON.stringify({
                    concept_name: selectedConcept,
                    ...(notebookId ? { notebook_id: notebookId } : {}),
                }),
            });
            const data = await res.json().catch(() => ({}));
            setQuestions(Array.isArray(data?.questions) ? data.questions : []);
        } catch {
            setQuestions([]);
        } finally {
            setLoading(false);
        }
    };

    const current = questions[qIdx];
    const total = questions.length;

    const handleSelect = (opt) => {
        if (revealed || !current) return;
        const isCorrect = opt === current.correct;
        setSelected(opt);
        setRevealed(true);
        setResponses(prev => ([...prev, {
            question_index: qIdx,
            selected: opt,
            correct: current?.correct || '',
            is_correct: isCorrect,
            concept: current?.concept || selectedConcept || '',
        }]));
        if (isCorrect) setScore(s => s + 1);
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
    }, [loading, done, current, revealed]);

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

        const conceptsTested = [{ label: selectedConcept || 'Concept', status: 'focused' }];

        fetch(`${API}/api/notebooks/${notebookId}/quizzes/complete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
                quiz_type: 'concept',
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
                        quiz_type: 'concept',
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
    }, [done, loading, total, notebookId, questions, responses, score, selectedConcept, onAttemptSaved]);

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()} style={{ maxWidth: 560, width: '96vw', maxHeight: '90vh', overflowY: 'auto' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <Brain size={22} color="var(--ag-purple)" />
                        <div>
                            <h3 style={{ marginBottom: 1 }}>Concept-wise Quiz</h3>
                            <p style={{ fontSize: 11, color: 'var(--text3)' }}>Choose one concept and attempt 5 focused questions</p>
                        </div>
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={18} /></button>
                </div>

                {!started && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        <div style={{ fontSize: 13, color: 'var(--text2)' }}>Select a concept by status:</div>
                        <div style={{ display: 'grid', gap: 8, maxHeight: 300, overflowY: 'auto' }}>
                            {conceptOptions.map(concept => (
                                <button
                                    key={concept.label}
                                    onClick={() => {
                                        setSelectedConcept(concept.label);
                                        setSelectedConceptFullLabel(concept.full_label);
                                    }}
                                    style={{
                                        border: selectedConcept === concept.label ? '2px solid var(--ag-purple)' : '1px solid var(--border)',
                                        borderRadius: 10,
                                        padding: '12px',
                                        background: selectedConcept === concept.label ? 'var(--ag-purple-bg)' : 'var(--surface)',
                                        color: 'var(--text)',
                                        cursor: 'pointer',
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 10,
                                        fontSize: 13,
                                        fontWeight: selectedConcept === concept.label ? 600 : 500,
                                        transition: 'all 0.2s',
                                    }}
                                >
                                    <span style={{ width: 18, height: 18, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>{getStatusIcon(concept.status)}</span>
                                    <div style={{ flex: 1, textAlign: 'left' }}>
                                        <div>{concept.label}</div>
                                        <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 2, textTransform: 'capitalize' }}>
                                            Status: {concept.status}
                                        </div>
                                    </div>
                                </button>
                            ))}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text3)' }}>This quiz always has 5 questions for the selected concept.</div>
                        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                            <button className="btn btn-primary" disabled={!selectedConcept} onClick={startConceptQuiz}>Start Concept Quiz</button>
                        </div>
                    </div>
                )}

                {started && loading && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '30px 0', justifyContent: 'center', color: 'var(--text3)', fontSize: 13 }}>
                        <Loader2 className="spin" size={18} /> Generating concept quiz...
                    </div>
                )}

                {started && !loading && done && (
                    <div style={{ textAlign: 'center', padding: '20px 0' }}>
                        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}>
                            {pct >= 70 ? <Trophy size={44} color="#EAB308" /> : pct >= 40 ? <TrendingUp size={44} color="#F59E0B" /> : <Dumbbell size={44} color="#A855F7" />}
                        </div>
                        <div style={{ fontSize: 22, fontWeight: 800, marginBottom: 6 }}>{score}/{total} correct</div>
                        <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 10 }}>Score: {pct}%</div>
                        {xpEarned > 0 && (
                            <div style={{ fontSize: 12, color: 'var(--ag-purple)', fontWeight: 700, marginBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                <Zap size={14} /> +{xpEarned} Aura XP earned!{pct >= 80 ? ' (includes accuracy bonus)' : ''}
                                {pct >= 80 && <Target size={13} />}
                            </div>
                        )}
                        <div style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 20, minHeight: 40 }}>
                            {pct >= 75
                                ? 'You rocked it! Excellent concept clarity.'
                                : pct >= 40 
                                ? 'Nice progress — revise weak sub-parts.' 
                                : "Let's spend some more time on this concept."}
                        </div>
                        <div className="progress-bar-track" style={{ marginBottom: 20 }}>
                            <div className="progress-bar-fill" style={{ width: `${pct}%`, background: pct >= 70 ? 'linear-gradient(90deg,#10B981,#34D399)' : pct >= 40 ? 'linear-gradient(90deg,#F59E0B,#FCD34D)' : 'linear-gradient(90deg,#EF4444,#FCA5A5)' }} />
                        </div>
                        {pct < 70 && (
                            <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexDirection: 'column' }}>
                                <button 
                                    className="btn btn-primary" 
                                    onClick={() => {
                                        setStarted(false);
                                        setQIdx(0);
                                        setSelected(null);
                                        setRevealed(false);
                                        setScore(0);
                                        setDone(false);
                                        setResponses([]);
                                        setQuestions([]);
                                        setSelectedConceptFullLabel('');
                                    }}
                                >
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><RotateCcw size={14} /> Retry This Concept</span>
                                </button>
                                <button
                                    className="btn btn-primary"
                                    onClick={() => {
                                        if (onNavigateToConcept) {
                                            onNavigateToConcept(selectedConceptFullLabel || selectedConcept);
                                        }
                                        onClose();
                                    }}
                                    style={{ minWidth: 200 }}
                                >
                                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><BookOpen size={14} /> Go To This Concept</span>
                                </button>
                            </div>
                        )}
                        <div style={{ display: 'flex', gap: 10, flexDirection: 'column', alignItems: 'center' }}>
                            <button 
                                className="btn btn-primary" 
                                onClick={onClose}
                                style={{ minWidth: 120, background: 'var(--surface)', color: 'var(--text2)', border: '1px solid var(--border)' }}
                            >
                                {pct >= 75 ? 'Done' : 'Back'}
                            </button>
                        </div>
                    </div>
                )}

                {started && !loading && !done && total === 0 && (
                    <div style={{ textAlign: 'center', padding: '30px 0' }}>
                        <div style={{ marginBottom: 12, display: 'flex', justifyContent: 'center' }}><AlertTriangle size={44} color="#F59E0B" /></div>
                        <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 6, color: 'var(--text)' }}>Could not generate concept quiz</div>
                        <div style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 20 }}>Please try a different concept or retry later.</div>
                        <button className="btn btn-primary" onClick={onClose}>Close</button>
                    </div>
                )}

                {started && !loading && !done && current && (
                    <>
                        <div style={{ marginBottom: 14 }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text3)', marginBottom: 5, fontWeight: 600 }}>
                                <span>Question {qIdx + 1} of {total}</span>
                                <span style={{ color: 'var(--ag-emerald)' }}>Score: {score}</span>
                            </div>
                            <div className="progress-bar-track">
                                <div className="progress-bar-fill" style={{ width: `${((qIdx) / total) * 100}%`, background: 'linear-gradient(90deg,var(--ag-purple-vivid),var(--ag-purple))' }} />
                            </div>
                        </div>

                        <div style={{ marginBottom: 10, display: 'inline-flex', alignItems: 'center', gap: 5, background: 'var(--purple-light)', color: 'var(--purple)', borderRadius: 6, padding: '3px 10px', fontSize: 11, fontWeight: 600 }}>
                            <Brain size={13} /> {current.concept || selectedConcept}
                        </div>

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
