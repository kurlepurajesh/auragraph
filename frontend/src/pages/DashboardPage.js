import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { setUser } from '../store';
import { ls_getNotebooks, ls_createNotebook, ls_deleteNotebook } from '../lib/localNotebooks';
import { BookOpen, Plus, Trash2, ChevronRight, LogOut, Loader2, BookMarked, Calendar, Search } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function authHeaders() {
  const token = localStorage.getItem('ag_token') || 'demo-token';
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}
function getUserId() {
  try { return JSON.parse(localStorage.getItem('ag_user'))?.id || 'demo-user'; } catch { return 'demo-user'; }
}

function CreateModal({ onClose, onCreate }) {
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
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }} onClick={onClose}>
      <div className="rounded-2xl p-7 w-[440px] max-w-[94vw]" style={{ background: '#fff', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }} onClick={e => e.stopPropagation()} data-testid="create-notebook-modal">
        <h3 className="text-lg font-bold mb-1" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>New Notebook</h3>
        <p className="text-xs mb-5" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Create a notebook for a specific course or subject.</p>
        <form onSubmit={submit}>
          <div className="mb-3">
            <label className="block text-xs font-medium mb-1 uppercase tracking-wider" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Title</label>
            <input data-testid="notebook-name-input" className="w-full px-3 py-2.5 rounded-lg text-sm outline-none" style={{ border: '1px solid #D4D4D8', fontFamily: "'Manrope', sans-serif" }} placeholder="e.g. Digital Signal Processing" value={name} onChange={e => setName(e.target.value)} autoFocus />
          </div>
          <div className="mb-5">
            <label className="block text-xs font-medium mb-1 uppercase tracking-wider" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Course</label>
            <input data-testid="notebook-course-input" className="w-full px-3 py-2.5 rounded-lg text-sm outline-none" style={{ border: '1px solid #D4D4D8', fontFamily: "'Manrope', sans-serif" }} placeholder="e.g. EC301" value={course} onChange={e => setCourse(e.target.value)} />
          </div>
          <div className="flex gap-3 justify-end">
            <button type="button" onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-medium" style={{ border: '1px solid #D4D4D8', color: '#52525B', fontFamily: "'Manrope', sans-serif" }} data-testid="cancel-create-btn">Cancel</button>
            <button type="submit" disabled={loading || !name || !course} className="px-5 py-2 rounded-lg text-sm font-semibold flex items-center gap-2" style={{ background: '#0F5132', color: '#fff', opacity: (loading || !name || !course) ? 0.5 : 1, fontFamily: "'Manrope', sans-serif" }} data-testid="confirm-create-btn">
              {loading ? <Loader2 size={14} className="animate-spin" /> : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function NotebookCard({ nb, onOpen, onDelete }) {
  const [deleting, setDeleting] = useState(false);
  const dateStr = new Date(nb.created_at).toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
  const hasNote = nb.note?.length > 0;
  const masterCount = nb.graph?.nodes?.filter(n => n.status === 'mastered').length || 0;
  const totalNodes = nb.graph?.nodes?.length || 0;

  return (
    <div
      data-testid={`notebook-card-${nb.id}`}
      className="group rounded-xl overflow-hidden cursor-pointer transition-all hover:-translate-y-1"
      style={{ background: '#fff', border: '1px solid #E5E5E5', boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}
      onClick={() => onOpen(nb.id)}
    >
      {/* Color bar */}
      <div className="h-1.5" style={{ background: hasNote ? 'linear-gradient(90deg, #0F5132, #0D9488)' : '#E5E5E5' }} />
      <div className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: '#F6F5F0' }}>
              <BookMarked size={18} style={{ color: '#0F5132' }} strokeWidth={1.5} />
            </div>
            <div>
              <div className="font-semibold text-sm" style={{ color: '#1A1A1A', fontFamily: "'Manrope', sans-serif" }}>{nb.name}</div>
              <div className="text-xs mt-0.5" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>{nb.course}</div>
            </div>
          </div>
          <button
            data-testid={`delete-notebook-${nb.id}`}
            className="opacity-0 group-hover:opacity-100 p-1.5 rounded-lg transition-all"
            style={{ color: '#A1A1AA' }}
            onClick={async e => { e.stopPropagation(); setDeleting(true); await onDelete(nb.id); setDeleting(false); }}
          >
            {deleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
        </div>

        <div className="text-xs leading-relaxed mb-3 line-clamp-2" style={{ color: '#52525B', minHeight: '2.5em', fontFamily: "'Manrope', sans-serif" }}>
          {hasNote ? nb.note.replace(/[#*]/g, '').slice(0, 120) + '...' : 'No notes yet - upload slides & textbook to begin'}
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1 text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>
              <Calendar size={11} /> {dateStr}
            </span>
            {totalNodes > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: '#ECFDF5', color: '#0F5132', fontFamily: "'Manrope', sans-serif" }}>
                {masterCount}/{totalNodes} mastered
              </span>
            )}
          </div>
          <ChevronRight size={14} style={{ color: '#A1A1AA' }} className="group-hover:translate-x-1 transition-transform" />
        </div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const user = useSelector(s => s.app.user);
  const [notebooks, setNotebooks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState('');
  const userId = getUserId();

  const loadNotebooks = async () => {
    try {
      const res = await fetch(`${API}/notebooks`, { headers: authHeaders() });
      if (res.ok) { setNotebooks(await res.json()); setLoading(false); return; }
    } catch {}
    setNotebooks(ls_getNotebooks(userId));
    setLoading(false);
  };

  useEffect(() => { loadNotebooks(); }, []);

  const handleCreate = async (name, course) => {
    let nb;
    try {
      const res = await fetch(`${API}/notebooks`, { method: 'POST', headers: authHeaders(), body: JSON.stringify({ name, course }) });
      if (res.ok) nb = await res.json();
    } catch {}
    if (!nb) nb = ls_createNotebook(userId, name, course);
    setNotebooks(prev => [nb, ...prev]);
  };

  const handleDelete = async (id) => {
    try { await fetch(`${API}/notebooks/${id}`, { method: 'DELETE', headers: authHeaders() }); } catch {}
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
  const filtered = notebooks.filter(nb => !search || nb.name.toLowerCase().includes(search.toLowerCase()) || nb.course.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="min-h-screen" style={{ background: '#FDFBF7' }} data-testid="dashboard-page">
      {/* Header */}
      <header className="sticky top-0 z-40 px-6 h-16 flex items-center justify-between" style={{ background: 'rgba(253,251,247,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid #E5E5E5' }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: '#0F5132' }}>
            <BookOpen size={15} color="white" strokeWidth={1.5} />
          </div>
          <span className="font-bold text-base tracking-tight" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>AuraGraph</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: '#0F5132', color: '#fff', fontFamily: "'Manrope', sans-serif" }}>
            {displayName[0]?.toUpperCase()}
          </div>
          <span className="text-sm font-medium hidden sm:inline" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>{displayName}</span>
          <button data-testid="logout-btn" onClick={handleLogout} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
            <LogOut size={13} /> Logout
          </button>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        <div className="flex items-end justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold tracking-tight mb-1" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>My Notebooks</h1>
            <p className="text-sm" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Upload slides & textbooks to create AI-fused study notes</p>
          </div>
          <button data-testid="new-notebook-btn" onClick={() => setShowCreate(true)} className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold transition-all active:scale-[0.97]" style={{ background: '#0F5132', color: '#fff', fontFamily: "'Manrope', sans-serif" }}>
            <Plus size={15} /> New Notebook
          </button>
        </div>

        {/* Search */}
        {notebooks.length > 0 && (
          <div className="mb-6 relative max-w-sm">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#A1A1AA' }} />
            <input
              data-testid="search-notebooks"
              placeholder="Search notebooks..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none"
              style={{ border: '1px solid #E5E5E5', background: '#fff', fontFamily: "'Manrope', sans-serif" }}
            />
          </div>
        )}

        {loading ? (
          <div className="text-center py-20">
            <Loader2 size={28} className="animate-spin mx-auto mb-3" style={{ color: '#A1A1AA' }} />
            <p className="text-sm" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>Loading notebooks...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-20">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5" style={{ background: '#F6F5F0' }}>
              <BookOpen size={28} style={{ color: '#A1A1AA' }} strokeWidth={1.5} />
            </div>
            <h3 className="font-semibold mb-2" style={{ color: '#1A1A1A', fontFamily: "'Playfair Display', serif" }}>
              {search ? 'No matching notebooks' : 'No notebooks yet'}
            </h3>
            <p className="text-sm mb-6" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif", lineHeight: 1.7 }}>
              Create your first notebook for a course.
            </p>
            {!search && (
              <button data-testid="create-first-notebook-btn" onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold" style={{ background: '#0F5132', color: '#fff', fontFamily: "'Manrope', sans-serif" }}>
                <Plus size={15} /> Create First Notebook
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {filtered.map(nb => (
              <NotebookCard key={nb.id} nb={nb} onOpen={id => navigate(`/notebook/${id}`)} onDelete={handleDelete} />
            ))}
          </div>
        )}
      </main>

      {showCreate && <CreateModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />}
    </div>
  );
}
