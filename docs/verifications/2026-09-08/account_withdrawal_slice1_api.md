# 독립 검증 기록 — 계정 탈퇴 Slice 1: 셀프 요청·취소 API

## Subject metadata

- **일자**: 2026-09-08 · **요청자**: 오너("다음작업 검증해줘… 전체 백엔드 스위트 돌고있다니까 그거도 참고하고") · **검증자**: 독립 검증 세션(구현 세션 41과 다른 세션 — Slice 0 검증과 같은 검증자)
- **대상 슬라이스**: 계정 탈퇴 Slice 1 — `POST`·`DELETE /me/withdrawal`. 커밋 `5ce06f3`(구현)·`374d93f`(H2 셀)·`23235d6`(기록)·`40c1a77`(기준선). 검증 범위에 **사이 이력 셋**을 포함한다: `936ae4f`(Slice 0 검증 H1 폐쇄 셀)·`ad7c877`(수령 기록)·`3d16d83`(기준선 2937/3878) — 이번 슬라이스의 H1·H2 폐쇄 주장이 그 위에 서 있으므로.
- **소스**: main HEAD `40c1a77`, 트리 clean, push 대기(검증 기록 커밋 전 기준 10커밋 선행).
- **정규 스펙**: [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) Slice 1(**2026-09-08 정정판** — 검증 목록 두 줄 고침 포함) + D1~D6 표 · SoT **v1.8.46** 행 · 선례: S-3(경로가 project id 를 받지 않는 것이 방어)·H3(detail 분기 금지)·`SignupNotPending` 409.

## Scope

★ = 가장 의심스러운 축.

1. ★ **라우트 계약** — 200 멱등(201 아님)·409 두 생산자(마지막 활성 관리자·취소 없는 취소, 404 아님)·401·**403 부재가 계약**이라는 주장(행위 축+선언 축)·`purge_due_at` 서버 제공.
2. ★ **계획서 검증 목록 두 줄 정정** — "타인 403" 도달 불가 · "활동 로그 기록" 불가(project 축/admin_audit 축 근거의 사실성).
3. **신규 라우트 등재 체크리스트 6축** — 오류 선언·tier 카운트(핀·HANDOFF·SoT)·활동 분류·라벨 표(경계 행렬 rationale)·plans 인덱스·유료 분류 제외 근거.
4. ★ **H1·H2 폐쇄 실증** — H1 셀(`936ae4f`)이 이전 X1 변이를 실제로 무는가 · H2 조건부 쓰기(`only_if_absent`)가 셀로 잠겼는가(자기 실토한 MW-4 무가드의 폐쇄).
5. 구현자 변이 MW-1~6 재유도 + **검증자 대항 변이 3종**(X1 재실행·X2 payload purge_due_at 제거·X4 409→404).
6. 초점 7파일·백엔드 전수·tsc 재실측과 산술.
7. 기록 일관성 — SoT v1.8.46·계획서·HANDOFF·plans 인덱스·work_log 세션 41 (+측정 낡음 2건의 확인).

## Methodology

전수는 구현 세션 캡처 파일(`backend_full3.txt`)을 검증자가 직접 판독 + 산술 대조. 초점·tsc·변이는 검증자 실행(전량 파일 캡처, 요약 라인+`FAILED|SUBFAILED` 판독). 변이는 매번 프리플라이트 `git status --short` 확인 → assert 유일성 검증 일회 치환 → 실행 → `git checkout --` 원복 → clean 확인(9회 전부; 사이에 구현 세션의 마감 문서 커밋이 있었지만 트리는 매 회 검사).

```bash
python3 -m pytest -q tests/test_auth_api.py tests/test_auth_users.py tests/test_auth_users_mongo.py \
  tests/test_activity_actions.py tests/test_activity_log.py tests/test_billable_actions.py \
  tests/test_typecheck.py > /tmp/verify_s1_focused.txt 2>&1   # → 283 passed, 1244 subtests, 109.32s
(cd frontend && npx tsc --noEmit)                              # → rc=0
# 전수(구현 세션 캡처): "2954 passed, 1 skipped, 3900 subtests in 1370.53s" EXIT=0
# 변이(예: MW-4): users.py 의 only_if_absent=True → False (assert count==1)
#   → pytest -q tests/test_auth_api.py tests/test_auth_users.py tests/test_auth_users_mongo.py
# 환경: WSL2 · test-mongo(rs-test 127.0.0.1:27020) · 개발 스택 전면 healthy(당일 복구분)
```

## Findings

