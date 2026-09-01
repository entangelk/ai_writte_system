# Work Log — 2026-09-01

## Session 1 — 장면 메모 Slice 2 독립 검증

### Goals

- HANDOFF "다음 순서" 지시: **Slice 2(명시적 저장 API와 활동 기록) 독립 검증** — 구현이
  아니라 반증. 대상 커밋 `edec884`(본체)·`a0257d9`(README 핀).
- 오너 요청 문언: "검증하고 의심하고 또 의심해줄래" — 구현자 변이 재실행에 더해
  **검증자 독자 변이**로 구현자가 안 덮은 방향을 찌른다.

### Completed work

- 검증 기록: [`verifications/2026-09-01/scene_note_slice_2.md`](../../verifications/2026-09-01/scene_note_slice_2.md)
  — 판정 **조건부 합격**(조건 = 연타 창 리터럴 "5초" 핀 셀). 인덱스 등재 + 건수 주장
  4곳(최상위 README 2·docs/README·검증 인덱스) 264→265·60→61일치·분포 조건부 76→77 갱신.
- **경계 행렬**: SoT v1.8.13 행·Phase 1 조항·페이즈 문서 §Slice 2 검증 16항·결정 브리프
  D4 추가 확정에서 행렬을 먼저 세워 46셀에 대응 — 계약 요구 분기·리터럴 중 빈 칸 1건(B1).
- **변이 13종**(구현자 9종 중 7종 재실행 + 독자 5종 + M9 두 구성):
  - 구현자 M1(9)·M3(1)·M4(1)·M5(1)·M7(5)·M8(1)·M9-삽입(6) 재실행 — **전부 기록된
    셀 수와 동일하게 재실패**. M9의 "6 failed"는 *삽입* 구성(try 앞 추가, 가드 유지)으로
    재현 — work_log 표기는 "이동"이었으나 이동 구성(가드 삭제)은 2 failed로, 두 독법 모두
    계약 핵심 셀을 문다.
  - 독자 변이: 읽기 순서 이동(7셀)·모델 경계 `>=`(1셀)·소유권 deps 제거(2파일 6fail —
    tier 행렬이 재유도로 잡음)·**행위자 출처 소유자 조회(0셀 — H2)**·**창 리터럴
    5초→6초(0셀 — B1 차단)**.
- **전수**(test-mongo ON, 38분 34초): 2663 passed / 9 failed / 1 skipped / 3082 subtests +
  7 SUBFAILED — **9 failed 전부 `test_docs_indexes`가 이 세션이 실행 중 만든 미등록
  기록 파일을 잡은 것**(제품 셀 전부 green). 등재 뒤 `test_docs_indexes` 단독
  **13 passed / 275 subtests**(판정 열 +1 규칙과 일치). **다음 전수 기대값
  2665 / 1 / 3089**.
- 집중 재현: 가드 4파일 **191 passed / 1116 subtests**, collect-only **2666** — 구현자
  주장과 동일.

### Issues found

1. **B1(차단) — 연타 창 "5초" 리터럴 무핀.** SoT v1.8.13·결정 브리프·페이즈 문서가 모두
   `SCENE_NOTE_DOUBLE_SUBMIT_WINDOW`(5초)를 오너 확정값으로 명시하는데, 회귀는 상수를
   상징적으로만 참조한다(`self.now += SCENE_NOTE_DOUBLE_SUBMIT_WINDOW`). 변이 실측:
   `seconds=5`→`6`으로 바꿔도 46셀 전부 green — 창이 위로 자라는 방향은 무신호다. 같은
   계열로 12000(상한)·200(미리보기)도 무핀(H3, Slice 0·1 유래).
