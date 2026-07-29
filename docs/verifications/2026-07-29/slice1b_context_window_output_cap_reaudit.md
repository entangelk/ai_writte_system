# 독립 재검증 — K-3 관측 1b 컨텍스트 창·출력 상한

## Subject metadata

- **날짜**: 2026-07-29
- **요청자**: 오너 — 작업 AI의 1b 완료 보고와 중단된 독립 감사의 재검증 요청
- **검증자**: Codex(독립 재감사)
- **대상 slice/artifact**: 커밋 `3639b77`, K-3 관측 1b
- **정본 계약**: `docs/system-contract-sot.md` v1.7.59, 특히 381행의 감사 필드 목록과
  396행의 창·상한·None·비차단·무재시도 계약
- **작업 출처**: `main`의 `HEAD=3639b77`; 제품 코드는 커밋 상태와 동일
- **선행 감사**:
  `docs/verifications/2026-07-29/slice1b_context_window_output_cap_audit.md`
  (검증 세션 중단으로 남은 초안; 이 문서가 판정을 대체)

정본 우선순위는 `docs/system-contract-sot.md:204-224`의 문서 역할 표에 따라 Approved SoT를
최우선으로 두고, 해당 SoT가 근거로 연결한
`docs/plans/context-budget-korean-tokens-decisions.md:495-504,545-553`, 구현, 테스트 순으로
역추적했다.

## Scope

1. `/props`의 `n_ctx`를 상수 없이 읽는 생산 경로
2. 한 번만 조회하고 성공·실패 모두 캐시하는 경계
3. 관측 조회가 생성 성공을 깨뜨리지 않는다는 시간/오류 경계
4. non-null `context_window`의 게이트웨이 → 앱 → scope 전달
5. `context_window`·`max_output_tokens`의 Mongo 저장/복원
6. 실패 호출의 `max_output_tokens` 기록
7. `None` 의미론, 헤드룸 미저장, 관측 전용(거부 없음)
8. 라이브 레코드와 작업자 헤드룸 표
9. 신규/관련 회귀와 양방향 뮤테이션
10. SoT·HANDOFF·완료 보고의 자기일관성

## Methodology

- 정본 범위를 먼저 읽고 아래 경계 행렬을 작성했다.
- `git show 3639b77^..3639b77`, 대상 symbol, 테스트 assertion을 각각 읽어 literal과 경계를
  역추적했다.
- 코드가 현재 맞아 보이는 것과 테스트가 그 사실을 잠그는 것을 분리했다.
- 테스트가 실제로 bite하는지 확인하기 위해 각 뮤테이션을 하나씩 적용하고 집중 테스트를 실행한 뒤
  즉시 원복했다. 최종 `git diff`로 제품 코드 무변을 확인했다.
- `/props` 지연은 성공 생성 + 느린 GET transport와 외부 `asyncio.wait_for` deadline으로 축소 재현했다.
- 배포 Mongo의 non-null 레코드를 직접 읽고 `창 - 입력 - 출력상한`을 재계산했다.
- 전체 테스트는 독립 실행했으나 3% 뒤 장시간 진행이 없어 중단했다. 수집은 **1713 tests**로
  확인했고, 대상 집중 테스트는 모두 통과했다. 전체 green 주장은 작업자의 기존
  `1712 passed / 1 skipped` 기록과 구분한다.

사용한 핵심 명령:

```bash
git show --stat --oneline 3639b77
git diff 3639b77^ 3639b77 -- <대상 코드·테스트>
PYTHONPATH=. python3 -m pytest tests/ --collect-only -q -p no:cacheprovider
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider \
  tests/test_llama_provider_client.py tests/test_httpx_transport.py \
  tests/test_llm_gateway_app.py tests/test_analysis_gateway_provider.py \
  tests/test_llm_call_scope.py tests/test_llm_call_audit_mongo.py \
  tests/test_llm_call_audit.py
```

## Boundary matrix

