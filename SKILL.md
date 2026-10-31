---
name: claim-extractor
description: >-
  CRUX claim extractor: turn a run’s input/ (or any folder of sources) into
  cleaned_jsons and evidence-traceable claims. Use when converting papers or
  approved web sources and extracting claims — not for hypothesizing or ranking.
  At start ask goal, presentation, run mode, and model/effort if missing from
  chat or run.json.
---

# CRUX claim extractor

Main orchestrates conversion, optional scout, and claim extraction. Pace
follows **run mode**. After `claims.jsonl`, invoke `crux-report` for
`02_claims.pdf` **before** the human-facing claims summary, then continue
into the loop unless the user only wanted extraction: **read and follow**
the sibling `/crux` skill at [`.claude/skills/crux/SKILL.md`](../crux/SKILL.md)
(install [CRUX](https://github.com/damiansproject/CRUX/tree/feat/three-skills)
as that folder). Do not rely on `/crux` until you have confirmed it loaded
that file — a user-level `~/.claude/skills/crux` with the same name shadows
the project skill. If the sibling file is missing, stop and tell the user to
install CRUX; do not continue the loop from memory. Hard blockers always
pause.
Ask before any web tool (scout / URL fetch).

Human how-to: [README.md](README.md). Schemas:
[prompts/schemas.md](prompts/schemas.md).

## Kickoff (always, this skill)

At the **start** of this skill — before convert / scout / extract — collect
what is still missing. Skip any item the user already gave in chat **or** that
is already set in `<run>/run.json`. Re-ask only if the user changes it.

Write `<run>/run.json` when the run starts (create if missing). Omit keys that
are not set yet. Do not write empty strings as “unknown.”

```json
{
  "research_goal": "…",
  "presentation": "professional|general",
  "run_mode": "autonomous|manual",
  "model_effort": "eco|intensive|inherit|custom"
}
```

1. **Research goal**, if missing. Record it even though extract does not
   filter by it; scout and later `/crux` need it.
2. **Presentation mode**, if missing — professional (jargon ok) vs general
   (plain language). Affects this skill’s chat summary and the claims report
   only. Workers stay technically precise.
3. **Run mode**, if missing. **Autonomous** *(default if unsure)* — keep
   advancing after each substage; honor mid-run steering. **Manual** — wait
   for go-ahead after each substage (including after the claims report).
4. **Model/effort**, if missing — applies to `/crux-extract-claims` and
   optional tools this skill runs. If unsure, default to **Eco**.

## Runtime

`<skill_root>` = `${CLAUDE_PLUGIN_ROOT}/.claude/skills/claim-extractor`
(plugin/Cowork) or `.claude/skills/claim-extractor` (this repo). Run Python
from the **repo / plugin root**.

Workflow: `/crux-extract-claims`. Plugin runs: pass `extractor_prompt_path`
under `<skill_root>/prompts/` (default is repo-relative).

**No Workflow tool** (Cowork, Codex, Cursor): one fresh subagent per paper; only that paper
+ `prompts/claim-extractor.md`; write a **shard** under
`<run>/shards/extract/` (use `write_shard.py`); return a tiny ack to main;
main runs `merge_extract.py` then invokes `crux-report`.

## Who does what

| Role | Responsibility |
| --- | --- |
| **Main (you)** | This skill’s kickoff; run dir + `input/`; convert; optional scout (ask first); `/crux-extract-claims` with `shards_dir`; `merge_extract.py`; then invoke `crux-report`; then follow sibling [crux/SKILL.md](../crux/SKILL.md) unless extract-only |
| **Provided scripts** | Convert PDFs; mint claim ids; merge extract shards — **no LLM**. URL fetch scripts are for optional web tools only |
| **Workflow / workers** | Extract using `prompts/claim-extractor.md`; with `shards_dir`, persist each result as a shard and return tiny acks |
| **Not provided** | Non-PDF→`cleaned_jsons` converter (main converts those) |

Do **not** invent claim ids or `source` objects — only `write_claims.py`
(via `merge_extract.py`) mints those.

## Scripts

All under `<skill_root>/scripts/`. Prefer these over throwaways.

| Script | You run it to… |
| --- | --- |
| `pdf_to_text.py` | `--pdfs <dir> --out <run>/cleaned_jsons` — PDFs → page JSON + index |
| `write_claims.py` | Bank extract (legacy `--workflow_result`) → `claims.jsonl` `[--append]` + `gists.json` |
| `scout_urls.py` | **Optional web tool only:** `--scout scout.json --out_urls urls.txt --out_meta scout_meta.json` |
| `web_to_text.py` | **Optional web tool only:** `--urls_file … --out <run>/cleaned_jsons [--scout_meta …]` |
| `index_to_papers.py` | `--cleaned_jsons … --out extract_papers.json` for `/crux-extract-claims` |
| `write_shard.py` | Worker helper: atomically write one shard JSON |
| `merge_extract.py` | `--shards <run>/shards/extract --run <run> --papers … --cleaned_jsons …` → `claims.jsonl` |

`scripts/lib/` is shared code (`kinds`, `source_quality`, `index_io`) — import
only; do not “run” it as a CLI.

## Workflows, shards, and path mode

In Claude Code the `crux` plugin registers each workflow under its own namespace: pass `crux:<name>` as the Workflow tool's `name` (for example `crux:crux-extract-claims`); the bare name is not found. Launch the shipped workflow by that name, never by `scriptPath`.

Ids: `clm_`. Optional literature-map tool ids `agr_` / `ctr_` / `gap_`.

**Default bank path (slash + Cowork):** pass `shards_dir` =
`<run>/shards/extract` on `/crux-extract-claims`. Workers persist the full
pre-bank payload; the workflow return is tiny acks only. Then main:

```
python .claude/skills/claim-extractor/scripts/merge_extract.py \
  --shards "$RUN/shards/extract" --run "$RUN" \
  --papers "$RUN/extract_papers.json" --cleaned_jsons "$RUN/cleaned_jsons"
```

Omit `shards_dir` only for tiny debug runs (legacy: full `results[]` returned,
then `write_claims.py --workflow_result`).

Extract args are a path **manifest** only — `{ papers: [{ paper_id, text_path }] }`
— never full page JSON. Workers read each `text_path`.

**Resume (do not trust bare harness hints):** after a pause/interrupt, relaunch
the workflow with the **same full args** as the original call **plus**
`resumeFromRunId`. Never resume with only `{ scriptPath, resumeFromRunId }`.
No Workflow tool: relaunch only the papers with no shard yet.

**Fan-out:** one worker per paper. Launch the full set in **one** workflow
call. Split only if the user asks or a run fails/truncates.

Prompt: `prompts/claim-extractor.md`. Optional tools: `prompts/web-scout.md`,
`prompts/literature-map.md`.

## Model and effort

After kickoff, before `/crux-extract-claims`, use the recorded `model_effort`.
If the user is unsure, default to **Eco**.

1. **Eco** *(default)* — worker `sonnet` / `medium` (extract; optional tools too)
2. **Intensive** — `/crux-extract-claims` `sonnet` / `medium`; web scout
   `opus` / `high`; literature map `sonnet` / `medium`
3. **Inherit main** — omit `model` / `effort`
4. **Custom** — user specifies

Model names are Claude Code's. On Codex or Cursor use the host's own models:
`sonnet` → its standard model, `opus` → its most capable. Keep the named
effort, or the nearest one the host offers.

Scripts ignore model/effort.

## Run dir

Default layout: create **`.crux_run/<name>/`** under the working directory,
copy or link the user’s sources into `<run>/input/`, and write artifacts under
that run.

- User already points at an existing `.crux_run/<name>/` → use it; do not nest.
- User names a loose folder of files → create `.crux_run/<name>/`, copy/link
  into `input/`, continue.
- User only names a study name / empty destination → create
  `.crux_run/<name>/input/` and wait for / accept files.
- **Cowork:** treat the attached **output** folder as the run dir; copy/link
  from the attached **source** folder into that run’s `input/`.

You create: `input/`, `cleaned_jsons/`, `claims.jsonl`, shards as needed.

## Sources → claims

1. Ensure `<run>/input/` has the user’s files.
2. **Optional — web scout** (only if the user asked): run per Tools; invoke
   `crux-report` for `01_web_scout.pdf`. May overlap step 3; merge fetched
   rows into the same `cleaned_jsons/`.
3. **Convert in parallel** (do not serialize these):
   - **PDF:** start `pdf_to_text.py --pdfs <run>/input --out <run>/cleaned_jsons`
     in the background when PDFs are present.
   - **Other types** (docx/pptx/html/md/txt/epub/…): no stock converter — while
     PDFs run, convert those files yourself into the same cleaned-source schema
     (or skip unsupported and say so). Keep `index.json` in sync as each batch
     lands; avoid stomping PDF rows.
4. When cleaned sources are ready:
   `index_to_papers.py` → `/crux-extract-claims` with
   `shards_dir=<run>/shards/extract` → `merge_extract.py` → `claims.jsonl` +
   `gists.json`. Then invoke `crux-report` for `02_claims.pdf` (include each
   paper's **gist**) **before** summarizing claims in chat.
   (Legacy: save full `extract_claims_result.json` → `write_claims.py`.)
5. Unless the user only wanted extraction, follow the sibling
   [`.claude/skills/crux/SKILL.md`](../crux/SKILL.md) (the loop, from CRUX).
   If that file is missing, stop. If `/crux` loaded a different path (often
   `~/.claude/skills/crux`), ignore that body and follow the sibling file.

## Optional tools (only when asked)

| Tool | You run it to… |
| --- | --- |
| **Web scout** | Scout subagent follows [prompts/web-scout.md](prompts/web-scout.md); main approves URLs; `scout_urls.py` → `web_to_text.py`. Main never searches or fetches the web itself. May run **concurrently** with local PDF/other conversion. Then invoke `crux-report` for `01_web_scout.pdf`. Suggested: `opus` / `high` |
| **Literature map** | Follow [prompts/literature-map.md](prompts/literature-map.md); write `<run>/literature_map.json`. Skim only — do **not** paste into propose/critique/revise. Then invoke `crux-report` for `literature_map.pdf`. Suggested: `sonnet` / `medium` |

## Invariants

- Schema-valid `cleaned_jsons/` before `/crux-extract-claims`.
- Ids + `source` only from `write_claims.py`.
- Kinds: `scripts/lib/kinds.py` (keep `/crux-extract-claims` enum in sync).
- Optional tools are **not** core — run only when the user asks.
- Extract `papers[]` is ids+paths only.
- **Resume** (Workflow tool): full original args + `resumeFromRunId` — never
  bare `scriptPath`. No Workflow tool: relaunch only the units with no shard yet.
- Always pause on hard errors or before any web tool.
