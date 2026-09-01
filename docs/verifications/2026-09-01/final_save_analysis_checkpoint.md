# 최종 저장·분석 연동(D4=A) 체크포인트 독립 검증

## Subject metadata

- 날짜: 2026-09-01
- 요청자: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래" — D4=A 기준 구현 체크포인트 검증)
- 검증자: Claude Code 세션(구현자와 다른 세션 — 구현은 커밋 `832089b`·`0922a24`)
- 대상: final-save D4=A 체크포인트 — `POST …/drafts/{draft_id}/finalize`(marker·snapshot 확정 → 서버 동기 분석 실행·실패 시 저장 보존), `DraftPayload` final/분석 상태 4필드, 프런트 최종 저장·분석 버튼·상태 배지(`DraftEditor.tsx`), 활동·과금 분류표, OpenAPI/`schema.d.ts`. 회귀 셀·SoT 문서 갱신은 작업자가 "남은 것"으로 명시
- 정본: [`docs/plans/final-save-analysis-decisions.md`](../../plans/final-save-analysis-decisions.md)(Resolved 2026-09-01, D1=B·D2=B·D3=B·**D4=A**) — §확정 계약 + §D4 Follow-up considerations. 상위 연결 `docs/system-contract-sot.md` v1.8.13(이 슬라이스가 아직 못 박은 조항 없음 — 작업자 명시 잔여)
- 검증 소스: 커밋 `832089b`(본체)·`0922a24`(fix), HEAD `0922a24`, 트리 clean(변이 전·후 매번 `git status --short` 확인 — 미커밋 파일은 검증자 repro 스크립트뿐)
- 환경: WSL2 베타, 저장소 루트 호스트 `python3 -m pytest`, test-mongo 컨테이너 up(`ai_writte_system-test-mongo-1`, 127.0.0.1:27020 healthy 실측). frontend `npx tsc --noEmit`·`npx vitest run`. `.env` 무관

## Scope

1. ★확정 계약 문언에서 경계 행렬을 먼저 세운 뒤 구현 대응(계약→코드 방향)
2. 작업자 주장 검증의 독립 재실행(Python 컴파일·활동/과금 분류 가드 18/193·프런트 tsc)
3. 작업자가 **돌리지 않은** 표면 — 과금 시행 suite(`test_quota_enforcement_api.py`)·프런트 vitest·백엔드 전수
4. 실행 경로 실측: 인메모리 TestClient 프로브(`repro_final_save_flow.py`) — 커밋 상태 그대로 → 런타임 패치 2단(dedupe 행 주입 → 서비스 메서드 패치)
5. 변이 3종(분류표 행 제거 2·경로 리터럴 변경 1)
6. 생성물 동기화: `openapi.json`·`schema.d.ts` 재생성 byte 대조

## Methodology

- 프로브 `docs/verifications/2026-09-01/repro_final_save_flow.py`(커밋됨): 인증 의존성 2개만 override하고 **`enforce_quota`는 실경로로** 돌린다 — `tests/auth_support.authenticate`를 쓰면 `enforce_quota`까지 덮여 dedupe 결함이 가려진다. `raise_server_exceptions=False`로 서버 예외를 상태코드로 관측.
- 변이 프로토콜: 사전 `git status --short` 확인 → 문자 그대로 diff 적용 → 집중 셀 실행(**요약 count 줄**로 판독, `grep FAILED` 아님) → `git checkout -- <path>` 복원 → `git status --short` 재확인. 3회 전부 clean 복원 확인.
- 전수·프런트 수치는 이 세션 실측값(환경은 Subject metadata 참조).

## Findings

### 1. 작업자 주장 재현 — 전부 정확

| 주장 | 재실측 |
|---|---|
| Python 컴파일 | 변경 9파일 `py_compile` 전부 OK |
| 활동/과금 분류 가드 18 passed / 193 subtests | `pytest tests/test_activity_actions.py tests/test_billable_actions.py -q` → **18 passed, 193 subtests** 동일 |
| 프런트 TypeScript 검사 | `npx tsc --noEmit` rc=0 |
| (부가) `openapi.json`·`schema.d.ts` 동기 | `dump_openapi.py` 재생성 및 `openapi-typescript` 재생성 모두 커밋본과 **byte-identical** — 손편집 없음 |

### 2. ★하지만 요청 하나를 안 보냈다 — 기능 전체가 동작하지 않는다

작업자 검증은 컴파일·분류 표·타입 검사까지이고 **엔드포인트로 요청 1건을 보낸 적이 없다.** 프로브(S0)가 커밋 상태 그대로의 첫 요청에서:

