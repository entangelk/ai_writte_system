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

## Task — 최종 재검증 합격 + 잔여 nit 3건 처리

### User Decisions and Rationale

- 오너가 재검증을 돌려 **합격(조건 없음)** 판정을 주고, 잔여 nit 보강 후 커밋을 지시했다. 검증자는 closure note를 신뢰하지 않고 mutation(`scratch_mongo` sort 반전)을 손수 재현해 bite를 독립 입증했다.

### Completed work

- **nit (1) HANDOFF markdown**: env 문장의 `**` 짝이 열린 채 끝나 "테스트 하네스 주의"까지 bold가 번지던 것을 닫았다. 파일 전체를 재검사해 line 12 balanced 확인.
- **nit (2) Mongo factory 분기 coverage**: `test_durable_branch_also_receives_the_cap` 추가(`from_uri` stub으로 Mongo 연결 없이).
- **nit (3) 검증 메시지**: `max_per_draft must be >= 1, got N (when configured from the environment, this is WRITING_SCRATCH_MAX_PER_DRAFT)`.

### Issues found

- **nit (2)는 "trivial hardening"보다 실질적이었다**: 캡을 in-memory 분기에만 남기고 Mongo 분기에서 빼는 mutation을 걸었더니 **오직 신규 테스트만** 실패했다. 즉 기존 20건으로는 **배포에서 실제로 쓰이는 durable 분기의 wiring 누락을 전혀 잡지 못했다**. 검증자 분류는 보수적이었고, 실측이 그것을 정정했다 — factory에 분기가 둘이면 양쪽 다 pin해야 한다.
- **line 63의 `**` 불균형은 오탐**: `` `***` `` scene marker를 세는 내 counter 문제이고 `835215d`의 기존 줄이라 손대지 않았다(CLAUDE.md §3 — 인접 코드 임의 수정 금지).

### Verification

- backend **1228 passed / 70 skipped / 299 subtests**(+1), scratch 양 파일 **27 passed / 2 subtests**.
- mutation: durable 분기 캡 누락 → 신규 테스트 1건만 실패(정확히 의도한 감지).

## Task — 보존/만료 정책 SoT 정본 승격 (v1.7.20)

### User Decisions and Rationale

- 오너가 **승격을 승인**했다("승격까지 문서 작업 마무리"). 이로써 D1=B가 요구하던 보존/만료 정책이 구현자 잠정값에서 **정본 계약**이 됐다.
- **승격 대상의 성격이 이전 결정으로 이미 바뀌어 있었다**: 오너가 상한을 환경변수화하라고 지시했을 때, 승격 대상은 "상한 = 20"이라는 숫자에서 **"기본 20 + 운영자 조정 가능"이라는 계약**으로 이동했다. 그 결과 dogfood에서 실사용 상한이 관찰되면 **기본값만** 조정하면 되고 계약을 다시 열 필요가 없다 — 승격이 미래의 조정을 막지 않는 구조가 됐다.

### Completed work

- **SoT v1.7.19 → v1.7.20**: 헤더 버전/갱신일, 계약 변경 이력 최상단 entry 추가.
- **Source of Truth 절에 정본 계약 추가**(가장 하중이 큰 위치 — 이 절이 "무엇이 정본인가"를 정의하므로): `writing_drafts_scratch`가 **Core SOT 외부·정본 아님·복구 전용 low-stakes tier**임을 먼저 못박고, 그 아래 키 규칙(`current_position` 없으면 미저장)·상한(기본 20 / `WRITING_SCRATCH_MAX_PER_DRAFT` / 1 미만 기동 실패)·정리 분기(저장된 accept만 = 정상 200 + analysis만 실패한 502 partial, **비-PASS는 미정리**)·시간 만료 없음·best-effort 격리·schema seam(`intent` nullable, `next_unit` 제외)을 계약화했다.
- **Phase 5 Writing AI 절**: "accept 전 candidate는 소실되지 않는다"를 추가하되, 기존 "사용자가 accept하기 전에는 draft version이나 canon이 바뀌지 않는다"와 **충돌하지 않음을 명시**했다(scratch는 정본이 아니라 복구 tier). 정본 계약끼리 모순으로 읽히지 않게 하는 것이 이 문장의 목적이다.
- **브리프**: 상태를 `완료 — ... SoT v1.7.20으로 정본 승격`으로 바꾸고, "잠정 보존/만료 정책" 절 제목을 승격 완료로 교체하며 **정본 위치는 SoT이고 충돌 시 SoT 우선**임을 명시했다(브리프가 정본 사본으로 오인되지 않게).
- **HANDOFF**: ★ 다음 작업을 "오너 선택 대기"로 교체(dogfood 착수가 최대 갈림길). Current Status의 잠정 표기를 승격 완료로 갱신. **stale했던 "정본 SoT ... v1.7.16" 표기를 v1.7.20으로 정정**(실제 SoT는 이미 v1.7.19였다 — 승격과 무관하게 틀린 상태였음).
- **CHANGELOG**: v1.7.20 entry.

