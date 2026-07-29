# 검증 기록 — 슬라이스 1a / 감사에 입력·출력 토큰 분해 남기기 (K-3 관측 1a)

## Subject metadata

- **날짜**: 2026-07-29
- **요청자**: 오너(entangelk) — "다음 작업 검증해줘. 1a 커밋 완료 — 934ef16."
- **검증자**: Claude(본 세션)
- **검증 대상**: K-3 관측 슬라이스 **1a** 구현 — `llm_call_audits` 레코드에 입력/출력 토큰 분해
  (`prompt_tokens`·`completion_tokens`)를 기록. 작업자 주장: 총량은 있었지만 분해가 없어 "창의
  얼마를 입력에 쓰는가"를 답할 수 없었고, 데이터가 없던 게 아니라 `ObservedProvider`가
  `total_tokens`만 취해 분해를 버리고 있었다(한 줄에서 버려지던 값을 살림). `None`="모른다"(0 아님).
- **정본 사양 참조**: `docs/system-contract-sot.md` **v1.7.42 H1**(감사 레코드 토큰 의미론 —
  `provider_error`의 `total_tokens=0`="알 수 없음", 토큰 집계는 `success`+`parse_error`만 대상) 및
  v1.7.43(`ObservedProvider` = `generate()` 1회 = 레코드 1건, 유일한 per-call 감사 경로). 작업자
  work_log의 K-3 관측 1a 절.
- **검증 대상 작업의 출처**: 커밋 **`934ef16`**(7개 파일: `llm_call_scope.py`·`llm_call_audit.py`·
  `llm_call_audit_mongo.py`·테스트 2·HANDOFF·work_log). **working tree clean**.

> **검증 성격**: 구현 슬라이스. §5 경계 매트릭스 적용 — should-fire(성공 시 분해 기록)·
> should-NOT-fire(실패·옛 레코드는 None, 0 아님)·왕복(지속성) 각각 회귀 셀에 대응, 빈 칸 없는지 확인.

## Scope

1. **캡처 배선 완전성** — provider 응답의 분해가 `ObservedProvider`→`_flush`→`record`→`StoredLlmCall`→
   Mongo까지 누락 없이 이어지는가(한 줄도 끊기지 않는가).
2. **"데이터가 있었다" 주장** — 게이트웨이·앱 provider가 분해를 이미 갖고 있었는가.
3. **None 의미(should-NOT-fire)** — `provider_error`·옛 레코드가 0이 아니라 None으로 읽히는가;
   SoT v1.7.42 H1의 0="알 수 없음"과 정합인가.
4. **Mongo 왕복** — 두 필드가 저장·재조회되고, 비어 있지 않은 값으로 왕복을 검증하는가.
5. **양방향 가드** — under-strict(캡처 누락)·over-strict(0 채움·반쪽 기록)가 둘 다 있는가.
6. **스윕 완전성** — 다른 per-call 감사 캡처 지점이 없는가(우회 경로).
7. **공개 계약 불변** — `schema.d.ts`/응답 모델에 변화가 없는가.
8. **후행 선택 필드 설계** — 필수화하면 기존 27건이 깨지는 것을 회피하면서 계약(기본값="모른다")을
   지키는가.
9. **회귀** — 기준선 1703/1/1468 대비 +3 = 신규 3개인가.
10. **HANDOFF 절차 함정** — test-mongo healthy 대기 함정이 기록됐는가.

## Methodology (재현 가능한 명령)

모든 주장은 1차 소스에서 재도출. 기계: WSL2, Python 3.12.3, `PYTHONPATH=.`. test-mongo는
**healthy를 기다린 뒤** 돌림(작업자의 1698/9-skip 교훈 — 본 검증에서도 함정으로 서술했기에 준수).

- **코드 읽기**: `llm_call_scope.py`(56-61·184-188·223-227) · `llm_call_audit.py`(122-135·177-198) ·
  `llm_call_audit_mongo.py`(56-85) · `llm_gateway/app/provider.py`(12-19) ·
  `llm_gateway/app/main.py`(160-170) · `observability/kpi.py`(204·218).
