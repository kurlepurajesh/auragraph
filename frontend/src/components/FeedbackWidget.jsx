/**
 * FeedbackWidget — floating AI-assistant-style feedback bubble.
 * Two modes:
 *   'dashboard'  — detailed multi-section form (notes quality, quizzes, doubts, mutation, UI)
 *   'notebook'   — brief single issue report pinned to a specific notebook
 */
import React, { useState, useRef, useEffect } from 'react';
import { MessageCircle, X, Star, Send, Loader2, Compass } from 'lucide-react';
import { API, authHeaders, parseApiError } from './utils';

const CATEGORIES = [
    { key: 'notes',    label: '📖 Notes quality',       placeholder: 'e.g. Notes were too long, missing diagrams...' },
    { key: 'questions',label: '📝 Quiz questions',       placeholder: 'e.g. Options were confusing, wrong difficulty...' },
    { key: 'doubts',   label: '💬 Doubt answers',        placeholder: 'e.g. Doubt answer was unclear, too short, or missed my exact question...' },
    { key: 'mutation', label: '⚡ Note mutation',         placeholder: 'e.g. Mutation rewrote too much, changed meaning, or skipped key steps...' },
    { key: 'ui',       label: '🎨 App UI/UX',            placeholder: 'e.g. Hard to find a feature, slow loading...' },
    { key: 'general',  label: '💬 General',              placeholder: 'Anything else on your mind...' },
];

const HELP_CHAT_SESSION_KEY = 'aura_nav_help_chat';
const NAV_HELP_DESCRIPTION = [
    'AuraGraph verified navigation context:',
    '- Dashboard: New Notebook, open notebook cards, grouped courses, profile/tour, stats cards, feedback/help widget.',
    '- Notebook top actions: Quiz Center (Ctrl+Shift+Q), Ask a Doubt (Ctrl+D), Quick Review, Version History, Aura panel, Study Hub toggle.',
    '- Reading tools: view mode (single/two/scroll), font size A- / A+, search in notes (Ctrl+F), copy/download/print.',
    '- Page navigation: previous/next buttons and page number jump.',
    '- Study Hub / Knowledge panel: concept mastery, jump to concept, practice questions by difficulty.',
    '- Quiz Center: General Test (10), Sniper Test (5 weak concepts), Concept Quiz (5 selected concept), history/review tabs.',
    '- Annotation tools: Highlight, Sticky Note, Draw, Eraser; highlight flow is select text then confirm Highlight in popup.',
    '- Annotation storage: Auto-save, Save now, Clear all.',
    '- Notebook actions: regenerate section, edit current page, translate page, TTS/read-aloud.',
    '- Shortcuts include Ctrl+Shift+Q, Ctrl+D, Ctrl+F, Ctrl+Enter, Esc and arrow/page keys for navigation.',
    '- Floating widget supports both Navigation Help Chat and Feedback.',
].join('\n');

