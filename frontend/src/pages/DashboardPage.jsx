import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { setUser } from '../store';
import { ls_getNotebooks, ls_createNotebook, ls_deleteNotebook } from '../localNotebooks';
import { API, apiFetch } from '../components/utils';
import {
    BookOpen, Plus, Trash2, ChevronRight, LogOut, Loader2, BookMarked,
    Calendar, Moon, Sun, Target, TrendingUp, Clock, Award, Star,
    ChevronDown, FolderOpen, Folder
} from 'lucide-react';

function getUserId(user) {
    return user?.id || 'demo-user';
}

// ─── Streak helpers ────────────────────────────────────────────────────────────
function getStreak() {
    try {
        const data = JSON.parse(localStorage.getItem('ag_streak') || '{}');
        const today = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86400000).toDateString();
        if (data.lastDate === today) return data.count || 1;
        if (data.lastDate === yesterday) return data.count || 0;
        return 0;
    } catch { return 0; }
}
function touchStreak() {
    try {
        const today = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86400000).toDateString();
        const data = JSON.parse(localStorage.getItem('ag_streak') || '{}');
        if (data.lastDate === today) return;
        const count = data.lastDate === yesterday ? (data.count || 0) + 1 : 1;
        localStorage.setItem('ag_streak', JSON.stringify({ lastDate: today, count }));
    } catch { }
}

// ─── Mastery summary across notebooks ─────────────────────────────────────────
function getMasteryStats(notebooks) {
    let mastered = 0, partial = 0, struggling = 0;
    for (const nb of notebooks) {
        for (const n of (nb.graph?.nodes || [])) {
            if (n.status === 'mastered') mastered++;
            else if (n.status === 'partial') partial++;
            else if (n.status === 'struggling') struggling++;
        }
    }
    return { mastered, partial, struggling, total: mastered + partial + struggling };
}

// ─── Mini donut chart ──────────────────────────────────────────────────────────
function MiniDonut({ mastered, partial, struggling, total }) {
    if (total === 0) return (
        <svg width={72} height={72} viewBox="0 0 72 72">
            <circle cx={36} cy={36} r={26} fill="none" stroke="var(--border)" strokeWidth={10} />
            <text x={36} y={40} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--text3)">–</text>
        </svg>
    );
    const R = 26, C = 2 * Math.PI * R;
    const segments = [
        { val: mastered, color: 'var(--ag-emerald)' },
        { val: partial, color: 'var(--ag-gold)' },
        { val: struggling, color: 'var(--ag-red)' },
    ];
    let offset = 0;
    const arcs = segments.map(s => {
        const len = (s.val / total) * C;
        const arc = { ...s, len, offset };
        offset += len;
        return arc;
    });
    const pct = Math.round((mastered / total) * 100);
    return (
        <svg width={72} height={72} viewBox="0 0 72 72" style={{ transform: 'rotate(-90deg)' }}>
            <circle cx={36} cy={36} r={R} fill="none" stroke="var(--border)" strokeWidth={10} />
            {arcs.map((a, i) => a.len > 0 && (
                <circle key={i} cx={36} cy={36} r={R} fill="none"
                    stroke={a.color} strokeWidth={10}
                    strokeDasharray={`${a.len} ${C - a.len}`}
                    strokeDashoffset={-a.offset}
                    strokeLinecap="butt"
                />
            ))}
            <text x={36} y={40} textAnchor="middle" fontSize={13} fontWeight={800}
                fill="var(--text)" style={{ transform: 'rotate(90deg)', transformOrigin: '36px 36px' }}>
                {pct}%
            </text>
        </svg>
    );
}

