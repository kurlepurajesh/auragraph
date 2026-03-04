import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { setUser } from '../store';
import { BookOpen, Loader2, Eye, EyeOff, ArrowRight } from 'lucide-react';

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

  return (
    <div className="min-h-screen flex" data-testid="login-page">
      {/* Left - Form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12" style={{ background: '#FDFBF7' }}>
        <div className="w-full max-w-[400px]">
          {/* Logo */}
          <div className="mb-10">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-11 h-11 rounded-xl flex items-center justify-center" style={{ background: '#0F5132' }}>
                <BookOpen size={20} color="white" strokeWidth={1.5} />
              </div>
              <span className="text-xl font-bold tracking-tight" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>AuraGraph</span>
            </div>
            <h1 className="text-3xl font-bold tracking-tight mb-2" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>
              {mode === 'login' ? 'Welcome back' : 'Create account'}
            </h1>
            <p className="text-sm" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
              {mode === 'login' ? 'Sign in to your study workspace.' : 'Start building your knowledge graph.'}
            </p>
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg text-sm" style={{ background: '#FEF2F2', border: '1px solid #FECACA', color: '#DC2626' }} data-testid="login-error">
              {error}
            </div>
          )}

          <form onSubmit={submit}>
            <div className="mb-4">
              <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Email</label>
              <input
                data-testid="login-email-input"
                type="email"
                placeholder="you@university.edu"
                value={email}
                onChange={e => setEmail(e.target.value)}
                autoFocus
                className="w-full px-4 py-3 rounded-lg text-sm outline-none transition-all"
                style={{ border: '1px solid #D4D4D8', background: '#fff', fontFamily: "'Manrope', sans-serif" }}
              />
            </div>
            <div className="mb-6">
              <label className="block text-xs font-medium mb-1.5 uppercase tracking-wider" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Password</label>
              <div className="relative">
                <input
                  data-testid="login-password-input"
                  type={showPw ? 'text' : 'password'}
                  placeholder="Enter your password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  className="w-full px-4 py-3 rounded-lg text-sm outline-none transition-all pr-10"
                  style={{ border: '1px solid #D4D4D8', background: '#fff', fontFamily: "'Manrope', sans-serif" }}
                />
                <button type="button" onClick={() => setShowPw(!showPw)} className="absolute right-3 top-1/2 -translate-y-1/2" style={{ color: '#A1A1AA' }}>
                  {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              data-testid="login-submit-btn"
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
              style={{ background: '#0F5132', color: '#fff', fontFamily: "'Manrope', sans-serif", opacity: loading ? 0.7 : 1 }}
            >
              {loading ? <Loader2 size={16} className="animate-spin" /> : <>{mode === 'login' ? 'Sign In' : 'Create Account'} <ArrowRight size={15} /></>}
            </button>
          </form>

          <div className="mt-6 text-center text-sm" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
            {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
            <button
              data-testid="login-toggle-mode"
              onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
              className="font-semibold underline underline-offset-2 bg-transparent border-none cursor-pointer"
              style={{ color: '#0F5132' }}
            >
              {mode === 'login' ? 'Sign up' : 'Sign in'}
            </button>
          </div>

          <p className="text-center mt-8 text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>
            IIT Roorkee &middot; Team Wowffulls &middot; AI Study Buddy
          </p>
        </div>
      </div>

      {/* Right - Visual */}
      <div className="hidden lg:flex flex-1 items-center justify-center relative overflow-hidden" style={{ background: '#0F5132' }}>
        <div className="absolute inset-0 opacity-10" style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg width=\'60\' height=\'60\' viewBox=\'0 0 60 60\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cg fill=\'none\' fill-rule=\'evenodd\'%3E%3Cg fill=\'%23ffffff\' fill-opacity=\'0.3\'%3E%3Cpath d=\'M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E")' }} />
        <div className="text-center px-12 relative z-10">
          <div className="w-20 h-20 mx-auto mb-8 rounded-2xl flex items-center justify-center" style={{ background: 'rgba(255,255,255,0.15)', backdropFilter: 'blur(10px)' }}>
            <BookOpen size={36} color="white" strokeWidth={1.5} />
          </div>
          <h2 className="text-3xl font-bold text-white mb-4" style={{ fontFamily: "'Playfair Display', serif" }}>
            AI That Learns<br />How You Learn
          </h2>
          <p className="text-sm leading-relaxed max-w-sm mx-auto" style={{ color: 'rgba(255,255,255,0.7)', fontFamily: "'Manrope', sans-serif" }}>
            Upload slides and textbooks. Get fused, proficiency-tuned notes. Watch your knowledge graph grow.
          </p>
          <div className="mt-10 flex items-center justify-center gap-6">
            {['Fusion', 'Mutation', 'Graph', 'Examiner'].map((f, i) => (
              <div key={f} className="text-center" style={{ animationDelay: `${i * 0.1}s` }}>
                <div className="w-10 h-10 rounded-lg mx-auto mb-2 flex items-center justify-center text-xs font-bold" style={{ background: 'rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.8)', fontFamily: "'Manrope', sans-serif" }}>
                  {i + 1}
                </div>
                <span className="text-xs" style={{ color: 'rgba(255,255,255,0.6)', fontFamily: "'Manrope', sans-serif" }}>{f}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
