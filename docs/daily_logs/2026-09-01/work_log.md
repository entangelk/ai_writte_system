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

## Session 7 — final-save 재검증 조건 보강

### Goals

- `final_save_hardening_recheck.md`의 조건 R1·R2·B4를 닫고, D5의 HTTP 얼굴은 오너가
  선택할 때까지 구현 계약을 바꾸지 않는다.

### Completed work

- R1: primitive `--danger-600`을 화면에서 직접 쓰지 않고 `--status-danger` semantic token으로
  라우팅했다. 상태 바의 주의 문구라는 화면 의미와 토큰 이름도 일치한다.
- R2: 수동 분석이 `complete`가 되면 `reloadLatest`가 Draft 정본과 version을 같이 읽어
  `analysis_snapshot_id`/`analysis_status`를 갱신한다. 따라서 최신 snapshot의 성공 분석은
  상태 바에 `분석 완료`로 표시되고, 저장 이력이 없는 Scene의 `분석 미실행` 우선순위는 유지한다.
- B4: S1~S13 41단정 실행 프로브를 `tests/test_final_save_analysis.py`의 pytest 셀로 편입했다.
  under-strict(저장·marker·동기 분석·재시도 훼손)와 over-strict(final 뒤 일반 저장·수동 분석·
  보관/없는 draft 경계)를 test docstring에 명시했다.
- 확인: 새 pytest 셀 collect, Python compile, `git diff --check` 통과. 이 환경은 30초 상한으로
  실행 중인 프로브/프런트 Vitest의 종료값은 3차 재검증 환경에서 다시 측정한다.

### Decisions

- 없음. D5=A/B는 HTTP 공개 계약이므로 오너 선택 전에는 502 선언을 제거하지 않는다.

### Next steps

- D5를 확정하고 OpenAPI·프런트 처리·pytest 단정을 그 선택으로 고정한다. 이후 S1~S13,
  새 pytest 셀, 프런트 관련 suite와 전수를 재실행해 조건부 합격을 최종 갱신한다.

## Session 8 — final-save 조건 폐쇄 3차 재검증

### Goals

- 오너 요청: "다시 한번 검증해줘" — 재검증 조건 R1·R2·B4 보강 커밋 `67e8609`의 폐쇄 확인.
  D5(A/B)는 오너 결정 대기로 구현을 바꾸지 않았다는 구현자 방침 확인 포함.

### Completed work

- 검증 기록: [`verifications/2026-09-01/final_save_conditions_closure.md`](../../verifications/2026-09-01/final_save_conditions_closure.md)
  — 판정 **조건부 합격 유지**(조건: R3·R4·D5). 인덱스 등재·건수 4곳 267→268·분포 조건부
  78→79, 등재 뒤 `test_docs_indexes` 단독 13/278 green.
- **R1·B4 폐쇄 실측**: semantic 토큰 정의+사용(designTokens 5/5, 변이 재실패) ·
  `tests/test_final_save_analysis.py` 1 passed(H1 변이 → 셀 FAILED 재실패 — 수집 배선 실증).
- **R2 계약 시나리오 폐쇄 + 구조 안전 확인**: 수동 분석 complete → `reloadLatest`가 draft까지
  재조회(변이 잠금). 실패 경로 reload 없음("필요" 유지), 저장 후에는 latestSnapshotId 로컬
  비교만으로 "필요" 전환 — stale 필드에 구조적으로 안전.
- **전수(백그라운드)**: 프런트 3 failed / 382 passed(전부 R3 채택 흐름 3셀, 파일 1개).
  백엔드 9 failed / 2666 passed / 3083 subtests — docs 가드 7(이 기록 미등재) + **R4 1** +
  live-mongo 부하 플레이크 1(단독 3 passed, 비귀속).

### Issues found

1. **R3(조건)** — `reloadLatest`가 모든 reload에서 `getDraft`를 추가로 불러 채택(Writing·PAD·
   discard-proceed) 3셀의 fetch 목이 어긋나 red. 폐쇄: 3셀 목 갱신 또는 draft 재조회를 수동
   분석 완료 경로에 국한.