### F1. ★ 라우트 계약 — 주장 전부 코드·셀로 확인

- `routers/auth.py:269-297`: `POST`(200 멱등·`LastActiveAdmin`→409)·`DELETE`(200·`WithdrawalNotRequested`→409), 둘 다 `_REQUIRE_AUTH`. `_ERRORS_WITHDRAWAL`(errors.py) = **409·503 뿐 — 403 없음**이 선언면에서도 사실.
- **403 부재가 설계**: 경로가 대상을 지목하지 않아(`/me/…`) 남의 계정을 향한 요청을 만들 수 없다. 행위 축 셀(`test_the_subject_is_the_session_not_a_path_argument` — 두 사람이 각각 요청해도 격리) + 선언 축 셀(`test_neither_operation_declares_a_403` — `route.responses`에 403 없음·401/409 있음)의 두 면으로 잠김.
- `purge_due_at` 는 라우터가 `purge_due_at(user)` 를 부를 뿐(**산술 없음**, `routers/auth.py:268-273`) — 유예 정본이 서버 상수 한 곳이라는 Slice 0 계약의 연장. `WithdrawalResponse` 는 두 값(`withdrawal_requested_at`·`purge_due_at`)만.
- D6 재사용은 서비스 축 그대로(라우터는 409 매핑만) — Slice 0 검증 F1 과 동일 구조.

### F2. ★ 계획서 두 줄 정정 — 사실 판단 전부 성립

- **"타인 403" 도달 불가**: 정정 전 문언이 diff(`23235d6`)에 남아 있고, 경로 모양(대상 인자 없음)·선언(403 없음)·셀(두 축)이 삼각으로 뒷받침. S-3 선례(경로가 project id 를 받지 않는 것이 IDOR 방어)와 같은 성질임도 코드상확인.
- **"활동 로그 기록" 불가**: `activity_events` 가 `project_id` 필드를 요구하는 프로젝트 축(`activity/log.py` 선례·D8-6 I1)이고 `admin_audit` 가 `admin_user_id` 를 요구하는 관리자 행위 축이라는 근거가 실제 스키마와 일치. `/auth/login`·`logout`·`signup` 이 같은 `not_project_scoped` 자리에 있는 것도 확인(`actions.py` 인증 절). **등재로 대체**(사유 "계정 축")한 것이 계약 정합 — 미기록이 아니라 기록면에 사유가 박혔다.
- 두 정정 모두 **오너 판단 불필요**에 동의: 계획서 체크리스트 문언이 확정 계약(프로젝트 축·S-3)을 몰랐던 것으로, 계약 쪽이 정본이다.

### F3. 등재 체크리스트 6축 — 전부 갱신됨

① 오류 선언 `_ERRORS_WITHDRAWAL` ② tier: 핀 102→104·project 76 무변(`test_auth_api.py:2052-2056`)·HANDOFF 두 자리·SoT v1.8.46 행·경계 행렬 rationale 2행("라벨 표") ③ 활동 분류 `EXCLUDED_OPERATIONS` 29→31·절 주석 인증 3→5 ④ plans 인덱스·계획서 상태 갱신 ⑤ `schema.d.ts` 재생성(`/me/withdrawal` 등재, tsc rc=0 재실측) ⑥ 유료 분류 제외 — provider 호출 없음(`billable_actions` 무변, 초점 7파일에 포함해 초록 확인). **낡은 "102" 표기 전수 스윕 0건**(변경이력 행 제외).

### F4. ★ H1·H2 폐쇄 실증 — 이전 검증의 권고 둘이 실제로 닫혔다

- **H1**: `936ae4f`의 왕복 셀(`test_the_write_face_carries_the_stamp_through_insert_and_replace`)이 insert·replace 양경로 왕복+저장면 검사. **X1 변이 재실행 → 1실패**(Slice 0 때는 0실패) — 폐쇄 실증.
- **H2**: 조건부 쓰기가 시임(Protocol·InMemory·Mongo 세 곳 동일 시그니처)+서비스+셀 6으로 닫혔다. **MW-4 재유도 → 1실패**(StaleOnce 경쟁 재현 셀). 구현자가 스스로 실토한 "처방만 넣고 셀을 안 둔 무가드"(커밋 메시지 "닫는다"는 그 시점 허위였음)는 재검증으로 확인 — 변이가 안 먹은 것이 아니라 가드가 없는 쪽이었다는 판단 절차(재적용+grep)도 work_log 에 남아 재현 가능.
- **닫히지 않는 것의 정정**(취소를 가로지르는 지연 요청은 여전히 걸림 — 순서의 모호함)이 코드 주석(`users.py:431-440`)과 SoT 행에 같은 문언으로 — 과장 정정이 계약에 반영됨.

