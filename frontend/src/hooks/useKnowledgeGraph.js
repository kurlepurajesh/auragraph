import { useState, useCallback } from 'react';
import { API, apiFetch } from '../components/utils';

/**
 * Manages the concept knowledge graph (nodes + edges)
 * and the node mastery status update handler.
 *
 * @param {string} id - Notebook ID
 */
export function useKnowledgeGraph(id) {
    const [graphNodes, setGraphNodes] = useState([]);
    const [graphEdges, setGraphEdges] = useState([]);

    const handleNodeStatusChange = useCallback(async (node, status) => {
        const nextStatus = String(status || '').toLowerCase();
        setGraphNodes(prev => prev.map(n => {
            const sameId = node?.id != null && n?.id === node.id;
            const sameLabel =
                typeof node?.label === 'string' &&
                typeof n?.label === 'string' &&
                n.label.toLowerCase() === node.label.toLowerCase();
            return (sameId || sameLabel) ? { ...n, status: nextStatus } : n;
        }));
        try {
            await apiFetch(`${API}/notebooks/${id}/graph/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ concept_name: node.label, status: nextStatus }),
            });
        } catch { }
    }, [id]);

    return {
        graphNodes, setGraphNodes,
        graphEdges, setGraphEdges,
        handleNodeStatusChange,
    };
}