```
POST /projects/p1/drafts/d1/finalize → 503
{"detail": "no dedupe key mapping for billable action 'draft_finalize'"}
```

- **B1(차단) — 과금 dedupe 표 무매핑.** `quota/dedupe.py::DEDUPE_SOURCES`에 `draft_finalize` 행이 없다. `enforce_quota`는 매핑 조회 실패를 **503 fail-closed**(`dependencies.py:233-238`)로 닫는다 — 유료 route가 중복 방지 없이 도는 것을 막는 설계 그대로. `app.state.quota`는 기본 시행 서비스로 **항상** 조립되므로(`main.py:1908`) 특별한 배치가 아니어도 전 요청이 막힌다. 이 슬라이스가 돌리지 않은 `DedupeMappingTest`(`test_quota_enforcement_api.py`)가 **HEAD에서 이미 FAILED** — 가드가 지금도 비명을 지르고 있다.
- **B2(차단) — 성공 경로 부재(500).** dedupe 행을 런타임 주입하고 같은 요청을 보내면 이번엔 500: `core_sot/service.py:1175`가 `draft = self._require_active_project_and_draft(...)`의 반환값을 쓰는데 이 메서드는 **`-> None` 검사 메서드**다(다른 호출처 1119·1228·1454는 전부 문장형 호출). `draft.finalized_snapshot_id` 접근에서 `AttributeError`. 즉 finalize의 성공 경로는 존재한 적이 없다. py_compile이 None 속성 접근을 잡지 못하는 것은 알려진 한계.

### 3. 유료 경로 선언 — 402/429 얼굴 미선언

- **B3(차단).** finalize route의 `responses`가 무료 경로용 `_ERRORS_400_404_409`를 쓴다(`routers/drafts.py:666`). 유료 경로는 `_billable(...)`로 402(한도 소진)·429(중복 잠금)를 선언해야 하고(`errors.py:334-343`의 분리 상수, 주석이 명시), `BillableRouteWiringTest::test_every_billable_operation_declares_402_and_429`가 정확히 finalize 셀에서 SUBFAILED. `schema.d.ts`·`openapi.json`도 이 선언에서 생성되므로 프런트 계약에 quota 얼굴이 없다.

### 4. 런타임 패치 아래의 계약 행렬(B1·B2를 우회한 관측)

B1·B2는 이 슬라이스의 결함이지만, 그 아래 계약 이행이 맞는지는 패치로 가려냈다(프로브 S0c~S13). **13/14 합격 — 이 아래에는 추가 차단은 없다.**

| 계약 조항(확정 계약) | 실측 | 결과 |
|---|---|---|
| marker·snapshot 확정 뒤 job 생성·runner 동기 실행 | S1: 200, `finalized_snapshot_id`·`finalized_at` 기록, `analysis_status="succeeded"`, runner 1회 | ✓ |
| 같은 final 요청 재시도 → 동일 결과 수렴·중복 없음 | S2: 동일 version/snapshot 반환, `idempotent_replay=true`, runner 재실행 없음 | ✓ |
| marker 덮기·재최종화 금지 | S3: 다른 키 → 409 `AlreadyFinalized` | ✓ |
| final 뒤 일반 저장 허용·분석 자동 생성 없음·marker 보존 | S4: 200, 새 snapshot에 job 없음(`analysis_status=null`), marker 유지 | ✓ |
| 분석 최신성 = snapshot 동일성(시간 아님) | S4→S5: 새 snapshot 수동 분석으로 `succeeded` 전환, 과거 성공은 최신엔 무효 | ✓ |
| runner 실패 → 저장 보존·`분석 필요` | S6: 200, marker·version 보존, 영속 job `failed`, `analysis_error` 통지 | ✓ |
| runner 미구성(0922a24 fix) → 저장 보존·안내 | S7: 200, job `pending`, `analysis_error="analysis runner is not configured"` | ✓ |
| source-ref 서버 준비·실패 시 marker 유지 | S8: final snapshot 모든 block span 커버 | ✓ |
| 4000자 상한 일반 저장과 같은 순서 | S9: 422(일반 저장과 동일 face) | ✓ |
| 보관 → 409 | S10 | ✓ |
| 활동 행(저장 성공 뒤) | S11: `draft_finalized` 1행 | ✓ |
| 실패 뒤 재실행 = 기존 수동 경로 | S12: `retry` route가 failed→pending 리셋 | ✓ |
| 없는 draft → 404 | S13 | ✓ |
| 부분 실패의 현재 얼굴 | **S6 응답의 `analysis_job.status`가 `"pending"`** — 영속 상태는 `"failed"`(GET으로 확인). route가 runner 재발생 예외를 받고도 낡은 job 객체를 응답에 싣는다(`routers/drafts.py` job 지역변수). 프런트는 non-`succeeded`를 실패로 읽어 안내는 맞음 | **H1** |

