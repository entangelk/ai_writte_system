# Work Log — 2026-07-20

## Task — 미채택 Writing candidate 영속 결정 브리프 확정 (D0/D1/D2)

### Goals

- `plans/unaccepted-candidate-persistence-decisions.md` 브리프의 오너 결정(D0/D1/D2)을 확정·기록한다.
- 오너가 명시한 프레이밍 전환("게이트 우선 → 게이트 ↔ UI/UX 동반 정합")을 HANDOFF에 반영한다.
- 확정된 방향(D1=B 이력 + D2=A 별도 collection)으로 구현을 착수할 수 있게 상태를 정리한다.

### User Decisions and Rationale

- **D0 = B (최소 복구 pre-Phase-7) + 프레이밍 전환**: 오너는 이 결정을 단순한 안전망 추가가 아니라 개발 단계 전환의 신호로 규정했다. 지금까지의 "게이트(Writing Gate) 우선" 개발에서, **이제는 게이트와 UI/UX를 동반 정합**하는 단계로 넘어간다 — 따라서 **앞으로 SoT 변경 작업이 잦아지는 구간**이다. D0=C(Phase 7 P1 정식 착수)는 각하가 아니라 **이 슬라이스가 향해 가는 방향으로 명시적으로 염두에 둔다**("B로 하되 C도 염두"). 즉 B는 Phase 7과 무관한 일회성이 아니라 Phase 7 계층으로 승격될 것을 전제한 좁은 첫 걸음이다.
- **D1 = B (draft별 미채택 candidate 이력)**: 브리프 추천(A: 최신 1건)과 달리 오너는 B를 택했다. 근거는 "개발하면서 후속 정책(이력·보존)까지 함께 만드는" 이 구간의 성격이며, 이는 D0의 "C도 염두"와 정합한다(이력은 Phase 7 `conversation_turn`으로 자연 흡수). B가 요구하는 보존/만료 정책은 회피 대상이 아니라 이 슬라이스가 떠안는 작업이다.
- **D2 = A (별도 collection `writing_drafts_scratch`, 정본 무변)**: 오너가 저장 위치 A/B/C를 직접 지정하지는 않았으나, D1=B(이력)는 서버측 영속이 필수라 B(loop_audit 재사용, append-only immutable ↔ mutable 의미 충돌)·C(localStorage, 이력·기기간 이동 불가)와 양립하지 않는다 → **A만 정합적**이라 A로 확정했다. 이 추론을 오너에게 명시하고 진행했다.
- **보존/만료 정책 = 구현자 재량 잠정 결정 + SoT 승격 대기**: 오너는 D1=B가 요구하는 보존/만료 정책을 구현자(Claude)가 잠정적으로 정하고 테스트하도록 위임했다. **단, 잠정값이며 나중에 오너가 SoT로 승격·확정해야 한다** — 아직 정본 계약이 아님을 브리프·work_log·HANDOFF에 명시한다.

### Completed work

- **브리프 확정**: `docs/plans/unaccepted-candidate-persistence-decisions.md` 상태를 `결정 확정 (2026-07-20) — D0=B / D1=B / D2=A, 구현 착수`로 바꾸고 "Owner decisions" 섹션에 D0/D1/D2 확정 내용과 근거를 채웠다. 잠정 보존/만료 정책 절을 추가했다.
- **backend — 복구 저장소**: `writing/scratch.py`에 `ScratchCandidate` + repository protocol + in-memory 구현 + `WritingScratchService`(save/list_for_draft/clear_draft, per-draft 상한 trim)를 추가했다. `writing/scratch_mongo.py`는 `writing_drafts_scratch` collection에 `(project_id, draft_id, created_at desc)` 인덱스로 같은 계약을 구현한다. loop_audit 선례를 따르되 **append-only immutable이 아니라 mutable(삭제 있음)** 이라는 점이 다르다.
- **backend — 배선**: `main.py`에 `_default_writing_scratch_service()`(Mongo URI 있으면 durable, 없으면 in-memory)와 `create_app(writing_scratch_service=...)` 주입을 추가했다. `generate`는 성공 후 `current_position`이 있을 때만 scratch에 append하고, `accept`는 **`result.accepted`일 때만** 해당 draft의 scratch를 정리한다. 두 훅 모두 best-effort(예외 삼킴)라 안전망이 정본 경로를 막지 않는다.
- **backend — HTTP**: `GET/DELETE /projects/{project_id}/writing/scratch?draft_id=`를 추가했다(loop-audits 선례대로 plain dict, `response_model` 없음). 미존재 project는 404.
- **frontend**: `api/client.ts`에 손선언 타입 + `listWritingScratch`/`discardWritingScratch`를 추가하고, `writing/ScratchRecovery.tsx`(편집기 진입 시 미채택 이력 배너 — 항목별 "복사", "모두 버리기" 확인 후 삭제)를 만들어 DraftEditor의 이어쓰기 패널 위에 마운트했다. accept 성공 시 `scratchRefresh`를 bump해 배너가 사라진다.

