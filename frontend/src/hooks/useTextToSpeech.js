/**
 * useTextToSpeech — manages TTS state for the note workspace.
 *
 * Features:
 * - Per-page audio caching (blob URLs, freed on unmount)
 * - Sentence-level chunking so first audio arrives fast
 * - Play / pause / stop / speed / voice controls
 * - Azure Neural TTS via backend proxy (keeps API key server-side)
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import { API, authHeaders } from '../components/utils';

export const DEFAULT_VOICE = 'en-IN-F';

export function useTextToSpeech() {
    const [isPlaying,    setIsPlaying]    = useState(false);
    const [isLoading,    setIsLoading]    = useState(false);
    const [activePageIdx,setActivePageIdx]= useState(null);
    const [voice,        setVoice]        = useState(() => localStorage.getItem('ag_tts_voice') || DEFAULT_VOICE);
    const [speed,        setSpeed]        = useState(() => parseFloat(localStorage.getItem('ag_tts_speed') || '1'));
    const [voices,       setVoices]       = useState([]);
    const [azureReady,   setAzureReady]   = useState(false);
    const [error,        setError]        = useState('');

    const audioRef  = useRef(null);          // current HTMLAudioElement
    const cacheRef  = useRef({});            // pageIdx → blob URL
    const abortRef  = useRef(null);          // AbortController
    const modeRef   = useRef('audio');       // 'audio' | 'browser'
    const utterRef  = useRef(null);          // active SpeechSynthesisUtterance

    // Load available voices on mount
    useEffect(() => {
        fetch(`${API}/api/tts/voices`, { headers: authHeaders() })
            .then(r => r.json())
            .then(d => {
                setVoices(d.voices || []);
                setAzureReady(d.azure_configured || false);
            })
            .catch(() => {});
    }, []);

    // Persist preferences
    useEffect(() => { localStorage.setItem('ag_tts_voice', voice); }, [voice]);
    useEffect(() => { localStorage.setItem('ag_tts_speed', String(speed)); }, [speed]);

    // Cleanup blob URLs on unmount
    useEffect(() => {
        return () => {
            Object.values(cacheRef.current).forEach(URL.revokeObjectURL);
            if (audioRef.current) { audioRef.current.pause(); audioRef.current = null; }
            if (typeof window !== 'undefined' && window.speechSynthesis) {
                window.speechSynthesis.cancel();
            }
            abortRef.current?.abort();
        };
    }, []);

    const _cleanForBrowserSpeech = useCallback((text) => {
        let t = String(text || '');
        t = t.replace(/\$\$[\s\S]*?\$\$/g, ' formula. ');
        t = t.replace(/\$[^$\n]{1,100}\$/g, ' formula ');
        t = t.replace(/\\[a-zA-Z]+(?:\{[^}]*\})*/g, ' ');
        t = t.replace(/^#{1,6}\s+/gm, '');
        t = t.replace(/`[^`]*`/g, ' ');
        t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
        t = t.replace(/[>*_#]/g, ' ');
        t = t.replace(/\s{2,}/g, ' ');
        return t.trim();
    }, []);

    const _speakWithBrowser = useCallback((text, pageIdx) => {
        if (typeof window === 'undefined' || !window.speechSynthesis) {
            throw new Error('Browser speech synthesis is unavailable');
        }
        const clean = _cleanForBrowserSpeech(text);
        if (!clean) return;

        modeRef.current = 'browser';
        window.speechSynthesis.cancel();

        const u = new SpeechSynthesisUtterance(clean);
        u.rate = Math.max(0.75, Math.min(2, speed));
        u.onstart = () => { setIsLoading(false); setIsPlaying(true); };
        u.onend = () => { setIsPlaying(false); setActivePageIdx(null); utterRef.current = null; };
        u.onerror = () => { setError('Browser speech playback failed'); setIsPlaying(false); setIsLoading(false); setActivePageIdx(null); utterRef.current = null; };
        utterRef.current = u;
        setActivePageIdx(pageIdx);
        setIsLoading(true);
        window.speechSynthesis.speak(u);
    }, [_cleanForBrowserSpeech, speed]);

    const stop = useCallback(() => {
        abortRef.current?.abort();
        if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = ''; audioRef.current = null; }
        if (typeof window !== 'undefined' && window.speechSynthesis) {
            window.speechSynthesis.cancel();
            utterRef.current = null;
        }
        setIsPlaying(false);
        setIsLoading(false);
        setActivePageIdx(null);
        setError('');
    }, []);

    const pause = useCallback(() => {
        if (modeRef.current === 'browser' && typeof window !== 'undefined' && window.speechSynthesis) {
            if (window.speechSynthesis.speaking && !window.speechSynthesis.paused) {
                window.speechSynthesis.pause();
                setIsPlaying(false);
            }
            return;
        }
        if (audioRef.current) { audioRef.current.pause(); }
        setIsPlaying(false);
    }, []);

    const resume = useCallback(() => {
        if (modeRef.current === 'browser' && typeof window !== 'undefined' && window.speechSynthesis) {
            if (window.speechSynthesis.paused) {
                window.speechSynthesis.resume();
                setIsPlaying(true);
            }
            return;
        }
        if (audioRef.current) {
            audioRef.current.playbackRate = speed;
            audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {});
        }
    }, [speed]);

    const rateToPercent = (s) => {
        // Convert 0.75→"-25%", 1→"0%", 1.25→"+25%", 1.5→"+50%", 2→"+100%"
        const pct = Math.round((s - 1) * 100);
        return `${pct >= 0 ? '+' : ''}${pct}%`;
    };

    const speak = useCallback(async (text, pageIdx) => {
        if (!text?.trim()) return;
        if (!azureReady) {
            try {
                setError('');
                _speakWithBrowser(text, pageIdx);
                return;
            } catch {
                setError('Azure Speech Service not configured — add AZURE_SPEECH_KEY to .env');
                return;
            }
        }

        // If same page is already playing, toggle pause/resume
        if (activePageIdx === pageIdx && audioRef.current) {
            if (isPlaying) { pause(); return; }
            else { resume(); return; }
        }

        stop();
        setActivePageIdx(pageIdx);
        setIsLoading(true);
        setError('');

        abortRef.current = new AbortController();

        try {
            // Check cache first
            const cacheKey = `${pageIdx}_${voice}_${speed}`;
            if (cacheRef.current[cacheKey]) {
                _playBlob(cacheRef.current[cacheKey], pageIdx, speed);
                setIsLoading(false);
                return;
            }

            const res = await fetch(`${API}/api/tts`, {
                method: 'POST',
                headers: { ...authHeaders(), 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, voice, rate: rateToPercent(speed) }),
                signal: abortRef.current.signal,
            });

            if (!res.ok) {
                const j = await res.json().catch(() => ({}));
                const detail = j.detail || `TTS error ${res.status}`;
                // Fallback for Azure auth/config/runtime issues.
                if (res.status >= 500 || res.status === 401 || res.status === 403) {
                    _speakWithBrowser(text, pageIdx);
                    return;
                }
                throw new Error(detail);
            }

            const blob   = await res.blob();
            const blobUrl = URL.createObjectURL(blob);
            cacheRef.current[cacheKey] = blobUrl;
            _playBlob(blobUrl, pageIdx, speed);
        } catch (e) {
            if (e.name === 'AbortError') return;
            try {
                _speakWithBrowser(text, pageIdx);
            } catch {
                setError(e.message || 'TTS failed');
                setIsLoading(false);
                setActivePageIdx(null);
            }
        }
    }, [azureReady, voice, speed, activePageIdx, isPlaying, stop, pause, resume, _speakWithBrowser]);

    const _playBlob = (blobUrl, pageIdx, spd) => {
        modeRef.current = 'audio';
        const audio = new Audio(blobUrl);
        audio.playbackRate = spd;
        audioRef.current   = audio;
        audio.onplay     = () => { setIsPlaying(true);  setIsLoading(false); };
        audio.onpause    = () => setIsPlaying(false);
        audio.onended    = () => { setIsPlaying(false); setActivePageIdx(null); };
        audio.onerror    = () => { setError('Audio playback failed'); setIsPlaying(false); setIsLoading(false); };
        audio.play().catch(() => {});
    };

    const changeSpeed = useCallback((s) => {
        setSpeed(s);
        if (audioRef.current) audioRef.current.playbackRate = s;
    }, []);

    return {
        speak, stop, pause, resume, changeSpeed,
        isPlaying, isLoading, activePageIdx,
        voice, setVoice, speed, changeSpeed,
        voices, azureReady, error, setError,
    };
}
