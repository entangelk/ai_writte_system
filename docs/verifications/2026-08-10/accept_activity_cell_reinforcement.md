# 독립 검증 — accept 활동 로그 보강분(502 partial 셀 + 주석 + 문서 정정)

| 항목 | 값 |
|---|---|
| 날짜 | 2026-08-10 |
| 요청자 | 오너 |
| 검증자 | 독립 세션(보강을 한 세션이 아니고, 그 앞의 검증 세션도 아니다) |
| 대상 | 미검증 구간 2커밋 — `66f2845`(셀 + 주석) · `33fe4b2`(문서) |
| 정본 | [`system-contract-sot.md`](../../system-contract-sot.md) **v1.7.93** · [`plans/09-0-service-activity-log-decisions.md`](../../plans/09-0-service-activity-log-decisions.md) §"A2 추가 확정" · [`guides/verification.md`](../../guides/verification.md) §"Mutation testing" |
| 소스 상태 | HEAD `33fe4b2`, 작업 트리 clean |
| 머신 | **베타(GTX 1060 3GB)**, test-mongo ON — 어제 기록은 알파 실측이다 |
| 선행 검증 | [`2026-08-09/service_activity_log_accept_extension.md`](../2026-08-09/service_activity_log_accept_extension.md) **조건부 합격**. 이 기록은 **그 조건의 폐쇄분**만 본다 |

**이 검증이 존재하는 이유.** 어제 그 조건(B-1)을 닫은 것이 **조건을 낸 검증 세션 자신**이라
판정이 승격되지 않았고, 폐쇄분이 미검증 구간으로 남았다. 승격 권한은 *"다음 독립 세션 또는
오너"* 이며(HANDOFF · 그 기록 §6-b), 이 세션이 그 독립 세션이다.

## 1. Scope

1. 새 셀이 계약의 **502 partial 분기**를 실제로 잠그는가 — 양방향 + 검증자 추가 축
2. Blocking 의 전제 재현 — 전수 가드가 그 분기를 못 본다는 것이 지금도 참인가
3. 계약의 **세 분기 열거가 완전한가** — 저장 뒤에 던져질 수 있는 예외가 더 있는가
4. `activity/log.py` 주석이 바꾼 수(20 경로 · 호출 지점 21)의 코드 실측
5. `33fe4b2` 가 **정정한** N10 페어링의 재현 — 정정 자체가 검증 대상이다
6. 문서 숫자 주장 전량 대조 — 기준선 · 인덱스 건수 · 판정 분포 · 셀 수

## 2. Methodology

```bash
git show 66f2845; git show 33fe4b2                       # 대상 diff 전량
PYTHONPATH=. python3 -c "…activity.actions…"             # 분류 수를 코드에서 직접 센다
grep -rn 'activity\.record(' services/application/app/   # 호출 지점을 센다
docker compose -f docker-compose.test.yml up -d          # healthy 대기 후
python3 -m pytest -q -rs                                 # 전수 회귀 + skip 사유
python3 -m pytest -q tests/test_writing_accept.py tests/test_activity_actions.py
python3 -m pytest -q tests/test_writing_accept.py tests/test_activity_actions.py \
                     tests/test_activity_log.py          # 기록이 "73 → 74" 라 적은 세트
python3 -m pytest -q tests/test_docs_indexes.py
# 뮤테이션: 트리 clean 확인 → 변형 → 실행 → git checkout -- <path> → git status --short
```

트리가 clean 이고 대상이 **커밋된** 코드이므로 가이드 §"The restore rule" 의 clean-tree
분기(`git checkout -- <path>`)를 썼다. 뮤테이션 **매회 전후로** `git status --short` 가
비어 있음을 확인했고, 마지막 원복 뒤 `git diff HEAD --stat` 도 비어 있다.

**결과 판독은 요약 줄로 했다** — `grep FAILED` 는 `SUBFAILED` 를 놓친다(가이드 §★).

## 3. 계약에서 뽑은 경계 행렬 (이 슬라이스가 채워야 하는 칸)

SoT v1.7.93: *"기록 조건은 상태코드가 아니라 **정본이 바뀌었는가**"* — 세 분기를 이름으로
열거한다.

| # | 분기 | 계약이 요구하는 것 | 잠그는 셀 | 실측 |
|---|---|---|---|---|
| 1 | 성공(200 · `saved` 있음) | 남긴다 | `test_a_saved_accept_is_recorded_in_the_activity_log` | `170ea3a` (선행 검증이 확인) |
| 2 | Gate 거부(200 · `saved=null`) | **안 남긴다**(over-strict) | `test_a_bounced_accept_is_not_recorded` | `170ea3a` (선행 검증이 확인) |
| 3 | **502 partial**(version 저장 · 분석 job 실패) | 남긴다 | **`test_a_partial_accept_still_records_the_saved_version`** | **`66f2845` — 이 검증의 대상** |