### Issues found

- **DraftEditor 테스트 23건 실패(내 변경이 원인)**: `ScratchRecovery`가 마운트 시 fetch를 하나 더 발생시키는데, `DraftEditor.test.tsx`의 `mockFetch`는 **순서 기반 큐**라 추가 호출이 큐를 한 칸씩 밀어 index/count 단언이 모두 깨졌다(child effect가 parent보다 먼저 실행돼 scratch가 `calls[0]`이 됨). 해결: 테스트 23건을 고치는 대신 **stub 지점 5곳을 `stubFetch()` 하나로 감싸** scratch URL 요청은 빈 목록으로 응답하고 **기록된 mock 호출에서 제외**했다. 기존 index/count 단언이 "편집기 자신의 요청"만 기술하도록 유지된다. 이후 DraftEditor 35건 전부 통과. **같은 원인이 `App.test.tsx`의 라우팅 테스트 1건("renders a directly addressed draft editor", 요청 시퀀스 단언)에도 있어** 그 파일의 `mockFetch`에도 동일한 우회를 적용했다 — 첫 수정 뒤 전체 스위트를 다시 돌려서야 드러났으므로, 단일 파일 통과를 슬라이스 완료로 보지 않는다.
- **jszip 미설치(기존 문제, 내 변경 무관)**: 이 머신 `node_modules`에 `jszip`(v1.7.18에 추가됨)이 없어 `tsc`가 2건 실패했다. `npm ci`(208 packages, 취약점 0)로 해소했고 이후 `tsc` clean.

### Decisions

- **오너 결정은 위 "User Decisions and Rationale" 참조.** 아래는 그 결정 안에서 구현자가 정한 사항이다.
- **scratch 키 = `(project_id, draft_id)`, draft_id는 `current_position.draft_id`에서 취득**. generate 요청에 `current_position`이 없으면 저장하지 않는다(키가 없으면 복구 대상이 아니다).
- **accept 정리는 `result.accepted`일 때만**. 비-PASS Gate(revise 등)는 저장된 정본이 없으므로 사용자가 아직 복구할 초안이 남아 있다 — 이때 지우면 안전망이 오히려 초안을 죽인다. 양방향 회귀로 잠갔다.
- **`intent`/`next_unit`은 generate 시점에 알 수 없다**(accept 경계에서만 결정). 브리프 Follow-up의 "candidate 식별을 그대로 싣는다"는 취지는 유지하되, `intent`는 nullable 필드로만 두어 나중 Phase 7 `conversation_turn` 흡수 시 스키마 변경 없이 채울 수 있게 했다. 대화 필드(`content_channel` 등)는 넣지 않았다(추측 금지).
- **알려진 한계(비차단)**: accept의 502 partial 경로(version은 저장됐지만 analysis job 실패)는 정리 훅을 타지 않아 scratch가 남는다. 상한(20)이 있고 다음 성공 accept에서 정리되므로 무해하다고 판단해 예외 분기를 건드리지 않았다.

### Verification

- backend: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **1212 passed / 70 skipped / 297 subtests**(신규 `tests/test_writing_scratch.py` 11건 포함).
- frontend: `npx vitest run` → **159 passed / 11 files**(신규 `ScratchRecovery.test.tsx` 4건 포함), `npm run build` 101 modules(CSS 18.48 / JS 391.41 kB).
- 실경로 스모크: in-process app에 scratch 2건 seed → `GET .../writing/scratch`가 최신순 반환 → accept 200(accepted=true) → 재조회 `items: []`로 정리 확인.
- `npx tsc --noEmit` clean, `npm run gen:api`는 scratch path 2개만 additive 추가(88줄).
- LLM 미사용 슬라이스다.

## Task — 독립 검증 조건부 합격 → B-1 closure + hardening

### User Decisions and Rationale

- 오너가 독립 검증(`docs/verifications/2026-07-20/writing_scratch_recovery.md`)을 돌려 **조건부 합격(blocking 1건)** 판정을 주고, "보강 후 커밋"을 지시했다. 검증자는 self-claim 수치를 인용하지 않고 전부 재실행해 일치를 확인했다.

### Completed work

- **B-1(blocking) 닫음 — `tests/test_writing_scratch_mongo.py`(6건)**: `MongoWritingScratchRepository`가 표준 suite에서 전혀 검증되지 않던 empty cell. 선례(`test_writing_loop_audit_mongo.py`)의 `_Collection`/`_Cursor` fake 패턴을 복제하되 scratch는 **mutable**이라 `delete_many`(+`$in` 연산자) 지원을 fake에 추가했다. round-trip field-for-field, index name, newest-first sort, draft/project 격리, `delete_ids`, empty-ids no-op(over-strict), legacy `intent` 부재를 pin.
- **H-2 잠금(검증 권고 (a) 채택)**: cleanup을 `_clear_scratch_for_saved_accept()`로 추출해 **502 partial 경로에서도 호출**하도록 정합화했다. 브리프 "잠정 보존/만료 정책"에 세 분기(200 정리 / 502 partial 정리 / 비-PASS 미정리)를 명시했다.
- **H-1/H-4 선제 추가**: `_ExplodingScratch`로 scratch가 항상 raise해도 generate/accept가 200인지, generate 실패 시 scratch가 0건인지 pin.
- **H-3 근거 기록**: 브리프 Follow-up에 `next_unit` 제외 근거를 남겼다.

