#!/usr/bin/env python3
"""Write a urls file (and optional meta) from a web_scout JSON for web_to_text.

Main runs scout (agent) → saves scout.json → this script → urls.txt → web_to_text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scout', required=True, type=Path, help='Scout JSON output')
    parser.add_argument('--out_urls', required=True, type=Path, help='urls.txt for web_to_text')
    parser.add_argument(
        '--out_meta',
        type=Path,
        default=None,
        help='Optional JSON map url → { source_type, suggested_quality, title, why }',
    )
    parser.add_argument(
        '--max',
        type=int,
        default=8,
        help='Max candidates to keep (default 8)',
    )
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.scout.read_text(encoding='utf-8-sig'))
        if not isinstance(data, dict) or not isinstance(data.get('candidates'), list):
            raise ValueError('scout JSON must contain candidates[]')

        cands = [c for c in data['candidates'] if isinstance(c, dict) and isinstance(c.get('url'), str)]
        cands.sort(key=lambda c: c.get('priority') if isinstance(c.get('priority'), int) else 999)
        cands = cands[: max(1, args.max)]

        args.out_urls.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# scout: {data.get('query', '')}".strip(), '']
        for c in cands:
            lines.append(c['url'].strip())
        args.out_urls.write_text('\n'.join(lines) + '\n', encoding='utf-8')

        if args.out_meta is not None:
            meta = {}
            for c in cands:
                meta[c['url'].strip()] = {
                    'title': c.get('title'),
                    'why': c.get('why'),
                    'source_type': c.get('source_type'),
                    'suggested_quality': c.get('suggested_quality'),
                    'priority': c.get('priority'),
                }
            args.out_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

        print(f'wrote {args.out_urls} ({len(cands)} urls)')
        if args.out_meta:
            print(f'wrote {args.out_meta}')
        return 0
    except Exception as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
