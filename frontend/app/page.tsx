'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ShaderAnimation } from '@/components/ui/shader-lines';
import { LiquidButton } from '@/components/ui/liquid-glass-button';

export default function LandingPage() {
  const router = useRouter();

  return (
    <div className="lp-root">

      {/* Background Shader */}
      <div style={{ position: 'fixed', inset: 0, zIndex: 0, pointerEvents: 'none' }}>
        <ShaderAnimation />
      </div>

      {/* Navigation */}
      <nav className="lp-nav">
        <div className="lp-nav-brand">
          <div className="lp-nav-dot"></div>
          <span className="lp-nav-name">Alithia</span>
        </div>
        <LiquidButton size="default" className="text-white" onClick={() => router.push('/app')}>
          Launch App
        </LiquidButton>
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

        <div className="lp-hero-cta-group" style={{ gap: '20px' }}>
          <LiquidButton size="lg" className="text-white" onClick={() => router.push('/app')}>
            Start Verifying Now
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M12 5l7 7-7 7" />
            </svg>
          </LiquidButton>
          <LiquidButton size="lg" className="text-gray-300" onClick={() => {
            document.getElementById('how')?.scrollIntoView({ behavior: 'smooth' });
          }}>
            See how it works
          </LiquidButton>
        </div>

        {/* Hero Mockup */}
        <div className="lp-hero-mockup" data-glow>
          <div className="lp-hero-mockup-inner">
            <div className="lp-mockup-toolbar">
              <div className="lp-mockup-dot"></div>
              <div className="lp-mockup-dot"></div>
              <div className="lp-mockup-dot"></div>
              <div className="lp-mockup-url">alithia.ai/verify</div>
            </div>
            <div className="lp-mockup-body">
              <div className="lp-mockup-field">
                &quot;The new AI regulation bill automatically bans all open-source models over 10B parameters and imposes a $1M fine on developers...&quot;
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
          {/* Feature 1 */}
          <div className="lp-feature-card" data-glow>
            <div className="lp-feature-icon">⚡</div>
            <h3 className="lp-feature-title">Real-Time Verification</h3>
            <p className="lp-feature-desc">
              Checks claims against millions of verified documents within milliseconds.
            </p>
          </div>

          {/* Feature 2 */}
          <div className="lp-feature-card" data-glow>
            <div className="lp-feature-icon">🔍</div>
            <h3 className="lp-feature-title">Source Origin Tracing</h3>
            <p className="lp-feature-desc">
              Identifies “Patient 0” of a claim to uncover coordinated networks.
            </p>
          </div>

          {/* Feature 3 */}
          <div className="lp-feature-card" data-glow>
            <div className="lp-feature-icon">🌐</div>
            <h3 className="lp-feature-title">Cross-Lingual Matching</h3>
            <p className="lp-feature-desc">
              Detects misinformation translated across 9 major local dialects.
            </p>
          </div>

          {/* Feature 4 */}
          <div className="lp-feature-card" data-glow>
            <div className="lp-feature-icon">📊</div>
            <h3 className="lp-feature-title">Entity Trust Scoring</h3>
            <p className="lp-feature-desc">
              Evaluates the reliability of authors based on historically verified data.
            </p>
          </div>
        </div>
      </section>

      {/* How it works Section */}
      <section id="how" className="lp-how">
        <div className="lp-section-eyebrow">Protocol</div>
        <h2 className="lp-section-title">Surgical verification.</h2>

        <div className="lp-steps">
          <div className="lp-step" data-glow>
            <div className="lp-step-num">1</div>
            <div className="lp-step-title">Ingestion & Extraction</div>
            <div className="lp-step-desc">Text is scanned to extract core empirical claims using our Llama-3 extraction pipeline.</div>
          </div>
          <div className="lp-step" data-glow>
            <div className="lp-step-num">2</div>
            <div className="lp-step-title">RAG Cross-Reference</div>
            <div className="lp-step-desc">The engine performs dense retrieval against trusted indices and DuckDuckGo news streams.</div>
          </div>
          <div className="lp-step" data-glow>
            <div className="lp-step-num">3</div>
            <div className="lp-step-title">Verdict Synthesis</div>
            <div className="lp-step-desc">An aggregate score is formulated, tracing origin nodes and generating a report.</div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="lp-final-cta">
        <h2 className="lp-final-cta-title">Upgrade your reality.</h2>
        <p className="lp-final-cta-sub">
          Stop guessing. Start knowing. Join the researchers, journalists, and truth-seekers relying on Alithia&apos;s neural verification engine.
        </p>
        <LiquidButton size="lg" className="text-white" onClick={() => router.push('/app')}>
          Launch Alithia App
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        </LiquidButton>
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