### Issues found

- **B-1은 내가 만든 실질 결손이었다**: `scratch_mongo.py` 주석과 work_log에 "loop_audit 선례를 따른다"고 써놓고 **정작 그 선례의 핵심(fake-collection 어댑터 테스트)은 복제하지 않았다**. 결과적으로 durable 모드에서만 터지는 field drift가 잠금 없이 남았다. 검증자 지적대로 `gate_findings`/`loop_audit`/`core_sot`/`analysis` 어댑터가 모두 갖는 관행에서 scratch만 이탈했다. **교훈: 선례를 인용할 때는 그 선례의 테스트까지 포함해 인용해야 한다.**
- **보강 테스트의 실효성은 mutation으로 실증했다**(green만으로는 검증이 아니라는 검증자 지적 반영): Mongo 6종 mutation(필드 오타·intent 누락·sort 반전·index명·empty-ids 가드·draft_id 무시) + 훅 4종 mutation(H-2 되돌림·generate/accept 격리 제거·accepted 가드 제거) 전부 의도한 테스트에서만 실패했다.

### Verification

- backend: **1222 passed / 70 skipped / 297 subtests**(+10 — Mongo 6, H-1/H-2/H-4 4).
- frontend: 159 passed / 11 files(이번 보강은 backend 한정이라 무변), tsc clean.

## Task — scratch per-draft 상한 환경변수화

### User Decisions and Rationale

- 오너가 하드코딩된 상한 20을 걸고 넘어졌다: **"실제로 어떻게 될지는 사람에 따라 달라서"** 환경변수로 조정 가능하게 하고 기본값 20으로 두자는 결정. 근거가 정확하다 — 이 값은 아직 SoT 승격 전 잠정값이고, 오너가 dogfood 중에 실제로 몇 건이 쓸모 있는지 관찰해봐야 승격 때 근거 있는 숫자를 올릴 수 있다. 코드 상수로 굳히면 그 관찰 자체가 코드 수정을 요구하게 된다.
- 이로써 **SoT 승격 시 확정할 대상이 바뀐다**: "상한 = 20"이 아니라 **"기본 20 + 운영자 조정 가능"**이라는 계약이 승격 대상이다.

### Completed work

- **`WRITING_SCRATCH_MAX_PER_DRAFT` 추가**: `_default_writing_scratch_service()`가 기존 `_env_int(name, default)` 헬퍼로 파싱(`WRITING_LOOP_MAX_*` 선례와 동형), 기본값은 `MAX_SCRATCH_PER_DRAFT = 20` 상수. in-memory/Mongo 두 경로 모두에 전달한다.
- **compose 노출**: `WRITING_SCRATCH_MAX_PER_DRAFT: "${WRITING_SCRATCH_MAX_PER_DRAFT:-20}"`.
- **1 미만 거부**: `WritingScratchService.__init__`에서 `max_per_draft < 1`이면 `ValueError`. 서비스 생성자에 둬서 env 경로뿐 아니라 모든 생성 경로가 보호된다.
- **회귀 5건 추가**(총 20건): env 미설정 시 기본 20, env override, **설정값이 실제 trim에 도달**, 0/-1 거부(subTest 2), 비수치 거부.

### Decisions

- **0을 "비활성화"로 해석하지 않고 거부했다.** 0을 허용하면 save 직후 스스로를 trim해 안전망이 지켜야 할 초안을 조용히 삭제한다 — 오타 하나가 조용한 데이터 손실이 되는 구조다. 오너가 요청한 것은 "조정 가능한 상한"이지 "끄는 스위치"가 아니므로, 비활성화 기능을 발명하지 않고(Simplicity First) 잘못된 구성은 기동 실패로 시끄럽게 알린다.
- 파싱은 기존 `_env_int`를 그대로 썼다(비수치 입력은 `int()`가 raise = 기동 실패). 자체 파서를 만들면 저장소의 다른 env 처리와 동작이 갈린다.

### Verification

- backend **1227 passed / 70 skipped / 299 subtests**(+5).
- mutation 4종 전부 bite: env 무시(하드코딩 복귀), 파싱했지만 서비스에 미전달, `<1` 검증 제거, 기본 상수 20→50.

### Next steps

- **오너가 잠정 보존/만료 정책(상한 20·accept 즉시 삭제·시간 만료 없음)을 SoT로 승격·확정**해야 한다. 그때까지 정본 계약이 아니다.
- 복구 UX 후속 후보: "복사"가 아니라 이어쓰기 패널 candidate로 직접 되살리기(WritingPanel 내부 상태 결합 필요), 502 partial 경로 정리, Phase 7 `conversation_turn` 흡수.
