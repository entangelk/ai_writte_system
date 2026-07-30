"""Phase 5.1 Writing prompt assembly.

Formats the verified ``ContextPackage`` and the ``WritingRequest`` into a single
Gateway chat request. The master system prompt is the local-model variant of
``writing_agent_prompt.md`` §6.1/§17.1: ContextPackage is the only project
memory, do_not_use overrides everything, candidate context is uncertain, output
is plain prose (owner Q2 — no JSON in slice 1).
"""

from __future__ import annotations

from services.application.app.context_search.item_render import render_context_item
from services.application.app.context_search.models import (
    ContextItem,
    ContextPackage,
)
from services.application.app.writing.models import WritingRequest
from services.llm_gateway.app.payload import ChatCompletionRequest, ChatMessage
from services.application.app.analysis.prompt_templates import PromptTemplate


WRITING_TASK_TYPE = "writing_generate"
WRITING_PROMPT_VERSION = "writing_continue_scene_v1"

# Local-model master prompt (writing_agent_prompt.md §6.1 condensed, §17.1
# compact). Plain-prose output for slice 1.
WRITING_CONTINUE_SCENE_TEMPLATE = """You are the Writing Agent in a personal writing AI system. You continue the current scene for the user.

You do not own memory, search databases, create source references, or decide canon. The ContextPackage is your ONLY project memory.

Rules, in priority order:
1. Obey do_not_use above everything else.
2. Obey constraints (POV, timeline) — they are hard, not stylistic.
3. Treat canonical context as hard truth and confirmed context as reliable.
4. Treat candidate context as uncertain — never state it as fact; use it only as possibility.
5. Do not invent project facts, characters, relationships, or events that are not in the ContextPackage.
6. Do not reveal future knowledge a POV character cannot know.
7. Do not resolve unresolved foreshadowing unless the instruction explicitly asks.
8. Continue naturally from the current draft excerpt; do not restart or summarize the scene.

Output the continuation prose only. No JSON, no headings, no meta commentary, no explanation."""


def format_context_package(
    package: ContextPackage, *, include_citation_numbers: bool = False
) -> str:
    """Compact context format (writing_agent_prompt.md §8.1). do_not_use and
    constraints come first (§8.2 hierarchy).

    ``include_citation_numbers`` numbers each item so the report extractor can
    cite the item it used by number (stable-pointer brief D2=A, rendered as a
    number since K-6=R-e). Only that one turn opts in: the generation and revise
    prompts produce prose, not citations, so their format stays unchanged
    (contract 3).
    """
    sections: list[str] = []
    if package.do_not_use:
        sections.append(
            "<do_not_use>\n"
            + "\n".join(f"- {rule}" for rule in package.do_not_use)
            + "\n</do_not_use>"
        )
    if package.constraints:
        sections.append(
            "<constraints>\n"
            + "\n".join(f"- {rule}" for rule in package.constraints)
            + "\n</constraints>"
        )
    if package.project_brief is not None:
        brief = package.project_brief
        brief_lines = [
            f"- premise: {brief.premise}" if brief.premise is not None else "",
            f"- genre: {brief.genre}" if brief.genre is not None else "",
            f"- tone: {brief.tone}" if brief.tone is not None else "",
            f"- pov: {brief.pov}" if brief.pov is not None else "",
            *(f"- constraint: {rule}" for rule in brief.constraints),
            *(f"- style rule: {rule}" for rule in brief.style_rules),
            *(f"- prefer: {pattern}" for pattern in brief.preferred_patterns),
            *(f"- avoid: {pattern}" for pattern in brief.forbidden_patterns),
            *(f"- style example: {example}" for example in brief.style_examples),
        ]
        populated = [line for line in brief_lines if line]
        sections.append(
            f'<project_brief authority="canonical" version="{brief.version_number}">\n'
            + ("\n".join(populated) if populated else "(empty)")
            + "\n</project_brief>"
        )
    # 인용 번호는 **macro → micro 순서로 1부터** 센다. `context_pointer.package_pointers`가
    # 같은 순서로 allowlist를 만들고 `report.parse_report`가 번호를 그 순서로 되돌리므로,
    # 두 순서가 갈라지면 claim의 근거가 조용히 다른 항목에 붙는다(실패가 아니라 오귀속).
    if package.macro_items:
        sections.append(
            "<macro_context>\n"
            + _format_items(package.macro_items, 1, include_citation_numbers)
            + "\n</macro_context>"
        )
    if package.micro_evidence:
        sections.append(
            "<micro_evidence>\n"
            + _format_items(
                package.micro_evidence,
                1 + len(package.macro_items),
                include_citation_numbers,
            )
            + "\n</micro_evidence>"
        )
    body = "\n\n".join(sections) if sections else "(no project memory retrieved)"
    return f"<context_package project=\"{package.project_id}\">\n{body}\n</context_package>"


def _format_items(
    items: tuple[ContextItem, ...], first_number: int, include_citation_numbers: bool
) -> str:
    return "\n".join(
        render_context_item(
            text=item.text,
            status=item.status,
            number=number if include_citation_numbers else None,
        )
        for number, item in enumerate(items, start=first_number)
    )


def build_writing_request(
    *,
    request: WritingRequest,
    package: ContextPackage,
    prompt_template: PromptTemplate,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
) -> ChatCompletionRequest:
    parts = [
        "[WRITING TASK]",
        f"task_type: {request.task_type.value}",
        "",
        "[INSTRUCTION]",
        request.instruction,
    ]
    parts += ["", "[CONTEXT PACKAGE]", format_context_package(package)]
    if request.draft_excerpt:
        parts += ["", "[CURRENT DRAFT EXCERPT]", request.draft_excerpt]
    parts += [
        "",
        "[FINAL INSTRUCTION]",
        "Continue the scene now. Use only the ContextPackage as project memory. "
        "Obey do_not_use. Preserve POV. Output the continuation prose only.",
    ]
    return ChatCompletionRequest(
        messages=(
            ChatMessage(role="system", content=prompt_template.template),
            ChatMessage(role="user", content="\n".join(parts)),
        ),
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        thinking=False,
    )
