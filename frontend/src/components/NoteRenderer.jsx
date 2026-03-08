import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function NoteRenderer({ content, onDoubtLink, fontSize = 16 }) {
    const mk = {
        h1({ children }) {
            return (
                <div style={{ marginBottom: 32, paddingBottom: 20, borderBottom: '2px solid #EDE9FE' }}>
                    <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.16em', color: '#7C3AED', marginBottom: 8, fontFamily: '"DM Sans",sans-serif', fontWeight: 700 }}>AuraGraph · Study Notes</div>
                    <div style={{ fontSize: 24, fontWeight: 800, color: '#0F0A1E', lineHeight: 1.2, fontFamily: '"Sora",sans-serif', letterSpacing: '-0.01em' }}>{children}</div>
                </div>
            );
        },
        h2({ children }) {
            return (
                <div style={{ marginTop: 44, marginBottom: 18 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'linear-gradient(135deg,#F5F3FF,#EDE9FE)', borderRadius: 10, padding: '11px 16px', border: '1px solid #E4DAFF', boxShadow: '0 1px 6px rgba(124,58,237,0.08)' }}>
                        <div style={{ width: 4, height: 24, borderRadius: 3, background: 'linear-gradient(180deg,#7C3AED,#4F46E5)', flexShrink: 0 }} />
                        <div style={{ fontSize: 17, fontWeight: 700, color: '#1E0B3D', lineHeight: 1.3, fontFamily: '"Sora",sans-serif', letterSpacing: '-0.01em' }}>{children}</div>
                    </div>
                </div>
            );
        },
        h3({ children }) {
            return (
                <div style={{ marginTop: 28, marginBottom: 12 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, color: '#5B21B6', background: '#F5F3FF', border: '1px solid #DDD6FE', borderRadius: 20, padding: '4px 13px', textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: '"DM Sans",sans-serif', boxShadow: '0 1px 4px rgba(124,58,237,0.10)' }}>
                        <span style={{ width: 5, height: 5, borderRadius: '50%', background: '#7C3AED', flexShrink: 0, display: 'inline-block' }} />
                        {children}
                    </span>
                </div>
            );
        },
        code({ className, children }) {
            if (!className) return <code style={{ background: '#F5F3FF', color: '#5B21B6', borderRadius: 5, padding: '2px 7px', fontSize: 13, fontFamily: '"JetBrains Mono","Courier New",monospace', fontWeight: 600, border: '1px solid #DDD6FE' }}>{children}</code>;
            return (
                <pre style={{ background: '#1E1B4B', border: '1px solid #312E81', borderRadius: 10, padding: '16px 20px', margin: '16px 0', fontFamily: '"JetBrains Mono","Courier New",monospace', fontSize: 13, lineHeight: 1.8, color: '#E0E7FF', overflowX: 'auto', whiteSpace: 'pre-wrap', boxShadow: '0 4px 16px rgba(79,70,229,0.12)' }}>
                    <code style={{ color: '#E0E7FF' }}>{children}</code>
                </pre>
            );
        },
        pre({ children }) { return <>{children}</>; },
        blockquote({ children }) {
            const extract = n => { if (!n) return ''; if (typeof n === 'string') return n; if (Array.isArray(n)) return n.map(extract).join(''); if (n?.props?.children) return extract(n.props.children); return ''; };
            const flat = extract(children);
            const isExamTip   = flat.includes('Exam Tip');
            const isFormula   = flat.includes('Formulas for this topic') || flat.includes('Formula');
            const isIntuition = flat.includes('💡') || flat.includes('Intuition') || flat.includes('Think of it');
            const isWarning   = flat.includes('⚠️') || flat.includes('⚠') || flat.includes('offline mode') || flat.includes('Offline') || flat.includes('Unresolved Doubt');
            const isMutation  = flat.includes('mutation') || flat.includes('Mutated');
            if (isExamTip) return (
                <div style={{ background: 'linear-gradient(135deg,#FFFBEB,#FEF3C7)', border: '1px solid #FDE68A', borderLeft: '4px solid #F59E0B', borderRadius: 10, padding: '14px 16px', margin: '16px 0', display: 'flex', gap: 12, alignItems: 'flex-start', boxShadow: '0 2px 8px rgba(245,158,11,0.1)' }}>
                    <span style={{ fontSize: 18, flexShrink: 0, marginTop: 1 }}>🎯</span>
                    <div style={{ fontSize: 13.5, color: '#78350F', lineHeight: 1.75, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>
                </div>
            );
            if (isFormula) return (
                <div style={{ background: 'linear-gradient(135deg,#EFF6FF,#DBEAFE)', border: '1px solid #93C5FD', borderLeft: '4px solid #2563EB', borderRadius: 10, padding: '14px 18px', margin: '16px 0', boxShadow: '0 2px 8px rgba(37,99,235,0.1)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}><span style={{ fontSize: 15 }}>🔢</span><span style={{ fontSize: 10, fontWeight: 700, color: '#1D4ED8', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: '"DM Sans",sans-serif' }}>Formula</span></div>
                    <div style={{ fontSize: 13.5, color: '#1E3A8A', lineHeight: 1.8, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>
                </div>
            );
            if (isIntuition) return (
                <div style={{ background: 'linear-gradient(135deg,#F5F3FF,#EDE9FE)', border: '1px solid #C4B5FD', borderLeft: '4px solid #7C3AED', borderRadius: 10, padding: '14px 18px', margin: '16px 0', boxShadow: '0 2px 8px rgba(124,58,237,0.08)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}><span style={{ fontSize: 15 }}>💡</span><span style={{ fontSize: 10, fontWeight: 700, color: '#6D28D9', textTransform: 'uppercase', letterSpacing: '0.1em', fontFamily: '"DM Sans",sans-serif' }}>Intuition</span></div>
                    <div style={{ fontSize: 13.5, color: '#3B0764', lineHeight: 1.8, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>
                </div>
            );
            if (isWarning) return (
                <div style={{ background: 'linear-gradient(135deg,#FFF7ED,#FFEDD5)', border: '1px solid #FED7AA', borderLeft: '4px solid #F97316', borderRadius: 10, padding: '14px 16px', margin: '12px 0', display: 'flex', gap: 12, alignItems: 'flex-start', boxShadow: '0 2px 8px rgba(249,115,22,0.1)' }}>
                    <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>⚠️</span>
                    <div style={{ fontSize: 13, color: '#7C2D12', lineHeight: 1.7, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>
                </div>
            );
            if (isMutation) return (
                <div style={{ background: 'linear-gradient(135deg,#F0FFF4,#DCFCE7)', border: '1px solid #86EFAC', borderLeft: '4px solid #22C55E', borderRadius: 10, padding: '14px 16px', margin: '12px 0', display: 'flex', gap: 12, alignItems: 'flex-start', boxShadow: '0 2px 8px rgba(34,197,94,0.1)' }}>
                    <span style={{ fontSize: 16, flexShrink: 0, marginTop: 1 }}>✨</span>
                    <div style={{ fontSize: 13.5, color: '#14532D', lineHeight: 1.7, fontFamily: '"DM Sans",sans-serif' }}>{children}</div>
                </div>
            );
            return (
                <div style={{ background: 'linear-gradient(135deg,#FDFCFF,#F7F4FF)', border: '1px solid #EDE9FE', borderLeft: '4px solid #8B5CF6', borderRadius: 10, padding: '13px 16px', margin: '14px 0', fontSize: 13.5, color: '#2D1B4E', lineHeight: 1.8, fontFamily: '"DM Sans",sans-serif', boxShadow: '0 1px 6px rgba(124,58,237,0.06)' }}>{children}</div>
            );
        },
        strong({ children }) { return <strong style={{ fontWeight: 700, color: '#4C1D95', background: 'rgba(124,58,237,0.06)', borderRadius: 3, padding: '0 2px' }}>{children}</strong>; },
        em({ children })     { return <span style={{ fontStyle: 'italic', color: '#374151' }}>{children}</span>; },
        hr()                 { return <div style={{ border: 'none', height: 1, background: 'linear-gradient(90deg,transparent,#DDD6FE 30%,#DDD6FE 70%,transparent)', margin: '32px 0' }} />; },
        p({ children })      { return <p style={{ marginBottom: 16, lineHeight: 2.05, color: '#1C1917', fontFamily: '"Source Serif 4",Georgia,serif', fontSize, letterSpacing: '0.005em' }}>{children}</p>; },
        ul({ children })     { return <ul style={{ paddingLeft: 0, margin: '12px 0 18px', lineHeight: 1.95, fontFamily: '"Source Serif 4",Georgia,serif', fontSize, color: '#1C1917', listStyle: 'none' }}>{children}</ul>; },
        ol({ children })     { return <ol style={{ paddingLeft: 22, margin: '12px 0 18px', lineHeight: 1.95, fontFamily: '"Source Serif 4",Georgia,serif', fontSize, color: '#1C1917' }}>{children}</ol>; },
        li({ children }) {
            return (
                <li style={{ marginBottom: 9, display: 'flex', gap: 11, alignItems: 'flex-start' }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#7C3AED', flexShrink: 0, marginTop: '0.55em', display: 'inline-block' }} />
                    <span style={{ flex: 1 }}>{children}</span>
                </li>
            );
        },
        img({ src, alt }) {
            const isApiImage = src && (src.startsWith('/api/images/') || src.startsWith('http'));
            const fullSrc = src && src.startsWith('/api/') ? `${API}${src}` : src;
            if (isApiImage) {
                return (
                    <figure style={{ margin: '20px 0', textAlign: 'center' }}>
                        <img src={fullSrc} alt={alt || 'Figure'}
                            style={{ maxWidth: '100%', maxHeight: 420, borderRadius: 8, border: '1px solid #E4E4E7', boxShadow: '0 2px 8px rgba(0,0,0,0.08)', display: 'inline-block' }}
                            onError={e => { e.currentTarget.style.display = 'none'; e.currentTarget.nextSibling.style.display = 'flex'; }}
                        />
                        <div style={{ display: 'none', alignItems: 'center', gap: 10, background: '#F4F4F5', border: '1px solid #E4E4E7', borderRadius: 8, padding: '12px 16px', margin: '14px 0', color: '#71717A', fontSize: 13, fontStyle: 'italic', fontFamily: '"DM Sans",sans-serif' }}>
                            <span style={{ fontSize: 18 }}>🖼</span>
                            <span>{alt ? `Figure: ${alt}` : 'Figure'}</span>
                        </div>
                        {alt && <figcaption style={{ fontSize: 12, color: '#71717A', marginTop: 6, fontFamily: '"DM Sans",sans-serif', fontStyle: 'italic' }}>{alt}</figcaption>}
                    </figure>
                );
            }
            return (
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, background: '#F4F4F5', border: '1px solid #E4E4E7', borderRadius: 8, padding: '12px 16px', margin: '14px 0', color: '#71717A', fontSize: 13, fontStyle: 'italic', fontFamily: '"DM Sans",sans-serif' }}>
                    <span style={{ fontSize: 18 }}>🖼</span>
                    <span>{alt ? `Figure: ${alt}` : 'Figure'}</span>
                </div>
            );
        },
        a({ href, children }) {
            if (href?.startsWith('#doubt-')) {
                return (
                    <span onClick={() => onDoubtLink?.(href.slice(1))}
                        style={{ color: '#7C3AED', cursor: 'pointer', textDecoration: 'underline', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                        {children}
                    </span>
                );
            }
            return <a href={href} target="_blank" rel="noopener noreferrer" style={{ color: '#2563EB', textDecoration: 'underline' }}>{children}</a>;
        },
        table({ children }) {
            return (
                <div style={{ overflowX: 'auto', margin: '18px 0', borderRadius: 10, border: '1px solid #DDD6FE', boxShadow: '0 2px 8px rgba(124,58,237,0.06)' }}>
                    <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 13.5, fontFamily: '"DM Sans",sans-serif' }}>{children}</table>
                </div>
            );
        },
        thead({ children }) { return <thead style={{ background: 'linear-gradient(135deg,#EDE9FE,#F5F3FF)' }}>{children}</thead>; },
        tbody({ children }) { return <tbody>{children}</tbody>; },
        tr({ children, node }) {
            const idx = node?.position?.start?.line ?? 0;
            return <tr style={{ borderBottom: '1px solid #EDE9FE', background: idx % 2 === 0 ? '#FAFAFA' : '#FFFFFF' }}>{children}</tr>;
        },
        th({ children }) { return <th style={{ padding: '10px 16px', textAlign: 'left', fontWeight: 700, color: '#4C1D95', borderBottom: '2px solid #C4B5FD', whiteSpace: 'nowrap', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{children}</th>; },
        td({ children }) { return <td style={{ padding: '9px 16px', color: '#374151', verticalAlign: 'top', lineHeight: 1.6 }}>{children}</td>; },
    };

    const safeMath = (src) => src.replace(/\$([^$\n]+?)\$/g, (m, inner) =>
        inner.includes('|') ? '$' + inner.replace(/\|/g, '\\vert ') + '$' : m
    );

    return (
        <div style={{ color: '#1C1917' }}>
            <ReactMarkdown
                remarkPlugins={[remarkMath, remarkGfm]}
                rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false, errorColor: '#cc0000' }]]}
                components={mk}
            >
                {safeMath(content || '')}
            </ReactMarkdown>
        </div>
    );
}
