import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { setUser } from '../store';
import { ls_getNotebooks, ls_createNotebook, ls_deleteNotebook } from '../lib/localNotebooks';
import { BookOpen, Plus, Trash2, ChevronRight, LogOut, Loader2, BookMarked, Calendar, Search, FileText } from 'lucide-react';

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
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(8px)' }} onClick={onClose}>
      <div className="rounded-2xl p-8 w-[440px] max-w-[94vw]" style={{ background: '#fff', boxShadow: '0 24px 80px rgba(0,0,0,0.15)' }} onClick={e => e.stopPropagation()} data-testid="create-notebook-modal">
        <h3 className="text-xl font-bold mb-1" style={{ fontFamily: "'Sora', sans-serif", color: '#000', letterSpacing: '-0.03em' }}>New Notebook</h3>
        <p className="text-sm mb-6" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>Create a notebook for a specific course or subject.</p>
        <form onSubmit={submit}>
          <div className="mb-4">
            <label className="block text-xs font-medium mb-2" style={{ color: '#000', fontFamily: "'DM Sans', sans-serif" }}>Title</label>
            <input data-testid="notebook-name-input" className="w-full h-11 px-4 rounded-lg text-sm outline-none focus:ring-2 focus:ring-black/10" style={{ border: '1px solid #E5E5E5', fontFamily: "'DM Sans', sans-serif" }} placeholder="e.g. Digital Signal Processing" value={name} onChange={e => setName(e.target.value)} autoFocus />
          </div>
          <div className="mb-6">
            <label className="block text-xs font-medium mb-2" style={{ color: '#000', fontFamily: "'DM Sans', sans-serif" }}>Course Code</label>
            <input data-testid="notebook-course-input" className="w-full h-11 px-4 rounded-lg text-sm outline-none focus:ring-2 focus:ring-black/10" style={{ border: '1px solid #E5E5E5', fontFamily: "'DM Sans', sans-serif" }} placeholder="e.g. EC301" value={course} onChange={e => setCourse(e.target.value)} />
          </div>
          <div className="flex gap-3 justify-end">
            <button type="button" onClick={onClose} className="h-10 px-5 rounded-lg text-sm font-medium" style={{ border: '1px solid #E5E5E5', color: '#71717A', fontFamily: "'DM Sans', sans-serif" }} data-testid="cancel-create-btn">Cancel</button>
            <button type="submit" disabled={loading || !name || !course} className="h-10 px-6 rounded-lg text-sm font-semibold flex items-center gap-2" style={{ background: '#000', color: '#fff', opacity: (loading || !name || !course) ? 0.4 : 1, fontFamily: "'DM Sans', sans-serif" }} data-testid="confirm-create-btn">
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
      className="group rounded-xl cursor-pointer transition-all hover:-translate-y-0.5"
      style={{ background: '#fff', border: '1px solid #E5E5E5' }}
      onClick={() => onOpen(nb.id)}
    >
      <div className="p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: hasNote ? '#000' : '#F4F4F5' }}>
            <BookMarked size={17} style={{ color: hasNote ? '#fff' : '#A1A1AA' }} strokeWidth={1.8} />
          </div>
          <button
            data-testid={`delete-notebook-${nb.id}`}
            className="opacity-0 group-hover:opacity-100 w-8 h-8 rounded-lg flex items-center justify-center transition-all"
            style={{ color: '#A1A1AA', background: '#F4F4F5' }}
            onClick={async e => { e.stopPropagation(); setDeleting(true); await onDelete(nb.id); setDeleting(false); }}
          >
            {deleting ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
          </button>
        </div>

        <div className="mb-1">
          <div className="font-semibold text-sm" style={{ color: '#000', fontFamily: "'DM Sans', sans-serif" }}>{nb.name}</div>
          <div className="text-xs mt-0.5" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>{nb.course}</div>
        </div>

        <div className="text-xs leading-relaxed my-3 line-clamp-2" style={{ color: '#71717A', minHeight: '2.5em', fontFamily: "'DM Sans', sans-serif" }}>
          {hasNote ? nb.note.replace(/[#*]/g, '').slice(0, 100) + '...' : 'No notes yet'}
        </div>

        <div className="flex items-center justify-between pt-3" style={{ borderTop: '1px solid #F4F4F5' }}>
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1 text-xs" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>
              <Calendar size={11} /> {dateStr}
            </span>
            {totalNodes > 0 && (
              <span className="text-xs px-2 py-0.5 rounded-full font-medium" style={{ background: '#F4F4F5', color: '#000', fontFamily: "'DM Sans', sans-serif" }}>
                {masterCount}/{totalNodes}
              </span>
            )}
          </div>
          <ChevronRight size={14} style={{ color: '#D4D4D8' }} className="group-hover:translate-x-0.5 transition-transform" />
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
    <div className="min-h-screen" style={{ background: '#fff' }} data-testid="dashboard-page">
      {/* Header */}
      <header className="sticky top-0 z-40 h-16 px-10 flex items-center justify-between" style={{ background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(12px)', borderBottom: '1px solid #E5E5E5' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md flex items-center justify-center" style={{ background: '#000' }}>
            <BookOpen size={16} color="#fff" strokeWidth={1.8} />
          </div>
          <span className="font-bold text-base" style={{ fontFamily: "'Sora', sans-serif", color: '#000', letterSpacing: '-0.03em' }}>AuraGraph</span>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: '#000', color: '#fff', fontFamily: "'DM Sans', sans-serif" }}>
              {displayName[0]?.toUpperCase()}
            </div>
            <span className="text-sm font-medium" style={{ color: '#000', fontFamily: "'DM Sans', sans-serif" }}>{displayName}</span>
          </div>
          <button data-testid="logout-btn" onClick={handleLogout} className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium transition-all" style={{ color: '#A1A1AA', border: '1px solid #E5E5E5', fontFamily: "'DM Sans', sans-serif" }}>
            <LogOut size={12} /> Logout
          </button>
        </div>
      </header>

      <main className="max-w-[1100px] mx-auto px-10 py-12">
        <div className="flex items-end justify-between mb-10">
          <div>
            <h1 className="text-3xl font-bold mb-1" style={{ fontFamily: "'Sora', sans-serif", color: '#000', letterSpacing: '-0.04em' }}>Notebooks</h1>
            <p className="text-sm" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>Upload slides & textbooks to create AI-fused study notes</p>
          </div>
          <button data-testid="new-notebook-btn" onClick={() => setShowCreate(true)} className="flex items-center gap-2 h-10 px-5 rounded-lg text-sm font-semibold transition-all active:scale-[0.97]" style={{ background: '#000', color: '#fff', fontFamily: "'DM Sans', sans-serif" }}>
            <Plus size={15} /> New Notebook
          </button>
        </div>

        {notebooks.length > 0 && (
          <div className="mb-8 relative max-w-sm">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2" style={{ color: '#A1A1AA' }} />
            <input
              data-testid="search-notebooks"
              placeholder="Search notebooks..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full h-10 pl-10 pr-4 rounded-lg text-sm outline-none focus:ring-2 focus:ring-black/10"
              style={{ border: '1px solid #E5E5E5', fontFamily: "'DM Sans', sans-serif" }}
            />
          </div>
        )}

        {loading ? (
          <div className="text-center py-24">
            <Loader2 size={24} className="animate-spin mx-auto mb-3" style={{ color: '#D4D4D8' }} />
            <p className="text-sm" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>Loading...</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-24">
            <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-5" style={{ background: '#F4F4F5' }}>
              <FileText size={24} style={{ color: '#D4D4D8' }} strokeWidth={1.5} />
            </div>
            <h3 className="text-lg font-bold mb-1" style={{ color: '#000', fontFamily: "'Sora', sans-serif" }}>
              {search ? 'No results' : 'No notebooks yet'}
            </h3>
            <p className="text-sm mb-7" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>
              {search ? 'Try a different search term.' : 'Create your first notebook to get started.'}
            </p>
            {!search && (
              <button data-testid="create-first-notebook-btn" onClick={() => setShowCreate(true)} className="inline-flex items-center gap-2 h-10 px-6 rounded-lg text-sm font-semibold" style={{ background: '#000', color: '#fff', fontFamily: "'DM Sans', sans-serif" }}>
                <Plus size={15} /> Create Notebook
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
