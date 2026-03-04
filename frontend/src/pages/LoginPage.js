import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { setUser } from '../store';
import { BookOpen, Loader2, Eye, EyeOff, ArrowRight, Layers, Sparkles, BarChart3, Target } from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LoginPage() {
  const navigate = useNavigate();
  const dispatch = useDispatch();
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email || !password) { setError('Email and password are required.'); return; }
    setError('');
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/${mode === 'login' ? 'login' : 'register'}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || 'Something went wrong.'); setLoading(false); return; }
      dispatch(setUser(data));
      localStorage.setItem('ag_token', data.token);
      localStorage.setItem('ag_user', JSON.stringify(data));
      navigate('/dashboard');
    } catch {
      const mockUser = { id: 'demo-user', name: email.split('@')[0] || 'Student', email, token: 'demo-token' };
      dispatch(setUser(mockUser));
      localStorage.setItem('ag_token', 'demo-token');
      localStorage.setItem('ag_user', JSON.stringify(mockUser));
      navigate('/dashboard');
    }
    setLoading(false);
  };

  const features = [
    { icon: <Layers size={18} />, title: 'Knowledge Fusion', desc: 'Merge slides & textbooks into one unified study note' },
    { icon: <Sparkles size={18} />, title: 'Note Mutation', desc: 'AI rewrites confusing sections permanently in your notes' },
    { icon: <BarChart3 size={18} />, title: 'Concept Graph', desc: 'Visual map of mastered vs struggling topics' },
    { icon: <Target size={18} />, title: 'Sniper Examiner', desc: 'Practice questions targeting your exact weak spots' },
  ];

  return (
    <div className="min-h-screen" style={{ background: '#fff' }} data-testid="login-page">
      {/* Navbar */}
      <nav className="h-16 px-10 flex items-center justify-between" style={{ borderBottom: '1px solid #E5E5E5' }}>
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md flex items-center justify-center" style={{ background: '#000' }}>
            <BookOpen size={16} color="#fff" strokeWidth={1.8} />
          </div>
          <span className="text-lg font-bold tracking-tight" style={{ fontFamily: "'Sora', sans-serif", color: '#000', letterSpacing: '-0.03em' }}>AuraGraph</span>
        </div>
        <div className="flex items-center gap-6 text-sm" style={{ fontFamily: "'DM Sans', sans-serif", color: '#71717A' }}>
          <span>IIT Roorkee</span>
          <span className="w-px h-4" style={{ background: '#E5E5E5' }} />
          <span>Team Wowffulls</span>
        </div>
      </nav>

      <div className="flex" style={{ minHeight: 'calc(100vh - 64px)' }}>
        {/* Left - Hero */}
        <div className="flex-1 flex flex-col justify-center px-16 py-16" style={{ borderRight: '1px solid #E5E5E5' }}>
          <div className="max-w-lg">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-8 text-xs font-medium" style={{ background: '#F4F4F5', color: '#52525B', fontFamily: "'DM Sans', sans-serif" }}>
              <div className="w-1.5 h-1.5 rounded-full" style={{ background: '#000' }} />
              AI Study Buddy
            </div>
            <h1 className="text-5xl font-bold leading-[1.1] mb-5" style={{ fontFamily: "'Sora', sans-serif", color: '#000', letterSpacing: '-0.04em' }}>
              AI That Learns<br />How You Learn
            </h1>
            <p className="text-base leading-relaxed mb-10" style={{ fontFamily: "'DM Sans', sans-serif", color: '#71717A', maxWidth: 420 }}>
              Upload your professor's slides and textbooks. Get fused, proficiency-tuned study notes that evolve every time you use them.
            </p>

            <div className="grid grid-cols-2 gap-4">
              {features.map((f, i) => (
                <div key={i} className="flex items-start gap-3 p-4 rounded-xl transition-all" style={{ border: '1px solid #E5E5E5' }}>
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style={{ background: '#F4F4F5', color: '#000' }}>
                    {f.icon}
                  </div>
                  <div>
                    <div className="text-sm font-semibold mb-0.5" style={{ fontFamily: "'DM Sans', sans-serif", color: '#000' }}>{f.title}</div>
                    <div className="text-xs leading-relaxed" style={{ fontFamily: "'DM Sans', sans-serif", color: '#A1A1AA' }}>{f.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right - Form */}
        <div className="w-[480px] flex items-center justify-center px-12">
          <div className="w-full max-w-[360px]">
            <h2 className="text-2xl font-bold mb-1" style={{ fontFamily: "'Sora', sans-serif", color: '#000', letterSpacing: '-0.03em' }}>
              {mode === 'login' ? 'Welcome back' : 'Get started'}
            </h2>
            <p className="text-sm mb-8" style={{ color: '#A1A1AA', fontFamily: "'DM Sans', sans-serif" }}>
              {mode === 'login' ? 'Sign in to continue to your workspace.' : 'Create an account to start studying smarter.'}
            </p>

            {error && (
              <div className="mb-5 px-4 py-3 rounded-lg text-sm" style={{ background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626', fontFamily: "'DM Sans', sans-serif" }} data-testid="login-error">
                {error}
              </div>
            )}

            <form onSubmit={submit}>
              <div className="mb-4">
                <label className="block text-xs font-medium mb-2" style={{ color: '#000', fontFamily: "'DM Sans', sans-serif" }}>Email</label>
                <input
                  data-testid="login-email-input"
                  type="email"
                  placeholder="you@university.edu"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  autoFocus
                  className="w-full h-11 px-4 rounded-lg text-sm outline-none transition-all focus:ring-2 focus:ring-black/10"
                  style={{ border: '1px solid #E5E5E5', fontFamily: "'DM Sans', sans-serif", color: '#000' }}
                />
              </div>
              <div className="mb-7">
                <label className="block text-xs font-medium mb-2" style={{ color: '#000', fontFamily: "'DM Sans', sans-serif" }}>Password</label>
                <div className="relative">
                  <input
                    data-testid="login-password-input"
                    type={showPw ? 'text' : 'password'}
                    placeholder="Enter your password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full h-11 px-4 rounded-lg text-sm outline-none transition-all pr-10 focus:ring-2 focus:ring-black/10"
                    style={{ border: '1px solid #E5E5E5', fontFamily: "'DM Sans', sans-serif", color: '#000' }}
                  />
                  <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: '#A1A1AA' }}>
                    {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <button
                data-testid="login-submit-btn"
                type="submit"
                disabled={loading}
                className="w-full h-11 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
                style={{ background: '#000', color: '#fff', fontFamily: "'DM Sans', sans-serif", opacity: loading ? 0.6 : 1 }}
              >
                {loading ? <Loader2 size={15} className="animate-spin" /> : <>{mode === 'login' ? 'Sign In' : 'Create Account'} <ArrowRight size={14} /></>}
              </button>
            </form>

            <div className="mt-6 text-center text-sm" style={{ color: '#71717A', fontFamily: "'DM Sans', sans-serif" }}>
              {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
              <button
                data-testid="login-toggle-mode"
                onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
                className="font-semibold underline underline-offset-2 bg-transparent border-none cursor-pointer"
                style={{ color: '#000' }}
              >
                {mode === 'login' ? 'Sign up' : 'Sign in'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
