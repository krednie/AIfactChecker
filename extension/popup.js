// popup.js — Alithia Extension
"use strict";

const BACKEND = "http://localhost:8000";

// ── State ─────────────────────────────────────────
let currentFile = null;
let lastText = "";
let lastTab = "text";

// ── DOM refs ──────────────────────────────────────
const views = {
  idle:    document.getElementById("view-idle"),
  loading: document.getElementById("view-loading"),
  results: document.getElementById("view-results"),
  error:   document.getElementById("view-error"),
};
const textInput     = document.getElementById("text-input");
const panelText     = document.getElementById("panel-text");
const panelImg      = document.getElementById("panel-img");
const tabText       = document.getElementById("tab-text");
const tabImg        = document.getElementById("tab-img");
const imgZone       = document.getElementById("img-zone");
const imgIdle       = document.getElementById("img-idle");
const imgPreview    = document.getElementById("img-preview");
const fileInput     = document.getElementById("file-input");
const btnPasteClip  = document.getElementById("btn-paste-clip");
const btnClearImg   = document.getElementById("btn-clear-img");
const btnPage       = document.getElementById("btn-page");
const btnSel        = document.getElementById("btn-sel");
const btnAnalyze    = document.getElementById("btn-analyze");
const btnBack       = document.getElementById("btn-back");
const btnRetry      = document.getElementById("btn-retry");
const loadingLabel  = document.getElementById("loading-label");
const errorMsg      = document.getElementById("error-msg");
const resultsMeta   = document.getElementById("results-meta");
const claimsNav     = document.getElementById("claims-nav");
const claimsContainer = document.getElementById("claims-container");
const sidebarScore  = document.getElementById("sidebar-score");
const scoreNum      = document.getElementById("score-num");
const scoreFill     = document.getElementById("score-fill");
const grabBtns      = document.getElementById("grab-btns");

// ── View switching ─────────────────────────────────
function showView(name) {
  Object.values(views).forEach(v => v.classList.remove("active"));
  views[name].classList.add("active");
}

// ── Tab switching ──────────────────────────────────
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

// ── Analyze button state ───────────────────────────
function updateAnalyzeBtn() {
  if (lastTab === "text") {
    btnAnalyze.disabled = textInput.value.trim().length === 0;
  } else {
    btnAnalyze.disabled = !currentFile;
  }
}
textInput.addEventListener("input", updateAnalyzeBtn);

// ── Image handling ─────────────────────────────────
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

// Click to upload
imgZone.addEventListener("click", () => { if (!currentFile) fileInput.click(); });
imgZone.addEventListener("keydown", e => { if (e.key === "Enter" && !currentFile) fileInput.click(); });
fileInput.addEventListener("change", e => {
  const f = e.target.files?.[0];
  if (f) setImage(f);
});

// Drag & drop
imgZone.addEventListener("dragover", e => { e.preventDefault(); imgZone.classList.add("drag-over"); });
imgZone.addEventListener("dragleave", () => imgZone.classList.remove("drag-over"));
imgZone.addEventListener("drop", e => {
  e.preventDefault();
  imgZone.classList.remove("drag-over");
  const f = e.dataTransfer.files[0];
  if (f) setImage(f);
});

// Ctrl+V global paste
window.addEventListener("paste", e => {
  if (lastTab !== "image") return;
  const items = e.clipboardData?.items;
  if (!items) return;
  for (const item of Array.from(items)) {
    if (item.type.startsWith("image/")) {
      const blob = item.getAsFile();
      if (blob) { setImage(blob); break; }
    }
  }
});

// Paste clipboard button
btnPasteClip.addEventListener("click", async e => {
  e.stopPropagation();
  try {
    const items = await navigator.clipboard.read();
    for (const item of items) {
      const imgType = item.types.find(t => t.startsWith("image/"));
      if (imgType) {
        const blob = await item.getType(imgType);
        const f = new File([blob], "clipboard.png", { type: imgType });
        setImage(f);
        return;
      }
    }
    showError("No image found in clipboard. Copy a screenshot first.");
  } catch {
    showError("Could not access clipboard. Try using Ctrl+V directly on the area above.");
  }
});

// Clear image
btnClearImg.addEventListener("click", e => { e.stopPropagation(); clearImage(); });

// ── Page / Selection grab ──────────────────────────
async function injectAndGet(msgType) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
  } catch (_) { /* already injected */ }
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tab.id, { type: msgType }, resp => {
      if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
      resolve(resp?.text || "");
    });
  });
}

btnPage.addEventListener("click", async () => {
  try {
    const t = await injectAndGet("GET_PAGE_TEXT");
    if (t) { textInput.value = t; updateAnalyzeBtn(); }
  } catch { /* no-op */ }
});

btnSel.addEventListener("click", async () => {
  try {
    const t = await injectAndGet("GET_SELECTION");
    if (t) { textInput.value = t; updateAnalyzeBtn(); }
  } catch { /* no-op */ }
});

// ── Analysis ──────────────────────────────────────
btnAnalyze.addEventListener("click", runAnalysis);
btnBack.addEventListener("click", () => showView("idle"));
btnRetry.addEventListener("click", () => { if (lastText) runAnalysis(); else showView("idle"); });

