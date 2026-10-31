"""Shared claim-kind vocabulary for write_claims / workflows.

Keep in sync with CLAIM_KINDS in:
  .claude/skills/claim-extractor/workflows/crux-extract-claims.js
"""

from __future__ import annotations

CLAIM_KINDS: tuple[str, ...] = (
    'finding',
    'mechanism',
    'method',
    'limitation',
    'assumption',
    'problem',
    'other',
)

ALLOWED_KINDS = frozenset(CLAIM_KINDS)
