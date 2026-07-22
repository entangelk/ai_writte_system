# 2026-07-22 작업 로그

## Task — 비동기 생성 + 결과 패드 증분 3: 읽기 전용 패드 + 완료 배지 + 5초 폴링 (D6=A, 프론트 전용)

### Goals

- 비동기 생성 슬라이스의 마지막 조각(증분 3, D6=A). 2c에서 endpoint 동기/비동기 분기가 개통되어 medium/long이 `202`로 job을 반환하지만, 아직 그 결과를 보여주는 UI가 없다. 이번 증분이 그 UI를 채운다.
  - **읽기 전용 패드**: 진행 중 job(생성 중) + 완료 결과(worker가 scratch에 append) 를 합쳐 보여준다.
  - **완료 배지**: 이어쓰기 탭에 완료 job 개수를 표시하고, 탭을 열면 지운다.
  - **5초 폴링(생성 중일 때만)**: `GET .../generation-jobs/{job_id}`를 5초마다 폴링해 종료를 감지하고, 종료 시 scratch를 재조회해 결과를 표시한다.
- **백엔드/계약 무변**: 기존 `GET .../generation-jobs/{job_id}`·`GET .../writing/scratch` 엔드포인트만 소비한다. 새 계약 리터럴이 없으므로 **SoT 버전 bump 없음**(§264가 이미 "패드 UI가 읽어 표시한다[증분 3]"를 전방 마커로 갖고 있고, 그 read는 이미 계약된 엔드포인트로 구현된다).

### Completed work

- **신규 `frontend/src/writing/useGenerationJobs.ts`(폴링 훅)**: 세션이 시작한 async job을 in-memory로 추적하고, **active(pending/running) job이 있을 때만** 5초 간격 `setInterval`로 각 job을 `getGenerationJob`으로 폴링한다(D6=A "생성 중일 때만"). job이 terminal(succeeded/failed)로 전이하면 `settledUnseen`을 올리고 `onSettled(job)`을 호출한다 — succeeded는 추적에서 제거(결과는 scratch에 있음), failed는 `failedJobs`로 남겨 패드에 노출(D6=A "실패 조용함 없음"). pending→running 전이는 배열 참조를 보존하며 반영(폴링마다 재렌더 방지). draft 변경 시 추적 리셋(job은 per-draft 키). 폴링 fetch 실패는 job을 active로 남기고 다음 tick 재시도. 노출: `activeJobs`·`failedJobs`·`track`·`settledUnseen`·`acknowledge`·`dismissFailed`.
- **신규 `frontend/src/writing/GenerationPad.tsx`(진행 중/실패 표시)**: 패드의 "진행 중" 절반. 완료 결과는 기존 `ScratchRecovery`(= scratch 목록)가 렌더하므로, 이 컴포넌트는 진행 중 job("백그라운드 생성 N건 진행 중… / 대기 중·생성 중")과 실패 job(사람이 읽는 failure copy + "닫기")만 담당한다. 실패 copy는 `WritingGenerationJobFailureReason`(6종 + `internal`) 미러이며 미지의 reason은 raw로 fallback(새 백엔드 reason도 노출). active/failed 둘 다 없으면 null.
- **`client.ts`**: 신규 `getGenerationJob(projectId, jobId)` — `GET /projects/{id}/writing/generation-jobs/{job_id}` 소비(read-only 상태).
- **`WritingPanel.tsx`**: 신규 optional prop `onAsyncJobStarted?: (job) => void`. async 분기(`"job" in produced`)에서 notice를 띄우기 전에 `onAsyncJobStarted?.(produced.job)`로 부모에 job을 넘겨 폴링을 시작시킨다. 동기 short 경로는 호출하지 않는다.
- **`DraftEditor.tsx`(배선)**: `useGenerationJobs(projectId, draftId, { onSettled: scratchRefresh 증가 })`를 편집기 레벨에서 호출한다 — **폴링을 편집기에 두어 탭 전환에 살아남고 탭 배지를 구동**한다(WritingPanel은 탭 전환 시 언마운트됨). job이 settle되면 scratch를 재조회(worker가 append한 결과가 `ScratchRecovery`에 뜬다). 이어쓰기 탭 버튼에 `unseenGenerationJobs > 0`이면 배지 span(aria-label 포함), 이어쓰기 탭을 보는 동안(`activePanel === "writing"`) 효과로 `acknowledge()`해 배지를 지운다. 이어쓰기 탭 영역에 `GenerationPad`(진행 중/실패) 를 `ScratchRecovery`(완료) 위에 얹어 둘이 한 패드로 읽히게 했고, `WritingPanel`에 `onAsyncJobStarted={track}`을 넘겼다.
- **`styles.css`**: `.tab-badge`(accent pill), `.generation-pad`/`.generation-pad-lead`/`.generation-pad-list`/`.generation-pad-failed` 스타일 추가(기존 `.spinner`·CSS 변수 재사용).

### User Decisions and Rationale

- 오너 지시("핸드오프와 데일리로그 확인해서 다음작업 진행")대로 확정된 다음 작업(증분 3, D6=A, `plans/async-generation-pad-decisions.md`)을 이어서 구현했다. D1~D7은 2026-07-20 확정분이라 새 결정 필요 없음.

### Decisions (구현자 판단)

- **폴링·배지 상태를 `DraftEditor`(편집기 레벨)에 둔다**: 배지가 탭에 있고 폴링이 탭 전환에도 이어져야 하므로(WritingPanel은 비활성 탭에서 언마운트). 훅으로 분리해 독립 유닛 테스트가 가능하게 했다.
- **완료 패드는 신설하지 않고 기존 `ScratchRecovery`를 재사용한다**: D1=A대로 async 결과와 복구분은 같은 scratch 저장소이므로 `ScratchRecovery`가 이미 완료 결과를 렌더한다. `GenerationPad`는 진행 중/실패만 담당해 관심사가 겹치지 않게 했다(2c notice "결과 패드에 표시됩니다"의 "패드" = ScratchRecovery + GenerationPad 인접 영역).
- **실패 job은 `dismissFailed`로 세션-로컬 닫기만 제공**(재시도 UI는 D4대로 deferred). 영구 dead-end 에러 상태를 피하는 최소 조치.
- **SoT 버전 bump 없음**: 계약 리터럴 변경이 없다(신규 엔드포인트·스키마·env 없음). §264의 전방 마커가 이미 이 read를 서술한다.

### Verification

