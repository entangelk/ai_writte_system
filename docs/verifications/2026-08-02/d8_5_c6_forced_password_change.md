# D8-5 C-6 — 관리자가 정한 비밀번호는 1회용 (최초 로그인 교체 강제 + 비밀번호 정책)

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("다음작업 검증해줘. C-6 완료")
- **검증자**: Claude Code(구현자와 다른 세션, 적대적 검증)
- **대상**: 커밋 `d13c471`(구현) + `9779a71`(정본·기록)
- **정규 스펙**: `plans/auth-d8-5-admin-decisions.md` §7 C-6, `system-contract-sot.md` v1.7.80,
  `verifications/2026-07-28/auth_d8_5a_admin_boundary.md` H-c(비차단 위험의 원출처)
- **검증 소스**: 커밋 `9779a71`(HEAD). 검증자는 코드·테스트·정본을 코드에서 재도출.

## Scope

D8-5a 검증 H-c가 남긴 위험(*관리자가 사용자의 비밀번호를 아는 상태*)을 "최초 로그인 시 변경 강제"로 닫는다.

1. **★ 강제 지점 = 세션 발급** — `/auth/login`에서 409. 대안(모든 operation)은 73개에 새 상태코드 + "403
   생산자는 정확히 둘" 불변식 위반. 파급 0 주장.
2. **자격증명-검증-우선** — 401 before 409. 409가 열거 신호가 되지 않는다.
3. **정책 = 교체 경로에만** — `MIN_PASSWORD_LENGTH=12`, `change_password`에서만, `create_user` 제외.
4. **Mongo `.get(..., False)`** — C-6 이전 계정(필드 없는 행) 잠김 방어.
5. **플래그 2표면 + 디스커버리 가드** — `POST /admin/users`·`create_user.py`만 True.
6. **제품 공백 ★** — 관리자 계정 브라우저 로그인 불가. 정직한 보고.

## Methodology

- 회귀·tsc 백그라운드 재현.
- 뮤테이션 4종 + 순서 가드 뮤테이션은 독립 에이전트가 `Edit` → `pytest` → 원복 → `git status` clean으로 재현(커밋 0건).
- 디스커버리 가드·Mongo `.get` 무방비는 에이전트가 능동 반증(false-negative 주입, 하드 서브스크립트 회귀)으로 검증.

## Findings

### 회귀·tsc — 정확히 재현
- `python3 -m pytest -q`: **1898 passed / 4 skipped / 1608 subtests / 107.44s**, exit 0. 직전 1887 대비 +9셀.
- `npx tsc --noEmit`: exit 0.

### 뮤테이션 4종 — 작업 AI 주장과 정확히 일치 (에이전트 독립 재현)
| 뮤테이션 | 주장 | 실측 | 비고 |
|---|---|---|---|
| 강제 무력화(`if user.must_change_password:`→`if False:`) | 7셀 | **7셀** | 7번째는 `AdminUserApiTest::test_created_user_can_log_in_and_is_active` — ForcedPasswordChangeTest 밖의 교차 셀 |
| over-strict(플래그 미삭제) | 2셀 | **2셀** | |
| 정책 1자(`MIN_PASSWORD_LENGTH=12`→`1`) | 2셀 | **2셀** | |
| 불필요 new_password 무시(elif `pass`) | 1셀 | **1셀** | |

### 자격증명-검증-우선 가드 — 실제 작동
`test_a_wrong_password_is_401_whether_or_not_a_change_is_due`(test_auth_api.py:1260)가 틀린 비밀번호+대기 / 틀린 비밀번호+정상이 모두 401(동일 JSON)임을 단정. 순서 바꾸기 뮤테이션(409를 먼저 띄우게)이 정확히 이 셀을 `409 != 401`로 깸 → 열거 누출을 잠그는 가드임이 증명됨.

### 강제 지점·정책·플래그 — 전부 정확
- `/auth/login`만 `_ERRORS_LOGIN_409` 선언 → 73개 operation은 검사·선언 모두 무영향 → "403 생산자는 정확히 둘" 불변식 유지.
- `MIN_PASSWORD_LENGTH=12`는 `change_password`에서만 검사. `create_user`는 통과 → 기존 fixture 88곳 무영향(작업 AI 주장 확인).
- `set_password`가 hash 교체 + `must_change_password=False`를 원자적으로 같이(InMemory·Mongo 양쪽).
- `POST /admin/users`(main.py:2631)·`scripts/create_user.py`만 `must_change_password=True`; `phase2a_provider_live_smoke.py:138`은 기본 False.

