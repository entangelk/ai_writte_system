"""Shared markdown code-fence extraction for strict terminal-JSON parsers.

A model occasionally wraps an otherwise-valid JSON object in a ``\\`\\`\\`json``
fence even when told to return raw JSON. That is a normal output-format
variation, not a model bug: the parser's job is to **extract** the JSON. These
helpers strip a whole-content code fence (any language tag) before ``json.loads``,
so the strict schema/enum/priority/evidence checks downstream apply unchanged —
**extraction, not contract relaxation** (no prose salvage, no ``{…}`` regex).

Shared by every strict terminal-JSON parser: ``gate_prompt.json_object``,
``report.parse_report``, ``compare_judge._json_object``,
``extractor._json_object``, ``planner._json_object`` and
``retrieval.parse_writing_retrieval_plan`` (the last four adopted it in
v1.6.86, closing the fence-strip tracked debt).
"""

from __future__ import annotations

import re

# A whole-content markdown code fence: ``` optional-lang \n body \n ```.
_CODE_FENCE_RE = re.compile(
    r"^\s*```[ \t]*(?:[A-Za-z0-9_+-]+)?[ \t]*\r?\n([\s\S]*?)\r?\n?[ \t]*```\s*$"
)


def strip_code_fence(content: str) -> str:
    """Return ``content`` with a single surrounding markdown code fence removed.

    Matches only when the whole content (ignoring surrounding whitespace) is one
    fenced block; returns content verbatim otherwise. No prose extraction, no
    partial salvage — the strict checks still see exactly the JSON the model
    produced, just unwrapped.
    """
    match = _CODE_FENCE_RE.match(content)
    if match is None:
        return content
    return match.group(1).strip()
