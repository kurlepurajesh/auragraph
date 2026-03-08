import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import { MessageCircle, X, GitBranch, ChevronDown, ChevronUp, Layers, BookOpen } from 'lucide-react';

const IM = ({ text }) => (
    <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}
        components={{
            p:     ({ children }) => <span style={{ display: 'block', marginBottom: 4 }}>{children}</span>,
            strong:({ children }) => <strong style={{ color: '#5B21B6', fontWeight: 700 }}>{children}</strong>,
            em:    ({ children }) => <em style={{ color: '#6D28D9' }}>{children}</em>,
            code:  ({ children }) => <code style={{ background: 'var(--ag-purple-soft)', color: '#5B21B6', borderRadius: 3, padding: '1px 4px', fontSize: 11, fontFamily: 'monospace' }}>{children}</code>,
            a:     ({ children }) => <span>{children}</span>,
            table: ({ children }) => <table style={{ borderCollapse: 'collapse', fontSize: 12, margin: '6px 0' }}>{children}</table>,
            th:    ({ children }) => <th style={{ padding: '4px 10px', borderBottom: '1px solid #C4B5FD', textAlign: 'left', fontWeight: 700, color: '#5B21B6' }}>{children}</th>,
            td:    ({ children }) => <td style={{ padding: '4px 10px', borderBottom: '1px solid #EDE9FE', color: '#3F3F46' }}>{children}</td>,
        }}
    >
        {text || ''}
    </ReactMarkdown>
);

