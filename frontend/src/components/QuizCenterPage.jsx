import React from 'react';
import { History, Target, BookOpen, Loader2, RefreshCw, ArrowLeft, Brain, GraduationCap } from 'lucide-react';
import { API, apiFetch } from './utils';
import SniperExamModal from './SniperExamModal';
import GeneralExamModal from './GeneralExamModal';
import ConceptExamModal from './ConceptExamModal';
import QuizAttemptReviewPage from './QuizAttemptReviewPage';

export default function QuizCenterPage({
    notebookId,
    nodes,
    onClose,
    onQuizCompleted,
    onNavigateToConcept = null,
}) {
    const [loading, setLoading] = React.useState(true);
    const [history, setHistory] = React.useState([]);
    const [historyTab, setHistoryTab] = React.useState('general');
    const [reviewRun, setReviewRun] = React.useState(null);
    const [sniperOpen, setSniperOpen] = React.useState(false);
    const [generalOpen, setGeneralOpen] = React.useState(false);
    const [conceptOpen, setConceptOpen] = React.useState(false);
    const [conceptFilter, setConceptFilter] = React.useState(''); // Filter for concept names

    const weakConcepts = React.useMemo(() => (nodes || []).filter(n => n.status === 'struggling'), [nodes]);

    const loadHistory = React.useCallback(async () => {
        setLoading(true);
        try {
            const res = await apiFetch(`${API}/api/notebooks/${notebookId}/quizzes`);
            const data = await res.json().catch(() => ({}));
            setHistory(Array.isArray(data?.quizzes) ? data.quizzes : []);
        } catch {
            setHistory([]);
        } finally {
            setLoading(false);
        }
    }, [notebookId]);

    React.useEffect(() => {
        loadHistory();
    }, [loadHistory]);

    const handleAttemptSaved = (attempt) => {
        if (!attempt) return;
        setHistory(prev => [attempt, ...prev]);
    };

    const runs = React.useMemo(() => {
        let filtered = history.filter(h => (h.quiz_type || 'general') === historyTab);
        if (historyTab === 'concept' && conceptFilter) {
            filtered = filtered.filter(h => {
                const concepts = Array.isArray(h.concepts_tested) ? h.concepts_tested : [];
                return concepts.some(c => (c?.label || '').toLowerCase().includes(conceptFilter.toLowerCase()));
            });
        }
        return filtered;
    }, [history, historyTab, conceptFilter]);

    // Get unique concept names from concept attempts
    const uniqueConcepts = React.useMemo(() => {
        const conceptAttempts = history.filter(h => (h.quiz_type || 'general') === 'concept');
        const conceptSet = new Set();
        conceptAttempts.forEach(attempt => {
            const concepts = Array.isArray(attempt.concepts_tested) ? attempt.concepts_tested : [];
            concepts.forEach(c => {
                if (c?.label) conceptSet.add(c.label);
            });
        });
        return Array.from(conceptSet).sort();
    }, [history]);

    return (
        <div style={{ flex: 1, overflowY: 'auto', background: 'var(--bg)', padding: '24px 24px 18px' }}>
            <div style={{ maxWidth: 1060, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 18, fontFamily: '"DM Sans", "Space Grotesk", system-ui, -apple-system, sans-serif' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
                    <div style={{ minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                            <span
                                style={{
                                    width: 30,
                                    height: 30,
                                    borderRadius: 10,
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    background: 'linear-gradient(145deg, #DDD6FE 0%, #C4B5FD 55%, #A78BFA 100%)',
                                    boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.42), 0 6px 14px rgba(124, 58, 237, 0.20)'
                                }}
                                aria-hidden="true"
                            >
                                <GraduationCap size={16} color="var(--ag-purple-medium)" strokeWidth={2.2} />
                            </span>
                            <span style={{ fontFamily: '"Sora", "DM Sans", sans-serif', fontSize: 28, fontWeight: 700, color: 'var(--text)', lineHeight: 1.1, letterSpacing: '-0.01em' }}>Quiz Center</span>
                        </div>
                        <div style={{ fontSize: 13, color: 'var(--text3)' }}>
                            View full quiz history and start new General or Sniper tests.
                        </div>
                    </div>

                    <button onClick={onClose} style={{ border: 'none', background: 'none', color: 'var(--text2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8 }}>
                        <ArrowLeft size={18} /> Back To Notes
                    </button>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                    <button onClick={loadHistory} style={{ border: 'none', background: 'none', color: 'var(--text2)', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, padding: 0 }}>
                        <RefreshCw size={17} /> Refresh
                    </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 500px) minmax(360px, 1fr)', gap: 14, alignItems: 'start' }}>
                    <div style={{ marginTop: 2, border: '1px solid var(--border)', borderRadius: 10, background: 'var(--surface)', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 5 }}>
                        <div style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.5 }}>
                            <strong style={{ color: 'var(--text)' }}>General Test</strong>: 10 mixed questions from all concepts.
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.5 }}>
                            <strong style={{ color: 'var(--text)' }}>Sniper Test</strong>: 5 focused questions on weak concepts.
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--text2)', lineHeight: 1.5 }}>
                            <strong style={{ color: 'var(--text)' }}>Concept-wise Quiz</strong>: 5 focused questions from one selected concept.
                        </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'flex-end', gap: 10, flexWrap: 'nowrap' }}>
                        <button
                            className="ag-hover-chip"
                            onClick={() => setGeneralOpen(true)}
                            style={{ border: '1px solid var(--border)', borderRadius: 12, padding: '10px 16px', background: 'var(--surface)', color: 'var(--text2)', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}
                        >
                            <BookOpen size={18} /> Take General Test
                        </button>
                        <button
                            className={weakConcepts.length === 0 ? '' : 'ag-hover-chip'}
                            onClick={() => setSniperOpen(true)}
                            disabled={weakConcepts.length === 0}
                            style={{ border: '1px solid var(--border)', borderRadius: 12, padding: '10px 16px', background: weakConcepts.length === 0 ? '#F3F4F6' : 'var(--surface)', color: weakConcepts.length === 0 ? '#9CA3AF' : 'var(--text2)', fontSize: 13, fontWeight: 600, cursor: weakConcepts.length === 0 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}
                        >
                            <Target size={18} /> Take Sniper Test
                        </button>
                        <button
                            className={(nodes || []).length === 0 ? '' : 'ag-hover-chip'}
                            onClick={() => setConceptOpen(true)}
                            disabled={(nodes || []).length === 0}
                            style={{ border: '1px solid var(--border)', borderRadius: 12, padding: '10px 16px', background: (nodes || []).length === 0 ? '#F3F4F6' : 'var(--surface)', color: (nodes || []).length === 0 ? '#9CA3AF' : 'var(--text2)', fontSize: 13, fontWeight: 600, cursor: (nodes || []).length === 0 ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap' }}
                        >
                            <Brain size={18} /> Take Concept Quiz
                        </button>
                    </div>
                </div>


                <div style={{ display: 'flex', gap: 8 }}>
                    <button
                        onClick={() => { setHistoryTab('general'); setReviewRun(null); setConceptFilter(''); }}
                        style={{ border: `1px solid ${historyTab === 'general' ? 'var(--ag-purple-border)' : 'var(--border)'}`, background: historyTab === 'general' ? 'var(--ag-purple-bg)' : 'var(--surface)', color: historyTab === 'general' ? 'var(--ag-purple)' : 'var(--text2)', borderRadius: 12, padding: '8px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                    >
                        General History
                    </button>
                    <button
                        onClick={() => { setHistoryTab('sniper'); setReviewRun(null); setConceptFilter(''); }}
                        style={{ border: `1px solid ${historyTab === 'sniper' ? 'var(--ag-purple-border)' : 'var(--border)'}`, background: historyTab === 'sniper' ? 'var(--ag-purple-bg)' : 'var(--surface)', color: historyTab === 'sniper' ? 'var(--ag-purple)' : 'var(--text2)', borderRadius: 12, padding: '8px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                    >
                        Sniper History
                    </button>
                    <button
                        onClick={() => { setHistoryTab('concept'); setReviewRun(null); setConceptFilter(''); }}
                        style={{ border: `1px solid ${historyTab === 'concept' ? 'var(--ag-purple-border)' : 'var(--border)'}`, background: historyTab === 'concept' ? 'var(--ag-purple-bg)' : 'var(--surface)', color: historyTab === 'concept' ? 'var(--ag-purple)' : 'var(--text2)', borderRadius: 12, padding: '8px 14px', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                    >
                        Concept History
                    </button>
                </div>

                <div style={{ border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden', background: 'var(--surface)' }}>
                    {!reviewRun && (
                        <>
                            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700, color: 'var(--text)', fontSize: 16 }}>
                                    <History size={18} /> {historyTab === 'general' ? 'General Test History' : historyTab === 'sniper' ? 'Sniper Test History' : 'Concept Quiz History'}
                                </div>
                                <div style={{ fontSize: 12, color: 'var(--text3)' }}>{runs.length} attempt{runs.length !== 1 ? 's' : ''}</div>
                            </div>

                            {historyTab === 'concept' && uniqueConcepts.length > 0 && (
                                <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 8 }}>
                                    <label style={{ fontSize: 12, color: 'var(--text2)', fontWeight: 600 }}>Filter by concept:</label>
                                    <select
                                        value={conceptFilter}
                                        onChange={(e) => setConceptFilter(e.target.value)}
                                        style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '6px 10px', fontSize: 12, background: 'var(--bg)', color: 'var(--text)', cursor: 'pointer' }}
                                    >
                                        <option value="">All concepts</option>
                                        {uniqueConcepts.map(concept => (
                                            <option key={concept} value={concept}>{concept}</option>
                                        ))}
                                    </select>
                                </div>
                            )}

                            <div style={{ maxHeight: '60vh', overflowY: 'auto', padding: 10 }}>
                                {loading ? (
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '30px 0', color: 'var(--text3)', fontSize: 12 }}>
                                        <Loader2 size={16} className="spin" /> Loading history...
                                    </div>
                                ) : runs.length === 0 ? (
                                    <div style={{ textAlign: 'center', padding: '30px 0', fontSize: 12, color: 'var(--text3)' }}>
                                        No {historyTab} attempts yet.
                                    </div>
                                ) : (
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                        {runs.map((run, idx) => {
                                            const total = run.total_questions || run.questions?.length || 0;
                                            const score = run.correct_answers || run.score || 0;
                                            const pct = total ? Math.round((score / total) * 100) : 0;
                                            const color = pct >= 70 ? '#16A34A' : pct >= 40 ? '#D97706' : '#DC2626';
                                            
                                            // Extract concept name for concept quizzes
                                            const conceptName = historyTab === 'concept' 
                                                ? (Array.isArray(run.concepts_tested) && run.concepts_tested.length > 0 
                                                    ? run.concepts_tested[0].label 
                                                    : 'Concept')
                                                : null;
                                            
                                            return (
                                                <button
                                                    key={run.id}
                                                    onClick={() => setReviewRun(run)}
                                                    style={{ border: '1px solid var(--border)', borderRadius: 12, background: 'var(--bg)', textAlign: 'left', padding: '14px 12px', cursor: 'pointer' }}
                                                >
                                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                                                        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>
                                                            {historyTab === 'general' ? 'General' : historyTab === 'sniper' ? 'Sniper' : 'Concept'} Attempt {runs.length - idx}
                                                            {conceptName && <span style={{ fontSize: 12, fontWeight: 600, marginLeft: 8, color: 'var(--text2)' }}>• {conceptName}</span>}
                                                        </div>
                                                        <div style={{ fontSize: 13, fontWeight: 700, color }}>
                                                            {score}/{total} ({pct}%)
                                                        </div>
                                                    </div>
                                                    <div style={{ fontSize: 11, color: 'var(--text3)' }}>
                                                        {new Date(run.completed_at || run.created_at || Date.now()).toLocaleString()}
                                                    </div>
                                                    <div style={{ marginTop: 4, fontSize: 11, color: 'var(--ag-purple)', fontWeight: 600 }}>View review -&gt;</div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        </>
                    )}

                    {reviewRun && <QuizAttemptReviewPage run={reviewRun} onBack={() => setReviewRun(null)} />}
                </div>
            </div>

            {sniperOpen && (
                <SniperExamModal
                    nodes={nodes}
                    notebookId={notebookId}
                    onClose={() => { setSniperOpen(false); loadHistory(); }}
                    onQuizCompleted={onQuizCompleted}
                    onAttemptSaved={handleAttemptSaved}
                />
            )}
            {generalOpen && (
                <GeneralExamModal
                    nodes={nodes}
                    notebookId={notebookId}
                    onClose={() => { setGeneralOpen(false); loadHistory(); }}
                    onQuizCompleted={onQuizCompleted}
                    onAttemptSaved={handleAttemptSaved}
                />
            )}
            {conceptOpen && (
                <ConceptExamModal
                    nodes={nodes}
                    notebookId={notebookId}
                    onClose={() => { setConceptOpen(false); loadHistory(); }}
                    onQuizCompleted={onQuizCompleted}
                    onAttemptSaved={handleAttemptSaved}
                    onNavigateToConcept={onNavigateToConcept}
                />
            )}
        </div>
    );
}