- **frontend `npx vitest run` → 180 passed / 13 files**(163→180, 신규 유닛 17: `useGenerationJobs.test.ts` 8 + `GenerationPad.test.tsx` 5 + `WritingPanel.test.tsx` +2[onAsyncJobStarted fire/not-fire] + `DraftEditor.test.tsx` +2[완료 결과 패드 노출·폴링 정지 / 오프탭 배지 점등·복귀 시 소거]).
- 훅 테스트가 두 방향 잠금: **under-strict**(추적 job 없으면 폴링 안 함·settle 후 폴링 정지·transient fetch 실패 시 active 유지 후 재시도) + **over-strict**(succeeded는 active에서 제거·failed는 패드에 남김·draft 변경 시 추적 리셋해 이전 draft가 계속 폴링 안 함).
- **`npm run build` → 103 modules**(CSS 19.42 kB / JS 397.98 kB), **`tsc --noEmit` clean**, **`npm run gen:api` → `schema.d.ts` byte-identical**(백엔드/OpenAPI 무변).
- **backend 무변** — 이번 증분은 프론트 전용이라 백엔드 스위트 재실행 불요(LLM 미사용).
- **테스트 하네스 주의(다음 작업자)**: `DraftEditor.test.tsx`의 fake-timer 테스트는 `userEvent`가 fake timer와 교착하므로 입력은 timer-free `fireEvent`를 쓰고, 초기 로드/폴링 fetch 체인은 다회 `pump()`(=`advanceTimersByTimeAsync` in `act`)로 flush한 뒤 `getBy`로 단정한다(`findBy`/`waitFor`는 스스로 타이머를 advance해 5초 간격과 충돌). `afterEach`에 `vi.useRealTimers()`를 선행 추가해 fake-timer 누수가 후속 테스트를 hang시키지 않게 했다.

## Task — 증분 3 오너 독립 검증 PASS(차단 없음) 후 비차단 hardening 반영 (H-1·H-2·H-3)

### User Decisions and Rationale

- 오너 독립 감사가 **합격(PASS, 차단 발견 없음)**으로 종료됐다(`docs/verifications/2026-07-22/increment3_d6_generation_pad_polling.md`). boundary matrix에 빈 cell 없음, 모든 계약 리터럴 unchanged 미러링 확인. 오너가 검증 기록의 비차단 hardening 후보(H-1/H-2/H-3) 보강 후 커밋을 지시했다.

### Completed work (`useGenerationJobs.test.ts` 전용, 소스 코드 무변)

- **H-1 — 5초 폴링 주기 직접 핀**: `expect` 없이 상수 참조/`pump(5000)`에만 의존하던 것을 **리터럴 5000 behavioral 핀**으로 보강 — 추적 job이 있을 때 4999ms에서는 fetch 없음(짧은 간격 방어=under-strict), 정확히 5000ms에서 첫 폴링(긴 간격 방어=over-strict). 상수(`GENERATION_POLL_INTERVAL_MS`)가 아닌 리터럴을 써 값 변경 시 재실패한다. 오너 "5초 확정"(decisions brief D6) 보호.
- **H-2 — `if (!hasActive) return` 가드 mutation-pin**: "idle no-fetch" 단정은 관측 계약만 잠그고 가드 제거에 둔감했으므로(빈 배열 폴링도 fetch 0), `vi.spyOn(globalThis, "setInterval")`로 **유휴 시 interval 미가동·활성 job 생기면 1회 가동**을 직접 단정. 가드 제거 시(영구 setInterval) 재실패.
- **H-3 — 다중 job 동시 폴링 직접 테스트**: `Promise.all` fan-out을 단일 job만 관통하던 것을, **2 job을 한 tick에 병렬 폴링(2 fetch)하고 독립 settle**(하나 succeeded→제거, 하나 failed→패드 잔존, 둘 다 `settledUnseen`)로 잠금.

### Verification

- **frontend `npx vitest run` → 183 passed / 13 files**(180→183, hook 8→11), `tsc --noEmit` clean. 소스 무변이라 build·gen:api 재검 불요(직전 103 modules·byte-identical 유효). 이후 오너 요청대로 커밋.

### Next steps (반영 후)

- **비동기 생성 + 결과 패드 슬라이스(증분 1~3) 전체 완료.** 남은 후속(슬라이스 밖): dogfood에서 per-draft 상한(기본 20, 복구+패드 공유) 밀어냄 관찰 시 `WRITING_SCRATCH_MAX_PER_DRAFT` 기본값 조정(계약 재개정 불요), 재시도 UI(D4 deferred), 실 12B 풀스택에서 medium/long 생성→worker→패드 표시 오너 관통 확인(sandbox 12B 불가).
- 비차단 hardening 후보(오너 검증 시 참고): DraftEditor 완료 배지의 다중 job 카운트(현재 유닛에서 settledUnseen 누적은 훅이 잠금, 통합은 1건만 관통), 폴링 백오프(현재 고정 5초·transient 실패도 5초 재시도).

## Task — accept 후 미저장 편집 소실 결손 수정 (reloadLatest 덮어쓰기, 비동기와 무관한 별개 결손)

### Goals

- 브리프(`plans/async-generation-pad-decisions.md`)의 Deferred에 "편집기 미저장 입력이 accept 후 `reloadLatest()`로 덮이는 문제 — 비동기와 무관한 별개 결손, 별도로 다룬다"로 명시됐던 실재 데이터 소실 결손을 수정한다.
- **결손**: generate는 clean+latest에서만 되지만, 후보가 뜬 뒤 사용자가 편집기에 입력하면(dirty) accept는 **frozen base_version_id + 후보 텍스트**로 새 version을 저장하고(편집기 텍스트 미반영), 성공 후 `onAccepted → reloadLatest()`가 `setRawText`로 편집기를 새 latest로 덮어써 **미저장 입력이 조용히 소실**된다([DraftEditor.tsx:434-455], [DraftEditor.tsx:611-615]).

### User Decisions and Rationale

- 오너 지시("결손 작업 진행. 브리프 필요 없으면 바로 진행"). **브리프 불필요로 판단**: 이 앱은 dirty 상태의 파괴적 동작을 전부 `window.confirm`으로 가드한다(페이지 이동 `:163`·version 전환 `:278`·근거 열기 `:347`) — accept만 이 관용구가 빠져 있었다. 따라서 새 아키텍처/정책 포크가 아니라 **선례 관용구를 accept에 적용**하는 일이라 결정 브리프가 아니라 Think-Before-Coding 범위다.

### Decisions (구현자 판단)

- **차단이 아니라 confirm**: generate만 dirty에서 차단하는데 그건 깨끗한 base가 있어야 정합적 후보를 만들기 때문이다. accept의 후보 base는 **이미 frozen**이라 accept 자체는 dirty와 무관하게 유효하고, 문제는 편집기 덮어쓰기 하나뿐 → 이동/version/근거 가드와 동일한 **confirm(경고 후 진행/취소)** 이 정합적이다. (차단하면 저장 강요 → base stale → 409 → 재생성 강요라는 dead-end를 confirm이 회피한다.)
- **가드 위치 = `WritingPanel.accept()` 최상단**(네트워크 호출·키 민팅 전): accept가 **version을 저장**하므로, `reloadLatest` 시점(이미 저장됨)이 아니라 저장 전에 취소 가능해야 한다.

### Completed work

- **`WritingPanel.tsx`**: `dirty` prop을 destructure에 추가하고 `accept()` 초입 early-return 직후에 가드 삽입 — `dirty && !window.confirm("저장하지 않은 편집 내용이 있습니다. 채택하면 그 내용은 사라지고, 채택된 후보가 새 version으로 저장됩니다. 계속할까요?")`이면 `return`(accept 중단). `dirty`는 이미 부모가 전달 중(availability에만 쓰이던 것을 accept에도 소비).

### Verification

