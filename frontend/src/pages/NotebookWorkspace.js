import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ls_getNotebook, ls_saveNote } from '../lib/localNotebooks';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import {
  Loader2, ChevronLeft, ChevronRight, Upload, FileText,
  BookOpen, ArrowLeft, Zap, Brain, CheckCircle2,
  AlertCircle, MinusCircle, X, ChevronDown, ChevronUp,
  MessageCircle, Sparkles, Target
} from 'lucide-react';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function authHeaders() {
  const token = localStorage.getItem('ag_token') || 'demo-token';
  return { Authorization: `Bearer ${token}` };
}

// ---- File Drop ----
function FileDrop({ label, icon: Icon, files, onFiles }) {
  const ref = useRef();
  const [drag, setDrag] = useState(false);
  const addFiles = (incoming) => {
    const valid = Array.from(incoming).filter(f => f.type === 'application/pdf' || f.name.endsWith('.pdf'));
    if (valid.length) onFiles(prev => [...prev, ...valid]);
  };
  return (
    <div
      data-testid={`file-drop-${label.toLowerCase().replace(/\s/g, '-')}`}
      onDragOver={e => { e.preventDefault(); setDrag(true); }}
      onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
      className="rounded-xl p-5 cursor-pointer transition-all"
      style={{
        border: `2px dashed ${drag ? '#0F5132' : files.length ? '#10B981' : '#D4D4D8'}`,
        background: drag ? '#F6F5F0' : files.length ? '#ECFDF5' : '#fff',
      }}
      onClick={() => !files.length && ref.current.click()}
    >
      <input ref={ref} type="file" accept=".pdf" multiple style={{ display: 'none' }} onChange={e => addFiles(e.target.files)} />
      {!files.length ? (
        <div className="text-center py-4">
          <Icon size={28} className="mx-auto mb-2" style={{ color: '#0F5132' }} strokeWidth={1.5} />
          <div className="text-sm font-semibold mb-1" style={{ color: '#1A1A1A', fontFamily: "'Manrope', sans-serif" }}>{label}</div>
          <div className="text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>Drop PDFs or click to browse</div>
        </div>
      ) : (
        <div>
          {files.map((f, i) => (
            <div key={i} className="flex items-center gap-2 px-3 py-2 rounded-lg mb-1" style={{ background: '#fff', border: '1px solid #D1FAE5' }}>
              <FileText size={13} style={{ color: '#10B981' }} />
              <span className="text-xs flex-1 truncate" style={{ color: '#065F46', fontFamily: "'Manrope', sans-serif" }}>{f.name}</span>
              <button onClick={e => { e.stopPropagation(); onFiles(prev => prev.filter((_, idx) => idx !== i)); }} className="text-xs" style={{ color: '#A1A1AA' }}>x</button>
            </div>
          ))}
          <button onClick={() => ref.current.click()} className="w-full mt-2 py-1.5 rounded-lg text-xs font-medium" style={{ border: '1px dashed #6EE7B7', color: '#10B981', fontFamily: "'Manrope', sans-serif" }}>
            + Add more ({files.length} file{files.length > 1 ? 's' : ''})
          </button>
        </div>
      )}
    </div>
  );
}