- **상태 표시(D3=B, 편집기)**: `DraftEditor.tsx` 상태 바 `초안/최종 저장됨/최종 저장 후 수정됨` + `분석 필요/진행 중/완료`(색 보조·텍스트 정본) + 비활성 final 버튼의 불가 사유 title — 코드 대조 합격. "작업실 입장"이 앱 전체 진입이므로 작업실 상기 = 편집기 `workspace-status` 배지로 충족.

### 5. 변이(분류 가드가 실제로 물리는지)

| 변이 | diff | 재실패 |
|---|---|---|
| M1 유료 행 제거 | `billable_actions.py`에서 `draft_finalize` BillableAction 2행 삭제 | `test_billable_actions.py` **4 failed**/109 subtests(요약 줄 기준) |
| M2 활동 행 제거 | `activity/actions.py`에서 `draft_finalized` ActivityAction 3행 삭제 | `test_activity_actions.py` **2 failed**/81 subtests |
| M4 경로 리터럴 | `…/finalize")` → `…/finalizeX")` | wiring 1 + `test_billable_actions.py` 4 failed |

전부 복원 확인(`git status --short` clean). 분류 표면의 가드는 진짜로 물린다 — 문제는 그 아래 실행 경로에 셀이 전혀 없다는 것(**B4**, 작업자 인지). B1·B2는 finalize를 한 번만 두드리는 셀 하나로 즉시 잡혔을 결함이다.

### 6. 백엔드 전수 — 작업자가 돌리지 않은 가드들이 이미 잡고 있었다

`python3 -m pytest -q`(test-mongo up) — **11 failed / 2659 passed / 1 skipped / 3031 subtests**(39:26). 직전 기준선(2026-09-01 세션 1, `2663/9` — 9 failed 전부 검증자 미등록 기록을 잡은 `test_docs_indexes`)과 달리 이번 11 failed는 **전부 이 슬라이스 유래**다:

| 실패 셀 | 귀속 |
|---|---|
| `test_quota_enforcement_api.py::DedupeMappingTest` | **B1** |
| `BillableRouteWiringTest::test_every_billable_operation_declares_402_and_429`(SUBFAILED, finalize 셀) | **B3** |
| `test_typecheck.py::RepositoryTypecheckTest` — mypy `service.py:1175: "_require_active_project_and_draft" … does not return a value [func-returns-value]` | **B2의 정적 증거** — 저장소의 mypy 가드가 커밋 시점에 이미 B2를 지목했다 |
| `test_chapter_hierarchy.py` 5셀 — `TypeError: register_drafts() missing 3 required keyword-only arguments: 'analysis', 'runner', and 'llm_call_audit'` | **B6** |
| `test_activity_ui_labels.py::ActivityUiLabelTableTest` — 라벨표(26행) vs 백엔드 분류표(27) 어긋남 | **B7** |
| `test_application_api.py::SpineEnvelopeKeyTest::test_draft_payload_keys` | **B8** |
| `test_auth_api.py::CombinedBoundaryMatrixTest::test_every_operation_lands_in_exactly_one_named_tier` | **B9** |

- **B6(차단).** `register_drafts` 시그니처에 `analysis`·`runner`·`llm_call_audit`를 추가하면서 `tests/test_chapter_hierarchy.py`의 직접 조립 지점 5곳을 갱신하지 않았다 — 5셀이 `TypeError`로 붕괴.
- **B7(차단).** 백엔드 활동 분류에 `draft_finalized`를 더했지만 프런트 라벨표(`frontend/src/projects/activityActions.ts:20` `ACTIVITY_ACTION_LABELS`)에 한국어 라벨을 추가하지 않았다. 양방향 전수 가드가 잡았고 방치 시 활동 화면이 `draft_finalized` 원문 리터럴로 폴백한다.
- **B8(차단).** `DraftPayload`에 4필드를 추가했지만 공개 봉투 키 핀(`SpineEnvelopeKeyTest`)을 갱신하지 않았다.
- **B9(차단).** 확정 계약이 "새 mutating route면 … **tier 행렬**·소유자/grant 경계를 함께 갱신한다"고 못 박았는데 finalize가 어느 tier에도 배치돼 있지 않다.

