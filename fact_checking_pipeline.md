# Scalable Fact-Checking Pipeline (Free Stack)

## Overview
- [ ] Minimize expensive operations
- [ ] Use structured ingestion (RSS/API first)
- [ ] Improve verification quality

---

## 1. Source Registry (Control Layer)
- [ ] Store source_id
- [ ] Store type (rss/api/html)
- [ ] Track update_frequency
- [ ] Track trust_score
- [ ] Track last_fetched
- [ ] Track block_rate
- [ ] Track language

---

## 2. Incremental Ingestion
- [ ] Implement URL hashing
- [ ] Implement content hashing (SimHash/MinHash)
- [ ] Skip duplicate URLs
- [ ] Skip near-duplicate content

---

## 3. Tiered Retrieval
- [ ] Add BM25 (Stage 1 filtering)
- [ ] Add metadata filtering
- [ ] Run FAISS only on top-k results

---

## 4. Structured Claim Extraction
- [ ] Output format: subject, predicate, object, time, location
- [ ] Remove opinions
- [ ] Remove unverifiable claims

---

## 5. Evidence Graph
- [ ] Map Claim → Evidence → Source
- [ ] Track supporting sources
- [ ] Track contradicting sources
- [ ] Store timestamps

---

## 6. Propagation Tracking
- [ ] Track earliest occurrence
- [ ] Count independent sources
- [ ] Track spread pattern

---

## 7. Source Credibility
- [ ] Compute historical accuracy
- [ ] Compute agreement rate
- [ ] Compute correction rate

---

## 8. Temporal Validation
- [ ] Compare claim_time vs evidence_time
- [ ] Penalize mismatches

---

## 9. Selective OCR
- [ ] Use OCR only if extraction fails
- [ ] Skip OCR otherwise

---

## 10. Translation Optimization
- [ ] Detect language first
- [ ] Translate only when needed
- [ ] Cache translations
- [ ] Store original + translated text

---

## 11. Confidence Decomposition
- [ ] Semantic match score
- [ ] Source trust score
- [ ] Cross-source agreement score
- [ ] Temporal match score

---

## 12. Caching Layer
- [ ] Cache embeddings
- [ ] Cache translations
- [ ] Cache FAISS queries
- [ ] Cache claim outputs

---

## 13. Async Pipeline
- [ ] Implement queue (Redis)
- [ ] Parallelize embedding
- [ ] Parallelize claim extraction
- [ ] Parallelize retrieval

---

## 14. Rate & Failure Control
- [ ] Monitor API usage
- [ ] Adjust ingestion rate dynamically
- [ ] Track block rate
- [ ] Track success rate

---

## 15. Final Pipeline
- [ ] Source Registry
- [ ] Scheduler
- [ ] RSS/API ingestion
- [ ] Deduplication
- [ ] Language detection
- [ ] Claim extraction
- [ ] BM25 retrieval
- [ ] FAISS retrieval
- [ ] Evidence graph
- [ ] Verification
- [ ] Confidence scoring
- [ ] Storage + cache

---

## 16. Free Stack
- [ ] RSS/APIs for ingestion
- [ ] Redis for queue/cache
- [ ] Whoosh (BM25)
- [ ] FAISS (vector search)
- [ ] spaCy + HuggingFace
- [ ] Tesseract OCR
- [ ] PostgreSQL / SQLite
