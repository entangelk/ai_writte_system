"""컨텍스트 예산 트랙 R-a/R-c 측정 CLI (오퍼레이터 전용).

`report` 호출의 **실제 입력 토큰**을 컨텍스트 예산별로 재고, 그 배포의 **실제 창**과
비교해 `입력 + 출력상한 ≤ 창`(K-3 가드의 식)이 어디서 깨지는지 찾는다. 즉 오너 결정
(2026-07-30) "R-a는 기본 채택하되 R-c(창 확대)도 측정한 뒤 최종 결정"의 **측정** 단계다.

- **R-a**(report 전용 예산): 통과하는 가장 큰 예산이 곧 답의 상한이다.
- **R-c**(창 확대): 같은 스크립트를 창이 더 큰 배포(알파 `LLAMA_CTX_SIZE`)에서 돌리면
  현행 예산 8192가 그 창에서 통과하는지가 바로 나온다. **창은 상수로 박지 않고
  `/props`에서 읽으므로** 스크립트가 배포를 따라간다.

왜 실측이 필요한가: 지금까지의 `−1,914`는 항목 7,656을 **비율로 외삽**한 값이고, 어느
머신에도 **예산을 꽉 채우는 프로젝트가 없어서**(HANDOFF 착수 체크리스트 ⓓ) 아무도 그
경계를 실제로 본 적이 없다. `--seed`가 그 재현 데이터를 만든다.

계수는 **게이트웨이 가드와 같은 경로**를 쓴다(`LlamaCppProvider`의 `/apply-template` +
`/tokenize`, `add_special=True`). 추정(`len/1.7`)이 아니라 서버가 실제로 셀 값이며,
가드가 판정에 쓰는 바로 그 숫자다 — 사본을 만들면 두 숫자가 조용히 갈라진다.

쓰기는 `--seed`를 줄 때 **project/draft/version 생성 한 번**뿐이고, 그 밖에는 아무것도
쓰지 않는다(감사·색인·LLM 생성 없음 — `/tokenize`는 생성이 아니다).

application 컨테이너에서 돌린다(앱 코드 + Mongo + 게이트웨이 env를 한 자리에서 갖는
유일한 곳). llama 주소는 게이트웨이가 아니라 **모델 서버**를 직접 가리켜야 한다::

    docker compose run --rm --no-deps \\
        -v "$PWD/scripts:/app/scripts" -v "$PWD/services:/app/services" \\
        -e LLAMA_BASE_URL=http://<llama-host>:9080 \\
        application python scripts/report_budget_measure.py --seed
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TextIO

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.application.app.context_search.models import (
    ContextBudget,
    ContextSearchPurpose,
    ContextSearchRequest,
    CurrentPosition,
)
from services.application.app.writing.models import (
    WritingCandidate,
    WritingOutputType,
    WritingTaskType,
)
from services.application.app.writing.prompt import format_context_package
from services.application.app.writing.report import (
    TASK as REPORT_TASK,
    VERSION as REPORT_VERSION,
)
from services.llm_gateway.app.payload import build_llama_payload


_SEED_IDEMPOTENCY_KEY = "report-budget-measure-v1"
_DEFAULT_INSTRUCTION = "장면을 이어서 계속 쓰세요."
_DEFAULT_BUDGETS = "2048,4096,6144,8192"

# 합성 원고의 문장 풀. 실제 원고 밀도(베타 실측 **1.708 자/tok**)에 가까운 평범한 한국어
# 서술문이며, 스크립트가 생성한 코퍼스의 밀도를 결과에 함께 출력하므로 이 가정이 맞았는지
# 읽는 사람이 바로 확인할 수 있다(밀도가 크게 다르면 그 측정은 대표성이 없다).
_SENTENCES = (
    "민아는 플랫폼 끝에 서서 멀어지는 불빛을 오래 바라보았다.",
    "빗물이 고인 자리마다 간판의 붉은 글씨가 흔들리며 비쳤다.",
    "그는 주머니 속 편지를 꺼내지 못한 채 손끝만 몇 번 문질렀다.",
    "역무원이 마지막 열차의 지연을 알리는 방송을 두 번 반복했다.",
    "계단을 내려오는 발소리가 멎자 승강장은 다시 조용해졌다.",
    "그녀는 약속 시간이 지난 것을 알면서도 자리를 옮기지 않았다.",
    "차가운 바람이 코트 자락을 들추고 지나가며 종이 냄새를 흩었다.",
    "멀리서 다가오는 전조등이 젖은 선로 위에 긴 선을 그었다.",
)


def build_manuscript(*, target_chars: int, sentences_per_paragraph: int = 6) -> str:
    """결정론적 한국어 원고를 만든다(문단 = 빈 줄 구분).

    **제목(heading)을 넣지 않는다.** `_split_scene_blocks`는 마지막 heading 뒤의 문단
    전부를 "현재 장면"으로 잡으므로, heading이 없으면 원고 전체가 현재 장면 항목이 되어
    예산을 실제로 채운다 — 긴 한 장면을 쓰는 사용자가 만드는 바로 그 형태다.

    **번호를 붙이지 않는다.** 문단마다 `장면 12-3.` 같은 표지를 달면 문단은 구별되지만
    숫자가 토큰을 많이 먹어 코퍼스 밀도가 **1.54 자/tok**까지 내려간다(실측) — 실제 원고
    **1.708**보다 촘촘해서, 같은 글자 수가 더 많은 토큰이 되고 측정이 실제보다 비관적으로
    기운다. 대신 문장 풀을 회전시켜 문단을 구별한다.
    """
    if target_chars <= 0:
        raise ValueError("target_chars must be positive")
    paragraphs: list[str] = []
    total = 0
    index = 0
    while total < target_chars:
        paragraph = " ".join(
            _SENTENCES[(index * sentences_per_paragraph + position) % len(_SENTENCES)]
            for position in range(sentences_per_paragraph)
        )
        paragraphs.append(paragraph)
        total += len(paragraph) + 2
        index += 1
    return "\n\n".join(paragraphs)


@dataclass(frozen=True, slots=True)
class BudgetRow:
    budget: int
    items: int
    budget_excluded: int
    accounting_tokens: int
    package_tokens: int
    input_tokens: int
    output_cap: int
    window: int

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_cap

    @property
    def headroom(self) -> int:
        return self.window - self.total

    @property
    def verdict(self) -> str:
        # 가드와 같은 식이다(`client._window_decision`): 같거나 작으면 통과.
        return "PASS" if self.total <= self.window else "REJECT"


@dataclass(frozen=True, slots=True)
class Overheads:
    """예산과 무관하게 report 입력에 늘 실리는 몫. R-a 산식의 고정항이다."""

    system_tokens: int
    candidate_tokens: int
    wrapper_tokens: int

    @property
    def total(self) -> int:
        return self.system_tokens + self.candidate_tokens + self.wrapper_tokens


class TokenCounter:
    """가드와 같은 경로로 세는 계수기.

    프롬프트 계수는 `LlamaCppProvider`의 것을 **그대로 쓴다**. 세 가지(같은
    `chat_template_kwargs` · BOS 포함 · 템플릿 몫 포함)를 맞춰야 실제 `usage.prompt_tokens`와
    일치하는데(실측 delta 0), 그 규칙을 여기서 다시 적으면 가드와 이 스크립트가 서로 다른
    숫자를 말하게 된다 — 그러면 측정이 가드를 검증하지 못한다.
    """

    def __init__(self, provider: Any, transport: Any) -> None:
        self._provider = provider
        self._transport = transport

    async def window(self) -> int | None:
        await self._provider._probe_context_window()  # noqa: SLF001 — 가드와 같은 조회
        return self._provider._guard_window()  # noqa: SLF001

    async def prompt_tokens(self, payload: Mapping[str, Any]) -> int | None:
        return await self._provider._count_prompt_tokens(payload)  # noqa: SLF001

    async def text_tokens(self, text: str) -> int:
        """구성요소별 몫(system·후보 산문·컨텍스트)을 재는 raw 계수.

        채팅 템플릿을 적용하지 않으므로 프롬프트 총계와 **일치하지 않는다** — 그 차이가
        곧 `wrapper`(템플릿·JSON 포장 몫)이고, R-a 산식이 "약 150"으로 추정하던 항이다.
        """
        response = await self._transport.post_json(
            "/tokenize", {"content": text, "add_special": False}
        )
        if not 200 <= response.status_code < 300:
            raise RuntimeError(f"/tokenize failed: HTTP {response.status_code}")
        return len(response.body["tokens"])


def _build_counter(base_url: str, timeout_seconds: float) -> TokenCounter:
    from services.llm_gateway.app.client import LlamaCppProvider
    from services.llm_gateway.app.httpx_transport import HttpxJsonTransport

    transport = HttpxJsonTransport(
        base_url=base_url, timeout_seconds=timeout_seconds, trust_env=False,
    )
    provider = LlamaCppProvider(
        transport=transport,
        default_model=os.environ.get("LLAMA_DEFAULT_MODEL", "gemma-local"),
        # report 요청은 `thinking=False`를 명시하므로 이 기본값은 렌더링에 영향을 주지
        # 않는다. 게이트웨이 기본값과 같은 값을 두어 혼동을 없앤다.
        default_thinking=False,
        provider_name="llama-measure",
    )
    return TokenCounter(provider, transport)


def seed_saturating_project(core_sot: Any, *, name: str, target_chars: int
                            ) -> tuple[str, str, str]:
    """예산을 꽉 채우는 프로젝트를 만든다(이 스크립트의 유일한 쓰기).

    HTTP가 아니라 core SOT 서비스를 직접 부른다 — 앱 HTTP는 D8-3a 이후 401이고(추적 부채),
    여기서 필요한 것은 정본 저장뿐이라 인증 경계를 우회하는 것이 아니라 **지나지 않는다**.
    """
    project = core_sot.create_project(name=name)
    draft = core_sot.create_draft(project_id=project.id, title="예산 포화 측정용 장면")
    saved = core_sot.save_draft(
        project_id=project.id,
        draft_id=draft.id,
        raw_text=build_manuscript(target_chars=target_chars),
        idempotency_key=_SEED_IDEMPOTENCY_KEY,
    )
    return project.id, draft.id, saved.draft_version.id


async def _grow_candidate(counter: TokenCounter, *, target_tokens: int,
                          tolerance: float = 0.02) -> tuple[str, int]:
    """목표 토큰 수에 맞는 후보 산문을 만든다(실측으로 맞춘다, 추정하지 않는다).

    `long` 프리셋의 출력 상한(기본 4096)을 다 쓴 후보가 report의 최악 입력이므로, 문자
    수가 아니라 **토큰 수**를 목표로 잡는다. 목표를 **넘되 넘치지 않게** 수렴시킨다 —
    첫 근사에서 멈추면 10%까지 넘치고(실측 4,096 목표에 4,511), 그 초과분이 고정
    오버헤드로 들어가 통과 판정을 실제보다 좁게 만든다.
    """
    chars = int(target_tokens * 1.7)
    best: tuple[str, int] | None = None
    for _ in range(8):
        text = build_manuscript(target_chars=chars)
        tokens = await counter.text_tokens(text)
        if tokens >= target_tokens and (best is None or tokens < best[1]):
            best = (text, tokens)
        if target_tokens <= tokens <= target_tokens * (1 + tolerance):
            return text, tokens
        chars = max(1, int(chars * target_tokens / max(tokens, 1)))
        # 정확히 목표에 닿는 글자 수는 없을 수 있다(문단 단위로 늘어난다) — 아래에서
        # 다시 재며 목표를 넘는 가장 작은 것을 남긴다.
        chars += 40
    if best is None:  # pragma: no cover — 8회 안에 목표를 못 넘는 경우
        return text, tokens
    return best


async def measure(args: argparse.Namespace, *, out: TextIO) -> int:
    from scripts.diagnose_writing_gate import build_search_request, build_services
    from services.application.app.main import _default_core_sot_service

    base_url = args.llama_base_url or os.environ.get("LLAMA_BASE_URL")
    if not base_url:
        raise RuntimeError(
            "llama base URL is unknown; pass --llama-base-url or set LLAMA_BASE_URL "
            "(this must be the model server, not the gateway)"
        )
    counter = _build_counter(base_url, args.timeout)
    window = await counter.window()
    if window is None:
        raise RuntimeError(f"/props did not report n_ctx at {base_url}")

    core_sot = _default_core_sot_service()
    if args.seed:
        project_id, draft_id, version_id = seed_saturating_project(
            core_sot, name=args.seed_name, target_chars=args.seed_chars,
        )
        print(f"seeded project_id={project_id} draft_id={draft_id} "
              f"version_id={version_id}", file=out)
    else:
        project_id = args.project_id
        draft_id, version_id = args.current_position

    services = build_services()
    reporter = services.reporter
    output_cap = reporter.max_tokens
    template = reporter.templates.get_template(
        task_type=REPORT_TASK, version=REPORT_VERSION,
    )

    candidate_text, candidate_tokens = await _grow_candidate(
        counter, target_tokens=args.candidate_tokens,
    )
    system_tokens = await counter.text_tokens(template.template)
    corpus_chars = len(candidate_text)

    rows: list[BudgetRow] = []
    overheads: Overheads | None = None
    for budget in args.budgets:
        package = await services.context_search.build_context_package(
            build_search_request(
                project_id=project_id, instruction=args.instruction,
                query=args.query, max_tokens=budget,
                position=CurrentPosition(draft_id=draft_id, version_id=version_id),
            )
        )
        candidate = WritingCandidate(
            request_id="report-budget-measure",
            project_id=project_id,
            task_type=WritingTaskType.CONTINUE_SCENE,
            output_type=WritingOutputType.DRAFT_PATCH,
            text=candidate_text,
        )
        # 프로덕션 report 요청 그대로다 — 페이로드 조립을 사본으로 두면 프롬프트가 바뀔 때
        # 측정만 조용히 옛 형태를 잰다.
        request = reporter._request(candidate, package, template.template)  # noqa: SLF001
        payload = build_llama_payload(
            request,
            default_model=os.environ.get("LLAMA_DEFAULT_MODEL", "gemma-local"),
            default_thinking=False,
        )
        input_tokens = await counter.prompt_tokens(payload)
        if input_tokens is None:
            raise RuntimeError("prompt token count failed (see /apply-template, /tokenize)")
        rendered = format_context_package(package, include_citation_numbers=True)
        package_tokens = await counter.text_tokens(rendered)
        rows.append(BudgetRow(
            budget=budget,
            items=len(package.macro_items) + len(package.micro_evidence),
            budget_excluded=len(package.trace.budget_excluded),
            accounting_tokens=package.token_estimate_total,
            package_tokens=package_tokens,
            input_tokens=input_tokens,
            output_cap=output_cap,
            window=window,
        ))
        overheads = Overheads(
            system_tokens=system_tokens,
            candidate_tokens=candidate_tokens,
            wrapper_tokens=input_tokens - package_tokens - system_tokens - candidate_tokens,
        )

    assert overheads is not None  # budgets 는 비어 있을 수 없다(파서가 막는다)
    print(format_measurement(
        rows, overheads=overheads, window=window, output_cap=output_cap,
        project_id=project_id, llama_base_url=base_url,
        candidate_chars=corpus_chars,
    ), file=out)
    return 0


def format_measurement(rows: list[BudgetRow], *, overheads: Overheads, window: int,
                       output_cap: int, project_id: str, llama_base_url: str,
                       candidate_chars: int) -> str:
    lines = [
        "report 입력 예산 측정 (R-a / R-c)",
        "===================================",
        f"project_id: {project_id}",
        f"llama: {llama_base_url}",
        f"창(n_ctx, /props 실측): {window}",
        f"report 출력 상한(WRITING_REPORT_MAX_TOKENS): {output_cap}",
        "",
        "고정 오버헤드 (예산과 무관하게 늘 실린다)",
        f"  system 프롬프트: {overheads.system_tokens} tok",
        f"  후보 산문: {overheads.candidate_tokens} tok "
        f"({candidate_chars}자, 밀도 {candidate_chars / max(overheads.candidate_tokens, 1):.2f} 자/tok "
        f"— 시드 원고와 같은 생성기이므로 항목 밀도이기도 하다. 실제 원고 실측은 1.71)",
        f"  래퍼(채팅 템플릿 + JSON 포장): {overheads.wrapper_tokens} tok",
        f"  합계: {overheads.total} tok",
        "",
        "예산별",
        "  예산 | 항목 | 예산제외 | 회계 | 컨텍스트(실측) | 입력 | 입력+출력 | 창 여유 | 판정",
    ]
    for row in rows:
        lines.append(
            f"  {row.budget} | {row.items} | {row.budget_excluded} | "
            f"{row.accounting_tokens} | {row.package_tokens} | {row.input_tokens} | "
            f"{row.total} | {row.headroom:+} | {row.verdict}"
        )
    passing = [row for row in rows if row.verdict == "PASS"]
    lines += ["", "판정"]
    if not passing:
        lines.append("  통과하는 예산이 없다 — 이 창에서는 report가 어떤 예산으로도 거부된다.")
    else:
        best = max(passing, key=lambda row: row.budget)
        lines.append(f"  측정한 값 중 통과하는 최대 예산: {best.budget} (여유 {best.headroom:+})")
    allowance = window - output_cap - overheads.total
    lines.append(
        f"  R-a 산식(실측): 창 {window} − 출력상한 {output_cap} − 고정 {overheads.total} "
        f"= 컨텍스트에 쓸 수 있는 실제 토큰 {allowance}"
    )
    saturated = [row for row in rows if row.budget_excluded > 0]
    if saturated:
        row = saturated[0]
        ratio = row.accounting_tokens / max(row.package_tokens, 1)
        lines.append(
            f"  회계/실측 비율 {ratio:.2f} (예산 {row.budget}에서 실측) → "
            f"회계 단위 권장 예산 약 {int(allowance * ratio)}"
        )
    else:
        lines.append(
            "  ⚠ 어떤 예산에서도 예산 제외가 0건이다 — 프로젝트가 예산을 채우지 못했으므로 "
            "이 표는 경계를 보여주지 않는다. --seed-chars 를 늘려 다시 잰다."
        )
    return "\n".join(lines)


def _budgets(raw: str) -> list[int]:
    budgets = [int(part) for part in raw.split(",") if part.strip()]
    if not budgets:
        raise argparse.ArgumentTypeError("at least one budget is required")
    if any(budget <= 0 for budget in budgets):
        raise argparse.ArgumentTypeError("budgets must be positive")
    return budgets


class _PositionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if len(values) != 2:
            raise argparse.ArgumentError(self, "expected DRAFT_ID VERSION_ID")
        setattr(namespace, self.dest, (values[0], values[1]))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="report 입력 예산을 창 대비로 실측한다 (R-a/R-c)",
    )
    parser.add_argument("--seed", action="store_true",
                        help="예산을 꽉 채우는 프로젝트를 새로 만든다(유일한 쓰기)")
    parser.add_argument("--seed-chars", type=int, default=24000,
                        help="시드 원고의 목표 글자 수 (기본 24000)")
    parser.add_argument("--seed-name", default="report budget saturation probe")
    parser.add_argument("--project-id", default=None,
                        help="--seed 없이 기존 프로젝트를 잴 때")
    parser.add_argument("--current-position", nargs=2, action=_PositionAction,
                        metavar=("DRAFT_ID", "VERSION_ID"), default=None)
    parser.add_argument("--budgets", type=_budgets, default=_budgets(_DEFAULT_BUDGETS))
    parser.add_argument("--candidate-tokens", type=int, default=4096,
                        help="후보 산문의 목표 토큰 수 (기본 = long 출력 상한 4096)")
    parser.add_argument("--instruction", default=_DEFAULT_INSTRUCTION)
    parser.add_argument("--query", default=None)
    parser.add_argument("--llama-base-url", default=None,
                        help="모델 서버 주소(게이트웨이가 아니다). 기본값은 LLAMA_BASE_URL")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser


def main(argv: list[str] | None = None, *,
         run: Callable[[argparse.Namespace, TextIO], int] | None = None,
         out: TextIO | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if not args.seed and (args.project_id is None or args.current_position is None):
        parser.error("--seed 를 주거나 --project-id 와 --current-position 을 함께 준다")
    stream = out if out is not None else sys.stdout
    runner = run if run is not None else (lambda a, o: asyncio.run(measure(a, out=o)))
    return runner(args, stream)


if __name__ == "__main__":  # pragma: no cover — CLI entry point
    raise SystemExit(main())
