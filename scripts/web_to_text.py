#!/usr/bin/env python3
"""Fetch web URL(s) into cleaned_jsons/ as page-addressable JSON.

Same shape as pdf_to_text so /crux-extract-claims treats PDF and web alike.
Main gates which URLs are fetched (gap fulfill or web-only corpus).
Raw user files stay in <run>/input/; this writes <run>/cleaned_jsons/.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

_HERE = Path(__file__).resolve().parent
for p in (_HERE, _HERE / 'lib'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from index_io import upsert_index  # noqa: E402
from source_quality import domain_of, suggest_source_quality  # noqa: E402

USER_AGENT = 'CruxWebToText/1.0 (+https://github.com/damiansproject/CRUX)'


def normalize_url_key(url: str) -> str:
    return url.strip().rstrip('/')


def load_scout_meta(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(f'{path}: scout_meta must be a JSON object keyed by URL')
    out: dict[str, dict] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[normalize_url_key(key)] = value
    return out


def meta_for_url(meta: dict[str, dict], *urls: str) -> dict | None:
    for url in urls:
        if not url:
            continue
        hit = meta.get(normalize_url_key(url))
        if hit is not None:
            return hit
    return None


def resolve_fetch_options(
    *,
    url: str,
    final_url: str,
    scout_meta: dict[str, dict],
    default_source_type: str | None,
    default_venue: str | None,
    default_quality: float | None,
) -> dict:
    """Merge scout_meta + CLI defaults for one URL."""
    m = meta_for_url(scout_meta, url, final_url)
    source_type = default_source_type
    title_override = None
    quality_override = None
    quality_label = None

    if m:
        if isinstance(m.get('source_type'), str) and m['source_type'].strip():
            source_type = m['source_type'].strip()
        if isinstance(m.get('title'), str) and m['title'].strip():
            title_override = m['title'].strip()
        sq = m.get('suggested_quality')
        if isinstance(sq, (int, float)) and not isinstance(sq, bool):
            quality_override = float(sq)
            quality_label = 'scout suggested'

    if quality_override is None and default_quality is not None:
        quality_override = default_quality
        quality_label = 'cli override'

    # Do not stamp a company venue onto journal/news pages from a mixed scout list
    venue = default_venue
    if m and source_type and source_type != 'company' and venue:
        venue = None

    return {
        'source_type': source_type,
        'venue': venue,
        'title_override': title_override,
        'quality_override': quality_override,
        'quality_label': quality_label,
    }


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = 0
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in {'script', 'style', 'noscript', 'svg'}:
            self._skip += 1
        if t == 'title':
            self._in_title = True
        if t in {'p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'h4', 'tr', 'section', 'article'}:
            self._chunks.append('\n')

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in {'script', 'style', 'noscript', 'svg'} and self._skip:
            self._skip -= 1
        if t == 'title':
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title and not self.title:
            self.title = text
        self._chunks.append(text + ' ')

    def text(self) -> str:
        raw = ''.join(self._chunks)
        raw = html.unescape(raw)
        raw = re.sub(r'[ \t]+', ' ', raw)
        raw = re.sub(r'\n{3,}', '\n\n', raw)
        return raw.strip()


def source_id_for(url: str) -> str:
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    host = domain_of(url) or 'web'
    host = re.sub(r'[^a-zA-Z0-9]+', '_', host).strip('_').lower()[:24]
    return f'web_{host}_{digest}'


def fetch(url: str, timeout: float = 30.0) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — main-gated URLs
        charset = resp.headers.get_content_charset() or 'utf-8'
        body = resp.read().decode(charset, errors='replace')
        final_url = resp.geturl()
    return body, final_url


def html_to_record(
    url: str,
    body: str,
    *,
    source_type: str | None,
    venue: str | None,
    title_override: str | None,
    quality_override: float | None,
    quality_label: str | None = None,
) -> dict:
    parser = _TextExtractor()
    try:
        parser.feed(body)
        parser.close()
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', body)
        text = html.unescape(re.sub(r'\s+', ' ', text)).strip()
        title = title_override
    else:
        text = parser.text()
        title = title_override or parser.title

    if not text:
        raise ValueError('no extractable text')

    st = source_type or 'web'
    score, rationale = suggest_source_quality(
        origin='web',
        url=url,
        venue=venue,
        source_type=st,
        override=quality_override,
        override_label=quality_label,
    )
    paper_id = source_id_for(url)
    return {
        'paper_id': paper_id,
        'origin': 'web',
        'source_pdf': None,
        'source_url': url,
        'title': title,
        'venue': venue,
        'source_type': st,
        'source_quality': score,
        'quality_rationale': rationale,
        'backend': 'web_fetch',
        'page_count': 1,
        'pages': [{'page': 1, 'text': text}],
    }


def collect_urls(cli_urls: list[str], urls_file: Path | None) -> list[str]:
    urls = list(cli_urls)
    if urls_file is not None:
        for line in urls_file.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#'):
                urls.append(line)
    seen: set[str] = set()
    unique: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', action='append', default=[], help='URL to fetch (repeatable)')
    parser.add_argument(
        '--urls_file',
        type=Path,
        default=None,
        help='Text file: one URL per line (# comments ok)',
    )
    parser.add_argument(
        '--out',
        required=True,
        type=Path,
        help='cleaned_jsons/ folder for page JSON (e.g. <run>/cleaned_jsons)',
    )
    parser.add_argument(
        '--source_type',
        default=None,
        help='Default type when scout_meta lacks one: journal|preprint|blog|social|company|news|gov|web',
    )
    parser.add_argument(
        '--venue',
        default=None,
        help='Optional venue label default (avoid for mixed scout lists)',
    )
    parser.add_argument(
        '--source_quality',
        type=float,
        default=None,
        help='Flat 0–1 override only for URLs with no scout_meta suggested_quality',
    )
    parser.add_argument(
        '--scout_meta',
        type=Path,
        default=None,
        help='scout_meta.json from scout_urls.py — per-URL source_type + suggested_quality',
    )
    args = parser.parse_args(argv)

    try:
        scout_meta = load_scout_meta(args.scout_meta)
    except Exception as exc:
        print(f'error: scout_meta: {exc}', file=sys.stderr)
        return 1

    unique = collect_urls(args.url, args.urls_file)
    if not unique:
        print('error: pass --url and/or --urls_file', file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    entries = []
    for url in unique:
        try:
            body, final_url = fetch(url)
            opts = resolve_fetch_options(
                url=url,
                final_url=final_url,
                scout_meta=scout_meta,
                default_source_type=args.source_type,
                default_venue=args.venue,
                default_quality=args.source_quality,
            )
            record = html_to_record(
                final_url,
                body,
                source_type=opts['source_type'],
                venue=opts['venue'],
                title_override=opts['title_override'],
                quality_override=opts['quality_override'],
                quality_label=opts['quality_label'],
            )
            record['source_url'] = final_url
            out_path = args.out / f"{record['paper_id']}.json"
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            entries.append(
                {
                    'paper_id': record['paper_id'],
                    'origin': 'web',
                    'source_url': record['source_url'],
                    'text_path': str(out_path.resolve()),
                    'page_count': 1,
                    'source_quality': record['source_quality'],
                    'source_type': record.get('source_type'),
                    'backend': 'web_fetch',
                    'status': 'ok',
                }
            )
            print(
                f"ok: {url} -> {out_path.name} "
                f"(type={record.get('source_type')} quality={record['source_quality']})"
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
            print(f'error: {url}: {exc}', file=sys.stderr)
            entries.append(
                {
                    'source_url': url,
                    'origin': 'web',
                    'status': 'error',
                    'error': str(exc),
                }
            )

    index_path = upsert_index(args.out, entries)
    ok = sum(1 for e in entries if e.get('status') == 'ok')
    print(f'wrote {index_path} ({ok} web ok this run)')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
