import React, { useState, useEffect } from 'react';

const FUSE_STEPS = [
    { label: 'Uploading files', icon: '📤' },
    { label: 'Extracting slides & notes', icon: '📄' },
    { label: 'Extracting textbook content', icon: '📚' },
    { label: 'Running Fusion Agent', icon: '🧠' },
    { label: 'Calibrating to your level', icon: '🎯' },
    { label: 'Verifying accuracy', icon: '🔍' },
    { label: 'Building concept map', icon: '🕸️' },
    { label: 'Finalising notes', icon: '✨' },
];

export default function FuseProgressBar({ active, forceStep = null }) {
    const [step, setStep] = useState(0);
    const [dots, setDots] = useState('');
    const [overdue, setOverdue] = useState(false);
    const displayStep = forceStep !== null ? forceStep : step;

    useEffect(() => {
        if (!active) { setStep(0); setDots(''); setOverdue(false); return; }
        const st = setInterval(() => setStep(s => {
            if (s < 4) return s + 1;
            if (s === 4) return 3;
            return s;
        }), 3500);
        const dt = setInterval(() => setDots(d => d.length >= 3 ? '' : d + '.'), 400);
        const ot = setTimeout(() => setOverdue(true), 45_000);
        return () => { clearInterval(st); clearInterval(dt); clearTimeout(ot); };
    }, [active]);

    if (!active) return null;
    return (
        <div style={{ marginBottom: 20, background: overdue ? '#FFFBEB' : 'var(--surface)', border: `1px solid ${overdue ? '#FDE68A' : 'var(--border)'}`, borderRadius: 12, padding: '16px 20px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <span style={{ fontSize: 22 }}>{FUSE_STEPS[displayStep].icon}</span>
                <div>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{FUSE_STEPS[displayStep].label}{dots}</div>
                    <div style={{ fontSize: 11, color: overdue ? '#92400E' : 'var(--text3)', marginTop: 2, fontWeight: overdue ? 600 : 400 }}>
                        {overdue
                            ? '⚠️ Large upload detected — AI is still working, please keep this tab open'
                            : displayStep === 5
                                ? 'Cross-checking formulas and definitions against source material…'
                                : `Step ${displayStep + 1} of ${FUSE_STEPS.length} — processing your materials${displayStep >= 3 ? ' (large books may take a few minutes)' : ''}`}
                    </div>
                </div>
            </div>
            <div style={{ height: 4, background: 'var(--border)', borderRadius: 4, overflow: 'hidden' }}>
                <div style={{ height: '100%', borderRadius: 4, background: 'linear-gradient(90deg, #7C3AED, #2563EB)', width: `${((displayStep + 1) / FUSE_STEPS.length) * 100}%`, transition: 'width 0.6s ease' }} />
            </div>
            <div style={{ display: 'flex', gap: 5, marginTop: 10 }}>
                {FUSE_STEPS.map((s, i) => (
                    <div key={i} title={s.label} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= displayStep ? '#7C3AED' : 'var(--border)', transition: 'background 0.4s' }} />
                ))}
            </div>
        </div>
    );
}
