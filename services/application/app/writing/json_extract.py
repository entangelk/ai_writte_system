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

Open-fence recovery (2026-08-23): when the output token ceiling cuts the
response, the model loses the *closing* fence first — the JSON body itself may
already be complete. ``gemma-4-31b-it`` fences habitually, so this shape showed
up on the very first deployed extract run. A leading fence whose remainder is
one complete JSON document is therefore unwrapped too. The remainder must parse
as a whole, so trailing prose still fails — this stays extraction, not salvage.
"""

from __future__ import annotations

import json
import re

# A whole-content markdown code fence: ``` optional-lang \n body \n ```.
_CODE_FENCE_RE = re.compile(
    r"^\s*```[ \t]*(?:[A-Za-z0-9_+-]+)?[ \t]*\r?\n([\s\S]*?)\r?\n?[ \t]*```\s*$"
)

# A leading fence that was never closed: ``` optional-lang \n <everything else>.
_OPEN_CODE_FENCE_RE = re.compile(
    r"^\s*```[ \t]*(?:[A-Za-z0-9_+-]+)?[ \t]*\r?\n([\s\S]+)$"
)


def strip_code_fence(content: str) -> str:
    """Return ``content`` with a single surrounding markdown code fence removed.

    Matches only when the whole content (ignoring surrounding whitespace) is one
    fenced block; returns content verbatim otherwise. No prose extraction, no
    partial salvage — the strict checks still see exactly the JSON the model
    produced, just unwrapped.

    A leading fence with no closing one (token-ceiling truncation) is unwrapped
    only when the remainder parses as one complete JSON document, so trailing
    prose keeps failing downstream checks.
    """
    match = _CODE_FENCE_RE.match(content)
    if match is not None:
        return match.group(1).strip()
    open_match = _OPEN_CODE_FENCE_RE.match(content)
    if open_match is not None:
        body = open_match.group(1).strip()
        try:
            json.loads(body)
        except ValueError:
            return content
        return body
    return content
