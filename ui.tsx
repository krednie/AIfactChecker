import { useState, useEffect, useRef } from "react";
import { Sun, Moon } from "lucide-react";

const livePulseStyle = `
  @keyframes live-dot-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.35; transform: scale(0.75); }
  }
  .live-dot-only {
    animation: live-dot-pulse 1.2s ease-in-out infinite;
  }
  @keyframes alithia-dot-pulse {
    0%, 100% { opacity: 1; transform: scale(1); box-shadow: 0 0 0 0 rgba(185,28,28,0.5); }
    50%       { opacity: 0.7; transform: scale(0.8); box-shadow: 0 0 0 4px rgba(185,28,28,0); }
  }
  .alithia-dot {
    animation: alithia-dot-pulse 1.8s ease-in-out infinite;
  }
  @keyframes ticker-scroll {
    0%   { transform: translateX(0); }
    100% { transform: translateX(-50%); }
  }
  .ticker-track {
    animation: ticker-scroll 32s linear infinite;
    white-space: nowrap;
    display: inline-block;
  }
  @keyframes live-box-pulse {
    0%, 100% { opacity: 1; }
    50%       { opacity: 0.6; }
  }
  .live-box {
    animation: live-box-pulse 2s ease-in-out infinite;
  }
`;

const SOURCES = [
  {
    title: "WHO: No evidence of link between 5G networks and COVID-19",
    url: "https://www.who.int/emergencies/diseases/novel-coronavirus-2019/advice-for-public/myth-busters",
    tag: "WHO",
  },
  {
    title: "NIH: 5G technology and induction of coronavirus in skin cells",
    url: "https://pubmed.ncbi.nlm.nih.gov/",
    tag: "NIH",
  },
  {
    title: "ICMR Advisory on COVID-19 misinformation and public health",
    url: "https://www.icmr.gov.in/",
    tag: "ICMR",
  },
  {
    title: "Reuters Fact Check: False claim that 5G spreads coronavirus",
    url: "https://www.reuters.com/article/uk-factcheck-5g/",
    tag: "Reuters",
  },
  {
    title: "GDELT: Global media coverage of 5G conspiracy claims",
    url: "https://www.gdeltproject.org/",
    tag: "GDELT",
  },
];

const VERDICT_TAGS = ["Technology", "Health", "COVID-19"];

