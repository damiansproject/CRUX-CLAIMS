# Artifact schemas (claim-extractor)

Ids for claims are minted only by `write_claims.py` — never by workflow
agents. Literature-map ids (`agr_` / `ctr_` / `gap_`) are assigned when Claude
writes `literature_map.json` (no write script).

| Prefix | Writer | Shape |
| --- | --- | --- |
| `clm_` | `write_claims.py` | `clm_<paper_id>_<nnnn>` |
| `agr_` / `ctr_` / `gap_` | Claude (`literature_map.json`) | local skim ids only; not write-script minted |

## Pre-bank / shard envelope (before write_claims)

Workers emit this; `/crux-extract-claims` also enforces it via `schema`.
`merge_extract.py` → `write_claims.py` stamp ids / `source`.

**Extract:** `{ paper_id, venue, source_type, suggested_quality, quality_rationale, title, gist, claims: [{ kind, statement, quotes }] }`

## Cleaned source (`cleaned_jsons/<paper_id>.json`)

One file per source. Convert whatever the user put in `input/` into this
shape (via converters or by hand). `cleaned_jsons/index.json` lists
`{paper_id, text_path, status: "ok"|"error", gist?, …}` for `index_to_papers.py`.
After extract, `write_claims.py` also writes `<run>/gists.json`
(`{ paper_id, title, gist, claim_count }`) for later seed packing.

```json
{
  "paper_id": "stable_id",
  "origin": "pdf|web|epub|text|other",
  "source_pdf": "path or null",
  "source_url": "url or null",
  "title": "…",
  "venue": null,
  "source_type": "pdf|journal|preprint|company|web|…",
  "source_quality": 0.7,
  "quality_rationale": "…",
  "gist": "80–160 word packing summary, stamped after extract",
  "backend": "docling|web_fetch|manual|…",
  "page_count": 1,
  "pages": [{ "page": 1, "text": "…" }]
}
```

## Claim (`claims.jsonl` row)

```json
{
  "id": "clm_<paper_id>_0001",
  "paper_id": "…",
  "origin": "pdf|web",
  "source_quality": 0.7,
  "source": {
    "type": "pdf|journal|company|…",
    "url": null,
    "venue": null,
    "title": "…",
    "quality_rationale": "type:pdf|venue:…|override"
  },
  "kind": "finding|mechanism|method|limitation|assumption|problem|other",
  "statement": "self-contained summary",
  "quotes": [
    {
      "text": "verbatim span from one page",
      "locator": { "paper": "<paper_id>", "page": 1, "section": null, "line": null }
    }
  ]
}
```

## Literature map (`literature_map.json`) — optional tool

Written only when the user asks for the literature-map **tool**. Follow
`prompts/literature-map.md` — no `write_*.py` script. Skim landscape only; not
seed input. Local map ids (`agr_` / `ctr_` / `gap_`) are assigned here; claim
pointers must be real `clm_…` ids from the claims file.

```json
{
  "schema_version": "1.0",
  "claims_path": "…/claims.jsonl",
  "research_goal": null,
  "created_at": "2026-08-07T00:00:00Z",
  "coverage_note": "…",
  "agreements": [
    {
      "id": "agr_001",
      "statement": "…",
      "evidence_claim_ids": ["clm_…", "clm_…"],
      "paper_ids": ["…", "…"],
      "confidence": 0.8,
      "note": null
    }
  ],
  "contradictions": [
    {
      "id": "ctr_001",
      "issue": "…",
      "claim_a_id": "clm_…",
      "claim_b_id": "clm_…",
      "reason": "…",
      "resolution": "…",
      "cluster": "method or system label",
      "confidence": 0.7
    }
  ],
  "gaps": [
    {
      "id": "gap_001",
      "description": "specific open question…",
      "caused_by_claim_ids": ["clm_…"],
      "importance": "critical|high|medium|low",
      "confidence": 0.75,
      "note": null
    }
  ]
}
```
