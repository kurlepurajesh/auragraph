import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { setUser } from '../store';
import { ls_getNotebooks, ls_createNotebook, ls_deleteNotebook } from '../localNotebooks';
import { useAura } from '../hooks/useAura';
import { useFullscreen } from '../hooks/useFullscreen';
import AuraPanel from '../components/AuraPanel';
import FeedbackWidget from '../components/FeedbackWidget';
import { API, apiFetch } from '../components/utils';
import {
    BookOpen, Plus, Trash2, ChevronRight, LogOut, Loader2, BookMarked,
    Calendar, Moon, Sun, Target, TrendingUp, Clock, Award, Star,
    ChevronDown, FolderOpen, Folder, UserCircle2, AlertTriangle
} from 'lucide-react';

const DASHBOARD_TOUR_SEEN_KEY = 'ag_dashboard_tour_seen_v1';

const EMPTY_PROFILE = {
    class_level: '',
    education_stage: '',
    institution: '',
    board_university: '',
    stream_major: '',
    target_exam: '',
    learning_goal: '',
};

function getUserId(user) {
    return user?.id || 'demo-user';
}

// ─── Streak helpers ────────────────────────────────────────────────────────────
function getStreakKey(userId) {
    return `ag_streak:${userId || 'demo-user'}`;
}

