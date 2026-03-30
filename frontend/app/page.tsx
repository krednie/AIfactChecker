'use client';

import Link from 'next/link';

export default function LandingPage() {
  return (
    <div className="lp-root">

      {/* Background Orbs */}
      <div className="lp-orbs">
        <div className="lp-orb lp-orb-1"></div>
        <div className="lp-orb lp-orb-2"></div>
        <div className="lp-orb lp-orb-3"></div>
      </div>

      {/* Navigation */}
      <nav className="lp-nav">
        <div className="lp-nav-brand">
          <div className="lp-nav-dot"></div>
          <span className="lp-nav-name">Alithia</span>
        </div>
        <Link href="/app" className="lp-nav-cta">
          Launch App
        </Link>
      </nav>

      {/* Hero Section */}
      <section className="lp-hero">
        <div className="lp-hero-badge">
          <div className="lp-hero-badge-dot"></div>
          Alithia Intelligence v1.0 Live
        </div>

        <h1 className="lp-hero-title">
          Truth at the speed of <span className="lp-hero-title-accent">thought.</span>
        </h1>

        <p className="lp-hero-sub">
          The ultimate verification engine for the digital age. Instantly cross-reference claims against thousands of trusted sources, trace origin nodes, and expose manipulation with surgical precision.
        </p>

        <div className="lp-hero-cta-group">
          <Link href="/app" className="lp-cta-primary">
            Start Verifying Now
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </Link>
          <a href="#how" className="lp-cta-secondary">
            See how it works
          </a>
        </div>

        {/* Hero Mockup */}
        <div className="lp-hero-mockup">
          <div className="lp-mockup-toolbar">
            <div className="lp-mockup-dot"></div>
            <div className="lp-mockup-dot"></div>
            <div className="lp-mockup-dot"></div>
            <div className="lp-mockup-url">alithia.ai/verify</div>
          </div>
          <div className="lp-mockup-body">
            <div className="lp-mockup-field">
              "The new AI regulation bill automatically bans all open-source models over 10B parameters and imposes a $1M fine on developers..."
            </div>
            <div className="lp-mockup-verdict">
              <span className="lp-mockup-verdict-badge">Debunked</span>
              <div className="lp-mockup-verdict-text">
                <strong>False claim detected.</strong> Cross-referenced with EU AI Act and recent legislative texts. The bill imposes restrictions on high-risk use cases, not parameter sizes, and open-source models are explicitly granted safe harbor exemptions.
                <div style={{ marginTop: '12px' }} className="lp-mockup-sources">
                  <span className="lp-mockup-source-chip">europa.eu/ai-act</span>
                  <span className="lp-mockup-source-chip">reuters.com/tech</span>
                  <span className="lp-mockup-source-chip">eff.org</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <div className="lp-divider"><hr className="lp-divider-line" /></div>

      {/* Stats Section */}
      <section className="lp-stats">
        <div>
          <div className="lp-stat-num">5K+</div>
          <div className="lp-stat-label">Queries Processed</div>
        </div>
        <div>
          <div className="lp-stat-num">0.8s</div>
          <div className="lp-stat-label">Avg Verification Time</div>
        </div>
        <div>
          <div className="lp-stat-num">10M+</div>
          <div className="lp-stat-label">Indexed Documents</div>
        </div>
      </section>

      {/* Features Section */}
      <section className="lp-features">
        <div className="lp-section-eyebrow">Engine Capability</div>
        <h2 className="lp-section-title">Built for the information war.</h2>

        <div className="lp-features-grid">
          <div className="lp-feature-card">
            <div className="lp-feature-icon">🧠</div>
            <h3 className="lp-feature-title">Neural Knowledge Graph</h3>
            <p className="lp-feature-desc">Utilizes advanced RAG to instantly cross-reference claims against a continuously updated vector database of verified multi-lingual sources and primary documents.</p>
          </div>

          <div className="lp-feature-card">
            <div className="lp-feature-icon">👁️</div>
            <h3 className="lp-feature-title">Deep Media Inspection</h3>
            <p className="lp-feature-desc">Goes beyond text. Analyzes images and screenshots using embedded OCR computer vision models to extract and verify embedded claims instantly.</p>
          </div>

          <div className="lp-feature-card">
            <div className="lp-feature-icon">⚡</div>
            <h3 className="lp-feature-title">Patient Zero Tracing</h3>
            <p className="lp-feature-desc">Employs linguistic forensics and reverse-chronological search to map the propagation of a claim and identify its earliest known digital footprint.</p>
          </div>

          <div className="lp-feature-card">
            <div className="lp-feature-icon">🛡️</div>
            <h3 className="lp-feature-title">Contextual Immunity</h3>
            <p className="lp-feature-desc">Doesn't just output True/False. Generates comprehensive, nuanced context explaining why a claim is misleading, missing context, or factually accurate.</p>
          </div>
        </div>
      </section>

      {/* How it works Section */}
      <section id="how" className="lp-how">
        <div className="lp-section-eyebrow">Protocol</div>
        <h2 className="lp-section-title">Surgical verification.</h2>

        <div className="lp-steps">
          <div className="lp-step">
            <div className="lp-step-num">1</div>
            <h3 className="lp-step-title">Ingest</h3>
            <p className="lp-step-desc">Paste a URL, drop a screenshot, or type a claim. The engine normalizes the input across languages.</p>
          </div>
          <div className="lp-step">
            <div className="lp-step-num">2</div>
            <h3 className="lp-step-title">Retrieve</h3>
            <p className="lp-step-desc">Parallel agents query live news APIs, fact-check databases, and our proprietary vector index.</p>
          </div>
          <div className="lp-step">
            <div className="lp-step-num">3</div>
            <h3 className="lp-step-title">Synthesize</h3>
            <p className="lp-step-desc">A specialized LLM analyzes evidence coherence, formulates a verdict, and outputs cited reality.</p>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="lp-final-cta">
        <h2 className="lp-final-cta-title">Upgrade your reality.</h2>
        <p className="lp-final-cta-sub">
          Stop guessing. Start knowing. Join the researchers, journalists, and truth-seekers relying on Alithia's neural verification engine.
        </p>
        <Link href="/app" className="lp-cta-primary">
          Launch Alithia App
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </Link>
      </section>

      {/* Footer */}
      <footer className="lp-footer">
        <Link href="/" className="lp-footer-brand">
          <div className="lp-nav-dot" style={{ width: 8, height: 8 }}></div>
          <span className="lp-footer-name">Alithia</span>
        </Link>
        <div className="lp-footer-copy">© 2026 Alithia Global. All systems nominal.</div>
      </footer>

    </div>
  );
}
