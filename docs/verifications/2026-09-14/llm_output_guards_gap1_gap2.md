# LLM 출력 가드 보강(GAP-1 B+D · GAP-2) 독립 검증

## Subject metadata

- 날짜: 2026-09-14 · 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래") · 검증자: 독립 검증 세션(구현 세션과 다른 세션).
- 대상: 커밋 4건 — `09c002f`(GAP-2 빈 출력 가드) · `8f6682c`(GAP-1 B+D finish_reason 계약) · `8ce8e44`·`bfcf113`(기록·CHANGELOG). 검증 트리 `bfcf113`(고정, 전수·변이 전 구간 clean 확인).
- 정규 스펙 참조: 오너 결정 2026-09-14 B+D(브리프 옵션 표는 work_log 세션 3 §Decisions에 요약로 존재). **★ 주의: 결정이 계약 리터럴을 세웠으나 SoT/plans 어디에도 반영되지 않았다 — 아래 차단 C3.**

## Scope

- ★ B 가드(`WritingService.generate`의 `finish_reason != "stop"` 거부)가 살아있는 전파 체인 전체 — 게이트웨이가 값을 어디서 얻는지, 하드코딩·기본값이 없는지.
- ★ B 계약의 범위 해석 — 결정 문면 "산문 경로"와 구현 범위(WritingService.generate 국한)의 정합. 패턴 스윕 완결성.
- D 가드(repair 루프의 length 단락)와 그 "최신 결과 기준" 분기의 잠금.
- GAP-2 가드(빈 content 승격)와 "게이트웨이는 통과시키고 소비자가 거부한다" 계약 구조의 보존.
- 신규 회귀 셀 3개의 실질(양방향 변이), 작업자 보고 수치(변이 5종·13파일 400/187·fixture 전부 stop)의 재현.
- 조사 주장(gemma4 이식 출처·부채 4곳·게이트웨이 기존 가드 인벤토리)의 1차 소스 대조.

## Methodology

호스트 WSL2 · python3 3.12.3 · pytest 9.0.2 · `PYTHONPATH=.` · test-mongo `127.0.0.1:27020` rs-test **PRIMARY 직접 확인**(`docker ps` + `hello`, setName=rs-test · isWritablePrimary=True). 전수·집중 모두 고정 트리 `bfcf113`에서 실행(문서 커밋 뒤 — 검증 세션 전수 순서 규칙 준수).

- 집중: `python3 -m pytest tests/test_writing.py tests/test_writing_report.py -v`
- 광범위(작업자 "13파일"의 목록이 기록에 없어 **초집합 30파일**로 대체 재현): writing 전체 19파일 + 게이트웨이 provider 5파일 + 분석 파서 4파일 + `test_json_extract.py`·`test_gateway_capabilities.py` 등.
- 전수: `python3 -m pytest tests/ -q`(파일 캡처, EXIT 기록).
- 변이(프리플라이트 `git status --short` empty → python3 문자열 치환 → 집중 실행 → `git checkout -- <path>` 원복 → clean 확인; 트리가 clean·작업물 커밋 상태이므로 clean-tree 분기가 정확한 복원 수단): 아래 표.
- fixture grep: `grep -rn 'finish_reason=' tests/` 전수에서 `"stop"`·`"length"` 외 값 색출.
- D mid-loop 분기 동작 확인: 검증자 자작 인라인 스크립트(`WritingCandidateReportService.enrich`에 첫 출력 malformed+stop → repair 결과 malformed+length 공급, calls 수 측정 — §Reproduction에 전문).
- gemma4 대조: `git -C /mnt/d/devel/gemma4_12b show/git grep 485c4e2`(추가 작업 디렉터리).

## Findings

### 1. 가드 3종 실재·전파 체인 생존 — 성립

