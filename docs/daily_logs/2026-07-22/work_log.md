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