- **git blame**: `llm_call_scope.py:226-227`이 `934ef168`(본 커밋)에서 추가됐는지 확인.
- **뮤테이션 매트릭스**: `_doc`에서 두 필드 제거(누락)·`_call`을 `doc.get(...,0)`(0 채움)·
  `ObservedProvider` 캡처 제거 — 각각 돌리고 `git checkout` 복구.
- **전수 스윕**: `grep -rn` record() 호출부·StoredLlmCall 생성·사용처.
- **회귀**: `docker compose -f docker-compose.test.yml up -d`(healthy 대기) →
  `PYTHONPATH=. python3 -m pytest tests/ -q`.
- **베타 DB 교차**: pymongo로 `llm_call_audits` 최근 레코드의 분해 필드 존재 확인.

## Findings

### 1. 캡처 배선 — 한 줄도 끊기지 않는다 (should-fire ✓)

`git blame` 확인: `llm_call_scope.py:226-227`(캡처)은 본 커밋 `934ef168`에서 추가됐다(작업자가
"한 줄에서 버려지던 값을 살렸다"고 한 바로 그 줄). 끝까지 이어진다:

`ObservedProvider` 성공 경로 → `result.usage.prompt_tokens`/`completion_tokens` 캡처
([`scope.py:226-227`](../../../services/application/app/observability/llm_call_scope.py#L226)) →
`PendingLlmCall` 적재([`:60-61`](../../../services/application/app/observability/llm_call_scope.py#L60)) →
`_flush`가 `record()`에 전달([`:187-188`](../../../services/application/app/observability/llm_call_scope.py#L187))
→ `StoredLlmCall` 필드([`audit.py:131-132`](../../../services/application/app/observability/llm_call_audit.py#L131))
→ Mongo `_doc`/`_call` 왕복([`audit_mongo.py:59-60·78-82`](../../../services/application/app/observability/llm_call_audit_mongo.py#L59)).

`TokenUsage`는 `prompt_tokens`·`completion_tokens`를 갖는다
([`provider.py:14-15`](../../../services/llm_gateway/app/provider.py#L14), `total_tokens`는 계산 속성)
→ 캡처 줄이 `AttributeError` 날 일이 없다.

### 2. "데이터가 있었다" 주장 — 정확하다 (✓)

게이트웨이는 분해를 이미 돌려준다
([`llm_gateway/app/main.py:163-168`](../../../services/llm_gateway/app/main.py#L163) —
`usage:{prompt_tokens,completion_tokens,total_tokens}`)·앱 provider도 파싱한다
([`analysis/gateway_provider.py:126-127`](../../../services/application/app/analysis/gateway_provider.py#L126)).
종전엔 `ObservedProvider`만 `total_tokens`을 취해 분해를 버렸다. "데이터가 없던 게 아니라
버려졌다"는 서술이 사실이다.

### 3. None 의미 — SoT v1.7.42 H1과 정합 (should-NOT-fire ✓)

- `provider_error`(provider 무응답) → 분해는 `None`(`PendingLlmCall` 기본값; 성공 경로만 캡처).
  `test_provider_error_leaves_the_split_unknown_not_zero`가 잠근다.
- 옛 레코드(필드 생기 전) → Mongo `_call`이 `doc.get("prompt_tokens")`로 읽어 `None`. 0 아님.
  `test_legacy_doc_without_the_split_reads_unknown_not_zero`가 잠근다(동시에 `total_tokens=222`는
  계속 읽힘).
- **SoT 정합**: v1.7.42 H1이 `provider_error`의 `total_tokens=0`="알 수 없음"으로 정의하고 토큰
  집계를 `success`+`parse_error`로 한정한다. 새 필드의 `None`="모른다"는 같은 개념의 **명시적**
  표현이며, 향후 집계 소비자가 `None`을 자연히 제외해 이 배제 규칙과 정렬된다(`0`이면 합에 섞여
  낙관 오염). 베타 DB 실측에서도 `provider_error` 레코드가 `total_tokens=0`인 것이 이 규칙과 일치.

### 4. Mongo 왕복 — 비어 있지 않은 값으로 잠금 (✓ + 뮤테이션 재현)

작업자 주장을 **뮤테이션으로 그대로 재현**:

| 뮤테이션 | 결과 | 작업자 주장 |
|---|---|---|
| `_doc`가 두 필드 통째로 누락 | **3 failed** | "누락 3건 실패" ✓ |
| `_call`이 `doc.get(...,0)`(0 채움) | **1 failed** | "0으로 채우기 1건 실패" ✓ |
| `ObservedProvider` 캡처 누락 | **1 failed** | 분리 캡처 셀 ✓ |

핵심: 픽스처 `_call`이 `prompt_tokens=200, completion_tokens=22`(비-None) 기본값을 가져,
"field-for-field 왕복" 비교가 `None==None`으로 지나가던 함정을 제거했다. 옛 문서 경로 셀이
`None`-vs-`0` 경계를 잡는다.

### 5. 양방향 가드 — 동등·None 기반으로 단단 (✓)

- `test_input_and_output_tokens_are_recorded_separately`: under-strict(캡처 누락→`None`→실패)·
  over-strict(`prompt+completion != total`이면 반쪽 기록으로 실패). 슬라이스 1의 느슨한 `2×`과 달리
  **동등 기반**이라 작은 드리프트도 잡는다.

### 6. 스윕 완전성 — 우회 per-call 캡처 없음 (독립 grep ✓)

per-call 감사 캡처는 `ObservedProvider`→`_flush`→`LlmCallAuditService.record`가 **유일 경로**
(SoT v1.7.43: "도메인 코드는 무변, `generate()` 1회=레코드 1건"). 직접 `record()`를 부르는 다른
호출부 없음(`writing_loop_audit.record`는 별개 루프 단위 저장소). `StoredLlmCall` 생성은
`record()` 내부가 유일. → 분해를 버리는 다른 지점이 없다.

### 7. 공개 계약 불변 (✓)

`schema.d.ts`에 `prompt_tokens`/`completion_tokens` **0건**. `main.py` 응답에도 등장 안 함(감사
레코드 자체가 typed 응답으로 노출되지 않음; KPI endpoint는 `total_tokens`만 집계). → 공개 계약
변화 0. 필드는 순수 내부 저장 추가.

### 8. 후행 선택 필드 설계 (✓)

새 필드는 `created_at`(필수) **뒤에** `= None` 기본값으로 뒀다 → 기존 `StoredLlmCall(...)` 생성
27건이 깨지지 않는다. "기본값='모른다'"가 계약과 맞다는 설계 근거(작업자: 필수화 시 27건 파열).
데이터 클래스 순서(필수→선택)도 유효(회귀 1706 수집 성공으로 확인).

### 9. KPI 소비자 — 아직 분해를 소비 안 함 (계획됨, 결함 아님)

`observability/kpi.py:204·218`은 여전히 `total_tokens`만 합산. 1a는 **기록**이며, 분해를 소비하는
자원배분 지표는 창 크기 분모(1b)가 들어온 뒤다. 작업자 서술("1a=분자 기록, 1b=창 분모")과 일치.

### 10. HANDOFF 절차 함정 — 기록됐다 (✓)

`HANDOFF.md:82`에 `up -d` 직후 조용한 skip 함정(실측 `1698/9 skipped`, 정상 `/1`)과 `until healthy`
한 줄이 추가됐다(본 커밋 +2줄). 작업자의 절차 실수 기록과 일치.

## Issues / Risks

### Blocking (계약 의무) — **0건**

경계 매트릭스 전 칸 충족: 성공-분해-기록(should-fire)·실패/옛레코드-None(should-NOT-fire, 0 아님)·
Mongo 왕복. 양방향 가드 존재(동등·None 기반). 회귀 +3. 공개 계약 무변. 빈 칸 없음.

### Hardening recommendations (비차단)

- **H1 — 새 필드의 None="모른다" 의미가 SoT에 아직 명시 안 됨.** SoT v1.7.42 H1은
  `total_tokens=0`="알 수 없음"을 정의하지만 `prompt_tokens`/`completion_tokens`를 언급 않는다.
  코드 주석·work_log엔 있고 회귀가 고정하나, 정본에 한 줄(옛 규칙의 병행 확장)로 올리면
  `total_tokens=0` vs 새 필드 `None`이라는 **같은 개념의 두 표현**이 다음 독자를 헷갈리게 않는다.
  → 권고: 분해를 소비하는 지표 슬라이스에서 SoT/`observability-kpi` 결정문에 병기. **비차단**:
  코드 동작은 올바르고 세 곳에 문서화됐으며, SoT v1.7.42 원칙을 그대로 따른다.

## Verdict — **합격 (PASS)**

차단 사유 0건. 분해 캡처 배선이 한 줄도 끊기지 않고 끝까지 이어지고(본 커밋에서 `ObservedProvider`
캡처 줄이 실제 추가됨을 blame로 확인), `None`="모른다" 의미가 SoT v1.7.42 H1과 정합하며, Mongo
왕복이 비-None 값으로 잠겨 있고, 뮤테이션 3종(누락 3·0 채움 1·캡처 누락 1)이 작업자 주장과 정확히
일치한다. 공개 계약 무변. 회귀 **`1706 passed / 1 skipped / 1468 subtests`(717.3s, exit 0)** —
기준선 1703/1/1468 대비 **+3 passed** = 신규 3 셀과 정확히 일치(독립 재실행, test-mongo healthy 대기 후).
작업자 주장과 정확히 일치.

## Outstanding items (오너 다음 행동에 영향, 결함 아님)

- **1a는 커미트됐지만 베타에 아직 배포되지 않았다.** 베타 DB `llm_call_audits` 최근 레코드 전부가
  분해 필드 미포함(non-null 0건) — pre-1a 이미지가 쓴 것이다. 1a(및 1b)의 실제 라이브 기록을
  관측하려면 application 이미지 재빌드·재배포가 필요하다. 작업자가 "1a 완료"라 한 것은 커밋
  완료이며 배포 주장은 아니다.
- **분해를 소비하는 자원배분 지표는 1b(창 크기 분모) 이후.** 1a는 기록만 채운다.
- **본 검증에서 test-mongo를 기동했다가**(`ai_writte_system-test-mongo-1`, healthy 대기 후 회귀) **다시
  내렸다** — 오너가 의도한 상태(베타 스택 UP · test-mongo DOWN)로 복구. 작업자가 1a 작업 중 올린
  컨테이너가 계속 떠 있었는데, 회귀 재실행에 썼다.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 3개 신규 셀
PYTHONPATH=. python3 -m pytest \
  tests/test_llm_call_scope.py::ScopeCaptureTest::test_input_and_output_tokens_are_recorded_separately \
  tests/test_llm_call_scope.py::ScopeCaptureTest::test_provider_error_leaves_the_split_unknown_not_zero \
  tests/test_llm_call_audit_mongo.py::MongoLlmCallAuditRepositoryTest::test_legacy_doc_without_the_split_reads_unknown_not_zero -v

# 뮤테이션: llm_call_audit_mongo.py 의 _doc 에서 두 필드 제거 → 3 fail;
#   _call 의 doc.get(...,0)으로 바꾸기 → 1 fail(옛 문서 셀);
#   llm_call_scope.py 의 ObservedProvider 캡처 2줄 제거 → capture 셀 1 fail.  매번 git checkout 복구.

# 회귀 (test-mongo healthy 대기 후 — 함정 준수)
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done
PYTHONPATH=. python3 -m pytest tests/ -q          # → 1706 passed / 1 skipped / 1468 subtests
```