- GAP-2: `services/application/app/writing/service.py:115-126`(빈·공백만 content → `INVALID_RESPONSE` `ProviderError`, retryable=False). B: `service.py:127-139`(실제 finish_reason을 메시지에 실음). D: `services/application/app/writing/report.py:123-124` + 최신화 `report.py:136`.
- **finish_reason은 어디서도 지어내지 않는다**: llama 서버 `choice["finish_reason"]` 엄격 파싱(`services/llm_gateway/app/client.py:301`) → `GenerationResult`(client.py:316, 필드에 기본값 없음 — `provider.py:26`) → `/v1/generate` 응답에 상시 포함(`services/llm_gateway/app/main.py:286`) → 앱 provider가 엄격 파싱(`services/application/app/analysis/gateway_provider.py:124`) → `ObservedProvider`는 결과를 무손실 통과(`observability/llm_call_scope.py:250-289`) → `WritingService`(배선 `main.py:1029-1041`). **B 가드는 죽은 코드가 아니다.**
- 앱 HTTP 매핑: `INVALID_RESPONSE` → 502(`api/errors.py:343-364`). 잡 실패 사유 `PROVIDER_ERROR`(`generation_worker.py:183-192`). 재시도는 명시 API 호출로만(`mark_pending_for_retry`, 상한+쿨다운) — D의 "예측 가능한 실패에 예산을 안 태운다" 취지를 잡 층이 무너뜨리지 않는다.
- GAP-2의 계약 구조 보존: 게이트웨이의 "닫히지 않은 thought → 빈 문자열" 계약(`client.py:330-344`)과 그 변이 셀(`tests/test_llama_provider_client.py:130`)은 무변. 소비자 측 거부로 승격한 설명(`service.py:116-120` 주석)은 사실과 일치 — gate(잘리면 strict 파싱 실패로 fail-closed, `gate.py:79-87`)·revise(빈 replacement 거부, `revise.py:134-136`)·report(strict 파싱) 확인.

### 2. 조사 주장 대조 — 전부 1차 소스로 성립

- 게이트웨이 인벤토리: stream 거부·max_tokens 검증(`payload.py:44-51`) · K-3 창 가드(모델 호출 전 거부, `client.py:106` 영역, `/props` n_ctx 캐싱) · 빈 choices 거부(`client.py:290-291`) · usage 엄격(`_token_count`).
- gemma4 출처: `payload.py:3-4`의 인용 커밋 `485c4e2` 실재("Add RTX 3050 hybrid inference"). 그 커밋에 `payload.py` 파일은 없으나 **thinking 토글(`enable_thinking` chat_template_kwargs)은 `gateway/app/llama_client.py:105-108`에 실재** — "behavior adapted from … at commit" 문면대로 행위 수준 인용은 정확.
- 부채 4곳 라인 인용 정확: `extractor.py:142`영역 · `compare_judge.py:113`영역 · `identity_judge.py:109`영역 · `planner.py:119`영역 모두 동일 parse→1회 repair 패턴. **단 아래 H1 참조.**

### 3. 테스트·수치 재현

- 집중: **88 passed / 29 subtests**(test_writing.py 70 + test_writing_report.py 18) — 세션 3 기록 "69 passed(변이 전)"와 +1(truncated 셀)로 정합. 신규 셀 3개 기명 녹색.
- fixture 전수 grep: `finish_reason=` 리터럴 값은 전부 `"stop"`(신규 "length" 셀과 파라미터화 fake 제외) — "기존 경로 무변" 주장 성립.
- 광범위 초집합 30파일: **632 passed / 257 subtests · EXIT=0**.
- 전수: **3078 passed / 1 skipped / 4272 subtests · EXIT=0**(2014.17s). 기준선 3075/1/4272(세션 2) 대비 **+3 = 신규 셋의 정확히 몫**, subtests 무변.
- **★ 변이 보고 불일치**: 요약·CHANGELOG은 "변이 5종 기명 재실패(양방향)", work_log에는 **3종**(GAP-2 1 + B·D 2)만 기록돼 있고 어느 쪽도 5와 안 맞는다. over-strict 방향은 "기존 셀이 잠근다"는 서술만 있고 실행 기록이 없다. 검증자 재실행(6종, 아래 표)으로 **가드 실질은 양방향으로 성립** — 문제는 기록 정합성만(H2).

