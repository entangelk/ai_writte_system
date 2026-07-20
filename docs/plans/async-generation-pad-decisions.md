# Decision brief — 비동기 생성 + 결과 패드

상태: `결정 확정 (2026-07-20) — D1~D7, 구현 미착수`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md) (v1.7.20 — **본 슬라이스가 개정을 요구함**), [`unaccepted-candidate-persistence-decisions.md`](unaccepted-candidate-persistence-decisions.md), [`writing-style-and-length-control-decisions.md`](writing-style-and-length-control-decisions.md), [`05-writing-ai.md`](05-writing-ai.md)
작성: 2026-07-20

> **오너 결정 완료** — D1~D7이 "Owner decisions" 절에 확정 기입됐다. 각 D절의 옵션·추천은 결정에 이른 분석 기록이며 **충돌 시 "Owner decisions" 절이 우선**한다. 구현은 미착수다.

## Decision needed

긴 생성(2048/4096 프리셋, 실측 ~46초/~91초)을 **백그라운드로 실행**하고 결과를 분할 화면 오른쪽 **읽기 전용 패드**에 쌓아, 작가가 대기 중에도 집필을 이어가며 원하는 것을 **복사해 쓰도록** 한다. 이때 실행 위치·결과 저장소·알림 방식과, 그로 인해 발생하는 **SoT v1.7.20 개정 범위**를 확정한다.

## 왜 정본 계약 변경이 (거의) 필요 없는가 — 설계의 핵심

초기 논의에서 "대기 중 집필"이 정본 계약과 충돌한다고 보았으나, **오너의 패드 설계는 그 충돌을 우회한다.** 정확한 이유:

- `POST /writing/generate`는 **정본을 전혀 쓰지 않는다**. 유일한 쓰기가 `writing_scratch.save`이고, 그것은 SoT v1.7.20이 이미 **Core SOT 외부·정본 아님**으로 계약한 tier다.
- 패드는 **읽기 전용 표시**이고 작가가 **직접 복사**한다. 따라서 `accept`를 타지 않는다.
- accept를 타지 않으므로 **`base_version_id` stale 검사(409)가 발생하지 않고**, accept 후 `reloadLatest()`가 **편집기의 미저장 입력을 덮어쓰는 경로도 발생하지 않는다**.
- 저장은 **작성창에서만** 일어난다(기존 명시적 version save 계약 그대로).

즉 "명시적 version save only", stale guard, accept 원자성 같은 **정본 계약은 손대지 않는다**. 개정이 필요한 곳은 **오직 scratch tier의 용도·정리 규칙**(아래)이다.

## ★ 계약 상호작용 선surface — SoT v1.7.20 개정이 필요하다

패드를 `writing_drafts_scratch`에 얹으면 **2026-07-20에 승격한 정본 계약 두 조항과 충돌**한다. 조용히 넘기지 않고 개정 대상으로 명시한다.

| 현행 SoT v1.7.20 조항 | 충돌 내용 |
|---|---|
| scratch는 "accept 전 소실을 막는 **복구 전용 low-stakes tier**" | 패드 저장소로도 쓰면 **용도가 확장**된다 → 문구 개정 필요 |
| "**정본 version이 저장된 accept만 scratch를 정리한다**" — 해당 draft의 **scratch 전체** 삭제 | 동기 경로에서 **한 번만 채택해도 패드가 통째로 사라진다**(`clear_draft` → draft 전체 삭제) → 정리 규칙 축소 필요 |

두 조항 모두 **구현과 함께 SoT를 개정**한다(CLAUDE.md: 계약 리터럴 변경은 계획/스키마에 함께 반영).

## 현재 동작 (grounding)

- **오른쪽 분할 rail은 이미 있다** — W1으로 구현 완료(`이어쓰기|분석|검토` 탭). 생성 결과는 이미 편집기가 아니라 rail의 `WritingPanel`에 뜬다. **없는 것은 백그라운드 실행·알림·대기 중 집필뿐이다.**
- **scratch는 패드의 절반 이상을 이미 갖췄다** — draft별 미채택 후보를 **이력으로 보관**(D1=B), per-draft 상한 20(env 조정), `GET/DELETE /projects/{id}/writing/scratch?draft_id=` 목록·삭제 API.
- **scratch 레코드에 `version_id`가 없다** — 현재 `draft_id`/`request_id`/`task_type`/`output_type`/`instruction`/`candidate_text`/`intent`/`created_at`뿐이라 "어느 version 기준으로 생성됐는지" 표시 불가.
- **worker는 이미 상시 compose 서비스**다 — `--loop` drain + SIGTERM graceful shutdown, **atomic outbox claim이 이중 실행을 막아 single-replica로 안전**. 다만 현재 용도는 **색인 outbox drain 전용**이며 **LLM 작업 fire-and-forget 선례가 없다**.
- **job 상태 선례가 있다** — Analysis가 `pending/running/succeeded/failed`와 실패 사유·retry 계약을 이미 갖는다.
- **푸시 인프라가 없다** — SSE/WebSocket 미사용. 알림은 폴링이 유일한 현실적 수단이다.