2. **R4(조건)** — R1의 `--status-danger`가 디자인 브리프 semantic 표에 미등재(브리프↔:root 1:1
   가드 `PaletteProvenanceTest` red, 단독 재현). 브리프 표에 행 1개 추가로 폐쇄. 위성 표 누락
   계열이 30초 상한 환경에서 또 놓친 것 — 백엔드 전수가 잡음.
3. **D5 미확정** — 502 선언 유지는 구현자의 의도적 보류(기록과 일치). A 확정 시 502 제거·HTTP
   계약·셀 문구 고정이 D5 폐쇄 슬라이스에 포함되어야 한다.

### Decisions

- **[사용자 확정, 2026-09-01] D5=A** — 최종 저장 성공·동기 분석만 실패 시 finalize는
  **200 + `analysis_error`**로 응답한다. 오너 응답: "A — 200 + analysis_error (권장)".
  결정 근거: D2=B가 "final marker와 본문 저장을 먼저 확정"이라 못 박았으므로 저장 성공 요청에
  실패 상태코드를 붙이는 B는 그 문언과 어긋난다(구현자 권고·3차 재검증 독립 판독 동일).
  정본 반영: `docs/plans/final-save-analysis-decisions.md` 상태 Resolved(D5=A)·§D5 오너 결정 추가,
  `docs/plans/README.md` 행 갱신. **도달 불가능해진 502 선언 제거·셀 문구 고정은 R3·R4와 같은
  폐쇄 슬라이스에서 시행**한다.

### Next steps

- 폐쇄 슬라이스: R3(채택 3셀 목 갱신 또는 draft 재조회 국한)·R4(브리프 semantic 표에
  `--status-danger` 행 추가)·502 선언 제거·D5=A 회귀 셀 문구 고정 → 4차 재검증으로 조건부
  승격 마무리. SoT v1.8.13·CHANGELOG 문서 정합성 동반.

## Session 9 — final-save D5=A 폐쇄 보강

### Goals

- 오너가 확정한 D5=A를 공개 API·회귀·정본 문서에 고정하고, 3차 재검증의 R3·R4를 닫는다.

### Completed work

- R3: `reloadLatest`를 원래 version/history 재조회로 복원하고, 수동 분석 `complete`에서만
  `refreshAnalysisStatus`가 Draft를 읽도록 분리했다. 채택 흐름의 기존 fetch 순서를 바꾸지
  않으면서 수동 분석 성공은 최신 `analysis_snapshot_id`/`analysis_status`를 상태 바에 반영한다.
- R4: `--status-danger` → `danger-600`을 디자인 브리프의 semantic 표에 등재했다.
- D5=A: final route는 402·429를 포함한 billable 선언은 유지하고 502를 제외한 새 선언을 쓴다.
  schema.d.ts를 재생성했고 S6·S7 프로브 단정을 `200 + analysis_error` 문언으로 고정했다.
  새 pytest 셀은 502 부활(under-strict)과 quota face 제거(over-strict)를 모두 막는다.
- SoT v1.8.14·README·CHANGELOG에 final marker·동기 분석·D5=A 공개 계약을 반영했다.
- 확인: D5 OpenAPI 셀 + Palette provenance + quota wiring **11 passed / 311 subtests**,
  Python compile, `git diff --check` 통과.

### Next steps

- **다음 작업의 첫 행동은 구현이 아니라 제한 없는 환경의 4차 재검증**이다. S1~S13,
  `tests/test_final_save_analysis.py`, 프런트 관련 suite, 백엔드·프런트 전수를 종료값까지
  측정해 조건부 합격을 최종 판정으로 갱신한다. 이 결과 전에는 final-save를 더 변경하지 않는다.

### Stop note

- 오늘 작업은 D5=A 계약 보강 커밋 `0f26f22`에서 종료한다. 이 실행 환경의 약 30초 상한 때문에
  Vitest·장기 pytest 전수 종료값을 신뢰성 있게 얻지 못했다. 다음 담당자는 HANDOFF ①-a와 위
  재검증 순서부터 시작한다.

## Session 10 — final-save D5=A 4차 재검증(최종 판정)