### 7. 프런트 — 기존 회귀 셀 3개를 깨뜨린 채 커밋

- **B5(차단).** 작업자는 tsc만 확인했고 **vitest는 red다**: 3 failed / 382 passed.
  - `DraftEditor.test.tsx` 상태 바 셀("분석 미실행" pin) — 문구를 `분석 필요/진행 중/완료`로 바꾸면서 pin을 깨뜨렸다. 상태 계약을 바꾸면 pin을 같이 갱신해야 한다. 깨진 셀은 정확히 §H6 회귀를 지키던 셀이다.
  - `designTokens.test.ts` 2셀 — 새 CSS `.status-attention { color: var(--status-danger, #a43b2c) }`가 **정의되지 않은 토큰을 소비**하고 **raw 색 리터럴을 규칙부에 박았다**("모든 색은 토큰 뒤에" 가드). 기존 위험 팔레트(`--danger-600: #b63132`)가 이미 있는데 그것을 쓰지 않고 미정의 `--status-danger`+폴백 `#a43b2c`(팔레트와도 불일치)를 만들었다. `git show 832089b~1:frontend/src/styles.css | grep -c "status-danger\|a43b2c"` = 0 — 이 슬라이스 유래 확정.

### 8. 관찰(차단 아님)

- quota 중복 잠금은 `(user, action, project)` 키다(`enforcement.py::admit`→`_claim`). 창 안 같은 프로젝트 **다른 장면**의 final도 429로 막히고, 프런트 `finalizeDraft`는 `X-Confirm-Duplicate`를 보내지 않는다 — 재시도·연달아 최종화 시 일반 오류로 보인다. 8.3 Q6=G4 설계를 공유하는 것이라 슬라이스 결함은 아니나 UI 안내 검토 가치.
- marker 보존: `rename_draft`·`archive_draft`는 `replace(draft, …)`라 final 필드 유지 확인. `start_next_unit`의 `Draft(…)`는 신규 객체라 무관.

## Issues / Risks

### Blocking (계약 의무)

1. **B1** `DEDUPE_SOURCES`에 `draft_finalize` 무매핑 — 전 finalize 요청 503 fail-closed. 표가 정본인 슬라이스(8.3 Q9)의 위성 표를 놓쳤고, 이미 실패 중인 가드를 확인하지 않았다.
2. **B2** `_require_active_project_and_draft`(→ None) 반환값 사용 — 성공 경로 전무(500). 요청 1건을 안 보낸 검증 체크리스트가 이를 통과시켰다.
3. **B3** 유료 경로 선언에 402/429 부재(무료용 선언 상수 사용) — 클라이언트 계약(schema.d.ts 포함)에 quota 얼굴 누락. 가드 SUBFAILED.
4. **B4** final API 계약 분기 전량 무셀(작업자 명시 잔여 — 본 기록의 경계 행렬 14행이 잠금 목록).
5. **B5** 프런트 vitest red 3셀로 커밋 — 상태 바 pin 파열 + 디자인 토큰 가드 2(§7).
6. **B6** `register_drafts` 시그니처 변경에 테스트 조립 지점 5곳 미갱신(`test_chapter_hierarchy.py` TypeError 5셀).
7. **B7** 활동 라벨표에 `draft_finalized` 미추가(백엔드 분류 27 vs 라벨 26 — 화면 리터럴 폴백).
8. **B8** `DraftPayload` 공개 봉투 4필드 추가에 키 핀(`SpineEnvelopeKeyTest`) 미갱신.
9. **B9** 새 operation의 tier 행렬 미배치 — 확정 계약의 갱신 의무 위반.

### Hardening (비차단)

