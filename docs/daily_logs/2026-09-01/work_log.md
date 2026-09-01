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
- **[구현 전 발견, 2026-09-01]** 현재 analysis job은 브라우저의 별도 `/run` 요청이 있어야
  실행되고 worker가 없다. final route가 job만 만들면 `pending`에 멈춘다. 따라서 D4(서버 동기
  실행 권장 / durable worker / 브라우저 후속 / job만 생성)를 오너 결정으로 열었다. D4가 없이는
  “최종 저장하면 분석”의 실제 실행·사용량 정산 경로를 임의로 정할 수 없다.
- **[사용자 확정, 2026-09-01]** D4=A를 선택했다. final API는 marker·snapshot을 먼저 확정한
  뒤 기존 runner를 동기로 실행하고, 실패하면 저장을 보존한 partial 결과와 `분석 필요`를 남긴다.
- 분석 결과는 새 결과가 기존 canonical memory나 사용자의 편집을 자동으로 덮지 않는다. 현재
  candidate edit은 append-only successor를 만들어 원본을 `superseded`로 보존하고 canonical로
  승격하며, conflict는 review queue에서 검토한다. 서로 다른 snapshot의 동일 본문을
  content-hash로 생략할지는 분석기 버전 정책과 함께 별도 결정한다.

### Next steps

- final-save를 Slice 3 화면 작업과 묶어 구현한다. `finalized_snapshot_id` 저장 위치, final
  route·응답의 analysis 상태, 작업실 조회 payload와 회귀 행렬을 구현하고 SoT·OpenAPI·
  `schema.d.ts`·활동 분류표를 함께 갱신한다.

## Session 4 — final-save D4=A 체크포인트 독립 검증

### Goals

- 오너 요청: "작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래" — D4=A 기준
  구현 체크포인트(커밋 `832089b`·`0922a24`)의 독립 검증. 구현자 보고(컴파일·분류 가드 18/193·
  tsc 확인 완료, final API 회귀 셀·문서 갱신 잔여)를 사실로 받지 않고 반증.

### Completed work

- 검증 기록: [`verifications/2026-09-01/final_save_analysis_checkpoint.md`](../../verifications/2026-09-01/final_save_analysis_checkpoint.md)
  — 판정 **불합격**. 인덱스 등재 + 건수 4곳(최상위 README 2·docs/README·검증 인덱스) 265→266·
  분포 불합격 3→4 갱신, 등재 뒤 `test_docs_indexes` 단독 13 passed / 276 subtests.
- **경계 행렬**: 확정 계약(final-save-analysis-decisions.md) 문언에서 14행을 먼저 세웠다.
- **프로브**(`verifications/2026-09-01/repro_final_save_flow.py`, 커밋): 인메모리 TestClient로
  커밋 상태 그대로의 finalize 첫 요청이 **503**(dedupe 표 무매핑), 표를 런타임 주입하면 **500**
  (`_require_active_project_and_draft` →None 반환값 오용)임을 관측 — 성공 경로 부재. B1·B2를
  패치해 우회한 행렬은 13/14 준수(잔여 H1: runner 실패 시 응답 job 상태 낡음).
- **작업자가 안 돌린 suite**: `test_quota_enforcement_api.py` 2 failed(B1·B3) · 프런트 vitest
  3 failed(B5 — 상태 바 pin + 디자인 토큰 2, `| tail`이 exit code를 삼켜 green으로 오독되는
  함정 포착) · 백엔드 전수 **11 failed / 2659 passed / 1 skipped / 3031 subtests**(39:26) —
  11 failed 전부 이 슬라이스 유래로 귀속 완료(B1·B3·mypy(B2 증거)·B6 5셀·B7·B8·B9).
- **변이 3종**(유료 행 제거 4failed·활동 행 제거 2failed·경로 리터럴 4failed+wiring) 전부
  재실패·복원 확인. 주장 수치(18/193·tsc·schema.d.ts byte-identical)는 전부 재현 — 보고 자체는
  정직했으나 커버리지가 실행 경로 전체를 비껴갔다.
