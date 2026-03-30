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