- **frontend `npx vitest run` → 188 passed / 13 files**(183→188, 신규 5): WritingPanel 3(취소 시 accept 미호출=under-strict[결손 자체]·confirm 시 진행·clean이면 confirm 미표시=over-strict) + DraftEditor 통합 2(취소 시 **편집기 텍스트 보존 + version 미저장** / confirm 시 **accept 저장 + 편집기가 새 latest로 재로드**되어 미저장 텍스트 discard). `tsc --noEmit` clean, `npm run build` 103 modules(JS 398.16 kB, 가드 코드로 +0.18 kB). **백엔드/OpenAPI 무변**(프론트 전용)이라 `gen:api` 영향 없음. LLM 미사용.
- 두 방향 잠금: 취소→accept 미발화+편집 보존(결손 재도입 방지), clean→confirm 미표시(과잉 nag 방지).
- **오너 독립 검증 PASS(차단 없음)** — `docs/verifications/2026-07-22/accept_dirty_guard_unsaved_edits.md`(boundary matrix·pattern sweep[accept가 유일한 무가드 setRawText 경로였음 확인]·수치 재실행 일치). 검증의 유일한 비차단 보강 후보(**proceed 경로 통합 테스트 부재** — cancel만 통합 관통)를 반영해 DraftEditor 통합 proceed-사슬 테스트 1건 추가(187→188). 이로써 `onAccepted→reloadLatest→setRawText` 사슬이 취소·진행 양방향 모두 통합 레벨에서 잠긴다.

### Next steps

- 남은 결손·후속: 재시도 UI(실패 job 재생성, D4 deferred), per-draft 상한 기본값 dogfood 관찰, 실 12B 풀스택 e2e. **오너 dogfood 착수(GATE-1)가 가장 큰 갈림길.**

## Task — 비동기 생성 job 재시도 endpoint + 결과 패드 재시도 버튼 (async-pad D4=A 재시도 UI 슬라이스, SoT v1.7.28)

### Goals

- 증분 2b에서 "재시도 UI 슬라이스로 지연"했던 `FAILED→PENDING` 전이를, 그 전이를 구동하는 endpoint·프론트 버튼과 함께 구현해 dead 분기 없이 실패한 백그라운드 생성을 재시도할 수 있게 한다.
- **worker가 PENDING을 자동 claim**하므로 Analysis retry(retry 후 프론트가 별도 `run` POST)와 달리 **retry만으로 재실행**된다.

### User Decisions and Rationale

- 오너 지시("재시도 UI쪽으로 하자"). **브리프 불필요로 판단**: 재시도 의미는 Analysis retry endpoint(`failed→pending`, 그 외 409, 404) 선례가 정하고, `generation_job.py` 주석이 이미 "retry 슬라이스에서 이 전이를 구동하는 public 메서드와 함께 추가"라고 지연 사유를 명시했다. 새 정책 포크가 아니라 선례+지연-노트 폐쇄라 결정 브리프가 아니라 Think-Before-Coding 범위다. 다만 백엔드 계약 변경(신규 endpoint + 상태 전이)이라 **SoT bump**(v1.7.28)는 필요.

### Decisions (구현자 판단)

- **retry만으로 재실행(별도 run 없음)**: 생성 worker의 claim 루프가 PENDING을 자동으로 집으므로, Analysis처럼 retry→run 2단계가 아니라 retry 1회로 충분하다. 이 차이를 서비스 메서드·SoT·endpoint 주석에 명시.
- **`InvalidJobStateTransition` 별칭 import(main.py)**: analysis·writing 두 모듈이 각각 동명 예외를 정의한다. retry endpoint가 analysis 것을 catch하면 writing 예외가 새어 500이 된다(구현 중 실제로 재현) → writing 것을 `InvalidGenerationJobStateTransition` 별칭으로 import해 catch. 회귀(`test_retry_non_failed_states_are_409`)가 409를 단정해 이 함정을 잠근다.
- **프론트 retry는 훅에 둔다**: 실패 job은 세션-추적(`failedJobs`)이므로, 훅의 `retry(jobId)`가 endpoint 호출 후 job을 PENDING(active)으로 되돌려 폴링을 재개한다. retry 요청 실패는 job을 failed로 남겨 재시도 가능하게 한다. GenerationPad는 실패 항목에 "다시 시도"(+"닫기") 버튼만 노출.

### Completed work

- **`writing/generation_job.py`**: `_ALLOWED_TRANSITIONS`에 `(FAILED, PENDING)` 추가 + `mark_pending_for_retry(job)` 서비스 메서드(FAILED→PENDING 전이, failure_reason/detail·claimed_at clear; 비-FAILED는 `InvalidJobStateTransition`). 전이 주석의 "deferred"를 실구현으로 갱신.
- **`main.py`**: `POST .../writing/generation-jobs/{job_id}/retry`(`response_model=WritingGenerationJobPayload`) — project 존재 검사 → job get(404 미발견/타 프로젝트) → `mark_pending_for_retry`(409 on invalid transition). writing `InvalidJobStateTransition`을 별칭 import.
- **`frontend`**: `client.ts` `retryGenerationJob`(POST retry) · `useGenerationJobs` `retry(jobId)`(failed 가드→endpoint→job을 pending으로 갱신해 폴링 재개; 요청 실패 시 failed 유지) · `GenerationPad` "다시 시도" 버튼 + `onRetryFailed` prop · `DraftEditor`가 훅의 `retry`를 배선 · styles `.generation-pad-failed-actions` 버튼 그룹.
- **SoT v1.7.28**: §271 전이 문구(FAILED→PENDING=명시 재시도) + §272 retry endpoint 계약 절 + 변경 이력 행.

### Verification

- **backend `python3 -m pytest --ignore=tests/test_memory_mongo.py -q` → 1322 passed / 73 skipped / 328 subtests**(1312→1322, 신규 10: 서비스 `RetryTest` 5[failed→pending clear·재claim 가능=under-strict·pending/running/succeeded 거절=over-strict] + mongo retry round-trip 1 + endpoint `WritingGenerationJobRetryTest` 4[200 failed·409×3 subtest·404 unknown·404 wrong-project]).
- **frontend `npx vitest run` → 192 passed / 13 files**(188→192, 신규 4: 훅 retry 3[reset→폴링 재개·retry 실패 시 failed 유지·비-failed no-op] + GenerationPad "다시 시도" 버튼 1). `tsc` clean, `npm run build` 103 modules(JS 398.69 kB), `npm run gen:api` retry path 1개 additive(49줄 삽입·0 삭제, 순수 additive 확인). LLM 미사용.
- **비차단 후보(오너 검증 시 참고)**: DraftEditor 통합 retry 사슬(생성→실패→"다시 시도"→재개) 테스트 부재 — 훅 retry(폴링 재개)·GenerationPad 버튼(onRetryFailed 호출)·DraftEditor 배선(`void retryGenerationJob(jobId)` 한 줄)이 각각 잠겨 있고, 통합은 fake-timer 비용이 커 단위로 대체. 필요 시 증분 3 배선처럼 추가 가능.

### 검증자 보강 + mongo 환경 진단 (독립 검증 세션)

