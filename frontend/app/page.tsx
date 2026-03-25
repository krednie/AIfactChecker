'use client';

import { useState, useRef, useCallback } from 'react';

const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

// ── Types ─────────────────────────────────────────────────
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
  structured_query: any;
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

// ── SVG Icons ─────────────────────────────────────────────
function IconRadar() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/>
      <path d="M12 12m-5 0a5 5 0 1 0 10 0a5 5 0 1 0 -10 0"/>
      <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/>
      <path d="M15 12l-3 -3"/>
    </svg>
  );
}

function IconPencil() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 20h4L18.5 9.5a2.121 2.121 0 0 0-4-4L4 16v4z"/>
      <line x1="13.5" y1="6.5" x2="17.5" y2="10.5"/>
    </svg>
  );
}

function IconImage() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <circle cx="8.5" cy="8.5" r="1.5"/>
      <polyline points="21 15 16 10 5 21"/>
    </svg>
  );
}

function IconCamera() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </svg>
  );
}

function IconSearch() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="11" cy="11" r="8"/>
      <path d="M21 21l-4.35-4.35"/>
    </svg>
  );
}

function IconAlertTriangle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}

function IconGlobe() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10"/>
      <line x1="2" y1="12" x2="22" y2="12"/>
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
    </svg>
  );
}

function IconHelpCircle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10"/>
      <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/>
      <line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}

function IconClock() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="10"/>
      <polyline points="12 6 12 12 16 14"/>
    </svg>
  );
}

function IconCheckCircle() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
      <polyline points="22 4 12 14.01 9 11.01"/>
    </svg>
  );
}

function IconActivity() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function IconDatabase() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <ellipse cx="12" cy="5" rx="9" ry="3"/>
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
    </svg>
  );
}

function IconCircle({ cls }: { cls: string }) {
  const fill = cls === 'supported' ? '#22c55e' : cls === 'refuted' ? '#f87171' : '#fbbf24';
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
      <circle cx="4" cy="4" r="4" fill={fill} />
    </svg>
  );
}

function IconTimer() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9"/>
      <polyline points="12 7 12 12 15 15"/>
      <path d="M9.5 3.5h5"/>
    </svg>
  );
}

// ── Helpers ───────────────────────────────────────────────
const TIER_CLASS: Record<string, string> = {
  govt: 'tier-dot govt',
  verified: 'tier-dot verified',
  portal: 'tier-dot portal',
};

function confidenceWidth(conf: string) {
  if (conf === 'High') return '100%';
  if (conf === 'Medium') return '60%';
  return '25%';
}

const STEPS = ['Scanning claims…', 'Searching corpus…', 'Classifying stance…', 'Tracing origin…'];

// ── Sub-components ────────────────────────────────────────

function RadarOverlay({ step }: { step: string }) {
  const stepIdx = STEPS.indexOf(step);
  return (
    <div className="radar-overlay" role="status" aria-live="polite" aria-label={step}>
      <div className="radar-ring">
        <div className="radar-sweep" />
        <div className="radar-center" />
        <div className="radar-dot radar-dot-1" />
        <div className="radar-dot radar-dot-2" />
        <div className="radar-dot radar-dot-3" />
      </div>
      <p className="radar-label">{step}</p>
      <div className="radar-steps" aria-hidden="true">
        {STEPS.map((_, i) => (
          <div key={i} className={`radar-step-dot ${i <= stepIdx ? 'active' : ''}`} />
        ))}
      </div>
    </div>
  );
}

