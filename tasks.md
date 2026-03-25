# Viral Claim Radar — Build Checklist
**Deadline:** 2026-03-27

---

## Day 1 — Foundation (2026-03-25)

### A · Project Setup
- [ ] Init GitHub repo (`/backend`, `/frontend`, `/scripts`, `/data`)
- [ ] Write `backend/requirements.txt`
- [ ] Create `.env.example` + `config.py` (chunk size, top-K, model names)
- [ ] Verify Groq API key works (test call)
- [ ] Verify Sarvam AI API key works (test call)
- [ ] Scaffold Next.js frontend (`create-next-app`)
- [ ] Confirm EasyOCR imports without error (CPU mode)

### B · Web Scraper
- [ ] Check each site for JS rendering (requests+BS4 vs Playwright)
- [ ] Build `scraper.py` base (rate-limit 1.5s, User-Agent rotation, dedup by URL hash)
- [ ] Scraper: BOOM Live
- [ ] Scraper: AltNews
- [ ] Scraper: Reuters, AFP, PIB
- [ ] Validate output — `data/scraped_corpus.jsonl` (2000+ entries)

### C · Corpus Ingestion & FAISS Index  *(Critical Path)*
- [ ] Load provided offline corpus + scraped JSONL into unified schema
- [ ] Clean text (strip HTML, normalize whitespace, dedup)
- [ ] Chunk with `RecursiveCharacterTextSplitter` (384 tokens, 64 overlap)
- [ ] Embed with `all-MiniLM-L6-v2` (batch=64, normalize vectors)
- [ ] Build & save `faiss.IndexFlatIP` → `data/faiss.index` + `data/chunk_meta.pkl`
- [ ] Write `retriever.py` with `retrieve(query, top_k=8) -> List[Chunk]`
- [ ] Smoke test retrieval on 5 known false claims

### D · Claim Extractor
- [ ] Write `claim_extractor.py` with LLM system + user prompt
- [ ] Add JSON parse validation + retry + fallback
- [ ] Test on 15 diverse inputs (tweets, WhatsApp forwards, Hindi text)
- [ ] Add claim deduplication (skip near-identical claims)

### E · RAG + Stance Classification  *(start)*
- [ ] Define `VerificationResult` Pydantic model
- [ ] Build trust-tier re-ranker (govt=1.5x, verified org=1.2x, portal=1.0x)
- [ ] Write stance LLM prompt → JSON output (Supported / Refuted / Uncertain)

---

## Day 2 — Full-Stack (2026-03-26)

### E · RAG + Stance Classification  *(finish)*
- [ ] Implement confidence calibration (Low / Medium / High)
- [ ] Force Uncertain if all FAISS scores < 0.30 (corpus miss)
- [ ] Async parallel verification (`asyncio.gather`)
- [ ] End-to-end CLI test

### F · Patient 0 Origin Tracer
- [ ] Write keyword extractor (claim → 3-5 query keywords via LLM)
- [ ] Implement Wayback Machine CDX API client
- [ ] Define `OriginResult` model + LLM origin-type classifier
- [ ] Wrap in `find_origin()` with 6s `asyncio.wait_for` timeout
- [ ] Test on 5 known viral claims (expect 3/5 hits)

### G · OCR Module
- [ ] Write `ocr.py` (resize, grayscale, deskew, EasyOCR)
- [ ] Post-process: strip timestamps, like/share counts, UI chrome text
- [ ] Pre-load EasyOCR reader in FastAPI lifespan (not per-request)
- [ ] Test on 8 screenshots (English + Hindi, blurry, rotated)

### H · Sarvam AI — Multilingual
- [ ] Write `multilingual.py` (detect language, translate via Sarvam API)
- [ ] Integrate into pipeline: non-English input → translate → process → translate reasoning back
- [ ] (Stretch) Sarvam TTS for verdict readback

### I · FastAPI Backend
- [ ] App skeleton with lifespan + CORS (`localhost:3000`)
- [ ] `POST /ocr` endpoint
- [ ] `POST /analyze` endpoint (orchestrate: OCR → translate → extract → RAG + Patient 0 parallel)
- [ ] `GET /health` endpoint
- [ ] Define `AnalysisResponse` schema
- [ ] Error handling (422, 503, corpus miss → Uncertain)
- [ ] Profile response times; target < 8s for 3-claim post

### J · Frontend UI  *(start)*
- [ ] CSS variables: dark mode color tokens + Inter font
- [ ] `InputPanel`: textarea + drag-drop image upload zone
- [ ] Radar sweep CSS animation (loading overlay)
- [ ] `ClaimPill` row (color-coded: 🟢/🔴/🟡, click → scroll to card)
- [ ] `EvidenceCard` (stance badge, confidence bar, reasoning, source chips)
- [ ] `Patient0Card` (timeline or "Origin Unknown" fallback)

---

## Day 3 — Polish & Submit (2026-03-27)

### J · Frontend UI  *(finish)*
- [ ] API integration (POST to backend, handle loading/error/success states)
- [ ] Language badge + original text collapsible block
- [ ] Mobile responsiveness (375px)

### K · Polish & Submission
- [ ] Stress test: 10+ diverse claims (health, politics, science, finance)
- [ ] Fix top 3 bugs from stress test
- [ ] Add skeleton loaders + card stagger animations
- [ ] Write `README.md` (setup, Mermaid architecture diagram)
- [ ] Record 2-3 min demo video  
- [ ] Prepare 5-slide pitch deck
- [ ] (Stretch) Deploy frontend to Vercel, backend to Render
