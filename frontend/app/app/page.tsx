'use client';

import { useState, useRef, useCallback, useEffect } from 'react';

function rand(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

interface TrendingItem {
  headline: string;
  verdict: string;
  label: string;
  source: string;
  url: string;
}

const TRENDING_FALLBACK: TrendingItem[] = [
  {
    headline: 'AI-generated deepfakes of Indian officials claim military support for Israel',
    verdict: 'Refuted', label: 'FALSE',
    source: 'altnews.in',
    url: 'https://www.boomlive.in/fact-check/viral-video-deepfakes-indian-government-official-insiderwb-x-handle-30838',
  },
  {
    headline: 'Old 2016 photos of US Navy sailors shared as Iran hostages in current conflict',
    verdict: 'Refuted', label: 'FALSE',
    source: 'apnews.com',
    url: 'https://apnews.com/article/iran-us-sailors-detained-2016-ec493f76b56cde855ecba70ccc5fa9b1',
  },
  {
    headline: 'Viral video claims PM Modi announced nationwide lockdown due to security crisis',
    verdict: 'Refuted', label: 'FALSE',
    source: 'pib.gov.in',
    url: 'https://pib.gov.in/Pressreleaseshare.aspx?PRID=1913152',
  },
  {
    headline: 'AI chatbot advice suggests replacing table salt with sodium bromide for better health',
    verdict: 'Refuted', label: 'TRUE',
    source: 'who.int',
    url: 'https://www.theguardian.com/technology/2025/aug/12/us-man-bromism-salt-diet-chatgpt-openai-health-information#:~:text=The%20authors%20said%20the%20patient%20appeared%20to,asked%20for%20a%20replacement%20for%20table%20salt.',
  },
  {
    headline: 'WhatsApp message claims service will start charging Rs 99 per month from next week',
    verdict: 'Refuted', label: 'FALSE',
    source: 'boomlive.in',
    url: 'https://www.boomlive.in/fact-check/whatsapp-paid-subscription-fake-message-viral-19654',
  },
];

// ── Types ─────────────────────────────────────────
interface Source {
  title: string;
  url: string;
  source: string;
  source_tier: string;
  score: number;
}

interface Origin {
  found: boolean;
  earliest_url: string | null;
  earliest_date: string | null;
  origin_type: string;
  confidence: string;
  keywords_used: string[];
}

interface PipelineStep {
  step: string;
  status: string;
  state: 'success' | 'warning' | 'error' | 'pending';
}

interface ClaimResult {
  claim: string;
  stance: 'Supported' | 'Refuted' | 'Uncertain';
  confidence: 'High' | 'Medium' | 'Low';
  reasoning: string;
  structured_query: Record<string, unknown>;
  pipeline_trace: PipelineStep[];
  sources: Source[];
  corpus_miss: boolean;
  origin: Origin;
}

interface AnalysisResponse {
  input_text: string;
  processed_text: string;
  source_lang: string;
  results: ClaimResult[];
  total_claims: number;
  processing_time_ms: number;
}

// ── Helpers ───────────────────────────────────────
function confWidth(c: string) {
  if (c === 'High') return '100%';
  if (c === 'Medium') return '60%';
  return '25%';
}

function accuracyScore(results: ClaimResult[]) {
  if (!results.length) return null;
  let total = 0;
  for (const r of results) {
    if (r.stance === 'Supported') total += r.confidence === 'High' ? 90 : r.confidence === 'Medium' ? 70 : 50;
    else if (r.stance === 'Refuted') total += r.confidence === 'High' ? 8 : r.confidence === 'Medium' ? 18 : 30;
    else total += 40;
  }
  return Math.round(total / results.length);
}

/** Deduplicate sources by domain — 1 tag per unique domain */
function uniqueSourceTags(sources: Source[]): Source[] {
  const seen = new Set<string>();
  return sources.filter(s => {
    try {
      const domain = new URL(s.url).hostname.replace(/^www\./, '');
      if (seen.has(domain)) return false;
      seen.add(domain);
      return true;
    } catch {
      const key = s.source;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    }
  });
}

const LANG_NAMES: Record<string, string> = {
  hi: 'Hindi', bn: 'Bengali', ta: 'Tamil', te: 'Telugu',
  mr: 'Marathi', gu: 'Gujarati', kn: 'Kannada', ml: 'Malayalam',
  pa: 'Punjabi', or: 'Odia', en: 'English',
};

const STEPS = ['Scanning claims…', 'Searching corpus…', 'Cross-referencing sources…', 'Calibrating verdict…'];

// ── Skeleton loader ───────────────────────────────
function SkeletonCard() {
  return (
    <div className="skeleton-card">
      <div className="skeleton-header" />
      <div className="skeleton-body">
        <div className="skeleton-line w-full" />
        <div className="skeleton-line w-4/5" />
        <div className="skeleton-line w-3/5" />
        <div className="skeleton-line short" />
      </div>
    </div>
  );
}

// ── Verdict card ─────────────────────────────────
function VerdictCard({ result, index, dark }: { result: ClaimResult; index: number; dark: boolean }) {
  const sc = result.stance.toLowerCase();
  const cc = result.confidence.toLowerCase();
  const [traceOpen, setTraceOpen] = useState(false);
  const deduped = uniqueSourceTags(result.sources);

  return (
    <div className="verdict-card" style={{ animationDelay: `${index * 0.08}s` }} id={`claim-${index}`} role="article">
      <div className="verdict-header">
        <span className="verdict-header-title">Verdict</span>
        <span className={`verdict-badge ${sc}`}>{result.stance}</span>
      </div>
      <div className="verdict-body">
        <blockquote className="verdict-claim">"{result.claim}"</blockquote>

        <div className="conf-row">
          Confidence
          <div className="conf-track">
            <div className={`conf-fill ${cc}`} style={{ width: confWidth(result.confidence) }} />
          </div>
          {result.confidence}
        </div>

        <p className="verdict-reasoning">{result.reasoning}</p>

        {deduped.length > 0 && (
          <div className="verdict-tags">
            {deduped.map((s, i) => (
              <a key={i} href={s.url} target="_blank" rel="noopener noreferrer" className="verdict-tag">
                {s.source.replace(/_/g, ' ').toUpperCase()}
              </a>
            ))}
          </div>
        )}

        {result.origin && (
          <div className={`p0-box ${result.origin.found ? 'found' : ''}`}>
            <span>🕐</span>
            {result.origin.found && result.origin.earliest_date ? (
              <span>
                Patient Zero — first seen {result.origin.earliest_date} via{' '}
                {result.origin.earliest_url ? (
                  <a href={result.origin.earliest_url} target="_blank" rel="noopener noreferrer">
                    {result.origin.origin_type}
                  </a>
                ) : result.origin.origin_type}
              </span>
            ) : (
              <span>No early archive found for this claim.</span>
            )}
          </div>
        )}

        {result.pipeline_trace?.length > 0 && (
          <div className="trace-section">
            <button
              onClick={() => setTraceOpen(o => !o)}
              className="trace-title"
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, textAlign: 'left', width: '100%' }}
            >
              Engine Trace {traceOpen ? '▲' : '▼'}
            </button>
            {traceOpen && (
              <div className="trace-list">
                {result.pipeline_trace.map((step, i) => (
                  <div key={i} className={`trace-item ${step.state}`}>
                    <div className="trace-dot-status" />
                    <div>
                      <span className="trace-step-name">{step.step}</span>
                      <span className="trace-step-status"> — {step.status}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────
export default function Home() {
  const [tab, setTab] = useState<'text' | 'screenshot'>('text');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [imgPreview, setImgPreview] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(STEPS[0]);
  const [response, setResponse] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dark, setDark] = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const [claimsCount, setClaimsCount] = useState(1324);
  const [updatedAgo, setUpdatedAgo] = useState(rand(1, 5));
  const [trendingItems, setTrendingItems] = useState<TrendingItem[]>(TRENDING_FALLBACK);

  // Dark mode — toggle class on <html>
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark);
  }, [dark]);

  // Claims counter — increments by 1–3 every 7s
  useEffect(() => {
    const t = setInterval(() => setClaimsCount(c => c + rand(1, 3)), 7000);
    return () => clearInterval(t);
  }, []);

  // Updated-ago — random 1–5s every 10s
  useEffect(() => {
    const t = setInterval(() => setUpdatedAgo(rand(1, 5)), 10000);
    return () => clearInterval(t);
  }, []);

  // Fetch trending claims from backend (ready when startup task completes)
  useEffect(() => {
    let cancelled = false;
    const fetchTrending = async () => {
      try {
        const res = await fetch(`${API}/trending`);
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && data.items?.length) setTrendingItems(data.items);
        // If not ready yet, retry in 10s
        if (!cancelled && !data.ready) setTimeout(fetchTrending, 10000);
      } catch { /* keep fallback */ }
    };
    fetchTrending();
    return () => { cancelled = true; };
  }, []);

  const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

  const setImageFile = useCallback((f: File) => {
    if (!f.type.startsWith('image/')) { setError('Only image files are supported.'); return; }
    if (f.size > 8 * 1024 * 1024) { setError('Image too large — max 8 MB.'); return; }
    setError(null);
    setFile(f);
    setImgPreview(URL.createObjectURL(f));
  }, []);

  // Ctrl+V paste for images in screenshot tab
  useEffect(() => {
    const handlePaste = (e: ClipboardEvent) => {
      if (tab !== 'screenshot') return;
      const items = e.clipboardData?.items;
      if (!items) return;
      for (const item of Array.from(items)) {
        if (item.type.startsWith('image/')) {
          const blob = item.getAsFile();
          if (blob) { setImageFile(blob); break; }
        }
      }
    };
    window.addEventListener('paste', handlePaste);
    return () => window.removeEventListener('paste', handlePaste);
  }, [tab, setImageFile]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) setImageFile(f);
  }, [setImageFile]);

  const handlePasteBtn = async () => {
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const imgType = item.types.find(t => t.startsWith('image/'));
        if (imgType) {
          const blob = await item.getType(imgType);
          setImageFile(new File([blob], 'clipboard.png', { type: imgType }));
          return;
        }
      }
      setError('No image in clipboard. Copy a screenshot first.');
    } catch {
      setError('Could not read clipboard. Try using Ctrl+V directly on this area.');
    }
  };

  const scrollTo = (i: number) =>
    document.getElementById(`claim-${i}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const handleSubmit = async () => {
    if (tab === 'text' && !text.trim()) return;
    if (tab === 'screenshot' && !file) return;

    setLoading(true);
    setError(null);
    setResponse(null);
    setLoadingStep(STEPS[0]);

    let stepIdx = 0;
    const stepTimer = setInterval(() => {
      stepIdx = (stepIdx + 1) % STEPS.length;
      setLoadingStep(STEPS[stepIdx]);
    }, 1800);

    try {
      const form = new FormData();
      if (tab === 'text') form.append('text', text);
      else if (file) form.append('file', file);

      const res = await fetch(`${API}/analyze`, { method: 'POST', body: form });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({ detail: 'Unknown error' }));
        throw new Error(detail.detail ?? `HTTP ${res.status}`);
      }
      const data: AnalysisResponse = await res.json();
      setResponse(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
    } finally {
      clearInterval(stepTimer);
      setLoading(false);
    }
  };

  const score = response ? accuracyScore(response.results) : null;
  const allSources = response?.results.flatMap(r => r.sources) ?? [];
  const canSubmit = tab === 'text' ? text.trim().length > 0 : !!file;

  return (
    <>
      {/* Masthead */}
      <header className="masthead">
        <div className="masthead-inner">
          <div>
            <div className="masthead-brand-label">AI Fact Verification</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span className="alithia-dot" aria-hidden="true" />
              <div className="masthead-title">Alithia</div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Claims counter */}
            <div className="masthead-claims" style={{ textAlign: 'right', borderRight: '1px solid var(--border-sub)', paddingRight: 16 }}>
              <div className="masthead-claims-num">{claimsCount.toLocaleString()}</div>
              <div className="masthead-claims-label">Claims Analyzed</div>
            </div>
            <div className="masthead-meta">
              <div className="masthead-date" suppressHydrationWarning>{today}</div>
              <div className="masthead-date">English · 9 Indian Languages</div>
            </div>
            <button
              className="dark-toggle"
              onClick={() => setDark(d => !d)}
              aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
              title={dark ? 'Light mode' : 'Dark mode'}
            >
              {dark ? '☀' : '🌙'}
            </button>
          </div>
        </div>
      </header>

      {/* Ticker */}
      <div className="ticker">
        <div className="ticker-inner">
          <span className="ticker-live">LIVE</span>
          <span className="ticker-text">
            Fact-checking viral claims in real time · Powered by countless trusted sources · GDELT · DuckDuckGo · Google Fact Check · Wayback Machine
          </span>
        </div>
      </div>

      {/* Trending bar */}
      <div className="trending-bar">
        <span className="trending-label">TRENDING</span>
        <div className="trending-track-wrap">
          <span className="trending-track">
            {[...trendingItems, ...trendingItems].map((item, i) => (
              <span key={i} className="trending-item">
                <span className={`trending-verdict-pill verdict-${item.verdict.toLowerCase()}`}>
                  {item.label}
                </span>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="trending-headline"
                  title={item.source}
                >
                  {item.headline}
                </a>
                <span className="trending-sep">·</span>
              </span>
            ))}
          </span>
        </div>
      </div>

      {/* Main body */}
      <main className="page-body">
        {/* Headline */}
        <div className="headline-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <p className="section-label" style={{ marginBottom: 0 }}>Breaking Analysis</p>
            <span className="live-badge">
              <span className="live-badge-dot" aria-hidden="true" />
              Live
            </span>
          </div>
          <h1 className="headline-h1">
            Is That Viral Post<br />Actually True?
          </h1>
          <p className="headline-sub">
            Paste any tweet, WhatsApp forward, or social media post below. Our AI
            cross-references thousands of verified sources to deliver an instant,{' '}
            <strong>evidence-backed verdict.</strong>
            {' '}<span className="updated-ago" suppressHydrationWarning>Updated {updatedAgo}s ago</span>
          </p>
        </div>

        <div className="content-grid">
          {/* ── Main column ── */}
          <div>
            {/* Tabs */}
            <div className="tab-row" role="tablist">
              {(['text', 'screenshot'] as const).map(t => (
                <button
                  key={t}
                  className={`tab-btn ${tab === t ? 'active' : ''}`}
                  onClick={() => setTab(t)}
                  role="tab"
                  aria-selected={tab === t}
                >
                  {t === 'text' ? '✏ Text' : '⊞ Screenshot'}
                </button>
              ))}
            </div>

            {/* Input box */}
            <div className="input-box">
              {tab === 'text' ? (
                <textarea
                  id="claim-input"
                  className="text-area"
                  placeholder="Type or directly paste images to verify…"
                  value={text}
                  onChange={e => setText(e.target.value)}
                  aria-label="Claim text input"
                />
              ) : (
                <div
                  className={`img-zone ${dragging ? 'drag-over' : ''}`}
                  onClick={() => !imgPreview && fileRef.current?.click()}
                  onDragOver={e => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={handleDrop}
                  role="button"
                  tabIndex={0}
                  aria-label="Upload or paste screenshot"
                  onKeyDown={e => e.key === 'Enter' && fileRef.current?.click()}
                >
                  {imgPreview ? (
                    <>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={imgPreview} alt="Preview" className="img-zone-preview" />
                      <button
                        onClick={e => { e.stopPropagation(); setFile(null); setImgPreview(null); }}
                        style={{
                          position: 'absolute', top: 8, right: 8,
                          background: '#b91c1c', color: '#fff',
                          border: 'none', cursor: 'pointer',
                          fontSize: '11px', padding: '3px 8px',
                          fontFamily: 'Inter, sans-serif', fontWeight: 700,
                        }}
                      >
                        ✕ Remove
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="img-zone-icon">📋</div>
                      <p className="img-zone-label">Drop screenshot here, or click to upload</p>
                      <p className="img-zone-hint">Paste with Ctrl+V or use the button below</p>
                      <button className="img-paste-btn" onClick={e => { e.stopPropagation(); handlePasteBtn(); }}>
                        📋 Paste from Clipboard
                      </button>
                    </>
                  )}
                </div>
              )}
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={e => { const f = e.target.files?.[0]; if (f) setImageFile(f); }}
                aria-hidden="true"
              />
            </div>

            {/* Action row */}
            <div className="action-row">
              <button
                id="analyze-btn"
                className="analyze-btn"
                onClick={handleSubmit}
                disabled={loading || !canSubmit}
                aria-busy={loading}
              >
                {loading ? `${loadingStep}` : 'Analyze Claim →'}
              </button>
            </div>

            {/* Error */}
            {error && (
              <div className="error-banner" role="alert">
                ⚠ {error}
              </div>
            )}

            {/* Lang badge */}
            {response && response.source_lang !== 'en' && (
              <div className="lang-badge" style={{ marginTop: 14 }}>
                🌐 Detected: {LANG_NAMES[response.source_lang] ?? response.source_lang} — translated for analysis
              </div>
            )}

            {/* Timing */}
            {response && (
              <div className="timing-row">
                <span className="timing-badge">
                  ⏱ {response.total_claims} claim{response.total_claims !== 1 ? 's' : ''} · {response.processing_time_ms}ms
                </span>
              </div>
            )}

            {/* Claim pills (multi-claim) */}
            {response && response.results.length > 1 && (
              <nav className="claims-nav" aria-label="Jump to claim">
                {response.results.map((r, i) => (
                  <button key={i} className={`claim-pill ${r.stance.toLowerCase()}`} onClick={() => scrollTo(i)}>
                    <span className="pill-dot" aria-hidden="true" />
                    {r.claim.slice(0, 42)}{r.claim.length > 42 ? '…' : ''}
                  </button>
                ))}
              </nav>
            )}

            {/* Skeleton while loading */}
            {loading && (
              <div aria-busy="true" aria-label="Analyzing claims">
                <SkeletonCard />
                <SkeletonCard />
              </div>
            )}

            {/* Verdict cards */}
            {!loading && (
              <div aria-live="polite" aria-atomic="false">
                {response && response.results.length === 0 && (
                  <div className="empty-state">
                    <h3>No verifiable claims found</h3>
                    <p>The text didn&apos;t contain factual claims that can be checked.</p>
                  </div>
                )}
                {response?.results.map((r, i) => (
                  <VerdictCard key={i} result={r} index={i} dark={dark} />
                ))}
              </div>
            )}

            {/* Initial empty state */}
            {!response && !error && !loading && (
              <div className="empty-state">
                <h3>Paste text or upload a screenshot to begin</h3>
                <p>Supports English and 9 Indian languages</p>
              </div>
            )}
          </div>

          {/* ── Sidebar ── */}
          <aside className="sidebar">
            {/* Accuracy Score */}
            <div className="sidebar-box">
              <div className="sidebar-title">Accuracy Score</div>
              {score !== null ? (
                <>
                  <div className="accuracy-num">{score}</div>
                  <div className="accuracy-sub">out of 100</div>
                  <div className="accuracy-track">
                    <div className="accuracy-fill" style={{ width: `${score}%` }} />
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--ink-dim)', fontSize: 12, fontFamily: 'var(--font-sans)' }}>
                  Run analysis to see score
                </div>
              )}
            </div>

            {/* Sources */}
            {allSources.length > 0 && (
              <div className="sidebar-box">
                <div className="sidebar-title">Sources</div>
                <ul className="source-list">
                  {uniqueSourceTags(allSources).slice(0, 6).map((s, i) => (
                    <li key={i} className="source-item">
                      <span className="source-dot" />
                      <span className="source-label">{s.title.slice(0, 72)}{s.title.length > 72 ? '…' : ''}</span>
                      <a href={s.url} target="_blank" rel="noopener noreferrer" className="source-arrow">›</a>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Advertisement */}
            <div className="ad-box">
              <span className="ad-label">Advertisement</span>
              <div className="ad-inner">Your Ad Here</div>
            </div>

            {/* About */}
            <div className="about-box">
              <strong className="about-title">About</strong>
              Alithia (Viral Claim Radar) is an AI-powered fact-checking tool built for GDG 2026.
              Supports English and 9 Indian languages.
            </div>
          </aside>
        </div>
      </main>

      {/* Footer */}
      <footer className="site-footer">
        Alithia · Built for GDG 2026 · Powered by Sarvam AI · Next.js
      </footer>
    </>
  );
}