function SkeletonCard({ index }: { index: number }) {
  return (
    <div
      className="skeleton-card"
      style={{ animationDelay: `${index * 0.12}s` }}
      aria-hidden="true"
    >
      <div className="skeleton-header">
        <div className="skeleton-line skeleton-badge" />
        <div className="skeleton-line skeleton-title" />
      </div>
      <div className="skeleton-body">
        <div className="skeleton-line skeleton-bar" />
        <div className="skeleton-line skeleton-text" />
        <div className="skeleton-line skeleton-text short" />
      </div>
      <div className="skeleton-footer-row">
        <div className="skeleton-line skeleton-chip" />
        <div className="skeleton-line skeleton-chip" />
        <div className="skeleton-line skeleton-chip" />
      </div>
    </div>
  );
}

function ClaimPill({ result, onClick }: { result: ClaimResult; onClick: () => void }) {
  const cls = result.stance.toLowerCase();
  return (
    <button
      className={`claim-pill ${cls}`}
      onClick={onClick}
      title={result.claim}
      role="button"
      tabIndex={0}
    >
      <span className="pill-dot" aria-hidden="true" />
      {result.claim.slice(0, 42)}{result.claim.length > 42 ? '…' : ''}
    </button>
  );
}

function Patient0Card({ origin }: { origin: Origin }) {
  if (!origin.found) {
    return (
      <div className="patient0-card">
        <div className="patient0-icon" aria-hidden="true"><IconSearch /></div>
        <div>
          <span className="patient0-label">Origin Unknown</span>
          No earliest archive found for this claim
        </div>
      </div>
    );
  }
  return (
    <div className="patient0-card found">
      <div className="patient0-icon" aria-hidden="true"><IconClock /></div>
      <div>
        <span className="patient0-label">Patient 0 — {origin.origin_type}</span>
        First archived: {origin.earliest_date}&nbsp;
        {origin.earliest_url && (
          <a
            href={origin.earliest_url}
            target="_blank"
            rel="noopener noreferrer"
            className="patient0-link"
          >
            View archive ↗
          </a>
        )}
      </div>
    </div>
  );
}

function StructuredQueryView({ query }: { query: any }) {
  if (!query || Object.keys(query).length === 0) return null;
  const struct = query.structure || {};
  
  return (
    <div className="bento-item">
      <div className="bento-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <IconDatabase /> Structured Breakdown
      </div>
      <div className="query-chips">
        {query.intent && (
          <div className="query-chip">
            <span>Intent</span> {query.intent}
          </div>
        )}
        {struct.subject && (
          <div className="query-chip">
            <span>Subject</span> {struct.subject}
          </div>
        )}
        {struct.predicate && (
          <div className="query-chip">
            <span>Predicate</span> {struct.predicate}
          </div>
        )}
        {struct.object && (
          <div className="query-chip">
            <span>Object</span> {struct.object}
          </div>
        )}
        {query.keywords?.map((kw: string, i: number) => (
          <div key={i} className="query-chip">
            <span>Keyword</span> {kw}
          </div>
        ))}
      </div>
    </div>
  );
}