- **✅ 비차단 보강 완료 — DraftEditor 통합 retry e2e**: 오너 독립 검증(`docs/verifications/2026-07-22/retry_slice_d4_generation_job.md`) 후, fake-timer 통합 패턴(증분 3 `routeAsyncPad`·`pump`·`jobPolls` 재사용)으로 retry 사슬 전체를 관통하는 통합 테스트 1건 추가 — async generate → 첫 5s poll FAILED → 패드 실패 row + "다시 시도" 버튼 → 클릭 시 `POST .../retry` 발화 + 서버 pending 응답 → 폴링 재개 → 다음 poll succeeded → 결과 표시. frontend **192→193 passed / 13 files**(DraftEditor 38→40), `tsc` clean. (accept 결손 fix 테스트 1건이 같은 파일에 있어 38→40.)
- **mongo 환경 진단(`test_memory_mongo` 실패 원인)**: 본 슬라이스 무관. `test_memory_mongo`는 `CORE_SOT_TEST_MONGO_URI`(기본 `mongodb://localhost:27017`)에 연결하는데, **27017 = `shared-mongo`는 인증 필수**(`Unauthorized, code=13, "Command insert requires authentication"`)라 인증 없는 연결로 read(ping)만 되고 write(`create_index`)가 거부 → `ensure_indexes()`가 `OperationFailure` → `MongoMemoryRepositorySetupError`. ping probe는 read라 `skipUnless`를 통과해 skip 대신 FAILED. **메모리 전용 컨테이너 27018(`agent-memory-mongodb`, mongo 7.0.30)로 돌리면 green** — `CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018 PYTHONPATH=services/application python3 -m pytest tests/ -q` → **1358 passed / 41 skipped / 0 failed / 328 subtests**(27017 환경의 1322 passed/73 skipped/4 failed에서 mongo를 올바른 컨테이너로 옮기니 +36 passed·-32 skipped·-4 failed, 총 1399 동일). 오너 판단 "몽고는 별도 컨테이너라 스킵/실패가 없어야 맞다" 정확 — 27018이 그 별도 컨테이너.

### Next steps

- **재시도 UI 완료.** 남은 후속: per-draft 상한 기본값 dogfood 관찰, 실 12B 풀스택 e2e(sandbox 12B 불가). **오너 dogfood 착수(GATE-1)가 가장 큰 갈림길.**

## Task — 실 12B 풀스택 e2e 검증 + GATE-1 정의 명확화 (오너 요청)

### Goals

- 오너 요청: async-pad 슬라이스(2b/2c/3/retry)가 실 12B(`192.168.1.22:9080`)로 엔드투엔드 관통하는지 검증. 2b work_log가 "완전 스택 e2e는 오너 풀스택 후속"으로 남겨둔 것을 폐쇄.
- GATE-1 정의 명확화(오너 "GATE-1이 정확히 뭔지 모르겠다").

### User Decisions and Rationale

- 오너: "dogfood는 작업 AI가 아니라 내가 하는 거" → GATE-1 본질 확인 요청.
- **GATE-1 정의**(`docs/plans/product-readiness-backlog.md:43`): **Phase 7(대화형 수정·아이디에이션·저작 감독) 진입 게이트**. 충족 조건 = `UX-1`(프론트 기본 루프) 완료 **+** `QUAL-1`(2주 dogfood 실사용 검토) 완료. 통과 시 dogfood에서 반복 재현된 문제 ↔ Phase 7 P1~P5 대조해 가치 입증된 첫 slice만 선택. 핵심 규칙(HANDOFF) "UX-1+QUAL-1 전 Phase 7 착수 금지". 현재 dogfood 미착수 = GATE-1 미충족. **GATE-1은 코드/검증 작업이 아니라 오너 dogfood 의사결정 게이트** — 작업 AI가 통과할 수 없고, 오너가 직접 실사용해 QUAL-1(2주)을 채워야 다음 기능군(Phase 7)이 열림. 그래서 "가장 큰 갈림길" = 개발이 막힌 게 아니라 오너 실사용 단계로의 분기.

### Completed work — 실 12B 풀스택 e2e (전부 green)

- **host-side 구성**(image rebuild 없이 working-tree, memory `live-smoke-runs-working-tree` 준수): gateway compose(`LLAMA_BASE_URL=http://192.168.1.22:9080 GATEWAY_PORT=8011` → `/health/ready`={"status":"ready"}) + application `uvicorn …:create_app --factory`(127.0.0.1:8010) + `scripts/generation_job_worker.py --loop`, mongo 27018(`agent-memory-mongodb`) 공유(`CORE_SOT_MONGO_TRANSACTIONS=false` non-transaction; job claim은 atomic `find_one_and_update`라 단일 노드에서 안전).
- **관통 결과**:
  1. 시드(project/draft/version POST) → async generate(medium) POST **202** (endpoint 배선 2c 정상, async 분기).
  2. job pending → worker claim → gateway **실 12B 호출** → **succeeded**, `result_scratch_id` 보존, 실 한국어 산문("아린은 거친 질감의 성문을 밀어냈다. 삐걱거리는 소리와 함께 육중한 문이 열렸고…").
  3. **retry 재실행 live**: 같은 job을 mongo에서 FAILED 강제 마킹 → retry POST **200 `pending`**(`mark_pending_for_retry` failure/lease clear 동작) → worker 재claim → **실 12B 재실행 → 새 scratch → succeeded**. scratch items=1(이전 결과는 H-3가 `request_id`로 정리 → 멱등 관통).
  4. retry over-strict: succeeded job → retry → **409**(FAILED만 재시도 가능, 정상).
- worker 로그에 `claim→succeeded` 이벤트(pass 37 `wgj:4447`, pass 42 `wgj:8d69`) 확인. 2b의 "오너 풀스택 후속" 폐쇄 — async-pad 전 슬라이스(저장소·worker·endpoint·패드·폴링·retry)가 실 12B에서 end-to-end 동작.
- 검증 후 임시 프로세스(application/worker/gateway)·mongo `e2e_async` db 정리.

### Next steps

- **async-pad 슬라이스(1~3 + retry) 실 12B 풀스택 관통 완료.** GATE-1(Phase 7 진입)은 오너 dogfood 의사결정 영역 — 오너가 UX-1 완료 + QUAL-1(2주 실사용)을 채우면 그때 dogfood 반복 문제 ↔ Phase 7 P1~P5 대조해 첫 slice 선택.

## Task — dogfood 발견 결손 2건 (오너 실사용 중)

### Goals

- 오너 dogfood(5173 브라우저) 중 발견: (1) 과거 테스트 draft 잔재로 `/drafts` 500, (2) 우측 레일 탭 전환(이어쓰기→분석→검토) 시 백그라운드 소통 통로 + 이어쓰기 입력값이 소실.

### User Decisions and Rationale

- 오너: (1) 잔재 정리, (2) **"URL이 바뀌는 게 아니라 레이어로 작동해야"** — 탭 전환은 컴포넌트 언마운트가 아니라 같은 페이지 내 레이어(display 토글) 전환이어야 state·통로가 유지. **세 탭 전부 레이어화** 선택(두 번 확인: review source 딥링크 테스트 조정 비용을 알고도).

### Issues found