- **H1** runner 실패 시 응답 `analysis_job.status`가 영속 상태와 어긋남("pending" vs "failed") — except에서 job을 다시 읽어 응답하면 폐쇄.
- **H2** 분석 실패의 HTTP 얼굴: 구현은 200+`analysis_error`. D2=B 권고문·D4=A 표의 "partial"은 accept의 **502 partial 선례**(`writing.py:1268-1281`, `JSONResponse(502)`)를 인용한다. 확정 계약 본문은 상태코드를 못 박지 않아 계약 내 긴장 — 오너가 어느 쪽이 정본인지 못 박아야 한다(200 유지 시 브리프 문안 정정, 502 채택 시 봉투·프런트 에러 경로 수정).
- **H3** `_draft_payload`가 draft마다 `list_draft_versions`+job 조회를 추가(N+1) — 목록 엔드포인트에서 Mongo 왕복 증가. 로컬 1인 단계에서 감수 가능하나 기록으로 남긴다.
- **H4** 구현 세션의 work_log 기록 부재(§5 위반 — 잔여 작업과 함께 정리 필요). SoT v1.8.13·tier/operation 수·CHANGELOG 미갱신은 작업자 명시 잔여.
- **H5** `DraftEditor.tsx` `<div className="editor-actions">` 들여쓰기만 2칸 밀림(JSX 유효, cosmetic).
- **H6** 새 표시 3항 연산에 `idle` 분기가 없다(`DraftEditor.tsx:643`). 저장 이력이 없는 새 장면은 `latestSnapshotId === null`이라 attention도 거짓 → **"분석 완료"로 오표시**된다(구현 전 "미실행"). B5에서 깨진 pin 셀이 바로 이 상태를 지키던 셀 — 갱신 시 idle/no-version 케이스를 함께 못 박아야 한다.

## 전수 (이 세션 실측)

- 프런트 전수: `npx vitest run` — **3 failed / 382 passed (385)**, exit 1. 실패 파일 2개: `src/drafts/DraftEditor.test.tsx` 상태 바 셀 1건(B5) + `src/designTokens.test.ts` 2건(B5 — 미정의 `--status-danger` 소비·raw 색 `#a43b2c`). 전부 이 슬라이스 유래(§6). 유의: `npx vitest run | tail`로 돌리면 파이프가 exit code를 삼켜 red가 green으로 보인다 — 이 슬라이스의 "프런트 TypeScript 검사"만 거친 검증 체크리스트가 놓친 것과 같은 맹점이다.
- 백엔드 전수: **11 failed / 2659 passed / 1 skipped / 3031 subtests** — 전수 실패 전수가 §6 표에 귀속(11 failed = B1 1 + B3 1 + mypy(B2 증거) 1 + B6 5 + B7 1 + B8 1 + B9 1). `test_docs_indexes`는 이번엔 green(기록 등재 후 실측 13 passed / 276 subtests).

## Verdict

**불합격** — D4=A 확정 계약의 실행 조항("final API가 marker·snapshot을 확정한 뒤 서버에서 기존 분석 runner를 동기로 실행")이 커밋된 코드로 이행 불능이다: 모든 요청이 503(B1)이고, 표를 고쳐도 성공 경로가 500(B2)이라 분석 실행은커녕 저장 자체가 일어나지 않는다. B2는 커밋 시점의 mypy 가드가 이미 지목했고(B10 항의 정적 증거), 백엔드 전수 11 failed·프런트 3 failed **전부 이 슬라이스 유래**로 main이 red다(B1·B3·B5~B9). 같은 뿌리는 하나다 — 요청 1건·돌릴 수 있는 가드 suite를 실행해 보지 않은 채 "확인 완료"로 보고한 검증 체크리스트.

## Outstanding items

- B1~B5 폐쇄 후 재검증 필요(재검증 범위: 이 기록의 경계 행렬 + 변이 재실행). 본 기록의 repro 스크립트가 회귀 셀의 뼈대로 쓰일 수 있다(S0~S13이 그대로 셀 목록).
- H2(200 vs 502)는 오너 판단 사항 — 폐쇄 방향에 따라 브리프 문안 정정 또는 봉투·프런트 수정이 갈린다.
- 잔여(작업자 명시): final API 회귀 셀·SoT/문서 정합성 갱신(확정 계약의 변경 이력·tier/operation 수·CHANGELOG·work_log 세션 정리·HANDOFF).

## Reproduction

```bash
# test-mongo 기동 확인
docker compose -f docker-compose.test.yml up -d
# 1) 이미 실패 중인 가드(B1·B3)
python3 -m pytest tests/test_quota_enforcement_api.py -q
#    → 2 failed, 37 passed(변이 검증 시점 실측)
# 2) 실행 경로 프로브 — 42 PASS + 설계된 1 FAIL(H1), rc=1
python3 docs/verifications/2026-09-01/repro_final_save_flow.py
#    S0 = 503 관측, S0b = 500 관측, S0c~S13 = 패치 아래 행렬
# 3) 프런트 회귀(B5) — 단, | tail 등 파이프는 exit code를 삼킨다
cd frontend && npx vitest run src/drafts/DraftEditor.test.tsx src/designTokens.test.ts
# 4) 작업자 주장 재현(18 passed / 193 subtests)
python3 -m pytest tests/test_activity_actions.py tests/test_billable_actions.py -q
```
