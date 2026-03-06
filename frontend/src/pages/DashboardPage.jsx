import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { setUser } from '../store';
import { ls_getNotebooks, ls_createNotebook, ls_deleteNotebook } from '../localNotebooks';
import { BookOpen, Plus, Trash2, ChevronRight, LogOut, Loader2, BookMarked, Calendar } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function authHeaders() {
    const token = localStorage.getItem('ag_token') || 'demo-token';
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

function getUserId() {
    try { return JSON.parse(localStorage.getItem('ag_user'))?.id || 'demo-user'; } catch { return 'demo-user'; }
}

// ─── Create Notebook Modal ─────────────────────────────────────────────────────
function CreateNotebookModal({ onClose, onCreate }) {
    const [name, setName] = useState('');
    const [course, setCourse] = useState('');
    const [loading, setLoading] = useState(false);

    const submit = async (e) => {
        e.preventDefault();
        if (!name || !course) return;
        setLoading(true);
        await onCreate(name, course);
        setLoading(false);
        onClose();
    };

    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal fade-in" onClick={e => e.stopPropagation()}>
                <h3 style={{ marginBottom: 4 }}>New Notebook</h3>
                <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 22 }}>Create a notebook for a specific course or subject.</p>
                <form onSubmit={submit}>
                    <div style={{ marginBottom: 14 }}>
                        <label>Notebook Title</label>
                        <input className="input" placeholder="e.g. Digital Signal Processing" value={name} onChange={e => setName(e.target.value)} autoFocus />
                    </div>
                    <div style={{ marginBottom: 22 }}>
                        <label>Course / Subject</label>
                        <input className="input" placeholder="e.g. EC301 — DSP" value={course} onChange={e => setCourse(e.target.value)} />
                    </div>
                    <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
                        <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
                        <button type="submit" className="btn btn-primary" disabled={loading || !name || !course}>
                            {loading ? <Loader2 className="spin" size={14} /> : 'Create Notebook'}
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

    return (
        <div className="card" style={{ padding: '20px', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 12 }}
            onClick={() => onOpen(nb.id)}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 38, height: 38, borderRadius: 10, background: 'var(--surface2)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                        <BookMarked size={18} color="var(--text2)" />
                    </div>
                    <div>
                        <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text)', lineHeight: 1.3 }}>{nb.name}</div>
                        <div style={{ fontSize: 12, color: 'var(--text3)', marginTop: 2 }}>{nb.course}</div>
                    </div>
                </div>
                <button className="btn btn-ghost btn-sm" style={{ flexShrink: 0, padding: '4px' }}
                    onClick={async e => { e.stopPropagation(); setDeleting(true); await onDelete(nb.id); setDeleting(false); }}>
                    {deleting ? <Loader2 className="spin" size={14} /> : <Trash2 size={14} color="var(--text3)" />}
                </button>
            </div>

            <div style={{ fontSize: 12, color: 'var(--text3)', background: 'var(--surface)', borderRadius: 6, padding: '8px 10px', minHeight: 36, lineHeight: 1.6, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                {hasNote ? nb.note.replace(/[#*`\\]/g, '').replace(/\$[^$]*\$/g, '').replace(/\$\$[\s\S]*?\$\$/g, '[formula]').slice(0, 130) + '…' : 'No notes yet — open to upload slides & textbook'}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--text3)' }}>
                        <Calendar size={11} /> {dateStr}
                    </div>
                    {nb.proficiency && (
                        <span style={{ fontSize: 10, fontWeight: 600, padding: '1px 7px', borderRadius: 10, background: nb.proficiency === 'Foundations' ? '#ECFDF5' : nb.proficiency === 'Expert' ? '#EFF6FF' : '#F5F3FF', color: nb.proficiency === 'Foundations' ? '#059669' : nb.proficiency === 'Expert' ? '#2563EB' : '#7C3AED', border: `1px solid ${nb.proficiency === 'Foundations' ? '#A7F3D0' : nb.proficiency === 'Expert' ? '#BFDBFE' : '#DDD6FE'}` }}>
                            {nb.proficiency}
                        </span>
                    )}
                    {nb.graph?.nodes?.length > 0 && (
                        <span style={{ fontSize: 10, color: 'var(--text3)' }}>· {nb.graph.nodes.length} concepts</span>
                    )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600, color: 'var(--text2)' }}>
                    Open <ChevronRight size={14} />
                </div>
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

    const userId = getUserId();

    const loadNotebooks = async () => {
        // 1) Try backend first
        try {
            const res = await fetch(`${API}/notebooks`, { headers: authHeaders() });
            if (res.ok) {
                const data = await res.json();
                setNotebooks(data);
                setLoading(false);
                return;
            }
        } catch { }
        // 2) Fallback to localStorage
        setNotebooks(ls_getNotebooks(userId));
        setLoading(false);
    };

    useEffect(() => { loadNotebooks(); }, []);

    const handleCreate = async (name, course) => {
        let nb;
        // 1) Try backend
        try {
            const res = await fetch(`${API}/notebooks`, {
                method: 'POST', headers: authHeaders(),
                body: JSON.stringify({ name, course })
            });
            if (res.ok) { nb = await res.json(); }
        } catch { }
        // 2) If backend failed, create locally; if backend succeeded, mirror only the
        //    metadata (not a second full entry) so offline fallback works on reload
        if (!nb) {
            nb = ls_createNotebook(userId, name, course);
        } else {
            // Store a lightweight mirror — same id so ls_getNotebook(id) finds it
            const local = { ...nb, user_id: userId };
            const existing = ls_getNotebooks(userId);
            if (!existing.find(e => e.id === nb.id)) {
                const stored = JSON.parse(localStorage.getItem('ag_notebooks') || '[]');
                stored.unshift(local);
                localStorage.setItem('ag_notebooks', JSON.stringify(stored));
            }
        }
        setNotebooks(prev => [nb, ...prev]);
    };

    const handleDelete = async (id) => {
        try { await fetch(`${API}/notebooks/${id}`, { method: 'DELETE', headers: authHeaders() }); } catch { }
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

    return (
        <div style={{ minHeight: '100vh', background: 'var(--surface)' }}>
            {/* Demo mode banner */}
            {localStorage.getItem('ag_token') === 'demo-token' && (
                <div style={{ background: '#FEF3C7', borderBottom: '1px solid #FDE68A', padding: '8px 32px', display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#92400E' }}>
                    <span style={{ fontSize: 14 }}>⚠️</span>
                    <span><b>Demo mode:</b> Backend is offline. Notes and notebooks are stored in your browser only and will be lost if you clear site data. <a href="https://github.com/your-repo" style={{ color: '#78350F', fontWeight: 600 }} onClick={e => e.preventDefault()}>Start the backend</a> to enable full AI features.</span>
                </div>
            )}
            {/* Header */}
            <header style={{ background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: '0 32px', height: 60, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 32, height: 32, background: 'var(--text)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <BookOpen size={16} color="white" />
                    </div>
                    <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: '-0.3px' }}>AuraGraph</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--text)', color: 'white', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13 }}>
                        {displayName[0]?.toUpperCase()}
                    </div>
                    <span style={{ fontSize: 14, color: 'var(--text2)', fontWeight: 500 }}>{displayName}</span>
                    <button className="btn btn-ghost btn-sm" onClick={handleLogout} style={{ gap: 5 }}>
                        <LogOut size={14} /> Logout
                    </button>
                </div>
            </header>

            {/* Main */}
            <main style={{ maxWidth: 1100, margin: '0 auto', padding: '40px 32px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 32 }}>
                    <div>
                        <h1 style={{ fontSize: 24, fontWeight: 800, letterSpacing: '-0.5px' }}>My Notebooks</h1>
                        <p style={{ fontSize: 14, color: 'var(--text3)', marginTop: 4 }}>Upload slides & textbooks to create AI-fused study notes</p>
                    </div>
                    <button className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ gap: 6 }}>
                        <Plus size={16} /> New Notebook
                    </button>
                </div>

                {loading ? (
                    <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--text3)' }}>
                        <Loader2 className="spin" size={28} style={{ margin: '0 auto 12px' }} />
                        <p style={{ fontSize: 14 }}>Loading your notebooks…</p>
                    </div>
                ) : notebooks.length === 0 ? (
                    <div style={{ textAlign: 'center', padding: '80px 0' }}>
                        <div style={{ width: 64, height: 64, borderRadius: 16, background: 'var(--surface2)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 16px' }}>
                            <BookOpen size={28} color="var(--text3)" />
                        </div>
                        <h3 style={{ color: 'var(--text)', marginBottom: 8 }}>No notebooks yet</h3>
                        <p style={{ fontSize: 14, color: 'var(--text3)', marginBottom: 24, lineHeight: 1.7 }}>
                            Create your first notebook for a course.<br />Upload slides + textbook to generate AI-powered notes.
                        </p>
                        <button className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ gap: 5 }}>
                            <Plus size={15} /> Create First Notebook
                        </button>
                    </div>
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 16 }}>
                        {notebooks.map(nb => (
                            <NotebookCard key={nb.id} nb={nb} onOpen={id => navigate(`/notebook/${id}`)} onDelete={handleDelete} />
                        ))}
                    </div>
                )}
            </main>

            {showCreate && <CreateNotebookModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}
        </div>
    );
}
