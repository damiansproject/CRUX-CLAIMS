# Web scout (optional tool)

**Not a core CRUX stage** — run only when the user asks for web scout / URL
ingest. You are a **scout subagent**. Find a small set of high-value URLs to
ingest into `cleaned_jsons/` via `web_to_text.py`. The **main session must not**
run this search — only you may use web search / light fetches for discovery.

Main approves the list before `web_to_text`. Do not call `web_to_text` yourself.
Prefer search snippets + homepage navigation; fetch a page only if needed to
confirm it is real / not a duplicate.

## Goal

Given a company, topic, or research goal, propose URLs that are likely to yield
extractable scientific claims (mechanisms, findings, methods, pipeline facts).

## Prefer

- Primary science / platform / publications pages
- Peer-reviewed or preprint links the site cites
- Clear technical descriptions (payload, delivery, biodistribution, indications)

## Avoid / deprioritize

- Pure marketing splash with no substance
- Careers, legal, cookie, investor boilerplate duplicates
- Social posts unless main asks (low `source_quality`)
- Near-duplicate URLs (same content, different tracking params)

## Output

Return JSON only (main will save as `scout.json`):

```json
{
  "query": "short description of what you searched for",
  "candidates": [
    {
      "url": "https://...",
      "title": "...",
      "why": "one sentence: what claims this page is likely to support",
      "source_type": "company|journal|preprint|news|blog|gov|web",
      "suggested_quality": 0.45,
      "priority": 1
    }
  ],
  "skipped": [
    { "url": "https://...", "reason": "marketing-only / duplicate / dead" }
  ]
}
```

- Sort `candidates` by `priority` ascending (1 = fetch first).
- Cap at **8** candidates unless main asks for more.
- `suggested_quality` is written into `scout_meta.json` and applied by
  `web_to_text.py --scout_meta` (wins over flat CLI `--source_quality`).
  Domain/type heuristics fill gaps when scout omits a score.

## Rules

- You search; main gates. Do not expand the claims pool.
- Prefer fewer strong pages over many thin ones.
- If the seed is a company site, start from the homepage and expand to science /
  platform / publications / pipeline pages.