- **이슈 1 (500)**: `GET /projects/{pid}/drafts` → `core_sot/service.py:890 _require_ordered_drafts` 500. 원인 = ordered-unit 구조(W0, SoT v1.7.10) 도입 *이전*의 과거 dev stack 잔재 draft가 현재 코드의 ordered 검증에 걸려 500. → mongo 볼륨 초기화(`docker compose down -v` + `up -d`)로 해결.
- **이슈 2 (탭 전환 state 소실)**: `DraftEditor.tsx`가 `activePanel === X && <X/>` 조건부 렌더라, (a) writing 탭이 아니면 `WritingPanel` 언마운트 → 입력 state(instruction·의도·next-unit·candidate, `WritingPanel.tsx:200-226`) 소실, (b) `GenerationPad`+`ScratchRecovery`(백그라운드 결과 통로)가 writing 탭 블록 안이라 비활성 탭에서 안 보임. `useGenerationJobs`(폴링/추적, DraftEditor 레벨)은 살아남지만 표시 통로가 closed.

### Completed work

- **잔재 정리**: compose mongo 볼륨 초기화 + 스택 재기동(application healthy / 5173 정상). 과거 ordered-이전 데이터 제거.
- **탭 레이어화(이슈 2 수정)**:
  - `DraftEditor.tsx`: `rail-panel` 안의 세 `{activePanel === X && (...)}` → 각각 `<div className="rail-layer"[.hidden] aria-hidden>` **항상 마운트** 레이어로. `panel` query param(selectPanel)·배지 ack·`aria-selected`는 무변경. → WritingPanel 입력 state + GenerationPad/ScratchRecovery 통로가 탭 전환에 유지.
  - `styles.css`: `.rail-layer { display:block }` + `.hidden { display:none !important }` 추가.
  - `WorkspaceReviewPanel.tsx`: **`tabActive` 게이트** — 패널은 항상 마운트(state 보존)하되 list/detail `useEffect` fetch를 `tabActive === false`일 때만 스킵. 비활성 탭의 fetch 부작용(기존 단순 테스트 mock 교란)을 0로. 더해 `detail?.actions?.find`·`data?.items?.length`·`data?.gate_findings?.length` 렌더 방어(불완전 응답/undefined 크래시 방지).
  - `DraftEditor.tsx`: `<WorkspaceReviewPanel tabActive={activePanel === "review"} />`.
  - `DraftEditor.test.tsx`: 항상 마운트 대응 — `stubFetch` review-inbox 분기는 `tabActive` 게이트로 불필요해져 원복(scratch만).

### Verification

- frontend **193 passed / 13 files** (회귀 없음 — 기존 source/review 테스트 전부 `tabActive` 게이트로 유지), `tsc` clean, build 103 modules(JS 399.03 kB, 레이어 코드로 +0.34 kB).
- frontend 컨테이너 rebuild → 5173 반영.

### 독립 검증 + 회귀 테스트 보강 (검증자)

- 오너 요청("검증하고 의심하고 또 의심")으로 commit `eb304ed` 독립 감사 → `docs/verifications/2026-07-22/rail-tab-layering.md`.
- 감사 결과: 코드 수정·부작용(게이트 정확성, AnalysisTrigger 무-useEffect라 게이트 비대칭 정당, `.hidden` 전역 충돌 없음)·green-bar(193 passed, tsc 0) 모두 재현. **그러나 이 커밋의 핵심 행위(WritingPanel 입력 state가 탭 전환에 유지)를 잠그는 회귀 테스트가 부재** — CLAUDE.md §4 미충족(테스트 변경은 코멘트 2줄뿐, 신규 테스트 0). 기존 테스트가 타이핑하는 "원고 본문"은 DraftEditor 소유 state라 원래도 소실 안 됨.
- **보강**: `DraftEditor.test.tsx`에 "preserves the Writing panel instruction input across a tab switch (탭 전환 state 유지)" 추가.
  - under-strict 가드 **증명**: writing 레이어를 조건부 렌더로 임시 되돌리면 `이어쓰기 지시` 필드가 `""`로 실패 → 원복 후 통과. 되돌리면 재실패함을 실측.
  - over-strict 방향: 탭 전환 중 "이 원고 분석" 버튼 존재 assert → no-op 전환 불가.
- 재검증: 전체 **194 passed / 13 files**, `tsc` clean.

### Next steps

- 오너 5173 dogfood에서 확인: 이어쓰기 medium 생성(백그라운드) → 분석/검토 탭 왕복 → **(a) 이어쓰기 입력값 유지 (b) 비활성 탭에서도 완료 배지/패드로 결과 확인**. 추가 dogfood 피드백 대기.

## Task — 레거시-데이터 `/drafts` 500 근본 수정 (dogfood 부채 폐쇄, 오너 결정 A=마이그레이션+endpoint 방어/503)

### Goals

- 커밋 `ef97c6a`로 추적 부채 등록된 `GET /projects/{pid}/drafts` 레거시-데이터 500의 근본 원인을 수정.
- 성공 기준: 레거시 draft(pre-W3, `unit_kind`/`position` 없음)가 있는 프로젝트에서 목록/생성/export가 500 아닌 명시적 503을 반환하고, 정상 프로젝트·클라이언트 입력 오류는 영향 없음(양방향 회귀로 잠금).

### User Decisions and Rationale

- **결정: A(마이그레이션 + endpoint 방어), 상태코드 503**. 오너에게 결정 브리프(선택지 A 둘 다 / B 마이그레이션만 / C endpoint만)를 제시하고 A + 503을 선택받음.
- **왜 A(둘 다)**: 로컬 1인 dogfood 단계라 지울 수 없는 실사용자 데이터는 아니나, 재현 가능하고 정본 보존 정책상 draft 손실 불가. `scripts/migrate_ordered_units.py`(docstring "run before deployment")가 데이터를 well-formed로 만드는 실해결이고, endpoint 방어는 미마이그레이션 상태에서도 opaque 500 대신 원인을 알려주는 안전망.
- **왜 503(409 아님)**: GET 읽기에 대한 409는 어색하고, 이 조건은 **서버 저장 데이터가 미준비**된 상태이므로 503(Service Unavailable)이 의미상 정확. `reorder_drafts`의 기존 409(입력 순열 오류 + 이 통합 케이스 혼재)와는 다른 관점이나, reorder는 500 누수가 없어 이번 수정 범위 밖(§3).

### Issues found

