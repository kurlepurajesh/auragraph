import React from 'react';
import { Clock, X, RefreshCw, Search } from 'lucide-react';

// ─── Study Timer (Pomodoro) ───────────────────────────────────────────────────
export function StudyTimer() {
    const MODES = { focus: 25 * 60, short: 5 * 60, long: 15 * 60 };
    const [mode, setMode] = React.useState('focus');
    const [secs, setSecs] = React.useState(MODES.focus);
    const [running, setRunning] = React.useState(false);
    const [sessions, setSessions] = React.useState(() => parseInt(localStorage.getItem('ag_sessions') || '0'));
    const [open, setOpen] = React.useState(false);
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
                        try { new Audio('data:audio/wav;base64,//uQRAAAAWMSLwUIYAAsYkXgoQwAEaYLWfkWgAI0wWs/ItAAAGDgYtAgAyN+QWaAAihwMWm4G8QQRDiMcCBcH3Cc+CDv/7xA4Tvh9Rz/y8QADBwMWgQAZG/ILNAARQ4GLTcDeIIIhxGOBAuD7hOfBB3/94gcJ3w+o5/5eIAIAAAVwWgQAVQ2ORaIQwEMAJiDg95G4nQL7mQVWI6GwRcfsZAcsKkJvxgxEjzFUgfHoSQ9Qq7KNwqHwuB13MA4a1q/DmBrHgPcmjiGoh//EwC5nGPEmS4RcfkVKOhJf+WOgoxJclFz3kgn//dBA+ya1GhurNn8zb//9NNutNuhz31f////9vt///z+IdAEAAAK4LQIAKobHItEIYCGAExBwe8jcToF9zIKrEdDYIuP2MgOWFSE34wYiR5iqQPj0JIeoVdlG4VD4XA67mAcNa1fhzA1jwHuTRxDUQ//iYBczjHiTJcIuPyKlHQkv/LHQUYkuSi57yQT//uggfZNajQ3Vmz+Zt//+mm3Wm3Q576v////+32///5/EOgAAADVghQAAAAA==').play(); } catch { }
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
            {sessions > 0 && <span style={{ position: 'absolute', top: -2, right: -2, background: 'var(--ag-purple)', color: '#fff', fontSize: 8, fontWeight: 700, width: 14, height: 14, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{sessions}</span>}
        </button>
    );

    return (
        <div style={{ position: 'relative' }}>
            <div style={{ position: 'absolute', top: '100%', right: 0, marginTop: 6, background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 16px', boxShadow: 'var(--shadow-md)', zIndex: 100, width: 200, animation: 'fadeIn 0.2s ease' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)' }}>⏱ Focus Timer</span>
                    <button onClick={() => setOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)' }}><X size={13} /></button>
                </div>
                <div style={{ display: 'flex', gap: 3, marginBottom: 12, background: 'var(--surface)', borderRadius: 7, padding: 2 }}>
                    {[['focus', '25m'], ['short', '5m'], ['long', '15m']].map(([m, l]) => (
                        <button key={m} onClick={() => switchMode(m)} style={{ flex: 1, padding: '4px 0', borderRadius: 5, border: 'none', cursor: 'pointer', background: mode === m ? 'var(--text)' : 'transparent', color: mode === m ? '#fff' : 'var(--text3)', fontSize: 10, fontWeight: 600, transition: 'all 0.15s' }}>{l}</button>
                    ))}
                </div>
                <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
                    <svg width={80} height={80} viewBox="0 0 50 50">
                        <circle cx={25} cy={25} r={R} fill="none" stroke="var(--border)" strokeWidth={4} />
                        <circle cx={25} cy={25} r={R} fill="none"
                            stroke={isAlmostDone ? 'var(--ag-red)' : mode === 'focus' ? 'var(--ag-purple)' : 'var(--ag-emerald)'}
                            strokeWidth={4}
                            strokeDasharray={`${pct * C} ${C}`}
                            strokeDashoffset={C * 0.25}
                            strokeLinecap="round"
                            style={{ transition: 'stroke-dasharray 0.5s ease, stroke 0.5s ease', transform: 'rotate(-90deg)', transformOrigin: '25px 25px' }}
                        />
                        <text x={25} y={28} textAnchor="middle" fontSize={9} fontWeight={700} fill={isAlmostDone ? 'var(--ag-red)' : 'var(--text)'} fontFamily="Space Grotesk, monospace">{mm}:{ss}</text>
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
export function NoteSearch({ pages, onJumpToPage, onClose }) {
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
            const end = Math.min(page.length, pos + query.length + 60);
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
                        <button key={r.idx} onClick={() => { onJumpToPage(r.idx, query); onClose(); }}
                            style={{ display: 'block', width: '100%', textAlign: 'left', padding: '10px 12px', borderRadius: 8, border: '1px solid transparent', background: 'var(--surface)', marginBottom: 6, cursor: 'pointer', transition: 'all 0.12s' }}
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

// ─── Keyboard Shortcuts Modal ─────────────────────────────────────────────────
export function ShortcutsModal({ onClose }) {
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
