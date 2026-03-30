// content.js — Viral Claim Radar
// Responds to messages from popup.js to extract text from the page.

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "GET_SELECTION") {
    const sel = window.getSelection()?.toString()?.trim();
    sendResponse({ text: sel || "" });
    return true;
  }
  if (msg.type === "GET_PAGE_TEXT") {
    // Extract meaningful text: paragraphs, headings, listed items
    const els = document.querySelectorAll(
      "p, h1, h2, h3, h4, article, [role='article'], .post-content, .article-body"
    );
    let text = "";
    if (els.length > 0) {
      text = Array.from(els)
        .map((el) => el.innerText?.trim())
        .filter(Boolean)
        .join("\n")
        .slice(0, 4000); // cap at 4k chars
    } else {
      text = document.body.innerText?.slice(0, 4000) || "";
    }
    sendResponse({ text: text.trim() });
    return true;
  }
});

// ── Floating Action Button (FAB) Overlay ──────────────────────

let overlayHost = null;
let shadowRoot = null;
let isIframeOpen = false;

function initOverlay() {
  if (overlayHost) return;

  overlayHost = document.createElement('div');
  overlayHost.style.position = 'fixed';
  overlayHost.style.bottom = '24px';
  overlayHost.style.right = '24px';
  overlayHost.style.zIndex = '2147483647'; // max z-index
  overlayHost.style.display = 'flex';
  overlayHost.style.flexDirection = 'column';
  overlayHost.style.alignItems = 'flex-end';
  overlayHost.style.pointerEvents = 'none';

  shadowRoot = overlayHost.attachShadow({ mode: 'closed' });

  const style = document.createElement('style');
  style.textContent = `
    * { box-sizing: border-box; }
    .fab-btn {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #000;
      border: 3px solid #111;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 4px 12px rgba(0,0,0,0.25);
      transition: transform 0.2s, box-shadow 0.2s;
      pointer-events: auto;
      user-select: none;
      font-family: 'Inter', -apple-system, sans-serif;
    }
    .fab-btn:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 16px rgba(0,0,0,0.3);
    }
    .fab-btn:active {
      transform: scale(0.95);
    }
    .fab-logo {
      display: flex;
      align-items:baseline;
      justify-content:center;
      line-height:1;
    }
    .fab-a {
      color: #fff;
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -1px;
    }
    .fab-dot {
      color: #ff0000;
      font-size: 24px;
      font-weight: 900;
      margin-left: 1px;
      line-height: 0.5;
    }
    .fab-ai {
      color: #fff;
      font-size: 14px;
      font-weight: 700;
      margin-left: 1px;
    }
    .iframe-container {
      width: 400px;
      height: 600px;
      max-height: calc(100vh - 100px);
      border: none;
      border-radius: 12px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.2);
      margin-bottom: 20px;
      background: transparent;
      overflow: hidden;
      display: none;
      pointer-events: auto;
      transform-origin: bottom right;
      animation: pop-up 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .iframe-container.open {
      display: block;
    }
    @keyframes pop-up {
      from { opacity: 0; transform: scale(0.9) translateY(10px); }
      to { opacity: 1; transform: scale(1) translateY(0); }
    }
  `;

  const iframe = document.createElement('iframe');
  iframe.src = chrome.runtime.getURL('popup.html') + '?overlay=1';
  iframe.className = 'iframe-container';
  iframe.allow = "clipboard-read; clipboard-write";

  const fab = document.createElement('div');
  fab.className = 'fab-btn';
  fab.innerHTML = `
    <div class="fab-logo">
      <span class="fab-a">A</span><span class="fab-dot">.</span><span class="fab-ai">ai</span>
    </div>
  `;

  fab.addEventListener('click', () => {
    isIframeOpen = !isIframeOpen;
    if (isIframeOpen) {
      iframe.classList.add('open');
    } else {
      iframe.classList.remove('open');
    }
  });

  shadowRoot.appendChild(style);
  shadowRoot.appendChild(iframe);
  shadowRoot.appendChild(fab);

  document.body.appendChild(overlayHost);
}

function removeOverlay() {
  if (overlayHost) {
    overlayHost.remove();
    overlayHost = null;
    shadowRoot = null;
    isIframeOpen = false;
  }
}

// Ensure setting is checked on load
chrome.storage.sync.get(['overlayEnabled'], (result) => {
  if (result.overlayEnabled) {
    initOverlay();
  }
});

// React to live changes
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'sync' && changes.overlayEnabled !== undefined) {
    if (changes.overlayEnabled.newValue) {
      initOverlay();
    } else {
      removeOverlay();
    }
  }
});
