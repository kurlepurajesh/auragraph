import React, { useMemo } from 'react';
import ReactFlow, { Background, Controls } from 'react-flow-renderer';
import { useSelector } from 'react-redux';

const defaultNodeStyle = {
    borderRadius: '50%',
    width: 14,
    height: 14,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 10,
    color: 'transparent',
    border: '2px solid transparent'
};

const NodeComponent = ({ data }) => {
    const S = {
        mastered: { bg: "#16a34a", ring: "#4ade80", dot: "#86efac" },
        partial: { bg: "#b45309", ring: "#f59e0b", dot: "#fcd34d" },
        struggling: { bg: "#b91c1c", ring: "#ef4444", dot: "#fca5a5" },
    };

    const c = S[data.status] || S.mastered;

    return (
        <div style={{ ...defaultNodeStyle, backgroundColor: c.bg, borderColor: c.ring, position: 'relative' }}>
            <div style={{ position: 'absolute', top: 20, whiteSpace: 'nowrap', color: '#94a3b8', fontSize: '10px', fontFamily: 'monospace' }}>{data.label}</div>
        </div>
    );
};

export default function EnhancedGraph() {
    const { nodes, edges } = useSelector(state => state.graph);

    const reactFlowNodes = useMemo(() => {
        return nodes.map(n => ({
            id: String(n.id),
            data: { label: n.label, status: n.status },
            position: { x: n.x * 3, y: n.y * 3 }, // scale up slightly from original SVG coords
            type: 'custom'
        }));
    }, [nodes]);

    const reactFlowEdges = useMemo(() => {
        return edges.map((e, i) => ({
            id: `e${e[0]}-${e[1]}`,
            source: String(e[0]),
            target: String(e[1]),
            animated: true,
            style: { stroke: '#1e3a5f', strokeWidth: 1.5 }
        }));
    }, [edges]);

    const nodeTypes = useMemo(() => ({ custom: NodeComponent }), []);

    if (!nodes || nodes.length === 0) return null;

    return (
        <div style={{ width: '100%', height: '100%', minHeight: '220px' }}>
            <ReactFlow
                nodes={reactFlowNodes}
                edges={reactFlowEdges}
                nodeTypes={nodeTypes}
                fitView
            >
                <Background color="#1e3a5f" gap={16} />
                <Controls />
            </ReactFlow>
        </div>
    );
}
