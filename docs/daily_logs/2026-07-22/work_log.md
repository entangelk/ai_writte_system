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