### Issues found

- **HANDOFF의 SoT 버전 표기가 stale이었다**: "현재 v1.7.16"이라고 적혀 있었으나 실제 SoT는 v1.7.19였다(W4 export·export UI 슬라이스에서 SoT는 올랐는데 HANDOFF 첫 줄은 갱신되지 않았다). 승격 작업 중 발견해 정정했다. 이 줄은 "정본 우선순위"를 선언하는 자리라 stale하면 다음 작업자가 잘못된 계약 버전을 기준으로 삼게 된다.

### Decisions

- **계약을 Source of Truth 절에 넣었다**(Phase 5 절에만 두지 않고). scratch의 핵심 위험은 "복구 저장소가 정본으로 오해되는 것"이고, 그 오해를 막는 자리는 정본 정의 절이기 때문이다. Phase 5에는 포인터만 두고 충돌 없음을 명시했다.
- **버전은 patch(v1.7.20)**. 최근 슬라이스들(v1.7.17~19)이 실제 기능 계약 추가에도 patch를 쓴 관행을 따랐다.
- **코드 변경 0**: 승격은 문서 작업이다. 구현은 이미 정책대로 동작하고 회귀로 잠겨 있어, 승격이 코드에 요구하는 변경이 없음을 확인했다.

### Verification

- backend **1228 passed / 70 skipped / 299 subtests**(승격 전후 무변 — 코드 미변경 확인).
- 문서 검증: SoT 내부 앵커(`#source-of-truth`) 유효, 브리프↔SoT 상호 참조 일치, 승격된 계약 문구가 코드/테스트의 실제 동작과 일치하는지 대조(상한 기본 20·1 미만 거부·세 정리 분기·best-effort).

## Task — 문체/분량 제어 결정 브리프 작성

### User Decisions and Rationale

- 오너가 **AI에게 직접 주는 입력 축**을 넓히고 싶어했다: 문체/어투를 **few-shot 또는 one-shot 형식**으로 주는 수단, 그리고 생성 분량이 고정인지(소/중/대 구분이 있는지) 확인. 먼저 현황 분석을 요청했고, 이어서 브리프 작성을 지시했다.
- 오너 질문 "별도 Phase로 진행할 정도는 아니지?"에 대한 분석 결론: **프로젝트 단위면 Phase 7이 아니다**. 문체 지시는 `WritingBrief` 독스트링이 이미 "Not project memory — never a fact source"로 계약해 둔 축이라, 메모리 거버넌스인 Phase 7 P5와 다르다. **단 장면/인물 단위로 내려가면 Phase 7 §6(4)를 선점**하므로 그 경계를 D0로 세웠다.

### Issues found

