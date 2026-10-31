#!/usr/bin/env python3
"""Build extract papers manifest from cleaned_jsons/index.json (status=ok only).

Writes { "papers": [ {"paper_id", "text_path"}, ... ] } for /crux-extract-claims.
Writes with --out, or prints to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--index',
        type=Path,
        default=None,
        help='Path to cleaned_jsons/index.json',
    )
    parser.add_argument(
        '--cleaned_jsons',
        type=Path,
        default=None,
        help='cleaned_jsons/ folder (uses index.json inside)',
    )
    parser.add_argument(
        '--input',
        type=Path,
        default=None,
        help=argparse.SUPPRESS,  # deprecated alias for --cleaned_jsons
    )
    parser.add_argument(
        '--out',
        type=Path,
        default=None,
        help='Optional path to write papers JSON (else stdout)',
    )
    args = parser.parse_args(argv)

    cleaned = args.cleaned_jsons or args.input
    if args.index is not None:
        index_path = args.index
    elif cleaned is not None:
        index_path = cleaned / 'index.json'
    else:
        print('error: pass --index or --cleaned_jsons', file=sys.stderr)
        return 1

    try:
        data = json.loads(index_path.read_text(encoding='utf-8-sig'))
        if isinstance(data, dict):
            ents = data.get('papers')
            if ents is None:
                ents = data.get('entries')
        elif isinstance(data, list):
            ents = data
        else:
            raise ValueError('index must be object with papers[] or a list')
        if not isinstance(ents, list):
            raise ValueError('papers/entries must be an array')

        papers = []
        for e in ents:
            if not isinstance(e, dict) or e.get('status') != 'ok':
                continue
            pid = e.get('paper_id')
            tpath = e.get('text_path')
            if not isinstance(pid, str) or not isinstance(tpath, str):
                continue
            papers.append({'paper_id': pid, 'text_path': tpath.replace('\\', '/')})

        text = json.dumps({'papers': papers}, ensure_ascii=False, indent=2)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text + '\n', encoding='utf-8')
            print(f'wrote {args.out} ({len(papers)} papers)', file=sys.stderr)
        else:
            print(text)
        return 0
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