- HANDOFF ①-a를 검증 결과(차단 9건·재검증 조건)로 재작성.

### Issues found

1. **차단 9건(B1~B9, 상세는 검증 기록)** — 뿌리는 하나: 요청 1건·돌릴 수 있는 가드 suite를
   실행하지 않은 채 "확인 완료"로 보고. 커밋 시점에 mypy 가드·dedupe 가드가 이미 red였다.
2. **H2(오너 판단 필요)** — 분석 실패의 HTTP 얼굴: 구현은 200+`analysis_error`, D2=B 권고문은
   accept의 502 partial 선례를 인용. 확정 계약 본문은 상태코드를 못 박지 않아 계약 내 긴장.
3. **H6** — 프런트 상태 바 3항 연산에 idle 분기가 없어 저장 이력 없는 새 장면이 "분석 완료"로
   오표시(구현 전 "미실행"). B5에서 깨진 pin 셀이 바로 이것을 지키던 셀.

### Decisions

- 없음(검증 세션 — 결함 폐쇄 방향과 H2 판정은 오너 결정 사항).

### Next steps

- **B1~B9 폐쇄 후 재검증**(경계 행렬 14행 + repro S0~S13이 회귀 셀 뼈대). 다음 전수 기대값은
  B 폐쇄·셀 신설 후 다시 잰다. H2 오너 판정 선행 권장(502 채택 시 봉투·프런트 에러 경로 수정).

## Session 5 — final-save 검증 보강

### Goals

- 독립 검증이 확인한 B1~B9와 H1·H6을 실제 실행 경로에서 닫고, H2의 HTTP 계약 충돌은
  오너가 판단할 수 있는 결정 브리프로 정리한다.

### Completed work

- 커밋 `66ece84`에서 B1(dedupe `draft_finalize`)·B2(활성 project 확인 함수의 `None` 반환값
  오용)·B4/B6(기존 router 조립 호환)·B5/H6(상태 바 pin·정의된 danger token·초기 장면의
  `분석 미실행`)·B7(활동 라벨)·B8(payload 키)·B9(tier 행렬)를 보강했다.
- H1도 runner 예외 뒤 저장소에서 job을 다시 읽도록 해, 응답의 `analysis_job.status`가
  실제 실패 상태와 어긋나지 않게 했다.
- B3 응답 선언은 처음 보강에서 save/final에 반대로 배선된 것을 focused wiring guard가
  찾아냈다. final에만 billable 402/429를 선언하도록 바로잡고 OpenAPI/`schema.d.ts`를
  재생성했다.
- 확인: `DedupeMappingTest` + `BillableRouteWiringTest` **8 passed / 220 subtests**,
  활동 라벨 **6 passed / 39 subtests**, `py_compile`, `git diff --check` 통과.

### Issues found

1. **H2는 여전히 오너 결정이 필요하다.** final marker/snapshot 저장은 성공하고 동기 분석만
   실패할 때 현재 구현은 `200 + analysis_error`다. D2 설명의 accept 502 partial 선례와
   문언 충돌하므로 상태코드를 정본으로 못 박아야 한다.
2. 이 실행 환경은 약 30초 뒤 장기 pytest·Vitest/tsc 프로세스를 강제 종료해 전수 종료값을
   이 세션에서 얻지 못했다. 종료된 process가 남지 않음을 확인했으며, 다음 재검증은 제한 없는
   실행 환경에서 S0~S13과 관련 전체 suite로 마무리한다.

### Decisions

