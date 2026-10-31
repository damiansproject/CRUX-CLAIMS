"""Parallel extraction workers once shared fixed scratch filenames and merged another
paper's claims under their own paper_id (damiansproject/CRUX#39). These tests pin the
two defences: per-paper scratch names in the prompts, and a merge-time quote check.

Run: python -m pytest tests
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import merge_extract  # noqa: E402

PAGE_A = (
    'We introduce PaperTrail, a novel interface for tracing claims back to their '
    'sources. The interface renders each quote on the page it came from.'
)
PAGE_B = (
    'AlphaEvolve is an evolutionary coding agent. It pairs an LLM with automated '
    'evaluators to discover new algorithms.'
)


def _paper(cleaned: Path, paper_id: str, text: str) -> None:
    cleaned.mkdir(parents=True, exist_ok=True)
    (cleaned / f'{paper_id}.json').write_text(
        json.dumps({'paper_id': paper_id, 'title': paper_id, 'pages': [{'page': 1, 'text': text}]}),
        encoding='utf-8',
    )


def _shard(shards: Path, paper_id: str, quotes: list[str]) -> None:
    shards.mkdir(parents=True, exist_ok=True)
    claims = [
        {
            'kind': 'finding',
            'statement': f'claim {i}',
            'quotes': [{'text': quote, 'locator': {'paper': paper_id, 'page': 1}}],
        }
        for i, quote in enumerate(quotes)
    ]
    (shards / f'{paper_id}.json').write_text(
        json.dumps({'stage': 'extract', 'result': {'paper_id': paper_id, 'claims': claims, 'gist': 'g'}}),
        encoding='utf-8',
    )


def _merge(tmp_path: Path, with_sources: bool) -> int:
    argv = ['--shards', str(tmp_path / 'shards'), '--run', str(tmp_path / 'run'), '--aggregate_only']
    if with_sources:
        argv += ['--cleaned_jsons', str(tmp_path / 'cleaned')]
    return merge_extract.main(argv)


def test_refuses_shard_whose_quotes_come_from_another_paper(tmp_path, capsys):
    _paper(tmp_path / 'cleaned', 'A', PAGE_A)
    _paper(tmp_path / 'cleaned', 'B', PAGE_B)
    # Worker A read B's scratch file: B's quotes, stamped paper_id A.
    _shard(tmp_path / 'shards', 'A', ['AlphaEvolve is an evolutionary coding agent.', 'discover new algorithms'])
    _shard(tmp_path / 'shards', 'B', ['AlphaEvolve is an evolutionary coding agent.'])

    assert _merge(tmp_path, with_sources=True) == 1
    err = capsys.readouterr().err
    assert 'A' in err and '0 of 2' in err
    assert not (tmp_path / 'run' / 'extract_claims_result.json').exists()


def test_accepts_quotes_that_differ_only_in_whitespace_and_case(tmp_path):
    _paper(tmp_path / 'cleaned', 'A', PAGE_A)
    _shard(tmp_path / 'shards', 'A', ['we introduce\n  PaperTrail, a novel   interface'])

    assert _merge(tmp_path, with_sources=True) == 0
    assert (tmp_path / 'run' / 'extract_claims_result.json').exists()


def test_accepts_quotes_that_omit_pdf_conversion_artifacts(tmp_path):
    # Real pages from the CRUX-EVAL jacobian and riemann sets. Conversion leaves a
    # private-use glyph where a ligature was ("a  rmative"), a control character at a
    # line-break hyphen ("asso\x02ciated"), and a superscript on its own line ("κ\n∗").
    page = 'Hubbers has an a  rmative answer. The zeros asso\x02ciated to κ\n∗ ≥ 0.40.'
    _paper(tmp_path / 'cleaned', 'A', page)
    _shard(
        tmp_path / 'shards',
        'A',
        ['has an a  rmative answer', 'The zeros associated to', 'κ∗ ≥ 0.40'],
    )

    assert _merge(tmp_path, with_sources=True) == 0
    assert (tmp_path / 'run' / 'extract_claims_result.json').exists()


def test_still_refuses_another_papers_quotes_after_dropping_artifacts(tmp_path, capsys):
    _paper(tmp_path / 'cleaned', 'A', 'An a  rmative answer for n = 3.')
    _shard(tmp_path / 'shards', 'A', ['AlphaEvolve is an evolutionary coding agent.', 'discover new algorithms'])

    assert _merge(tmp_path, with_sources=True) == 1
    assert '0 of 2' in capsys.readouterr().err


def test_guard_needs_cleaned_jsons(tmp_path):
    _shard(tmp_path / 'shards', 'A', ['AlphaEvolve is an evolutionary coding agent.'])

    assert _merge(tmp_path, with_sources=False) == 0


@pytest.mark.parametrize(
    'path, needle',
    [
        ('workflows/crux-extract-claims.js', 'use exactly ${textScratch}'),
        ('prompts/claim-extractor.md', 'scratch file'),
    ],
)
def test_extraction_prompts_name_scratch_files_by_paper_id(path, needle):
    text = (ROOT / path).read_text(encoding='utf-8')
    if path.endswith('.js'):
        text = text.split('async function extractWork', 1)[1].split('async function extractWriteShard', 1)[0]
    else:
        text = text.split('## Rules', 1)[1]
    assert needle in text
