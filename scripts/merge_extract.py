#!/usr/bin/env python3
"""Merge extract shards into claims.jsonl via write_claims.py.

  python merge_extract.py --shards "$RUN/shards/extract" --run "$RUN" \\
    --papers "$RUN/extract_papers.json" --cleaned_jsons "$RUN/cleaned_jsons"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_WRITER = _SCRIPTS / 'write_claims.py'


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(f'{path}: expected JSON object')
    return data


def unwrap_shard(path: Path) -> dict:
    data = load_json(path)
    if 'result' in data and isinstance(data['result'], dict):
        declared = data.get('stage')
        if isinstance(declared, str) and declared and declared != 'extract':
            raise ValueError(f'{path}: envelope stage {declared!r} != \'extract\'')
        item = dict(data['result'])
    else:
        item = dict(data)
    stem = path.stem
    if stem.startswith('.') or stem.startswith('tmp-') or stem.startswith('.tmp-'):
        raise ValueError(f'{path}: refusing scratch/tmp shard name')
    item['paper_id'] = stem
    for key in ('paper_id', 'claims'):
        if key not in item:
            raise ValueError(f'{path}: missing required key {key!r}')
    return item


def load_shards(shards_dir: Path) -> list[dict]:
    if not shards_dir.is_dir():
        raise ValueError(f'shards dir not found: {shards_dir}')
    paths = sorted(
        p
        for p in shards_dir.glob('*.json')
        if p.is_file() and not p.name.startswith('.')
    )
    if not paths:
        raise ValueError(f'no *.json shards in {shards_dir}')
    return [unwrap_shard(p) for p in paths]


# Unicode categories PDF conversion emits that a faithful quote cannot reproduce:
# Cc control characters (often \x02 where a word was hyphenated across a line break)
# and Co private-use glyphs (U+E000.. where a font's ligature, such as "fi" or "ffi",
# had no Unicode mapping).
_CONVERSION_ARTIFACTS = ('Cc', 'Co')


def _squash(text: str) -> str:
    """Lower-cased text without conversion artifacts or any whitespace.

    Whitespace is dropped, not collapsed: conversion puts a superscript on its own
    line, so the page reads "κ ∗" where the quote reads "κ∗".
    """
    kept = [c for c in text if not c.isspace() and unicodedata.category(c) not in _CONVERSION_ARTIFACTS]
    return ''.join(kept).lower()


def quote_recovery(item: dict, cleaned_jsons: Path, sample: int = 20) -> tuple[int, int]:
    """Count how many of a shard's first `sample` quotes occur in its own paper's pages.

    Returns (found, checked); (0, 0) when the paper text is missing or the shard
    has no quotes, so the caller cannot judge.
    """
    source = cleaned_jsons / f"{item['paper_id']}.json"
    if not source.is_file():
        return (0, 0)
    pages = load_json(source).get('pages')
    if not isinstance(pages, list):
        return (0, 0)
    haystack = _squash(' '.join(str(p.get('text', '')) for p in pages if isinstance(p, dict)))
    quotes = [
        q['text']
        for c in item.get('claims') or []
        if isinstance(c, dict)
        for q in c.get('quotes') or []
        if isinstance(q, dict) and isinstance(q.get('text'), str) and q['text'].strip()
    ][:sample]
    return (sum(1 for q in quotes if _squash(q) in haystack), len(quotes))


def check_shards_against_sources(results: list[dict], cleaned_jsons: Path, min_ratio: float = 0.5) -> None:
    """Refuse shards whose quotes are not recoverable from their own paper.

    A worker that read another paper's scratch file returns a schema-valid shard
    stamped with its own paper_id (damiansproject/CRUX#39); its quotes then score
    ~0 against the right source, a correct shard ~1.
    """
    bad = []
    for item in results:
        found, checked = quote_recovery(item, cleaned_jsons)
        if checked and found / checked < min_ratio:
            bad.append(f"{item['paper_id']}: {found} of {checked} quotes found in its own text")
    if bad:
        raise ValueError('wrong-paper shards, re-run extraction for them: ' + '; '.join(bad))


def papers_from_path(path: Path | None) -> list[dict]:
    if path is None:
        return []
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if isinstance(data, dict):
        papers = data.get('papers')
        if isinstance(papers, list):
            return [p for p in papers if isinstance(p, dict)]
    raise ValueError(f'{path}: expected {{papers: [...]}}')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shards', required=True, type=Path)
    parser.add_argument('--run', type=Path, default=None)
    parser.add_argument('--workflow_result_out', type=Path, default=None)
    parser.add_argument('--out', type=Path, default=None)
    parser.add_argument('--research_goal', type=str, default=None)
    parser.add_argument('--model', type=str, default=None)
    parser.add_argument('--effort', type=str, default=None)
    parser.add_argument('--papers', type=Path, default=None)
    parser.add_argument('--cleaned_jsons', type=Path, default=None)
    parser.add_argument('--append', action='store_true')
    parser.add_argument('--max_claims_per_paper', type=int, default=None)
    parser.add_argument('--aggregate_only', action='store_true')
    args = parser.parse_args(argv)

    try:
        results = load_shards(args.shards)
        if args.cleaned_jsons is not None:
            check_shards_against_sources(results, args.cleaned_jsons)
        papers = papers_from_path(args.papers)
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1

    empty = [
        r['paper_id']
        for r in results
        if isinstance(r.get('paper_id'), str)
        and (not isinstance(r.get('claims'), list) or len(r['claims']) == 0)
    ]
    workflow: dict = {
        'model': args.model,
        'effort': args.effort,
        'results': results,
        'merged_from_shards': True,
        'shard_count': len(results),
        'empty': empty,
        'failed': [],
        'papers': papers,
    }
    if args.research_goal is not None:
        workflow['research_goal'] = args.research_goal
    if args.max_claims_per_paper is not None:
        workflow['max_claims_per_paper'] = args.max_claims_per_paper

    if args.workflow_result_out is not None:
        result_path = args.workflow_result_out
    elif args.run is not None:
        result_path = args.run / 'extract_claims_result.json'
    else:
        print('error: provide --run or --workflow_result_out', file=sys.stderr)
        return 1

    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(
        json.dumps(
            {
                'stage': 'extract',
                'shard_count': len(results),
                'workflow_result': str(result_path),
                'aggregate_only': bool(args.aggregate_only),
            },
            indent=2,
        )
    )
    if args.aggregate_only:
        return 0

    if args.out is not None:
        out = args.out
    elif args.run is not None:
        out = args.run / 'claims.jsonl'
    else:
        print('error: provide --run or --out to bank', file=sys.stderr)
        return 1

    cmd = [
        sys.executable,
        str(_WRITER),
        '--workflow_result',
        str(result_path),
        '--out',
        str(out),
    ]
    if args.append:
        cmd.append('--append')
    if args.cleaned_jsons is not None:
        cmd.extend(['--cleaned_jsons', str(args.cleaned_jsons)])
    return int(subprocess.run(cmd, check=False).returncode)


if __name__ == '__main__':
    raise SystemExit(main())
