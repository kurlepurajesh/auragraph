/**
 * ShortNotesModal — AI-generated cheatsheet for a notebook.
 * Renders streamed markdown in a full-screen-style modal.
 * Downloadable as .md file.
 */
import React, { useState, useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { X, Loader2, Download, RefreshCw, Zap, Undo2, Redo2 } from 'lucide-react';
import { API, authHeaders } from './utils';

export default function ShortNotesModal({ notebookId, notebookName, proficiency, onClose, darkMode = false }) {
    const [content, setContent] = useState('');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');
    const [hasPrevious, setHasPrevious] = useState(false);
    const [previewMode, setPreviewMode] = useState('latest');
    const scrollRef = useRef(null);

    const loadExisting = async () => {
        const res = await fetch(`${API}/api/notebooks/${notebookId}/short-notes`, {
            headers: { ...authHeaders() },
        });
        if (!res.ok) return null;
        const data = await res.json().catch(() => ({}));
        return data;
    };

    const generate = async () => {
        setLoading(true);
        setError('');
        setPreviewMode('latest');
        try {
            const res = await fetch(`${API}/api/notebooks/${notebookId}/short-notes`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            });
            if (!res.ok) {
                const j = await res.json().catch(() => ({}));
                throw new Error(j.detail || `HTTP ${res.status}`);
            }
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const parts = buf.split('\n\n');
                buf = parts.pop();
                for (const part of parts) {
                    const line = part.trim();
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const ev = JSON.parse(line.slice(6));
                        if (ev.content) {
                            setContent(ev.content);
                            setHasPrevious(!!ev.has_previous);
                            setPreviewMode(ev.preview_mode || 'latest');
                        }
                    } catch { }
                }
            }
        } catch (e) {
            setError(e.message || 'Failed to generate. Try again.');
        }
        setLoading(false);
    };

    const undoPreview = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch(`${API}/api/notebooks/${notebookId}/short-notes/undo-preview`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            });
            if (!res.ok) {
                const j = await res.json().catch(() => ({}));
                throw new Error(j.detail || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setContent(data.content || '');
            setHasPrevious(!!data.has_previous);
            setPreviewMode(data.preview_mode || 'undo');
        } catch (e) {
            setError(e.message || 'Could not preview previous version.');
        }
        setLoading(false);
    };

    const redoPreview = async () => {
        setLoading(true);
        setError('');
        try {
            const res = await fetch(`${API}/api/notebooks/${notebookId}/short-notes/redo-preview`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
            });
            if (!res.ok) {
                const j = await res.json().catch(() => ({}));
                throw new Error(j.detail || `HTTP ${res.status}`);
            }
            const data = await res.json();
            setContent(data.content || '');
            setHasPrevious(!!data.has_previous);
            setPreviewMode('latest');
        } catch (e) {
            setError(e.message || 'Could not return to latest version.');
        }
        setLoading(false);
    };

    useEffect(() => {
        (async () => {
            setLoading(true);
            setError('');
            try {
                const existing = await loadExisting();
                if (existing?.content) {
                    setContent(existing.content);
                    setHasPrevious(!!existing.has_previous);
                    setPreviewMode(existing.preview_mode || 'latest');
                    setLoading(false);
                    return;
                }
            } catch { }
            await generate();
        })();
    }, [notebookId]);

    const download = () => {
        const workspaceRoot = document.querySelector('.notebook-workspace-root');
        if (!workspaceRoot) {
            window.print();
            return;
        }

        const existing = document.getElementById('ag-shortnotes-print-root');
        if (existing) existing.remove();

        const printRoot = document.createElement('div');
        printRoot.id = 'ag-shortnotes-print-root';

        const page = document.createElement('div');
        page.className = 'ag-print-page';

        const meta = document.createElement('div');
        meta.style.fontSize = '10px';
        meta.style.fontWeight = '700';
        meta.style.color = '#9CA3AF';
        meta.style.textTransform = 'uppercase';
        meta.style.letterSpacing = '0.1em';
        meta.style.fontFamily = 'Inter,sans-serif';
        meta.style.marginBottom = '16px';
        meta.style.paddingBottom = '10px';
        meta.style.borderBottom = '1px solid #E5E7EB';
        meta.textContent = `${notebookName || 'Quick Review'} · Short Notes`;

        const title = document.createElement('h1');
        title.textContent = `Quick Review Cheatsheet: ${notebookName || 'Notebook'}`;
        title.style.margin = '0 0 12px 0';
        title.style.fontSize = '22px';
        title.style.lineHeight = '1.25';
        title.style.color = '#111827';

        const body = document.createElement('div');
        body.className = 'ag-shortnotes-print-content';
        const rendered = document.querySelector('.short-notes-content');
        if (rendered) {
            body.appendChild(rendered.cloneNode(true));
        } else {
            body.textContent = content || '';
        }

        page.appendChild(meta);
        page.appendChild(title);
        page.appendChild(body);
        printRoot.appendChild(page);
        workspaceRoot.appendChild(printRoot);

        const cleanup = () => {
            document.body.classList.remove('ag-shortnotes-print-mode');
            const node = document.getElementById('ag-shortnotes-print-root');
            if (node) node.remove();
            window.removeEventListener('afterprint', cleanup);
        };

        document.body.classList.add('ag-shortnotes-print-mode');
        window.addEventListener('afterprint', cleanup);
        window.print();
        setTimeout(cleanup, 1200);
    };

    return (
        <div
            onClick={onClose}
            style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 9000, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '24px 16px', overflowY: 'auto' }}
        >
            <div
                onClick={e => e.stopPropagation()}
                style={{ width: '100%', maxWidth: 760, background: 'var(--bg)', borderRadius: 18, boxShadow: '0 24px 80px rgba(0,0,0,0.3)', overflow: 'hidden', marginTop: 8 }}
            >
                {/* Header */}
                <div style={{ background: 'linear-gradient(135deg, #0f0a1e, #1a0f3d)', padding: '18px 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{ width: 40, height: 40, borderRadius: 12, background: 'rgba(124,58,237,0.3)', border: '1px solid rgba(124,58,237,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Zap size={20} color="#A78BFA" />
                        </div>
                        <div>
                            <div style={{ fontSize: 16, fontWeight: 800, color: '#fff' }}>Quick Review Cheatsheet</div>
                            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.55)', marginTop: 1 }}>
                                {notebookName} · {proficiency} · doubts + mastery focused
                            </div>
                        </div>
                    </div>
                    <div style={{ display: 'flex', gap: 8 }}>
                        {!loading && content && (
                            <>
                                <button onClick={download} title="Download as PDF"
                                    style={{ padding: '7px 12px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 600 }}>
                                    <Download size={13} /> PDF
                                </button>
                                {hasPrevious && previewMode === 'latest' && (
                                    <button onClick={undoPreview} title="Preview previous version"
                                        style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600 }}>
                                        <Undo2 size={13} /> Undo
                                    </button>
                                )}
                                {previewMode === 'undo' && (
                                    <button onClick={redoPreview} title="Back to latest saved version"
                                        style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600 }}>
                                        <Redo2 size={13} /> Redo
                                    </button>
                                )}
                                <button onClick={generate} title="Regenerate"
                                    style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                                    <RefreshCw size={13} />
                                </button>
                            </>
                        )}
                        <button onClick={onClose}
                            style={{ padding: '7px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                            <X size={14} />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div ref={scrollRef} style={{ padding: '28px 32px', maxHeight: '76vh', overflowY: 'auto' }}>
                    {loading && (
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '60px 0' }}>
                            <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--ag-purple-bg)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid var(--ag-purple-border)' }}>
                                <Loader2 className="spin" size={24} color="var(--ag-purple)" />
                            </div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Generating your cheatsheet…</div>
                            <div style={{ fontSize: 13, color: 'var(--text3)', textAlign: 'center', maxWidth: 320, lineHeight: 1.6 }}>
                                Analysing doubts, mastery data, and notes to build a personalised summary.
                            </div>
                        </div>
                    )}
                    {error && (
                        <div style={{ padding: '20px', background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 10, color: 'var(--ag-red)', fontSize: 13 }}>
                            ⚠ {error} <button onClick={generate} style={{ marginLeft: 8, background: 'none', border: 'none', color: 'var(--ag-purple)', cursor: 'pointer', fontWeight: 700 }}>Retry</button>
                        </div>
                    )}
                    {!loading && content && (
                        <div className="short-notes-content" style={{ fontSize: 14, lineHeight: 1.8, color: 'var(--text)' }}>
                            {previewMode === 'undo' && (
                                <div style={{ marginBottom: 10, padding: '8px 10px', borderRadius: 8, border: '1px solid #FCD34D', background: '#FFFBEB', color: '#92400E', fontSize: 12 }}>
                                    Showing previous snapshot preview. Latest saved version is unchanged.
                                </div>
                            )}
                            <ReactMarkdown
                                remarkPlugins={[remarkMath, remarkGfm]}
                                rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
                                components={{
                                    h1: ({ children }) => <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--ag-purple)', marginBottom: 4, marginTop: 0, borderBottom: '2px solid var(--ag-purple-border)', paddingBottom: 8 }}>{children}</h1>,
                                    h2: ({ children }) => <h2 style={{ fontSize: 16, fontWeight: 800, color: 'var(--text)', marginTop: 28, marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8 }}>{children}</h2>,
                                    h3: ({ children }) => <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text2)', marginTop: 16, marginBottom: 6 }}>{children}</h3>,
                                    ul: ({ children }) => <ul style={{ paddingLeft: 20, marginBottom: 12 }}>{children}</ul>,
                                    li: ({ children }) => <li style={{ marginBottom: 5, lineHeight: 1.65 }}>{children}</li>,
                                    strong: ({ children }) => <strong style={{ color: 'var(--ag-purple-medium)', fontWeight: 700 }}>{children}</strong>,
                                    blockquote: ({ children }) => (
                                        <blockquote style={{ borderLeft: '3px solid var(--ag-purple)', paddingLeft: 14, margin: '12px 0', color: 'var(--text2)', fontStyle: 'normal', background: 'var(--ag-purple-bg)', borderRadius: '0 8px 8px 0', padding: '10px 14px' }}>
                                            {children}
                                        </blockquote>
                                    ),
                                    code: ({ inline, children }) => inline
                                        ? <code style={{ background: 'var(--ag-purple-bg)', color: 'var(--ag-purple-medium)', borderRadius: 4, padding: '1px 6px', fontSize: 13, fontFamily: 'monospace' }}>{children}</code>
                                        : <pre style={{ background: 'var(--surface)', borderRadius: 8, padding: '12px 16px', overflow: 'auto', border: '1px solid var(--border)', fontSize: 13 }}><code>{children}</code></pre>,
                                    p: ({ children }) => <p style={{ marginBottom: 10, lineHeight: 1.75 }}>{children}</p>,
                                    em: ({ children }) => <em style={{ color: 'var(--text2)' }}>{children}</em>,
                                    hr: () => <hr style={{ border: 'none', borderTop: '1px solid var(--border)', margin: '20px 0' }} />,
                                }}
                            >
                                {content}
                            </ReactMarkdown>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
