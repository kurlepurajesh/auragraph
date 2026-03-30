import { useState, useCallback } from "react";

const INITIAL_NOTE = `The Convolution Theorem states that convolution in the time domain corresponds to multiplication in the frequency domain. Formally, if x(t) and h(t) are signals with Fourier transforms X(f) and H(f) respectively, then the Fourier transform of their convolution equals the product X(f) times H(f).

This is remarkably powerful: instead of computing the expensive convolution integral directly, you can transform both signals, multiply pointwise, then inverse-transform the result. For LTI systems, this means the output spectrum is simply the input spectrum shaped by the system frequency response H(f). Engineers exploit this constantly in digital filtering and spectral analysis.`;

const NODES = [
  { id:1, label:"Fourier Transform",   status:"mastered",   x:50, y:18 },
  { id:2, label:"Convolution Theorem", status:"struggling", x:50, y:44 },
  { id:3, label:"LTI Systems",         status:"partial",    x:20, y:70 },
  { id:4, label:"Freq. Response",      status:"mastered",   x:80, y:70 },
  { id:5, label:"Z-Transform",         status:"partial",    x:50, y:90 },
];
const EDGES = [[1,2],[2,3],[2,4],[3,5],[4,5]];
const S = {
  mastered:   { bg:"#16a34a", ring:"#4ade80", dot:"#86efac" },
  partial:    { bg:"#b45309", ring:"#f59e0b", dot:"#fcd34d" },
  struggling: { bg:"#b91c1c", ring:"#ef4444", dot:"#fca5a5" },
};