### Goals

- HANDOFF ①-a 지시: 제한 없는 환경에서 4차 재검증 — S1~S13·새 pytest 셀·프런트 관련 suite·
  양쪽 전수를 종료값까지 측정해 3차 조건부 합격(R3·R4·D5)을 최종 판정한다. 오너 요청 문언:
  "검증하고 의심하고 또 의심해줘" — 폐쇄 확인에 더해 검증자 독자 스윕으로 새 축을 찌른다.

### Completed work

- 검증 기록: [`verifications/2026-09-01/final_save_d5_closure.md`](../../verifications/2026-09-01/final_save_d5_closure.md)
  — 판정 **조건부 합격**(조건: N1 프런트 finality 표시 축 무셀). 인덱스 등재 + 건수 4곳
  (최상위 README 2·docs/README·검증 인덱스) 268→269·분포 조건부 79→80 갱신, 등재 뒤
  `test_docs_indexes` 단독 **13 passed / 279 subtests**(판정 열 +1 규칙과 일치).
- **3차 조건 전부 실측 폐쇄**: D5 선언 집합 {400,401,402,403,404,409,429,503} 직독 + 앱 전체
  502 생산지 스캔(drafts 경로 무관) + `npm run gen:api` 재생성 뒤 `git status` 0줄(schema.d.ts
  byte-identical) + SoT v1.8.14·CHANGELOG·README 동기·operation 100·tier 74/100 실측 일치.
  R3(reloadLatest 복원·refreshAnalysisStatus 국한·채택 3셀 mock 복원)·R4(브리프 행·
  PaletteProvenance green) 확인.
- **전수(제한 없는 실행, 종료값)**: 백엔드 **2668 / 4 / 3114, rc=0, 289.86초**(알파 —
  `elasticsearch` 패키지 부재로 skip 4 관례; **기록을 쓰기 전에 돌려** docs 가드 green —
  선행 3회와 다른 순서, 다음 기대값 2668/4/3115). 프런트 **385 / 35 files, rc=0, 90.43초**
  (3차 R3 3셀 회복 — 백엔드와 순차 실행으로 부하 플레이크 0). mypy 8/3·집중 suite
  67/553·tsc rc=0·프로브 41단정 rc=0·새 pytest 셀 2/2.
- **뮤테이션 5종**(전부 복원·트리 clean 확인):

  | 변이 | diff(file:line) | 재실패 셀 |
  |---|---|---|
  | M1 D5 under-strict | `routers/drafts.py` import + :668 `responses=_owned(_BILLABLE_400_404_409_502_CONFIG)`(502 부활) | `test_final_save_analysis.py::test_d5_a_keeps_analysis_failure_inside_a_200_payload` FAILED |
  | M2 D5 over-strict | `routers/drafts.py:668` `responses=_owned(_ERRORS_400_404_409)`(402/429 제거) | D5 셀 FAILED + `BillableRouteWiringTest::test_every_billable_operation_declares_402_and_429` SUBFAILED(finalize 자리 — 요약 줄 판독) |
  | M3 D5 행동 | `routers/drafts.py` finalize except 첫 줄에 `raise HTTPException(status_code=502, …)` 삽입 | 프로브 **S6** "expected=200 observed=502" |
  | M4 R3 | `DraftEditor.tsx:949` `if (status === "complete") void refreshAnalysisStatus();` → `{ void 0; }` | `DraftEditor > renders and updates the save, analysis, and pending-review status bar` FAIL(1/54) |
  | M5 R4 | `10-frontend-design-system-decisions.md` `--status-danger` 표 행 삭제 | `PaletteProvenanceTest::test_the_brief_semantic_table_matches_the_stylesheet` FAILED |

- **독자 스윕(신규 발견 4)**: ①**N1(조건)** 프런트 테스트 전 파일에서 `finalize`·`최종 저장`
  언급 0건 — 배지 3상태·final 버튼·finalize 흐름·`미실행`/`진행 중` 라벨 무셀(동작은
  계약과 일치, 빠진 것은 잠금) ②**N2** DraftList가 finality·분석 필드 미소비(계약 제7조
  "Scene 목록" 문언 긴장) ③**N3** 같은 키 재전송 활동 행 2건 중복(실측; accept 선례 긴장·
  UI 도달 불가) ④**N4** 실패 뒤 재전송 봉투 `analysis_error=None` 비대칭(상태 얼굴은 보존).