- **내 직전 분석이 틀렸고 오너에게 정정했다**: "사용자가 어투를 지정할 방법이 전혀 없다"고 보고했으나 **거짓이었다**. `ProjectBriefVersion.tone`이 존재하고(`core_sot/models.py:40`), ProjectOverview UI에서 편집 가능하며(`ProjectOverview.tsx:18`), 프롬프트에 `<project_brief authority="canonical">- tone:`로 실제로 실린다(`prompt.py:80`). `WritingBrief` 하나만 grep하고 성급히 결론냈다. **교훈: "기능이 없다"는 주장은 한 심볼이 아니라 그 기능의 모든 후보 경로를 훑고 나서 해야 한다.**
- **계약 모순 발견 — 어투가 두 곳에 있다**: `ProjectBriefVersion.tone`(정본, version/API/UI/프롬프트 전부 배선)과 `WritingBrief.tone`(Phase 5, `style_rules`/`preferred_patterns`/`forbidden_patterns`까지 설계되고 `_format_brief`·서비스 시그니처까지 완성됐으나 **`main.py`가 `brief=`를 넘기지 않아 런타임 도달 불가**). 테스트가 서비스 레벨로 직접 주입해 살아 있는 것처럼 보인다(`tests/test_writing.py:212`). CLAUDE.md §1대로 조용히 한쪽을 고르지 않고 브리프 D1로 올렸다.
- **분량 관련 사실 확인**: 출력 길이는 `WRITING_GENERATE_MAX_TOKENS` 기본 1024 **서버 전역 고정**(요청 파라미터 아님 → UI 조절 불가, 소/중/대 없음). 요청 필드 `max_tokens`는 **출력이 아니라 입력 컨텍스트 예산**이라 이름이 충돌한다. 원고 분량 제한은 **전무**(`raw_text` 제약 없음, `maxLength` 없음, `UnitKind`는 분류일 뿐).

### Completed work

- `docs/plans/writing-style-and-length-control-decisions.md` 작성: 계약 모순 선surface, Phase 경계 분석(D0 근거), 현황 grounding(file:line), D0~D3 옵션 표 + 추천, Follow-up, Deferred.
- `plans/README.md` 인덱스 추가 + 이전 브리프(37번)를 완료 상태로 갱신.
- HANDOFF ★ 다음 작업을 이 브리프 확정으로 전환하고, 핵심 발견 2가지와 분량 현황을 요약.

### Decisions

- **D1 추천을 A(ProjectBrief 확장 + WritingBrief 삭제)로 잡은 근거**: W2가 이미 append-only version·optimistic base·idempotency·history·archived 경계를 문체에도 그대로 필요한 형태로 구현해 뒀다. B(WritingBrief 부활)는 그걸 재구현하면서 tone 중복도 남긴다. 죽은 경로를 살리는 것보다 **살아 있는 계약으로 모으는 편**이 모순을 자연 소멸시킨다.
- **분량 필드는 새 이름을 쓰도록 브리프에 명시**했다. 기존 `max_tokens`(입력 예산)의 의미를 바꾸면 5개 endpoint의 기존 계약이 흔들린다.

## Task — 문체 브리프 개정 (오너 3축 분석 반영)

### User Decisions and Rationale

- 오너가 결정적 분석을 제시했다: **전체 문서의 어투와 캐릭터의 어투는 분리되어야 하고**, Phase 7에 있는 톤 항목은 *쓴 글에 대한 분석* 쪽일 것이며, 따라서 **분석의 어투 관찰은 글 전체 분위기가 아니라 각 캐릭터에 대한 것**이어야 한다. 나아가 이를 **별도 Gate로 활용**해 "설정한 문장체 vs 작성된 문장체"의 일치를 검증할 수 있다고 제안했다.
- 검증 결과 **오너 가설이 맞았고, 더 나아가 Phase 7이 막혔던 지점을 푼다**: 아이디에이션 원문(`chat-revision-ideation.md:200`)이 분위기·톤을 directive에서 뺀 이유는 **"'아린'처럼 키를 못 박으므로"** — 즉 차단 사유가 **안정적 키의 부재**다. **캐릭터 어투는 캐릭터라는 키를 갖는다.** 따라서 캐릭터 축으로 좁히는 것은 Phase 7 판단을 뒤집는 게 아니라 **그 전제를 만족시키는 유일한 하위 사례**다. 분위기/mood는 여전히 키가 없어 Phase 7 몫으로 남긴다.
- 오너가 "한꺼번에 결정하겠다"고 하여 D0~D6을 한 브리프에 담았다.