// ─── Create Notebook Modal ─────────────────────────────────────────────────────
function CreateNotebookModal({ onClose, onCreate }) {
    const [name, setName] = useState('');
    const [course, setCourse] = useState('');
    const [loading, setLoading] = useState(false);
    const [nameError, setNameError] = useState('');
    const [courseError, setCourseError] = useState('');

    const validateName = (v) => {
        if (!v.trim()) return 'Title is required.';
        if (v.trim().length < 2) return 'Title must be at least 2 characters.';
        if (v.length > 120) return 'Title must be 120 characters or less.';
        return '';
    };
    const validateCourse = (v) => {
        if (!v.trim()) return 'Course / subject is required.';
        if (v.length > 80) return 'Course code must be 80 characters or less.';
        return '';
    };

    const submit = async (e) => {
        e.preventDefault();
        const ne = validateName(name);
        const ce = validateCourse(course);
        setNameError(ne); setCourseError(ce);
        if (ne || ce) return;
        setLoading(true);
        await onCreate(name.trim(), course.trim());
        setLoading(false);
        onClose();
    };

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
                    <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--purple)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <BookOpen size={18} color="#fff" />
                    </div>
                    <div>
                        <h3 style={{ marginBottom: 2 }}>New Notebook</h3>
                        <p style={{ fontSize: 12, color: 'var(--text3)' }}>Create a notebook for a course or subject</p>
                    </div>
                </div>
                <form onSubmit={submit}>
                    <div style={{ marginBottom: 14 }}>
                        <label>Notebook Title</label>
                        <input className={`input${nameError ? ' input-error' : ''}`} placeholder="e.g. Digital Signal Processing" value={name}
                            onChange={e => { setName(e.target.value); if (nameError) setNameError(validateName(e.target.value)); }}
                            maxLength={120} autoFocus />
                        {nameError && <p style={{ fontSize: 11, color: 'var(--ag-red)', marginTop: 4 }}>{nameError}</p>}
                    </div>
                    <div style={{ marginBottom: 24 }}>
                        <label>Course Code / Subject</label>
                        <input className={`input${courseError ? ' input-error' : ''}`} placeholder="e.g. EC301 — DSP" value={course}
                            onChange={e => { setCourse(e.target.value); if (courseError) setCourseError(validateCourse(e.target.value)); }}
                            maxLength={80} />
                        {courseError && <p style={{ fontSize: 11, color: 'var(--ag-red)', marginTop: 4 }}>{courseError}</p>}
                    </div>
                    <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                        <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={loading}>
                            {loading ? <Loader2 className="spin" size={14} /> : <><Plus size={14} /> Create Notebook</>}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── Notebook Card ─────────────────────────────────────────────────────────────
function NotebookCard({ nb, onOpen, onDelete }) {
    const [deleting, setDeleting] = useState(false);
    const dateStr = new Date(nb.created_at).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
    const hasNote = nb.note?.length > 0;
    const nodes = nb.graph?.nodes || [];
    const mastered = nodes.filter(n => n.status === 'mastered').length;
    const total = nodes.length;
    const pct = total > 0 ? Math.round((mastered / total) * 100) : null;

    const profColor = {
        Foundations: { bg: '#ECFDF5', text: '#059669', border: '#A7F3D0' },
        Practitioner: { bg: '#F5F3FF', text: 'var(--ag-purple)', border: '#DDD6FE' },
        Expert: { bg: '#EFF6FF', text: '#2563EB', border: '#BFDBFE' },
    }[nb.proficiency] || { bg: 'var(--surface2)', text: 'var(--text3)', border: 'var(--border)' };

    return (
        <div className="card" style={{ padding: '20px', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 14 }}
            onClick={() => onOpen(nb.id)}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 42, height: 42, borderRadius: 11, background: 'linear-gradient(135deg,#7C3AED22,#7C3AED44)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: '1px solid #7C3AED33' }}>
                        <BookMarked size={19} color="#7C3AED" />
                    </div>
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', lineHeight: 1.3 }}>{nb.name}</div>
                        <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>{nb.course}</div>
                    </div>
                </div>
                <button className="btn btn-ghost btn-sm" style={{ flexShrink: 0, padding: '4px', opacity: 0.5 }}
                    onClick={async e => { e.stopPropagation(); setDeleting(true); await onDelete(nb.id); setDeleting(false); }}>
                    {deleting ? <Loader2 className="spin" size={14} /> : <Trash2 size={14} color="var(--text3)" />}
                </button>
            </div>

            <div style={{ fontSize: 12, color: 'var(--text3)', background: 'var(--surface)', borderRadius: 8, padding: '8px 10px', minHeight: 36, lineHeight: 1.65, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', borderLeft: hasNote ? '3px solid var(--purple)' : '3px solid var(--border)' }}>
                {hasNote ? nb.note.replace(/[#*`\\]/g, '').replace(/\$[^$]*\$/g, '').replace(/\$\$[\s\S]*?\$\$/g, '[formula]').slice(0, 130) + '…' : 'No notes yet — open to upload slides & textbook'}
            </div>

            {/* Progress bar */}
            {pct !== null && (
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                        <span style={{ fontSize: 11, color: 'var(--text3)', fontWeight: 600 }}>Mastery</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: pct >= 70 ? 'var(--ag-emerald)' : pct >= 40 ? 'var(--ag-gold)' : 'var(--ag-red)' }}>{pct}%</span>
                    </div>
                    <div className="progress-bar-track">
                        <div className="progress-bar-fill" style={{ width: `${pct}%`, background: pct >= 70 ? 'linear-gradient(90deg,#10B981,#34D399)' : pct >= 40 ? 'linear-gradient(90deg,#F59E0B,#FCD34D)' : 'linear-gradient(90deg,#EF4444,#FCA5A5)' }} />
                    </div>
                </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text3)' }}>
                        <Calendar size={11} /> {dateStr}
                    </div>
                    {nb.proficiency && (
                        <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 7px', borderRadius: 10, background: profColor.bg, color: profColor.text, border: `1px solid ${profColor.border}` }}>
                            {nb.proficiency}
                        </span>
                    )}
                    {total > 0 && <span style={{ fontSize: 10, color: 'var(--text3)' }}>· {total} concepts</span>}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600, color: 'var(--purple)' }}>
                    Open <ChevronRight size={14} />
                </div>
            </div>
        </div>
    );
}

// ─── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, color, sublabel }) {
    return (
        <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 12, padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14, boxShadow: 'var(--shadow)', flex: 1 }}>
            <div style={{ width: 40, height: 40, borderRadius: 10, background: color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {React.cloneElement(icon, { size: 18, color })}
            </div>
            <div>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)', lineHeight: 1 }}>{value}</div>
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 3, fontWeight: 500 }}>{label}</div>
                {sublabel && <div style={{ fontSize: 10, color, fontWeight: 600, marginTop: 2 }}>{sublabel}</div>}
            </div>
        </div>
    );
}