### Issues found

1. **N1(조건)** — 계약 제3조·D3=B가 요구하는 프런트 표시 분기에 기명 셀이 없다. 가드 규칙상
   합격으로 못 닫는다 — 셀 묶음 추가가 조건의 전부.
2. **N2·N3(오너 판단)** — 계약 무침/문언 긴장. 결정 없이 구현하지 않는다.
3. **우발 — `/mnt/f`에서 perl `-i` 제자리 쓰기가 파일을 손상시켰다**(검증 인덱스 1행에 교체
   문자열이 앞에 붙음). `git checkout` 복원 뒤 Edit 도구로 재적용, `test_docs_indexes` green으로
   확인. 이 머신에서는 제자리 편집에 perl/sed `-i`를 쓰지 않는다.

### Decisions

- 없음(검증 세션 — N2·N3 판정은 오너 몫).

### Next steps

- **N1 폐쇄 슬라이스**: DraftEditor finality 배지 3상태·final 버튼·finalize 흐름(성공/부분
  성공 안내)·`미실행`·`진행 중` 기명 셀(under/over-strict 짝). 폐쇄 후 5차 재검증은 집중
  셀+변이로 승격 판정.
- N2·N3 오너 결정 대기(결정 즉시 셀 1~2줄로 봉인 가능).

## Session 11 — N1 폐쇄(프런트 finality 표시 축 기명 셀)

### Goals

- 4차 재검증([`final_save_d5_closure.md`](../../verifications/2026-09-01/final_save_d5_closure.md))의
  유일한 조건 N1을 닫는다: 확정 계약 제3조·D3=B가 요구하는 프런트 표시 분기 —
  배지 3상태·final 버튼(활성/비활성+사유)·finalize 성공/부분 성공 안내·`미실행`/`진행 중`
  라벨 — 에 기명 셀을 붙이고 양방향 변이로 잠금을 실측한다.
- 범위 밖: N2·N3은 오너 판정 대기이므로 **손대지 않는다**(4차 재검증 지시와 동일).

### Completed work

- `frontend/src/drafts/DraftEditor.test.tsx`에 `describe("최종 저장 표시 축 …")` 신설 —
  **12셀**(파일 54 → 66, 프런트 전수 385 → **397**). 구현 코드는 한 줄도 바꾸지 않았다
  (이 슬라이스는 잠금이지 수정이 아니다 — 4차 재검증이 동작은 계약과 일치한다고 실측했다).
  - 배지 3상태: marker 없음 → `초안` / marker == 최신 snapshot → `최종 저장됨` /
    marker보다 최신 version 존재 → `최종 저장 후 수정됨`. 셋 다 `expectOnly` 헬퍼로
    **기대 문구만 켜져 있고 나머지 두 문구는 꺼져 있음**을 함께 문다(과잉 표시 방지).
  - final 버튼: marker 없음 → 활성·`title` 부재 / marker 존재 → 비활성 + 사유 문언
    `"최종 저장은 Scene당 한 번만 할 수 있습니다."` 정확 대조. 추가로 상한 초과 →
    비활성(상한 아래에서는 활성이어야 함을 같은 셀에서 확인)·보관 원고 → 버튼 부재.
  - finalize 흐름: 성공 셀은 `/finalize` POST의 `raw_text`·`idempotency_key`까지 대조하고
    배지 `초안`→`최종 저장됨`·`분석 완료`·성공 안내 문구를 함께 잠근다. 부분 성공은
    `it.each` 2행 — job `failed` / **job 없음 + `analysis_error`(D5=A의 200 얼굴)** —
    둘 다 저장은 `최종 저장됨`, 분석은 `필요`, 안내는 부분 성공 문구이며 성공 문구가
    뜨지 않는 것까지 확인한다.
  - 분석 라벨 `it.each` 4행: 저장본 없음 → `미실행` / 최신 snapshot job `pending`·`running`
    → `진행 중` / 성공 job의 snapshot이 최신과 다름(stale) → `필요`. 네 라벨 중 하나만
    켜져 있음을 매 행에서 확인 — 제3조의 "시간이 아니라 snapshot 동일성" 규칙이 앵커다.