### F5. 변이 재유도 — 구현자 6종 전부 재현 + 대항 3종

| 변이 | 적용 diff(그대로) | 결과 | 표와 |
|---|---|---|---|
| MW-1 멱등 파괴 | 조기 반환 2줄 삭제 + `only_if_absent=True`→`False` (users.py) | **3실패**(API 반복·도메인 반복·**경쟁 재현 셀**) | 표 "2" — ★아래 |
| MW-2 취소 no-op | `WithdrawalNotRequested` raise 블록 삭제 | **3실패**(409-not-404·subject-is-session·도메인 거부) | ✓ 3 |
| MW-3 over-strict 403 선언 | `_ERRORS_WITHDRAWAL`에 `403: _ERROR` 추가 | **6 SUBFAILED**(선언 셀 2·`ProjectAuthorizationTest` 2·`CombinedBoundaryMatrixTest` 2) | ✓ 6 subtests |
| MW-4 조건부→무조건 | `only_if_absent=True`→`False`(서비스 호출부만) | **1실패**(경쟁 재현 셀) | ✓ 1 |
| MW-5 활동 등재 제거 | `ExcludedOperation` 2행 삭제 | **3실패**(분류·절 주석 subtest·머리 수) | ✓ 3 |
| MW-6 Mongo 조건 제거 | `query["withdrawal_requested_at"] = None`→`pass` | **1실패**(질의가 가른다 셀) | ✓ 1 |
| **X1 재실행** | `_doc` 탈퇴 필드 줄 삭제 | **1실패**(H1 왕복 셀) | — H1 폐쇄 실증 |
| **X2 대항** | payload에서 `"purge_due_at": purge_due_at(user),` 줄 삭제 | **7실패**(응답 계약 전반) | — 두 번째 정본 시나리오 강잠금 |
| **X4 대항** | 취소 `status_code=409`→`404` | **2실패**(409-not-404·subject-is-session) | — |

★ **표 두 곳의 낡음(비차단)**: MW-1의 "2실패"와 초점 전수 "277"(F6)은 모두 **H2 셀 커밋(`374d93f`) 이전 트리에서의 측정치**가 세션 마감 기록까지 그대로 흘러든 것 — 최종 트리에서는 MW-1=3(경쟁 셀 추가)·초점=283. 가드 자체는 전부 물므로 잠금 문제가 아니라 측정 시점 표기 문제다("측정 트리를 밝혀라" — 기록 규칙의 정신).

### F6. 전수·초점·tsc 재실측과 산술

- **초점 7파일(검증자 실행): 283 passed / 1244 subtests · EXIT=0 · 109.32s.** 구현자 기록 "277/1244"와 **passed 6 차이 = H2 셀 6개**(277+6=283, subtests 는 H2 셀에 subtest 가 없어 불변) — 위 낡음과 동일 근원.
- **백엔드 전수(구현 세션 캡처 판독): 2954 passed / 1 skipped / 3900 subtests · EXIT=0 · 1370.53s.** 산술: 직전 기준선 2937/3878(3d16d83, H1 셀 포함) + 신규 17(API 11·도메인 4·Mongo 2) = **2954 정확**. subtests +22는 선언 셀 2(메서드별 subTest)와 라우트 104를 도는 열거 가드들의 반복 증가로 방향이 설명된다(전건 귀속은 구현 세션 마감 `40c1a77`이 이미 수행 — 증분 22 전건 귀속 기록과 독립 산술이 일치).
- **tsc rc=0 재실측**(frontend/ 안에서 — 함정 절의 cwd 경고대로 절대경로 서브셸).
- 셀 수: `test_auth_api.py` 132→143(+11)·`test_auth_users.py` 60→64(+4)·`test_auth_users_mongo.py` 22→25(+2, 별도 H1 +1은 936ae4f) — "17셀" 주장과 정확히 일치.

### F7. 기록 일관성

SoT v1.8.46(헤더·행 — v1.8.45 바로 뒤, 내용이 코드와 대응)·계획서 Slice 1 정정판·HANDOFF(tier 두 자리·착수 지점 Slice 2·첫 판단 질문)·plans 인덱스·README SoT 버전 bump·work_log 세션 41(자기 실토·정정 절차·변이 표) — 상호 모순 0건. 유일한 흠은 F5/F6의 측정 낡음 2건과 **CHANGELOG 행 부재**(아래).