function Graph({ nodes }) {
  return (
    <svg viewBox="0 0 100 100" style={{width:"100%",height:"100%"}}>
      <defs>
        <filter id="glow">
          <feGaussianBlur stdDeviation="1.8" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>
      {EDGES.map(([a,b],i)=>{
        const na=nodes.find(n=>n.id===a), nb=nodes.find(n=>n.id===b);
        return <line key={i} x1={na.x} y1={na.y} x2={nb.x} y2={nb.y} stroke="#1e3a5f" strokeWidth="0.7" strokeDasharray="2,1.5"/>;
      })}
      {nodes.map(nd=>{
        const c=S[nd.status];
        return (
          <g key={nd.id}>
            <circle cx={nd.x} cy={nd.y} r="7" fill={c.bg} filter="url(#glow)" opacity="0.85"/>
            <circle cx={nd.x} cy={nd.y} r="7" fill="none" stroke={c.ring} strokeWidth="1.2"/>
            <text x={nd.x} y={nd.y+11} textAnchor="middle" fontSize="3.5" fill="#94a3b8" fontFamily="monospace">{nd.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Modal({ paragraph, onClose, onMutate }) {
  const [doubt, setDoubt] = useState("");
  const [busy, setBusy] = useState(false);
  const go = async () => {
    if (!doubt.trim()) return;
    setBusy(true);
    await onMutate(paragraph, doubt);
    setBusy(false);
    onClose();
  };
  return (
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.8)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:99}}>
      <div style={{background:"#0d1b2a",border:"1px solid #1e3a5f",borderRadius:14,padding:30,width:540,maxWidth:"92vw",boxShadow:"0 30px 80px #000a"}}>
        <div style={{fontSize:16,fontWeight:800,color:"#e2e8f0",marginBottom:6,fontFamily:"'Courier New',monospace",letterSpacing:0.5}}>
          Flag a Doubt
        </div>
        <div style={{fontSize:12,color:"#475569",marginBottom:14}}>
          Describe your confusion. AuraGraph will permanently rewrite this section.
        </div>
        <div style={{background:"#0f172a",borderRadius:8,padding:12,fontSize:12,color:"#64748b",fontFamily:"Georgia,serif",lineHeight:1.7,marginBottom:14,maxHeight:90,overflowY:"auto",border:"1px solid #1e293b"}}>
          {paragraph.slice(0,220)}...
        </div>
        <textarea
          value={doubt} onChange={e=>setDoubt(e.target.value)} rows={4}
          placeholder="e.g. I can't visualise why multiplying in frequency domain equals convolution in time..."
          style={{width:"100%",background:"#0f172a",border:"1px solid #1e3a5f",borderRadius:8,padding:12,color:"#e2e8f0",fontSize:13,fontFamily:"Georgia,serif",resize:"vertical",outline:"none",boxSizing:"border-box"}}
        />
        <div style={{display:"flex",gap:10,marginTop:14,justifyContent:"flex-end"}}>
          <button onClick={onClose} style={{padding:"8px 18px",borderRadius:8,border:"1px solid #1e293b",background:"transparent",color:"#475569",cursor:"pointer",fontSize:13}}>Cancel</button>
          <button onClick={go} disabled={busy||!doubt.trim()} style={{padding:"9px 22px",borderRadius:8,border:"none",background:busy?"#1e3a8a":"linear-gradient(135deg,#1d4ed8,#7c3aed)",color:"#fff",cursor:busy?"not-allowed":"pointer",fontSize:13,fontWeight:700}}>
            {busy ? "Mutating..." : "Mutate Note"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [note, setNote] = useState(INITIAL_NOTE);
  const [nodes, setNodes] = useState(NODES);
  const [modal, setModal] = useState(false);
  const [mutated, setMutated] = useState(false);
  const [gap, setGap] = useState("");
  const [prof, setProf] = useState("Intermediate");

  const handleMutate = useCallback(async (_para, doubt) => {
    await new Promise(r=>setTimeout(r,1500));
    setNote(`The Convolution Theorem becomes intuitive when thought of as a translation between two mathematical languages. In the time domain, convolution asks: how does a system with impulse response h(t) respond to every infinitesimal slice of input x(t)? It slides h over x, multiplying and integrating at every instant.

The frequency domain offers a compelling shortcut. Each frequency component of x simply gets scaled and phase-shifted independently by H(f), with no interaction between frequencies. So multiplying X(f) by H(f) pointwise captures all of this at once. Think of it like switching from hand-painting each pixel (time domain) to applying a colour filter over the whole image in one pass (frequency domain). Same result, drastically less work.

Inverse-transforming the product brings you back to the time-domain output. This is why DSP engineers default to the frequency domain: filtering, equalisation, and spectral shaping all reduce to pointwise multiplication followed by a single IFFT.`);
    setGap("Student confused the computational process of convolution with its spectral equivalence.");
    setMutated(true);
    setNodes(prev=>prev.map(n=>n.label==="Convolution Theorem"?{...n,status:"partial"}:n));
  }, []);

  const bg = "#020817";
  const border = "1px solid #1e293b";

  return (
    <div style={{minHeight:"100vh",background:bg,color:"#e2e8f0",fontFamily:"'Courier New',monospace",display:"flex",flexDirection:"column"}}>
      {/* Header */}
      <header style={{padding:"14px 24px",borderBottom:border,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          <div style={{width:38,height:38,borderRadius:10,background:"linear-gradient(135deg,#1d4ed8,#7c3aed)",display:"flex",alignItems:"center",justifyContent:"center",fontSize:19,boxShadow:"0 0 18px #3b82f644"}}>
            ⬡
          </div>
          <div>
            <div style={{fontSize:17,fontWeight:800,letterSpacing:1}}>AuraGraph</div>
            <div style={{fontSize:10,color:"#475569",marginTop:-1}}>IIT Roorkee · Team Wowffulls</div>
          </div>
        </div>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <span style={{fontSize:11,color:"#475569",marginRight:2}}>Proficiency:</span>
          {["Beginner","Intermediate","Advanced"].map(p=>(
            <button key={p} onClick={()=>setProf(p)} style={{padding:"4px 11px",borderRadius:6,fontSize:11,cursor:"pointer",border:"1px solid "+(prof===p?"#3b82f6":"#1e293b"),background:prof===p?"#1e3a5f":"transparent",color:prof===p?"#93c5fd":"#64748b",transition:"all 0.15s"}}>
              {p}
            </button>
          ))}
          <div style={{marginLeft:6,fontSize:10,padding:"3px 9px",borderRadius:4,border:border,color:"#f59e0b",background:"#1c1200"}}>
            DEMO MODE
          </div>
        </div>
      </header>

      {/* Body */}
      <main style={{flex:1,display:"grid",gridTemplateColumns:"1fr 310px",minHeight:0}}>

        {/* Left – Note */}
        <section style={{borderRight:border,display:"flex",flexDirection:"column"}}>
          <div style={{padding:"12px 22px",borderBottom:border,display:"flex",alignItems:"center",justifyContent:"space-between"}}>
            <div>
              <div style={{fontSize:13,fontWeight:700,color:"#e2e8f0"}}>Digital Note — DSP: Convolution Theorem</div>
              <div style={{fontSize:10,color:"#475569",marginTop:1}}>Fused: Oppenheim 3.2 + Prof. Kumar Slides · {prof}</div>
            </div>
            <div style={{display:"flex",gap:8,alignItems:"center"}}>
              <span style={{fontSize:11,padding:"2px 9px",borderRadius:4,background:S[mutated?"partial":"struggling"].bg+"33",color:S[mutated?"partial":"struggling"].dot,border:`1px solid ${S[mutated?"partial":"struggling"].bg}66`}}>
                {mutated?"Partial":"Struggling"}
              </span>
              {mutated&&<span style={{fontSize:10,color:"#a78bfa",background:"#1e1b4b",border:"1px solid #4c1d95",borderRadius:4,padding:"2px 8px"}}>MUTATED</span>}
            </div>
          </div>

          <div style={{flex:1,padding:"22px 26px",overflowY:"auto"}}>
            {mutated&&gap&&(
              <div style={{marginBottom:18,padding:"10px 14px",background:"#1e1b4b",border:"1px solid #4c1d95",borderRadius:8,fontSize:12,color:"#a78bfa",lineHeight:1.6}}>
                <b>Gap diagnosed: </b>{gap}
              </div>
            )}
            <div style={{fontSize:14,lineHeight:1.9,color:"#cbd5e1",fontFamily:"Georgia,'Times New Roman',serif"}}>
              {note.split("\n\n").map((p,i)=><p key={i} style={{marginBottom:20}}>{p}</p>)}
            </div>
          </div>

          <div style={{padding:"12px 22px",borderTop:border,display:"flex",gap:12,alignItems:"center"}}>
            <button onClick={()=>setModal(true)}
              style={{padding:"10px 22px",borderRadius:8,cursor:"pointer",background:"linear-gradient(135deg,#1d4ed8,#7c3aed)",color:"#fff",fontWeight:700,fontSize:13,border:"none",fontFamily:"monospace",boxShadow:"0 0 24px #3b82f630",letterSpacing:0.3}}>
              Flag Confusion → Mutate Note
            </button>
            <span style={{fontSize:11,color:"#334155"}}>Rewrite persists permanently</span>
          </div>
        </section>

        {/* Right – Graph + Examiner */}
        <aside style={{display:"flex",flexDirection:"column",background:"#020c1b"}}>
          <div style={{padding:"12px 18px",borderBottom:border}}>
            <div style={{fontSize:12,fontWeight:700}}>Cognitive Knowledge Map</div>
            <div style={{fontSize:10,color:"#334155",marginTop:1}}>Live mastery graph</div>
          </div>

          <div style={{flex:1,padding:12,minHeight:220}}>
            <Graph nodes={nodes}/>
          </div>

          <div style={{padding:"8px 18px",borderTop:border,display:"flex",gap:12}}>
            {Object.entries(S).map(([k,v])=>(
              <div key={k} style={{display:"flex",alignItems:"center",gap:5}}>
                <div style={{width:8,height:8,borderRadius:"50%",background:v.bg,boxShadow:`0 0 5px ${v.ring}`}}/>
                <span style={{fontSize:10,color:"#475569",textTransform:"capitalize"}}>{k}</span>
              </div>
            ))}
          </div>

          <div style={{margin:"0 10px 10px",padding:12,background:"#0a0f1e",borderRadius:10,border:"1px solid #1e293b"}}>
            <div style={{fontSize:11,fontWeight:700,color:"#f59e0b",marginBottom:8}}>Examiner Agent — Weak Zones</div>
            {["Convolution Theorem","Z-Transform"].map(t=>(
              <div key={t} style={{padding:"6px 10px",marginBottom:5,background:"#160808",border:"1px solid #7f1d1d",borderRadius:6,fontSize:11,color:"#fca5a5"}}>
                5 problems on: <b>{t}</b>
              </div>
            ))}
            <button style={{width:"100%",marginTop:4,padding:"8px 0",background:"transparent",border:"1px solid #7f1d1d",borderRadius:6,color:"#ef4444",fontSize:11,cursor:"pointer",fontFamily:"monospace",letterSpacing:0.3}}>
              Generate Practice Paper
            </button>
          </div>
        </aside>
      </main>

      {modal&&<Modal paragraph={note} onClose={()=>setModal(false)} onMutate={handleMutate}/>}
    </div>
  );
}