- 확인: `DraftEditor.test.tsx` **66 passed**, 프런트 전수 **397 passed / 35 files, rc=0**,
  `npx tsc --noEmit` rc=0. 백엔드는 이 슬라이스가 건드리지 않는다(프런트 테스트 파일 1개 변경).
- **뮤테이션 11종**(전부 `DraftEditor.tsx`에 적용 → 실행 → 복원, 매회 `git status --porcelain`
  0줄 확인. 규칙대로 **셀 커밋 `f248d8c` 뒤에** 변이했다):

  | 변이 | diff(file:line) | 재실패 셀 |
  |---|---|---|
  | M1 배지 under | `:665` 배지를 `isFinalized ? "최종 저장됨" : "초안"`(snapshot 동일성 무시) | `marker 보다 최신 version 이 있으면 …` |
  | M2 배지 over | `:665` 배지를 `isFinalized ? "최종 저장 후 수정됨" : "초안"` | `marker 가 최신 snapshot 과 같으면 …` + 성공 셀 + 부분 성공 2셀 (4 failed) |
  | M3 버튼 잠금 | `:721` `disabled=`에서 `isFinalized` 제거 | mount 2셀 + 성공 셀 (3 failed) |
  | M4 버튼 사유 | `:722` `title={undefined}` | `marker 가 최신 snapshot 과 같으면 …` + 성공 셀 |
  | M5 안내 under | `:395` `setNotice(true …` (부분 성공도 성공 문구) | 부분 성공 2셀 |
  | M6 안내 over | `:395` `setNotice(false …` (성공도 부분 성공 문구) | 성공 셀 |
  | M7 라벨 미실행 | `:215` `latestSnapshotId === null ? "필요"` | `분석 라벨: 저장본이 없으면 미실행` |
  | M8 라벨 최신성 | `:210` `draft?.analysis_snapshot_id !== latestSnapshotId ||` → `false ||` | `분석 라벨: 성공 job 의 snapshot 이 최신과 다르면 필요` + `marker 보다 최신 version …` |
  | M9 라벨 진행 중 | `:219` 에서 `draft?.analysis_status === "pending"/"running"` 제거 | `분석 라벨: … pending 이면 진행 중` · `… running 이면 진행 중` |
  | M10 상한 | `:721` `disabled=`에서 `overLimit` 제거 | `상한을 넘은 본문은 … 최종 저장 버튼도 잠근다` |
  | M11 보관 | `:717` final 버튼의 `{!readOnly && (` → `{true && (` | `보관된 원고에는 최종 저장 버튼 자체가 없다` |

### Issues found

1. `it.each` 제목에 `%s`를 2개 쓰는 바람에 두 번째 자리가 배열 인자를 먹어 실패 이름이
   `… 이면 [object Object]`로 찍혔다. 검증 프로토콜이 **기명 실패 줄을 읽어** 판정하므로
   이름이 망가지면 가드가 약해진다 — 제목을 `%s` 하나로 줄이고 기대 라벨을 행 이름에
   포함시켜 재실행(66 passed) 확인했다.
2. (관찰, 이 슬라이스 밖) 최상위 README ② 카운터가 낡았다는 4차 재검증 지적은 그대로다.
   프런트 전수가 385 → 397로 다시 움직였으므로 갱신 시 함께 반영해야 한다.

### Decisions

- 없음(오너 결정을 요하는 갈림 없음 — N1은 판정문이 요구 범위를 문언으로 못 박은 잠금 작업).
  N2·N3은 여전히 오너 대기이며 이 세션에서 건드리지 않았다.

### Next steps

- **5차(승격) 재검증**: 4차 판정문대로 집중 셀 + 변이로 충분하다. 대상은 이 세션 커밋
  (`f248d8c` 셀 + 제목 정정)·프런트 전수 **397/35** 기대값·위 변이 표 재현.