## Issues / Risks

### Blocking (contract obligations)

**없음.** 정정된 검증 목록의 분기 전부(멱등 200·취소 후 재요청·마지막 관리자 409·401·403 부재 두 축·활동 비등재·purge_due_at)가 기명 셀에 잠겼고 변이 9종 전부 물었다.

### Hardening recommendations (non-blocking)

- 없음(신규). 참고로 "취소를 가로지르는 지연 요청"은 설계상 수용(순서의 모호함)이며 코드 주석·SoT·계획서에 같은 문언으로 명시돼 있다 — Slice 2 착수 시 이 문언이 그대로 유지되는지만 보면 된다.

### 기록 정확성 (비차단, 수정 권고)

- **R1 초점 전수 "277"**: 최종 트리에서는 **283/1244**(H2 셀 6 이전 측정).
- **R2 변이 표 MW-1 "2"**: 최종 트리에서는 **3**(경쟁 재현 셀 포함).
- **R3 CHANGELOG 행 부재**: Slice 0(v1.8.45)·Slice 1(v1.8.46) 둘 다 없다 — 기록 가이드는 "주요 설계·기능 변화"마다 행을 요구하고 D4(v1.8.43, 더 작은 변경)가 행을 가진 선례다. **두 슬라이스를 묶은 행 1개**를 권장(기준선 갱신 커밋에 실으면 충분).

## Verdict

**합격**

- 정정된 계획서 계약의 분기 전부가 기명 셀에 추적 — 빈 칸 0; 등재 체크리스트 6축 전부 갱신.
- 구현자 변이 6종 + 대항 3종(이전 검증 X1 포함) 재유도 **전부 기명 셀 재실패** — MW-3의 6 subtests 구성(내 셀 2·기존 가드 4)까지 정확히 일치.
- H1·H2(이전 검증 권고)의 폐쇄가 셀 수준에서 실증됨(X1 재실패 1실패·MW-4 1실패).
- 초점 283/1244·전수 2954/1/3900 EXIT=0 산술 정확(2937+17)·tsc rc=0.
- 계획서 두 줄 정정의 근거(프로젝트 축·S-3·`SignupNotPending`)가 전부 원문 확인 — 오너 재판단 불요에 동의.
- R1·R2(측정 낡음)·R3(CHANGELOG)은 기록 정확성 권고이며 잠금·계약 흠결이 아니다.

## Outstanding items

- **push 대기**: 구현 9커밋(Slice 0 2 + 수령·기준선 3 + Slice 1 4) + 검증 기록 2커밋(Slice 0 검증 `0bd8153` + 본 커밋) = **11커밋**. 오너가 push 한다.
- **CHANGELOG 행 1개 권고**(R3 — 두 슬라이스 묶음, 다음 기록 커밋에).
- **Slice 2 첫 판단(오너 없이 진행 가능한 갈림길 아님)**: 상태 읽기 표면(남은 일수)을 `/auth/me` 확장으로 둘지 별도 `GET /me/withdrawal` 로 둘지 — work_log Next steps·HANDOFF 에 질문으로 등재되어 있다. 응답 계약을 늘리는 쪽이므로 착수 시 구현자가 브리프 형태로 정리해 오너 확정을 받는 것이 순서에 맞다(`WithdrawalResponse` 가 이미 있어 별도 GET 은 자연스럽고, `/auth/me` 확장은 모든 소비자의 payload 가 변한다).
- 전수 캡처 `backend_full3.txt`(구현 세션 scratchpad) — 세션 종료 시 소실 여부는 구현 세션 몫.

## Reproduction

```bash
git status --short   # 공백이어야 변이 가능
# 초점(≈110초): 283 passed / 1244 subtests
python3 -m pytest -q tests/test_auth_api.py tests/test_auth_users.py tests/test_auth_users_mongo.py \
  tests/test_activity_actions.py tests/test_activity_log.py tests/test_billable_actions.py tests/test_typecheck.py
(cd frontend && npx tsc --noEmit)   # rc=0
# 변이 예시(MW-4): users.py 의 only_if_absent=True→False 후 상기 3 auth 파일 → 1 failed
#   → git checkout -- services/application/app/auth/users.py → status 공백
# 백엔드 전수(test-mongo 27020): 2954 passed / 1 skipped / 3900 subtests
docker compose -f docker-compose.test.yml up -d && python3 -m pytest -q > /tmp/full.txt 2>&1; echo EXIT=$?
```