| 계약 경계 | 현재 구현 | 직접 회귀 | 뮤테이션 결과 | 판정 |
|---|---|---|---|---|
| `/props`에서 `n_ctx` 읽기 | `client.py:40-57` | fake transport만 있음 | 실제 HTTP GET→POST여도 18/18 통과 | **빈 셀** |
| 성공/실패 후 재조회 없음 | 구현됨 | `test_llama_provider_client.py:322-363` | 기존 감사의 재시도 mutation이 bite | 충족 |
| 조회 오류가 생성 예외를 만들지 않음 | 즉시 오류는 격리 | `:342-363` 연결 오류만 | 즉시 오류 셀은 bite | 부분 충족 |
| 조회 지연도 생성을 깨지 않음 | 생성 뒤 GET을 동기 대기 | 없음 | 외부 deadline에서 `TimeoutError` | **구현 위반** |
| provider 결과 → 게이트웨이 non-null 봉투 | `gateway main.py:160-172` | None exact test만 있음 | 항상 None이어도 7/7 통과 | **빈 셀** |
| 게이트웨이 → 앱 non-null 파싱 | `gateway_provider.py:121-136` | non-null test 없음 | 항상 None이어도 관련 21개 통과 | **빈 셀** |
| 성공 호출 scope에 창·상한 기록 | `llm_call_scope.py:230-240` | `test_llm_call_scope.py:134-179` | 캡처 제거 시 해당 셀 bite | 충족 |
| 실패 호출에도 출력 상한 기록 | `llm_call_scope.py:219-228` | 없음 | 캡처 제거 후 scope 14개 통과 | **빈 셀** |
| Mongo non-null 왕복 | `llm_call_audit_mongo.py:48-88` | fixture가 두 필드 모두 None | 저장+복원 삭제 후 6/6 통과 | **빈 셀** |
| 모르면 None, 기본값 금지 | 구현됨 | `test_llm_call_scope.py:160-179` | 기본값 mutation 대상 셀 존재 | 충족 |
| 헤드룸 미저장·초과 거부 없음 | 저장 모델/호출 경로에 파생값·guard 없음 | 원천값 산식 확인 | 구조 확인 | 충족 |

## Findings

### 1. 라이브 데이터와 작업자 산술은 정확하다

배포 `llm_call_audits`의 `context_window != null` 3건을 재조회했다.

| 호출부 | 입력 | 실제 출력 | 출력 상한 | 창 | 헤드룸 |
|---|---:|---:|---:|---:|---:|
| `query_planner` | 483 | 145 | 1,024 | 16,384 | 14,877 |
| `writing_generation` | 2,633 | 1,539 | 4,096 | 16,384 | 9,655 |
| `writing_report` | 11,905 | 1,371 | 6,144 | 16,384 | **-1,665** |

`writing_report` 입력 비중 `11,905 / 16,384 = 72.66%`이므로 작업자의 “73%” 반올림도 맞다.
배포 컨테이너의 `StoredLlmCall`, `_doc`, `_call`에도 두 필드가 존재했다. 따라서 “관측 데이터가
실제로 생겼다”는 주장은 참이다.

### 2. 현재 제품 코드는 non-null 전달과 Mongo 저장을 구현하고 있다

`GenerationResult.context_window` → 게이트웨이 봉투 → 앱 `GenerationResult` →
`PendingLlmCall` → `StoredLlmCall` → Mongo `_doc/_call` 경로는 현재 코드상 이어져 있다
(`provider.py:23-32`, `llm_gateway/app/main.py:160-172`,
`analysis/gateway_provider.py:121-136`, `llm_call_scope.py:230-240`,
`llm_call_audit_mongo.py:48-88`). 라이브 3건도 이 경로가 현재 배포에서 동작했다는 별도 증거다.

하지만 아래 뮤테이션들이 모두 green이므로 그 경로는 회귀 계약으로 잠겨 있지 않다.