### 변이 표(검증자 전량 재실행 · 매 회 원복·clean 확인)

| # | 방향 | 적용 diff | 위치 | 재실패 셀 |
|---|---|---|---|---|
| M1 | under | `if not result.content.strip():` → `if False and not result.content.strip():` | service.py:115 | `test_empty_provider_output_is_rejected_as_provider_fault` (1 failed) |
| M2 | under | `if result.finish_reason != "stop":` → `if False and result.finish_reason != "stop":` | service.py:127 | `test_truncated_provider_output_is_rejected_as_provider_fault` (1) |
| M3 | under | `and result.finish_reason != "length"):` → `and True):` | report.py:124 | `test_truncated_first_output_skips_the_repair_loop` (1 — fake 소진 IndexError로 발화) |
| M4 | over | `if not result.content.strip():` → `if not result.content.strip() or result.content != result.content.strip():` | service.py:115 | `test_plain_prose_is_wrapped_into_candidate` (1) |
| M5 | over | `!= "stop"` → `!= "stop" or result.finish_reason == "stop"` | service.py:127 | `test_plain_prose_is_wrapped_into_candidate` (1) |
| M6 | over | `and result.finish_reason != "length"):` → `and result.finish_reason != "stop"):` | report.py:124 | `test_invalid_first_output_repairs_once` + `test_truncated_first_output_skips_the_repair_loop` (2) |
| M7 | 무잠금 증명 | `result = retry` 줄 삭제(최신 결과 갱신 제거) | report.py:136 | **0셀 — 18 passed 전원 초록** |

### 4. ★ B 가드의 범위 — 두 번째 산문 표면이 무가드 (차단 C1)

결정 문면은 "산문 경로에서 `stop` 외 종료 거부"(work_log 세션 3 브리프)이고 GAP-1 정의는 "`finish_reason`을 앱 **전체에서** 아무도 소비하지 않음"이다. 그러나 구현은 `WritingService.generate` 한 곳에만 가드를 달았고, **`WritingRevisionService.revise_metered`(`services/application/app/writing/revise.py:100-141`)가 같은 산문 생성 표면인데 finish_reason을 전혀 보지 않는다.** 빈 replacement(`revise.py:134`)·동일 replacement(`:137`)만 검사하고, `finish_reason=length`로 잘린 치환문은 그대로 원고에 splice(`:142-146`)돼 저장·반환된다(HTTP 노출: `routers/writing.py:861` · 측정 하네스: `per_stage_measure.py:229`). 잘린 개정문의 저장·과금이 "정상"으로 기록되는 것 — GAP-1 B가 막기로 한 정확히 그 "조용한 헛소리"가 개정 경로에 살아있다. GAP-2 스윕 때는 revise를 "이미 각자 거부하는 소비자"로 세면서 finish_reason 축에서는 세지 않은 과잉 좁은 스윕이다. `tests/test_writing_revise.py`에 finish_reason 셀 0건.

### 5. ★ D의 "최신 결과 기준" 분기 무잠금 (차단 C2)

코드 주석(`report.py:119-121`)과 결정 기록(work_log "repair 도중 잘리면 다음 repair 도 건너뛴다")이 명시하는 mid-loop 분기 — repair 결과가 length면 다음 repair를 건너뛴다 — 가 동작은 한다(검증자 실측: 첫 malformed+stop → repair1 malformed+length → **calls=2**로 종료). 그러나 신규 셀은 **첫 출력**이 length인 경우만 다루고, 그 메커니즘(`result = retry`, report.py:136)을 지워도 **M7에서 18셀 전원 초록** — 이 계약 분기를 잠그는 셀이 존재하지 않는다. 경계 행렬의 빈 칸이다.

### 6. ★ 정본 미반영 (차단 C3)

