# 2026-08-10 작업 로그

## Goals

- 핸드오프·어제 로그가 가리키는 **다음 작업**을 집는다.
- 어제 남은 **미검증 구간**(accept 활동 로그 보강분 `66f2845`·`33fe4b2`)을 독립 검증한다.
- 조건이 실제로 닫혔으면 **판정 승격**까지 처리하고, 인덱스·기준선 숫자를 정합으로 만든다.

---

## Task 1 — 보강분 독립 검증 (`66f2845`·`33fe4b2`)

검증 서사·경계 행렬·재현 명령은 기록에 있다(여기 복사하지 않는다):
[`verifications/2026-08-10/accept_activity_cell_reinforcement.md`](../../verifications/2026-08-10/accept_activity_cell_reinforcement.md).

### User Decisions and Rationale

- **오너 지시(2026-08-10)**: *"핸드오프와 어제자 데일리로그 확인해서 다음작업 진행해줘."*
  다음 작업을 문서가 정하게 하라는 것. HANDOFF Next Tasks 와 어제 Task 8 이 **미검증 구간 =
  보강분**을 명시하고, 이 저장소의 표준 리듬은 *"미검증 구간을 남긴 채 다음 슬라이스를 열지
  않는다"* 이며 **어제 오너가 화면 슬라이스·재빌드·dogfood 를 제치고 검증을 고른 선례**가
  있다. 그래서 화면(활동 타임라인)이 아니라 **검증**을 집었다. 화면은 새 슬라이스라
  오너 브리프가 선행한다.

### 판정

**합격 — Blocking 0**, 비차단 1건.

| 축 | 결과 |
|---|---|
| 새 셀이 502 partial 분기를 잠그는가 | **네 방향 전부 재실패**(아래 표) |
| 전수 가드가 분기를 못 본다는 Blocking 전제 | 지금도 참 — V1 아래 `test_activity_actions.py` 전부 통과 |
| 계약의 3분기 열거가 완전한가 | **완전** — 저장 뒤 예외는 `_finalize` 하나(코드 근거) |
| 주석이 바꾼 수(20 경로 · 지점 21) | 코드 실측 일치 |
| `33fe4b2` 가 정정한 N10 페어링 | **정정대로 재현**(2 cells) |
| 기준선 `2250/1/2325` | **베타 원시값으로 재현**(939s) |

### 뮤테이션 (5종 — 2종은 재현, **3종은 이 세션이 추가**)

전부 [`routers/writing.py`](../../../services/application/app/routers/writing.py) 를 변형하고
`pytest -q tests/test_writing_accept.py tests/test_activity_actions.py`(기준선 `58 passed`)로
요약 줄을 읽었다.

| # | 방향 | 적용한 diff | 재실패 셀 |
|---|---|---|---|
| V1 | under | 502 분기의 `activity.record(...)` **6줄 삭제**(:1273) | `test_a_partial_accept_still_records_the_saved_version` (1) — `1 failed, 57 passed` |
| V2 | over | 같은 분기에 동일 호출 **한 번 더 삽입** | 같은 셀 (1) |
| **V3** | under | 같은 분기 리터럴만 `"draft_version_accepted"` → `"draft_version_saved"` | 같은 셀 (1) |
| **V4** | under | 같은 분기 `target_id=exc.saved.draft_version.id` → `exc.target_draft.id` | 같은 셀 (1) |
| **N10 재현** | over | 성공 경로 `if result.saved is not None:` → `if True:`(:1301) | `test_a_bounced_accept_is_not_recorded` · `test_non_pass_is_200_without_saved_artifacts` (2) — `2 failed, 56 passed` |

**V3·V4 를 추가한 이유**: V1·V2 만으로는 셀이 *"상태코드와 건수"* 만 재는 공허한 단정일
가능성이 남는다. 리터럴과 `target_id` 를 각각 흔들어 **무엇이 남았는지**까지 잠근다는 것을
확인했다. 둘 다 물었다.

**N10 을 재현한 이유**: 그 페어링 **정정 자체가 `33fe4b2` 의 산출물**이라 검증 대상이다.
정정된 표기와 문자 그대로 일치했고, 정정 전 표기(`test_a_saved_accept_is_recorded_…`)가
틀렸던 것도 함께 확인됐다 — 그 셀은 이 변이에서 통과한다(Gate PASS 경로라 조건 제거가
관측을 안 바꾼다).

### ★ 이 검증이 새로 채운 축 — 계약의 3분기 열거가 완전한가

어제 검증은 *"계약이 열거한 셋 중 하나가 빈 칸"* 을 봤다. 이 세션은 **열거 자체가 누락이
아닌지**를 물었다 — 계약이 세 개만 적은 것이 옳은가.

[`writing/accept.py`](../../../services/application/app/writing/accept.py) 에서 저장 지점은
넷(`start_next_unit` :127 · `save_draft` :143 · `_replay` :163·:174)이고 **그 뒤 모든 경로가
`_finalize`(:179) 하나로 모인다.** `_finalize` 가 던질 수 있는 것은 `except Exception` 이
감싼 **`WritingAcceptAnalysisError` 하나뿐**(:186) = 502 partial 분기다. 나머지 예외는 전부
저장 **이전**에 난다.

**결론: "정본이 바뀌었는데 기록이 없는 경로"는 남아 있지 않다.** 부수로, **replay 도
`_finalize` 를 지나므로 기록된다**는 코드 근거가 나왔다 — 어제 비차단 ②(replay 가 이벤트를
매번 추가)의 정확한 기전이며, 여전히 오너 결정 대기다.

