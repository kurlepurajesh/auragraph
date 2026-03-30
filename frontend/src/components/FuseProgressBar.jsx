import React, { useState, useEffect, useRef } from 'react';
import {
    AlertCircle,
    ArrowLeft,
    BookOpen,
    Brain,
    CheckCircle2,
    Compass,
    GitBranch,
    History,
    Languages,
    Layers,
    MessageCircle,
    MinusCircle,
    RefreshCw,
    Search,
    Sparkles,
    Star,
    Target,
    Timer,
} from 'lucide-react';

// Study-science facts — short, punchy, performance-relevant
// Stored as a plain array so zero network cost; cached by the JS bundle
const FACTS = [
    { icon: Brain, text: 'Spaced repetition improves recall by up to 200% compared to cramming.' },
    { icon: History, text: 'Sleep consolidates memory. Studying before bed and reviewing the next morning is scientifically optimal.' },
    { icon: Languages, text: 'Writing by hand activates more of the brain than typing, even when studying digital notes.' },
    { icon: RefreshCw, text: 'The “Forgetting Curve” shows 70% of new information is lost within 24 hours without review.' },
    { icon: Search, text: 'Retrieval practice (testing yourself) is about 2× more effective than re-reading notes.' },
    { icon: Timer, text: 'The Pomodoro method (25 minutes focus + 5 minutes rest) helps prevent cognitive fatigue.' },
    { icon: GitBranch, text: 'Interleaving topics strengthens long-term retention more than studying one topic in a block.' },
    { icon: Layers, text: 'Concept mapping improves understanding by making hidden relationships between ideas visible.' },
    { icon: Compass, text: 'Even 10 minutes of mindfulness before studying can improve focus and working memory.' },
    { icon: AlertCircle, text: 'Mild dehydration (1–2%) can measurably reduce cognitive performance.' },
    { icon: Target, text: 'Students who set specific goals before a study session perform better on assessments.' },
    { icon: MessageCircle, text: 'Asking “why?” while studying (elaborative interrogation) strongly improves retention.' },
    { icon: Star, text: 'Instrumental music at slower tempos can improve concentration for many learners.' },
    { icon: ArrowLeft, text: 'Alertness often peaks around 10 AM and 3 PM, making them strong windows for deep study.' },
    { icon: BookOpen, text: 'Summarising concepts in your own words is one of the highest-yield study strategies.' },
    { icon: CheckCircle2, text: 'Connecting new information to prior knowledge reduces cognitive load and improves recall.' },
    { icon: Sparkles, text: 'A short walk before studying can boost readiness for learning and memory encoding.' },
    { icon: MinusCircle, text: 'Flashcards are most effective when you attempt recall before revealing the answer.' },
];

// Fisher-Yates shuffle — runs once per session, negligible cost
function shuffleFacts() {
    const arr = [...FACTS];
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

// Cache shuffled order per page session so facts don't reset on re-render
let _sessionFacts = null;
function getSessionFacts() {
    if (!_sessionFacts) _sessionFacts = shuffleFacts();
    return _sessionFacts;
}

export default function FuseProgressBar({ active }) {
    const [factIdx, setFactIdx] = useState(0);
    const [factVisible, setFactVisible] = useState(true);
    const facts = useRef(getSessionFacts()).current;

    useEffect(() => {
        if (!active) { setFactIdx(0); setFactVisible(true); return; }

        // Rotate facts every 8 s for faster insight cadence
        const ft = setInterval(() => {
            setFactVisible(false);
            setTimeout(() => {
                setFactIdx(i => (i + 1) % facts.length);
                setFactVisible(true);
            }, 350);
        }, 8000);

        return () => { clearInterval(ft); };
    }, [active, facts.length]);

    if (!active) return null;

    const currentFact = facts[factIdx];
    const FactIcon = currentFact.icon;
    const cubeLayers = [1, 2, 3];

    return (
        <div style={{ marginBottom: 20 }}>
            <div className="ag-fuse-loader-section">
                <div className="ag-cube-preloader" style={{ marginTop: 120 }} aria-hidden="true">
                    {cubeLayers.map((h) => (
                        cubeLayers.map((w) => (
                            cubeLayers.map((l) => (
                                <div
                                    key={`h${h}-w${w}-l${l}`}
                                    className="ag-cube"
                                    style={{ '--h': h, '--w': w, '--l': l, zIndex: -h }}
                                >
                                    <div className="ag-cube-face ag-cube-top" />
                                    <div className="ag-cube-face ag-cube-left" />
                                    <div className="ag-cube-face ag-cube-right" />
                                </div>
                            ))
                        ))
                    ))}
                </div>
            </div>

            {/* Rotating fact card (kept separate from cube loader) */}
            <div className="ag-fuse-insight-card" style={{
                marginTop: 140,
                opacity: factVisible ? 1 : 0,
                transform: factVisible ? 'translateY(0)' : 'translateY(4px)',
                transition: 'opacity 0.35s ease, transform 0.35s ease',
            }}>
                <div className="ag-fuse-insight-icon-wrap" aria-hidden="true">
                    <FactIcon size={20} className="ag-fuse-insight-icon" strokeWidth={2.1} />
                </div>
                <div className="ag-fuse-insight-body">
                    <div className="ag-fuse-insight-label">Did you know?</div>
                    <p className="ag-fuse-insight-text">{currentFact.text}</p>
                </div>
            </div>
        </div>
    );
}