CLAUDE.md §1: 결정이 계약 리터럴·경계를 세우면 "canonical plan / schema에 구현과 함께 반영"한다. 이 결정은 세 개를 세웠다 — 빈 content → INVALID_RESPONSE(502) · `stop` 외 거부(실제 사유 메시지) · report repair의 length 단락. 반영된 곳: work_log·CHANGELOG뿐. `docs/system-contract-sot.md`(버전 로그 마지막 v1.8.69, 본문 :605는 게이트웨이 응답 필드 규정뿐) · `docs/plans/05-writing-generation-decisions.md`(finish_reason·빈 출력·GAP·2026-09-14 어떤 언급도 없음) · `docs/plans/05-writing-report-api-decisions.md`(:34 "1회 repair" — 코드는 `MAX_REPORT_REPAIRS=2`로 이미 갈린, 이번 슬라이스 이전 유래의 드리프트) 어디에도 없다. 스펙-침묳-코드-시행 상태 — 다음 검증자를 추측가로 만드는 자리다. 부차: `docs/product-overview.md:106` "잘렸는지는 아직 직접 관측되지 않는다" 문구가 낡았다(H5).

## Issues / Risks

### Blocking (계약 의무)

- **C1 — revise 산문 표면 무가드**: 위 §4. 처방 둘 중 하나는 오너 결정 — (a) B 가드를 `revise_metered`에 동일하게 확장(같은 `INVALID_RESPONSE` 분류 + 셀 1개), 또는 (b) B의 범위를 generate 국한으로 명시적으로 확정하고 revise를 트리거 붙은 부채로 기록. 어느 쪽이든 현재는 결정 문면과 구현 범위가 어긋난 채다.
- **C2 — mid-loop length 단락 무잠금**: 위 §5. 처방: 첫 malformed+stop → repair1 malformed+length 시나리오 셀(`provider.calls == 2` 단정) 1개. M7이 정확히 이 셀에 물리도록.
- **C3 — 정본 미반영**: 위 §6. 처방: SoT 버전 행 + writing generation/report 플랜에 세 계약 리터럴 반영(보고 플랜의 "1회 repair"→2회 드리프트도 이 기회에 정정).

### Hardening (비차단)

- **H1** — 패턴 스윕 완결성: D-유형 부채 목록이 4곳인데 `services/application/app/writing/retrieval.py:144-169`(parse 실패 → 1회 repair)이 같은 모양의 **5번째**다. 누락 등재.
- **H2** — 변이 기록 불일치: work_log 3종(tally식) vs CHANGELOG "5종(양방향)". 레코드 가이드가 요구하는 "한 줄에 diff·file:line·기명 셀" 표도 없다. 본 검증의 7종 표가 대체 근거로 남는다.
- **H3** — "광범위 13파일 400/187"(및 세션 3의 "8파일 237/140")은 파일 목록이 기록에 없어 비재현. 초집합 632/257 녹색으로 실질은 확인.
- **H4** — 빈 content 에러 메시지가 finish_reason을 안 싣는다. 닫히지 않은 thought 사례는 실제로 length인데 "empty generation result"만 보고된다 — 진단 품질 한 줄.
- **H5** — `docs/product-overview.md:106` 낡은 문구(감사 관측 축은 여전히 참이므로 문장 정정 수준).
- **H6** — finish_reason 대소문자·유사값 정규화 없음(엄격 리터럴 `"stop"` 비교). 이 저장소의 실측값은 전부 소문자(client.py 주석·벤치마크 fixture)라 현 위험은 낮다 — 계약 리터럴 관점에서는 오히려 정확한 해석.
- **H7** — 슬라이스가 백엔드 passed 수를 움직였는데(3075→3078) HANDOFF 회귀 기준선 줄·README ②행을 갱신하지 않았다. 상호 가드(`test_the_readme_repeats_the_regression_baseline`)는 두 문서의 *합치*만 검사해 **둘 다 같이 낡으면 초록**이다 — "이 수를 움직인 슬라이스가 같은 날 이 줄까지 온다"는 HANDOFF 자기 규칙 미이행. 본 검증이 갱신했다(실측 3078/1/4272 · 2014.17초).

## Verdict

**조건부 합격** — C1(revise 산문 표면의 B 가드 범위 확정·시행)·C2(mid-loop length 단락 셀 잠금)·C3(세 계약 리터럴의 정본 반영)이 닫히기 전까지.