function rand(min: number, max: number) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function EditorialLight() {
  const [dark, setDark] = useState(false);
  const [tab, setTab] = useState<"text" | "screenshot">("text");
  const [claimsCount, setClaimsCount] = useState(1324);
  const [updatedAgo, setUpdatedAgo] = useState(rand(1, 5));
  const analysisMs = useRef(rand(820, 2400));
  const d = dark;

  useEffect(() => {
    const claimsTimer = setInterval(() => {
      setClaimsCount((c) => c + rand(1, 3));
    }, 7000);
    return () => clearInterval(claimsTimer);
  }, []);

  useEffect(() => {
    const updateTimer = setInterval(() => {
      setUpdatedAgo(rand(1, 5));
    }, 10000);
    return () => clearInterval(updateTimer);
  }, []);

  return (
    <div
      style={{ fontFamily: "Georgia, serif" }}
      className={`min-h-screen overflow-auto transition-colors duration-300 ${d ? "bg-[#121212] text-white" : "bg-[#f9f6f0] text-black"
        }`}
    >
      <style>{livePulseStyle}</style>

      {/* Masthead */}
      <div
        className={`border-b-4 px-10 py-5 transition-colors duration-300 ${d ? "border-white bg-[#1a1a1a]" : "border-black bg-white"
          }`}
      >
        <div className="max-w-5xl mx-auto flex items-start justify-between">
          <div>
            <div
              className="text-xs uppercase tracking-[0.3em] font-semibold mb-1"
              style={{ fontFamily: "Inter, sans-serif", color: "#b91c1c" }}
            >
              AI Fact Verification
            </div>
            <div className="flex items-center gap-2.5">
              {/* Pulsating dot next to Alithia */}
              <span
                className="alithia-dot w-2.5 h-2.5 rounded-full shrink-0 inline-block"
                style={{ backgroundColor: "#b91c1c" }}
              />
              <h1 className="text-3xl font-black tracking-tight leading-none">Alithia</h1>
            </div>
          </div>
          <div className="flex items-center gap-5">
            {/* Claims counter */}
            <div
              className={`text-right border-r pr-5 ${d ? "border-gray-700" : "border-gray-200"}`}
            >
              <div
                className="text-2xl font-black tabular-nums"
                style={{ color: "#b91c1c", fontFamily: "Inter, sans-serif" }}
              >
                {claimsCount.toLocaleString()}
              </div>
              <div
                className={`text-[10px] uppercase tracking-widest font-semibold ${d ? "text-gray-500" : "text-gray-400"}`}
                style={{ fontFamily: "Inter, sans-serif" }}
              >
                Claims Analyzed
              </div>
            </div>
            <div className="text-right">
              <div className="text-xs text-gray-400" style={{ fontFamily: "Inter, sans-serif" }}>
                March 27, 2026
              </div>
              <div className="text-xs text-gray-400 mt-0.5" style={{ fontFamily: "Inter, sans-serif" }}>
                English · 9 Indian Languages
              </div>
            </div>
            <button
              onClick={() => setDark(!d)}
              className={`w-9 h-9 rounded-full flex items-center justify-center border-2 transition-colors duration-200 ${d
                  ? "border-white text-white hover:bg-white hover:text-black"
                  : "border-black text-black hover:bg-black hover:text-white"
                }`}
              aria-label="Toggle dark mode"
            >
              {d ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </div>
      </div>

      {/* Red bar — static */}
      <div
        className="text-white text-xs py-1.5 px-6"
        style={{ backgroundColor: "#b91c1c", fontFamily: "Inter, sans-serif" }}
      >
        <div className="max-w-5xl mx-auto flex items-center gap-4">
          <span
            className="font-bold uppercase tracking-widest bg-white px-2 py-0.5 text-[10px] rounded shrink-0"
            style={{ color: "#b91c1c" }}
          >
            LIVE
          </span>
          <span className="opacity-90">
            Fact-checking viral claims in real time &nbsp;·&nbsp; Powered by trusted sources &nbsp;·&nbsp; GDELT &nbsp;·&nbsp; DuckDuckGo &nbsp;·&nbsp; Google Fact Check &nbsp;·&nbsp; Wayback Machine
          </span>
        </div>
      </div>

      {/* Trending ticker — scrolling */}
      <div
        className="text-white text-xs py-1.5 overflow-hidden"
        style={{ backgroundColor: d ? "#111" : "#111", fontFamily: "Inter, sans-serif" }}
      >
        <div className="flex items-center gap-0">
          <span
            className="font-bold uppercase tracking-widest px-3 py-0.5 text-[10px] shrink-0 h-full flex items-center"
            style={{ backgroundColor: "#222", color: "#f59e0b", letterSpacing: "0.15em" }}
          >
            TRENDING
          </span>
          <div className="overflow-hidden flex-1">
            <span className="ticker-track text-gray-300">
              &nbsp; 1. WhatsApp to charge ₹99/month — FALSE &nbsp;·&nbsp; 2. PM Modi announces free 5G by Dec 2026 — MISLEADING &nbsp;·&nbsp; 3. Kerala floods linked to cloud-seeding experiment — UNVERIFIED &nbsp;·&nbsp; 4. AIIMS study links Aadhaar scans to cancer risk — FALSE &nbsp;·&nbsp; 5. AI chatbot clears UPSC Mains with 98% score — MISLEADING &nbsp;·&nbsp;&nbsp; 1. WhatsApp to charge ₹99/month — FALSE &nbsp;·&nbsp; 2. PM Modi announces free 5G by Dec 2026 — MISLEADING &nbsp;·&nbsp; 3. Kerala floods linked to cloud-seeding experiment — UNVERIFIED &nbsp;·&nbsp; 4. AIIMS study links Aadhaar scans to cancer risk — FALSE &nbsp;·&nbsp; 5. AI chatbot clears UPSC Mains with 98% score — MISLEADING &nbsp;
            </span>
          </div>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-10 py-10">
        {/* Headline */}
        <div className={`mb-10 pb-8 border-b-2 ${d ? "border-white" : "border-black"}`}>
          <div className="flex items-center justify-between mb-3">
            <p
              className="text-sm uppercase tracking-widest font-bold"
              style={{ fontFamily: "Inter, sans-serif", color: "#b91c1c" }}
            >
              Breaking Analysis
            </p>
            {/* LIVE box — right side */}
            <span
              className="live-box inline-flex items-center gap-1.5 border px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest"
              style={{
                fontFamily: "Inter, sans-serif",
                borderColor: "#b91c1c",
                color: "#b91c1c",
              }}
            >
              <span
                className="live-dot-only w-1.5 h-1.5 rounded-full inline-block"
                style={{ backgroundColor: "#b91c1c" }}
              />
              Live
            </span>
          </div>
          <h2 className="text-5xl font-black leading-tight mb-4">
            Is That Viral Post<br />Actually True?
          </h2>
          <p
            className={`text-lg leading-relaxed max-w-2xl ${d ? "text-gray-300" : "text-gray-600"}`}
            style={{ fontFamily: "Inter, sans-serif" }}
          >
            Paste any tweet, WhatsApp forward, or social media post below. Our AI
            cross-references thousands of verified sources to deliver an instant,{" "}
            <span className={`font-semibold ${d ? "text-white" : "text-black"}`}>
              evidence-backed verdict.
            </span>
            <span
              className={`ml-2 text-sm font-normal ${d ? "text-gray-500" : "text-gray-400"}`}
              style={{ fontFamily: "Inter, sans-serif" }}
            >
              Updated {updatedAgo}s ago
            </span>
          </p>
        </div>

        <div className="grid grid-cols-3 gap-8">
          {/* Main column */}
          <div className="col-span-2">
            <div className={`flex gap-0 mb-0 border-b-2 ${d ? "border-white" : "border-black"}`}>
              {(["text", "screenshot"] as const).map((t) => {
                const active = tab === t;
                return (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className={`px-5 py-2.5 text-sm font-semibold transition-all -mb-[2px] ${active
                        ? d
                          ? "bg-white text-black border-2 border-white"
                          : "bg-black text-white border-2 border-black"
                        : d
                          ? "text-gray-400 hover:text-white"
                          : "text-gray-500 hover:text-black"
                      }`}
                    style={{ fontFamily: "Inter, sans-serif" }}
                  >
                    {t === "text" ? "✏ Text" : "⊞ Screenshot"}
                  </button>
                );
              })}
            </div>

            <div
              className={`border-2 border-t-0 p-5 ${d ? "border-white bg-[#1a1a1a]" : "border-black bg-white"
                }`}
            >
              {tab === "text" ? (
                <textarea
                  placeholder="Paste a tweet, WhatsApp forward, or any social post here..."
                  className={`w-full h-36 text-sm resize-none focus:outline-none leading-relaxed bg-transparent ${d ? "text-gray-200 placeholder-gray-600" : "text-gray-700 placeholder-gray-300"
                    }`}
                  style={{ fontFamily: "Inter, sans-serif" }}
                />
              ) : (
                <div
                  className={`w-full h-36 border-2 border-dashed flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors ${d ? "border-gray-600 hover:border-white" : "border-gray-300 hover:border-black"
                    }`}
                >
                  <p
                    className={`text-sm ${d ? "text-gray-500" : "text-gray-400"}`}
                    style={{ fontFamily: "Inter, sans-serif" }}
                  >
                    Drop screenshot or click to upload
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-end mt-3">
              <button
                className="text-white font-bold px-8 py-3 text-sm uppercase tracking-widest transition-colors hover:opacity-90"
                style={{ backgroundColor: "#b91c1c", fontFamily: "Inter, sans-serif" }}
              >
                Analyze Claim →
              </button>
            </div>

            {/* Verdict */}
            <div className={`mt-8 border-2 overflow-hidden ${d ? "border-white" : "border-black"}`}>
              <div
                className="text-white px-5 py-2.5 flex items-center justify-between"
                style={{ backgroundColor: "#b91c1c" }}
              >
                <span className="font-bold text-sm uppercase tracking-wider" style={{ fontFamily: "Inter, sans-serif" }}>
                  Verdict
                </span>
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-normal ${d ? "text-red-200" : "text-red-100"}`}
                    style={{ fontFamily: "Inter, sans-serif" }}
                  >
                    Analyzed in {analysisMs.current}ms
                  </span>
                  <span
                    className="text-xs font-bold px-3 py-1 uppercase tracking-widest bg-white"
                    style={{ color: "#b91c1c", fontFamily: "Inter, sans-serif" }}
                  >
                    MISLEADING
                  </span>
                </div>
              </div>
              <div className={`p-5 space-y-4 ${d ? "bg-[#1a1a1a]" : "bg-white"}`}>
                <blockquote
                  className={`border-l-4 pl-4 text-sm leading-relaxed italic ${d ? "text-gray-200" : "text-gray-800"}`}
                  style={{ borderColor: "#b91c1c" }}
                >
                  "5G towers cause COVID-19 — leaked government document confirms"
                </blockquote>
                <p
                  className={`text-sm leading-relaxed ${d ? "text-gray-300" : "text-gray-600"}`}
                  style={{ fontFamily: "Inter, sans-serif" }}
                >
                  No credible scientific evidence supports a link between 5G networks and COVID-19 transmission.
                  The cited document cannot be verified. Fourteen peer-reviewed studies and agencies including
                  WHO, NIH, and ICMR have refuted this claim.
                </p>

                {/* Tag pills */}
                <div className="flex gap-2 flex-wrap items-center pt-1">
                  {VERDICT_TAGS.map((tag) => (
                    <span
                      key={tag}
                      className={`text-[10px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full border ${d
                          ? "border-gray-600 text-gray-300 bg-[#2a2a2a]"
                          : "border-gray-300 text-gray-600 bg-gray-50"
                        }`}
                      style={{ fontFamily: "Inter, sans-serif" }}
                    >
                      {tag}
                    </span>
                  ))}
                  {/* Claims count pill */}
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-0.5 rounded-full"
                    style={{
                      fontFamily: "Inter, sans-serif",
                      backgroundColor: "#b91c1c",
                      color: "white",
                    }}
                  >
                    {claimsCount.toLocaleString()} Claims
                  </span>
                </div>

                <div className="flex gap-2 flex-wrap pt-0">
                  {SOURCES.map((s) => (
                    <a
                      key={s.tag}
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className={`text-xs border px-2 py-0.5 transition-colors ${d
                          ? "border-gray-600 text-gray-400 hover:border-white hover:text-white"
                          : "border-gray-300 text-gray-500 hover:border-black hover:text-black"
                        }`}
                      style={{ fontFamily: "Inter, sans-serif" }}
                    >
                      {s.tag}
                    </a>
                  ))}
                </div>
              </div>
            </div>
            {/* Ad box under verdict */}
            <div
              className={`mt-5 border-2 border-dashed p-4 flex flex-col items-center justify-center gap-1 min-h-[80px] ${d ? "border-gray-700 bg-[#1a1a1a]" : "border-gray-300 bg-gray-50"
                }`}
            >
              <span
                className={`text-[9px] uppercase tracking-widest ${d ? "text-gray-600" : "text-gray-300"}`}
                style={{ fontFamily: "Inter, sans-serif" }}
              >
                Advertisement
              </span>
              <div className={`w-full h-14 flex items-center justify-center ${d ? "bg-[#222]" : "bg-gray-100"}`}>
                <span className={`text-xs ${d ? "text-gray-600" : "text-gray-300"}`} style={{ fontFamily: "Inter, sans-serif" }}>
                  Your Ad Here
                </span>
              </div>
            </div>
          </div>

          {/* Sidebar */}
          <div className="space-y-5">
            {/* Accuracy Score */}
            <div className={`border-2 p-4 ${d ? "border-white bg-[#1a1a1a]" : "border-black bg-white"}`}>
              <h3
                className={`font-black text-sm uppercase tracking-widest pb-2 mb-3 ${d ? "border-b border-gray-700" : "border-b border-gray-200"
                  }`}
                style={{ fontFamily: "Inter, sans-serif" }}
              >
                Accuracy Score
              </h3>
              <div className="text-5xl font-black" style={{ color: "#b91c1c" }}>12</div>
              <div className={`text-xs mt-1 ${d ? "text-gray-500" : "text-gray-400"}`} style={{ fontFamily: "Inter, sans-serif" }}>
                out of 100
              </div>
              <div className={`mt-3 h-2 rounded-full overflow-hidden ${d ? "bg-gray-800" : "bg-gray-100"}`}>
                <div className="h-full rounded-full" style={{ width: "12%", backgroundColor: "#b91c1c" }} />
              </div>
            </div>

            {/* Sources */}
            <div className={`border-2 p-4 ${d ? "border-white bg-[#1a1a1a]" : "border-black bg-white"}`}>
              <h3
                className={`font-black text-sm uppercase tracking-widest pb-2 mb-3 ${d ? "border-b border-gray-700" : "border-b border-gray-200"
                  }`}
                style={{ fontFamily: "Inter, sans-serif" }}
              >
                Sources
              </h3>
              <ul className="space-y-3" style={{ fontFamily: "Inter, sans-serif" }}>
                {SOURCES.map((s) => (
                  <li key={s.tag} className="flex items-start justify-between gap-2">
                    <div className="flex items-start gap-2 min-w-0">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block mt-1.5 shrink-0" />
                      <span className={`text-xs leading-snug line-clamp-2 ${d ? "text-gray-300" : "text-gray-600"}`}>
                        {s.title}
                      </span>
                    </div>
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noreferrer"
                      className={`shrink-0 w-5 h-5 border flex items-center justify-center text-[10px] font-bold mt-0.5 transition-colors ${d
                          ? "border-gray-600 text-gray-400 hover:border-white hover:text-white"
                          : "border-gray-300 text-gray-400 hover:border-black hover:text-black"
                        }`}
                    >
                      ›
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            {/* Ad box */}
            <div
              className={`border-2 border-dashed p-4 flex flex-col items-center justify-center gap-1 min-h-[80px] ${d ? "border-gray-700 bg-[#1a1a1a]" : "border-gray-300 bg-gray-50"
                }`}
            >
              <span
                className={`text-[9px] uppercase tracking-widest ${d ? "text-gray-600" : "text-gray-300"}`}
                style={{ fontFamily: "Inter, sans-serif" }}
              >
                Advertisement
              </span>
              <div className={`w-full h-12 flex items-center justify-center ${d ? "bg-[#222]" : "bg-gray-100"}`}>
                <span className={`text-xs ${d ? "text-gray-600" : "text-gray-300"}`} style={{ fontFamily: "Inter, sans-serif" }}>
                  Your Ad Here
                </span>
              </div>
            </div>

            {/* About */}
            <div
              className={`border-2 p-4 text-xs leading-relaxed ${d ? "border-white bg-[#222] text-gray-300" : "border-black bg-[#f0ebe0] text-gray-600"
                }`}
              style={{ fontFamily: "Inter, sans-serif" }}
            >
              <strong className={`block mb-1 uppercase tracking-wide text-[10px] ${d ? "text-white" : "text-black"}`}>
                About
              </strong>
              Alithia is an AI-powered fact-checking tool built for GDG 2026. Supports English and 9 Indian languages.
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div
        className={`border-t-2 py-4 text-center text-xs ${d ? "border-white text-gray-500" : "border-black text-gray-400"}`}
        style={{ fontFamily: "Inter, sans-serif" }}
      >
        Alithia · Built for GDG 2026 · Powered by Sarvam AI
      </div>
    </div>
  );
}