---

## D1 — 결과 저장소

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `writing_drafts_scratch` 재사용 + SoT 개정 | 패드 결과를 기존 scratch에 저장 | 이력·상한·목록 API·복구 UI가 **이미 존재**, 두 저장소가 같은 것(미채택 생성물)을 담는 중복 회피 | SoT v1.7.20 용도·정리 조항 개정 필요 |
| B. 패드 전용 저장소 신설 | scratch는 복구 전용 유지 | 정본 문구 무변 | **사실상 동일한 데이터를 담는 저장소 2개**, 상한·API·UI 재구현 |

**추천: A.** 두 저장소가 담을 것이 실질적으로 같다(미채택 생성물). B는 방금 만든 것을 그대로 한 번 더 만든다. 개정은 **문구 2곳**이면 된다.

## D2 — accept 정리 규칙을 어떻게 축소할 것인가 (D1=A의 필수 후속)

현행: 저장된 accept → 해당 draft **전체** 삭제.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. **채택된 항목만** 삭제 | accept의 `request_id`와 일치하는 scratch 항목만 제거 | "채택한 것은 더 이상 미채택이 아니다"라는 원 의도를 보존하면서 **패드는 유지** | accept ↔ scratch의 `request_id` 대응을 구현 시 확인해야 함 |
| B. accept 시 정리하지 않음 | 상한·명시 삭제에만 의존 | 규칙 최소 | 채택한 것이 패드에 계속 남아 혼동 |
| C. 현행 유지 | 전체 삭제 | 변경 0 | **패드가 통째로 날아감 — 채택 불가** |

**추천: A.** 원 계약의 rationale("사용자가 정본을 확정했으므로 **그 미채택본은** 무의미")은 채택된 항목에 대해서만 참이다. 다른 생성 결과는 accept 후에도 여전히 복사 가치가 있다(패드의 존재 이유). **구현 시 accept가 generate의 `request_id`를 그대로 싣는지 확인**하고, 대응이 없으면 no-op으로 안전하게 처리한다.

## D3 — 백그라운드 실행 위치

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. in-process background task | FastAPI/asyncio 태스크 | 가장 단순, 신규 인프라 0 | **앱 재시작 시 진행 중인 3분짜리 생성이 증발**, 관측·재시도 없음 |
| B. **worker 서비스 확장 + outbox 이벤트 신설** | 기존 상시 worker가 생성 job을 claim해 실행 | **재시작에 살아남음**, atomic claim이 이중 실행 방지, worker가 이미 application 코드 공유 | outbox 이벤트 타입·job 저장 신설 |

**추천: B.** 몇 분짜리 작업이 앱 재시작으로 사라지면 비동기를 만든 이유가 사라진다. worker는 이미 compose 상시 서비스이고 중복 실행 방지도 이미 갖췄다.

## D4 — job 상태를 어디에 둘 것인가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. **job 레코드 분리** (`job`=실행 상태, `scratch`=결과) | 성공 시 job이 기존 `scratch.save` 경로로 결과를 남김 | 관심사 분리, **scratch의 append/delete 단순 계약 유지**, Analysis job 선례와 동형 | 컬렉션 1개 신설 |
| B. scratch 레코드에 status 부여 | 한 레코드가 pending→succeeded로 전이 | 저장소 1개 | scratch에 **update 의미 도입**(현재 append/delete뿐), 실패 job이 결과 없이 목록에 섞임 |

**추천: A.** scratch는 지금 append + delete만 하는 단순 저장소이고 그 단순함이 회귀로 잠겨 있다. 실행 상태는 성격이 다르며 Analysis에 이미 `pending/running/succeeded/failed` 선례가 있다. 패드는 **완료분(scratch) + 진행 중(job)** 을 합쳐 보여준다.

## D5 — 동기/비동기 분기 기준

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. **프리셋 기준 분기** — 1024는 동기, 2048/4096은 비동기 | 짧은 것은 지금처럼 기다림 | 짧은 생성(~23초)에 "제출→대기→확인" 3단계를 강요하지 않음 | **코드 경로 2개** 유지 비용 |
| B. 전부 비동기 | 단일 경로 | 일관성 | 23초짜리도 패드를 거쳐야 함 — 즉시성 상실 |
| C. 전부 동기 | 현행 | 변경 0 | 4096(~91초) 대기 문제 미해결 |

