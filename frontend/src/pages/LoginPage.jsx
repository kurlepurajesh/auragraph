import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDispatch } from 'react-redux';
import { setUser } from '../store';
import { Loader2, Sparkles } from 'lucide-react';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function LoginPage() {
    const navigate = useNavigate();
    const dispatch = useDispatch();

    const [mode, setMode] = useState('login'); // 'login' | 'register'
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
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
            // Demo mode - mock login
            const mockUser = { id: 'demo-user', name: email.split('@')[0] || 'Student', email, token: 'demo-token' };
            dispatch(setUser(mockUser));
            localStorage.setItem('ag_token', 'demo-token');
            localStorage.setItem('ag_user', JSON.stringify(mockUser));
            navigate('/dashboard');
        }
        setLoading(false);
    };

    return (
        <div style={{ minHeight: '100vh', background: 'var(--surface)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px' }}>
            <div style={{ width: '100%', maxWidth: '400px' }}>
                {/* Logo */}
                <div style={{ textAlign: 'center', marginBottom: '36px' }}>
                    <div style={{ display: 'inline-block', background: '#fff', borderRadius: 14, padding: '10px 20px', marginBottom: 16, boxShadow: '0 2px 12px rgba(0,0,0,0.08)' }}>
                        <img src="/logo.jpeg" alt="AuraGraph" style={{ height: 52, width: 'auto' }} />
                    </div>
                    <p style={{ color: 'var(--text3)', marginTop: 4, fontSize: 14 }}>Your AI-powered study companion</p>
                </div>

                {/* Card */}
                <div className="card" style={{ padding: '32px' }}>
                    <h2 style={{ fontSize: '18px', fontWeight: 700, marginBottom: 4 }}>
                        {mode === 'login' ? 'Welcome back' : 'Create your account'}
                    </h2>
                    <p style={{ fontSize: 13, color: 'var(--text3)', marginBottom: 24 }}>
                        {mode === 'login' ? 'Sign in to access your notebooks.' : 'Start building your knowledge graph.'}
                    </p>

                    {error && (
                        <div style={{ padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, fontSize: 13, color: 'var(--danger)', marginBottom: 16 }}>
                            {error}
                        </div>
                    )}

                    <form onSubmit={submit}>
                        <div style={{ marginBottom: 14 }}>
                            <label>Email address</label>
                            <input className="input" type="email" placeholder="you@university.edu" value={email} onChange={e => setEmail(e.target.value)} autoFocus />
                        </div>
                        <div style={{ marginBottom: 22 }}>
                            <label>Password</label>
                            <input className="input" type="password" placeholder="••••••••" value={password} onChange={e => setPassword(e.target.value)} />
                        </div>
                        <button type="submit" className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={loading}>
                            {loading ? <Loader2 className="spin" size={18} /> : mode === 'login' ? 'Sign In' : 'Create Account'}
                        </button>
                    </form>

                    <div style={{ marginTop: 20, textAlign: 'center', fontSize: 13, color: 'var(--text3)' }}>
                        {mode === 'login' ? "Don't have an account? " : 'Already have an account? '}
                        <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }} style={{ background: 'none', border: 'none', color: 'var(--text)', fontWeight: 600, cursor: 'pointer', textDecoration: 'underline', fontSize: 13 }}>
                            {mode === 'login' ? 'Sign up' : 'Sign in'}
                        </button>
                    </div>
                </div>

                <p style={{ textAlign: 'center', color: 'var(--text3)', fontSize: 12, marginTop: 20 }}>
                    IIT Roorkee · Team Wowffulls · Hackathon Prototype
                </p>
            </div>
        </div>
    );
}