### 제품 공백 ★ — 정직하게 등재됨
- SoT v1.7.80 changelog: "★ 알려진 제품 공백: 프론트가 아직 new_password를 못 보내므로 관리자가 만든 계정은
  브라우저로 로그인할 수 없다(API로는 가능) — D8-5d 필수 항목".
- HANDOFF L46-47(C-6 완료 + 5-d 필수 항목 ★강제 교체 UI)·L58(부트스트랩 명령에 1회용 명시).
- D8-5a 검증 H-c(2026-07-28)를 정확히 참조.

## Issues / Risks

### Blocking (계약 의무 위반)
없음. 코드는 정확하고 즉시 위험은 없다.

### Hardening recommendations (비차단)

**#1 [우선] Mongo `.get(..., False)`가 테스트 무방비 — SoT 명시 방어가 green bar에 잠기지 않는다.**
에이전트가 결정적 반증: `_entry`의 `doc.get("must_change_password", False)`를 하드 서브스크립트
`doc["must_change_password"]`로 뮤테이션(pre-C-6 행에서 KeyError → 로그인 전체 잠김)했더니 **전체
1898 테스트가 0 failed로 통과**. 라운드트립 테스트가 모두 `_doc`를 거쳐 항상 필드를 쓰기 때문. SoT v1.7.80이
"C-6 이전 계정은 안 잠긴다"고 명시한 방어가 단 하나의 테스트도 잠그지 않는다 — 코드 주석이 "KeyError here
would lock every pre-existing account out of login"이라 쓴 위험을 테스트가 뒷받침하지 않는다. 코드는
올바르지만, 누군가 `.get`을 `[]`로 바꿔도 green bar가 못 잡는다. **권고**: pre-C-6 행(필드 없는 doc)을
`_entry`에 먹이는 셀을 추가해 `must_change_password=False`가 나오는지 단정.

**#2 디스커버리 가드가 문자열 그렙 — 작업 AI "실제 호출부 집합" 주장은 과장.**
`test_the_two_admin_surfaces_mark_the_password_single_use`는 `assertIn("must_change_password=True",
source)` 부분문자열 매칭. 에이전트 증명: `create_user.py`에서 kwarg 제거하되 **주석에
`must_change_password=True` 문자열을 남기면 가드가 통과**(false negative). 변수 전달
(`flag=True; create_user(..., must_change_password=flag)`)이나 새로운 제3의 관리자 표면(3개 하드코딩
경로만 봄)을 못 잡는다. 양방향으로는 작동하지만 "실제 호출부 집합"이라는 표현은 정확하지 않다. **권고**:
호출부를 AST/임포트 기반으로 잡거나, 적어도 주석이 아닌 kwarg만 매칭하게 좁힌다.

## Verdict

**합격.** 핵심 설계(강제 지점=세션 발급·자격증명-검증-우선·정책=교체 경로·제품 공백 정직 보고)가 코드·테스트·
정본에서 일관되고, 뮤테이션 4종(7/2/2/1)이 작업 AI 주장과 정확히 일치하며, 자격증명-검증-우선 가드가 실제로
열거 방어를 잠근다. 코드는 올바르고 즉시 위험은 없다. Hardening #1(Mongo `.get` 무방비)은 SoT 명시 방어가
green bar에 잠기지 않은 것으로, 셀 추가를 우선 권고한다 — 이 슬라이스의 잔여 빈 셀.

## Outstanding items

- Hardening #1(pre-C-6 행 `_entry` 셀)·#2(디스커버리 가드 정밀화) — 작업 AI 판단에 맡기되, #1은 SoT 명시라 우선.
- D8-5 남은 유일 항목: 5-d(관리자 화면) — 필수 4(① 강제 교체 UI ★ ② 전 프로젝트 목록 ③ 사용자 관리 ④ 승격 발급/접근 이력). 첫 프론트 슬라이스.
- 본 검증은 커밋하지 않은 상태에서 기록만 작성 후 커밋.

## Reproduction

```bash
python3 -m pytest -q            # 1898 passed / 4 skipped / 1608 subtests
cd frontend && npx tsc --noEmit # exit 0

# 뮤테이션(Edit → pytest tests/test_auth_api.py -q → 원복, 커밋 금지)
# 1. main.py 의 if user.must_change_password: → if False: → 7셀 실패
# 2. users.py set_password 에서 must_change_password=False 제거 → 2셀 실패
# 3. users.py MIN_PASSWORD_LENGTH=12 → 1 → 2셀 실패
# 4. main.py elif request.new_password is not None: → pass → 1셀 실패
# 순서 가드: authenticate 앞에 409 먼저 띄우기 → test_a_wrong_password_is_401... 실패
# Mongo .get 무방비: users_mongo.py _entry 의 .get(...,False) → doc[...] → 1898 통과(★ 빈 셀)
```
