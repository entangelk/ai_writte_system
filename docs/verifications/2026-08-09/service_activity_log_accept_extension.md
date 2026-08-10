# 독립 검증 — Phase 9 A2 추가 확정(`writing/accept` 활동 로그 포함, 19 → 20)

| 항목 | 값 |
|---|---|
| 날짜 | 2026-08-09 |
| 요청자 | 오너 |
| 검증자 | 독립 세션(구현 세션이 아님) |
| 대상 | 미검증 구간 2커밋 — `170ea3a`(구현) · `ca97f2b`(기록) |
| 정본 | [`system-contract-sot.md`](../../system-contract-sot.md) **v1.7.93** · [`plans/09-0-service-activity-log-decisions.md`](../../plans/09-0-service-activity-log-decisions.md) §"A2 추가 확정" · [`mongo_collections.md`](../../mongo_collections.md) §43G |
| 소스 상태 | HEAD `ca97f2b`, 작업 트리 clean |
| 머신 | 알파(RTX 3060 12GB), test-mongo ON |
| 선행 검증 | Phase 9 본체는 [`service_activity_log.md`](service_activity_log.md) 합격(`ad195e5`). **이 기록은 그 뒤 확장분만** 본다 |

## 1. Scope

1. 계약 스코프 대조 — SoT v1.7.93 · 브리프 §"A2 추가 확정" · §43G · 부모 계획 §2
2. 분류표(`activity/actions.py`) 실측 — 20 / 20 / 40 · 리터럴 · `target_type`
3. 배선(`routers/writing.py`) — 성공 경로 · **502 partial 경로**
4. 회귀 셀이 계약의 분기를 실제로 잠그는가 (경계 행렬)
5. 뮤테이션 — 구현자 보고(N9·N10) 재현 + 검증자 추가 축(V1)
6. 회귀 기준선 재도출 및 문서 숫자 주장 대조

## 2. Methodology

```bash
git show 170ea3a; git show ca97f2b                      # 대상 diff 전량
PYTHONPATH=. python3 -c "…activity.actions…"            # 분류 수를 코드에서 직접 센다
docker compose -f docker-compose.test.yml up -d          # healthy 대기 후
python3 -m pytest -q -rs                                 # 전수 회귀 + skip 사유
python3 -m pytest -q tests/test_writing_accept.py tests/test_activity_actions.py
# 뮤테이션: 트리 clean 확인 → Edit 으로 변형 → 실행 → git checkout -- <path> → git status --short
```

뮤테이션 전 `git status --short`가 비어 있음을 매회 확인했고, 원복 후에도 매회
비어 있음을 확인했다(가이드 §"The restore rule" clean-tree 분기).

## 3. 계약 스코프에서 뽑은 경계 행렬

SoT v1.7.93 은 이 슬라이스의 기록 조건을 **상태코드가 아니라 "정본이 바뀌었는가"** 로
못박고, 세 분기를 이름으로 열거한다.

| # | 계약 문언 | 분기 | 기대 | 잠그는 셀 |
|---|---|---|---|---|
| B1 | "정본 draft version 을 실제로 만든다" | 성공(200, `saved≠null`) | **남긴다** | `WritingAcceptApiTest::test_a_saved_accept_is_recorded_in_the_activity_log` |
| B2 | "Gate 가 거부하면(200 · `saved=null`) 남기지 않고" | Gate 거부 | **안 남긴다** | `::test_a_bounced_accept_is_not_recorded` (over-strict) |
| B3 | "**502 partial envelope**(version 은 저장되고 분석 job 만 실패한 경로)은 **남긴다**" | 502 partial | **남긴다** | **없음 — §5 Blocking 1** |
| B4 | 리터럴 `draft_version_accepted` · `target_type="draft_version"` | 분류표 ↔ 배선 | 동일 | `ActivityActionClassificationTest::test_the_recorded_action_literal_matches_the_table` |
| B5 | 정본 11 + 검토 9 = 20 · `ai_request` 13 | 수 | 고정 | `::test_the_logged_set_is_the_twenty_the_owner_approved` · `::test_every_ai_request_is_excluded_with_that_reason` |