### Completed work

- 브리프를 **3축 프레이밍**(작품 문체 / 캐릭터 어투 / 분위기)으로 재작성하고 D0~D6으로 확장했다: D0 범위, D1 작품 문체 위치(모순 해소), D2 few-shot 형태, D3 분량, **D4 캐릭터 어투 관찰의 모양(★핵심)**, **D5 Gate 정합 검증**, **D6 설정↔관찰 우선순위**.
- `plans/README.md` 인덱스를 3축·D4 전제 확인 필요까지 반영해 갱신.

### Issues found (브리프 작성 중 확인한 제약)

- **Gate 배관은 이미 있다**: Gate가 `format_context_package(package)`를 쓰므로 **`<project_brief>`(tone·pov 포함)를 이미 프롬프트에서 본다**(`gate_prompt.py:67`). 게다가 **"설정 vs 작성" 대조는 이미 작동하는 선례가 있다 — POV다**(`ProjectBrief.pov` ↔ `pov` finding). 따라서 검증 층의 실제 증분은 새 인프라가 아니라 **finding type 1개 + 템플릿 절**이다(현재 템플릿이 `Check only: do_not_use, POV, and continuity`로 닫혀 있음, `gate_prompt.py:21`).
- **taxonomy 동결이 D4를 좌우한다**: `character_observation` payload가 **exact-match `("name","observation")`**이고(`analysis/schema.py:34`) Phase 7 §2가 taxonomy 확장을 금지한다. 그래서 캐릭터 어투는 (A) 자유 텍스트 `observation`에 서술 — schema 무변이나 **Gate가 기계적으로 대조 불가**, (B) `aspect` payload 필드 추가 — taxonomy 3종은 유지하며 식별 가능, (C) 신규 type — **명시적 위반** 중 택일이다. **B의 합법성은 "동결"이 3종 유지를 뜻하는지 payload 불변까지 뜻하는지에 달려 있어, 오너 확인 없이는 진행 불가**임을 브리프에 명시했다.
- **새 finding type은 자동 revise 정책을 건드린다**: 자동 revise는 **continuity 전용**이라(`_eligible_revision_finding` → `_is_eligible_continuity_revise`, `revise_gate.py:541`) 새 type은 기본적으로 루프가 무시한다. 정하지 않으면 "finding은 뜨는데 루프가 무시하는" 어중간한 상태가 된다.

### Decisions

- **D5 추천을 A(warning 전용·자동 revise 제외)로 잡은 근거**: Gate quality baseline 21/21은 **경계가 명확한 케이스**에서 나온 수치다. 문체 일치는 본질적으로 흐릿해 오탐이 구조적으로 높고, 자동 revise에 넣으면 **Gate가 틀렸을 때 멀쩡한 산문을 고쳐 놓는다**. "실 오판 fixture가 생길 때만 Gate를 손댄다"는 기존 자세와 일관된다.
- **D6 추천을 A(Phase 7 D7 트리 재사용)로 잡은 근거**: `저자 directive > canonical 관찰 > candidate 관찰`은 이미 잠긴 원칙이고 문체에도 타당하다. 다만 D7 원문이 서사 사실을 상정하므로 **"문체에도 적용"을 이 브리프가 명시**해야 잠긴다.
- **분위기/mood는 Deferred로 명확히 분리**했다. 키가 없다는 성격 차이가 Phase 7이 별도 설계를 남긴 이유이므로, 여기서 끌어오면 그 설계를 선점한다.

### Verification

- 브리프의 신규 `file:line` 인용 8건과 링크 대상 3건을 전수 재확인(전부 OK). 코드 변경 0.

## Task — 문체 브리프 오너 결정 확정 (D0~D6)

### User Decisions and Rationale