function getStreak(userId) {
    try {
        const data = JSON.parse(localStorage.getItem(getStreakKey(userId)) || '{}');
        const today = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86400000).toDateString();
        if (data.lastDate === today) return Math.max(0, data.count || 0);
        if (data.lastDate === yesterday) return data.count || 0;
        return 0;
    } catch { return 0; }
}
function touchStreak(userId) {
    try {
        const today = new Date().toDateString();
        const yesterday = new Date(Date.now() - 86400000).toDateString();
        const key = getStreakKey(userId);
        const data = JSON.parse(localStorage.getItem(key) || '{}');
        if (!data.lastDate) {
            localStorage.setItem(key, JSON.stringify({ lastDate: today, count: 0 }));
            return 0;
        }
        if (data.lastDate === today) return Math.max(0, data.count || 0);
        const count = data.lastDate === yesterday ? (data.count || 0) + 1 : 1;
        localStorage.setItem(key, JSON.stringify({ lastDate: today, count }));
        return count;
    } catch {
        return 0;
    }
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
            <circle cx={36} cy={36} r={26} fill="none" stroke="var(--border)" strokeWidth={7} />
            <text x={36} y={40} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--text3)">–</text>
        </svg>
    );
    const R = 26, C = 2 * Math.PI * R;
    const segments = [
        { val: mastered, color: 'var(--ag-mastery-strong)' },
        { val: partial, color: 'var(--ag-mastery-medium)' },
        { val: struggling, color: 'var(--ag-mastery-faint)' },
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
            <circle cx={36} cy={36} r={R} fill="none" stroke="var(--border)" strokeWidth={7} />
            {arcs.map((a, i) => a.len > 0 && (
                <circle key={i} cx={36} cy={36} r={R} fill="none"
                    stroke={a.color} strokeWidth={7}
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
                        <BookOpen size={18} color="var(--ag-on-primary)" />
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

function EducationProfileModal({ profile, onClose, onSave }) {
    const [form, setForm] = useState({ ...EMPTY_PROFILE, ...(profile || {}) });
    const [saving, setSaving] = useState(false);

    const setField = (k, v) => setForm(prev => ({ ...prev, [k]: v }));

    const submit = async (e) => {
        e.preventDefault();
        setSaving(true);
        await onSave(form);
        setSaving(false);
        onClose();
    };

    const labelStyle = { fontSize: 15, fontWeight: 700, color: 'var(--text2)', marginBottom: 7 };
    const inputStyle = { width: '100%', borderRadius: 12, border: '1px solid var(--border)', padding: '12px 16px', fontSize: 14, background: 'var(--surface)', color: 'var(--text)', outline: 'none', boxSizing: 'border-box' };

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()} style={{ maxWidth: 900, width: '96vw', padding: '22px 24px 20px', borderRadius: 18 }}>
                <div style={{ fontSize: 33, fontWeight: 800, color: 'var(--text)', marginBottom: 4 }}>Education Profile</div>
                <div style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 18 }}>These details help AuraGraph generate notes at the right level for you.</div>

                <form onSubmit={submit}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                        <div>
                            <div style={labelStyle}>Class / Level</div>
                            <input className="ag-profile-field" style={inputStyle} placeholder="e.g. Class 12, 2nd Year B.Tech" value={form.class_level} maxLength={80} onChange={e => setField('class_level', e.target.value)} autoFocus />
                        </div>
                        <div>
                            <div style={labelStyle}>Education Stage</div>
                            <select style={inputStyle} value={form.education_stage} onChange={e => setField('education_stage', e.target.value)}>
                                <option value="">Select</option>
                                <option value="School">School</option>
                                <option value="Undergraduate">Undergraduate</option>
                                <option value="Postgraduate">Postgraduate</option>
                                <option value="Professional">Professional</option>
                            </select>
                        </div>

                        <div>
                            <div style={labelStyle}>Institute</div>
                            <input className="ag-profile-field" style={inputStyle} placeholder="e.g. IIT Roorkee" value={form.institution} maxLength={120} onChange={e => setField('institution', e.target.value)} />
                        </div>
                        <div>
                            <div style={labelStyle}>Board / University</div>
                            <input className="ag-profile-field" style={inputStyle} placeholder="e.g. CBSE / AKTU" value={form.board_university} maxLength={120} onChange={e => setField('board_university', e.target.value)} />
                        </div>

                        <div>
                            <div style={labelStyle}>Stream / Major</div>
                            <input className="ag-profile-field" style={inputStyle} placeholder="e.g. CSE, Physics" value={form.stream_major} maxLength={120} onChange={e => setField('stream_major', e.target.value)} />
                        </div>
                        <div>
                            <div style={labelStyle}>Target Exam</div>
                            <input className="ag-profile-field" style={inputStyle} placeholder="e.g. JEE, GATE, Semester Finals" value={form.target_exam} maxLength={120} onChange={e => setField('target_exam', e.target.value)} />
                        </div>
                    </div>

                    <div style={{ marginTop: 14 }}>
                        <div style={labelStyle}>Learning Goal</div>
                        <textarea className="ag-profile-field" style={{ ...inputStyle, minHeight: 90, resize: 'vertical' }} placeholder="e.g. Build strong fundamentals for probability and score 80%+ in exams" value={form.learning_goal} maxLength={240} onChange={e => setField('learning_goal', e.target.value)} />
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 18 }}>
                        <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={saving}>
                            {saving ? <Loader2 className="spin" size={14} /> : 'Save Profile'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

// ─── Notebook Card ─────────────────────────────────────────────────────────────
function NotebookCard({ nb, onOpen, onDelete, darkMode = false, tourAnchor = null }) {
    const [deleting, setDeleting] = useState(false);
    const dateStr = new Date(nb.created_at).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
    const hasNote = nb.note?.length > 0;
    const nodes = nb.graph?.nodes || [];
    const mastered = nodes.filter(n => n.status === 'mastered').length;
    const total = nodes.length;
    const pct = total > 0 ? Math.round((mastered / total) * 100) : null;

    const profColor = darkMode
        ? {
            Foundations: { bg: 'var(--ag-accent-soft)', text: 'var(--ag-accent)', border: 'var(--ag-accent-border-soft)' },
            Practitioner: { bg: 'var(--ag-secondary-soft)', text: 'var(--ag-secondary)', border: 'var(--ag-secondary-border-soft)' },
            Expert: { bg: 'var(--ag-primary-soft)', text: 'var(--ag-primary)', border: 'var(--ag-primary-border-soft)' },
        }[nb.proficiency] || { bg: 'var(--surface2)', text: 'var(--text3)', border: 'var(--border)' }
        : {
            Foundations: { bg: 'var(--ag-accent-soft)', text: 'var(--ag-accent)', border: 'var(--ag-accent-border-soft)' },
            Practitioner: { bg: 'var(--ag-secondary-soft)', text: 'var(--ag-secondary)', border: 'var(--ag-secondary-border-soft)' },
            Expert: { bg: 'var(--ag-primary-soft)', text: 'var(--ag-primary)', border: 'var(--ag-primary-border-soft)' },
        }[nb.proficiency] || { bg: 'var(--surface2)', text: 'var(--text3)', border: 'var(--border)' };

        return (
            <div data-tour={tourAnchor || undefined} className="card" style={{ padding: '20px', borderRadius: 16, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 14, background: 'var(--bg)', border: '1px solid var(--ag-dashboard-card-border)', boxShadow: 'var(--ag-dashboard-card-shadow)', transition: 'all 0.18s' }}
                onClick={() => onOpen(nb.id)}
                onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow-hover)'; }}
                onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow)'; }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 42, height: 42, borderRadius: 11, background: 'var(--ag-dashboard-icon-indigo-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: '1px solid var(--ag-primary-border-soft)' }}>
                        <BookMarked size={19} color="var(--ag-primary)" />
                    </div>
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', lineHeight: 1.3 }}>{nb.name}</div>
                        <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>{nb.course}</div>
                    </div>
                </div>
                <button className="btn btn-ghost btn-sm" style={{ flexShrink: 0, padding: '4px', opacity: 0.6 }}
                    onClick={async e => { e.stopPropagation(); setDeleting(true); await onDelete(nb.id); setDeleting(false); }}>
                    {deleting ? <Loader2 className="spin" size={14} /> : <Trash2 size={14} color="var(--text3)" />}
                </button>
            </div>

        <div style={{ fontSize: 12, color: 'var(--text2)', background: 'var(--surface)', borderRadius: 12, padding: '10px 12px', minHeight: 40, lineHeight: 1.65, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', borderLeft: hasNote ? '3px solid var(--ag-primary)' : '3px solid var(--border)' }}>
                {hasNote ? nb.note.replace(/[#*`\\]/g, '').replace(/\$[^$]*\$/g, '').replace(/\$\$[\s\S]*?\$\$/g, '[formula]').slice(0, 130) + '…' : 'No notes yet — open to upload slides & textbook'}
            </div>

            {/* Progress bar */}
            {pct !== null && (
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                        <span style={{ fontSize: 11, color: 'var(--text3)', fontWeight: 600 }}>Mastery</span>
                        <span style={{ fontSize: 11, fontWeight: 700, color: pct >= 70 ? 'var(--ag-primary)' : pct >= 40 ? 'var(--ag-secondary)' : 'var(--text2)' }}>{pct}%</span>
                    </div>
                    <div className="progress-bar-track">
                        <div className="progress-bar-fill" style={{ width: `${pct}%`, background: pct >= 70 ? 'var(--ag-progress-strong)' : pct >= 40 ? 'var(--ag-progress-medium)' : 'var(--ag-progress-faint)' }} />
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
                <button
                    className="btn btn-ghost btn-sm"
                    onClick={e => { e.stopPropagation(); onOpen(nb.id); }}
                    aria-label={`Open notebook ${nb.name}`}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600, color: 'var(--ag-primary)', padding: '4px 6px', borderRadius: 8 }}
                >
                    Open <ChevronRight size={14} />
                </button>
            </div>
        </div>
    );
}

// ─── Stat Info Modal ───────────────────────────────────────────────────────────
function StatInfoModal({ title, color, icon, onClose, children }) {
    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in-scale" onClick={e => e.stopPropagation()}
                style={{ maxWidth: 400, width: '94vw', padding: 0, overflow: 'hidden', borderRadius: 14 }}>
                <div style={{ background: color + '15', borderBottom: `1px solid ${color}30`, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{ width: 36, height: 36, borderRadius: 9, background: color + '25', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        {React.cloneElement(icon, { size: 18, color })}
                    </div>
                    <div style={{ flex: 1, fontWeight: 800, fontSize: 15, color: 'var(--text)' }}>{title}</div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text3)', padding: 4 }}>
                        <svg width={14} height={14} viewBox="0 0 14 14" fill="none"><path d="M1 1l12 12M13 1L1 13" stroke="currentColor" strokeWidth={2} strokeLinecap="round"/></svg>
                    </button>
                </div>
                <div style={{ padding: '18px 20px', background: 'var(--bg)' }}>
                    {children}
                </div>
            </div>
        </div>
    );
}

// ─── Stat card ─────────────────────────────────────────────────────────────────
function StatCard({ icon, label, value, color, sublabel, onClick, cardBackground = 'var(--bg)', iconBackground = 'var(--ag-primary-soft)', borderColor = 'var(--border)' }) {
    return (
        <div
            onClick={onClick}
            style={{
                background: cardBackground, border: `1px solid ${borderColor}`, borderRadius: 16,
                padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 14,
                boxShadow: 'var(--ag-dashboard-card-shadow)', flex: 1, minWidth: 150,
                cursor: onClick ? 'pointer' : 'default',
                transition: 'all 0.25s ease',
                userSelect: 'none',
            }}
            onMouseEnter={e => { if (onClick) { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow-hover)'; e.currentTarget.style.borderColor = borderColor; } }}
            onMouseLeave={e => { if (onClick) { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow)'; e.currentTarget.style.borderColor = borderColor; } }}
        >
            <div style={{ width: 40, height: 40, borderRadius: 10, background: iconBackground, border: `1px solid ${borderColor}`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                {React.cloneElement(icon, { size: 18, color })}
            </div>
            <div style={{ flex: 1 }}>
                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)', lineHeight: 1 }}>{value}</div>
                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 3, fontWeight: 500 }}>{label}</div>
                {sublabel && <div style={{ fontSize: 10, color, fontWeight: 600, marginTop: 2 }}>{sublabel}</div>}
            </div>
            {onClick && <svg width={12} height={12} viewBox="0 0 12 12" style={{ flexShrink: 0, opacity: 0.35 }}><path d="M5 2l4 4-4 4" stroke={color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>}
        </div>
    );
}

// ─── Dashboard Page ────────────────────────────────────────────────────────────
export default function DashboardPage() {
    const navigate = useNavigate();
    const dispatch = useDispatch();
    const user = useSelector(s => s.graph.user);
    const aura = useAura();
    const { isFullscreen, toggle: toggleFullscreen } = useFullscreen();

    const [notebooks, setNotebooks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showCreate, setShowCreate] = useState(false);
    const [showProfile, setShowProfile] = useState(false);
    const [profile, setProfile] = useState(EMPTY_PROFILE);
    const [showAuraPanel, setShowAuraPanel] = useState(false);
    const [showStatModal, setShowStatModal] = useState(null); // 'notebooks' | 'concepts' | 'streak'
    const [darkMode, setDarkMode] = useState(() => localStorage.getItem('ag_dark') === '1');
    const [showTour, setShowTour] = useState(false);
    const [tourStep, setTourStep] = useState(0);
    const [tourRect, setTourRect] = useState(null);
    const [tourBootstrapped, setTourBootstrapped] = useState(false);
    const [streak, setStreak] = useState(0);
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
        // For each notebook, effective recency = max(created_at, last localStorage open)
        const nbRecency = (nb) => {
            const created = new Date(nb.created_at || 0).getTime();
            const used = parseInt(localStorage.getItem(`ag_nb_used:${nb.id}`) || '0', 10);
            return Math.max(created, used);
        };
        return Object.entries(map).sort(([keyA, nbsA], [keyB, nbsB]) => {
            if (keyA === 'Uncategorized') return 1;
            if (keyB === 'Uncategorized') return -1;
            // Course recency = most recent notebook in that course
            const latestA = Math.max(...nbsA.map(nbRecency));
            const latestB = Math.max(...nbsB.map(nbRecency));
            return latestB - latestA;
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

    useEffect(() => {
        const current = getStreak(userId);
        setStreak(current);
        const next = touchStreak(userId);
        setStreak(typeof next === 'number' ? next : getStreak(userId));
    }, [userId]);

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

    useEffect(() => {
        (async () => {
            try {
                const res = await apiFetch(`${API}/auth/profile`);
                if (!res.ok) return;
                const data = await res.json().catch(() => ({}));
                if (data?.profile && typeof data.profile === 'object') {
                    setProfile(prev => ({ ...prev, ...data.profile }));
                }
            } catch { }
        })();
    }, []);

    const saveProfile = async (nextProfile) => {
        const payload = { ...EMPTY_PROFILE, ...(nextProfile || {}) };
        try {
            const res = await apiFetch(`${API}/auth/profile`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (res.ok) {
                const data = await res.json().catch(() => ({}));
                setProfile({ ...EMPTY_PROFILE, ...(data?.profile || payload) });
                return;
            }
        } catch { }
        setProfile(payload);
    };

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

    const tourSteps = useMemo(() => {
        const steps = [
            {
                selector: '[data-tour="new-notebook"]',
                title: 'Create your first notebook',
                text: 'Start here to create a notebook for any subject. You can then upload slides, PDFs, and notes to generate AI-ready study content.',
            },
            {
                selector: '[data-tour="profile-btn"]',
                title: 'Set your learning profile',
                text: 'Add your class level, board, and goals so AuraGraph can personalize explanations and question quality for you.',
            },
        ];

        if (notebooks.length > 0 || masteryStats.total > 0) {
            steps.push({
                selector: '[data-tour="stats-row"]',
                title: 'Track your progress',
                text: 'These cards summarize notebook count, study streak, XP rank, and mastery insights. Click any card for details.',
            });
        }

        if (notebooks.length > 0) {
            steps.push(
                {
                    selector: '[data-tour="courses-section"]',
                    title: 'Your notebooks, grouped by course',
                    text: 'Courses are sorted by recent activity. Collapse a course to keep your dashboard clean and focused.',
                },
                {
                    selector: '[data-tour="first-notebook"]',
                    title: 'Open a notebook to study',
                    text: 'Click any notebook card to open the workspace for notes, quiz, doubts, highlighting, and more.',
                }
            );
        } else {
            steps.push({
                selector: '[data-tour="empty-create"]',
                title: 'No notebooks yet? Start here',
                text: 'Use this button to create your first notebook and begin your learning workflow.',
            });
        }

        steps.push({
            selector: '[data-tour="feedback-widget-btn"]',
            title: 'Need help or want to share feedback?',
            text: 'Use this floating button anytime to open Navigation Help Chat or send product feedback. We use it to improve your study experience.',
        });

        return steps;
    }, [notebooks.length, masteryStats.total]);

    useEffect(() => {
        if (tourStep > 0 && tourStep >= tourSteps.length) {
            setTourStep(Math.max(0, tourSteps.length - 1));
        }
    }, [tourStep, tourSteps.length]);

    useEffect(() => {
        if (loading || tourBootstrapped) return;
        setTourBootstrapped(true);
        if (!localStorage.getItem(DASHBOARD_TOUR_SEEN_KEY)) {
            setShowTour(true);
            setTourStep(0);
        }
    }, [loading, tourBootstrapped]);

    const startTour = useCallback(() => {
        setTourStep(0);
        setShowTour(true);
    }, []);

    const endTour = useCallback((markSeen = true) => {
        setShowTour(false);
        if (markSeen) localStorage.setItem(DASHBOARD_TOUR_SEEN_KEY, '1');
    }, []);

    useEffect(() => {
        if (!showTour || !tourSteps.length) {
            setTourRect(null);
            return;
        }

        const active = tourSteps[tourStep];
        if (!active) {
            setTourRect(null);
            return;
        }

        const updateRect = () => {
            const el = document.querySelector(active.selector);
            if (!el) {
                setTourRect(null);
                return;
            }

            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) {
                setTourRect(null);
                return;
            }

            const vPad = 16;
            const inViewport = r.bottom >= 0 && r.top <= window.innerHeight;
            if (!inViewport) {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }

            setTourRect({
                left: Math.max(8, r.left - 6),
                top: Math.max(8, r.top - 6),
                width: r.width + 12,
                height: r.height + 12,
                anchorLeft: r.left + (r.width / 2),
                anchorTop: r.top,
                anchorBottom: r.bottom,
            });
        };

        updateRect();
        const timer = setTimeout(updateRect, 220);
        window.addEventListener('resize', updateRect);
        window.addEventListener('scroll', updateRect, true);
        return () => {
            clearTimeout(timer);
            window.removeEventListener('resize', updateRect);
            window.removeEventListener('scroll', updateRect, true);
        };
    }, [showTour, tourStep, tourSteps]);

    const activeTourStep = showTour ? tourSteps[tourStep] : null;
    const tourCardWidth = 340;
    const tourCardHeightApprox = 190;
    const cardLeft = tourRect
        ? Math.max(12, Math.min(window.innerWidth - tourCardWidth - 12, tourRect.anchorLeft - (tourCardWidth / 2)))
        : Math.max(12, (window.innerWidth - tourCardWidth) / 2);
    const cardTop = tourRect
        ? (tourRect.anchorBottom + 14 + tourCardHeightApprox > window.innerHeight
            ? Math.max(12, tourRect.anchorTop - tourCardHeightApprox - 16)
            : tourRect.anchorBottom + 14)
        : Math.max(70, (window.innerHeight - tourCardHeightApprox) / 2);

    return (
        <div style={{ minHeight: '100vh', background: 'var(--surface)' }}>
            {/* Demo banner — only shown when truly offline (backend unreachable) */}
            {localStorage.getItem('ag_offline_mode') === '1' && (
                <div style={{ background: 'var(--ag-primary-soft)', borderBottom: '1px solid var(--ag-primary-border-soft)', padding: '8px 32px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: 'var(--ag-primary)' }}>
                    <AlertTriangle size={14} />
                    <span><b>Offline demo mode:</b> Backend is unreachable. Notes are stored in your browser only.</span>
                </div>
            )}

            {/* Header */}
            <header style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: '0 32px', height: 64, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ background: 'var(--bg)', borderRadius: 10, padding: '4px 12px', display: 'flex', alignItems: 'center' }}>
                        <img src="/logo.jpeg" alt="AuraGraph" style={{ height: 30, width: 'auto' }} />
                    </div>
                    <div className="streak-badge" style={{ marginLeft: 4 }}>
                        <TrendingUp size={12} /> {streak} day{streak === 1 ? '' : 's'} streak
                    </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <button onClick={() => setDarkMode(d => !d)} className="btn btn-ghost btn-sm" title="Toggle dark mode" style={{ padding: '6px 8px' }}>
                        {darkMode ? <Sun size={16} /> : <Moon size={16} />}
                    </button>
                    <button onClick={toggleFullscreen} className="btn btn-ghost btn-sm" title={isFullscreen ? 'Exit fullscreen (F11)' : 'Fullscreen (F11)'} style={{ padding: '6px 8px' }}>
                        {isFullscreen
                            ? <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/></svg>
                            : <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoherein="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
                        }
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={startTour} style={{ gap: 5, marginLeft: 8 }} title="Take dashboard tour">
                        <Star size={14} /> Tour
                    </button>
                    <button
                        data-tour="profile-btn"
                        className="btn btn-ghost btn-sm"
                        onClick={() => setShowProfile(true)}
                        style={{ gap: 7, paddingLeft: 6, paddingRight: 10 }}
                        title="Edit education profile"
                    >
                        <span style={{ width: 24, height: 24, borderRadius: '50%', background: 'linear-gradient(135deg,var(--ag-primary),var(--ag-secondary))', color: 'var(--ag-on-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 12, lineHeight: 1 }}>
                            {displayName[0]?.toUpperCase()}
                        </span>
                        <span>Profile</span>
                    </button>
                    <button className="btn btn-ghost btn-sm" onClick={handleLogout} style={{ gap: 5 }}>
                        <LogOut size={14} /> Logout
                    </button>
                </div>
            </header>

            <main style={{ maxWidth: 1140, margin: '0 auto', padding: '40px 32px' }}>
                {/* Welcome row */}
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32, gap: 24 }}>
                    <div>
                        <div style={{ fontSize: 13, color: 'var(--text2)', fontWeight: 500, marginBottom: 6 }}>{greeting}, {displayName}</div>
                        <h1 style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-0.5px', marginBottom: 8 }}>My Notebooks</h1>
                        <p style={{ fontSize: 14, color: 'var(--text2)' }}>Upload slides & textbooks to create AI-fused study notes</p>
                    </div>
                    <button data-tour="new-notebook" className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ gap: 6, flexShrink: 0, marginTop: 4 }}>
                        <Plus size={16} /> New Notebook
                    </button>
                </div>

                {/* Stats row */}
                {!loading && (
                    <div data-tour="stats-row" style={{ display: 'grid', gap: 16, marginBottom: 32, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
                        <StatCard icon={<BookOpen />} label="Notebooks" value={notebooks.length} color="var(--ag-primary)" cardBackground="var(--ag-dashboard-card-notebooks)" iconBackground="var(--ag-dashboard-icon-indigo-bg)" borderColor="var(--ag-dashboard-card-border)" sublabel={notebooksWithNotes > 0 ? `${notebooksWithNotes} With Notes` : null} onClick={() => setShowStatModal('notebooks')} />
                        <StatCard icon={<TrendingUp />} label="Study streak" value={streak > 0 ? `${streak}d` : '0d'} color="var(--ag-orange)" cardBackground="var(--ag-dashboard-card-streak)" iconBackground="var(--ag-dashboard-icon-orange-bg)" borderColor="var(--ag-dashboard-card-border)" sublabel={streak > 0 ? 'Keep it up' : 'Start today'} onClick={() => setShowStatModal('streak')} />
                        {/* Aura XP card */}
                        <div
                            onClick={() => setShowAuraPanel(true)}
                            style={{ background: 'var(--ag-dashboard-card-xp)', border: '1px solid var(--ag-dashboard-card-border)', borderRadius: 16, padding: '16px 18px', display: 'flex', alignItems: 'center', gap: 12, boxShadow: 'var(--ag-dashboard-card-shadow)', cursor: 'pointer', textAlign: 'left', transition: 'all 0.25s ease', userSelect: 'none' }}
                            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow-hover)'; e.currentTarget.style.borderColor = 'var(--ag-dashboard-card-border)'; }}
                            onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow)'; e.currentTarget.style.borderColor = 'var(--ag-dashboard-card-border)'; }}
                        >
                            <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--ag-dashboard-icon-purple-bg)', border: '1px solid var(--ag-dashboard-card-border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                <Award size={18} color="var(--ag-secondary)" />
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)', lineHeight: 1 }}>{aura.data.xp.toLocaleString()} XP</div>
                                <div style={{ fontSize: 11, color: 'var(--text3)', marginTop: 3, fontWeight: 500 }}>Aura Rank</div>
                                <div style={{ fontSize: 10, color: 'var(--ag-secondary)', fontWeight: 700, marginTop: 2 }}>{aura.badge.name}{aura.nextBadge ? ` · ${aura.nextBadge.minXp - aura.data.xp} to ${aura.nextBadge.name}` : ' · Max rank!'}</div>
                            </div>
                            <svg width={12} height={12} viewBox="0 0 12 12" style={{ flexShrink: 0, opacity: 0.35 }}><path d="M5 2l4 4-4 4" stroke="var(--ag-secondary)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
                        </div>
                        {/* Overall Mastery card */}
                        <div
                            onClick={() => setShowStatModal('concepts')}
                            style={{ background: 'var(--ag-dashboard-card-mastery)', border: '1px solid var(--ag-dashboard-card-border)', borderRadius: 16, padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 14, boxShadow: 'var(--ag-dashboard-card-shadow)', cursor: 'pointer', transition: 'all 0.25s ease', userSelect: 'none' }}
                            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow-hover)'; e.currentTarget.style.borderColor = 'var(--ag-dashboard-card-border)'; }}
                            onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow)'; e.currentTarget.style.borderColor = 'var(--ag-dashboard-card-border)'; }}
                        >
                            <MiniDonut {...masteryStats} />
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>Overall Mastery</div>
                                {[['mastered', 'var(--ag-mastery-strong)'], ['partial', 'var(--ag-mastery-medium)'], ['struggling', 'var(--ag-mastery-faint)']].map(([k, c]) => (
                                    <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3 }}>
                                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0 }} />
                                        <span style={{ fontSize: 11, color: 'var(--text3)', textTransform: 'capitalize' }}>{k}</span>
                                        <span style={{ fontSize: 11, fontWeight: 700, color: c, marginLeft: 'auto' }}>{masteryStats[k]}</span>
                                    </div>
                                ))}
                            </div>
                            <svg width={12} height={12} viewBox="0 0 12 12" style={{ flexShrink: 0, opacity: 0.35, alignSelf: 'center' }}><path d="M5 2l4 4-4 4" stroke="var(--ag-secondary)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" fill="none"/></svg>
                        </div>
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
                        <div style={{ width: 72, height: 72, borderRadius: 18, background: 'var(--ag-dashboard-icon-indigo-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 20px', border: '1px solid var(--ag-primary-border-soft)' }}>
                            <BookOpen size={30} color="var(--ag-primary)" />
                        </div>
                        <h3 style={{ color: 'var(--text)', marginBottom: 10, fontSize: 18 }}>No notebooks yet</h3>
                        <p style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 28, lineHeight: 1.75, maxWidth: 360, margin: '0 auto 28px' }}>
                            Create your first notebook for a course.<br />Upload slides + textbook → get AI-powered, personalised notes.
                        </p>
                        <button data-tour="empty-create" className="btn btn-primary btn-lg" onClick={() => setShowCreate(true)} style={{ gap: 6 }}>
                            <Plus size={16} /> Create First Notebook
                        </button>
                    </div>
                ) : (
                    <>
                        {/* ── My Courses section heading ──────────────────── */}
                        <div data-tour="courses-section" style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12, padding: '12px 14px' }}>
                            <div>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <span style={{ fontFamily: '"Sora", "DM Sans", sans-serif', fontSize: 16, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.2px' }}>My Courses</span>
                                    <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 20, background: 'var(--ag-primary-soft)', color: 'var(--ag-primary)', border: '1px solid var(--ag-primary-border-soft)' }}>
                                        {byCourse.length} Course{byCourse.length !== 1 ? 's' : ''} · {notebooks.length} Notebook{notebooks.length !== 1 ? 's' : ''}
                                    </span>
                                </div>
                                <p style={{ fontSize: 12, color: 'var(--text3)', marginTop: 3 }}>
                                    Sorted By Most Recently Active · Click A Course To Collapse It · Click A Notebook To Open It
                                </p>
                            </div>
                        </div>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                            {byCourse.map(([courseKey, nbs]) => {
                                const collapsed = collapsedCourses.has(courseKey);
                                // Most recent activity for this course (create or open)
                                const latestTs = Math.max(...nbs.map(n => {
                                    const created = new Date(n.created_at || 0).getTime();
                                    const used = parseInt(localStorage.getItem(`ag_nb_used:${n.id}`) || '0', 10);
                                    return Math.max(created, used);
                                }));
                                const latestDate = new Date(latestTs);
                                const relativeDate = (() => {
                                    const diffDays = Math.floor((Date.now() - latestDate.getTime()) / 86400000);
                                    if (diffDays === 0) return 'Active Today';
                                    if (diffDays === 1) return 'Active Yesterday';
                                    if (diffDays < 7) return `Active ${diffDays}d Ago`;
                                    return `Active ${latestDate.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}`;
                                })();
                                return (
                                    <div key={courseKey}>
                                        {/* Course header */}
                                        <button
                                            onClick={() => toggleCourse(courseKey)}
                                            onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--ag-dashboard-card-shadow-hover)'; }}
                                            onMouseLeave={e => { e.currentTarget.style.transform = 'none'; e.currentTarget.style.boxShadow = 'none'; }}
                                            style={{
                                                display: 'flex', alignItems: 'center', gap: 10, marginBottom: collapsed ? 0 : 14,
                                                background: 'var(--bg)',
                                                border: '1px solid var(--border)',
                                                borderRadius: collapsed ? 12 : '12px 12px 0 0',
                                                borderBottom: collapsed ? '1px solid var(--border)' : '1px solid var(--border)',
                                                cursor: 'pointer', padding: '10px 14px', width: '100%',
                                                transition: 'all 0.15s',
                                            }}
                                        >
                        <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--ag-dashboard-icon-indigo-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--ag-primary-border-soft)', flexShrink: 0 }}>
                                                {collapsed
                            ? <Folder size={16} color="var(--ag-primary)" />
                            : <FolderOpen size={16} color="var(--ag-primary)" />}
                                            </div>
                                            <div style={{ flex: 1, textAlign: 'left', minWidth: 0 }}>
                                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                                    {courseKey === 'Uncategorized' ? 'Uncategorized' : courseKey}
                                                </div>
                                                <div style={{ fontSize: 10, color: 'var(--text3)', marginTop: 1 }}>
                                                    {nbs.length} Notebook{nbs.length !== 1 ? 's' : ''} · {relativeDate}
                                                </div>
                                            </div>
                                            <ChevronDown size={14} color="var(--text3)"
                                                style={{ transform: collapsed ? 'rotate(-90deg)' : 'none', transition: 'transform 0.2s', flexShrink: 0 }} />
                                        </button>

                                        {/* Notebooks grid for this course */}
                                        {!collapsed && (
                                            <div style={{
                                                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 16,
                                                padding: '16px',
                                                border: '1px solid var(--ag-dashboard-card-border)', borderTop: 'none',
                                                borderRadius: '0 0 12px 12px',
                                                background: 'var(--bg)',
                                            }}>
                                                {nbs.map(nb => (
                                                    <NotebookCard key={nb.id} nb={nb}
                                                        tourAnchor="first-notebook"
                                                        darkMode={darkMode}
                                                        onOpen={id => { localStorage.setItem(`ag_nb_used:${id}`, String(Date.now())); navigate(`/notebook/${id}`); }}
                                                        onDelete={handleDelete} />
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </>
                )}
            </main>

            {showCreate && <CreateNotebookModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}
            {showProfile && <EducationProfileModal profile={profile} onClose={() => setShowProfile(false)} onSave={saveProfile} />}

            {/* Notebooks modal */}
            {showStatModal === 'notebooks' && (
                <StatInfoModal title="Your Notebooks" color="var(--ag-primary)" icon={<BookOpen />} onClose={() => setShowStatModal(null)}>
                    <div style={{ fontSize: 12, color: 'var(--text2)', marginBottom: 14 }}>
                        You have <strong style={{ color: 'var(--ag-primary)' }}>{notebooks.length}</strong> notebook{notebooks.length !== 1 ? 's' : ''}.
                        {notebooksWithNotes > 0 && <> <strong style={{ color: 'var(--ag-primary)' }}>{notebooksWithNotes}</strong> of them have generated notes.</>}
                    </div>
                    {notebooks.slice(0, 6).map(nb => (
                        <div key={nb.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 8, border: '1px solid var(--border)', marginBottom: 6, cursor: 'pointer', background: 'var(--surface)' }}
                            onClick={() => { setShowStatModal(null); localStorage.setItem(`ag_nb_used:${nb.id}`, String(Date.now())); navigate(`/notebook/${nb.id}`); }}>
                            <div style={{ width: 8, height: 8, borderRadius: '50%', background: nb.note?.length > 0 ? 'var(--ag-primary)' : 'var(--border2)', flexShrink: 0 }} />
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{nb.name}</div>
                                <div style={{ fontSize: 10, color: 'var(--text3)' }}>{nb.course || 'No course set'}</div>
                            </div>
                            <svg width={12} height={12} viewBox="0 0 12 12" fill="none"><path d="M4 2l4 4-4 4" stroke="var(--ag-primary)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"/></svg>
                        </div>
                    ))}
                    {notebooks.length > 6 && <div style={{ fontSize: 11, color: 'var(--text3)', textAlign: 'center', marginTop: 4 }}>+{notebooks.length - 6} more below</div>}
                </StatInfoModal>
            )}

            {/* Concepts modal */}
            {showStatModal === 'concepts' && (
                <StatInfoModal title="Concept Mastery" color="var(--ag-secondary)" icon={<Target />} onClose={() => setShowStatModal(null)}>
                    <div style={{ display: 'flex', gap: 10, marginBottom: 16 }}>
                        {[['mastered', 'var(--ag-mastery-strong)', masteryStats.mastered], ['partial', 'var(--ag-mastery-medium)', masteryStats.partial], ['struggling', 'var(--ag-mastery-faint)', masteryStats.struggling]].map(([k, c, v]) => (
                            <div key={k} style={{ flex: 1, textAlign: 'center', background: c + '15', borderRadius: 8, padding: '10px 4px', border: `1px solid ${c}30` }}>
                                <div style={{ fontSize: 22, fontWeight: 800, color: c }}>{v}</div>
                                <div style={{ fontSize: 9, color: c, textTransform: 'uppercase', fontWeight: 700, marginTop: 2 }}>{k}</div>
                            </div>
                        ))}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.7 }}>
                        You're tracking <strong>{masteryStats.total}</strong> concepts across all notebooks.
                        {masteryStats.mastered > 0 && <> <strong style={{ color: 'var(--ag-mastery-strong)' }}>{Math.round(masteryStats.mastered / masteryStats.total * 100)}%</strong> are mastered.</>}
                        {masteryStats.struggling > 0 && <> Open a notebook and use the <strong>Sniper Exam</strong> to target the <strong style={{ color: 'var(--ag-mastery-medium)' }}>{masteryStats.struggling}</strong> struggling concept{masteryStats.struggling !== 1 ? 's' : ''}.</>}
                    </div>
                </StatInfoModal>
            )}

            {/* Streak modal */}
            {showStatModal === 'streak' && (
                <StatInfoModal title="Study Streak" color="var(--ag-orange)" icon={<TrendingUp />} onClose={() => setShowStatModal(null)}>
                    <div style={{ textAlign: 'center', padding: '8px 0 16px' }}>
                        <div style={{ width: 56, height: 56, margin: '0 auto 10px', borderRadius: 14, background: 'rgba(254, 159, 92, 0.14)', border: '1px solid rgba(249, 115, 22, 0.34)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <TrendingUp size={30} color="var(--ag-orange)" />
                        </div>
                        <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--ag-orange)' }}>{streak} day{streak !== 1 ? 's' : ''}</div>
                        <div style={{ fontSize: 13, color: 'var(--text3)', marginTop: 4 }}>{streak > 0 ? 'Current streak — keep it going!' : 'Open a notebook today to start your streak.'}</div>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.7, background: 'var(--surface)', borderRadius: 8, padding: '10px 12px', border: '1px solid var(--border)' }}>
                        <strong>Tip:</strong> A streak is counted when you open AuraGraph on consecutive days. Consistent daily review is proven to increase long-term retention by up to 80%.
                    </div>
                </StatInfoModal>
            )}

            {showAuraPanel && <AuraPanel aura={aura} onClose={() => setShowAuraPanel(false)} darkMode={darkMode} />}
            <FeedbackWidget mode="dashboard" darkMode={darkMode} tourAnchor="feedback-widget-btn" />

            {showTour && activeTourStep && (
                <>
                    <div
                        onClick={() => endTour(true)}
                        style={{
                            position: 'fixed',
                            inset: 0,
                            zIndex: 9000,
                            background: tourRect ? 'transparent' : 'var(--ag-overlay)',
                        }}
                    />

                    {tourRect && (
                        <div
                            style={{
                                position: 'fixed',
                                left: tourRect.left,
                                top: tourRect.top,
                                width: tourRect.width,
                                height: tourRect.height,
                                borderRadius: 12,
                                border: '2px solid var(--ag-purple-ring)',
                                boxShadow: '0 0 0 9999px var(--ag-overlay-strong), 0 0 0 5px var(--ag-focus-ring)',
                                zIndex: 9001,
                                pointerEvents: 'none',
                                transition: 'all 0.2s ease',
                            }}
                        />
                    )}

                    <div
                        style={{
                            position: 'fixed',
                            left: cardLeft,
                            top: cardTop,
                            width: tourCardWidth,
                            maxWidth: 'calc(100vw - 24px)',
                            background: 'var(--bg)',
                            border: '1px solid var(--border)',
                            borderRadius: 14,
                            boxShadow: 'var(--ag-popover-shadow-xl)',
                            padding: '14px 14px 12px',
                            zIndex: 9002,
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--ag-purple)', letterSpacing: '0.02em' }}>
                                Dashboard Tour
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--text3)', fontWeight: 600 }}>
                                {tourStep + 1} / {tourSteps.length}
                            </div>
                        </div>

                        <div style={{ fontSize: 16, fontWeight: 800, color: 'var(--text)', marginBottom: 6, lineHeight: 1.25 }}>
                            {activeTourStep.title}
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--text2)', lineHeight: 1.6, marginBottom: 12 }}>
                            {activeTourStep.text}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                            {tourSteps.map((_, idx) => (
                                <div key={idx} style={{ width: idx === tourStep ? 18 : 6, height: 6, borderRadius: 99, background: idx === tourStep ? 'var(--ag-purple)' : 'var(--border2)', transition: 'all 0.16s ease' }} />
                            ))}
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                            <button className="btn btn-ghost btn-sm" onClick={() => endTour(true)}>
                                Skip
                            </button>
                            <div style={{ display: 'flex', gap: 8 }}>
                                <button className="btn btn-secondary btn-sm" onClick={() => setTourStep(s => Math.max(0, s - 1))} disabled={tourStep === 0}>
                                    Back
                                </button>
                                {tourStep < tourSteps.length - 1 ? (
                                    <button className="btn btn-primary btn-sm" onClick={() => setTourStep(s => Math.min(tourSteps.length - 1, s + 1))}>
                                        Next
                                    </button>
                                ) : (
                                    <button className="btn btn-primary btn-sm" onClick={() => endTour(true)}>
                                        Done
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                </>
            )}
        </div>
    );
}
