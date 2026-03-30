import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { ArrowLeft } from 'lucide-react';

export default function QuizAttemptReviewPage({ run, onBack }) {
    if (!run) return null;

    const questions = Array.isArray(run.questions) ? run.questions : [];
    const responses = Array.isArray(run.responses) ? run.responses : [];
    const responseByIndex = new Map();
    responses.forEach(r => {
        const idx = Number(r?.question_index);
        if (Number.isFinite(idx)) responseByIndex.set(idx, r);
    });

    const total = run.total_questions || questions.length || 0;
    const score = run.correct_answers || run.score || 0;
    const pct = total ? Math.round((score / total) * 100) : 0;

    return (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                    <div style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)' }}>{(run.quiz_type || 'quiz').toUpperCase()} Attempt Review</div>
                    <div style={{ fontSize: 12, color: 'var(--text3)' }}>
                        {new Date(run.completed_at || run.created_at || Date.now()).toLocaleString()} · {score}/{total} ({pct}%)
                    </div>
                </div>
                <button onClick={onBack} style={{ border: 'none', background: 'none', color: 'var(--text2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                    <ArrowLeft size={18} /> Back To History
                </button>
            </div>

            <div style={{ maxHeight: '60vh', overflowY: 'auto', padding: 10, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {questions.map((q, idx) => {
                    const r = responseByIndex.get(idx);
                    const selected = r?.selected || null;
                    const correct = q?.correct || '';
                    return (
                        <div key={idx} style={{ borderBottom: '1px solid var(--border)', paddingBottom: 14 }}>
                            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 8 }}>Q{idx + 1}.</div>
                            <div style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.6, marginBottom: 10 }}>
                                <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}>{q?.question || ''}</ReactMarkdown>
                            </div>

                            <div style={{ display: 'grid', gap: 8 }}>
                                {['A', 'B', 'C', 'D'].map(opt => {
                                    const activeCorrect = opt === correct;
                                    const activeWrong = selected === opt && selected !== correct;
                                    return (
                                        <div key={opt} style={{ borderRadius: 10, border: `1px solid ${activeCorrect ? '#86EFAC' : activeWrong ? '#FCA5A5' : 'var(--border)'}`, background: activeCorrect ? '#DCFCE7' : activeWrong ? '#FEF2F2' : 'var(--bg)', padding: '10px 12px', fontSize: 14, color: activeCorrect ? '#166534' : activeWrong ? '#991B1B' : 'var(--text2)', display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <span style={{ fontWeight: 700, minWidth: 32 }}>{opt})</span>
                                            <span style={{ flex: 1 }}><ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}>{q?.options?.[opt] || ''}</ReactMarkdown></span>
                                            {activeCorrect && <span style={{ color: '#166534', fontWeight: 700, fontSize: 12 }}>Correct</span>}
                                        </div>
                                    );
                                })}
                            </div>

                            <div style={{ marginTop: 6, fontSize: 13, color: 'var(--text3)' }}>
                                Your answer: <b>{selected || '-'}</b> · Correct: <b>{correct || '-'}</b>
                            </div>

                            {q?.explanation ? (
                                <div style={{ marginTop: 8, fontSize: 13, color: 'var(--text2)' }}>
                                    <strong>Explanation:</strong>{' '}
                                    <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}>{q.explanation}</ReactMarkdown>
                                </div>
                            ) : null}
                        </div>
                    );
                })}
                {questions.length === 0 && (
                    <div style={{ fontSize: 13, color: 'var(--text3)', textAlign: 'center', padding: '24px 0' }}>
                        No question data found for this attempt.
                    </div>
                )}
            </div>
        </div>
    );
}