export default function DoubtsPanel({ doubts, currentPage }) {
    const [expanded, setExpanded] = useState({});
    const [viewAll, setViewAll] = useState(false);
    const toggle = id => setExpanded(p => ({ ...p, [id]: !p[id] }));

    const pageDiagnostics = doubts.filter(d => d.pageIdx === currentPage);
    const otherPages = [...new Set(doubts.filter(d => d.pageIdx !== currentPage).map(d => d.pageIdx))].sort((a, b) => a - b);

    // Which doubts to render (all vs current-page)
    const visibleDiagnostics = viewAll ? doubts : pageDiagnostics;

    // ── View-all toggle bar (shown whenever there are doubts on other pages) ──
    const toggleBar = doubts.length > 0 && (
        <div style={{ padding: '6px 12px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0, background: 'var(--surface)' }}>
            <button
                onClick={() => setViewAll(false)}
                style={{ flex: 1, padding: '4px 0', fontSize: 10, fontWeight: 700, borderRadius: 6, border: `1px solid ${!viewAll ? 'var(--ag-purple)' : 'var(--border)'}`, background: !viewAll ? 'var(--ag-purple-soft)' : 'transparent', color: !viewAll ? 'var(--ag-purple)' : 'var(--text3)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, transition: 'all 0.15s' }}
            >
                <BookOpen size={10} /> This page {pageDiagnostics.length > 0 ? `(${pageDiagnostics.length})` : ''}
            </button>
            <button
                onClick={() => setViewAll(true)}
                style={{ flex: 1, padding: '4px 0', fontSize: 10, fontWeight: 700, borderRadius: 6, border: `1px solid ${viewAll ? 'var(--ag-purple)' : 'var(--border)'}`, background: viewAll ? 'var(--ag-purple-soft)' : 'transparent', color: viewAll ? 'var(--ag-purple)' : 'var(--text3)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, transition: 'all 0.15s' }}
            >
                <Layers size={10} /> All doubts ({doubts.length})
            </button>
        </div>
    );

    if (visibleDiagnostics.length === 0) return (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {toggleBar}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 }}>
                <MessageCircle size={26} color="#C4B5FD" />
                <div style={{ fontSize: 12, color: 'var(--text3)', textAlign: 'center', lineHeight: 1.7 }}>
                    {viewAll
                        ? <><b>No doubts yet.</b><br /><span style={{ fontSize: 11 }}>Click <b>Ask a Doubt</b> to add one.</span></>
                        : <>No doubts on <b>page {currentPage + 1}</b> yet.<br /><span style={{ fontSize: 11 }}>Click <b>Ask a Doubt</b> to add one.</span></>
                    }
                </div>
            </div>
            {!viewAll && otherPages.length > 0 && (
                <div style={{ padding: '10px 14px', borderTop: '1px solid var(--border)', fontSize: 11, color: 'var(--text3)', lineHeight: 1.6 }}>
                    Doubts on page{otherPages.length > 1 ? 's' : ''}{' '}
                    <button onClick={() => setViewAll(true)} style={{ color: 'var(--ag-purple)', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontSize: 11, textDecoration: 'underline' }}>
                        {otherPages.map(p => p + 1).join(', ')}
                    </button>
                    {' '}— <button onClick={() => setViewAll(true)} style={{ color: 'var(--ag-purple)', fontWeight: 600, background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontSize: 11 }}>View all</button>
                </div>
            )}
        </div>
    );

    return (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {toggleBar}
            {!viewAll && (
                <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--ag-purple)', background: 'var(--ag-purple-soft)', border: '1px solid #C4B5FD', borderRadius: 10, padding: '2px 8px' }}>Page {currentPage + 1}</span>
                    <span style={{ fontSize: 11, color: 'var(--text3)' }}>{pageDiagnostics.length} doubt{pageDiagnostics.length > 1 ? 's' : ''}</span>
                    {otherPages.length > 0 && <span style={{ fontSize: 10, color: '#9CA3AF', marginLeft: 'auto' }}>+{doubts.length - pageDiagnostics.length} on other pages</span>}
                </div>
            )}
            <div style={{ flex: 1, overflowY: 'auto', padding: '12px 10px', display: 'flex', flexDirection: 'column', gap: 14 }}>
                {visibleDiagnostics.map(d => {
                    const isExp = !!expanded[d.id];
                    const pl = 380;
                    const needsExp = d.insight.length > pl;
                    const preview = needsExp && !isExp ? d.insight.slice(0, pl).replace(/\*\*[^*]*$/, '').replace(/\$[^$]*$/, '') + '…' : d.insight;
                    return (
                        <div key={d.id} id={'doubt-' + d.id}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 6, marginBottom: 4 }}>
                                {viewAll && d.pageIdx !== currentPage && (
                                    <span style={{ fontSize: 9, fontWeight: 600, color: '#6B7280', background: '#F3F4F6', borderRadius: 6, padding: '1px 6px', border: '1px solid #E5E7EB' }}>p.{d.pageIdx + 1}</span>
                                )}
                                {d.success
                                    ? d.kind === 'answered'
                                        ? <span style={{ fontSize: 9, color: '#0369A1', fontWeight: 700 }}>💬 answered</span>
                                        : <span style={{ fontSize: 9, color: 'var(--ag-purple)', fontWeight: 700 }}>✨ mutated</span>
                                    : d.unresolved
                                        ? <span style={{ fontSize: 9, color: '#D97706', fontWeight: 600 }}>⏳ pending</span>
                                        : <span style={{ fontSize: 9, color: 'var(--ag-red)', fontWeight: 600 }}>⚠ failed</span>}
                                {d.success && d.source && (
                                    <span style={{ fontSize: 8, fontWeight: 600, padding: '1px 5px', borderRadius: 6, background: d.source === 'azure' ? '#EFF6FF' : d.source === 'groq' ? '#ECFDF5' : '#F5F5F5', color: d.source === 'azure' ? '#1D4ED8' : d.source === 'groq' ? '#065F46' : '#52525B', border: `1px solid ${d.source === 'azure' ? '#BFDBFE' : d.source === 'groq' ? '#A7F3D0' : '#D4D4D8'}` }}>{d.source}</span>
                                )}
                                <span style={{ fontSize: 9, color: '#D1D5DB' }}>{d.time}</span>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 6 }}>
                                <div style={{ maxWidth: '84%', background: 'var(--ag-purple)', color: '#fff', borderRadius: '14px 14px 3px 14px', padding: '9px 13px', fontSize: 12.5, lineHeight: 1.55 }}>{d.doubt}</div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                                {d.success ? (
                                    <div style={{ maxWidth: '90%', background: '#F5F3FF', border: '1px solid #DDD6FE', borderRadius: '3px 14px 14px 14px', padding: '9px 13px', fontSize: 12, lineHeight: 1.7, color: '#3B0764' }}>
                                        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--ag-purple)', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 4 }}><GitBranch size={10} /> AuraGraph</div>
                                        <div style={{ color: '#4C1D95' }}><IM text={preview} /></div>
                                        {d.gap && isExp && <div style={{ marginTop: 7, paddingTop: 7, borderTop: '1px solid #DDD6FE', fontSize: 11, color: 'var(--ag-purple)', fontStyle: 'italic' }}>🔍 {d.gap}</div>}
                                        {needsExp && (
                                            <button onClick={() => toggle(d.id)} style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 3, fontSize: 11, color: 'var(--ag-purple)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontWeight: 600 }}>
                                                {isExp ? <><ChevronUp size={11} /> Show less</> : <><ChevronDown size={11} /> Read more</>}
                                            </button>
                                        )}
                                    </div>
                                ) : (
                                    <div style={{ maxWidth: '90%', background: '#FEF2F2', border: '1px solid #FCA5A5', borderRadius: '3px 14px 14px 14px', padding: '9px 13px', fontSize: 12, lineHeight: 1.7, color: '#991B1B' }}>
                                        <div style={{ fontSize: 10, fontWeight: 700, color: '#DC2626', marginBottom: 5, display: 'flex', alignItems: 'center', gap: 4 }}>
                                            {d.unresolved ? '⏳ Not yet resolved' : '⚠ Not delivered'}
                                        </div>
                                        <div style={{ color: d.unresolved ? '#92400E' : '#7F1D1D' }}>
                                            {d.unresolved ? (d.insight || 'AI unavailable — doubt saved. Retry when online.') : 'Backend was unreachable. Your doubt is saved — try re-submitting when the server is running.'}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}