### 3. “관측이 기능을 깨뜨리지 않는다”는 계약은 시간 경계에서 위반된다

`LlamaCppProvider.generate()`는 성공 응답을 파싱한 뒤 `/props`를 **순차 await**하고 나서야 결과를
반환한다(`client.py:91-94`). `/props`와 생성은 같은 최대 120초 transport timeout을 쓴다
(`httpx_transport.py:17-24,37-38`). 앱의 게이트웨이 요청 deadline도 기본 120초다
(`analysis/gateway_provider.py:14-24,47-53`).

따라서 생성이 성공했어도 `/props`가 지연되면 앱의 deadline이 먼저 끝날 수 있다. 축소 재현:

```text
성공 POST 즉시 반환
GET /props 0.2초 지연
provider.generate 외부 deadline 0.05초
→ TimeoutError
→ _window_probed=True, _context_window=None
```

`except Exception`은 GET이 스스로 timeout/connection 예외를 낸 뒤에는 이를 삼키지만, 상위 deadline의
취소가 먼저 오면 이미 성공한 생성 결과를 보존하지 못한다. 이는 SoT
`docs/system-contract-sot.md:396`의 “그 조회는 생성을 깨뜨릴 수 없다”를 직접 위반한다.

### 4. 경계 행렬에 필수 회귀 셀 5개가 비어 있다

1. **실제 HTTP GET**: `HttpxJsonTransport.get_json()`을 POST로 바꿔도
   `test_httpx_transport.py + test_llama_provider_client.py` **18 passed / 16 subtests**.
2. **게이트웨이 non-null 봉투**: 응답을 항상 `context_window=None`으로 바꿔도
   `test_llm_gateway_app.py + test_analysis_gateway_provider.py`
   **7 passed / 5 subtests**.
3. **앱 non-null 파싱**: 파서를 항상 `None`으로 바꿔도 관련 테스트 전부 통과.
4. **Mongo non-null 왕복**: `_doc`·`_call`에서 두 필드를 모두 삭제해도
   `test_llm_call_audit_mongo.py` **6 passed**. 픽스처
   `tests/test_llm_call_audit_mongo.py:64-77`가 직전 1a 필드만 non-null로 채우고 1b 필드는
   기본 `None`으로 두기 때문에 `None == None`으로 통과한다.
5. **실패 호출 상한**: provider error 경로의 `max_output_tokens=`를 삭제해도 scope 테스트
   14개가 통과한다. 테스트 `tests/test_llm_call_scope.py:181-218`은 분해·outcome·error만 보고
   출력 상한은 assertion하지 않는다.

이 중 4번은 같은 테스트 파일 주석이 1a에서 이미 경고한 정확히 같은 실패 패턴이다
(`tests/test_llm_call_audit_mongo.py:67-69`). 1b가 그 선례를 확장하지 않았다.

### 5. 문서 현재 상태도 자기모순이다

- `HANDOFF.md:159`는 네 원천 필드가 들어왔다고 올바르게 적는다.
- 같은 문서 `HANDOFF.md:130`은 여전히 `total_tokens`만 있고 분해도 없다고 적는다.
- `HANDOFF.md:161`은 “창을 아는 코드가 0줄”이라고 적어 현재 구현과 모순된다.
- 중단된 감사 초안은 working tree clean, test-mongo 제거, 차단 0건을 썼지만 현재 감사 파일은
  untracked이고 test-mongo가 남아 있었다. 제품 코드 상태와 감사 작업 상태를 혼동하면 안 된다.

## Issues / Risks

### Blocking (contract obligations)

- **B1 — 구현 위반**: 느린 `/props`가 이미 성공한 생성을 상위 deadline에서 실패시킬 수 있다.
- **B2 — production GET 회귀 부재**: GET이 POST로 퇴행해도 green.
- **B3 — non-null gateway/app 전달 회귀 부재**: 두 중간 경계가 각각 항상 None이어도 green.
- **B4 — Mongo non-null 왕복 회귀 부재**: 두 필드 저장·복원을 함께 삭제해도 green.
- **B5 — 실패 호출 출력 상한 회귀 부재**: SoT의 명시 분기가 삭제돼도 green.