- N2·N3 오너 결정 대기(결정 즉시 셀 1~2줄로 봉인 가능).

## Session 12 — 배포 서버 업데이트(장면 메모 + 최종 저장·분석)

### Goals

- 오너 지시: 배포 서버를 현재 main으로 업데이트한다. 서버가 `f73e820`(08-29)에 머물러 있어
  장면 메모 Slice 0~2와 최종 저장·분석(D1~D5) 전체가 미배포 상태였다.

### Completed work

- **배포 범위 산정**: `f73e820..a875fc0` = 45커밋 / 59파일. `scripts/`·compose·Dockerfile
  변경 **0건** → 별도 migration·구성 변경 없이 이미지 재빌드만으로 충분하다고 판단했다.
  신규 Mongo 인덱스 `uniq_scene_note`는 저장소 setup이 기동 시 설치하며, **빈 신규 컬렉션**이라
  08-29의 멀티 프로젝트 unique 충돌 같은 위험이 없다(그 사고와 형상이 다름을 미리 확인).
- **소스 정렬**: 서버 저장소를 `origin/main`으로 `merge --ff-only`(트리에 서버 전용 override
  1건이 untracked로 남아 있으나 무관·무변).
- **이미지 재빌드**: `application`(4서비스 공유 이미지 `ai_writte_system-app`)·`frontend` 2종,
  rc=0. requirements·package.json 무변으로 설치 레이어는 캐시 적중.
- **앱 계열 교체**: `application`·`admin`·`worker`·`generation_worker`·`frontend` 5서비스를
  `--no-deps`로 재생성 — **영속 저장소(mongo·chroma·elasticsearch)와 gateway는 건드리지 않았다**.
  소요 **29.5초**. 08-29 세션 3이 겪은 "의존성 재검사 10분 대기"는 재발하지 않았다
  (세션 4가 만든 `docker-compose.external-embedding.yml` override를 실제 배포에 처음 적용).

### Verification

- 스택 전체 healthy(교체 5종 + 무변 4종). `application /health` **200**, 프론트 `/` **200**,
  프론트의 `/api/health` 프록시 **200**.
- **신규 라우트 4종이 실제로 서빙된다** — 배포 앱은 OpenAPI 문서를 노출하지 않으므로(404)
  인증 경계로 확인했다: `POST …/finalize`·`GET /projects/{id}/notes`·`GET|PUT …/note` 전부
  **401**(존재), 대조군인 없는 경로는 **404**(라우터 판정이지 일괄 401이 아님을 분리).
- **신규 인덱스 설치 확인**: 운영 Mongo에 `scene_notes` 컬렉션 + `_id_`, `uniq_scene_note`.
- **프론트 번들이 새 빌드**: 서빙 중인 번들에 `최종 저장·분석`·`최종 저장 후 수정됨`·
  `최종 저장은 Scene당 한 번만` 3문구 모두 존재.
- **공개 경로 보존**: 교체 후에도 컨테이너 이름·게시 포트·네트워크가 교체 전과 동일.
- 로그: 애플리케이션·워커에 오류 없음. 기동 시 외부 라이브러리(chroma client) telemetry 전송
  경고만 있으며 이는 [08-28 기록](../2026-08-28/work_log.md)의 기존 비차단 잡음과 같은 것이다.

### Issues found

- 없음(배포·검증 전 단계 무사고).

### Decisions

- **저장소·게이트웨이는 교체하지 않는다**(`--no-deps`). 이번 델타에 compose·Dockerfile 변경이
  0건이라 재생성할 이유가 없고, 08-29 사고 이후 "앱 계열만 교체"가 이 서버의 확립된 절차다.

### Next steps

- **오너 육안 확인**: 공개 사이트 편집기에서 최종 저장 버튼·배지 3상태·장면 메모 UI를 본다.
  운영 데이터에 최종 저장 이력은 아직 0건이라 첫 실행이 곧 첫 실사용 검증이다.
- 5차(승격) 재검증은 배포와 무관하게 예정대로 진행한다(세션 11 참조).