2. **H1 — SoT v1.8.13 행의 "27→46" 오기.** 실측 23→46(+23; `git show edec884~1` grep로
   확인). work_log 세션 5는 바르게 적었다. 정본 행의 회귀 문언 정정 필요(선례: 세션 2
   hardening #5의 in-place 정정). 커밋 메시지의 같은 오기는 불변 — 기록만 남김.
3. **H2 — 행위자 셀 docstring 과잉 주장.** `test_the_row_names_the_actor_not_the_owner_field`가
   소유자/세션 구분을 잠긴다고 읽히지만 이 경로는 grant가 GET/HEAD뿐이라 소유자만 쓸 수
   있어 둘이 구조적으로 항상 같다 — 소유자 조회 변이가 46셀 통과. 셀은 유효하되 주장
   범위를 docstring에 바로잡을 것.
4. **우발 실측 — 기록 가드 증명.** 전수를 기록 등재 전에 돌리는 실수가 각자 저지를
   확인해 줬다(인덱스 미등재·건수 4곳·일수·분포 합 전부 실패). 검증 기록의 Findings §5에
   환경 그대로 남겼다.

### Decisions

- 없음(검증 세션 — 오너 결정 필요 사항은 B1 폐쇄 시점뿐: 이번 세션에서 바로 닫을지,
  다음 세션에 넘길지).

### Next steps

- **B1 폐쇄**: 핀 셀 1개(5초; 권고 — 12000·200 같은 형태 셋으로) + SoT v1.8.13 행 회귀
  문언 정정(H1) + H2 docstring 정정. 폐쇄 후 전수 기대값 2666 / 1 / 3089(collect 2667).
- 폐쇄 뒤 **Slice 3(별도 메모 화면)** 착수.

## Session 2 — Slice 2 검증 보강 폐쇄

### Goals

- 독립 검증의 차단 B1(연타 창 5초 리터럴 무핀)을 닫고, 동일 원인의 H3(본문 12000자·미리보기
  200자 무핀) 및 H1·H2 문서 정합 지적을 함께 해소한다.

### Completed work

- 리터럴 핀 셀 3개를 추가했다. `tests/test_scene_notes.py`는
  `SCENE_NOTE_MAX_CHARS == 12000`, `tests/test_scene_notes_api.py`는
  `SCENE_NOTE_DOUBLE_SUBMIT_WINDOW == timedelta(seconds=5)`와
  `SCENE_NOTE_PREVIEW_MAX_CHARS == 200`을 각각 직접 단정한다. 각 docstring은 SoT 버전·오너
  확정일과 under/over 방향의 짝 가드를 명시한다. 동작 경계 셀은 그대로 남겨 값 고정과 행동
  검증을 분리했다.
- SoT v1.8.13 변경 이력의 사실 오기 `27→46`을 실측값 **`23→46(+23)`**으로 in-place 정정했다.
  과거 커밋 메시지는 불변 기록이므로 수정하지 않았다.
- 행위자 셀 docstring을 현재 소유자 전용 PUT 구조(소유자 ID와 세션 사용자 ID가 항상 같음)에
  맞춰 좁혔다. 셀의 실제 단정은 유지했다.
- mutation verification(체크포인트 `836e6cf` 뒤, 각 변이 뒤 `git restore`·clean 확인):

  | 변이 | 파일:줄 | 재실패 셀 |
  |---|---|---|
  | `12000 → 12001` | `core_sot/service.py:102` | `SceneNoteBoundaryTest.test_the_owner_approved_body_limit_literal_is_12000_characters` |
  | `5초 → 6초` | `routers/notes.py:64` | `SceneNoteLiteralTest.test_the_owner_approved_double_submit_window_is_five_seconds` |
  | `200 → 201` | `routers/notes.py:47` | `NotePreviewTest.test_the_owner_approved_preview_limit_literal_is_200_characters` |

### Issues found

- 없음. B1과 H1~H3은 이 세션의 회귀·문서 보강으로 폐쇄한다.

### Decisions

- 검증 권고대로 세 리터럴을 같은 형식으로 함께 핀했다. 모두 이미 Approved SoT에 명시된
  오너 확정값이므로 새 제품 결정이나 SoT 버전 상승이 아니다.

### Next steps

- 검증 완료: 새 핀 3개 + `test_docs_indexes.py` = **16 passed / 275 subtests**. Slice 3 화면
  작업에서 frontend 전수를 함께 측정한다.

## Session 3 — 최종 저장·분석 연동 결정 브리프

### Goals

- 도그푸드에서 발견한 “일반 저장 뒤 분석 시점을 놓침”을 확인하고, Slice 3 화면과 함께
  시행할 수 있는 최종 저장 상태·분석 연동 계약을 구현 전에 정리한다.

### Completed work

- [`final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md)를 작성하고 계획
  인덱스에 등재했다. 일반 저장은 version만 만들고, 수동 분석과 `채택하고 저장`의 분석 job은
  snapshot 키를 공유한다는 실제 구현을 대조했다.
- 오너의 방향을 브리프에 반영했다: final은 Scene당 한 번만 실행하고, 뒤의 편집은 일반 저장과
  수동 분석으로 처리한다. 추천은 final snapshot을 보존한 채 최신 version과 다르면
  `최종 저장 후 수정됨`으로 표시하는 B안이다.
- 오너가 D1~D3 모두 B로 확정했다. 편집기뿐 아니라 작업실에서도 최신 저장본이 분석되지
  않았음을 상기시킨다. 이 상태는 `마지막 분석 시간`이 아니라 최신 snapshot과 성공 analysis
  job의 `snapshot_id`가 같은지로 계산한다. 현재 job에 시각 필드가 없고, snapshot 동일성이
  비동기 재시도 순서에도 안전하기 때문이다.
- 장/Scene compacting과 다음 장면 프롬프트 주입은 이번 slice에서 제외했다. 현재 생성 문맥은
  최신 Scene의 최근 문단과 승인된 canonical memory이며, 분석 후보의 자동 승격은 정본 정책을
  위반하므로 별도 결정을 필요로 한다.

### Issues found

- 현재 Draft 모델에는 archive 외의 수명 상태가 없어 final을 프론트 상태로만 두면 재접속·다른
  기기에서 사라진다. 서버 정본 marker와 API 계약이 필요하다.

### Decisions

- **[사용자 방향, 2026-09-01]** Scene의 최종 저장은 한 번만 가능하게 하고, 그 뒤 수정은 일반
  저장과 수동 분석으로 처리한다. 화면은 final·분석·후속 수정 상태를 구별해 보여야 한다.
- **[사용자 확정, 2026-09-01]** D1=B(최초 final snapshot 보존·후속 수정됨), D2=B(저장/final
  확정 뒤 분석 job·장애는 분석 필요), D3=B(텍스트 상태 배지·비활성 final·수동 분석 안내)로
  확정했다. latest snapshot이 `succeeded` job과 다르면 작업실도 `분석 필요`를 표시한다.
- 분석 결과는 새 결과가 기존 canonical memory나 사용자의 편집을 자동으로 덮지 않는다. 현재
  candidate edit은 append-only successor를 만들어 원본을 `superseded`로 보존하고 canonical로
  승격하며, conflict는 review queue에서 검토한다. 서로 다른 snapshot의 동일 본문을
  content-hash로 생략할지는 분석기 버전 정책과 함께 별도 결정한다.

### Next steps

- final-save를 Slice 3 화면 작업과 묶어 구현한다. 구현 전 `finalized_snapshot_id` 저장 위치,
  final route·응답의 analysis 상태, 작업실 조회 payload와 회귀 행렬을 세부 구현 계획으로
  내리고, 구현 시 SoT·OpenAPI·`schema.d.ts`·활동 분류표를 함께 갱신한다.
