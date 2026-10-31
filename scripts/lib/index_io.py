"""Shared cleaned_jsons/index.json helpers for converters."""

from __future__ import annotations

import json
from pathlib import Path


def load_index(out_dir: Path) -> dict:
    path = out_dir / 'index.json'
    if not path.exists():
        return {'papers': []}
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or not isinstance(data.get('papers'), list):
        raise ValueError(f'{path}: expected object with papers[]')
    return data


def upsert_index(out_dir: Path, entries: list[dict]) -> Path:
    """Merge entries into cleaned_jsons/index.json by paper_id (or source path/url)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index = load_index(out_dir)
    by_key: dict[str, dict] = {}
    for item in index['papers']:
        if not isinstance(item, dict):
            continue
        key = item.get('paper_id') or item.get('source_url') or item.get('source_pdf')
        if isinstance(key, str) and key:
            by_key[key] = item
    for entry in entries:
        key = entry.get('paper_id') or entry.get('source_url') or entry.get('source_pdf')
        if isinstance(key, str) and key:
            by_key[key] = entry
    path = out_dir / 'index.json'
    path.write_text(
        json.dumps({'papers': list(by_key.values())}, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    return path