function loadHelpChatHistory() {
    try {
        const raw = sessionStorage.getItem(HELP_CHAT_SESSION_KEY);
        if (!raw) return [];
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

function saveHelpChatHistory(messages) {
    try {
        sessionStorage.setItem(HELP_CHAT_SESSION_KEY, JSON.stringify(messages.slice(-30)));
    } catch { }
}

function NavigationHelpChat() {
    const starter = {
        role: 'assistant',
        content: 'Hi! I can help you navigate AuraGraph. Ask things like: "How do I ask a doubt?" or "How do I mutate a page?"',
    };

    const [messages, setMessages] = useState(() => {
        const existing = loadHelpChatHistory();
        return existing.length ? existing : [starter];
    });
    const [query, setQuery] = useState('');
    const [sending, setSending] = useState(false);

    useEffect(() => {
        saveHelpChatHistory(messages);
    }, [messages]);

    const ask = async () => {
        const q = query.trim();
        if (!q || sending) return;

        const next = [...messages, { role: 'user', content: q }];
        setMessages(next);
        setQuery('');
        setSending(true);

        try {
            const res = await fetch(`${API}/api/navigation-help-chat`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    query: q,
                    history: next.slice(-8).map(m => ({ role: m.role, content: m.content })),
                    context: `Route: ${window.location.pathname}\nMode: Navigation help chat`,
                    description: NAV_HELP_DESCRIPTION,
                }),
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok) {
                throw new Error(parseApiError(data?.detail, 'Navigation helper is unavailable right now.'));
            }
            const answer = (data?.answer || '').trim() || 'I can help with navigation. Try asking how to use doubts, mutate, quick review, or feedback.';
            setMessages(prev => [...prev, { role: 'assistant', content: answer }]);
        } catch (err) {
            setMessages(prev => [...prev, {
                role: 'assistant',
                content: err?.message || 'Navigation helper is unavailable right now. Please try again in a moment.',
            }]);
        } finally {
            setSending(false);
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ border: '1px solid var(--border)', borderRadius: 16, background: 'var(--surface)', padding: 12, maxHeight: 300, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12 }}>
                {messages.map((m, idx) => (
                    <div key={idx} style={{ display: 'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start' }}>
                        <div style={{ maxWidth: '90%', borderRadius: m.role === 'user' ? '16px 16px 8px 16px' : '16px 16px 16px 8px', padding: '10px 13px', fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap', background: m.role === 'user' ? 'var(--ag-primary)' : 'var(--bg)', color: m.role === 'user' ? '#fff' : 'var(--text)', border: m.role === 'user' ? 'none' : '1px solid var(--border)', boxShadow: m.role === 'user' ? '0 8px 18px rgba(79,70,229,0.30)' : '0 2px 8px rgba(15,23,42,0.08)' }}>
                            {m.content}
                        </div>
                    </div>
                ))}
                {sending && (
                    <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                        <div style={{ borderRadius: '16px 16px 16px 8px', padding: '10px 13px', fontSize: 13, background: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text2)', display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Loader2 size={12} className="spin" /> Thinking...
                        </div>
                    </div>
                )}
            </div>

            <textarea
                rows={2}
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        ask();
                    }
                }}
                placeholder="Ask about navigation... (e.g. How do I ask a doubt?)"
                maxLength={600}
                style={{ width: '100%', fontSize: 13, lineHeight: 1.5, padding: '11px 13px', borderRadius: 12, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', resize: 'none', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box', boxShadow: 'inset 0 1px 3px rgba(15,23,42,0.06)' }}
            />

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--text3)', letterSpacing: '0.01em' }}>Press Enter to send</span>
                <button
                    type="button"
                    onClick={ask}
                    disabled={sending || !query.trim()}
                    style={{ padding: '9px 16px', borderRadius: 12, border: 'none', background: 'linear-gradient(135deg, #111827 0%, #1F2937 55%, #312E81 100%)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, opacity: !query.trim() ? 0.5 : 1, boxShadow: '0 8px 20px rgba(15,23,42,0.25)' }}
                >
                    <Send size={14} /> Ask
                </button>
            </div>
        </div>
    );
}

function StarRating({ value, onChange, label }) {
    const [hover, setHover] = useState(0);
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 12, color: 'var(--text2)', fontWeight: 600, minWidth: 80 }}>{label}</span>
            <div style={{ display: 'flex', gap: 3 }}>
                {[1,2,3,4,5].map(n => (
                    <button
                        key={n}
                        type="button"
                        onMouseEnter={() => setHover(n)}
                        onMouseLeave={() => setHover(0)}
                        onClick={() => onChange(n)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: n <= (hover || value) ? '#F59E0B' : 'var(--border2)', transition: 'color 0.1s' }}
                    >
                        <Star size={18} fill={n <= (hover || value) ? '#F59E0B' : 'none'} />
                    </button>
                ))}
            </div>
            {value > 0 && <span style={{ fontSize: 11, color: 'var(--text3)' }}>{['','Poor','Fair','Good','Great','Excellent'][value]}</span>}
        </div>
    );
}