function PipelineTraceView({ trace }: { trace: PipelineStep[] }) {
  if (!trace || trace.length === 0) return null;
  return (
    <div className="bento-item">
      <div className="bento-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <IconActivity /> Engine Trace
      </div>
      <div className="trace-timeline">
        {trace.map((step, i) => (
          <div key={i} className={`trace-step ${step.state}`}>
            <div className="trace-dot" aria-hidden="true" />
            <div className="trace-step-name">{step.step}</div>
            <div className="trace-step-status">{step.status}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceCard({ result, index }: { result: ClaimResult; index: number }) {
  const cls = result.stance.toLowerCase();
  const confCls = result.confidence.toLowerCase();
  return (
    <div
      className="evidence-card"
      id={`claim-${index}`}
      style={{ animationDelay: `${index * 0.07}s` }}
      role="article"
      aria-label={`Claim: ${result.claim}`}
    >
      <div className="card-header">
        <span className={`stance-badge ${cls}`}>
          {result.stance}
        </span>
        <p className="claim-text">{result.claim}</p>
      </div>

      <div className="bento-grid">
        <div className="bento-item full-width">
          <div className="confidence-row">
            <span className="confidence-label">Confidence</span>
            <div className="confidence-bar-track" role="progressbar" aria-valuenow={confCls === 'high' ? 100 : confCls === 'medium' ? 60 : 25} aria-valuemin={0} aria-valuemax={100}>
              <div
                className={`confidence-bar-fill ${confCls}`}
                style={{ width: confidenceWidth(result.confidence) }}
              />
            </div>
            <span className={`confidence-value ${confCls}`}>{result.confidence}</span>
          </div>

          <p className="reasoning">{result.reasoning}</p>

          <Patient0Card origin={result.origin} />
        </div>

        <StructuredQueryView query={result.structured_query} />
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <PipelineTraceView trace={result.pipeline_trace} />
          
          {result.sources.length > 0 && (
            <div className="bento-item">
               <div className="bento-title">Evidence Sources</div>
               <div className="source-stack">
                 {result.sources.map((src, i) => (
                   <a
                     key={i}
                     href={src.url}
                     target="_blank"
                     rel="noopener noreferrer"
                     className="source-card"
                   >
                     <div className="source-card-header">
                       <span className={TIER_CLASS[src.source_tier] ?? 'tier-dot portal'} aria-hidden="true" />
                       <span className="source-card-domain">{src.source.toUpperCase()}</span>
                     </div>
                     <span className="source-card-title">{src.title}</span>
                   </a>
                 ))}
               </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────

export default function Home() {
  const [tab, setTab] = useState<'text' | 'image'>('text');
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(STEPS[0]);
  const [response, setResponse] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const MAX_IMAGE_MB = 8;

  const validateAndSetFile = useCallback((f: File | null) => {
    if (!f) return;
    if (!f.type.startsWith('image/')) { setError('Only image files are supported.'); return; }
    if (f.size > MAX_IMAGE_MB * 1024 * 1024) { setError(`Image too large — max ${MAX_IMAGE_MB} MB.`); return; }
    setError(null);
    setFile(f);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    validateAndSetFile(e.dataTransfer.files[0] ?? null);
  }, [validateAndSetFile]);

  const scrollTo = (index: number) => {
    document.getElementById(`claim-${index}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleSubmit = async () => {
    if (tab === 'text' && !text.trim()) return;
    if (tab === 'image' && !file) return;

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
      if (tab === 'text') {
        form.append('text', text);
      } else if (file) {
        form.append('file', file);
      }

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

  const LANG_NAMES: Record<string, string> = {
    hi: 'Hindi', bn: 'Bengali', ta: 'Tamil', te: 'Telugu',
    mr: 'Marathi', gu: 'Gujarati', kn: 'Kannada', ml: 'Malayalam',
    pa: 'Punjabi', or: 'Odia', en: 'English',
  };

  return (
    <>
      {loading && <RadarOverlay step={loadingStep} />}

      <div className="container">
        {/* Header */}
        <header className="header">
          <div className="logo-wrap">
            <div className="logo-icon" aria-hidden="true">
              <IconRadar />
            </div>
          </div>
          <div className="header-text">
            <h1>Viral Claim Radar</h1>
            <p>AI-powered fact-checking for social media posts</p>
          </div>
        </header>

        {/* Input Card */}
        <div className="input-card">
          <div className="tab-row" role="tablist" aria-label="Input type">
            <button
              id="tab-text"
              className={`tab-btn ${tab === 'text' ? 'active' : ''}`}
              onClick={() => setTab('text')}
              role="tab"
              aria-selected={tab === 'text'}
            >
              <IconPencil /> Text
            </button>
            <button
              id="tab-image"
              className={`tab-btn ${tab === 'image' ? 'active' : ''}`}
              onClick={() => setTab('image')}
              role="tab"
              aria-selected={tab === 'image'}
            >
              <IconImage /> Screenshot
            </button>
          </div>

          {tab === 'text' ? (
            <textarea
              id="claim-input"
              className="text-area"
              placeholder="Paste a tweet, WhatsApp forward, or any social post…"
              value={text}
              onChange={e => setText(e.target.value)}
              aria-label="Claim text input"
            />
          ) : (
            <>
              <div
                className={`drop-zone ${dragging ? 'drag-over' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                role="button"
                tabIndex={0}
                aria-label="Upload screenshot — click or drag and drop"
                onKeyDown={e => e.key === 'Enter' && fileRef.current?.click()}
              >
                <div className="drop-icon" aria-hidden="true">
                  <IconCamera />
                </div>
                {file ? (
                  <p className="drop-success">
                    <IconCheckCircle />
                    {file.name}
                  </p>
                ) : (
                  <p>Drop a screenshot here, or click to upload</p>
                )}
              </div>
              <input
                ref={fileRef}
                type="file"
                accept="image/*"
                style={{ display: 'none' }}
                onChange={e => validateAndSetFile(e.target.files?.[0] ?? null)}
                aria-hidden="true"
              />
            </>
          )}

          <div className="submit-row">
            <button
              id="analyze-btn"
              className="analyze-btn"
              onClick={handleSubmit}
              disabled={loading || (tab === 'text' ? !text.trim() : !file)}
              aria-busy={loading}
            >
              <IconSearch />
              Analyze Claims
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="error-banner" role="alert">
            <IconAlertTriangle />
            {error}
          </div>
        )}

        {/* Results */}
        <div aria-live="polite" aria-atomic="false">
          {response && (
            <div>
              {/* Language badge */}
              {response.source_lang !== 'en' && (
                <div className="lang-badge">
                  <IconGlobe />
                  Detected: {LANG_NAMES[response.source_lang] ?? response.source_lang} — translated for analysis
                </div>
              )}

              {/* Claim pills */}
              {response.results.length > 0 && (
                <nav className="claims-nav" aria-label="Jump to claim">
                  {response.results.map((r, i) => (
                    <ClaimPill key={i} result={r} onClick={() => scrollTo(i)} />
                  ))}
                </nav>
              )}

              {/* Timing */}
              <div className="timing-row">
                <span className="timing-badge">
                  <IconTimer />
                  {response.total_claims} claim{response.total_claims !== 1 ? 's' : ''} · {response.processing_time_ms}ms
                </span>
              </div>

              {/* Evidence cards */}
              {response.results.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-state-icon" aria-hidden="true"><IconHelpCircle /></div>
                  <h3>No verifiable claims found</h3>
                  <p>The text didn&apos;t contain factual claims that can be checked.</p>
                </div>
              ) : (
                response.results.map((r, i) => (
                  <EvidenceCard key={i} result={r} index={i} />
                ))
              )}
            </div>
          )}
        </div>

        {/* Skeleton loaders while loading */}
        {loading && (
          <div className="skeleton-stack" aria-label="Loading results">
            <SkeletonCard index={0} />
            <SkeletonCard index={1} />
            <SkeletonCard index={2} />
          </div>
        )}

        {/* Initial empty state */}
        {!response && !error && !loading && (
          <div className="empty-state">
            <div className="empty-state-icon" aria-hidden="true"><IconRadar /></div>
            <h3>Paste text or upload a screenshot to begin</h3>
            <p>Supports English and 9 Indian languages</p>
          </div>
        )}

        {/* Footer */}
        <footer className="site-footer">
          <div className="footer-stack">
            <span className="footer-badge">Groq</span>
            <span className="footer-badge">FAISS</span>
            <span className="footer-badge">GDELT</span>
            <span className="footer-badge">DuckDuckGo</span>
            <span className="footer-badge">Sarvam AI</span>
            <span className="footer-badge">Next.js</span>
          </div>
          <p className="footer-text">Viral Claim Radar · Built for GDG 2026</p>
        </footer>
      </div>
    </>
  );
}
