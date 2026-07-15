"""Phase 5.1 Writing prompt assembly.

Formats the verified ``ContextPackage`` and the ``WritingRequest`` into a single
Gateway chat request. The master system prompt is the local-model variant of
``writing_agent_prompt.md`` §6.1/§17.1: ContextPackage is the only project
memory, do_not_use overrides everything, candidate context is uncertain, output
is plain prose (owner Q2 — no JSON in slice 1).
"""

from __future__ import annotations

from services.application.app.context_search.models import (
    ContextItem,
    ContextItemStatus,
    ContextPackage,
)
from services.application.app.writing.context_pointer import (
    context_pointer_of,
    pointer_json,
)
from services.application.app.writing.models import (
    WritingBrief,
    WritingRequest,
)
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
    package: ContextPackage, *, include_pointers: bool = False
) -> str:
    """Compact context format (writing_agent_prompt.md §8.1). do_not_use and
    constraints come first (§8.2 hierarchy).

    ``include_pointers`` prefixes each item with its stable ContextPointer so the
    report extractor can cite the item it used (stable-pointer brief D2=A). Only
    that one turn opts in: the generation and revise prompts produce prose, not
    pointers, so their format stays unchanged (contract 3).
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
    if package.macro_items:
        sections.append(
            "<macro_context>\n"
            + "\n".join(
                _format_item(item, package, include_pointers)
                for item in package.macro_items
            )
            + "\n</macro_context>"
        )
    if package.micro_evidence:
        sections.append(
            "<micro_evidence>\n"
            + "\n".join(
                _format_item(item, package, include_pointers)
                for item in package.micro_evidence
            )
            + "\n</micro_evidence>"
        )
    body = "\n\n".join(sections) if sections else "(no project memory retrieved)"
    return f"<context_package project=\"{package.project_id}\">\n{body}\n</context_package>"


def _format_item(
    item: ContextItem, package: ContextPackage, include_pointers: bool
) -> str:
    # Candidate-origin items are labeled so the model never treats them as
    # approved knowledge (writing_agent_prompt.md §2.2).
    label = (
        "candidate (uncertain)"
        if item.status is ContextItemStatus.CANDIDATE
        else "canonical"
    )
    if not include_pointers:
        return f"- [{label}] {item.text}"
    pointer = context_pointer_of(item.pointer, project_id=package.project_id)
    return f"- [{label}] {pointer_json(pointer)} {item.text}"


def _format_brief(brief: WritingBrief) -> str:
    lines: list[str] = []
    if brief.tone:
        lines.append("Tone: " + ", ".join(brief.tone))
    for rule in brief.style_rules:
        lines.append(f"Style: {rule}")
    for pattern in brief.preferred_patterns:
        lines.append(f"Prefer: {pattern}")
    for pattern in brief.forbidden_patterns:
        lines.append(f"Avoid: {pattern}")
    return "\n".join(lines)


def build_writing_request(
    *,
    request: WritingRequest,
    package: ContextPackage,
    prompt_template: PromptTemplate,
    brief: WritingBrief | None = None,
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
    if brief is not None:
        brief_text = _format_brief(brief)
        if brief_text:
            parts += ["", "[WRITING BRIEF]", brief_text]
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