- **D0=B / D1=A / D2=A / D3=A / D4=B / D5=A / D6=A** 확정. 근거는 브리프 "Owner decisions" 절에 기입했다. 특기할 오너 근거:
  - **D2=A only**: 원고 span 참조(B)를 후속 후보로도 두지 않는다. "특정 구간이 필요하면 그 구간을 직접 자유 텍스트로 붙여넣는 편이 낫다."
  - **D4=B + "taxonomy 동결 = 3종 유지"**: 오너가 동결의 의미를 확정해 주어 payload 필드 추가가 합법이 됐고, 이로써 D5의 기계적 대조가 실효를 갖게 됐다(자유 텍스트였다면 D5가 사실상 무력).
  - **D5=A**: "어투는 저자가 알아차리면 충분하고, **일부러 다르게 쓰는 경우도 정당**하니 차단하거나 재생성 루프를 태우면 안 된다."
  - **D6**: 설정 우선이되 **경고만**, **최종 결정은 사용자 선택**. 관찰→설정 자동 반영 기능은 만들지 않는다("필요하면 직접 수정하겠지").
- **D3 숫자는 내가 제기한 충돌 때문에 오너가 하향 조정했다**: 최초 제안 8192는 실측 ~45 tok/s에서 ~182초가 걸려 `LLM_GATEWAY_TIMEOUT_SECONDS=120`을 초과 → **기능 자체가 실패**. 오너가 실사용 체감(1024=짧은 수정)을 기준으로 **1024/2048/4096**으로 재설정했다.

### Issues found

- **D3 최초 숫자가 배포된 운영 한계와 충돌했다**(확정 전 발견): B2b 실측(`docs/benchmarks/2026-07-15/`)의 stage별 completion/wall-clock에서 생성 속도가 **약 45 tok/s**로 도출된다(report 259tok/5.47s, gate 140tok/3.37s). 이 속도에서 8192tok≈182초 > gateway timeout 120초. 또 `WRITING_LOOP_MAX_TOTAL_TOKENS=10000`은 **루프 전체 실측 ceiling 4991tok**에 ~2배 여유를 준 값이라, 8192짜리 단일 생성은 **기존 루프 전체보다 큰** 요청이 된다. 이 값들은 오너가 B4로 승인한 숫자라 조용히 바꾸면 결정을 뒤집는 것이므로 확정 전에 올렸다.
- **잔여 제약(하향 후에도 유효)**: **4096(~91초)은 `WRITING_LOOP_MAX_WALL_CLOCK_MS=60000`을 초과**해 자동 revise 루프를 탈 수 없다. 결함이 아니라 의도된 경계로 브리프·HANDOFF에 명시했다.
- **오너의 D6 우려는 이미 해결돼 있었다**: "설정 변경도 히스토리가 필요할지도" → **ProjectBrief는 이미 append-only version + history API**(`GET /projects/{id}/brief/versions`, UI 노출)라 직접 수정하면 이력이 자동 보존된다. 신규 작업 불요임을 확인해 드렸다.
- **오너가 기억한 "아이디에이션 단계"는 미구현**이다(Phase 7 P3 `ideate`, 계획만). 따라서 D2=A(자유 텍스트)가 현재 동작하는 유일한 경로다.

### Decisions

- **비동기 생성은 이 슬라이스에 흡수하지 않고 별도 브리프 후보로 분리했다.** 오너 제안(백그라운드 실행 + 완료 알림 + 대기 중 집필)의 방향은 타당하나: (1) 분할 화면 오른쪽 rail은 **W1으로 이미 구현**돼 결과가 이미 rail에 뜨므로 새로운 부분은 백그라운드·알림·대기 중 집필뿐이고, (2) **"대기 중 집필"이 정본 계약과 정면 충돌**한다 — Writing은 깨끗한 최신 version에서만 가능하고(D1=A) accept는 `base_version_id` stale 시 409이므로, 대기 중 저장하면 완료된 후보를 **채택할 수 없게 된다**. stale base 처리는 정본 계약 결정이라 문체 브리프에 끼워 넣으면 브리프가 두 주제로 쪼개진다. (3) Writing job 모델·백그라운드 실행 경로도 신규다(현 worker는 색인 outbox drain 전용, LLM fire-and-forget 선례 없음).
- 브리프 헤더 주석을 "결정 대기"에서 "**결정 완료 + 충돌 시 Owner decisions 절 우선**"으로 바꿔, 각 D절의 옵션/추천이 정본으로 오인되지 않게 했다.

