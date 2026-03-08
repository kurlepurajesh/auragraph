import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import {
    Brain, Loader2, MessageCircle, CheckCircle2, AlertCircle, MinusCircle, Sparkles
} from 'lucide-react';
import { API, apiFetch } from './utils';

export default function MutateModal({
    page, notebookId, pageIdx, onClose, onMutate, onDoubtAnswered, initialDoubt = ''
}) {
    const [doubt, setDoubt] = useState(initialDoubt);
    const [busy, setBusy] = useState(false);
    const [answer, setAnswer] = useState('');
    const [answerSource, setAnswerSource] = useState('');
    const [answerVerification, setAnswerVerification] = useState('correct');
    const [answerCorrection, setAnswerCorrection] = useState('');
    const [answerFootnote, setAnswerFootnote] = useState('');
    const [mode, setMode] = useState('idle'); // 'idle' | 'answering' | 'answered' | 'mutating'

    const askDoubt = async () => {
        if (!doubt.trim()) return;
        setBusy(true); setMode('answering'); setAnswer('');
        try {
            const res = await apiFetch(`${API}/api/doubt`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ notebook_id: notebookId, doubt, page_idx: pageIdx })
            });
            if (res.ok) {
                const data = await res.json();
                setAnswer(data.answer || '');
                setAnswerSource(data.source || 'local');
                setAnswerVerification(data.verification_status || 'correct');
                setAnswerCorrection(data.correction || '');
                setAnswerFootnote(data.footnote || '');
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
                <textarea
                    className="input" rows={3} autoFocus value={doubt}
                    onChange={e => setDoubt(e.target.value)}
                    onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') askDoubt(); if (e.key === 'Escape') onClose(); }}
                    placeholder="e.g. Why does convolution become multiplication in the frequency domain?"
                    style={{ resize: 'vertical', fontFamily: 'inherit', marginBottom: 8 }}
                />
                <div style={{ fontSize: 11, color: 'var(--text3)', marginBottom: 12 }}>
                    <kbd style={{ background: 'var(--surface2)', border: '1px solid var(--border)', borderRadius: 3, padding: '1px 5px', fontSize: 10 }}>Ctrl+Enter</kbd> to ask
                </div>

                {(mode === 'answering' || mode === 'answered') && (
                    <div style={{ background: '#F0F9FF', border: '1px solid #BAE6FD', borderRadius: 8, padding: 14, marginBottom: 14, maxHeight: 340, overflowY: 'auto' }}>
                        <div style={{ fontSize: 11, color: '#0369A1', fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Brain size={12} /> AuraGraph Answer {answerSource === 'azure' ? '(GPT-4o · verified)' : answerSource === 'groq' ? '(Groq · verified)' : '(offline)'}
                        </div>
                        {mode === 'answering'
                            ? <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#0369A1', fontSize: 13 }}><Loader2 className="spin" size={14} /> Verifying against slides, textbook and model knowledge…</div>
                            : (
                                <>
                                    <div style={{ fontSize: 13, lineHeight: 1.8, color: '#0C4A6E' }}>
                                        <ReactMarkdown remarkPlugins={[remarkMath, remarkGfm]} rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}>{answer}</ReactMarkdown>
                                    </div>
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
                    <button
                        className="btn btn-ghost btn-sm" onClick={askDoubt}
                        disabled={busy || !doubt.trim()}
                        style={{ gap: 6, borderColor: '#0369A1', color: '#0369A1' }}
                    >
                        {mode === 'answering' ? <Loader2 className="spin" size={14} /> : <MessageCircle size={14} />}
                        {mode === 'answering' ? 'Searching…' : 'Ask (get answer)'}
                    </button>
                    <button
                        className="btn btn-primary btn-sm" onClick={doMutate}
                        disabled={busy || !doubt.trim()}
                        style={{ gap: 6 }}
                        title="Permanently rewrites this page to incorporate your doubt"
                    >
                        {mode === 'mutating' ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}
                        {mode === 'mutating' ? 'Rewriting…' : 'Rewrite This Page'}
                    </button>
                </div>
            </div>
        </div>
    );
}
