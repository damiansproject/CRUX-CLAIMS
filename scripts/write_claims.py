#!/usr/bin/env python3
"""Write claims.jsonl from /crux-extract-claims output.

Assigns unique claim ids and attaches origin + source_quality. Quality comes
from /crux-extract-claims bibliographic cues (venue / source_type /
suggested_quality) when present, else from each source's cleaned_jsons/*.json
(pdf_to_text / web_to_text). Local PDFs no longer stay stuck at a flat 0.7 when
the extractor can read the journal masthead.

Ids: clm_<paper_id>_<nnnn>. Use --append to add into an existing claims.jsonl
(gap fulfill / extra sources) without wiping prior rows. Also writes gists.json
(paper-level gist + title + claim_count) for seed packing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent  # scripts/
for p in (_SCRIPT_DIR, _SCRIPT_DIR / 'lib'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from kinds import ALLOWED_KINDS  # noqa: E402
from source_quality import suggest_source_quality  # noqa: E402


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(f'{path}: expected JSON object')
    return data


def load_claims(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding='utf-8-sig') as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not isinstance(row.get('id'), str):
                raise ValueError(f'{path}:{line_no}: bad claim row')
            rows.append(row)
    return rows


def next_index(existing: list[dict], paper_id: str) -> int:
    prefix = f'clm_{paper_id}_'
    highest = 0
    for row in existing:
        cid = row.get('id')
        if isinstance(cid, str) and cid.startswith(prefix):
            suffix = cid[len(prefix) :]
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return highest + 1


def _fields_from_text(text_path: Path | None) -> dict:
    """Load origin/type/url/venue/title/quality from cleaned_jsons/*.json."""
    if text_path is None or not text_path.exists():
        return {
            'origin': 'pdf',
            'source_type': 'pdf',
            'url': None,
            'venue': None,
            'title': None,
            'base_override': None,
            'base_rationale': None,
        }
    data = load_json(text_path)
    origin = data.get('origin') if isinstance(data.get('origin'), str) else 'pdf'
    base_override = data.get('source_quality')
    if not isinstance(base_override, (int, float)) or isinstance(base_override, bool):
        base_override = None
    return {
        'origin': origin,
        'source_type': (
            data.get('source_type') if isinstance(data.get('source_type'), str) else origin
        ),
        'url': data.get('source_url') if isinstance(data.get('source_url'), str) else None,
        'venue': data.get('venue') if isinstance(data.get('venue'), str) else None,
        'title': data.get('title') if isinstance(data.get('title'), str) else None,
        'base_override': base_override,
        'base_rationale': (
            data.get('quality_rationale')
            if isinstance(data.get('quality_rationale'), str)
            else None
        ),
    }


def _merge_extractor_cues(fields: dict, extractor: dict) -> dict:
    """Overlay extractor venue/type/title onto cleaned_json fields."""
    ext_venue = extractor.get('venue') if isinstance(extractor.get('venue'), str) else None
    ext_type = (
        extractor.get('source_type')
        if isinstance(extractor.get('source_type'), str)
        else None
    )
    ext_title = extractor.get('title') if isinstance(extractor.get('title'), str) else None
    venue = fields['venue']
    source_type = fields['source_type']
    title = fields['title']
    if ext_venue:
        venue = ext_venue.strip() or venue
    if ext_type:
        source_type = ext_type
    if ext_title:
        title = ext_title.strip() or title
    return {
        **fields,
        'venue': venue,
        'source_type': source_type,
        'title': title,
        'ext_venue': ext_venue,
        'ext_type': ext_type,
        'ext_quality': (
            extractor.get('suggested_quality')
            if isinstance(extractor.get('suggested_quality'), (int, float))
            and not isinstance(extractor.get('suggested_quality'), bool)
            else None
        ),
        'ext_rationale': (
            extractor.get('quality_rationale')
            if isinstance(extractor.get('quality_rationale'), str)
            else None
        ),
    }


def _quality_override(fields: dict) -> tuple[float | None, str | None]:
    """Choose quality override; drop flat pdf 0.7 when extractor gave venue/type."""
    ext_quality = fields['ext_quality']
    base_override = fields['base_override']
    base_rationale = fields['base_rationale']
    override = float(ext_quality) if ext_quality is not None else (
        float(base_override) if base_override is not None else None
    )
    # If extractor only gave venue/type, ignore a flat pdf 0.7 on the input file
    # so suggest_source_quality can use venue/type instead.
    if ext_quality is None and (
        fields['ext_venue'] or (fields['ext_type'] and fields['ext_type'] != 'pdf')
    ):
        if base_rationale in (None, 'type:pdf') or (
            isinstance(base_override, (int, float)) and abs(float(base_override) - 0.7) < 1e-9
        ):
            override = None
    override_label = fields['ext_rationale'] if ext_quality is not None else (
        base_rationale if override is not None else None
    )
    return override, override_label


def meta_from_text(text_path: Path | None, extractor: dict | None = None) -> dict:
    """Build origin + source_quality for a paper.

    Priority for quality:
      1. extractor suggested_quality (from /crux-extract-claims)
      2. extractor venue / source_type via suggest_source_quality
      3. fields already on cleaned_jsons/*.json (web_to_text / pdf_to_text)
      4. flat type default (pdf → 0.7)
    """
    extractor = extractor if isinstance(extractor, dict) else {}
    fields = _merge_extractor_cues(_fields_from_text(text_path), extractor)
    override, override_label = _quality_override(fields)
    score, rationale = suggest_source_quality(
        origin=fields['origin'],
        url=fields['url'],
        venue=fields['venue'],
        source_type=fields['source_type'],
        override=override,
        override_label=override_label,
    )
    return {
        'origin': fields['origin'],
        'source_quality': score,
        'source': {
            'type': fields['source_type'],
            'url': fields['url'],
            'venue': fields['venue'],
            'title': fields['title'],
            'quality_rationale': rationale,
        },
    }


def build_claim_rows(
    workflow: dict,
    *,
    input_dir: Path | None,
    existing: list[dict],
) -> tuple[list[dict], dict]:
    rows: list[dict] = []
    per_paper: dict[str, int] = {}
    empty: list[str] = []
    skipped = 0
    truncated = 0

    max_claims = workflow.get('max_claims_per_paper')
    if max_claims is not None and (
        not isinstance(max_claims, int) or isinstance(max_claims, bool) or max_claims < 1
    ):
        raise ValueError('max_claims_per_paper must be a positive integer when set')

    # Optional map paper_id → text_path from workflow papers list if present
    text_paths: dict[str, Path] = {}
    if isinstance(workflow.get('papers'), list):
        for p in workflow['papers']:
            if isinstance(p, dict) and isinstance(p.get('paper_id'), str) and isinstance(p.get('text_path'), str):
                text_paths[p['paper_id']] = Path(p['text_path'])

    for result in workflow.get('results') or []:
        if not isinstance(result, dict):
            skipped += 1
            continue
        paper_id = result.get('paper_id')
        if not isinstance(paper_id, str) or not paper_id or any(ch in paper_id for ch in '"\\{}'):
            skipped += 1
            continue

        claims = result.get('claims')
        if not isinstance(claims, list):
            per_paper[paper_id] = 0
            empty.append(paper_id)
            continue
        if max_claims is not None and len(claims) > max_claims:
            truncated += len(claims) - max_claims
            claims = claims[:max_claims]

        text_path = text_paths.get(paper_id)
        if text_path is None and input_dir is not None:
            candidate = input_dir / f'{paper_id}.json'
            if candidate.exists():
                text_path = candidate
        meta = meta_from_text(text_path, extractor=result)

        idx = next_index(existing + rows, paper_id)
        count = 0
        for claim in claims:
            if not isinstance(claim, dict):
                skipped += 1
                continue
            kind = claim.get('kind')
            statement = claim.get('statement')
            quotes = claim.get('quotes')
            if kind not in ALLOWED_KINDS or not isinstance(statement, str) or not statement.strip():
                skipped += 1
                continue
            if not isinstance(quotes, list) or not quotes:
                skipped += 1
                continue
            rows.append(
                {
                    'id': f'clm_{paper_id}_{idx:04d}',
                    'paper_id': paper_id,
                    'origin': meta['origin'],
                    'source_quality': meta['source_quality'],
                    'source': meta['source'],
                    'kind': kind,
                    'statement': statement.strip(),
                    'quotes': quotes,
                }
            )
            idx += 1
            count += 1
        per_paper[paper_id] = count
        if count == 0:
            empty.append(paper_id)

    workflow_empty = workflow.get('empty') if isinstance(workflow.get('empty'), list) else []
    summary = {
        'papers': len(per_paper),
        'claims': len(rows),
        'skipped_invalid': skipped,
        'truncated_to_cap': truncated,
        'empty': sorted(set(empty) | {e for e in workflow_empty if isinstance(e, str)}),
        'failed': workflow.get('failed') if isinstance(workflow.get('failed'), list) else [],
        'claims_per_paper': per_paper,
        'model': workflow.get('model'),
        'effort': workflow.get('effort'),
        'kinds': workflow.get('kinds'),
        'max_claims_per_paper': max_claims,
    }
    return rows, summary


def _gist_text(result: dict) -> str | None:
    raw = result.get('gist')
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def persist_gists(
    *,
    results: list,
    per_paper: dict[str, int],
    cleaned_dir: Path | None,
    gists_path: Path,
    append: bool,
) -> None:
    """Stamp extractor gists onto cleaned JSON + index, and write gists.json for packing."""
    incoming: dict[str, dict] = {}
    for result in results:
        if not isinstance(result, dict):
            continue
        paper_id = result.get('paper_id')
        if not isinstance(paper_id, str) or not paper_id:
            continue
        title = result.get('title') if isinstance(result.get('title'), str) else None
        incoming[paper_id] = {
            'paper_id': paper_id,
            'title': title.strip() if isinstance(title, str) and title.strip() else None,
            'gist': _gist_text(result),
            'claim_count': per_paper.get(paper_id, 0),
        }

    existing: dict[str, dict] = {}
    if append and gists_path.exists():
        data = json.loads(gists_path.read_text(encoding='utf-8-sig'))
        papers = data.get('papers') if isinstance(data, dict) else None
        if isinstance(papers, list):
            for row in papers:
                if isinstance(row, dict) and isinstance(row.get('paper_id'), str):
                    existing[row['paper_id']] = row
    existing.update(incoming)
    gists_path.parent.mkdir(parents=True, exist_ok=True)
    gists_path.write_text(
        json.dumps({'papers': list(existing.values())}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    if cleaned_dir is None or not cleaned_dir.exists():
        return
    index_path = cleaned_dir / 'index.json'
    index_rows = []
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding='utf-8-sig'))
        index_rows = index.get('papers') if isinstance(index, dict) else None
        if not isinstance(index_rows, list):
            index_rows = []
    by_id = {
        row['paper_id']: row
        for row in index_rows
        if isinstance(row, dict) and isinstance(row.get('paper_id'), str)
    }
    for paper_id, gist_row in incoming.items():
        paper_path = cleaned_dir / f'{paper_id}.json'
        if paper_path.exists():
            paper = json.loads(paper_path.read_text(encoding='utf-8-sig'))
            if isinstance(paper, dict):
                if gist_row['gist']:
                    paper['gist'] = gist_row['gist']
                if gist_row['title'] and not paper.get('title'):
                    paper['title'] = gist_row['title']
                paper_path.write_text(
                    json.dumps(paper, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
                )
        row = by_id.get(paper_id)
        if row is None:
            continue
        if gist_row['gist']:
            row['gist'] = gist_row['gist']
        if gist_row['title'] and not row.get('title'):
            row['title'] = gist_row['title']
    if index_path.exists():
        index_path.write_text(
            json.dumps({'papers': index_rows}, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workflow_result', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='claims.jsonl')
    parser.add_argument(
        '--cleaned_jsons',
        type=Path,
        default=None,
        help='cleaned_jsons/ folder (reads origin/quality from <id>.json)',
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=None,
        help=argparse.SUPPRESS,  # deprecated alias for --cleaned_jsons
    )
    parser.add_argument(
        '--append',
        action='store_true',
        help='Append to existing claims.jsonl instead of overwriting',
    )
    parser.add_argument('--summary', type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        workflow = load_json(args.workflow_result)
        if 'results' not in workflow or not isinstance(workflow['results'], list):
            raise ValueError('workflow result must contain results[]')
        existing = load_claims(args.out) if args.append else []
        cleaned_dir = args.cleaned_jsons or args.input
        rows, summary = build_claim_rows(
            workflow, input_dir=cleaned_dir, existing=existing
        )
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    mode = 'a' if args.append else 'w'
    with args.out.open(mode, encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')

    summary_path = args.summary or args.out.with_name('extract_summary.json')
    summary['appended'] = bool(args.append)
    summary['total_claims_in_file'] = len(existing) + len(rows)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    gists_path = args.out.with_name('gists.json')
    persist_gists(
        results=workflow.get('results') or [],
        per_paper=summary.get('claims_per_paper') or {},
        cleaned_dir=cleaned_dir,
        gists_path=gists_path,
        append=bool(args.append),
    )

    print(
        f'wrote {args.out} ({summary["claims"]} new claims; '
        f'skipped={summary["skipped_invalid"]}; empty={len(summary["empty"])})'
    )
    print(f'wrote {summary_path}')
    print(f'wrote {gists_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