**빈 칸 없음.** 그리고 §4.3 이 이 열거 자체가 완전함(넷째 분기가 없음)을 코드에서 확인한다.

## 4. Findings

### 4.1 새 셀은 그 분기를 잠근다 — 네 축 전부 재실패

[`tests/test_writing_accept.py:315`](../../../tests/test_writing_accept.py#L315). 기준선은
`58 passed / 79 subtests`(두 파일 세트).

| # | 방향 | 적용한 diff (`routers/writing.py`) | 재실패 |
|---|---|---|---|
| V1 | under | 502 분기의 `activity.record(...)` **6줄 삭제**([:1273](../../../services/application/app/routers/writing.py#L1273)) | `::test_a_partial_accept_still_records_the_saved_version` (1) — `1 failed, 57 passed` |
| V2 | over | 같은 분기에 동일 호출을 **한 번 더 삽입**(이중 기록) | 같은 셀 (1) — 동일 요약 |
| **V3** | under(신규) | 같은 분기의 리터럴만 `"draft_version_accepted"` → `"draft_version_saved"` | 같은 셀 (1) |
| **V4** | under(신규) | 같은 분기의 `target_id=exc.saved.draft_version.id` → `exc.target_draft.id` | 같은 셀 (1) |

V1·V2 는 보강 세션이 보고한 축이고 **재실패 셀·요약 줄까지 일치**한다. **V3·V4 는 이 검증이
추가한 축**이다 — 셀이 상태코드와 건수만 재고 페이로드는 안 보는(=공허한) 단정일 가능성을
닫으려는 것이며, 리터럴과 `target_id` 둘 다 실제로 물었다. 즉 이 셀은 "무언가 한 줄 남았다"가
아니라 **무엇이 남았는지**를 잠근다.

### 4.2 Blocking 의 전제는 지금도 참이다 — 전수 가드는 분기를 못 본다

V1(502 분기 통째 삭제) 아래에서 **`tests/test_activity_actions.py` 는 전부 통과했다**
(`1 failed, 57 passed` — 실패는 새 셀 하나뿐). 전수 가드
`ActivityActionClassificationTest::test_every_logged_route_actually_records` 는 endpoint
소스에 `activity.record(` 가 **있는지**만 보므로 같은 handler 의 성공 분기로 만족된다.

**그래서 이 셀은 중복 방어가 아니라 유일 방어다.** 지우면 어제의 구멍이 그대로 돌아온다.

### 4.3 계약의 세 분기 열거는 완전하다 (넷째 분기 없음)

계약이 세 개만 열거한 것이 **누락이 아닌지**를 코드에서 확인했다.
[`writing/accept.py`](../../../services/application/app/writing/accept.py) 에서 저장이
일어나는 지점은 `start_next_unit`(:127) · `save_draft`(:143) · `_replay`(:163·:174) 넷이고,
**그 뒤의 모든 경로가 `_finalize`(:179) 하나로 모인다.** `_finalize` 안에서 던져질 수 있는
것은 `except Exception` 이 감싼 **`WritingAcceptAnalysisError` 하나뿐**(:186)이며, 이것이 곧
502 partial 분기다. 나머지 예외(404·409·400·503·504·다른 502)는 **전부 저장 이전**에 난다.

따라서 "정본이 바뀌었는데 기록이 없는 경로"는 남아 있지 않다. **replay(:134·:137)는
`_finalize` 를 지나므로 기록된다** — 이것이 선행 기록 §6-② 가 연 replay 축이고 여전히 오너
결정 대기다(계약 침묵, 이 검증의 범위 밖).

### 4.4 주석이 바꾼 수는 코드와 일치한다

`activity/log.py:88` 이 *"19 개 호출부"* → *"20 개 경로(호출 지점은 21 — accept 가 성공·502
partial 두 분기에서 부른다)"*.

| 주장 | 실측 | 방법 |
|---|---|---|
| logged **20** | **20** (`LOGGED_OPERATIONS`) | `ACTIVITY_ACTIONS 20` · `_CANONICAL 11` + `_REVIEW 9` |
| 분류 전수 **40** | **40** (`CLASSIFIED_OPERATIONS`) · excluded 20 | 같은 모듈 |
| 호출 지점 **21** | **21** | `grep -rn 'activity\.record(' services/application/app/` — analysis 9 · drafts 5 · projects 4 · source_refs 1 · **writing 2** |

writing 이 2인 것이 곧 "경로 20 · 지점 21" 의 근거다. 주석은 정확하다.

### 4.5 N10 페어링 정정은 옳다 (정정 자체를 재현했다)

`33fe4b2` 가 SoT 행과 work_log 를 정정하며 *"over-strict 변이가 문 둘째 셀은
`test_a_saved_accept_is_recorded_in_the_activity_log` 가 아니라 기존
`test_non_pass_is_200_without_saved_artifacts`"* 라고 적었다. 그 변이를 다시 만들어 확인했다.

| 적용한 diff | 재실패 |
|---|---|
| 성공 경로의 `if result.saved is not None:` → `if True:`([:1301](../../../services/application/app/routers/writing.py#L1301)) | `test_a_bounced_accept_is_not_recorded` · **`test_non_pass_is_200_without_saved_artifacts`** — `2 failed, 56 passed` |

**정정된 표기와 문자 그대로 일치한다**(건수 2 · 셀 이름 둘). 원래 표기가 틀렸던 것도 함께
확인된다 — `test_a_saved_accept_is_recorded_in_the_activity_log` 는 이 변이에서 통과한다
(Gate 가 PASS 인 경로라 조건 제거가 관측을 바꾸지 않는다).

### 4.6 회귀 기준선과 문서 숫자

| 주장 | 실측 | 판정 |
|---|---|---|
| 전수 회귀 보정 `2250 / 1 / 2325` | **`2250 passed / 1 skipped / 2325 subtests in 939s`** | **일치** |
| skip 사유 | `test_chroma_adapter.py:490` live Chroma 1건뿐 | 일치 |
| `README.md` 기준선 `2,250 / 2,325` | 위와 동일 | 일치 |
| `test_docs_indexes.py` `13 cells / 240 subtests` | **`13 passed / 240 subtests`** | 일치 |
| 검증 인덱스 `46일치 · 230건` | 날짜 디렉터리 **46** · 기록 파일 **230** | 일치 |
| 판정 분포 합격 161 / 조건부 **67** / 불합격 2 | 인덱스 표 행에서 **161 / 67 / 2** (합 230) | 일치 |
| accept 확장 회귀 **+3 cells** | `170ea3a` +2 · `66f2845` +1 = **3** | 일치 |
| operation 77 무변 | tier 전수 셀 통과 | 일치 |

**★ 베타에서 원시값이 곧 보정값이다.** 알파는 `elasticsearch` 패키지가 없어 3건이 skip 되어
`2247/4` 를 보정해 왔는데, 이 머신에는 설치돼 있어 그 3 cells 가 실제로 돌았다. 즉 어제
알파에서 보정으로 얻은 `2250/1/2325` 를 **다른 머신이 원시로 재현**했다 — 보정이 옳았다는
독립 증거다. 소요는 939초(알파 185초, HANDOFF 가 적는 4~5배 차이와 부합).

## 5. Issues / Risks

### Blocking

**없다.** 계약이 요구하는 잠금 중 비어 있는 칸이 없고(§3), 새 셀은 네 방향으로 문다(§4.1).

### Hardening recommendations (비차단)

1. **★ "73 → 74 cells" 는 파일 하나의 수가 아니다 — 라벨이 잘못 붙었다.**
   [`service_activity_log_accept_extension.md`](../2026-08-09/service_activity_log_accept_extension.md)
   §6-b 표와 [work_log Task 8](../../daily_logs/2026-08-09/work_log.md) 의 Completed work 표가
   **`tests/test_writing_accept.py` 행에** `73 → 74 cells` 를 적었다. 그런데 그 파일은
   **50 → 51 cells** 다(`git show 66f2845^:… | grep -c '    def test_'` = 50, 현재 51).

   **숫자 자체는 맞다** — 출처는 같은 기록 §4 의 **3-파일 세트**(`test_writing_accept.py` +
   `test_activity_actions.py` + `test_activity_log.py`)이고, 그 세트를 test-mongo ON 으로
   돌리면 **정확히 `74 passed / 79 subtests`** 다(실측). 즉 값이 아니라 **귀속 대상**이 틀렸다.

   **왜 비차단인가**: 계약이 요구하는 잠금이 아니라 기록의 서술이고, 셀은 실재한다.
   **왜 그래도 적는가**: 이 저장소의 표준 확인법이 "그 파일을 열어 세어 보는 것"이라,
   다음 사람이 51 을 세고 기록과 23 만큼 어긋난 채 *"셀이 사라졌나"* 를 조사하게 된다.
   고치는 법은 두 표의 행 라벨을 3-파일 세트로 바꾸는 한 줄이다.

   > **폐쇄(2026-08-10, 발행 뒤 추가).** 오너 지시(*"보강이 필요한 부분 보강해줘"*)로 같은 날
   > 두 행을 정정했다 — 어제 기록 §6-b 와 [work_log Task 8](../../daily_logs/2026-08-09/work_log.md)
   > 이 이제 **파일 하나 50 → 51 · 3-파일 세트 73 → 74** 를 함께 적는다. 위 지적 원문은
   > 발행 시점 그대로 두었다(무엇이 지적이었는지 지워지면 안 된다). **판정은 원래 `합격`
   > 이므로 승격 문제가 없다** — 비차단 지적의 폐쇄일 뿐이다.

2. **replay 축은 여전히 열려 있다**(선행 기록 §6-② 승계) — 오너 결정 사안이고 트리거는 화면
   슬라이스다. 이 검증이 §4.3 에서 **replay 도 `_finalize` 를 지나 기록된다**는 코드 근거를
   더했다.

## 6. Outstanding items

- **선행 기록의 판정 승격이 이제 가능하다.** 조건(B-1)의 폐쇄를 **독립 세션이 재현**했으므로
  (§4.1·§4.2), 오너 결정(2026-08-06) *"판정 열은 그 기록의 **최종** 판정"* 에 따라
  [`service_activity_log_accept_extension.md`](../2026-08-09/service_activity_log_accept_extension.md)
  는 **합격**으로 승격된다. 인덱스 분포가 합격 161 → **162** · 조건부 67 → **66** 으로 움직인다.
- **이 기록 자체**가 인덱스 건수를 230 → **231**(날짜 46 → **47**일치)로, 판정 열 전수 셀의
  subtest 를 1 늘린다 — **다음 전수 회귀 예상값 `2250 / 1 / 2326`**(예고값이지 측정값이 아니다).
- 범위 밖으로 그대로 남는 것: Slice 2 의 nginx 한 홉(`curl :5520/api/admin/users` = 401,
  재빌드 대기) · dogfood 착수(GATE-1) · 화면(활동 타임라인) 슬라이스.
- **머신이 알파 → 베타로 바뀌었다**(이 세션 실측 `nvidia-smi` GTX 1060 3GB). HANDOFF 의
  머신 관측 절을 이 사실로 갱신했다.

## 7. Reproduction

```bash
git checkout 33fe4b2
docker compose -f docker-compose.test.yml up -d
until [ "$(docker inspect -f '{{.State.Health.Status}}' ai_writte_system-test-mongo-1)" = healthy ]; do sleep 3; done

python3 -m pytest -q -rs                                  # 2250 / 1 / 2325
python3 -m pytest -q tests/test_writing_accept.py tests/test_activity_actions.py   # 58
python3 -m pytest -q tests/test_writing_accept.py tests/test_activity_actions.py \
                     tests/test_activity_log.py           # 74  ← "73 → 74" 의 실제 세트
grep -c '    def test_' tests/test_writing_accept.py      # 51  ← 파일 하나는 이 값
PYTHONPATH=. python3 -c "from services.application.app.activity import actions as a; \
  print(len(a.LOGGED_OPERATIONS), len(a.CLASSIFIED_OPERATIONS), len(a._CANONICAL), len(a._REVIEW))"
grep -rn 'activity\.record(' services/application/app/ | wc -l   # 21

# 뮤테이션 V1~V4 · N10 — 전부 routers/writing.py 를 변형하고
#   python3 -m pytest -q tests/test_writing_accept.py tests/test_activity_actions.py
# 로 요약 줄을 읽은 뒤 git checkout -- services/application/app/routers/writing.py
```

## 8. Verdict

**합격** — blocking 결함 없음.

근거가 되는 사실:

- 계약이 열거한 세 분기가 **전부** 잠겨 있고, 어제 비어 있던 셋째 칸을 새 셀이 채운다(§3).
- 그 셀은 **네 방향**으로 문다 — 삭제(under) · 이중 기록(over) · **리터럴 변조** · **`target_id`
  변조**. 뒤의 둘은 이 검증이 추가한 축이며, 셀이 공허한 단정이 아님을 보인다(§4.1).
- 그 셀이 **유일 방어**임이 지금도 참이다 — 502 분기를 통째로 지워도 전수 가드는 통과한다(§4.2).
- 계약의 3분기 열거가 **완전**하다 — 저장 뒤 예외는 `_finalize` 의 하나뿐이다(§4.3, 코드 근거).
- 주석이 바꾼 수(20 경로 · 지점 21)가 코드 실측과 일치한다(§4.4).
- **정정한 N10 페어링이 재현된다** — 정정 전 표기가 틀렸던 것까지 확인된다(§4.5).
- 기준선 `2250/1/2325` 가 **다른 머신에서 원시값으로** 재현된다 — 알파의 보정이 옳았다는
  독립 증거다(§4.6).

비차단 1건(§5-1)은 기록의 숫자 **귀속** 오류이며 값은 맞다 — 고치는 것은 두 표의 행 라벨
한 줄이고, 판정에 영향하지 않는다.