## Task — 비동기 생성 + 결과 패드 브리프 작성·확정 (D1~D7)

### User Decisions and Rationale

- 오너가 비동기 설계를 **패드(읽기 전용 표시 + 수동 복사)** 방식으로 명확히 했다. 확정: D1=A(scratch 재사용+SoT 개정) · D2=A(accept는 채택된 항목만 삭제) · D3=B(worker 확장) · D4=A(job 레코드 분리) · D5=A(1024 동기 / 2048·4096 비동기) · D6=A(배지·인앱 + **폴링 5초**) · D7(scratch에 `version_id` 신설).
- **폴링 주기**: 오너는 "분 단위 대기라 10초도 괜찮다"고 했으나 **5초로 확정**했다.

### Issues found

- **내가 문제를 과대평가했고 오너가 정정했다**: 나는 "대기 중 집필"이 정본 계약(stale base 409, `reloadLatest`의 미저장 입력 덮어쓰기)과 충돌한다고 두 턴에 걸쳐 주장했으나, **오너는 이미 첫 제안에서 "복사 붙여넣기가 가능한 형태로"라고 명시**했었다. 패드 설계는 **accept를 타지 않으므로** 두 문제가 **발생 자체를 하지 않는다** — `POST /writing/generate`는 정본을 전혀 쓰지 않고(유일한 쓰기가 비정본 scratch), 저장은 작성창에서만 일어난다. 내가 "정본 계약 변경이 맞습니다"라고 동의한 것도 **틀렸다**. **교훈: 사용자가 이미 제시한 설계 요소를 읽고 그 전제 위에서 답해야 한다. 내 가정(accept 경로)을 상대 설계에 덮어씌우면 없는 문제를 만들어낸다.**
- **다만 검증 중 실제 충돌을 하나 찾았고, 그건 유효하다**: 패드를 scratch에 얹으면 **2커밋 전 승격한 SoT v1.7.20과 충돌**한다 — (1) scratch를 "복구 전용 low-stakes tier"로 규정한 문구, (2) **"저장된 accept가 draft scratch 전체를 정리"** 규칙. 후자는 동기 경로에서 **한 번만 채택해도 패드를 통째로 삭제**한다. 두 조항 모두 구현과 함께 개정 대상으로 브리프·HANDOFF에 명시했다.

### Completed work

- `docs/plans/async-generation-pad-decisions.md` 작성 + D1~D7 확정 기입. "왜 정본 계약 변경이 거의 필요 없는가"를 근거(정본 write 0 · accept 미경유)와 함께 앞에 두고, 개정이 필요한 **scratch 조항 2곳만** 별도로 선surface했다.
- `plans/README.md` 39번 인덱스, HANDOFF 다음 슬라이스 후보 갱신(개정 요구·상한 상호작용·worker의 LLM 호출 주의 포함).

### Decisions (구현자 판단, 오너 추천 승인분)

- **D2 정리 규칙 축소 방식**: 원 계약 rationale("정본을 확정했으므로 **그 미채택본은** 무의미")은 **채택된 항목에 대해서만 참**이다. 다른 생성 결과는 accept 후에도 복사 가치가 있으므로 `request_id` 대응 항목만 삭제한다. 구현 시 accept가 generate의 `request_id`를 싣는지 확인하고 대응이 없으면 no-op.
- **D4 job 분리**: scratch는 현재 append+delete만 하는 단순 저장소이고 그 단순함이 회귀로 잠겨 있다. 실행 상태를 얹으면 update 의미가 생기므로, job(실행)과 scratch(결과)를 분리하고 패드는 **완료분+진행중**을 합쳐 보여준다.

### Verification

