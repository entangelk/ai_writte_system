# 검증 기록 — 비동기 생성 + 결과 패드 증분 3: 읽기 전용 패드 + 완료 배지 + 5초 폴링 (D6=A)

## Subject metadata

- **날짜**: 2026-07-22
- **요청자**: 오너 ("작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래?" — 명시적 검증 트리거)
- **검증자**: 독립 AI 감사자 (작업자와 다른 세션, CLAUDE.md §5 기준)
- **대상 슬라이스/아티팩트**: 비동기 생성 + 결과 패드 슬라이스 **증분 3** (D6=A, 프론트 전용). `frontend/src/writing/useGenerationJobs.{ts,test.ts}` · `GenerationPad.{tsx,test.tsx}` · `frontend/src/drafts/DraftEditor.{tsx,test.tsx}` · `frontend/src/writing/WritingPanel.{tsx,test.tsx}` · `frontend/src/api/client.ts` · `frontend/src/styles.css`
- **정본 계약 참조**: [`docs/plans/async-generation-pad-decisions.md`](../../plans/async-generation-pad-decisions.md) (D1~D7, 2026-07-20 확정; 본 증분은 **D6=A + D1=A/D4=A 소비**) · [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.27** (§264/§271/§272 — 본 증분은 bump 없음, 이유는 §264 전방 마커)
- **작업 출처**: working tree, **uncommitted** (`git status`로 확인 — 커밋 미수행, 오너 요청 전까지)

## Scope

본 증분(D6=A)의 계약 범위는 **순수 프론트엔드**: 이미 계약된 `GET .../writing/generation-jobs/{job_id}`(증분 2a/2c)·`GET .../writing/scratch`(증분 1) 엔드포인트만 소비해, 2c가 개통한 async 경로(medium/long → `202` job)의 결과를 보여주는 UI를 채운다. 백엔드/OpenAPI 무변이어서 **SoT bump 없음**이 작업자 주장이다.

정본 계약 읽기 **전**에 스코핑한 계약 표면:

1. **D6=A 결정 리터럴** — "배지/인앱 표시 + 폴링 **5초**(생성 중일 때만)"; "실패 조용함 없음"; 브라우저 Notification 미사용 (decisions brief D6 절 + Owner decisions 121행).
2. **D1=A 의존** — async 결과와 복구분은 같은 scratch 저장소 (Owner decisions 116행). 즉 완료 결과는 기존 `ScratchRecovery`가 렌더.
3. **D4=A 의존(소비만)** — job 상태 `pending/running/succeeded/failed`; succeeded는 worker가 scratch에 결과 append (Owner decisions 119행, SoT §271).
4. **SoT §264 전방 마커** — "패드 UI가 읽어 표시한다[증분 3]" (이 read가 bump 없이 정당화되는 근거).
5. **스키마 리터럴** — `WritingGenerationJobPayload`(job_id/status/output_length/failure_reason 필드) + backend `WritingGenerationJobStatus`·`WritingGenerationJobFailureReason` enum (증분 2a에서 이미 계약).
6. **구현 코드 + 회귀 테스트 + 훅/통합 테스트** (신규 17개 단정).

## Methodology

독립 재도출 — 작업자의 work_log/CHANGELOG 주장을 그대로 믿지 않고 일차 소스에서 재검증.

1. **계약 스코핑**: decisions brief D1~D7 + SoT §264/§271/§272 + backend `generation_job.py` enum + `schema.d.ts` 를 읽어 boundary matrix(should-fire / should-NOT-fire + 리터럴) 구축.
2. **리터럴 일치(spec↔impl)**: backend `services/application/app/writing/generation_job.py`의 status/failure-reason enum ↔ 프론트 `useGenerationJobs.ts`·`GenerationPad.tsx` 상수 대조. `schema.d.ts` ↔ `client.ts` 타입 대조.
3. **테스트 코드 감사(audit subject)**: 4개 테스트 파일의 각 단정이 (a) 계약을 실제로 고정하는지 (b) under-strict(버그 재도입 시 re-fail) (c) over-strict(should-NOT-fire 정상 케이스) 양방향 잠금이 있는지 확인.
4. **재실행(정확한 명령)**:
   - `cd frontend && npx vitest run` (전체 스위트)
   - `npm run build` (= `tsc --noEmit && vite build`)
   - `npm run gen:api` 후 `git status --short src/api/schema.d.ts` + `git ls-files`/`git check-ignore` 로 byte-identical 독립 확인
   - `git status --short | grep -E 'services/|scripts/'` 로 백엔드 무변 확인

## Findings

### 1. Boundary matrix — D6=A 계약 분기 전 cell 매핑됨

모든 계약-필수 분기(should-fire / should-NOT-fire)가 명명된 회귀 테스트에 매핑되고, 적용 가능处 양방향 잠금이 있다. **빈 cell 없음.**

| 분기 | 방향 | 잠금 테스트 (file:line 근거) | 구현 (file:line) |
|---|---|---|---|
| 활성(pending/running) job 있을 때만 폴링 | should-fire | `useGenerationJobs.test.ts:77` "polls a tracked job every interval" | `useGenerationJobs.ts:79-80,124` (`if (!hasActive) return` + `setInterval`) |
| 활성 job 없으면 폴링 안 함(no fetch) | should-NOT-fire | `useGenerationJobs.test.ts:69` "does not poll when no job is tracked" | 같은 게이트 |
| terminal 전이 시 `onSettled` + `settledUnseen`↑ | should-fire | `useGenerationJobs.test.ts:95,121` (succeeded/failed 둘 다) | `useGenerationJobs.ts:111-112` |
| succeeded는 active에서 제거(결과는 scratch) | should-fire | `useGenerationJobs.test.ts:110` "drops it from active" | `useGenerationJobs.ts:113-115` |
| failed는 패드에 잔존("실패 조용함 없음") | should-fire | `useGenerationJobs.test.ts:139` + `GenerationPad.test.tsx:51` "never silent" | `useGenerationJobs.ts:113,116-118` + `GenerationPad.tsx:53-65` |
| settle 후 폴링 정지 | should-NOT-fire(under-strict 명시) | `useGenerationJobs.test.ts:114-118` + `DraftEditor.test.tsx`(통합) settle 후 `jobPolls` 증가 없음 | `useGenerationJobs.ts:80,129` (hasActive false → cleanup) |
| 일시적 fetch 실패 시 failed 아님(재시도) | should-NOT-fire | `useGenerationJobs.test.ts:144` "leaves active and retries" | `useGenerationJobs.ts:90-93` (`catch { return }`) |
| draft 변경 시 추적 리셋(이전 draft 폴링 안 함) | should-fire | `useGenerationJobs.test.ts:191` "resets when draft changes" + 207행 no-poll 단정 | `useGenerationJobs.ts:70-73` |
| async 분기 → 부모에 job 전달(`onAsyncJobStarted`) | should-fire | `WritingPanel.test.tsx:674` (under-strict 명시) | `WritingPanel.tsx:292` + `DraftEditor.tsx:653` |
| 동기 short 경로는 `onAsyncJobStarted` 미호출 | should-NOT-fire(over-strict) | `WritingPanel.test.tsx:685` "does not fire for sync short" | `WritingPanel.tsx:291` (`"job" in produced` 가드) |
| 완료 배지 점등(off-tab) | should-fire | `DraftEditor.test.tsx`(통합) 오프탭에서 배지 등장 | `DraftEditor.tsx:617-624` |
| writing 탭 활성 시 배지 소거(acknowledge) | should-fire | `DraftEditor.test.tsx`(통합) 복귀 시 소거 + `useGenerationJobs.test.ts:165` | `DraftEditor.tsx:173-177` + `useGenerationJobs.ts:62` |
| 빈 패드는 null 렌더 | should-NOT-fire | `GenerationPad.test.tsx:26` "renders nothing" | `GenerationPad.tsx:33` |
| 완료 결과는 scratch에 표시(D1=A) | should-fire | `DraftEditor.test.tsx`(통합) "surfaces its result in the pad on completion" | `DraftEditor.tsx:108`(onSettled→scratchRefresh) + `636-640`(ScratchRecovery) |

신규 단정 수: `useGenerationJobs.test.ts` 8 + `GenerationPad.test.tsx` 5 + `WritingPanel.test.tsx` +2 + `DraftEditor.test.tsx` +2 = **17**. 작업자 주장(17)과 일치.

### 2. 리터럴 일치(spec ↔ implementation) — 전부 unchanged

- **폴링 주기 5000ms** — `useGenerationJobs.ts:10` `GENERATION_POLL_INTERVAL_MS = 5000`. D6=A "5초"와 일치.
- **status enum** — backend `generation_job.py:46-50` (`pending/running/succeeded/failed`) ↔ 프론트 `useGenerationJobs.ts:11` (`ACTIVE_STATUSES = {pending, running}`) + settle 핸들러의 `succeeded`/`failed` 분기. 완전 일치.
- **failure reason enum (7종)** — backend `generation_job.py:53-85` (`invalid_request`/`invalid_report`/`context_budget_exceeded`/`context_search_failed`/`provider_error`/`provider_timeout`/`internal`) ↔ 프론트 `GenerationPad.tsx:15-23` `FAILURE_COPY` **동일 7키**. 미러링 누락 없음. 미지 reason은 raw fallback(`GenerationPad.tsx:57-59`) + `GenerationPad.test.tsx:64`로 잠금.
- **엔드포인트 경로** — schema op `get_writing_generation_job_..._job_id__get`(path `{project_id, job_id}`) ↔ `client.ts:234-243` `/projects/${projectId}/writing/generation-jobs/${encodeURIComponent(jobId)}`. 일치.
- **타입 체인** — `client.ts:75` `WritingGenerationJob = WritingGenerationJobPayload`(schema.d.ts:1559) — 프론트가 읽는 `job_id`/`output_length`/`status`/`failure_reason` 전부 스키마에 존재. `WritingGenerationJobAcceptedPayload.job`(schema.d.ts:1556) → `produced.job`(`WritingPanel.tsx:292`) 타입 정확.

### 3. 재실행 결과 — 작업자 주장 전부 재현

| 항목 | 작업자 주장 | 독립 재실행 결과 |
|---|---|---|
| frontend suite | 180 passed / 13 files | **180 passed / 13 files** ✓ ( Duration 211s, hang 아님 — setup 66.5s/environment 364.5s 병렬 cold run) |
| 신규 분량 | 163→180 (+17) | useGenerationJobs 8 · GenerationPad 5 · DraftEditor 37(was 35) · WritingPanel 44(was 42) = +17 ✓ |
| `tsc --noEmit` | clean | clean(build가 vite 단까지 진행) ✓ |
| build | 103 modules / JS 397.98 kB | **103 modules / CSS 19.42 kB / JS 397.98 kB** ✓ |
| `gen:api` | byte-identical | `schema.d.ts` **tracked·non-ignored** 상태에서 재생성 후 `git status` 변경 없음 → byte-identical ✓ (`openapi.json`은 gitignore 중간 산출물) |
| 백엔드 | 무변 | `git status`의 `services/`·`scripts/` 전부 clean ✓ |

### 4. 계약 자기일관성 — 모순 없음

- §264 전방 마커("패드 UI가 읽어 표시한다[증분 3]", v1.7.26 기재)가 본 증분의 read를 사전 서술 → "SoT bump 없음" 정당. SoT 파일은 본 증분에서 무수정(git status 확인) → v1.7.27 유지 일치.
- decisions brief 상태→"구현 완료(증분 1~3)"·CHANGELOG(2026-07-22)·HANDOFF(Next Tasks→dogfood GATE-1) 전부 정합. stale 섹션은 재작성(HANDOFF 원칙 준수).
- D6=A "5초/생성 중만/실패 조용함 없음" ↔ 구현/테스트/문서 3곳 모두 동일 문구. 내부 모순 발견 안 됨.

## Issues / Risks

### Blocking (계약 의무) — **없음**

boundary matrix에 빈 cell이 없고, 모든 계약 리터럴이 코드에 unchanged로 존재하며, spec↔impl·계약 자기일관성이 모두 성립한다. over-strict/under-strict 양방향 잠금이 D6=A의 모든 should-fire/should-NOT-fire 분기에 있다.

### Hardening recommendations (비차단, 현행 spec을 넘는 보강)

- **H-1 — 폴링 주기 5000ms 리터럴 직접 핀 권장**: `GENERATION_POLL_INTERVAL_MS`는 테스트에서 상수 **참조**로 사용되고(`useGenerationJobs.test.ts:53` `tick()`), 통합 테스트는 `pump(5000)`로 5000ms를 전진하지만, `expect(GENERATION_POLL_INTERVAL_MS).toBe(5000)` 같은 **직접 단정**은 없다. 따라서 값을 6000으로 바꿔도 현재 훅 테스트는 통과한다(통합 `pump`는 6라운드×5000=30000ms 전진이라 6000ms 간격도 발화). 오너가 "10초도 괜찮다"를 **5초로 확정**(decisions brief 121행)한 결정을 보호하려면 1줄 직접 핀이 권장된다. 리터럴 자체는 코드에 unchanged로 존재하므로 spec↔impl 규칙은 **만족**하며, 이 핀은 그 이상의 보강이다.
- **H-2 — "idle no-poll" 가드 메커니즘이 mutation-pinning이 아님**: `useGenerationJobs.test.ts:69`의 "idle never fetches" 단정은 **관측 가능 계약**(idle일 때 fetch 없음)은 잠그지만, `if (!hasActive) return`(`useGenerationJobs.ts:80`) 가드 자체를 잠그지는 않는다 — 가드를 제거해도 `poll()`이 `jobsRef.current.filter(isActive)`로 빈 배열을 폴링해 fetch가 일어나지 않기 때문이다. D6=A의 관측 계약(유휴 시 네트워크 없음)은 어느 쪽이든 성립하므로 **비차단**이나, 가드가 보장하는 자원-효율(영구 setInterval 미가동)을 명시적으로 잠그려면 별도 단정이 필요하다.
- **H-3 — 다중 job 동시 폴링 직접 테스트 부재**: 폴링은 `Promise.all(stillActive.map(...))`(`useGenerationJobs.ts:84-86`)로 다수 active job을 병렬 폴링하지만, 단정은 단일 job만 관통한다. 메커니즘은 건전(활성 job이 남으면 `hasActive` true 유지→간격 유지)하며 work_log도 이를 인지 후보로 명시했으므로 추적 중인 부채다.

## Verdict

**합격 (PASS).**

이유(load-bearing):
1. D6=A(및 D1=A/D4=A 소비)의 boundary matrix에 **빈 cell이 없음** — 모든 should-fire/should-NOT-fire 분기가 명명된 회귀 테스트에 매핑되고 양방향 잠금이 있다.
2. 모든 계약 리터럴(5000ms · status 4종 · failure reason 7종 · 엔드포인트 경로)이 코드에 **unchanged**로 존재하고 backend enum과 정확히 미러링된다.
3. 계약 자기일관성·spec↔impl 일치에 모순이 없고, "SoT bump 없음"이 §264 전방 마커로 정당화된다.
4. 재실행(180 passed / tsc clean / build 103·397.98 kB / gen:api byte-identical / 백엔드 clean)이 작업자 주장과 전부 일치한다.

H-1/H-2/H-3은 현행 spec을 넘는 보강 후보(비차단)이며, 본 슬라이스 종료를 막지 않는다.

## Outstanding items

- **작업 미커밋**: 본 증분은 working tree에만 존재(`git status`로 확인). 오너가 커밋을 요청하면 진행 — 현재는 요청 전이라 미수행(작업자 판단과 일치).
- **슬라이스 종료**: 증분 1~3 전부 완료. 남은 후속은 **슬라이스 밖**: (a) 오너 dogfood 착수(GATE-1, 가장 큰 갈림길), (b) **실 12B 풀스택** medium/long 생성→worker→패드 표시 관통(sandbox에서 12B 불가 — 본 검증은 단위/통합 레벨만, live 12B e2e 미관통), (c) per-draft 상한(기본 20) 밀어냄 관찰 시 `WRITING_SCRATCH_MAX_PER_DRAFT` 기본값만 조정(재개정 불요), (d) 재시도 UI(D4 deferred).

## Reproduction

```bash
# 전체 스위트 + 타입 + 빌드 (frontend/)
cd frontend
npx vitest run                       # 기대: 180 passed / 13 files
npm run build                        # 기대: tsc clean, 103 modules, JS 397.98 kB

# OpenAPI 재생성 → schema.d.ts byte-identical + 백엔드 무변 확인
npm run gen:api
git status --short src/api/schema.d.ts   # 기대: 출력 없음 (tracked, non-ignored)
git -C "$(git rev-parse --show-toplevel)" status --short | grep -E 'services/|scripts/'
                                         # 기대: 출력 없음 (백엔드 무변)

# boundary matrix 재감사(선택): 신규 테스트만 빠르게
npx vitest run src/writing/useGenerationJobs.test.ts src/writing/GenerationPad.test.tsx
```
