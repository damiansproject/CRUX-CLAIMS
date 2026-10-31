#!/usr/bin/env python3
"""Convert a folder of PDFs into page-addressable JSON under cleaned_jsons/.

User sources (PDFs, and later EPUB/etc.) live in <run>/input/. This script
reads PDFs from --pdfs (usually that folder) and writes cleaned page JSON to
--out (usually <run>/cleaned_jsons/).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault('TORCHDYNAMO_DISABLE', '1')
os.environ.setdefault('TORCH_COMPILE_DISABLE', '1')

_HERE = Path(__file__).resolve().parent
for p in (_HERE, _HERE / 'lib'):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from index_io import upsert_index  # noqa: E402
from source_quality import suggest_source_quality  # noqa: E402


def paper_id_for(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]  # same PDF, same id, wherever it sits
    stem = re.sub(r'[^a-zA-Z0-9]+', '_', path.stem).strip('_').lower()[:40]
    return f'{stem}_{digest}' if stem else f'pap_{digest}'


def build_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        PdfPipelineOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.accelerator_options = AcceleratorOptions(
        device=AcceleratorDevice.CPU,
    )
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def extract_pdf(path: Path, converter) -> dict:
    result = converter.convert(str(path))
    document = result.document
    page_count = len(document.pages) if document.pages else 0
    if page_count == 0:
        text = document.export_to_text() or document.export_to_markdown() or ''
        pages = [{'page': 1, 'text': text}] if text.strip() else []
    else:
        pages = []
        for page_no in range(1, page_count + 1):
            text = document.export_to_text(page_no=page_no) or ''
            text = text.replace('\n\n---\n\n', '\n\n').strip()
            pages.append({'page': page_no, 'text': text})

    paper_id = paper_id_for(path)
    score, rationale = suggest_source_quality(origin='pdf', source_type='pdf')
    return {
        'paper_id': paper_id,
        'origin': 'pdf',
        'source_pdf': str(path.resolve()),
        'source_url': None,
        'title': path.stem,
        'venue': None,
        'source_type': 'pdf',
        'source_quality': score,
        'quality_rationale': rationale,
        'backend': 'docling',
        'page_count': len(pages),
        'pages': pages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--pdfs',
        required=True,
        type=Path,
        help='Folder of source PDFs (typically <run>/input)',
    )
    parser.add_argument(
        '--out',
        required=True,
        type=Path,
        help='cleaned_jsons/ folder for page JSON (e.g. <run>/cleaned_jsons)',
    )
    args = parser.parse_args(argv)

    try:
        converter = build_converter()
    except ImportError as exc:  # pragma: no cover
        raise SystemExit('Docling is required. Install with: pip install docling') from exc

    if not args.pdfs.is_dir():
        print(f'error: not a directory: {args.pdfs}', file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(args.pdfs.glob('*.pdf')) + sorted(args.pdfs.glob('*.PDF'))
    seen: set[Path] = set()
    unique: list[Path] = []
    for pdf in pdfs:
        key = pdf.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(pdf)

    entries = []
    for pdf in unique:
        try:
            record = extract_pdf(pdf, converter)
        except Exception as exc:
            print(f'error: {pdf.name}: {exc}', file=sys.stderr)
            entries.append(
                {
                    'source_pdf': str(pdf.resolve()),
                    'origin': 'pdf',
                    'status': 'error',
                    'error': str(exc),
                }
            )
            continue

        out_path = args.out / f"{record['paper_id']}.json"
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        entries.append(
            {
                'paper_id': record['paper_id'],
                'origin': 'pdf',
                'source_pdf': record['source_pdf'],
                'text_path': str(out_path.resolve()),
                'page_count': record['page_count'],
                'source_quality': record['source_quality'],
                'backend': 'docling',
                'status': 'ok',
            }
        )
        print(f"ok: {pdf.name} -> {out_path.name} ({record['page_count']} pages)")

    index_path = upsert_index(args.out, entries)
    ok = sum(1 for p in entries if p.get('status') == 'ok')
    print(f'wrote {index_path} ({ok} pdf ok this run)')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