경계 행렬의 빈 셀은 프로젝트 검증 규칙상 green bar와 무관하게 차단 finding이다.

### Hardening recommendations (non-blocking)

- **H1 — malformed positive-domain 경계**: `/props`의 `n_ctx=0`은 공통 `_token_count`가
  non-negative 값으로 받아들인다. 실제 llama.cpp 창은 양수지만, SoT가 유효 범위를 명시하지
  않았으므로 이번 verdict의 차단 사유로 쓰지 않는다. 계약을 양수로 좁힐 때 회귀를 함께 추가한다.
- **H2 — 전체 suite 실행성**: 독립 전체 실행이 3%에서 장시간 진행하지 않았다. 테스트 순서/환경
  문제인지 별도 진단 후보이며, 이 slice의 재현된 B1~B5를 완화하지 않는다.

## Verdict — **FAIL**

라이브 관측 데이터, 헤드룸 산술, 현재 non-null 배선 자체는 맞다. 그러나 핵심 계약인 “관측이 생성을
깨뜨릴 수 없다”가 느린 `/props`에서 실제로 깨지고, 필수 생산 경로 4곳과 실패 호출 분기 1곳이
회귀로 잠겨 있지 않다. 따라서 중단된 감사의 PASS/차단 0건은 폐기한다.

합격 전 최소 조건:

1. `/props` 지연이 성공 생성의 반환 경로와 deadline을 공유하지 않도록 B1 수정
2. 느린/실패 probe 양방향 회귀
3. HTTP GET, 게이트웨이 non-null, 앱 non-null, Mongo non-null 왕복, 실패 호출 상한 테스트 추가
4. 위 5개 mutation이 각각 해당 테스트에서 bite함을 재확인
5. 관련 집중 suite와 실행 가능한 광역 suite green

## Outstanding items

- 제품 코드 수정은 이번 독립 감사 범위에서 하지 않았다.
- working tree에는 중단된 감사 초안, 본 재감사 기록, work log/HANDOFF 갱신만 남는다.
- test-mongo는 중단된 검증 세션이 남긴 컨테이너를 확인했고 감사 종료 전에 stop·remove했다.
- R-e(K-6)로 넘어가기 전에 B1~B5를 먼저 닫아야 한다. 그렇지 않으면 새 헤드룸 수치의 생산 경로가
  다시 조용히 `None`으로 퇴행할 수 있다.

## Reproduction

```bash
# 대상 집중 회귀
PYTHONPATH=. python3 -m pytest -q -p no:cacheprovider \
  tests/test_llama_provider_client.py tests/test_httpx_transport.py \
  tests/test_llm_gateway_app.py tests/test_analysis_gateway_provider.py \
  tests/test_llm_call_scope.py tests/test_llm_call_audit_mongo.py \
  tests/test_llm_call_audit.py

# 수집 수
PYTHONPATH=. python3 -m pytest tests/ --collect-only -q -p no:cacheprovider
# 1713 tests collected

# mutation 1: HttpxJsonTransport.get_json의 .get(path)를 .post(path)로
# → test_httpx_transport.py + test_llama_provider_client.py: 18 passed
# mutation 2: gateway main의 result.context_window를 None으로
# → test_llm_gateway_app.py + test_analysis_gateway_provider.py: 7 passed
# mutation 3: application _generation_result의 context_window를 None으로
# → 관련 21개 통과
# mutation 4: llm_call_audit_mongo._doc/_call에서 두 필드 삭제
# → test_llm_call_audit_mongo.py: 6 passed
# mutation 5: provider_error PendingLlmCall의 max_output_tokens 삭제
# → test_llm_call_scope.py: 14개 통과
```
