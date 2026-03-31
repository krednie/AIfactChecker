"""
backend/analytics.py - Deterministic post-analysis metrics for verification runs.

The goal is to keep scoring, clustering, and explainability grounded in explicit
computation instead of folding everything into LLM prose. These analytics are
built from retrieved evidence, source metadata, and lightweight heuristics that
work with the current pipeline.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import math
import re
from typing import Any
from urllib.parse import urlparse

import numpy as np

from backend.patient0 import OriginResult
from backend.retriever import RetrievedChunk, Retriever


_DATE_PATTERNS = (
    re.compile(r"(?P<date>20\d{2}-\d{2}-\d{2})"),
    re.compile(r"(?P<date>20\d{2}/\d{2}/\d{2})"),
    re.compile(r"(?P<date>20\d{6})"),
)

_REFUTE_TERMS = (
    "false",
    "fake",
    "debunk",
    "debunked",
    "misleading",
    "fabricated",
    "no evidence",
    "not true",
    "hoax",
    "incorrect",
    "altered",
)
_SUPPORT_TERMS = (
    "true",
    "confirmed",
    "official",
    "verified",
    "did happen",
    "announced",
    "approved",
    "reported",
    "statement",
)
_UNCERTAIN_TERMS = (
    "alleged",
    "unclear",
    "unverified",
    "reportedly",
    "claims",
    "claimed",
    "possible",
    "under investigation",
)
_INTENSITY_TERMS = (
    "shocking",
    "viral",
    "urgent",
    "must watch",
    "explosive",
    "breaking",
    "panic",
    "massive",
)

_DEFAULT_REGISTRY = {
    "govt": {
        "credibility_score": 0.92,
        "category": "government",
        "political_bias": 0.15,
        "historical_accuracy": 0.92,
    },
    "verified": {
        "credibility_score": 0.82,
        "category": "verified-news",
        "political_bias": 0.12,
        "historical_accuracy": 0.85,
    },
    "portal": {
        "credibility_score": 0.68,
        "category": "web",
        "political_bias": 0.2,
        "historical_accuracy": 0.72,
    },
}

_SOURCE_REGISTRY = {
    "reuters.com": {
        "credibility_score": 0.94,
        "category": "wire",
        "political_bias": 0.06,
        "historical_accuracy": 0.96,
    },
    "apnews.com": {
        "credibility_score": 0.93,
        "category": "wire",
        "political_bias": 0.05,
        "historical_accuracy": 0.95,
    },
    "bbc.com": {
        "credibility_score": 0.9,
        "category": "broadcaster",
        "political_bias": 0.08,
        "historical_accuracy": 0.92,
    },
    "bbc.co.uk": {
        "credibility_score": 0.9,
        "category": "broadcaster",
        "political_bias": 0.08,
        "historical_accuracy": 0.92,
    },
    "who.int": {
        "credibility_score": 0.96,
        "category": "health-authority",
        "political_bias": 0.04,
        "historical_accuracy": 0.96,
    },
    "cdc.gov": {
        "credibility_score": 0.95,
        "category": "health-authority",
        "political_bias": 0.08,
        "historical_accuracy": 0.95,
    },
    "pib.gov.in": {
        "credibility_score": 0.9,
        "category": "government",
        "political_bias": 0.18,
        "historical_accuracy": 0.9,
    },
    "altnews.in": {
        "credibility_score": 0.86,
        "category": "fact-checker",
        "political_bias": 0.18,
        "historical_accuracy": 0.87,
    },
    "boomlive.in": {
        "credibility_score": 0.84,
        "category": "fact-checker",
        "political_bias": 0.14,
        "historical_accuracy": 0.86,
    },
    "factcheck.afp.com": {
        "credibility_score": 0.88,
        "category": "fact-checker",
        "political_bias": 0.07,
        "historical_accuracy": 0.9,
    },
    "theguardian.com": {
        "credibility_score": 0.78,
        "category": "publisher",
        "political_bias": 0.22,
        "historical_accuracy": 0.79,
    },
}


@dataclass
class _EvidenceRecord:
    title: str
    url: str
    domain: str
    source: str
    source_tier: str
    source_credibility: float
    category: str
    political_bias: float
    historical_accuracy: float
    relevance_score: float
    recency_score: float
    date: datetime | None
    stance: str
    stance_signal: float
    cluster_id: int = 0
    cluster_uniqueness: float = 1.0
    final_weight: float = 0.0


def build_claim_analytics(
    claim: str,
    chunks: list[RetrievedChunk],
    stance: Any,
    confidence: Any,
    origin: OriginResult | None = None,
) -> dict[str, Any]:
    if not chunks:
        return {
            "source_distribution": {},
            "stance_scores": {
                "supported": 0.0,
                "refuted": 0.0,
                "uncertain": 1.0,
                "verdict": _enum_value(stance),
            },
            "clusters": [],
            "temporal_metrics": {
                "first_seen_timestamp": origin.earliest_date if origin and origin.found else None,
                "peak_density_window": None,
                "decay_rate": 0.0,
                "dated_evidence_count": 0,
            },
            "bias_index": 0.0,
            "confidence_score": _confidence_value(confidence) / 100,
            "virality_index": 0.0,
            "agreement_score": 0.0,
            "avg_source_credibility": 0.0,
            "evidence_volume_normalized": 0.0,
            "weighted_sources": [],
            "explainability": {
                "top_supporting_sources": [],
                "top_refuting_sources": [],
                "key_conflicts": [],
                "dominant_narrative": "No evidence available.",
                "minority_narrative": None,
            },
        }

    evidence = [_build_evidence_record(rc) for rc in chunks]
    _assign_clusters(evidence)
    _apply_weights(evidence)

    weighted_sources = sorted(evidence, key=lambda item: item.final_weight, reverse=True)
    stance_scores = _compute_stance_scores(weighted_sources, stance)
    temporal = _compute_temporal_metrics(weighted_sources, origin)
    bias_index = _compute_bias_index(weighted_sources)
    agreement_score = max(
        stance_scores["supported"],
        stance_scores["refuted"],
        stance_scores["uncertain"],
    )
    avg_source_credibility = round(
        sum(item.source_credibility * item.final_weight for item in weighted_sources)
        / max(sum(item.final_weight for item in weighted_sources), 1e-6),
        3,
    )
    evidence_volume_normalized = round(
        min(math.log1p(len(weighted_sources)) / math.log(12), 1.0),
        3,
    )
    confidence_score = round(
        agreement_score * avg_source_credibility * evidence_volume_normalized,
        3,
    )
    clusters = _serialize_clusters(weighted_sources)

    return {
        "source_distribution": dict(Counter(item.domain for item in weighted_sources)),
        "stance_scores": stance_scores,
        "clusters": clusters,
        "temporal_metrics": temporal,
        "bias_index": bias_index,
        "confidence_score": confidence_score,
        "virality_index": temporal["virality_index"],
        "agreement_score": round(agreement_score, 3),
        "avg_source_credibility": avg_source_credibility,
        "evidence_volume_normalized": evidence_volume_normalized,
        "weighted_sources": [
            {
                "title": item.title,
                "url": item.url,
                "domain": item.domain,
                "source": item.source,
                "source_tier": item.source_tier,
                "source_credibility": round(item.source_credibility, 3),
                "category": item.category,
                "political_bias": round(item.political_bias, 3),
                "historical_accuracy": round(item.historical_accuracy, 3),
                "relevance_score": round(item.relevance_score, 3),
                "recency_score": round(item.recency_score, 3),
                "cluster_uniqueness": round(item.cluster_uniqueness, 3),
                "stance": item.stance,
                "final_weight": round(item.final_weight, 3),
            }
            for item in weighted_sources
        ],
        "explainability": _build_explainability(weighted_sources, clusters),
    }


def build_report_analytics(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "claim_count": 0,
            "stance_distribution": {},
            "average_confidence_score": 0.0,
            "average_bias_index": 0.0,
            "top_influencers": [],
            "dominant_narratives": [],
        }

    stance_distribution = Counter(result["stance"] for result in results)
    confidence_scores = [
        result.get("analytics", {}).get("confidence_score", 0.0)
        for result in results
    ]
    bias_scores = [
        result.get("analytics", {}).get("bias_index", 0.0)
        for result in results
    ]

    influencer_pool: list[dict[str, Any]] = []
    narratives: list[str] = []
    for result in results:
        analytics = result.get("analytics") or {}
        influencer_pool.extend(analytics.get("weighted_sources", [])[:3])
        explainability = analytics.get("explainability") or {}
        dominant = explainability.get("dominant_narrative")
        if dominant:
            narratives.append(dominant)

    influencer_pool.sort(key=lambda item: item.get("final_weight", 0.0), reverse=True)

    return {
        "claim_count": len(results),
        "stance_distribution": dict(stance_distribution),
        "average_confidence_score": round(sum(confidence_scores) / len(confidence_scores), 3),
        "average_bias_index": round(sum(bias_scores) / len(bias_scores), 3),
        "top_influencers": influencer_pool[:5],
        "dominant_narratives": narratives[:5],
    }


def _build_evidence_record(rc: RetrievedChunk) -> _EvidenceRecord:
    domain = _normalize_domain(rc.chunk.url)
    profile = _lookup_source_profile(domain, rc.chunk.source_tier)
    title = rc.chunk.title or domain or rc.chunk.source
    date = _extract_date(rc.chunk.text, rc.chunk.title, rc.chunk.url)
    stance, stance_signal = _classify_evidence_stance(rc.chunk.text, rc.chunk.title)
    return _EvidenceRecord(
        title=title,
        url=rc.chunk.url,
        domain=domain or rc.chunk.source,
        source=rc.chunk.source,
        source_tier=rc.chunk.source_tier,
        source_credibility=profile["credibility_score"],
        category=profile["category"],
        political_bias=profile["political_bias"],
        historical_accuracy=profile["historical_accuracy"],
        relevance_score=max(0.0, min(rc.boosted_score, 1.0)),
        recency_score=_compute_recency_score(date),
        date=date,
        stance=stance,
        stance_signal=stance_signal,
    )


def _assign_clusters(evidence: list[_EvidenceRecord]) -> None:
    if len(evidence) == 1:
        evidence[0].cluster_id = 1
        evidence[0].cluster_uniqueness = 1.0
        return

    texts = [f"{item.title}. {item.domain}. {item.source}" for item in evidence]
    try:
        embeddings = Retriever.get()._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except Exception:
        embeddings = np.eye(len(texts), dtype="float32")

    centroids: list[np.ndarray] = []
    cluster_members: list[list[int]] = []
    threshold = 0.74

    for idx, emb in enumerate(embeddings):
        if not centroids:
            centroids.append(np.array(emb, dtype="float32"))
            cluster_members.append([idx])
            evidence[idx].cluster_id = 1
            continue

        similarities = [float(np.dot(emb, centroid)) for centroid in centroids]
        best_idx = int(np.argmax(similarities))
        if similarities[best_idx] >= threshold:
            cluster_members[best_idx].append(idx)
            members = cluster_members[best_idx]
            centroid = np.mean([embeddings[m] for m in members], axis=0)
            norm = np.linalg.norm(centroid) or 1.0
            centroids[best_idx] = centroid / norm
            evidence[idx].cluster_id = best_idx + 1
        else:
            centroids.append(np.array(emb, dtype="float32"))
            cluster_members.append([idx])
            evidence[idx].cluster_id = len(centroids)

    cluster_sizes = Counter(item.cluster_id for item in evidence)
    for item in evidence:
        item.cluster_uniqueness = round(1 / cluster_sizes[item.cluster_id], 3)


def _apply_weights(evidence: list[_EvidenceRecord]) -> None:
    for item in evidence:
        item.final_weight = (
            item.source_credibility * 0.4
            + item.relevance_score * 0.3
            + item.recency_score * 0.2
            + item.cluster_uniqueness * 0.1
        )


def _compute_stance_scores(
    evidence: list[_EvidenceRecord],
    fallback_stance: Any,
) -> dict[str, Any]:
    totals = {"supported": 0.0, "refuted": 0.0, "uncertain": 0.0}
    for item in evidence:
        if item.stance == "support":
            totals["supported"] += item.final_weight
        elif item.stance == "refute":
            totals["refuted"] += item.final_weight
        else:
            totals["uncertain"] += item.final_weight

    total_mass = sum(totals.values())
    if total_mass <= 0:
        return {
            "supported": 0.0,
            "refuted": 0.0,
            "uncertain": 1.0,
            "verdict": _enum_value(fallback_stance),
        }

    normalized = {key: round(value / total_mass, 3) for key, value in totals.items()}
    winner = max(normalized, key=normalized.get)
    winner_map = {
        "supported": "Supported",
        "refuted": "Refuted",
        "uncertain": "Uncertain",
    }
    normalized["verdict"] = winner_map.get(winner, _enum_value(fallback_stance))
    return normalized


def _compute_temporal_metrics(
    evidence: list[_EvidenceRecord],
    origin: OriginResult | None,
) -> dict[str, Any]:
    dated = sorted(item.date for item in evidence if item.date is not None)
    first_seen = origin.earliest_date if origin and origin.found else None

    if not dated:
        return {
            "first_seen_timestamp": first_seen,
            "peak_density_window": None,
            "decay_rate": 0.0,
            "virality_index": 0.0,
            "dated_evidence_count": 0,
        }

    if first_seen is None:
        first_seen = dated[0].date().isoformat()

    peak_count = 0
    peak_start = dated[0]
    peak_end = dated[0]
    left = 0
    for right, right_date in enumerate(dated):
        while (right_date - dated[left]).days > 7:
            left += 1
        window_count = right - left + 1
        if window_count > peak_count:
            peak_count = window_count
            peak_start = dated[left]
            peak_end = right_date

    span_days = max((dated[-1] - dated[0]).days, 1)
    tail_count = sum(1 for dt in dated if (dated[-1] - dt).days <= 7)
    decay_rate = round(max(peak_count - tail_count, 0) / span_days, 3)
    time_to_peak = max((peak_end - dated[0]).days, 1)
    virality_index = round(peak_count / time_to_peak, 3)

    return {
        "first_seen_timestamp": first_seen,
        "peak_density_window": f"{peak_start.date().isoformat()} to {peak_end.date().isoformat()}",
        "decay_rate": decay_rate,
        "virality_index": virality_index,
        "dated_evidence_count": len(dated),
    }


def _compute_bias_index(evidence: list[_EvidenceRecord]) -> float:
    if not evidence:
        return 0.0

    source_bias = sum(abs(item.political_bias) for item in evidence) / len(evidence)
    stance_extremes = sum(item.stance_signal for item in evidence) / len(evidence)
    language_intensity = sum(_language_intensity(item.title) for item in evidence) / len(evidence)
    return round(
        min(1.0, source_bias * 0.5 + stance_extremes * 0.3 + language_intensity * 0.2),
        3,
    )


def _serialize_clusters(evidence: list[_EvidenceRecord]) -> list[dict[str, Any]]:
    grouped: dict[int, list[_EvidenceRecord]] = {}
    for item in evidence:
        grouped.setdefault(item.cluster_id, []).append(item)

    clusters: list[dict[str, Any]] = []
    for cluster_id, members in grouped.items():
        stance_distribution = Counter(item.stance for item in members)
        dominant_stance = stance_distribution.most_common(1)[0][0]
        total_weight = sum(item.final_weight for item in members)
        label = members[0].title[:96]
        clusters.append(
            {
                "cluster_id": cluster_id,
                "label": label,
                "evidence_count": len(members),
                "total_weight": round(total_weight, 3),
                "dominant_stance": dominant_stance,
                "domains": sorted({item.domain for item in members}),
            }
        )

    clusters.sort(key=lambda item: item["total_weight"], reverse=True)
    return clusters


def _build_explainability(
    evidence: list[_EvidenceRecord],
    clusters: list[dict[str, Any]],
) -> dict[str, Any]:
    supporting = [item for item in evidence if item.stance == "support"][:3]
    refuting = [item for item in evidence if item.stance == "refute"][:3]
    key_conflicts: list[str] = []

    if supporting and refuting:
        key_conflicts.append(
            f"Supportive evidence from {supporting[0].domain} conflicts with refuting evidence from {refuting[0].domain}."
        )

    dominant_narrative = clusters[0]["label"] if clusters else "No dominant narrative."
    minority_narrative = clusters[1]["label"] if len(clusters) > 1 else None

    return {
        "top_supporting_sources": [
            {
                "title": item.title,
                "domain": item.domain,
                "url": item.url,
                "final_weight": round(item.final_weight, 3),
            }
            for item in supporting
        ],
        "top_refuting_sources": [
            {
                "title": item.title,
                "domain": item.domain,
                "url": item.url,
                "final_weight": round(item.final_weight, 3),
            }
            for item in refuting
        ],
        "key_conflicts": key_conflicts,
        "dominant_narrative": dominant_narrative,
        "minority_narrative": minority_narrative,
    }


def _lookup_source_profile(domain: str, source_tier: str) -> dict[str, float | str]:
    if domain in _SOURCE_REGISTRY:
        return _SOURCE_REGISTRY[domain]
    return _DEFAULT_REGISTRY.get(source_tier, _DEFAULT_REGISTRY["portal"])


def _normalize_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _extract_date(*values: str) -> datetime | None:
    for value in values:
        if not value:
            continue
        for pattern in _DATE_PATTERNS:
            match = pattern.search(value)
            if not match:
                continue
            raw = match.group("date")
            normalized = raw.replace("/", "-")
            if len(normalized) == 8:
                normalized = f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]}"
            try:
                return datetime.strptime(normalized, "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                continue
    return None


def _compute_recency_score(date: datetime | None) -> float:
    if date is None:
        return 0.35
    age_days = max((datetime.now(UTC) - date).days, 0)
    return round(1 / (1 + age_days / 30), 3)


def _classify_evidence_stance(text: str, title: str) -> tuple[str, float]:
    haystack = f"{title} {text}".lower()
    refute_hits = sum(term in haystack for term in _REFUTE_TERMS)
    support_hits = sum(term in haystack for term in _SUPPORT_TERMS)
    uncertain_hits = sum(term in haystack for term in _UNCERTAIN_TERMS)

    if refute_hits > max(support_hits, uncertain_hits):
        return "refute", min(1.0, refute_hits / 3)
    if support_hits > max(refute_hits, uncertain_hits):
        return "support", min(1.0, support_hits / 3)
    return "uncertain", min(1.0, max(uncertain_hits, 1) / 3)


def _language_intensity(text: str) -> float:
    haystack = text.lower()
    hits = sum(term in haystack for term in _INTENSITY_TERMS)
    return min(1.0, hits / 3)


def _confidence_value(confidence: Any) -> int:
    label = _enum_value(confidence)
    if label == "High":
        return 90
    if label == "Medium":
        return 60
    return 35


def _enum_value(value: Any) -> str:
    return getattr(value, "value", str(value))