B3 은 정본이 **문장으로 열거한 "should fire" 분기**이며, 구현도 그 분기에 코드를
넣었다([`routers/writing.py:1273-1278`](../../../services/application/app/routers/writing.py#L1273)).
따라서 이것은 스펙 침묵 자리가 아니라 **계약이 요구하는 잠금**이다.

## 4. Findings

### 4.1 분류표 — 계약과 일치 (합격)

코드에서 직접 센 값:

```
logged 20 · excluded 20 · classified 40
canonical 11 · review 9
excluded 사유: ai_request 13 · admin_audited 4 · not_project_scoped 2 · derived_rebuild 1
```

[`activity/actions.py:96-97`](../../../services/application/app/activity/actions.py#L96)의 행이
`ActivityAction("draft_version_accepted", "POST", "/projects/{project_id}/writing/accept",
"draft_version")` 이고, SoT v1.7.93 이 적은 리터럴 두 개와 **문자 그대로 일치**한다.
`mongo_collections.md:2497`("정본 변경 **11** + 검토 결정 9 = **20 경로**")·브리프
§"A2 추가 확정"·`test_activity_actions.py:83-101` 도 같은 수를 말한다. 어긋난 자리 없음.

### 4.2 배선 — 두 분기 모두 존재, 격리는 자동 상속 (합격)

- 성공 경로: [`writing.py:1301-1307`](../../../services/application/app/routers/writing.py#L1301) —
  `if result.saved is not None:` 뒤. **결과를 안 뒤에 쓴다**(A7=A).
- 502 partial: [`writing.py:1273-1278`](../../../services/application/app/routers/writing.py#L1273) —
  `except WritingAcceptAnalysisError` 안, `JSONResponse` 반환 앞.
- `WritingAcceptAnalysisError.__init__` 이 `saved` 를 **키워드 필수 인자**로 받으므로
  ([`writing/accept.py:58-61`](../../../services/application/app/writing/accept.py#L58))
  `exc.saved.draft_version.id` 는 이 분기에서 항상 안전하다. `None` 역참조 경로 없음.
- A4=A 격리는 [`activity/log.py:130-136`](../../../services/application/app/activity/log.py#L130)의
  서비스 안 **한 곳**이라 두 분기가 자동으로 상속한다 — 호출부에 `try/except` 가
  없는 것이 옳다.

### 4.3 ★ B3 을 잠그는 셀이 하나도 없다 (Blocking)

`tests/test_writing_accept.py` 의 502 경로 셀
`test_partial_failure_is_502_and_retry_converges`([:365](../../../tests/test_writing_accept.py#L365))는
`_setup(analysis=analysis)` 로만 앱을 만들고 **`activity_repo` 를 싣지 않는다** —
즉 그 경로에서 활동 로그를 아무도 관측하지 않는다. 신설된 두 셀은 B1·B2 만 본다.

**뮤테이션 V1(검증자 추가 축, under-strict)** — 502 분기의 `activity.record(...)`
블록 6줄을 통째로 삭제:

| 실행 범위 | 결과 |
|---|---|
| `tests/test_writing_accept.py` + `test_activity_actions.py` + `test_activity_log.py` | `73 passed / 79 subtests` |
| `pytest -k "activity or accept or partial"` | `133 passed / 127 subtests` |
| **전수 회귀** | **`2246 passed / 4 skipped / 2324 subtests`** — 클린 실행과 **완전히 동일** |

즉 계약이 "남긴다"고 명시한 분기의 코드를 **통째로 지워도 저장소 전체가 green** 이다.
전수 가드 `test_every_logged_route_actually_records` 는 같은 handler 의 성공 분기에
남은 `activity.record(` 로 소스 스캔이 만족돼 통과한다 — 구현자 자신이 work_log 와
SoT v1.7.93 에 *"전수 가드는 배선의 존재만 보고 분기는 못 본다 … 분기마다 행위 셀이
필요하다"* 고 적어 두고, **정작 그 두 번째 분기의 셀을 넣지 않았다.**

가이드 §"The boundary matrix has no empty cells" 에 따라 이것은 Blocking 이다 —
"보강 후보"로 미룰 수 있는 자리가 아니다(계약이 요구하는 잠금이지 스펙 너머의
hardening 이 아니다).

### 4.4 구현자 보고 뮤테이션 재현 — 1종 정확, 1종 페어링 불일치

| # | 적용한 diff | 구현자 보고 | 검증자 실측 |
|---|---|---|---|
| N9 | 성공 경로 `if result.saved is not None:` 블록(record 포함) 삭제 | `::test_a_saved_accept_is_recorded_in_the_activity_log` (1) | **일치** — `1 failed, 56 passed`. 전수 가드는 예고대로 통과 |
| N10 | `if result.saved is not None:` → `if True:` | `::test_a_bounced_accept_is_not_recorded` · `::test_a_saved_accept_is_recorded_in_the_activity_log` (2) | **불일치** — 실제 재실패는 `::test_a_bounced_accept_is_not_recorded` · **`::test_non_pass_is_200_without_saved_artifacts`** (`2 failed, 55 passed`) |

N10 의 두 번째 셀이 다르다. `saved=None` 인 경로에서 `result.saved.draft_version.id`
가 `AttributeError` → 500 이 되어 **기존 셀**(`test_non_pass_is_200_without_saved_artifacts`)
이 물었고, 신설된 saved 셀은 그 시나리오를 타지 않아 통과했다. 재실패 **건수 2 는
맞았지만 어느 셀인지가 틀렸다** — 가이드 §"Record which mutation hit which cell" 이
경고하는 형태이며, 뒤에 읽는 사람이 "신설 셀 둘이 서로를 덮는다"고 오독할 수 있다.
비차단(§6-①).

### 4.5 회귀 기준선 재도출 — 보고와 일치 (합격)

```
2246 passed, 4 skipped, 2324 subtests passed in 191.20s
SKIPPED  test_chroma_adapter.py:490            (live Chroma — 호스트 구조적 skip)
SKIPPED  test_context_search_memory_lexical_retrieval.py:324/336/341  (elasticsearch 미설치 ×3)
```

`elasticsearch` 3건을 보정하면 **`2249 / 1 / 2324`** 로 work_log Task 6·README:88
(`2,249 passed / 2,324 subtests`)과 정확히 일치한다. operation 77 무변.

### 4.6 문서 숫자·리터럴 주장 (합격)

| 주장 | 위치 | 실측 |
|---|---|---|
| 계약 버전 v1.7.93 | `README.md:90` · SoT 머리말 | 일치 |
| 20 경로 / 정본 11 / `ai_request` 13 | SoT:36 · §43G:2497 · 브리프 · 테스트 | 코드와 일치 |
| 리터럴 `draft_version_accepted` · `target_type` | SoT:36 · 브리프:57 | 코드와 일치 |
| plans 인덱스 두 행 갱신 | `plans/README.md:159-160` | 갱신됨 |
| 부모 계획 상태 `Done` | `plans/09-service-activity-log.md:3` | 갱신됨 |

## 5. Issues — Blocking

**B-1. 502 partial envelope 경로의 기록을 잠그는 회귀 셀이 0건이다.**

- 계약: SoT v1.7.93 *"**502 partial envelope**(version 은 저장되고 분석 job 만 실패한
  경로)은 **남긴다**"* · 브리프 §"A2 추가 확정" 마지막 항목.
- 실측: 뮤테이션 V1 로 [`writing.py:1273-1278`](../../../services/application/app/routers/writing.py#L1273)
  을 삭제한 채 **전수 회귀 2246/4/2324 전부 통과**(§4.3).
- 왜 조용한가: A4=A 격리 때문에 배선이 없어도 런타임이 아무 소리를 내지 않고,
  전수 가드는 같은 handler 의 다른 분기로 만족된다. **런타임·회귀 어느 쪽도
  신호를 주지 않는다.**
- 닫는 비용은 작다 — 이미 있는 502 셀 옆에 한 셀:

  ```python
  def test_a_partial_accept_still_records_the_saved_version(self):
      repo = InMemoryActivityLogRepository()
      client, project, draft, base, _ = self._setup(
          analysis=_FailingAnalysis(InMemoryAnalysisRepository()),
          activity_repo=repo)
      response = self._post(client, project, draft, base.draft_version.id)
      self.assertEqual(response.status_code, 502)
      self.assertEqual(len(repo.events), 1)
      self.assertEqual(repo.events[0].target_id,
                       response.json()["saved"]["draft_version_id"])
  ```

  `_setup` 은 이미 `analysis` 와 `activity_repo` 를 함께 받으므로 하네스 변경이 없다.
- **검증자는 고치지 않았다**(가이드 §"If verification fails, the verifier does not
  silently fix the defect"). 오너 판단 사안이다.

## 6. Hardening recommendations (비차단)

① **뮤테이션 페어링 정정** — work_log Task 6 표와 SoT v1.7.93 의 N10 행이 재실패 셀
하나를 잘못 적었다(§4.4). 건수는 맞으므로 결론은 안 바뀌지만, 이 저장소는 페어링을
근거로 "이 셀이 이 조항을 잠근다"를 주장하므로 정정해 두는 편이 낫다.

② **idempotent replay 가 이벤트를 매번 추가한다 — 이 슬라이스가 만든 것은 아니다.**
같은 `idempotency_key` 로 3회 POST 하면 활동 이벤트가 **3건**(대상 draft version 은 1개)
남는다. 실측(검증자 프로브, in-memory 조립):

| 경로 | 3회 POST 응답 | 이벤트 | 서로 다른 target |
|---|---|---|---|
| `writing/accept`(성공) | 200·200·200 | 3 | 1 |
| `writing/accept`(502 partial) | 502·502·502 | 3 | 1 |
| `drafts/{id}/versions`(수동 저장, **9.0 본체**) | 200·200·200 | 3 | 1 |

즉 **9.0 본체의 `draft_version_saved` 와 정확히 같은 성질**이고 accept 가 도입한
편차가 아니다. A2·A8 어느 조항도 replay 축을 말하지 않으므로 계약 위반이 아니다.
다만 **화면(활동 타임라인) 슬라이스가 "저장 3번"으로 그리게 되므로** 그때 ⓐ 그대로
둔다 ⓑ `idempotent_replay` 를 기록에서 제외한다 ⓒ 이벤트에 replay 표식을 단다 중
하나를 정해야 한다. 지금 결정할 필요는 없다.

③ **주석 수치 갱신** — [`activity/log.py:88`](../../../services/application/app/activity/log.py#L88)의
`ActivityLogService` docstring 이 아직 *"19 개 호출부"* 라 적는다(현재 logged 20 ·
`activity.record(` 호출 지점 21). 계약이 아니라 서술이라 비차단.

## 6-b. 조건 폐쇄 (2026-08-09, 발행 뒤 추가)

오너 지시(*"보강할 부분 네가 보강해줘"*)로 **같은 날 조건과 비차단 2건이 닫혔다.**
아래는 발행 후 추가된 사실이며, §5·§6 의 원 판정 근거는 그대로 둔다(발행 시점 기록이
바뀌면 다음 사람이 무엇이 원래 지적이었는지 알 수 없다).

| 항목 | 처리 | 실측 |
|---|---|---|
| **B-1**(Blocking) | `WritingAcceptApiTest::test_a_partial_accept_still_records_the_saved_version` 추가. **3-파일 세트**(`test_writing_accept.py`+`test_activity_actions.py`+`test_activity_log.py`, §4 가 재는 그 세트) 73 → **74 cells**, **파일 하나로는 50 → 51**(2026-08-10 검증 정정) | **양방향으로 문다** — 502 분기 record 삭제(under) · 같은 분기 이중 기록(over) 모두 **그 셀 하나**가 재실패(`1 failed, 57 passed`) |
| §6-① 페어링 | work_log Task 6 N10 행 · SoT v1.7.93 행을 실측대로 정정 | — |
| §6-③ 주석 | `activity/log.py` docstring "19 개 호출부" → 20 경로(호출 지점 21) | — |
| §6-② replay | **닫지 않았다** — 계약이 침묵하는 축이고 선택지 ⓐⓑⓒ 중 고르는 것은 오너 결정이다. 화면 슬라이스가 트리거 | — |

**★ 판정은 승격하지 않았다.** 오너 결정(2026-08-06)은 *"조건이 닫히면 그 기록의 최종
판정을 따른다"* 지만, **이 폐쇄를 한 것이 검증을 한 바로 그 세션**이라 승격까지 자기가
하면 독립성이 남지 않는다. **그래서 보강분(`test_writing_accept.py` +1 cell ·
`activity/log.py` 주석)은 지금 미검증 구간이고**, 승격은 다음 독립 세션 또는 오너
판단이다. 뒤에 오는 사람이 볼 것은 위 표의 양방향 뮤테이션 한 줄뿐이다.

## 7. Outstanding items

- ~~**B-1 은 커밋되지 않았다**~~ → **오너 지시로 같은 날 닫혔다**(§6-b). 남은 것은
  **판정 승격 여부**이며, 폐쇄를 검증 세션 자신이 했으므로 다음 독립 세션 또는 오너가
  본다. **보강분 자체가 지금 미검증 구간이다.**
- **§6-② replay 는 열려 있다** — 오너 결정 사안(선택지 ⓐⓑⓒ)이고 트리거는 화면 슬라이스.
- 이 기록 자체가 검증 인덱스 건수(229 → 230)·조건부 분포(66 → 67)를 움직이며,
  `test_docs_indexes.py` 의 판정 열 전수 셀이 subtest 를 1 늘린다
  (다음 전수 회귀 예상값 **`2249 / 1 / 2325`**, 측정값이 아니라 예고값이다).
- Slice 2 의 nginx 한 홉(`curl :5520/api/admin/users` = 401)은 여전히 재빌드 대기 —
  이 검증의 범위 밖이다.

## 8. Verdict

**합격** — 발행 시점 판정은 `조건부 합격`(조건 원문 아래)이었고, **그 조건이 닫힌 것을
2026-08-10 독립 세션이 재현해 승격했다**(오너 결정 2026-08-06: *"판정 열은 그 기록의 최종
판정이다"*). 승격 근거 기록: [`../2026-08-10/accept_activity_cell_reinforcement.md`](../2026-08-10/accept_activity_cell_reinforcement.md)
— 새 셀이 **네 방향**(삭제 · 이중 기록 · 리터럴 변조 · `target_id` 변조)으로 물고, 그 셀이
**유일 방어**임(502 분기를 지워도 전수 가드는 통과)까지 재확인됐다.

> **발행 시점 판정(원문, 보존)** — `**조건부 합격**` — 조건: SoT v1.7.93 이 "남긴다"고 명시한
> **502 partial envelope 분기를 잠그는 행위 셀**을 추가할 것(§5 B-1). 그때까지 그 분기는
> 계약이 요구하는 잠금이 없는 빈 칸이며, 삭제해도 전수 회귀가 green 이다.
>
> 조건은 같은 날 닫혔고(§6-b, 오너 지시), **승격을 그때 하지 않은 것은 폐쇄를 검증 세션
> 자신이 했기 때문**이다 — 승격 권한은 다음 독립 세션 또는 오너에게 있었다.

근거가 되는 사실:

- 분류표·리터럴·수(20/20/40·11/9·13)가 정본 3종과 문자 그대로 일치한다(§4.1).
- 성공·Gate 거부 두 분기는 양방향으로 잠겨 있고 격리도 옳게 상속된다(§4.2·§4.3).
- 회귀 기준선 `2246/4/2324`(보정 `2249/1`)가 skip 사유까지 재현된다(§4.5).
- **그러나 계약이 세 분기를 열거했는데 잠긴 것은 둘뿐이고**, 남은 하나는 코드를
  통째로 지워도 저장소 전체가 통과한다(§4.3) — 이 저장소가 `ObservedProvider`
  계측 누락으로 이미 값을 치른 "회귀는 green, 배포만 조용히 틀림"과 같은 형태다.

## 9. Reproduction

```bash
git checkout ca97f2b && git status --short          # 비어 있어야 한다
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' \
  ai_writte_system-test-mongo-1)" = healthy ]; do sleep 2; done

PYTHONPATH=. python3 -c "
from services.application.app.activity.actions import *
import services.application.app.activity.actions as m
print(len(ACTIVITY_ACTIONS), len(EXCLUDED_OPERATIONS), len(CLASSIFIED_OPERATIONS),
      len(m._CANONICAL), len(m._REVIEW))"          # 20 20 40 11 9

python3 -m pytest -q -rs                            # 2246/4/2324 + skip 사유 4줄

# B-1: 502 분기의 activity.record(...) 6줄 삭제 후
python3 -m pytest -q                                # 여전히 2246/4/2324 (Blocking)
git checkout -- services/application/app/routers/writing.py && git status --short
```