// ── Detailed Dashboard Feedback ────────────────────────────────────────────────
function DetailedFeedbackForm({ notebookId, onDone }) {
    const [rating, setRating] = useState(0);
    const [category, setCategory] = useState('general');
    const [liked, setLiked] = useState('');
    const [disliked, setDisliked] = useState('');
    const [message, setMessage] = useState('');
    const [submitting, setSubmitting] = useState(false);
    const cat = CATEGORIES.find(c => c.key === category) || CATEGORIES.find(c => c.key === 'general') || CATEGORIES[0];

    const submit = async () => {
        if (!message.trim() && !liked.trim() && !disliked.trim()) return;
        setSubmitting(true);
        try {
            await fetch(`${API}/api/feedback`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    context: notebookId ? 'notebook' : 'dashboard',
                    notebook_id: notebookId || null,
                    rating,
                    liked,
                    disliked,
                    category,
                    message,
                    page_url: window.location.pathname,
                }),
            });
        } catch { /* offline — silently ignore */ }
        setSubmitting(false);
        onDone();
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            <StarRating value={rating} onChange={setRating} label="Overall" />

            {/* Category selector */}
            <div style={{ marginBottom: 12 }}>
                <label style={{ fontSize: 11, fontWeight: 700, color: 'var(--text3)', textTransform: 'uppercase', letterSpacing: '0.06em', display: 'block', marginBottom: 6 }}>What are you reviewing?</label>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {CATEGORIES.map(c => (
                        <button key={c.key} type="button" onClick={() => setCategory(c.key)}
                            style={{ padding: '4px 10px', borderRadius: 20, border: `1px solid ${category === c.key ? 'var(--ag-purple)' : 'var(--border)'}`, background: category === c.key ? 'var(--ag-purple-bg)' : 'var(--surface)', color: category === c.key ? 'var(--ag-purple)' : 'var(--text2)', fontSize: 11, fontWeight: 600, cursor: 'pointer', transition: 'all 0.12s' }}>
                            {c.label}
                        </button>
                    ))}
                </div>
            </div>

            <div style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text2)', display: 'block', marginBottom: 5 }}>What worked well?</label>
                <textarea
                    rows={2}
                    value={liked}
                    onChange={e => setLiked(e.target.value)}
                    placeholder="What did you like?"
                    maxLength={500}
                    style={{ width: '100%', fontSize: 12, lineHeight: 1.5, padding: '9px 11px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', resize: 'none', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box', boxShadow: 'inset 0 1px 2px rgba(15,23,42,0.05)' }}
                />
            </div>

            <div style={{ marginBottom: 10 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text2)', display: 'block', marginBottom: 5 }}>What could be better?</label>
                <textarea
                    rows={2}
                    value={disliked}
                    onChange={e => setDisliked(e.target.value)}
                    placeholder="What frustrated you or didn't work?"
                    maxLength={500}
                    style={{ width: '100%', fontSize: 12, lineHeight: 1.5, padding: '9px 11px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', resize: 'none', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box', boxShadow: 'inset 0 1px 2px rgba(15,23,42,0.05)' }}
                />
            </div>

            <div style={{ marginBottom: 14 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: 'var(--text2)', display: 'block', marginBottom: 5 }}>💬 Anything else?</label>
                <textarea
                    rows={2}
                    value={message}
                    onChange={e => setMessage(e.target.value)}
                    placeholder={cat.placeholder}
                    maxLength={1000}
                    style={{ width: '100%', fontSize: 12, lineHeight: 1.5, padding: '9px 11px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', resize: 'none', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box', boxShadow: 'inset 0 1px 2px rgba(15,23,42,0.05)' }}
                />
            </div>

            <button
                type="button"
                onClick={submit}
                disabled={submitting || (!message.trim() && !liked.trim() && !disliked.trim())}
                style={{ width: '100%', padding: '10px', borderRadius: 12, border: 'none', background: 'linear-gradient(135deg, #111827 0%, #1F2937 55%, #312E81 100%)', color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, opacity: (!message.trim() && !liked.trim() && !disliked.trim()) ? 0.5 : 1, transition: 'opacity 0.15s', boxShadow: '0 8px 18px rgba(15,23,42,0.22)' }}
            >
                {submitting ? <Loader2 className="spin" size={14} /> : <Send size={14} />}
                {submitting ? 'Sending…' : 'Send Feedback'}
            </button>
        </div>
    );
}

// ── Brief Notebook Feedback ────────────────────────────────────────────────────
function BriefFeedbackForm({ notebookId, onDone }) {
    const [category, setCategory] = useState('notes');
    const [message, setMessage] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const submit = async () => {
        if (!message.trim()) return;
        setSubmitting(true);
        try {
            await fetch(`${API}/api/feedback`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    context: 'notebook',
                    notebook_id: notebookId,
                    category,
                    message,
                    page_url: window.location.pathname,
                }),
            });
        } catch { }
        setSubmitting(false);
        onDone();
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {CATEGORIES.filter(c => c.key !== 'general').map(c => (
                    <button key={c.key} type="button" onClick={() => setCategory(c.key)}
                        style={{ padding: '3px 9px', borderRadius: 20, border: `1px solid ${category === c.key ? 'var(--ag-purple)' : 'var(--border)'}`, background: category === c.key ? 'var(--ag-purple-bg)' : 'var(--surface)', color: category === c.key ? 'var(--ag-purple)' : 'var(--text2)', fontSize: 10, fontWeight: 600, cursor: 'pointer' }}>
                        {c.label}
                    </button>
                ))}
            </div>
            <textarea
                autoFocus
                rows={3}
                value={message}
                onChange={e => setMessage(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) submit(); }}
                placeholder="Briefly describe the issue you faced…"
                maxLength={500}
                style={{ width: '100%', fontSize: 12, lineHeight: 1.5, padding: '9px 11px', borderRadius: 10, border: '1px solid var(--border)', background: 'var(--surface)', color: 'var(--text)', resize: 'none', fontFamily: 'inherit', outline: 'none', boxSizing: 'border-box', boxShadow: 'inset 0 1px 2px rgba(15,23,42,0.05)' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 10, color: 'var(--text3)' }}>Ctrl+Enter to send</span>
                <button type="button" onClick={submit} disabled={submitting || !message.trim()}
                    style={{ padding: '7px 14px', borderRadius: 10, border: 'none', background: 'linear-gradient(135deg, #7C3AED 0%, #2563EB 100%)', color: '#fff', fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, opacity: !message.trim() ? 0.5 : 1, boxShadow: '0 8px 16px rgba(79,70,229,0.25)' }}>
                    {submitting ? <Loader2 className="spin" size={12} /> : <Send size={12} />} Send
                </button>
            </div>
        </div>
    );
}

// ── Thank-you screen ───────────────────────────────────────────────────────────
function ThankYou({ onClose }) {
    useEffect(() => { const t = setTimeout(onClose, 3000); return () => clearTimeout(t); }, []);
    return (
        <div style={{ textAlign: 'center', padding: '24px 16px' }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>🙏</div>
            <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text)', marginBottom: 6 }}>Thank you!</div>
            <div style={{ fontSize: 13, color: 'var(--text3)', lineHeight: 1.6 }}>Your feedback helps us make AuraGraph better for every student.</div>
        </div>
    );
}

// ── Main FeedbackWidget ────────────────────────────────────────────────────────
export default function FeedbackWidget({ mode = 'dashboard', notebookId = null, darkMode = false, tourAnchor = null }) {
    const [open, setOpen] = useState(false);
    const [done, setDone] = useState(false);
    const [activeTab, setActiveTab] = useState('help');
    const ref = useRef(null);

    // Close on outside click
    useEffect(() => {
        if (!open) return;
        const onOut = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        setTimeout(() => document.addEventListener('mousedown', onOut), 100);
        return () => document.removeEventListener('mousedown', onOut);
    }, [open]);

    const handleDone = () => { setDone(true); };
    const handleClose = () => { setOpen(false); setTimeout(() => setDone(false), 400); };

    useEffect(() => {
        if (!open) return;
        setDone(false);
    }, [open]);

    return (
        <div ref={ref} style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 8000 }}>
            {/* Popover panel */}
            {open && (
                <div style={{
                    position: 'absolute', bottom: 60, right: 0,
                    width: mode === 'dashboard' ? 372 : 332,
                    background: 'var(--bg)',
                    border: '1px solid var(--border)',
                    borderRadius: 20,
                    boxShadow: '0 22px 56px rgba(15,23,42,0.24), 0 8px 22px rgba(15,23,42,0.14)',
                    overflow: 'hidden',
                    animation: 'feedbackSlideUp 0.18s ease',
                }}>
                    {/* Header */}
                    <div style={{ background: 'linear-gradient(135deg, #334155 0%, #1E293B 36%, #312E81 100%)', padding: '16px 18px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 }}>
                        <div>
                            <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: '0.01em', color: '#fff' }}>
                                {activeTab === 'help' ? 'Navigation Help' : (mode === 'dashboard' ? 'Product Feedback' : 'Report an Issue')}
                            </div>
                            <div style={{ fontSize: 11.5, color: 'rgba(255,255,255,0.82)', marginTop: 3, lineHeight: 1.4 }}>
                                {activeTab === 'help' ? 'Ask how to use doubts, mutation, quick review, and more.' : (mode === 'dashboard' ? 'Help us improve AuraGraph for every study session.' : 'Tell us what went wrong and we’ll look into it.')}
                            </div>
                        </div>
                        <button onClick={handleClose} style={{ background: 'rgba(255,255,255,0.14)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: 10, cursor: 'pointer', color: '#fff', padding: 7, display: 'flex' }}>
                            <X size={14} />
                        </button>
                    </div>

                    <div style={{ padding: '18px' }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 14, padding: 4, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14 }}>
                            <button
                                type="button"
                                onClick={() => setActiveTab('help')}
                                style={{ border: `1px solid ${activeTab === 'help' ? 'rgba(124,58,237,0.35)' : 'transparent'}`, background: activeTab === 'help' ? 'var(--bg)' : 'transparent', color: activeTab === 'help' ? 'var(--ag-purple)' : 'var(--text2)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, boxShadow: activeTab === 'help' ? '0 2px 8px rgba(15,23,42,0.12)' : 'none' }}
                            >
                                <Compass size={14} /> Help Chat
                            </button>
                            <button
                                type="button"
                                onClick={() => setActiveTab('feedback')}
                                style={{ border: `1px solid ${activeTab === 'feedback' ? 'rgba(124,58,237,0.35)' : 'transparent'}`, background: activeTab === 'feedback' ? 'var(--bg)' : 'transparent', color: activeTab === 'feedback' ? 'var(--ag-purple)' : 'var(--text2)', borderRadius: 10, padding: '8px 10px', fontSize: 12, fontWeight: 600, cursor: 'pointer', boxShadow: activeTab === 'feedback' ? '0 2px 8px rgba(15,23,42,0.12)' : 'none' }}
                            >
                                Feedback
                            </button>
                        </div>

                        {activeTab === 'help' && <NavigationHelpChat />}

                        {activeTab === 'feedback' && (
                            done
                                ? <ThankYou onClose={handleClose} />
                                : mode === 'dashboard'
                                    ? <DetailedFeedbackForm notebookId={notebookId} onDone={handleDone} />
                                    : <BriefFeedbackForm notebookId={notebookId} onDone={handleDone} />
                        )}
                    </div>
                </div>
            )}

            {/* Floating bubble button */}
            <button
                data-tour={tourAnchor || undefined}
                onClick={() => setOpen(o => !o)}
                title={open ? 'Close feedback' : 'Share feedback'}
                style={{
                    width: 52, height: 52, borderRadius: '50%',
                    background: open ? 'var(--ag-purple)' : 'linear-gradient(135deg, var(--ag-purple), #2563EB)',
                    border: 'none', cursor: 'pointer',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    boxShadow: '0 4px 20px rgba(124,58,237,0.45)',
                    color: '#fff',
                    transition: 'all 0.2s',
                    transform: open ? 'scale(0.9)' : 'scale(1)',
                }}
                onMouseEnter={e => { if (!open) e.currentTarget.style.transform = 'scale(1.08)'; }}
                onMouseLeave={e => { if (!open) e.currentTarget.style.transform = 'scale(1)'; }}
            >
                {open ? <X size={20} /> : <MessageCircle size={22} />}
            </button>

            {/* Pulse dot indicator */}
            {!open && (
                <span style={{ position: 'absolute', top: 0, right: 0, width: 12, height: 12, borderRadius: '50%', background: '#10B981', border: '2px solid var(--bg)', animation: 'feedbackPulse 2s ease-in-out infinite' }} />
            )}
        </div>
    );
}