- 없음. H2를 D5로 분리해 [`final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md)에
  A(200 + payload, 권고) / B(502 partial envelope) 선택지를 기록했다.

### Next steps

- 오너가 D5를 선택하면 API 응답 계약·프런트 처리·회귀 셀을 해당 정본으로 고정하고,
  repro S0~S13 및 백엔드/프런트 관련 전수를 다시 측정해 불합격 판정을 갱신한다.

## Session 6 — final-save 보강 재검증

### Goals

- 오너 요청: "보강한거 재검증해줘" — 불합격 판정 뒤 보강된 커밋 `66ece84`·`30a9194`의
  폐쇄 주장(B1~B9·H1·H6, 역배선 발견·수정)을 독립 재검증.

### Completed work

- 검증 기록: [`verifications/2026-09-01/final_save_hardening_recheck.md`](../../verifications/2026-09-01/final_save_hardening_recheck.md)
  — 판정 **조건부 합격**(조건: R1·R2 프런트 red 2셀 + B4 suite 편입 + D5 확정). 인덱스 등재·
  건수 4곳 266→267·분포 조건부 77→78, 등재 뒤 `test_docs_indexes` 단독 13/277 green.
- **백엔드 폐쇄 실측**: B1(dedupe 행)·B2(문장형+`_require_draft`)·B3(유료 402/429·무료 복원,
  생성 스펙 직독)·B6(기본인자)·B7(라벨 27)·B8(키 핀 4)·B9(tier 74/100)·H1(재조회) 전부 확인.
  변이 M-A(dedupe 행) 1fail·M-B(B2 되돌림) 프로브 rc=1·M-C(H1 제거) S6 기명 1fail·
  M-D(CSS 되돌림) 토큰 2셀 — 신규 잠금 전부 물림. 구현자 주장 수치(8/220 등)도 정확히 재현.
- **프로브 전환본**: 패치 없이 현재 코드로 S1~S13 **41단정 전부 통과** — D4=A 실행 경로가
  끝까지 돈다.
- **전수(백그라운드, 제한 없는 실행)**: 백엔드 **7 failed / 2667 passed / 3107 subtests** —
  7 failed 전부 `test_docs_indexes`가 이 기록 미등재를 잡은 것, **제품 셀 0**(선행 11 failed
  소멸). 프런트 **3 failed / 382 passed** — 슬라이스 귀속 2셀(R1·R2) + App 관리자 라우팅 1건은
  단독 28/28 green인 부하 플레이크(비귀속).

### Issues found

1. **R1(조건)** — `--danger-600` 프리미티브 직접 사용으로 designTokens semantic 라우팅 셀 red.
   선행 검증 하드닝 권고가 이 방향을 제시했던 점을 정정 — 폐쇄는 semantic 토큰 정의(예:
   `:root`에 `--status-danger: var(--danger-600)`)로.
2. **R2(조건, 실앱 회귀)** — H6 수정이 라벨 우선순위를 `draft.analysis_*`로 옮겼는데 수동 분석
   경로는 그 필드를 갱신하지 않는다(`AnalysisTrigger`는 `onStatusChange`만). 수동 분석 성공 후에도
   상태 바가 "분석 필요" 고정 — 확정 계약 "최신 snapshot succeeded = 분석 완료" 위반 표시.
   pin 셀이 이 회귀를 잡은 채 red.
3. **B4 잔여(조건)** — finalize 분기의 pytest 셀 부재. 잠금은 커밋된 프로브가 홀로 담당(M-B는
   크래시 잠금이라 기명 단정화 권고).
4. **D5 미확정** — A(200, 권장)/B(502 partial) 오너 결정 대기. 결정 전 HTTP 계약·셀·502 선언
   정리 불가.

### Decisions

- 없음(검증 세션 — D5는 오너 결정 대기).

### Next steps

- D5 결정 → HTTP 계약 고정·회귀 셀 작성(502 선언 정리 포함).
- R1·R2 수정 + B4 셀 편입 후 3차 재검증(프로브 + 전수 기대치 재계산).
- SoT v1.8.13·CHANGELOG 문서 정합성(구현자 잔여 목록)은 R1·R2와 함께 정리.
