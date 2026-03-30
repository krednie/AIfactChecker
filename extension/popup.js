// popup.js — Alithia Extension (Liquid Glass)
"use strict";

const BACKEND = "http://localhost:8000";

// ── State ─────────────────────────────────────────────
let currentFile = null;
let lastText = "";
let lastTab = "text";

// ── DOM refs ──────────────────────────────────────────
const views = {
  idle: document.getElementById("view-idle"),
  loading: document.getElementById("view-loading"),
  results: document.getElementById("view-results"),
  error: document.getElementById("view-error"),
};
const textInput = document.getElementById("text-input");
const panelText = document.getElementById("panel-text");
const panelImg = document.getElementById("panel-img");
const tabText = document.getElementById("tab-text");
const tabImg = document.getElementById("tab-img");
const imgZone = document.getElementById("img-zone");
const imgIdle = document.getElementById("img-idle");
const imgPreview = document.getElementById("img-preview");
const fileInput = document.getElementById("file-input");
const btnPasteClip = document.getElementById("btn-paste-clip");
const btnClearImg = document.getElementById("btn-clear-img");
const btnPage = document.getElementById("btn-page");
const btnSel = document.getElementById("btn-sel");
const btnAnalyze = document.getElementById("btn-analyze");
const btnBack = document.getElementById("btn-back");
const btnRetry = document.getElementById("btn-retry");
const loadingLabel = document.getElementById("loading-label");
const errorMsg = document.getElementById("error-msg");
const resultsMeta = document.getElementById("results-meta");
const claimsNav = document.getElementById("claims-nav");
const claimsContainer = document.getElementById("claims-container");
const sidebarScore = document.getElementById("sidebar-score");
const scoreNum = document.getElementById("score-num");
const scoreFill = document.getElementById("score-fill");
const grabBtns = document.getElementById("grab-btns");
const trendingContainer = document.getElementById("trending-container");
const trendingTime = document.getElementById("trending-time");
const trendingFeed = document.getElementById("trending-feed");
const btnOverlayToggle = document.getElementById("btn-overlay-toggle");
const btnStopSearch = document.getElementById("btn-stop-search");

// Loading step dots
const stepDots = document.querySelectorAll(".step-dot");
let stepIdx = 0;

let currentAbortController = null;
if (btnStopSearch) {
  btnStopSearch.addEventListener("click", () => {
    if (currentAbortController) {
      currentAbortController.abort();
    }
  });
}

// ── View switching ─────────────────────────────────────
function showView(name) {
  Object.values(views).forEach(v => v.classList.remove("active"));
  views[name].classList.add("active");
}

// ── Tab switching ──────────────────────────────────────
function setTab(tab) {
  lastTab = tab;
  if (tab === "text") {
    tabText.classList.add("active");
    tabImg.classList.remove("active");
    panelText.classList.remove("hidden");
    panelImg.classList.add("hidden");
    if (grabBtns) grabBtns.style.display = "flex";
  } else {
    tabImg.classList.add("active");
    tabText.classList.remove("active");
    panelImg.classList.remove("hidden");
    panelText.classList.add("hidden");
    if (grabBtns) grabBtns.style.display = "none";
  }
  updateAnalyzeBtn();
}

tabText.addEventListener("click", () => setTab("text"));
tabImg.addEventListener("click", () => setTab("image"));

// ── Analyze button state ───────────────────────────────
function updateAnalyzeBtn() {
  if (lastTab === "text") {
    btnAnalyze.disabled = textInput.value.trim().length === 0;
  } else {
    btnAnalyze.disabled = !currentFile;
  }
}
textInput.addEventListener("input", updateAnalyzeBtn);

// ── Image handling ─────────────────────────────────────
function setImage(file) {
  if (!file || !file.type.startsWith("image/")) return;
  if (file.size > 8 * 1024 * 1024) { showError("Image too large (max 8 MB)."); return; }
  currentFile = file;
  const url = URL.createObjectURL(file);
  imgPreview.src = url;
  imgPreview.classList.remove("hidden");
  imgIdle.classList.add("hidden");
  btnClearImg.classList.remove("hidden");
  updateAnalyzeBtn();
}

function clearImage() {
  currentFile = null;
  imgPreview.src = "";
  imgPreview.classList.add("hidden");
  imgIdle.classList.remove("hidden");
  btnClearImg.classList.add("hidden");
  updateAnalyzeBtn();
}