// ---- Note Renderer ----
function NoteRenderer({ content }) {
  const mkComponents = useMemo(() => ({
    h1: ({ children }) => (
      <div className="rounded-xl mb-7 px-7 py-5" style={{ background: '#0F5132', color: '#fff' }}>
        <div className="text-xs uppercase tracking-widest mb-2" style={{ opacity: 0.6, fontFamily: "'Manrope', sans-serif" }}>AuraGraph Study Notes</div>
        <div className="text-xl font-bold" style={{ fontFamily: "'Playfair Display', serif" }}>{children}</div>
      </div>
    ),
    h2: ({ children }) => (
      <div className="flex items-stretch gap-0 mt-8 mb-4">
        <div className="w-1 rounded-full mr-3 flex-shrink-0" style={{ background: '#0F5132' }} />
        <div>
          <div className="text-lg font-bold" style={{ color: '#0F5132', fontFamily: "'Playfair Display', serif" }}>{children}</div>
          <div className="h-px mt-1" style={{ background: 'linear-gradient(90deg, #D1FAE5, transparent)' }} />
        </div>
      </div>
    ),
    h3: ({ children }) => (
      <div className="mt-5 mb-2 pl-3" style={{ borderLeft: '3px solid #0D9488' }}>
        <span className="text-xs font-bold uppercase tracking-wide" style={{ color: '#0D9488', fontFamily: "'Manrope', sans-serif" }}>{children}</span>
      </div>
    ),
    p: ({ children }) => (
      <p className="mb-3 leading-relaxed" style={{ color: '#1A1A1A', fontFamily: "'Crimson Pro', Georgia, serif", fontSize: '16px', lineHeight: '1.85' }}>{children}</p>
    ),
    strong: ({ children }) => (
      <strong className="font-bold" style={{ color: '#0F5132' }}>{children}</strong>
    ),
    em: ({ children }) => (
      <em style={{ color: '#8B5CF6' }}>{children}</em>
    ),
    blockquote: ({ children }) => {
      const extractText = (node) => {
        if (!node) return '';
        if (typeof node === 'string') return node;
        if (Array.isArray(node)) return node.map(extractText).join('');
        if (node?.props?.children) return extractText(node.props.children);
        return '';
      };
      const flat = extractText(children);
      const isExamTip = flat.includes('Exam Tip');
      const isMutation = flat.includes('Intuition');
      if (isExamTip) return (
        <div className="rounded-lg px-4 py-3 my-3 flex gap-2.5 items-start" style={{ background: '#FFFBEB', border: '1px solid #FDE68A', borderLeft: '4px solid #F59E0B' }}>
          <Target size={15} className="flex-shrink-0 mt-0.5" style={{ color: '#F59E0B' }} />
          <div className="text-sm leading-relaxed" style={{ color: '#78350F', fontFamily: "'Crimson Pro', serif" }}>{children}</div>
        </div>
      );
      if (isMutation) return (
        <div className="rounded-lg px-4 py-3 my-3 flex gap-2.5 items-start" style={{ background: '#F5F3FF', border: '1px solid #C4B5FD', borderLeft: '4px solid #8B5CF6' }}>
          <Sparkles size={15} className="flex-shrink-0 mt-0.5" style={{ color: '#8B5CF6' }} />
          <div className="text-sm leading-relaxed" style={{ color: '#4C1D95', fontFamily: "'Crimson Pro', serif" }}>{children}</div>
        </div>
      );
      return (
        <div className="rounded-lg px-4 py-3 my-3" style={{ background: '#ECFDF5', border: '1px solid #A7F3D0', borderLeft: '4px solid #10B981' }}>
          <div className="text-sm leading-relaxed" style={{ color: '#064E3B', fontFamily: "'Crimson Pro', serif" }}>{children}</div>
        </div>
      );
    },
    code: ({ className, children }) => {
      if (!className) return (
        <code className="px-1.5 py-0.5 rounded text-sm font-medium" style={{ background: '#F0FDF4', color: '#0F5132', fontFamily: "'JetBrains Mono', monospace" }}>{children}</code>
      );
      return (
        <pre className="rounded-lg px-5 py-4 my-3 overflow-x-auto text-sm" style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', fontFamily: "'JetBrains Mono', monospace", color: '#334155', lineHeight: 1.75 }}>
          <code>{children}</code>
        </pre>
      );
    },
    pre: ({ children }) => <>{children}</>,
    ul: ({ children }) => <ul className="pl-5 my-2" style={{ fontFamily: "'Crimson Pro', serif", fontSize: '16px', lineHeight: '1.85', color: '#1A1A1A' }}>{children}</ul>,
    ol: ({ children }) => <ol className="pl-5 my-2" style={{ fontFamily: "'Crimson Pro', serif", fontSize: '16px', lineHeight: '1.85', color: '#1A1A1A' }}>{children}</ol>,
    li: ({ children }) => <li className="mb-1">{children}</li>,
    hr: () => <div className="my-7" style={{ borderTop: '2px dashed #E5E5E5' }} />,
  }), []);

  return <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]} components={mkComponents}>{content || ''}</ReactMarkdown>;
}

// ---- Knowledge Graph ----
const STATUS_COLOR = {
  mastered: { fill: '#10B981', ring: '#6EE7B7', text: '#064E3B' },
  partial: { fill: '#F59E0B', ring: '#FCD34D', text: '#78350F' },
  struggling: { fill: '#EF4444', ring: '#FCA5A5', text: '#7F1D1D' },
};

