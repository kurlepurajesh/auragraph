/**
 * AuraGraphNodeGraph — SVG-based knowledge graph (replaces broken react-flow-renderer v10).
 * Uses the same Redux graph state; renders with plain SVG for zero extra deps.
 */
import React, { useMemo } from 'react';
import { useSelector } from 'react-redux';

const STATUS = {
    mastered:   { fill: '#10B981', ring: '#6EE7B7', label: '#064E3B' },
    partial:    { fill: '#F59E0B', ring: '#FCD34D', label: '#78350F' },
    struggling: { fill: '#EF4444', ring: '#FCA5A5', label: '#7F1D1D' },
};

export default function EnhancedGraph() {
    const { nodes, edges } = useSelector(state => state.graph);

    const W = 280, H = 280;

    // Map concept positions (given as % 0-100) to SVG viewport
    const svgNodes = useMemo(() =>
        (nodes || []).map(n => ({
            ...n,
            cx: (n.x / 100) * W,
            cy: (n.y / 100) * H,
        })), [nodes]);

    const idToPos = useMemo(() => {
        const m = {};
        svgNodes.forEach(n => { m[n.id] = { x: n.cx, y: n.cy }; });
        return m;
    }, [svgNodes]);

    if (!svgNodes.length) return null;

    return (
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: '100%', minHeight: 220 }}>
            {/* edges */}
            {(edges || []).map(([s, t], i) => {
                const a = idToPos[s], b = idToPos[t];
                if (!a || !b) return null;
                return (
                    <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                        stroke="#1e3a5f" strokeWidth="1.5" strokeOpacity="0.6"
                        markerEnd="url(#arr)" />
                );
            })}
            {/* arrowhead marker */}
            <defs>
                <marker id="arr" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                    <path d="M0,0 L0,6 L6,3 z" fill="#1e3a5f" opacity="0.6" />
                </marker>
            </defs>
            {/* nodes */}
            {svgNodes.map(n => {
                const c = STATUS[n.status] || STATUS.partial;
                return (
                    <g key={n.id}>
                        <circle cx={n.cx} cy={n.cy} r={9} fill={c.ring} opacity={0.35} />
                        <circle cx={n.cx} cy={n.cy} r={6} fill={c.fill} />
                        <text x={n.cx} y={n.cy + 18} textAnchor="middle"
                            fontSize="8" fill="#94a3b8" fontFamily="monospace"
                            style={{ pointerEvents: 'none', userSelect: 'none' }}>
                            {n.label}
                        </text>
                    </g>
                );
            })}
        </svg>
    );
}
