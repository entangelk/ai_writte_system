# LLM 출력 가드 조건 폐쇄 재감사

## Subject metadata

- 날짜: 2026-09-14 · 요청자: 오너(작업 AI 결과 재검증 요청) · 검증자: 독립 검증 세션.
- 대상: `d26fe1e`(C1·C2·H4 코드) · `35d3e21`(C3·기록), 현 `HEAD`.
- 정본: SoT v1.8.70 `docs/system-contract-sot.md:71,842`, 생성 브리프 `docs/plans/05-writing-generation-decisions.md:58-66`, report 브리프 `docs/plans/05-writing-report-api-decisions.md:34-35`.

## Scope

1. C1 revise 산문 표면의 빈 content·non-stop 종료 분류와 토큰 계량.
2. C2 report repair의 최신 결과 length 단락 및 양방향 회귀 잠금.
3. C3 정본·계획·코드·테스트 리터럴의 일치, 작업자 변이 주장 재현.

## Methodology

- 코드·정본·테스트를 파일:행 단위로 대조했다.
- 원 트리 focused 회귀: `python3 -m pytest tests/test_writing_revise.py::WritingRevisionServiceTest::test_truncated_replacement_is_rejected_as_provider_fault tests/test_writing_revise.py::WritingRevisionServiceTest::test_revise_metered_returns_provider_usage tests/test_writing_report.py::WritingReportTest::test_truncated_first_output_skips_the_repair_loop tests/test_writing_report.py::WritingReportTest::test_a_repair_that_finishes_length_stops_further_repairs tests/test_writing_report.py::WritingReportTest::test_invalid_first_output_repairs_once -q -p no:cacheprovider` → 5 passed.
- 변이 전마다 clean을 확인했다. clean 트리이므로 변이 후 원본은 역패치로 복원하고 `git diff`가 비어 있음을 확인했다. 전체 스위트는 새 blocking을 확인한 시점에 재실행하지 않았다.

## Findings

### C1 length 및 C2 최신 결과 잠금 — 성립

- revise의 `finish_reason != "stop"` 가드가 `MeteredCallError(ProviderError(INVALID_RESPONSE), usage)`로 감싸져 있다(`services/application/app/writing/revise.py:143-157`). 가드를 통째로 제거한 변이는 `test_truncated_replacement_is_rejected_as_provider_fault`에서 `MeteredCallError not raised`로 재실패했다.
- report의 `result = retry`를 삭제한 변이는 첫 malformed+stop → repair malformed+length에서 calls가 3이 되어 `test_a_repair_that_finishes_length_stops_further_repairs`가 `3 != 2`로 재실패했다. 이로써 C2의 mid-loop 경계는 실제로 잠겼다.
- stop 정상 치환도 과잉 거부하는 변이(`if result.finish_reason != "stop" or result.finish_reason == "stop"`)는 `test_replaces_only_unique_evidence_and_clears_stale_report`와 `test_revise_metered_returns_provider_usage`를 재실패시켰다.

### 차단 B1 — revise의 빈 content는 정본과 다른 분류

- 정본은 두 산문 표면 모두 공백 content를 `provider_invalid_response`로 분류하고 finish_reason을 메시지에 포함한다고 명시한다(`docs/system-contract-sot.md:71,842`; 생성 브리프:62-64).
- 생성은 이를 따른다(`services/application/app/writing/service.py:115-129`). 반면 revise는 `_replacement_text` 뒤 공백을 먼저 `InvalidWritingRevision("replacement must not be empty")`로 낸다(`services/application/app/writing/revise.py:131-137`). `test_revise_metered_invalid_result_carries_usage`도 이 상이한 도메인 예외를 명시적으로 기대한다(`tests/test_writing_revise.py:159-166`). 따라서 빈 content의 502/`provider_invalid_response` 분류와 finish_reason 진단이 revise 표면에는 없다.

### 차단 B2 — `!= "stop"` 계약의 일반값 경계가 무셀

- Gateway는 finish_reason을 enum으로 제한하지 않고 문자열 그대로 전달한다(`services/llm_gateway/app/client.py:301,313-320`). 계약은 특정 `length`가 아니라 `finish_reason != "stop"` 전체를 거부한다.
- 현재 생성·revise 셀은 `length`만 공급한다(`tests/test_writing.py:288-302`, `tests/test_writing_revise.py:168-185`). revise 가드를 `result.finish_reason == "length"`로 좁힌 변이에서도 기존 length 거부·stop 정상 focused 두 셀이 모두 2 passed였다. 즉 `"content_filter"` 같은 non-stop 값이 통과하도록 과소 보정해도 회귀가 못 잡는다. 생성 표면도 동일한 테스트 공백이다.

## Issues / Risks

### Blocking (계약 의무)

- **B1**: revise의 빈/공백 content를 생성과 같은 `ProviderErrorCode.INVALID_RESPONSE`로, `MeteredCallError`의 usage 보존 상태에서 거부하고 finish_reason을 메시지에 실어야 한다. 기존 `InvalidWritingRevision` 기대 셀도 새 계약을 단정하도록 바꿔야 한다.
- **B2**: generate와 revise 각각에서 `length` 외의 non-stop 값도 거부하는 회귀를 추가해야 한다. 정상 `stop` 회귀는 이미 있으므로, 한 표면씩 `"content_filter"` 같은 값으로 code·message·retryable·usage(revise)를 단정하면 경계가 닫힌다.

### Hardening recommendations (non-blocking)

- 작업자 전수 주장(3080/1/4274)은 이 재감사에서 새 차단을 먼저 발견해 독립 재실행하지 않았다. B1·B2 폐쇄 뒤 깨끗한 트리에서 전수를 다시 재고 환경과 함께 기록해야 한다.

## Verdict

**조건부 합격** — B1(revise 빈 content의 정본 분류·진단 일치)과 B2(non-stop 일반값의 양 표면 회귀 잠금)가 닫히기 전까지.

C1의 length 가드와 C2의 최신 결과 분기는 실제 변이로 재실패했고, C3의 정본 반영도 존재한다. 그러나 현재 정본이 "둘 다 같은 두 가드·같은 분류"라고 명시하므로 B1은 코드-계약 불일치이며, B2는 `!= "stop"` 계약-required 경계의 빈 셀이다.

## Outstanding items

- B1·B2는 구현 변경을 수반한다. 이 독립 검증은 코드·테스트를 수정하지 않았다.
- 변이 후 원본은 역패치로 복원했고, 기록 작성 전 트리는 clean이었다.

## Reproduction

```bash
git status --short
python3 -m pytest \
  tests/test_writing_revise.py::WritingRevisionServiceTest::test_truncated_replacement_is_rejected_as_provider_fault \
  tests/test_writing_revise.py::WritingRevisionServiceTest::test_revise_metered_returns_provider_usage \
  tests/test_writing_report.py::WritingReportTest::test_truncated_first_output_skips_the_repair_loop \
  tests/test_writing_report.py::WritingReportTest::test_a_repair_that_finishes_length_stops_further_repairs \
  tests/test_writing_report.py::WritingReportTest::test_invalid_first_output_repairs_once -q -p no:cacheprovider
```
