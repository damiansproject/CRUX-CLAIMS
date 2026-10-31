# CRUX Claims

Converts papers and other sources into a bank of atomic scientific claims.

Every claim is evidence-traceable — a typed statement backed by verbatim
quotes with page locators, so anything built on it downstream can be walked
back to the exact sentence in the source. The claim bank is the input for other crux modules of the [CRUX suite](#the-crux-suite)

## Claim kinds

Every claim is exactly one of seven kinds:

| Kind | What it captures |
|------|------------------|
| `finding` | An empirical result — what was measured, in what system, under what intervention or condition |
| `mechanism` | How or why an effect happens |
| `method` | A technique, protocol, or tool the work uses or introduces |
| `limitation` | A stated boundary of the evidence or the approach |
| `assumption` | Something the work takes as given rather than shows |
| `problem` | An open problem or unmet need the source identifies |
| `other` | Evidence worth keeping that fits none of the above |

Claims also carries a short self-contained statement, one
or more verbatim quotes, and its locators.

## Works with

| Host        | Status      |
|-------------|-------------|
| [Claude Code](https://claude.com/claude-code) | Supported |
| Codex       | In progress |
| Claude Cowork | In progress |

## Requirements

- Python 3.12+ — the scripts use the standard library only
- [Docling](https://github.com/docling-project/docling) for PDF conversion:
  `pip install docling`

## Install

Clone it into the skills folder of a CRUX checkout, from inside the CRUX folder:

```bash
git clone https://github.com/damiansproject/CRUX-CLAIMS.git .claude/skills/claim-extractor
```

Install it only there, under exactly that name; the CRUX skills find each other
by these paths. The [CRUX quickstart](https://github.com/damiansproject/CRUX#quickstart)
installs the whole suite this way.

## Usage

Point the skill at your sources — PDFs, text files, saved pages:

```
/claim-extractor
```

Runs write under `.crux_run/`:

- `claims.jsonl` — the claim bank, one evidence-traceable claim per line
- `cleaned_jsons/` — converted sources
- `gists.json` — one-line paper gists

Then run `/crux` from [CRUX](https://github.com/damiansproject/CRUX) for hypotheses.

## Optional tools

- **Web scout** — ask for one to find more sources on the web; you approve each page.
- **Literature map** — agreements, contradictions, and gaps across the claim bank.

## The CRUX suite

| Repo | Stage |
|------|-------|
| **CRUX Claims** (this repo) | Sources → atomic claim bank |
| [CRUX](https://github.com/damiansproject/CRUX) | Hypothesis loop: propose → critique → revise → tournament |
| [CRUX Reports](https://github.com/damiansproject/CRUX-REPORTS) | PDF reports of a run |
| [CRUX Viewer](https://github.com/damiansproject/CRUX-VIEWER) | Claim quotes highlighted on the original sources |