### Issues found — 비차단 1건: "73 → 74 cells" 는 파일 하나의 수가 아니다

**문제.** 어제 기록 §6-b 표와 work_log Task 8 Completed work 표가 **`tests/test_writing_accept.py`
행에** `73 → 74 cells` 를 적었다. 그 파일은 실제로 **50 → 51 cells** 다.

**원인.** 숫자 자체는 맞고 **귀속 대상이 틀렸다**. 73/74 의 출처는 같은 기록 §4 의
**3-파일 세트**(`test_writing_accept.py` + `test_activity_actions.py` + `test_activity_log.py`)
이며, 그 세트를 test-mongo ON 으로 돌리면 정확히 `74 passed / 79 subtests` 다(실측).

**왜 비차단인가.** 계약이 요구하는 잠금이 아니라 기록의 서술이고, 셀은 실재하며 네 방향으로
문다. **왜 그래도 적는가.** 이 저장소의 표준 확인법이 *"그 파일을 열어 세어 보는 것"* 이라,
다음 사람이 51 을 세고 23 만큼 어긋난 채 *"셀이 사라졌나"* 를 조사하게 된다.

**처리.** **고치지 않았다** — 가이드 §*"the verifier does not silently fix the defect"*.
고치는 법은 두 표의 행 라벨을 3-파일 세트로 바꾸는 한 줄이고, 반영은 오너 판단이다.

### 판정 승격 (이 세션이 한 것)

어제는 **조건을 낸 검증 세션 자신이 조건을 닫아** 판정을 올리지 않았고, 승격 권한을
*"다음 독립 세션 또는 오너"* 로 남겼다. 이 세션이 그 독립 세션이고 폐쇄를 재현했으므로,
오너 결정(2026-08-06) *"판정 열은 그 기록의 **최종** 판정이다"* 에 따라 승격했다.

| 대상 | 처리 |
|---|---|
| [`service_activity_log_accept_extension.md`](../../verifications/2026-08-09/service_activity_log_accept_extension.md) §8 | `조건부 합격` → **`합격`**. **발행 시점 원문을 인용 블록으로 보존**했다(무엇이 원래 지적이었는지 지워지면 안 된다) |
| `docs/verifications/README.md` | 인덱스 판정 열 승격 + 새 행 · 건수 230 → **231** · 46 → **47**일치 · 분포 합격 161 → **163** · 조건부 67 → **66** |
| `README.md` · `docs/README.md` | 같은 수 세 자리 + 분포 문장 |

**★ 분포가 +2 인 이유**: 승격 1(조건부 → 합격) + 이 기록 신규 1. 합 231 = 163 + 66 + 2.

### 머신 전환 관측 (알파 → 베타)

`nvidia-smi` **GTX 1060 3GB** = 베타다(어제 기록은 알파 실측). HANDOFF 전환 절차대로 확인:
HEAD `33fe4b2` clean · `docker compose ps` 는 `frontend`(healthy)·`worker`·`generation_worker`
셋뿐 · test-mongo 는 회귀 때만 올렸다 내렸다.

**★ 이 전환이 준 뜻밖의 증거**: 알파는 `elasticsearch` 패키지가 없어 3건이 skip 돼
`2247/4` 를 **보정**해 `2250/1` 을 얻어 왔는데, 베타에는 그 패키지가 있어 3 cells 가 실제로
돌았다 — 즉 **보정값을 다른 머신이 원시값으로 재현**했다. 보정이 옳았다는 독립 증거다.
소요는 939초(알파 185초).

### Verification

| 검사 | 결과 |
|---|---|
| 전수 회귀(베타, test-mongo ON) | `2250 passed / 1 skipped / 2325 subtests in 939s` — **원시값이 곧 보정값** |
| skip 사유 | live Chroma 1건뿐(`test_chroma_adapter.py:490`) |
| 문서 갱신 후 `test_docs_indexes.py` | `13 cells / **241** subtests`(240 → +1, 새 기록 1건) |
| 문서 갱신 후 전수 회귀 | `2250 / 1 / **2326**` |
| 뮤테이션 전후 `git status --short` | 매회 비어 있음 · 마지막 원복 뒤 `git diff HEAD` 도 비어 있음 |

### 아직 안 한 것 (의도)

- **비차단 1건(라벨 정정)** — 검증자가 고치지 않는다. 오너 판단.
- **replay 축** — 계약 침묵, 오너 결정 사안. 트리거는 화면 슬라이스.
- **화면(활동 타임라인)** — 새 슬라이스라 오너 브리프 선행.
- **스택 재빌드 · nginx 한 홉 · dogfood 착수** — 오너 대기 유지.

### Next steps (다음 작업자에게)

1. **미검증 구간이 없다.** 보강분까지 독립 검증이 끝났고 판정도 승격됐다.
2. **자연스러운 다음은 화면(활동 타임라인)** — API 는 operation 77 로 서 있고 `schema.d.ts` 도
   재생성돼 있다. **새 슬라이스이므로 오너 decision brief 가 먼저다**(replay 표시 방식이 그
   브리프 안에서 함께 결정되는 자리다 — 어제 비차단 ②의 트리거가 바로 이것이다).
3. **오너 대기 두 건 유지**: 재빌드 후 `curl :5520/api/admin/users` = 401 · dogfood 착수(GATE-1).