- 브리프 주장 6건(scratch에 version_id 부재 · worker 상시 서비스 · Analysis 4상태 선례 · `delete_for_draft` 전체 삭제 · 전체삭제 단정 회귀 존재 · SSE/WebSocket 미사용)과 링크 4건 전수 확인. 코드 변경 0.

## Task — 비동기 브리프 독립 검증 합격 + hardening 4건 반영

### User Decisions and Rationale

- 오너가 독립 검증(`docs/verifications/2026-07-20/async_generation_pad_brief.md`)을 돌려 **합격** 판정을 주고, 보강/스킵 판단 후 커밋을 지시했다. 검증자는 브리프의 하중 큰 주장 3건(정본 write 0 · accept가 패드 전체 삭제 · 내 자기 정정의 타당성)과 사실 6건·링크 4건을 1차 사료에서 재도출했다.
- non-blocking 4건이었으나 **전부 반영**했다. 셋은 브리프 정밀도를 실제로 높였고, 하나(H3)는 **내 서술의 모호함이라 방치하면 구현이 잘못 갈 수 있었다**.

### Completed work / Issues found

- **H3(가장 실질적) — 내 브리프의 모호함이었다**: D3에 "outbox 이벤트 신설", D4에 "job 레코드(Analysis 선례)"라고 써서 **서로 다른 메커니즘을 가리켰다**. 직접 확인하니 `IndexSyncEvent`는 전부 `*_ARCHIVED`/`*_UPSERTED`인 **데이터 변경 CDC**(멱등·단발 drain)이고, 생성 job은 **사용자 요청 기반 장시간·비멱등**이라 성격이 다르다. 글자 그대로 읽으면 "생성-via-색인-outbox"라는 어색한 결합으로 가고 `03-index-sync-outbox-decisions.md` 계약까지 흔들렸을 것이다. D3 옵션·확정문을 **"독립 job 테이블 claim"**으로 고치고 **"색인 outbox는 건드리지 않는다"**를 브리프·HANDOFF에 명시했다("outbox 이벤트 신설" 표현 0건 확인).
- **H1 — 과잉 헤지 제거**: "구현 시 accept가 `request_id`를 싣는지 확인"이라 썼으나 **이미 확정적으로 존재**한다(`main.py:1298` 필수 필드, `accept.py:227` candidate 일치 검증 — 둘 다 재확인). 헤지를 **검증된 사실 + 인용**으로 교체했다. 안전 방향이라 남겨도 됐지만, **확인 가능한 것을 "나중에 확인"으로 미루면 구현자가 같은 조사를 반복**하므로 지금 닫는 편이 낫다.
- **H2 — 승격 당시 정밀도 결함 인지**: v1.7.20의 "정리한다"가 **whole-vs-per-item에 침묵**하고 whole-draft 의미는 rationale·구현에만 있었다. 개정 시 **"채택된 항목(`request_id` 일치)만"을 문구로 못박을 것**을 "구현 시 필수 사항"에 추가했다.
- **H4 — 순서 표현 정정**: 내가 채팅에서 "의존 관계상 문체 먼저"라고 했으나, 의존 대상은 **결정이 아니라 구현**이고 **hard block이 아닌 soft ordering**이다(비동기 인프라는 프리셋 없이 병행 scaffold 가능). HANDOFF에 정확한 형태로 남겼다.
- 검증 기록에는 **closure note만 덧붙이고 원 본문은 수정하지 않았다**(판정 불변, 감사 이력 보존).

### Verification

- H1/H3 인용 재확인(`main.py:1298`·`accept.py:227`·`IndexSyncEvent` 값 집합), 4건 반영 여부 기계 확인. **코드 변경 0**(문서만).

### Next steps

- **오너가 잠정 보존/만료 정책(상한 20·accept 즉시 삭제·시간 만료 없음)을 SoT로 승격·확정**해야 한다. 그때까지 정본 계약이 아니다.
- 복구 UX 후속 후보: "복사"가 아니라 이어쓰기 패널 candidate로 직접 되살리기(WritingPanel 내부 상태 결합 필요), 502 partial 경로 정리, Phase 7 `conversation_turn` 흡수.