- **문제**: `_require_ordered_drafts`([service.py](../../../services/application/app/core_sot/service.py))가 레거시/손상 데이터에 `InvalidDraftOrder`를 던지는데, `list_drafts`/`create_draft`/`export_project` endpoint가 `NotFound`만 잡아 미포착 → **500**.
- **원인**: `InvalidDraftOrder`가 (a) 서버 데이터 무결성(마이그레이션 필요, `_require_ordered_drafts` 내부)과 (b) 클라이언트 입력 오류(잘못된 unit_kind `service.py:367`·`:734`, 순열 오류 reorder `:511`/`:522`/`:525` — 서브클래스 추가 후 현재 라인) **양쪽에 재사용**돼 endpoint가 단순 포착하면 입력 오류까지 503으로 잘못 분류될 위험.
- **패턴 스윕(§4)**: `_require_ordered_drafts` 호출 5개 메서드 → endpoint 노출 4개 중 `list_drafts`·`create_draft`·`export_project`가 500 누수, `reorder_drafts`만 기존 409로 방어. 추가로 `start_next_unit`(writing accept 경로, [accept.py:127](../../../services/application/app/writing/accept.py#L127))도 동일 누수 발견 → 도달성 낮고(list가 상류 가드) 테스트 하네스 무거워 추적 부채 등록(HANDOFF).

### Completed work

- **`DraftOrderIntegrityError(InvalidDraftOrder)` 서브클래스 신설**([core_sot/service.py](../../../services/application/app/core_sot/service.py)): 저장 데이터 무결성 위반 전용. `_require_ordered_drafts` 두 분기(metadata 누락·non-contiguous position)가 이 서브클래스를 던지도록 변경. 입력 오류 경로(354 등)는 기존 `InvalidDraftOrder` 유지.
- **3개 endpoint 방어**([main.py](../../../services/application/app/main.py)): `list_drafts`·`create_draft`·`export_project`에 `except DraftOrderIntegrityError → 503(detail=str(exc))` 추가. `reorder_drafts`는 서브클래스가 기존 `(Archived, InvalidDraftOrder)`절에 잡혀 409 유지(무변경).
- **회귀 6건(양방향)**:
  - service([test_ordered_units.py](../../../tests/test_ordered_units.py)) 1: 레거시 데이터→`DraftOrderIntegrityError`(under-strict), 잘못된 unit_kind→`InvalidDraftOrder`이되 서브클래스 아님(over-strict, 503 오분류 방지).
  - API([test_application_api.py](../../../tests/test_application_api.py)) 5: `LegacyOrderedDraftMigration503Test` — list/create/export 레거시→503(under-strict, 되돌리면 500 재발), 정상 프로젝트→200(over-strict), 잘못된 unit_kind→422 not 503(over-strict).
- **효과**: 레거시 데이터가 남아도 목록/생성/export가 opaque 500 대신 "migration is required" 503을 반환. 데이터 실해결은 마이그레이션 스크립트(`scripts/migrate_ordered_units.py` — **W3 선례, commit `56a73a3` Jul 19 산물이며 본 슬라이스에서 신규 작성한 게 아님**. 본 슬라이스는 이를 데이터 해결 경로로 참조만).

### Verification

- 포커스: `test_ordered_units.py` + `test_application_api.py` → **92 passed / 25 subtests**(hardening H-1 반영 후, +1).
- 전체 백엔드(`CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`): **1365 passed / 41 skipped / 328 subtests**(baseline 1358 + 초기 6 + H-1 1). 프론트·OpenAPI 무변경(순수 백엔드 예외 매핑). LLM 미사용.

### 오너 독립 검증 PASS + 비차단 hardening 반영

- **오너 독립 검증 PASS(차단 사유 없음)**: `docs/verifications/2026-07-22/legacy_drafts_500_503_integrity_mapping.md`. 되돌림 실험 2종(endpoint catch 제거 / 서브클래스 되돌림)으로 양방향을 직접 증명, full suite 1364 독립 재도출.
- 검증이 제기한 비차단 hardening 반영:
  - **H-1(reorder 잠금 갭)**: `test_reorder_on_legacy_data_stays_409_not_500` 추가 — reorder가 legacy 데이터에 409(500/503 아님)를 유지함을 핀. 종전 기계론+기존 order-error 테스트에만 의존하던 §3 무변경 정당화를 명시 잠금. **1365 passed**로 재도출.
  - **H-3(문서 정확도)**: work_log 라인 번호를 서브클래스 추가 후 현재값(367·734, 511/522/525)으로 정정, API 테스트 docstring "every endpoint"를 "세 read endpoint(list/create/export) + reorder 409/start_next_unit 부채"로 정확화.
  - **H-4(스크립트 출처)**: `migrate_ordered_units.py`가 W3 선례(`56a73a3`)이며 본 슬라이스 비작성임을 명시.
  - **H-2(503을 정본 SoT/OpenAPI에 반영)**: 최초 "관행 일치로 skip" 권고 → **오너 재검토로 뒤집힘**. 오너가 "선언 안 하는 게 제품성에 실제로 맞는가"를 물었고, 검토 결과 "선언 안 함"은 미덕이 아니라 H1이 남긴 **기존 부채**(성숙한 API 계약은 에러 상태코드를 문서화하는 게 정석)임을 확인. **결정: 부채가 아니라 다음 페이즈(H3)로 정면 처리** — 아래 "Task — H3 착수" 참조. 세 endpoint만 503 넣는 부분 패치는 오히려 최악(불완전+불일치)이라 skip 유지가 맞고, 대신 **CRUD 패밀리 전체 + SoT 전역 정책**을 슬라이스로 처리.

### Next steps

- `start_next_unit` 500 누수(추적 부채, HANDOFF) — writing_accept_endpoint에 `except DraftOrderIntegrityError → 503` + endpoint 에러 매핑 회귀. **→ H3 페이즈 S5로 흡수**(아래).
- 실 mongo에 레거시 데이터가 남은 배포/dev stack이 있으면 `scripts/migrate_ordered_units.py` 1회 실행이 정본 해결.

## Task — 공개 계약 조이기 H3(에러 응답 계약) 페이즈 착수 + 계획 문서 (오너 결정 D1~D4=A)

### Goals

- 위 500-fix 검증 H-2(503이 새 public 상태코드인데 정본/OpenAPI 미반영)를 계기로, H1(성공 응답 모델)이 남긴 **에러 응답 계약**을 페이즈로 정면 처리하기 위한 계획 문서 확정.

### User Decisions and Rationale

- **오너 의도**: "선언 안 하는 게 관행이니 맞다"는 약한 근거임을 지적. dogfood 보정마다 동일 갭이 재발하므로 **부채가 아니라 다음 스텝 페이즈로** 처리하고, 계획 문서 + 슬라이스 분해 후 진행하기로 함.
- **확정 결정(4)**: **D1=A** 균일 `{detail}` 에러 본문 유지(reason 코드는 실사용 근거 시 additive) · **D2=A** spine-first 슬라이싱(H1 선례) · **D3=A** SoT 전역 에러 정책 섹션 + endpoint별 OpenAPI 선언 · **D4=A** 이번 페이즈는 계약/타입만, 프론트 에러 UX 불변.
- **왜 A 패키지**: `gen:api`가 타입 전용 생성기 + 에러 본문 균일이라 선언의 실익은 타입 안전성이 아닌 **계약 정직성/자기발견성**. spine-first는 H1이 검증한 방식이고 diff가 작아 검증 가능. 프론트 UX·reason 코드는 실사용 근거가 쌓일 때 additive로 분리(Simplicity First).

### Completed work

- **계획 문서 신설**: [`docs/plans/api-error-response-contract-decisions.md`](../../plans/api-error-response-contract-decisions.md). H1/H2 계보의 H3로 프레이밍, 실측, D1~D4 옵션표+추천, 슬라이스 분해(S1 SoT 전역 섹션 → S2 CRUD family 20 → S3 analysis → S4 memory/source → S5 writing 잔여+`start_next_unit` 503 방어), 슬라이스별 검증 방법(런타임 불변 회귀 + openapi.json 재덤프 self-discovery + schema.d.ts 재생성/빌드 + exact-key).
- 이전 task의 H-2 "미반영 결정" 노트를 오너 재검토 반영으로 갱신(부채→페이즈).

### 독립 검증(조건부 합격) 반영

- **오너 독립 검증 조건부 합격**: `docs/verifications/2026-07-22/h3_error_response_contract_plan.md`. S2 lock 리스트 20 endpoint 전부 실코드 일치, D1~D4 건전 확인. 비차단 3건(F1/F2/F3) 정정:
  - **F1(분포 숫자)**: 502 20→19(1건 partial JSONResponse), 202×1은 에러 아님(async-generate success arm JSONResponse) 제외, 동적×9 raise+JSONResponse 혼재 명시. 404×62/400×30/503×18/409×16/504×7은 정확 확인됨.
  - **F2("에러 선언 3개")**: 에러 본문 모델 선언은 2개(revise-and-gate·accept). generate는 202 success만, 에러 모델 없음. 미선언 58→59.
  - **F3(S2 범위 자기모순)**: lock 리스트 20 나열 vs 라벨 "spine 14" 불일치. **오너 위임 결정: 20으로 재라벨**(spine 14 + CRUD 형제 6[brief 4·draft-order·project-export]). 14로 안 줄인 이유 = 형제 6은 같은 저복잡도 균일-에러 CRUD 표면이고 project-export가 503(페이즈 동기 endpoint) 포함 → 분리 시 동기 집합 분열. D2=A·S2 행·lock 헤딩·S5 문구 정합화.

### Next steps (다음 세션)

- **S1 착수**: SoT 전역 HTTP 에러 계약 섹션 신설 + 503-migration/`start_next_unit` 명문화. 정본(SoT) 편집.
- 이후 S2(CRUD family 20)부터 각 슬라이스 별도 커밋.

## Task — 실 12B 풀스택 e2e 관통 (오너 테스트 머신) + 라이브 결손 2건 폐쇄

### Goals

- 오너의 실제 사용자 머신(RTX 3060 12GB, in-stack llama 12B)에서 **집필 루프 전체 + 비동기 생성 패드**를 브라우저 동등 경로(`:5173/api`)로 관통 확인한다. sandbox에 12B가 없어 unit/build 증거로 대체돼 있던 축을 실측으로 닫는다.
- HANDOFF가 남긴 잔여 후속 중 "실 12B 풀스택 medium/long 생성→worker→패드 표시 오너 관통 확인"이 직접 대상.

### 결손 1 — prompt template 본문 변경으로 기존 배포 기동 불가 (스택이 아예 안 뜸)

- **문제**: `docker compose up` 시 application·generation_worker·worker가 전부 `PromptTemplateConflict: prompt template version already exists`로 죽어 스택이 기동되지 않았다. 이 머신의 컨테이너들이 3일 전부터 `Exited (1)`이었던 것도 같은 원인으로 보인다.
- **원인**: v1.7.23(character aspect, commit `41999ef`)이 `analysis_extract_v3`의 **버전 문자열은 그대로 둔 채 본문에 aspect 안내 1줄을 추가**했다. `seed_template()`([prompt_templates.py:104-108](../../../services/application/app/analysis/prompt_templates.py#L104-L108))은 같은 version에 다른 본문이 이미 저장돼 있으면 `PromptTemplateConflict`를 던지고, 이 호출이 `create_app()` 안에 있어 **기존 Mongo를 가진 배포에서만** 기동이 실패한다. sandbox는 항상 빈 DB로 뜨기 때문에 회귀·CI가 잡을 수 없었다.
- **확인**: 배포 DB(`ai_writing_system`)의 v3 본문 sha256 `4376310080…b52a` = 복원한 코드 상수와 byte-identical. 코드 v3와의 diff는 aspect 1줄뿐.
- **오너 결정 A(v4 신설)**: 프로젝트 선례(v1·초기 v2 immutable 보존, 본문이 바뀔 때 v3 신설)와 일치. 과거 candidate 61건의 `prompt_version` 추적성이 보존된다. DB 덮어쓰기(B)는 그 추적성을 거짓으로 만들어 기각.

#### Completed work (결손 1)

- [prompt_templates.py](../../../services/application/app/analysis/prompt_templates.py): `ANALYSIS_EXTRACT_PROMPT_VERSION_V3`/`_TEMPLATE_V3`로 **배포된 구본문을 immutable 복원**하고, aspect 포함 본문을 `analysis_extract_v4`(= 현행 `ANALYSIS_EXTRACT_PROMPT_VERSION`)로 승격. `seed_analysis_extract_v4()` 신설.
- [main.py](../../../services/application/app/main.py): `_default_prompt_template_service`의 두 분기(in-memory/Mongo)가 v4까지 시딩.
- 현행 기본을 시딩하려던 호출부를 v4로 이동: `tests/test_analysis_extractor_schema.py`(6), `tests/test_analysis_prompt_builder.py`(6), `scripts/phase2a_provider_live_smoke.py`(1).
- **재발 방지 회귀 4건**([test_prompt_templates.py](../../../tests/test_prompt_templates.py)) — 이 결손의 본질은 "출시된 본문을 조용히 고칠 수 있다"는 것이라, 그 행위 자체를 잠갔다:
  - `test_shipped_template_bodies_are_immutable`: v1/v2/v3 본문 sha256 핀(subtest 3). 출시본을 고치면 실패하며, 주석이 "해시를 갱신하지 말고 새 버전을 만들라"고 지시한다.
  - `test_optional_character_aspect_guidance_is_v4_only`: aspect 줄이 v4에만 존재(under-strict: v3로 되돌리면 재실패 / over-strict: v4에서 빠져도 실패).
  - `test_seed_sequence_replays_against_previously_seeded_storage`: v1~v3가 이미 시딩된 저장소에 현재 코드가 재시딩 — 이번 기동 실패의 직접 재현.
  - `test_seed_analysis_extract_v4_is_current_and_keeps_v1_v2_v3`.
- **mutation 확인**: aspect 줄을 v3 본문에 되돌리자 위 회귀 2건이 재-fail, 복원 시 green.

### 결손 2 — self-report 출력 상한 1024 고정 → `invalid_report` truncation

- **문제**: 비동기 medium/long job이 `invalid_report`로 실패했다(관측 실패율 5회 중 3회). 실패 detail이 전부 JSON parse 오류.
- **원인**: v1.7.22가 **산문** 출력을 프리셋화(1024/2048/4096)했지만, 그 산문을 요약하는 **self-report의 출력 상한은 `WRITING_REPORT_MAX_TOKENS` 기본 1024로 고정**돼 있었고 compose에 선언조차 없었다([main.py](../../../services/application/app/main.py) `_build_report_service`). report JSON이 상한에서 잘려 파서가 실패한다.
- **확증(실험)**: 실패 지점이 입력 길이와 무관하게 **항상 같은 구간**에서 끊긴다 — worker 실패 `char 2199`/`2267`, report 직접 호출 실패 `char 2288`/`2344`. 상한만 4096으로 올려 동일 입력을 재현하자 **truncation 시그니처 0건**(직접 호출 4회 + async 4회). 잔존 실패 2건은 `report field must be an array`로 **다른 유형**(HANDOFF에 기록된 12B 간헐 비-배열 report, repair가 흡수하는 축)이다.
- **범위**: 231자짜리 짧은 산문에서도 재현됐다 → async 전용이 아니라 **동기 short 경로 포함 전 경로**. report가 장황해지면 프리셋과 무관하게 걸린다.

#### User Decisions and Rationale (결손 2)

- **오너 결정**: 비례 매핑은 불필요하고, 산문 최대치(4096)보다 위에 두되 이 시스템의 VRAM(기본 12GB, 최소 8GB) 안에 들어와야 한다. 구체 수치는 구현자 판단에 위임("7~8000 정도?").
- **구현 판단 = 6144** (오너가 제시한 7~8000에서 하향, 근거 제시 후 적용):
  - `max_tokens`는 VRAM을 선점하는 값이 아니라 **프롬프트와 함께 llama 슬롯 컨텍스트(`LLAMA_CTX_SIZE` 8192)를 나눠 쓰는 예산**이다. 8000을 주면 프롬프트가 192 토큰만 넘어도 서버가 남은 만큼으로 클램프하므로, 숫자가 게이트 역할을 못 하고 truncation이 그대로 재발한다.
  - 8000을 실효화하려면 ctx를 함께 키워야 하는데 실측 VRAM 여유가 2.9GB(12288 중 9211 사용)뿐이고, 오너가 하한으로 든 8GB 머신에서는 기동 자체가 어렵다.
  - 6144 = 산문 최대(4096)의 1.5배로 "최대보다 위" 요구를 충족하면서 프롬프트에 2048 토큰을 남겨 상한이 실제 한계로 작동한다.

#### Completed work (결손 2)

- [main.py](../../../services/application/app/main.py): `WRITING_REPORT_DEFAULT_MAX_TOKENS = 6144` 상수 신설(산문 프리셋과의 결합·ctx 천장 근거를 주석에 명시), `_build_report_service`가 `_env_int`로 이를 읽는다.
- [docker-compose.yml](../../../docker-compose.yml): `application`·`generation_worker` 양쪽에 `WRITING_REPORT_MAX_TOKENS: "${WRITING_REPORT_MAX_TOKENS:-6144}"` 명시(종전엔 어느 서비스에도 없어 기본값이 암묵적이었다).
- **회귀 4건**([test_writing.py](../../../tests/test_writing.py) `WritingReportBudgetTest`) — 단순히 숫자를 핀하지 않고 **결합 자체**를 잠갔다:
  - `test_report_budget_exceeds_longest_prose_preset`: report 예산 > 현재 최대 산문 프리셋(하드코딩 4096이 아니라 `_writing_output_length_tokens()`에서 도출).
  - `test_raising_the_long_preset_alone_is_caught`: `WRITING_OUTPUT_LENGTH_LONG`만 올리면 불변식이 깨짐을 확인 — 다음 사람이 산문 상한만 올리는 걸 막는다.
  - `test_default_budget_reaches_the_report_provider`(over-strict) / `test_report_budget_is_env_adjustable`.
- **mutation 확인**: `_build_report_service`를 옛 `1024` 리터럴로 되돌리자 `test_default_budget_reaches_the_report_provider`가 `1024 != 6144`로 재-fail.

### e2e 관통 결과 (실 12B, 브라우저 동등 `:5173/api`)

전 구간 통과. 각 단계는 프론트(`client.ts`/`WritingPanel`/`useGenerationJobs`)와 같은 호출 순서를 따랐다.

- **집필 루프**: 프로젝트 생성 → ProjectBrief(문체 설정) → 원고 저장(v1) → **동기 이어쓰기 short 200**(실 12B, 193자, 35s) → **Gate `pass`**(10.5s) → **accept 200**(28.6s) → version 2 + snapshot + pending analysis job.
- **분석 → 검토함**: catalog 2건 생성 → job create가 **accept가 심은 job과 동일 ID로 수렴**(`idempotent_replay=true`) → run **succeeded, candidate 3건**(33.5s, 중복 0) → Review Inbox 3건 + 어포던스 `{confirm,reject,edit}` → **confirm 200 → memory 승격**, inbox 3→2.
  - **v1.7.23 `aspect`가 라이브에서 처음 확증**됐다: 실 12B가 `{"name":"윤","observation":"…","aspect":"trait"}`, `"aspect":"voice"`를 실제로 추출.
- **비동기 패드**: medium/long 모두 **202 + job**(D5=A 분기), generation_worker가 claim→실 12B 실행→**scratch에 `version_id` 보존한 채 append**(패드 표시 재료), 같은 `request_id` 재요청은 동일 job으로 수렴. **retry(v1.7.28) 라이브 검증**: FAILED job → retry 200 `pending` → worker 자동 재claim → **succeeded(41s)**; succeeded job에 retry → **409**.
- **export**: 통합 txt/markdown이 원본+AI 이어쓰기를 verbatim 연결, `manifest=true`가 `version_id`/`content_hash` 포함 traceability 반환.

### Verification

- 백엔드 전체: **1333 passed / 76 skipped / 331 subtests**(`--ignore=tests/test_memory_mongo.py`). 결손 1 수정 시점 1329 → 결손 2 회귀 4건 추가 후 1333.
- 두 결손 모두 mutation으로 회귀 물림 확인(위 각 항목).
- 라이브: 수정 반영(6144) 후 report 직접 호출·async job 재측정.

### 수정 반영 후 라이브 재확인

- **6144 반영 상태 async PASS**: medium **succeeded(78s)**, long **succeeded(62s)**. llama 로그가 `n_decoded = 1031 … truncated = 0`으로 **자연 종료**를 직접 보고 — 실제 report 소비가 ~1000토큰이라 1024 상한에 정확히 걸렸던 것이고, 6144는 6배 여유다.
- **재확인 중 발견한 신규 운영 함정**: `application` 재기동 후 frontend nginx가 **옛 upstream 컨테이너 IP를 계속 물어 `:5173/api`가 전부 502**가 된다. 검증 스크립트가 30분 매달린 실제 원인이 이것이었다(llama는 idle인데 클라이언트만 대기). `docker restart ai_writte_system-frontend-1`로 즉시 복구. 기존에 기록된 healthcheck false-negative(`localhost`→`::1`)와는 다른 문제이며 HANDOFF 차후 검증 7번에 등록했다.

### Next steps

- 오너 dogfood 착수(GATE-1)가 여전히 가장 큰 갈림길. 이번 e2e로 "실 12B 풀스택 관통" 잔여 후속은 닫혔다. **단, 관통은 HTTP 경로까지이며 브라우저 UI(패드 렌더·완료 배지·폴링·다시 시도 버튼)는 미검증** — HANDOFF 차후 검증 1번.
- 잔존 `report field must be an array`(12B 간헐 비-배열 report)는 truncation과 별개 축이며 repair가 흡수한다. 실패율이 dogfood에서 문제가 되면 그때 프롬프트 축으로 별도 판단(Gate quality baseline 선례).
