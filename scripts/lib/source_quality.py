"""Heuristic source-quality scores for claims (0.0–1.0).

Main / extractors may override. These defaults bias later seeding and review
toward higher-trust evidence without hard-filtering low scores.
"""

from __future__ import annotations

from urllib.parse import urlparse

# Domains → default score. Unknown hosts fall through to TYPE_DEFAULTS.
DOMAIN_SCORES: dict[str, float] = {
    'nature.com': 0.95,
    'science.org': 0.95,
    'cell.com': 0.95,
    'nejm.org': 0.95,
    'thelancet.com': 0.95,
    'pnas.org': 0.92,
    'oup.com': 0.88,
    'springer.com': 0.85,
    'wiley.com': 0.85,
    'elsevier.com': 0.85,
    'acs.org': 0.88,
    'rsc.org': 0.88,
    'ieee.org': 0.85,
    'acm.org': 0.85,
    'nih.gov': 0.9,
    'ncbi.nlm.nih.gov': 0.88,
    'who.int': 0.88,
    'cdc.gov': 0.88,
    'biorxiv.org': 0.65,
    'medrxiv.org': 0.65,
    'arxiv.org': 0.6,
    'chemrxiv.org': 0.6,
    'ssrn.com': 0.55,
    'doi.org': 0.7,
    'statnews.com': 0.55,
    'technologyreview.com': 0.5,
    'scientificamerican.com': 0.55,
    'medium.com': 0.3,
    'substack.com': 0.3,
    'twitter.com': 0.25,
    'x.com': 0.25,
    'linkedin.com': 0.3,
    'facebook.com': 0.2,
    'reddit.com': 0.25,
    'youtube.com': 0.25,
}

TYPE_DEFAULTS: dict[str, float] = {
    'journal': 0.85,
    'preprint': 0.6,
    'pdf': 0.7,  # local PDF without known venue
    'gov': 0.85,
    'news': 0.45,
    'blog': 0.3,
    'company': 0.4,  # startup / corp; bump if funded-signal noted
    'social': 0.25,
    'web': 0.4,
}

VENUE_SCORES: list[tuple[str, float]] = [
    ('nature biotechnology', 0.95),
    ('nature medicine', 0.95),
    ('nature nanotechnology', 0.95),
    ('nature communications', 0.9),
    ('nature', 0.95),
    ('science translational', 0.92),
    ('science advances', 0.9),
    ('science', 0.95),
    ('cell', 0.95),
    ('lancet', 0.95),
    ('nejm', 0.95),
    ('new england journal', 0.95),
    ('pnas', 0.92),
    ('molecular therapy', 0.88),
    ('nucleic acids research', 0.88),
    ('journal of controlled release', 0.85),
    ('acs nano', 0.88),
    ('nano letters', 0.88),
    ('biorxiv', 0.65),
    ('medrxiv', 0.65),
    ('chemrxiv', 0.6),
    ('arxiv', 0.6),
]


def clamp(score: float) -> float:
    return max(0.0, min(1.0, round(float(score), 3)))


def domain_of(url: str | None) -> str | None:
    if not url or not isinstance(url, str):
        return None
    try:
        host = urlparse(url.strip()).netloc.lower()
    except Exception:
        return None
    if host.startswith('www.'):
        host = host[4:]
    return host or None


def score_domain(domain: str | None) -> float | None:
    if not domain:
        return None
    d = domain.lower()
    if d in DOMAIN_SCORES:
        return DOMAIN_SCORES[d]
    for key, score in DOMAIN_SCORES.items():
        if d == key or d.endswith('.' + key):
            return score
    return None


def score_venue(venue: str | None) -> float | None:
    if not venue or not isinstance(venue, str):
        return None
    v = venue.lower()
    for needle, score in VENUE_SCORES:
        if needle in v:
            return score
    return None


def suggest_source_quality(
    *,
    origin: str,
    url: str | None = None,
    domain: str | None = None,
    venue: str | None = None,
    source_type: str | None = None,
    override: float | None = None,
    override_label: str | None = None,
) -> tuple[float, str]:
    """Return (score, short rationale). override wins when provided."""
    if override is not None:
        return clamp(override), override_label or 'override'

    venue_score = score_venue(venue)
    if venue_score is not None:
        return clamp(venue_score), f'venue:{venue}'

    host = domain or domain_of(url)
    domain_score = score_domain(host)
    if domain_score is not None:
        return clamp(domain_score), f'domain:{host}'

    st = (source_type or origin or 'web').lower()
    if st in TYPE_DEFAULTS:
        return clamp(TYPE_DEFAULTS[st]), f'type:{st}'
    if origin == 'pdf':
        return clamp(TYPE_DEFAULTS['pdf']), 'type:pdf'
    return clamp(TYPE_DEFAULTS['web']), 'type:web'