가드 3종 자체는 진짜로 작동한다 — 전파 체인에 하드코딩이 없고, 검증자 재실행 변이 6종이 양방향으로 기명 재실패했으며, 전수는 기준선+3 셀의 정확히 몫으로 무회귀다. 조건 셋은 모두 "가드의 빈 칸과 기록의 빈 칸"이지 가드의 실패가 아니다.

## Outstanding items

- 오너 결정 대기: C1의 (a) 확장 vs (b) 범위 명시.
- 이 검증은 결함을 고치지 않았다 — 트리는 대상 그대로 `bfcf113` + 이 기록·인덱스 행뿐(미커밋 시점 기준; 검증 세션이 커밋함).
- test-mongo(27020)·개발 mongo(27520) 컨테이너가 검증 내내 가동 중이었다(기존 상태, 이 검증이 기동한 것은 아님).

## Reproduction

```bash
git status --short   # empty 확인(고정 트리 bfcf113)
# 집중 / 광범위 초집합 / 전수
PYTHONPATH=. python3 -m pytest tests/test_writing.py tests/test_writing_report.py -q
PYTHONPATH=. python3 -m pytest tests/test_writing*.py tests/test_llama_provider_client.py \
  tests/test_llm_gateway_app.py tests/test_llm_gateway_payload.py tests/test_gateway_capabilities.py \
  tests/test_analysis_gateway_provider.py tests/test_analysis_compare_judge.py \
  tests/test_analysis_extractor_schema.py tests/test_context_search_planner.py \
  tests/test_identity_judge_runner_wiring.py tests/test_json_extract.py -q
PYTHONPATH=. python3 -m pytest tests/ -q   # 3078/1/4272 · EXIT=0
# 변이: 위 표의 diff를 적용(문자열 치환) → 해당 셀 -k 실행 → git checkout -- <path> → clean 확인
# fixture 값 전수
grep -rn 'finish_reason=' tests/ | grep -v '"stop"' | grep -v '"length"'
```

D mid-loop 분기 실측(검증자 자작, 기록 재현용 — 의존는 전부 저장소 내):

```python
# PYTHONPATH=. python3 - <<'PY'
import asyncio
from services.application.app.analysis.prompt_templates import (
    PromptTemplateService, InMemoryPromptTemplateRepository)
from services.application.app.writing.report import (
    WritingCandidateReportService, seed_report_template)
from services.application.app.writing.models import (
    WritingCandidate, WritingTaskType, WritingOutputType)
from services.application.app.context_search.models import (
    ContextPackage, ContextSearchPurpose)
from services.llm_gateway.app.provider import GenerationResult, TokenUsage

class P:
    def __init__(s, outs, fins): s.outs=list(outs); s.fs=list(fins); s.calls=0
    async def generate(s, request):
        s.calls += 1
        return GenerationResult("fake", s.outs.pop(0), s.fs.pop(0), TokenUsage(1,1))

p = P(["bad1", "bad2"], ["stop", "length"])   # 첫 malformed+stop → repair1 결과 malformed+length
t = PromptTemplateService(InMemoryPromptTemplateRepository()); seed_report_template(t)
s = WritingCandidateReportService(p, prompt_templates=t)
c = WritingCandidate("r","p",WritingTaskType.CONTINUE_SCENE,WritingOutputType.DRAFT_PATCH,"본문")
pkg = ContextPackage("p",ContextSearchPurpose.WRITING_CONTEXT,(),(),(),(),0,False)
try: asyncio.run(s.enrich(c, pkg))
except Exception as e: print("terminated with:", type(e).__name__)
print("calls =", p.calls)   # 계약 D: 2 (repair2 건너뜀)
PY
```

문서 가드 양단: 기록·인덱스 작성 전 34 passed / 1086 subtests → 작성 후 **34 passed / 1088 subtests**(+2 = 이 기록 파일·인덱스 행의 몫). 건수 주장 갱신 4곳(루트 README 2 · docs/README 1 · verifications 인덱스 머리 1)은 `test_docs_indexes` 의 건수 가드가 안내한 그 자리다.