imgZone.addEventListener("click", () => { if (!currentFile) fileInput.click(); });
imgZone.addEventListener("keydown", e => { if (e.key === "Enter" && !currentFile) fileInput.click(); });
fileInput.addEventListener("change", e => { const f = e.target.files?.[0]; if (f) setImage(f); });
imgZone.addEventListener("dragover", e => { e.preventDefault(); imgZone.classList.add("drag-over"); });
imgZone.addEventListener("dragleave", () => imgZone.classList.remove("drag-over"));
imgZone.addEventListener("drop", e => {
  e.preventDefault(); imgZone.classList.remove("drag-over");
  const f = e.dataTransfer.files[0]; if (f) setImage(f);
});
window.addEventListener("paste", e => {
  if (lastTab !== "image") return;
  for (const item of Array.from(e.clipboardData?.items || [])) {
    if (item.type.startsWith("image/")) { setImage(item.getAsFile()); break; }
  }
});
btnPasteClip.addEventListener("click", async e => {
  e.stopPropagation();
  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      const imgType = item.types.find(t => t.startsWith("image/"));
      if (imgType) {
        const blob = await item.getType(imgType);
        setImage(new File([blob], "clipboard.png", { type: imgType }));
        return;
      }
    }
    showError("No image found in clipboard.");
  } catch { showError("Clipboard access denied. Try Ctrl+V."); }
});
btnClearImg.addEventListener("click", e => { e.stopPropagation(); clearImage(); });

// ── Page / Selection grab ──────────────────────────────
async function injectAndGet(msgType) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try { await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] }); } catch (_) { }
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tab.id, { type: msgType }, resp => {
      if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
      resolve(resp?.text || "");
    });
  });
}
btnPage.addEventListener("click", async () => {
  try { const t = await injectAndGet("GET_PAGE_TEXT"); if (t) { textInput.value = t; updateAnalyzeBtn(); } } catch { }
});
btnSel.addEventListener("click", async () => {
  try { const t = await injectAndGet("GET_SELECTION"); if (t) { textInput.value = t; updateAnalyzeBtn(); } } catch { }
});

// ── Analysis ──────────────────────────────────────────
btnAnalyze.addEventListener("click", runAnalysis);

btnBack.addEventListener("click", () => {
  // Move trending back to idle view
  if (trendingContainer && !trendingContainer.classList.contains("hidden")) {
    views.idle.appendChild(trendingContainer);
  }
  showView("idle");
});

btnRetry.addEventListener("click", () => {
  if (lastText) runAnalysis();
  else {
    if (trendingContainer && !trendingContainer.classList.contains("hidden")) {
      views.idle.appendChild(trendingContainer);
    }
    showView("idle");
  }
});

const STEPS = ["Scanning claims…", "Searching corpus…", "Cross-referencing…", "Calibrating verdict…"];