function KnowledgeGraph({ nodes, edges, onNodeClick }) {
  const W = 280, H = 380;
  if (!nodes?.length) return (
    <div className="flex flex-col items-center justify-center h-48 text-center px-4">
      <Brain size={26} style={{ color: '#D4D4D8' }} className="mb-2" />
      <p className="text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>Concept graph appears after generating notes.</p>
    </div>
  );
  const nodeById = Object.fromEntries(nodes.map(n => [n.id, n]));
  const getPos = (n) => ({ cx: (n.x / 100) * (W - 50) + 25, cy: (n.y / 100) * (H - 50) + 25 });

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', width: '100%' }}>
      {edges.map((e, i) => {
        const src = nodeById[e[0]], dst = nodeById[e[1]];
        if (!src || !dst) return null;
        const sp = getPos(src), dp = getPos(dst);
        return <line key={i} x1={sp.cx} y1={sp.cy} x2={dp.cx} y2={dp.cy} stroke="#D4D4D8" strokeWidth={1.2} strokeDasharray="4,3" />;
      })}
      {nodes.map(n => {
        const c = STATUS_COLOR[n.status] || STATUS_COLOR.partial;
        const { cx, cy } = getPos(n);
        const label = n.label.length > 16 ? n.label.slice(0, 14) + '...' : n.label;
        return (
          <g key={n.id} style={{ cursor: 'pointer' }} onClick={() => onNodeClick(n)}>
            <circle cx={cx} cy={cy} r={16} fill={c.ring} opacity={0.2} />
            <circle cx={cx} cy={cy} r={10} fill={c.fill} stroke="#fff" strokeWidth={2} />
            <text x={cx} y={cy + 22} textAnchor="middle" fontSize={8} fill="#52525B" fontWeight={500} style={{ pointerEvents: 'none', fontFamily: "'Manrope', sans-serif" }}>{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ---- Node Popover ----
function NodePopover({ node, onClose, onExamine, onStatusChange }) {
  const colors = { mastered: '#10B981', partial: '#F59E0B', struggling: '#EF4444' };
  const icons = { mastered: <CheckCircle2 size={12} />, partial: <MinusCircle size={12} />, struggling: <AlertCircle size={12} /> };
  return (
    <div className="mx-3 mb-3 rounded-xl p-4" style={{ background: '#fff', border: '1px solid #E5E5E5', boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }} data-testid="node-popover">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-bold" style={{ color: '#1A1A1A', fontFamily: "'Manrope', sans-serif" }}>{node.label}</span>
        <button onClick={onClose} style={{ color: '#A1A1AA' }}><X size={14} /></button>
      </div>
      <div className="flex gap-1.5 mb-3">
        {['mastered', 'partial', 'struggling'].map(s => (
          <button key={s} onClick={() => onStatusChange(node, s)} className="flex-1 flex items-center justify-center gap-1 py-1.5 rounded-lg text-xs font-semibold transition-all" data-testid={`status-${s}-btn`}
            style={{ border: `1px solid ${node.status === s ? colors[s] : '#E5E5E5'}`, background: node.status === s ? colors[s] + '18' : 'transparent', color: node.status === s ? colors[s] : '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>
            {icons[s]} {s}
          </button>
        ))}
      </div>
      <button data-testid="generate-questions-btn" onClick={() => onExamine(node.label)} className="w-full py-2 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5" style={{ background: node.status === 'struggling' ? '#EF4444' : '#0F5132', color: '#fff', fontFamily: "'Manrope', sans-serif" }}>
        <Brain size={12} /> Generate Practice Questions
      </button>
    </div>
  );
}

// ---- Examiner Modal ----
function ExaminerModal({ concept, onClose }) {
  const [questions, setQuestions] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/examine`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ concept_name: concept }) });
        const data = await res.json();
        setQuestions(data.practice_questions);
      } catch { setQuestions(`## Practice Questions: ${concept}\n\nBackend not reachable.`); }
      finally { setLoading(false); }
    })();
  }, [concept]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }} onClick={onClose}>
      <div className="rounded-2xl w-[600px] max-w-[96vw] max-h-[80vh] flex flex-col" style={{ background: '#fff', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }} onClick={e => e.stopPropagation()} data-testid="examiner-modal">
        <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid #E5E5E5' }}>
          <div>
            <h3 className="text-base font-bold" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>Practice Questions</h3>
            <p className="text-xs mt-0.5" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>Targeted for: <b>{concept}</b></p>
          </div>
          <button onClick={onClose} style={{ color: '#A1A1AA' }} data-testid="close-examiner-btn"><X size={18} /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-6">
          {loading
            ? <div className="flex items-center gap-2 text-sm" style={{ color: '#A1A1AA' }}><Loader2 size={15} className="animate-spin" /> Generating questions...</div>
            : <div style={{ fontFamily: "'Crimson Pro', serif", fontSize: '15px', lineHeight: '1.8', color: '#1A1A1A' }}>
                <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>{questions}</ReactMarkdown>
              </div>
          }
        </div>
      </div>
    </div>
  );
}

// ---- Mutation Modal ----
function MutateModal({ page, onClose, onMutate }) {
  const [doubt, setDoubt] = useState('');
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!doubt.trim()) return;
    setBusy(true);
    await onMutate(page, doubt);
    setBusy(false);
    onClose();
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)', backdropFilter: 'blur(4px)' }} onClick={onClose}>
      <div className="rounded-2xl p-7 w-[480px] max-w-[94vw]" style={{ background: '#fff', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }} onClick={e => e.stopPropagation()} data-testid="mutation-modal">
        <h3 className="text-lg font-bold mb-1" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>Ask a Doubt</h3>
        <p className="text-xs mb-4 leading-relaxed" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
          Describe your confusion. AuraGraph will permanently rewrite this section.
        </p>
        <div className="rounded-lg px-3 py-2.5 mb-4 text-xs line-clamp-3 leading-relaxed" style={{ background: '#F6F5F0', border: '1px solid #E5E5E5', color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
          {page?.slice(0, 200)}...
        </div>
        <textarea
          data-testid="doubt-input"
          rows={3}
          autoFocus
          value={doubt}
          onChange={e => setDoubt(e.target.value)}
          placeholder="e.g. Why does convolution in time become multiplication in frequency?"
          className="w-full px-4 py-3 rounded-lg text-sm outline-none resize-y mb-4"
          style={{ border: '1px solid #D4D4D8', fontFamily: "'Manrope', sans-serif" }}
        />
        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm font-medium" style={{ border: '1px solid #D4D4D8', color: '#52525B' }} data-testid="cancel-mutation-btn">Cancel</button>
          <button data-testid="mutate-btn" onClick={go} disabled={busy || !doubt.trim()} className="px-5 py-2 rounded-lg text-sm font-semibold flex items-center gap-2" style={{ background: '#8B5CF6', color: '#fff', opacity: (busy || !doubt.trim()) ? 0.5 : 1, fontFamily: "'Manrope', sans-serif" }}>
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {busy ? 'Mutating...' : 'Mutate This Page'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- Main Workspace ----
export default function NotebookWorkspace() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [notebook, setNotebook] = useState(null);
  const [note, setNote] = useState('');
  const [prof, setProf] = useState('Intermediate');
  const [slidesFiles, setSlidesFiles] = useState([]);
  const [textbookFiles, setTextbookFiles] = useState([]);
  const [fusing, setFusing] = useState(false);
  const [fuseProgress, setFuseProgress] = useState('');
  const [mutating, setMutating] = useState(false);
  const [currentPage, setCurrentPage] = useState(0);
  const [gapText, setGapText] = useState('');
  const [mutatedPages, setMutatedPages] = useState(new Set());
  const [doubtsLog, setDoubtsLog] = useState([]);
  const [rightTab, setRightTab] = useState('map');
  const [graphNodes, setGraphNodes] = useState([]);
  const [graphEdges, setGraphEdges] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [examinerConcept, setExaminerConcept] = useState(null);

  const pages = useMemo(() => {
    if (!note) return [];
    const byH2 = note.split(/(?=^## )/m).map(s => s.trim()).filter(Boolean);
    if (byH2.length > 1) {
      const merged = [];
      let buffer = '';
      for (const section of byH2) {
        const body = section.replace(/^## .+$/m, '').trim();
        if (body.length < 100) { buffer = buffer ? buffer + '\n\n' + section : section; }
        else { merged.push(buffer ? buffer + '\n\n' + section : section); buffer = ''; }
      }
      if (buffer) merged.push(buffer);
      return merged.filter(Boolean);
    }
    const byH3 = note.split(/(?=^### )/m).map(s => s.trim()).filter(Boolean);
    if (byH3.length > 1) return byH3;
    const paras = note.split(/\n\n+/).filter(p => p.trim().length > 40);
    const chunks = [];
    let current = '';
    for (const para of paras) {
      if (current.length + para.length > 700 && current.length > 150) { chunks.push(current.trim()); current = para; }
      else { current += (current ? '\n\n' : '') + para; }
    }
    if (current) chunks.push(current.trim());
    return chunks.length ? chunks : [note];
  }, [note]);

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/notebooks/${id}`, { headers: authHeaders() });
        if (!res.ok) throw new Error();
        const nb = await res.json();
        setNotebook(nb);
        setNote(nb.note || '');
        setProf(nb.proficiency || 'Intermediate');
        if (nb.graph?.nodes?.length) { setGraphNodes(nb.graph.nodes); setGraphEdges(nb.graph.edges || []); }
      } catch {
        const local = ls_getNotebook(id);
        if (local) { setNotebook(local); setNote(local.note || ''); setProf(local.proficiency || 'Intermediate'); if (local.graph?.nodes?.length) { setGraphNodes(local.graph.nodes); setGraphEdges(local.graph.edges || []); } }
        else { setNotebook({ id, name: 'Untitled', course: '' }); }
      }
    })();
  }, [id]);

  const saveNote = async (newNote, newProf) => {
    ls_saveNote(id, newNote, newProf);
    try {
      await fetch(`${API}/notebooks/${id}/note`, { method: 'PATCH', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ note: newNote, proficiency: newProf }) });
    } catch {}
  };

  const extractGraph = async (noteText) => {
    try {
      const res = await fetch(`${API}/extract-concepts`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: noteText, notebook_id: id }) });
      const graph = await res.json();
      if (graph.nodes?.length) { setGraphNodes(graph.nodes); setGraphEdges(graph.edges || []); }
    } catch {}
  };

  const handleFuse = async () => {
    if (!slidesFiles.length || !textbookFiles.length) return;
    setFusing(true);
    setFuseProgress('Uploading PDFs...');
    try {
      const form = new FormData();
      slidesFiles.forEach(f => form.append('slides_pdfs', f));
      textbookFiles.forEach(f => form.append('textbook_pdfs', f));
      form.append('proficiency', prof);
      setFuseProgress('Running Fusion Agent...');
      const res = await fetch(`${API}/upload-fuse-multi`, { method: 'POST', body: form });
      const data = await res.json();
      setNote(data.fused_note);
      setCurrentPage(0);
      await saveNote(data.fused_note, prof);
      setFuseProgress('Extracting concepts...');
      await extractGraph(data.fused_note);
    } catch {
      setNote('## Backend Not Reachable\n\nPlease ensure the backend is running.');
    }
    setFusing(false);
    setFuseProgress('');
  };

  const handleMutate = useCallback(async (page, doubt) => {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const logId = Date.now();
    try {
      const res = await fetch(`${API}/mutate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ original_paragraph: page, student_doubt: doubt }) });
      const data = await res.json();
      const heading = pages[currentPage]?.match(/^(## .+)/m)?.[1];
      const parts = note.split(/(?=^## )/m);
      const idx = heading ? parts.findIndex(p => p.trimStart().startsWith(heading)) : -1;
      let newNote;
      if (idx !== -1) { parts[idx] = data.mutated_paragraph + '\n'; newNote = parts.join(''); }
      else { newNote = data.mutated_paragraph; }
      setNote(newNote);
      setGapText(data.concept_gap);
      setMutatedPages(prev => new Set([...prev, currentPage]));
      await saveNote(newNote, prof);
      extractGraph(newNote);
      setDoubtsLog(prev => [{ id: logId, pageIdx: currentPage, doubt, insight: data.concept_gap || 'Page updated.', time: timestamp, success: true }, ...prev]);
      setRightTab('doubts');
    } catch {
      setDoubtsLog(prev => [{ id: logId, pageIdx: currentPage, doubt, insight: 'Backend unreachable.', time: timestamp, success: false }, ...prev]);
      setRightTab('doubts');
    }
  }, [note, prof, id, currentPage, pages]);

  const handleNodeStatusChange = async (node, newStatus) => {
    setGraphNodes(prev => prev.map(n => n.id === node.id ? { ...n, status: newStatus } : n));
    setSelectedNode(prev => prev?.id === node.id ? { ...prev, status: newStatus } : prev);
    try {
      await fetch(`${API}/notebooks/${id}/graph/update`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...authHeaders() }, body: JSON.stringify({ concept_name: node.label, status: newStatus }) });
    } catch {}
  };

  if (!notebook) return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: '#FDFBF7' }}>
      <Loader2 size={28} className="animate-spin" style={{ color: '#A1A1AA' }} />
    </div>
  );

  const hasNote = note.trim().length > 0;
  const masterCount = graphNodes.filter(n => n.status === 'mastered').length;
  const partialCount = graphNodes.filter(n => n.status === 'partial').length;
  const strugCount = graphNodes.filter(n => n.status === 'struggling').length;

  return (
    <div className="h-screen flex flex-col overflow-hidden" style={{ background: '#FDFBF7' }} data-testid="notebook-workspace">
      {/* Header */}
      <header className="flex-shrink-0 px-5 h-14 flex items-center justify-between" style={{ background: 'rgba(253,251,247,0.9)', backdropFilter: 'blur(12px)', borderBottom: '1px solid #E5E5E5' }}>
        <div className="flex items-center gap-3">
          <button data-testid="back-to-dashboard" onClick={() => navigate('/dashboard')} className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg transition-all" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
            <ArrowLeft size={13} /> Back
          </button>
          <div className="w-px h-5" style={{ background: '#E5E5E5' }} />
          <div>
            <div className="font-semibold text-sm" style={{ color: '#1A1A1A', fontFamily: "'Manrope', sans-serif" }}>{notebook.name}</div>
            <div className="text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>{notebook.course}</div>
          </div>
        </div>
        {hasNote && (
          <div className="flex items-center gap-3">
            <span className="text-xs px-3 py-1 rounded-full font-medium" style={{ background: '#F6F5F0', border: '1px solid #E5E5E5', color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>{prof}</span>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full" style={{ background: '#fff', border: '1px solid #E5E5E5' }}>
              <button data-testid="prev-page" onClick={() => setCurrentPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0} style={{ color: currentPage === 0 ? '#D4D4D8' : '#52525B' }}><ChevronLeft size={14} /></button>
              <span className="text-xs min-w-[50px] text-center font-medium" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>{currentPage + 1} / {pages.length}</span>
              <button data-testid="next-page" onClick={() => setCurrentPage(Math.min(pages.length - 1, currentPage + 1))} disabled={currentPage >= pages.length - 1} style={{ color: currentPage >= pages.length - 1 ? '#D4D4D8' : '#52525B' }}><ChevronRight size={14} /></button>
            </div>
            <button data-testid="ask-doubt-btn" onClick={() => setMutating(true)} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition-all active:scale-[0.97]" style={{ background: '#8B5CF6', color: '#fff', fontFamily: "'Manrope', sans-serif" }}>
              <Sparkles size={13} /> Ask a Doubt
            </button>
          </div>
        )}
      </header>

      {/* Body */}
      <div className="flex-1 flex overflow-hidden">
        {!hasNote ? (
          <div className="flex-1 overflow-y-auto flex items-center justify-center px-6 py-10">
            <div className="max-w-[600px] w-full">
              <div className="text-center mb-10">
                <div className="w-14 h-14 rounded-2xl mx-auto mb-5 flex items-center justify-center" style={{ background: '#0F5132' }}>
                  <Zap size={26} color="white" strokeWidth={1.5} />
                </div>
                <h2 className="text-2xl font-bold mb-2" style={{ fontFamily: "'Playfair Display', serif", color: '#1A1A1A' }}>Generate Fused Notes</h2>
                <p className="text-sm leading-relaxed" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>
                  Upload your course materials. AuraGraph will fuse them into personalised study notes calibrated to your level.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-4 mb-6">
                <FileDrop label="Professor's Slides" icon={BookOpen} files={slidesFiles} onFiles={setSlidesFiles} />
                <FileDrop label="Textbook PDFs" icon={FileText} files={textbookFiles} onFiles={setTextbookFiles} />
              </div>
              <div className="mb-6">
                <label className="block text-xs font-medium mb-2 uppercase tracking-wider" style={{ color: '#52525B', fontFamily: "'Manrope', sans-serif" }}>Proficiency Level</label>
                <div className="flex gap-3">
                  {[['Beginner', 'Analogies first'], ['Intermediate', 'Balanced depth'], ['Advanced', 'Full rigour']].map(([p, d]) => (
                    <button key={p} data-testid={`prof-${p.toLowerCase()}`} onClick={() => setProf(p)} className="flex-1 py-3 px-2 rounded-lg text-center transition-all"
                      style={{ border: `1.5px solid ${prof === p ? '#0F5132' : '#E5E5E5'}`, background: prof === p ? '#0F5132' : '#fff', color: prof === p ? '#fff' : '#52525B', fontFamily: "'Manrope', sans-serif" }}>
                      <div className="text-sm font-semibold">{p}</div>
                      <div className="text-xs mt-0.5" style={{ opacity: 0.7 }}>{d}</div>
                    </button>
                  ))}
                </div>
              </div>
              <button data-testid="generate-notes-btn" onClick={handleFuse} disabled={fusing || !slidesFiles.length || !textbookFiles.length}
                className="w-full py-3.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98]"
                style={{ background: '#0F5132', color: '#fff', opacity: (fusing || !slidesFiles.length || !textbookFiles.length) ? 0.5 : 1, fontFamily: "'Manrope', sans-serif" }}>
                {fusing ? <><Loader2 size={15} className="animate-spin" /> {fuseProgress}</> : <><Sparkles size={15} /> Generate Digital Notes</>}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto flex justify-center py-8 px-6" style={{ background: '#F0EDE6' }}>
            <div className="max-w-[720px] w-full">
              {gapText && (
                <div className="mb-4 px-4 py-3 rounded-lg flex items-start gap-2 text-xs" style={{ background: '#FEF3C7', border: '1px solid #FDE68A', color: '#92400E' }} data-testid="gap-banner">
                  <Brain size={13} className="flex-shrink-0 mt-0.5" />
                  <div className="flex-1"><b>Concept gap:</b> {gapText}</div>
                  <button onClick={() => setGapText('')} style={{ color: '#92400E' }}><X size={12} /></button>
                </div>
              )}
              {/* Notebook page */}
              <div className="rounded-sm overflow-hidden flex" style={{ background: '#fff', boxShadow: '0 2px 12px rgba(0,0,0,0.08), 0 12px 40px rgba(0,0,0,0.06)', border: '1px solid #D4D4D8' }}>
                <div className="w-9 flex-shrink-0 flex flex-col items-center justify-evenly py-8" style={{ background: '#FAFAF9', borderRight: '2px solid #E5E7EB' }}>
                  {[0,1,2,3,4,5].map(i => <div key={i} className="w-4 h-4 rounded-full" style={{ background: '#fff', border: '2px solid #CBD5E1', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.12)' }} />)}
                </div>
                <div className="w-px flex-shrink-0" style={{ background: '#FCA5A5' }} />
                <div className="flex-1 px-10 py-10 min-w-0" style={{ minHeight: '500px' }}>
                  <div className="flex justify-between items-center mb-7 pb-3" style={{ borderBottom: '1px solid #E5E5E5' }}>
                    <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>{notebook?.name}</span>
                    <div className="flex items-center gap-2">
                      {mutatedPages.has(currentPage) && <span className="text-xs font-bold px-2 py-0.5 rounded-full" style={{ background: '#F5F3FF', color: '#8B5CF6', border: '1px solid #C4B5FD', fontFamily: "'Manrope', sans-serif" }}>Mutated</span>}
                      <span className="text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>Page {currentPage + 1} of {pages.length}</span>
                    </div>
                  </div>
                  <NoteRenderer content={pages[currentPage]} />
                  <div className="mt-8 pt-3 flex justify-between items-center" style={{ borderTop: '1px solid #E5E5E5' }}>
                    <span className="text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>{notebook?.course}</span>
                    <span className="text-xs" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>AuraGraph &middot; {prof}</span>
                  </div>
                </div>
              </div>
              <div className="mt-4 flex justify-center gap-3">
                <button data-testid="re-upload-btn" onClick={() => setNote('')} className="flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg" style={{ color: '#52525B', border: '1px solid #E5E5E5', fontFamily: "'Manrope', sans-serif" }}>
                  <Upload size={12} /> Re-upload
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Right Sidebar */}
        <aside className="w-[300px] min-w-[300px] flex flex-col overflow-hidden" style={{ borderLeft: '1px solid #E5E5E5', background: '#fff' }}>
          <div className="flex flex-shrink-0" style={{ borderBottom: '1px solid #E5E5E5' }}>
            {[{ key: 'map', label: 'Concepts', icon: <Brain size={12} /> }, { key: 'doubts', label: `Doubts${doubtsLog.length ? ` (${doubtsLog.length})` : ''}`, icon: <MessageCircle size={12} /> }].map(tab => (
              <button key={tab.key} data-testid={`tab-${tab.key}`} onClick={() => setRightTab(tab.key)} className="flex-1 flex items-center justify-center gap-1.5 py-3 text-xs font-semibold transition-all"
                style={{ borderBottom: rightTab === tab.key ? '2px solid #0F5132' : '2px solid transparent', color: rightTab === tab.key ? '#0F5132' : '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>
                {tab.icon} {tab.label}
              </button>
            ))}
          </div>

          {rightTab === 'map' ? (
            <div className="flex-1 flex flex-col overflow-hidden">
              {graphNodes.length > 0 && (
                <div className="px-4 py-3 flex gap-2" style={{ borderBottom: '1px solid #E5E5E5' }}>
                  {[['mastered', '#10B981', masterCount], ['partial', '#F59E0B', partialCount], ['struggling', '#EF4444', strugCount]].map(([k, c, count]) => (
                    <div key={k} className="flex-1 text-center rounded-lg py-1.5" style={{ background: c + '12', border: `1px solid ${c}30` }}>
                      <div className="text-base font-bold" style={{ color: c }}>{count}</div>
                      <div className="text-[9px] font-semibold uppercase" style={{ color: c }}>{k}</div>
                    </div>
                  ))}
                </div>
              )}
              <div className="flex-1 overflow-y-auto px-1 pt-2">
                <KnowledgeGraph nodes={graphNodes} edges={graphEdges} onNodeClick={n => setSelectedNode(prev => prev?.id === n.id ? null : n)} />
                {selectedNode && <NodePopover node={selectedNode} onClose={() => setSelectedNode(null)} onExamine={label => { setExaminerConcept(label); setSelectedNode(null); }} onStatusChange={handleNodeStatusChange} />}
                {graphNodes.length > 0 && (
                  <div className="px-3 pt-2 pb-3" style={{ borderTop: '1px solid #E5E5E5' }}>
                    <div className="text-[10px] font-semibold uppercase tracking-wider mb-2" style={{ color: '#A1A1AA' }}>All Concepts</div>
                    {graphNodes.map(n => {
                      const c = STATUS_COLOR[n.status] || STATUS_COLOR.partial;
                      return (
                        <div key={n.id} onClick={() => setSelectedNode(prev => prev?.id === n.id ? null : n)} className="flex items-center gap-2 px-2 py-1.5 rounded-lg mb-0.5 cursor-pointer transition-all"
                          style={{ background: selectedNode?.id === n.id ? '#F6F5F0' : 'transparent' }}>
                          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: c.fill, boxShadow: `0 0 4px ${c.fill}66` }} />
                          <span className="flex-1 text-xs truncate" style={{ fontFamily: "'Manrope', sans-serif" }}>{n.label}</span>
                          <span className="text-[10px] font-semibold capitalize" style={{ color: c.fill }}>{n.status}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto px-3 py-3">
              {doubtsLog.filter(d => d.pageIdx === currentPage).length === 0 ? (
                <div className="flex flex-col items-center justify-center h-48 text-center">
                  <MessageCircle size={24} style={{ color: '#D4D4D8' }} className="mb-2" />
                  <p className="text-xs leading-relaxed" style={{ color: '#A1A1AA', fontFamily: "'Manrope', sans-serif" }}>No doubts on page {currentPage + 1} yet.<br />Click <b>Ask a Doubt</b> to add one.</p>
                </div>
              ) : (
                doubtsLog.filter(d => d.pageIdx === currentPage).map(d => (
                  <div key={d.id} className="mb-4">
                    <div className="flex justify-end mb-1">
                      <div className="max-w-[85%] px-3 py-2 rounded-xl rounded-br-sm text-xs leading-relaxed" style={{ background: '#8B5CF6', color: '#fff', fontFamily: "'Manrope', sans-serif" }}>
                        {d.doubt}
                      </div>
                    </div>
                    <div className="flex justify-start">
                      <div className="max-w-[90%] px-3 py-2 rounded-xl rounded-bl-sm text-xs leading-relaxed" style={{ background: '#F5F3FF', border: '1px solid #DDD6FE', color: '#4C1D95', fontFamily: "'Manrope', sans-serif" }}>
                        <div className="text-[10px] font-bold mb-1" style={{ color: '#8B5CF6' }}>AuraGraph</div>
                        {d.insight}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </aside>
      </div>

      {mutating && pages.length > 0 && <MutateModal page={pages[currentPage]} onClose={() => setMutating(false)} onMutate={handleMutate} />}
      {examinerConcept && <ExaminerModal concept={examinerConcept} onClose={() => setExaminerConcept(null)} />}
    </div>
  );
}