const STEPS = ["Scanning claims…", "Searching corpus…", "Cross-referencing sources…", "Calibrating verdict…"];

async function runAnalysis() {
  const text = textInput.value.trim();
  lastText = text;

  if (lastTab === "text" && !text) return;
  if (lastTab === "image" && !currentFile) return;

  showView("loading");
  let stepIdx = 0;
  loadingLabel.textContent = STEPS[0];
  const stepTimer = setInterval(() => {
    stepIdx = (stepIdx + 1) % STEPS.length;
    loadingLabel.textContent = STEPS[stepIdx];
  }, 1800);

  try {
    const formData = new FormData();
    if (lastTab === "text") formData.append("text", text);
    else formData.append("file", currentFile);

    const res = await fetch(`${BACKEND}/analyze`, { method: "POST", body: formData });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
      throw new Error(detail);
    }
    const data = await res.json();
    renderResults(data);
    showView("results");
  } catch (err) {
    errorMsg.textContent = err.message?.includes("fetch")
      ? "Cannot reach backend. Make sure the server is running on localhost:8000."
      : (err.message || "An unexpected error occurred.");
    showView("error");
  } finally {
    clearInterval(stepTimer);
  }
}

// ── Render ─────────────────────────────────────────
function renderResults(data) {
  const ms = data.processing_time_ms;
  resultsMeta.textContent = `${data.total_claims} claim${data.total_claims !== 1 ? "s" : ""} · ${ms}ms`;

  claimsNav.innerHTML = "";
  claimsContainer.innerHTML = "";

  // Accuracy score
  const score = accuracyScore(data.results);
  if (score !== null) {
    scoreNum.textContent = score;
    scoreFill.style.width = score + "%";
    sidebarScore.classList.remove("hidden");
  } else {
    sidebarScore.classList.add("hidden");
  }

  if (!data.results.length) {
    claimsContainer.innerHTML = `<p style="text-align:center;color:var(--ink-muted);font-size:12px;padding:24px;">No verifiable claims found.</p>`;
    return;
  }

  // Claim pills (>1 claim)
  if (data.results.length > 1) {
    data.results.forEach((r, i) => {
      const pill = document.createElement("button");
      pill.className = `claim-pill ${stanceClass(r.stance)}`;
      pill.innerHTML = `<span class="pill-dot"></span>${esc(r.claim.slice(0, 30))}${r.claim.length > 30 ? "…" : ""}`;
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
  card.style.animationDelay = `${idx * 0.07}s`;

  // Header
  const hdr = document.createElement("div");
  hdr.className = "verdict-hdr";
  hdr.innerHTML = `<span class="verdict-lbl">Verdict</span><span class="verdict-badge ${sc}">${r.stance}</span>`;
  card.appendChild(hdr);

  // Body
  const body = document.createElement("div");
  body.className = "verdict-body";

  // Claim
  const claim = document.createElement("blockquote");
  claim.className = "verdict-claim";
  claim.textContent = `"${r.claim}"`;
  body.appendChild(claim);

  // Confidence
  const confRow = document.createElement("div");
  confRow.className = "conf-row";
  const confWidth = { high: "100%", medium: "60%", low: "25%" }[cc] || "25%";
  confRow.innerHTML = `Confidence <div class="conf-track"><div class="conf-fill ${cc}" style="width:${confWidth}"></div></div> ${r.confidence}`;
  body.appendChild(confRow);

  // Reasoning
  const reasoning = document.createElement("p");
  reasoning.className = "verdict-reasoning";
  reasoning.textContent = r.reasoning;
  body.appendChild(reasoning);

  // Source tags
  if (r.sources?.length) {
    const tags = document.createElement("div");
    tags.className = "verdict-tags";
    r.sources.slice(0, 6).forEach(s => {
      const a = document.createElement("a");
      a.href = s.url;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
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
    toggle.textContent = "Sources ▼";
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
      toggle.textContent = open ? "Sources ▲" : "Sources ▼";
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

// ── Utilities ──────────────────────────────────────
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

function showError(msg) {
  errorMsg.textContent = msg;
  showView("error");
}

function esc(str) {
  const d = document.createElement("div");
  d.textContent = str || "";
  return d.innerHTML;
}

// ── Overlay Toggle Logic ───────────────────────────
const btnOverlayToggle = document.getElementById("btn-overlay-toggle");
if (btnOverlayToggle) {
  // Read initial state
  chrome.storage.sync.get(['overlayEnabled'], (result) => {
    // Default to true or false depending on preference. Let's say false by default.
    const isEnabled = result.overlayEnabled === true;
    if (!isEnabled) {
      btnOverlayToggle.classList.add("off");
    }
  });

  // Handle click
  btnOverlayToggle.addEventListener("click", () => {
    const isCurrentlyOff = btnOverlayToggle.classList.contains("off");
    const newState = isCurrentlyOff; // if it was off, new state is true (on)
    
    if (newState) {
      btnOverlayToggle.classList.remove("off");
    } else {
      btnOverlayToggle.classList.add("off");
    }
    
    chrome.storage.sync.set({ overlayEnabled: newState });
  });
}