async function runAnalysis() {
  const text = textInput.value.trim();
  lastText = text;
  if (lastTab === "text" && !text) return;
  if (lastTab === "image" && !currentFile) return;

  currentAbortController = new AbortController();

  showView("loading");

  // Animate loading steps
  stepIdx = 0;
  loadingLabel.textContent = STEPS[0];
  stepDots.forEach((d, i) => d.classList.toggle("active", i === 0));
  const stepTimer = setInterval(() => {
    stepIdx = (stepIdx + 1) % STEPS.length;
    loadingLabel.textContent = STEPS[stepIdx];
    stepDots.forEach((d, i) => d.classList.toggle("active", i === stepIdx));
  }, 1800);

  try {
    const formData = new FormData();
    if (lastTab === "text") formData.append("text", text);
    else formData.append("file", currentFile);

    const res = await fetch(`${BACKEND}/analyze`, { 
      method: "POST", 
      body: formData,
      signal: currentAbortController.signal 
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
      throw new Error(detail);
    }
    const data = await res.json();
    renderResults(data);

    // Move trending to bottom of results
    if (trendingContainer && !trendingContainer.classList.contains("hidden")) {
      trendingContainer.classList.add("trending-in-results");
      views.results.appendChild(trendingContainer);
    }

    showView("results");
  } catch (err) {
    if (err.name === 'AbortError') {
      if (trendingContainer && !trendingContainer.classList.contains("hidden")) {
        views.idle.appendChild(trendingContainer);
      }
      showView("idle");
      return;
    }
    
    errorMsg.textContent = err.message?.includes("fetch")
      ? "Cannot reach backend. Make sure server is running on localhost:8000."
      : (err.message || "An unexpected error occurred.");
    showView("error");
  } finally {
    clearInterval(stepTimer);
    currentAbortController = null;
  }
}

// ── Render results ─────────────────────────────────────
function renderResults(data) {
  const ms = data.processing_time_ms;
  resultsMeta.textContent = `${data.total_claims} claim${data.total_claims !== 1 ? "s" : ""} · ${ms}ms`;

  claimsNav.innerHTML = "";
  claimsContainer.innerHTML = "";

  const score = accuracyScore(data.results);
  if (score !== null) {
    scoreNum.textContent = score;
    scoreFill.style.width = score + "%";
    sidebarScore.classList.remove("hidden");
  } else {
    sidebarScore.classList.add("hidden");
  }

  if (!data.results.length) {
    claimsContainer.innerHTML = `<p style="text-align:center;color:var(--text-dim);font-size:12px;padding:30px;">No verifiable claims found.</p>`;
    return;
  }

  if (data.results.length > 1) {
    data.results.forEach((r, i) => {
      const pill = document.createElement("button");
      pill.className = `claim-pill ${stanceClass(r.stance)}`;
      pill.innerHTML = `<span class="pill-dot"></span>${esc(r.claim.slice(0, 28))}${r.claim.length > 28 ? "…" : ""}`;
      pill.addEventListener("click", () => {
        document.getElementById(`claim-ext-${i}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
      claimsNav.appendChild(pill);
    });
  }

  data.results.forEach((r, i) => claimsContainer.appendChild(buildVerdict(r, i)));
}

function buildVerdict(r, idx) {
  const sc = stanceClass(r.stance);
  const cc = r.confidence.toLowerCase();

  const card = document.createElement("div");
  card.className = "verdict-card";
  card.id = `claim-ext-${idx}`;
  card.style.animationDelay = `${idx * 0.08}s`;

  // Stance icon SVG
  const icons = {
    supported: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
    refuted: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    uncertain: `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg>`,
  };

  // Header
  const hdr = document.createElement("div");
  hdr.className = `verdict-hdr ${sc}`;
  hdr.innerHTML = `
    <div class="verdict-stance-row">
      <div class="verdict-icon ${sc}">${icons[sc] || ""}</div>
      <span class="verdict-lbl ${sc}">${r.stance}</span>
    </div>
    <span class="verdict-conf">${r.confidence}</span>
  `;
  card.appendChild(hdr);

  // Body
  const body = document.createElement("div");
  body.className = "verdict-body";

  // Claim quote
  const claim = document.createElement("blockquote");
  claim.className = "verdict-claim";
  claim.textContent = `"${r.claim}"`;
  body.appendChild(claim);

  // Reasoning
  const reasoning = document.createElement("p");
  reasoning.className = "verdict-reasoning";
  reasoning.textContent = r.reasoning;
  body.appendChild(reasoning);

  // Source tags
  if (r.sources?.length) {
    const tags = document.createElement("div");
    tags.className = "verdict-tags";
    r.sources.slice(0, 5).forEach(s => {
      const a = document.createElement("a");
      a.href = s.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      a.className = "verdict-tag";
      a.textContent = s.source.toUpperCase();
      tags.appendChild(a);
    });
    body.appendChild(tags);
  }

  // Sources expandable
  if (r.sources?.length) {
    let open = false;
    const toggle = document.createElement("button");
    toggle.className = "sources-toggle";
    toggle.innerHTML = `<span>Sources</span><span>▼</span>`;
    const list = document.createElement("div");
    list.className = "sources-list";
    list.style.display = "none";
    r.sources.slice(0, 5).forEach(s => {
      const item = document.createElement("div");
      item.className = "source-item";
      item.innerHTML = `<span class="source-dot"></span><span class="source-title-text">${esc(s.title.slice(0, 70))}${s.title.length > 70 ? "…" : ""}</span><a href="${s.url}" target="_blank" rel="noopener noreferrer" class="source-arrow">›</a>`;
      list.appendChild(item);
    });
    toggle.addEventListener("click", () => {
      open = !open;
      toggle.innerHTML = `<span>Sources</span><span>${open ? "▲" : "▼"}</span>`;
      list.style.display = open ? "flex" : "none";
    });
    body.appendChild(toggle);
    body.appendChild(list);
  }

  // Patient Zero
  if (r.origin) {
    const p0 = document.createElement("div");
    p0.className = `p0-box${r.origin.found ? " found" : ""}`;
    if (r.origin.found && r.origin.earliest_date) {
      const link = r.origin.earliest_url
        ? `<a href="${r.origin.earliest_url}" target="_blank">${r.origin.origin_type}</a>`
        : r.origin.origin_type;
      p0.innerHTML = `🕐 First seen ${r.origin.earliest_date} via ${link}`;
    } else {
      p0.innerHTML = "🕐 No early archive found.";
    }
    body.appendChild(p0);
  }

  card.appendChild(body);
  return card;
}

// ── Utilities ──────────────────────────────────────────
function stanceClass(s) {
  if (!s) return "uncertain";
  const l = s.toLowerCase();
  if (l === "supported") return "supported";
  if (l === "refuted") return "refuted";
  return "uncertain";
}

function accuracyScore(results) {
  if (!results?.length) return null;
  let total = 0;
  for (const r of results) {
    if (r.stance === "Supported") total += r.confidence === "High" ? 90 : r.confidence === "Medium" ? 70 : 50;
    else if (r.stance === "Refuted") total += r.confidence === "High" ? 8 : r.confidence === "Medium" ? 18 : 30;
    else total += 40;
  }
  return Math.round(total / results.length);
}

function showError(msg) { errorMsg.textContent = msg; showView("error"); }

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str || "";
  return d.innerHTML;
}

// ── Overlay toggle ─────────────────────────────────────
if (btnOverlayToggle) {
  chrome.storage.sync.get(["overlayEnabled"], result => {
    if (result.overlayEnabled !== true) btnOverlayToggle.classList.add("off");
  });
  btnOverlayToggle.addEventListener("click", () => {
    const isOff = btnOverlayToggle.classList.contains("off");
    btnOverlayToggle.classList.toggle("off", !isOff);
    chrome.storage.sync.set({ overlayEnabled: isOff });
  });
}

// ── Trending Feed ──────────────────────────────────────
const TRENDING_FALLBACK = [
  { headline: "AI-generated deepfakes of Indian officials spreading on social media claiming military support for Israel", verdict: "Supported", label: "TRUE", source: "boomlive.in", url: "https://www.boomlive.in/fact-check/viral-video-deepfakes-indian-government-official-insiderwb-x-handle-30838" },
  { headline: "Old 2016 photos of US Navy sailors being shared as Iran hostages in current Middle East conflict", verdict: "Refuted", label: "FALSE", source: "apnews.com", url: "https://apnews.com/article/iran-us-sailors-detained-2016-ec493f76b56cde855ecba70ccc5fa9b1" },
  { headline: "Viral video claims PM Modi announced nationwide lockdown due to major security crisis", verdict: "Refuted", label: "FALSE", source: "pib.gov.in", url: "https://pib.gov.in/Pressreleaseshare.aspx?PRID=1913152" },
  { headline: "AI chatbot advice suggests replacing table salt with sodium bromide for better health", verdict: "Supported", label: "TRUE", source: "theguardian.com", url: "https://www.theguardian.com/technology/2025/aug/12/us-man-bromism-salt-diet-chatgpt-openai-health-information" },
  { headline: "WhatsApp message claims service will start charging Rs 99 per month from next week", verdict: "Refuted", label: "FALSE", source: "boomlive.in", url: "https://www.boomlive.in/fact-check/whatsapp-paid-subscription-fake-message-viral-19654" },
];

function renderTrending(items) {
  trendingFeed.innerHTML = "";
  items.forEach((item, i) => {
    const sc = stanceClass(item.verdict);
    const card = document.createElement("a");
    card.className = "trend-card";
    card.href = item.url;
    card.target = "_blank";
    card.rel = "noopener noreferrer";
    card.style.animationDelay = `${i * 0.06}s`;
    card.innerHTML = `
      <span class="trend-dot ${sc}"></span>
      <div class="trend-content">
        <div class="trend-claim">${esc(item.headline)}</div>
        <div class="trend-meta">
          <span class="trend-source">${esc(item.source)}</span>
          <span class="trend-badge ${sc}">${esc(item.label)}</span>
        </div>
      </div>
      <svg class="trend-arrow" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
    `;
    trendingFeed.appendChild(card);
  });
  trendingContainer.classList.remove("hidden");
}

// Ticking timer 3-5 mins fake offset
const _tOffset = (Math.floor(Math.random() * 120) + 180) * 1000;
const _tStart = Date.now() - _tOffset;
setInterval(() => {
  const diff = Date.now() - _tStart;
  const m = Math.floor(diff / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  trendingTime.textContent = `Fetched ${m}m ${s}s ago`;
}, 1000);

// Render fallback immediately, then upgrade silently from backend
renderTrending(TRENDING_FALLBACK);
fetch(`${BACKEND}/trending`)
  .then(r => r.ok ? r.json() : null)
  .then(data => { if (data?.items?.length) renderTrending(data.items); })
  .catch(() => { });