// ─── Dashboard Page ────────────────────────────────────────────────────────────
export default function DashboardPage() {
    const navigate = useNavigate();
    const dispatch = useDispatch();
    const user = useSelector(s => s.graph.user);

    const [notebooks, setNotebooks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [darkMode, setDarkMode] = useState(() => localStorage.getItem('ag_dark') === '1');
    const [streak] = useState(getStreak);
    const [collapsedCourses, setCollapsedCourses] = useState(() => {
        try { return new Set(JSON.parse(localStorage.getItem('ag_collapsed_courses') || '[]')); }
        catch { return new Set(); }
    });

    const byCourse = useMemo(() => {
        const map = {};
        for (const nb of notebooks) {
            const key = (nb.course?.trim()) || 'Uncategorized';
            (map[key] = map[key] || []).push(nb);
        }
        return Object.entries(map).sort(([a], [b]) => {
            if (a === 'Uncategorized') return 1;
            if (b === 'Uncategorized') return -1;
            return a.localeCompare(b);
        });
    }, [notebooks]);

    const toggleCourse = (key) => {
        setCollapsedCourses(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key); else next.add(key);
            localStorage.setItem('ag_collapsed_courses', JSON.stringify([...next]));
            return next;
        });
    };

    const userId = getUserId(user);

    // Apply dark mode
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light');
        localStorage.setItem('ag_dark', darkMode ? '1' : '0');
    }, [darkMode]);

    useEffect(() => { touchStreak(); }, []);

    const loadNotebooks = async () => {
        try {
            const res = await apiFetch(`${API}/notebooks`);
            if (res.ok) {
                const data = await res.json();
                setNotebooks(data.notebooks || data || []);
                setLoading(false);
                return;
            }
        } catch { }
        setNotebooks(ls_getNotebooks(userId));
        setLoading(false);
    };

    useEffect(() => { loadNotebooks(); }, []);

    const handleCreate = async (name, course) => {
        let nb;
        try {
            const res = await apiFetch(`${API}/notebooks`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, course }) });
            if (res.ok) nb = await res.json();
        } catch { }
        if (!nb) {
            nb = ls_createNotebook(userId, name, course);
        } else {
            const existing = ls_getNotebooks(userId);
            if (!existing.find(e => e.id === nb.id)) {
                const stored = JSON.parse(localStorage.getItem('ag_notebooks') || '[]');
                stored.unshift({ ...nb, user_id: userId });
                localStorage.setItem('ag_notebooks', JSON.stringify(stored));
            }
        }
        setNotebooks(prev => [nb, ...prev]);
    };

    const handleDelete = async (id) => {
        try { await apiFetch(`${API}/notebooks/${id}`, { method: 'DELETE' }); } catch { }
        ls_deleteNotebook(id);
        setNotebooks(prev => prev.filter(nb => nb.id !== id));
    };

    const handleLogout = () => {
        localStorage.removeItem('ag_token');
        localStorage.removeItem('ag_user');
        dispatch(setUser(null));
        navigate('/');
    };

    const displayName = user?.name || (user?.email?.split('@')[0]) || 'Student';
    const masteryStats = getMasteryStats(notebooks);
    const notebooksWithNotes = notebooks.filter(nb => nb.note?.length > 0).length;
    const totalConcepts = masteryStats.total;

    const greetingHour = new Date().getHours();
    const greeting = greetingHour < 12 ? 'Good morning' : greetingHour < 17 ? 'Good afternoon' : 'Good evening';

    return (
        <div style={{ minHeight: '100vh', background: 'var(--surface)' }}>
            {/* Demo banner — only shown when truly offline (backend unreachable) */}
            {localStorage.getItem('ag_offline_mode') === '1' && (
                <div style={{ background: darkMode ? '#1a1200' : '#FEF3C7', borderBottom: '1px solid #FDE68A', padding: '8px 32px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#92400E' }}>
                    <span style={{ fontSize: 14 }}>⚠️</span>
                    <span><b>Offline demo mode:</b> Backend is unreachable. Notes are stored in your browser only.</span>
                </div>
            )}

            {/* Header */}
            <header style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: '0 32px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ background: '#fff', borderRadius: 10, padding: '4px 12px', display: 'flex', alignItems: 'center' }}>
                        <img src="/logo.jpeg" alt="AuraGraph" style={{ height: 30, width: 'auto' }} />
                    </div>
                    {streak > 0 && (
                        <div className="streak-badge" style={{ marginLeft: 4 }}>
                            🔥 {streak} day streak
                        </div>
                    )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <button onClick={() => setDarkMode(d => !d)} className="btn btn-ghost btn-sm" title="Toggle dark mode" style={{ padding: '6px 8px' }}>
                        {darkMode ? <Sun size={16} /> : <Moon size={16} />}
                    </button>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'linear-gradient(135deg,#7C3AED,#2563EB)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>
                        {displayName[0]?.toUpperCase()}
                    </div>
                    <span style={{ fontSize: 14, color: 'var(--text2)', fontWeight: 600 }}>{displayName}</span>
                    <button className="btn btn-ghost btn-sm" onClick={handleLogout} style={{ gap: 5 }}>
                        <LogOut size={14} /> Logout
                    </button>
                </div>
            </header>

            <main style={{ maxWidth: 1100, margin: '0 auto', padding: '36px 32px' }}>
                {/* Welcome row */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28, gap: 16 }}>
                    <div>
                        <div style={{ fontSize: 13, color: 'var(--text3)', fontWeight: 500, marginBottom: 4 }}>{greeting}, {displayName} 👋</div>
                        <h1 style={{ fontSize: 26, fontWeight: 800, letterSpacing: '-0.5px', marginBottom: 6 }}>My Notebooks</h1>
                        <p style={{ fontSize: 14, color: 'var(--text3)' }}>Upload slides & textbooks to create AI-fused study notes</p>
                    </div>
                    <button className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ gap: 6, flexShrink: 0, marginTop: 4 }}>
                        <Plus size={16} /> New Notebook
                    </button>
                </div>

                {/* Stats row */}
                {!loading && (notebooks.length > 0 || masteryStats.total > 0) && (
                    <div style={{ display: 'flex', gap: 12, marginBottom: 28, flexWrap: 'wrap' }}>
                        <StatCard icon={<BookOpen />} label="Notebooks" value={notebooks.length} color="#7C3AED" sublabel={notebooksWithNotes > 0 ? `${notebooksWithNotes} with notes` : null} />
                        <StatCard icon={<Target />} label="Concepts tracked" value={totalConcepts || '—'} color="#2563EB" sublabel={totalConcepts > 0 ? `${masteryStats.mastered} mastered` : null} />
                        <StatCard icon={<TrendingUp />} label="Study streak" value={streak > 0 ? `${streak}d` : '0d'} color="#FF6B35" sublabel={streak > 0 ? 'Keep it up! 🔥' : 'Start today!'} />
                        {masteryStats.total > 0 && (
                            <div style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 12, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 14, boxShadow: 'var(--shadow)', flex: 1 }}>
                                <MiniDonut {...masteryStats} />
                                <div>
                                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>Overall Mastery</div>
                                    {[['mastered', 'var(--ag-emerald)'], ['partial', 'var(--ag-gold)'], ['struggling', 'var(--ag-red)']].map(([k, c]) => (
                                        <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                                            <div style={{ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0 }} />
                                            <span style={{ fontSize: 11, color: 'var(--text3)', textTransform: 'capitalize' }}>{k}</span>
                                            <span style={{ fontSize: 11, fontWeight: 700, color: c, marginLeft: 'auto' }}>{masteryStats[k]}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Notebook grid — grouped by course */}
                {loading ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 16 }}>
                        {[...Array(4)].map((_, i) => (
                            <div key={i} style={{ borderRadius: 14, border: '1px solid var(--border)', background: 'var(--card)', padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
                                <div style={{ height: 14, width: '60%', borderRadius: 6, background: 'var(--border)', animation: 'skeleton-pulse 1.4s ease-in-out infinite' }} />
                                <div style={{ height: 11, width: '40%', borderRadius: 6, background: 'var(--border)', animation: 'skeleton-pulse 1.4s ease-in-out 0.2s infinite' }} />
                                <div style={{ height: 6, borderRadius: 4, background: 'var(--border)', animation: 'skeleton-pulse 1.4s ease-in-out 0.3s infinite' }} />
                                <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                                    <div style={{ height: 11, width: 60, borderRadius: 6, background: 'var(--border)', animation: 'skeleton-pulse 1.4s ease-in-out 0.4s infinite' }} />
                                    <div style={{ height: 11, width: 80, borderRadius: 6, background: 'var(--border)', animation: 'skeleton-pulse 1.4s ease-in-out 0.5s infinite' }} />
                                </div>
                            </div>
                        ))}
                    </div>
                ) : notebooks.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '80px 0' }}>
                        <div style={{ width: 72, height: 72, borderRadius: 18, background: 'linear-gradient(135deg,#7C3AED22,#2563EB22)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px', border: '1px solid #7C3AED33' }}>
                            <BookOpen size={30} color="#7C3AED" />
                        </div>
                        <h3 style={{ color: 'var(--text)', marginBottom: 10, fontSize: 18 }}>No notebooks yet</h3>
                        <p style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 28, lineHeight: 1.75, maxWidth: 360, margin: '0 auto 28px' }}>
                            Create your first notebook for a course.<br />Upload slides + textbook → get AI-powered, personalised notes.
                        </p>
                        <button className="btn btn-primary btn-lg" onClick={() => setShowCreate(true)} style={{ gap: 6 }}>
                            <Plus size={16} /> Create First Notebook
                        </button>
                    </div>
                ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                        {byCourse.map(([courseKey, nbs]) => {
                            const collapsed = collapsedCourses.has(courseKey);
                            return (
                                <div key={courseKey}>
                                    {/* Course header */}
                                    <button
                                        onClick={() => toggleCourse(courseKey)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 8, marginBottom: collapsed ? 0 : 12,
                                            background: 'none', border: 'none', cursor: 'pointer', padding: 0, width: '100%'
                                        }}
                                    >
                                        <div style={{ width: 28, height: 28, borderRadius: 7, background: 'linear-gradient(135deg,#7C3AED22,#2563EB22)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #7C3AED22' }}>
                                            {collapsed
                                                ? <Folder size={14} color="#7C3AED" />
                                                : <FolderOpen size={14} color="#7C3AED" />}
                                        </div>
                                        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)', flexGrow: 1, textAlign: 'left' }}>
                                            {courseKey}
                                        </span>
                                        <span style={{ fontSize: 11, color: 'var(--text3)', marginRight: 6, fontWeight: 500 }}>
                                            {nbs.length} notebook{nbs.length !== 1 ? 's' : ''}
                                        </span>
                                        <ChevronDown size={15} color="var(--text3)"
                                            style={{ transform: collapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s' }} />
                                    </button>

                                    {/* Notebooks grid for this course */}
                                    {!collapsed && (
                                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                                            {nbs.map(nb => (
                                                <NotebookCard key={nb.id} nb={nb}
                                                    onOpen={id => navigate(`/notebook/${id}`)}
                                                    onDelete={handleDelete} />
                                            ))}
                                        </div>
                                    )}
                                </div>
                            );
                        })}
                    </div>
                )}
            </main>

            {showCreate && <CreateNotebookModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}
        </div>
    );
}