**추천: A.** 1024는 오너 실사용 기준 "짧은 수정"이고 23초는 기다릴 만하다. 다만 경로가 둘이 되는 비용을 인정하고, **UI에서 프리셋 선택이 곧 동기/비동기 선택임을 사용자에게 드러낸다**.

## D6 — 알림과 폴링

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. **배지/인앱 표시 + 폴링** | 탭에 완료 배지, 생성 중일 때만 폴링 | 권한 불요, 실패 조용함 없음 | 폴링 주기만큼 지연 |
| B. 브라우저 Notification API | OS 알림 | 창 밖에서도 인지 | **권한 거부 시 조용히 실패**, 권한 요청 UX 비용 |

**추천: A.** 푸시 인프라가 없고, 권한 거부 시 알림이 조용히 사라지는 것은 "완료를 놓친다"는 최악의 실패 모드다.

## D7 — scratch에 `version_id` 추가

패드가 "어느 version 기준으로 생성됐는지"를 표시하려면 필요하다(오너: *"여러번 호출한다고 하면 저장 버전이랑 연결해서 패드에 표시"*). 현재 scratch 레코드에 없다.

**추천: 추가.** 비정본 tier의 additive 필드이며, SoT v1.7.20의 scratch schema 문구도 함께 갱신한다. 기존 레코드는 `None`으로 읽히게 한다(선례: `intent` nullable).

---

## Owner decisions — 확정 (2026-07-20)

- **D1 = A** — `writing_drafts_scratch`를 패드 저장소로 재사용하고 **SoT v1.7.20을 개정**한다(용도 문구 + 정리 규칙).
- **D2 = A** — accept는 **채택된 항목만** 삭제한다(`request_id` 대응). 구현 시 accept가 generate의 `request_id`를 싣는지 확인하고, 대응이 없으면 no-op.
- **D3 = B** — **worker 서비스 확장 + outbox 이벤트 신설**. 앱 재시작에도 진행 중 생성이 살아남아야 한다.
- **D4 = A** — job 레코드를 분리한다(job=실행 상태, scratch=결과). 상태 모델은 Analysis 선례대로 `pending/running/succeeded/failed`, orphan/retry도 Analysis 계약을 재사용한다.
- **D5 = A** — 프리셋 기준 분기: **1024=동기, 2048/4096=비동기**.
- **D6 = A** — **배지/인앱 표시 + 폴링 5초**(생성 중일 때만). 오너는 "분 단위 대기라 10초도 괜찮다"고 했으나 **5초로 확정**했다. 브라우저 Notification API는 쓰지 않는다.
- **D7 = 추가** — scratch 레코드에 `version_id`를 신설하고 SoT schema 문구를 함께 갱신한다.

## 구현 시 필수 사항

- **SoT v1.7.20 개정 2곳**(구현과 함께): (1) scratch 용도를 "복구 전용"에서 **"복구 + 비동기 생성 결과 보관"**으로, (2) accept 정리 규칙을 "draft 전체"에서 **"채택된 항목만"**으로. 기존 회귀(`test_partial_analysis_failure_still_clears_scratch` 등)가 전체 삭제를 단정하므로 **함께 갱신**해야 한다.
- **상한 상호작용**: per-draft 상한(기본 20, `WRITING_SCRATCH_MAX_PER_DRAFT`)이 이제 **복구분 + 패드분을 함께** 담는다. 비동기 결과가 쌓여 복구분을 밀어낼 수 있으므로 dogfood에서 관찰하고, 필요하면 기본값을 올린다(계약은 이미 "기본값 + 운영자 조정 가능"이라 **재개정 불요**).
- **worker는 LLM을 호출하게 된다** — 현재 색인 drain 전용이므로 gateway 접근·타임아웃·실패 분류를 명시적으로 다룬다.

## Deferred / out of scope

- accept 경로 자체의 비동기화 — 패드는 복사 방식이므로 accept는 동기 그대로.
- 편집기 미저장 입력이 accept 후 `reloadLatest()`로 덮이는 문제 — **비동기와 무관하게 존재하는 별개 결손**이며, 패드 설계는 이 경로를 타지 않으므로 이 슬라이스 범위 밖이다. 별도로 다룬다.
- 패드에서 편집기로 **자동 삽입** — 오너 결정은 수동 복사다.
- 브라우저 Notification / 창 밖 알림.
- 여러 draft를 가로지르는 통합 패드 — 현재 키는 `(project_id, draft_id)`다.
