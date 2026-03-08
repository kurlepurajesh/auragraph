import React, { useState, useEffect } from 'react';
import { Copy, Check, Download, Printer, Undo2 } from 'lucide-react';

export function CopyNoteButton({ note }) {
    const [copied, setCopied] = useState(false);
    const copy = async () => {
        try { await navigator.clipboard.writeText(note); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch { }
    };
    return (
        <button className="btn btn-ghost btn-sm" onClick={copy} title="Copy full note as Markdown" style={{ fontSize: 12, gap: 5 }}>
            {copied ? <Check size={12} color="#10B981" /> : <Copy size={12} />}
            {copied ? 'Copied!' : 'Copy MD'}
        </button>
    );
}

export function DownloadNoteButton({ note, name }) {
    const dl = () => {
        const b = new Blob([note], { type: 'text/markdown' });
        const u = URL.createObjectURL(b);
        const a = document.createElement('a');
        a.href = u; a.download = `${name || 'notes'}.md`;
        document.body.appendChild(a); a.click();
        document.body.removeChild(a); URL.revokeObjectURL(u);
    };
    return (
        <button className="btn btn-ghost btn-sm" onClick={dl} title="Download as .md" style={{ fontSize: 12, gap: 5 }}>
            <Download size={12} /> Export
        </button>
    );
}

export function PrintNoteButton({ onPrint }) {
    return (
        <button className="btn btn-ghost btn-sm" onClick={onPrint} title="Export as PDF – prints all pages" style={{ fontSize: 12, gap: 5 }}>
            <Printer size={12} /> Print PDF
        </button>
    );
}

const UNDO_TTL_MS = 5 * 60 * 1000; // 5 minutes

export function UndoToast({ toast, onUndo, onDismiss }) {
    const [remaining, setRemaining] = useState(() => Math.max(0, toast.expiresAt - Date.now()));

    useEffect(() => {
        const tick = setInterval(() => {
            const r = Math.max(0, toast.expiresAt - Date.now());
            setRemaining(r);
            if (r === 0) onDismiss();
        }, 1000);
        return () => clearInterval(tick);
    }, [toast.expiresAt, onDismiss]);

    const pct = (remaining / UNDO_TTL_MS) * 100;
    const mins = Math.floor(remaining / 60000);
    const secs = Math.floor((remaining % 60000) / 1000);
    const timeStr = mins > 0 ? `${mins}:${String(secs).padStart(2, '0')}` : `${secs}s`;
    const barColor = pct > 50 ? '#10B981' : pct > 20 ? '#F59E0B' : '#EF4444';

    return (
        <div className="no-print" style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 10000, background: '#1E1B4B', borderRadius: 12, padding: '12px 16px', boxShadow: '0 8px 32px rgba(0,0,0,0.45)', display: 'flex', flexDirection: 'column', gap: 8, minWidth: 270, animation: 'slideUpFade 0.25s ease' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                    <Check size={13} color="#10B981" />
                    <span style={{ fontSize: 13, fontWeight: 600, color: '#E0E7FF' }}>{toast.label}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button onClick={onUndo} style={{ background: '#4F46E5', border: 'none', color: '#fff', borderRadius: 6, padding: '4px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4 }}>
                        <Undo2 size={11} /> Undo
                    </button>
                    <button onClick={onDismiss} style={{ background: 'none', border: '1px solid #4C1D95', color: '#A78BFA', borderRadius: 5, padding: '3px 7px', fontSize: 11, cursor: 'pointer' }}>✕</button>
                </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <div style={{ flex: 1, height: 3, background: 'rgba(255,255,255,0.1)', borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ height: '100%', borderRadius: 2, background: barColor, width: `${pct}%`, transition: 'width 1s linear, background 0.5s' }} />
                </div>
                <span style={{ fontSize: 10, color: '#6B7280', fontVariantNumeric: 'tabular-nums', minWidth: 34, textAlign: 'right' }}>{timeStr}</span>
            </div>
        </div>
    );
}
