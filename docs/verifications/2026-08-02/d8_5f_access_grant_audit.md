# D8-5f — 승격 아래 요청 감사(access_grant_uses) + C-4 소유자 사후 조회

## Subject metadata

- **날짜**: 2026-08-02
- **요청자**: 오너("다음작업 검증해줘. D8-5f 완료")
- **검증자**: Claude Code(구현자와 다른 세션, 적대적 검증)
- **대상**: 커밋 `d2cb433`(구현) + `cafcd65`(정본·기록)
- **정규 스펙**: `plans/auth-d8-5-admin-decisions.md` §7 C-3·C-4, `system-contract-sot.md` v1.7.78
- **검증 소스**: 커밋 `cafcd65`(HEAD). 검증자는 코드·테스트·정본을 코드에서 재도출.

## Scope

F1=C 하위 결정의 마지막 두 축이 시행됐다 — C-3(operation 단위 감사)와 C-4(소유자 사후 조회).
검증은 다섯 표면을 본다:

1. **계약 일관성** — 브리프 §7 C-3/C-4 요건 vs SoT v1.7.78 단언 vs 코드
2. **★ fail-closed 정책** — 감사 기록 실패 시 읽기도 실패(503). LLM 호출 감사(격리)와 정반대라는 단언
3. **기록 지점 choke point** — require_project_owner 승격 분기 하나. endpoint 추가로 우회 불가
4. **boundary matrix** — 소유자 미기록 · 거부 미기록 · 기록 내용(method/path/reason denormalize)
5. **직전 D8-5e Blocking(owner_id=None)의 폐쇄** — `8f3c52e` fix와 이 슬라이스의 상호작용

## Methodology

- 회귀·tsc는 백그라운드 재현(`python3 -m pytest -q`, `npx tsc --noEmit`).
- 뮤테이션 3종은 독립 에이전트가 `Edit` 적용 → `pytest` → 역방향 원복 → `git status` clean 으로 재현(커밋 0건).
- fail-closed 셀·choke point·owner_id=None 상호작용은 코드 경로 직접 추적 + 임시 재현.
- 모든 단언은 `file:line` 근거.

## Findings

### 계약 일관성 — 충실
- 브리프 §7 C-3("발급 + operation 단위 기록")·C-4("소유자 사후 조회")가 이 슬라이스로 전부 시행됐다.
  v1.7.77이 발급 축만 두어 "무엇을 봤는가"가 비어 있었고(오너가 C-3에서 지적한 절반),
  v1.7.78이 operation 단위(`access_grant_uses`) + C-4 조회(`GET /projects/{id}/access-log`)로 채운다.
- SoT v1.7.78 changelog + §경계 본문이 fail-closed를 **명시적 계약**으로 등재한다:
  "LLM 호출 감사와 정반대이며 의도적이다 — 그쪽은 보안 하중이 없어 격리가 옳고 이쪽은 하중을
  받아 격리가 틀리다". 코드 주석(`access_grants.py` record_use docstring)도 같은 말을 한다.
- **★ v1.7.77의 `owner_id=None` 단언이 유지**되며, `8f3c52e` fix로 실제로 지켜진다(아래).

### 회귀·tsc — 정확히 재현
- `python3 -m pytest -q`(test-mongo 127.0.0.1:27020): **1881 passed / 4 skipped / 1591 subtests /
  106.11s**, exit 0. 구현자 보고(1881/4/1591)와 일치. 직전 1874 대비 +6셀.
- `npx tsc --noEmit`: exit 0.

### 뮤테이션 3종 — 작업 AI 주장과 정확히 일치 (에이전트 독립 재현)
베이스라인: 89 passed / 760 subtests(clean tree).

| 뮤테이션 | 주장 | 실측 | 실패 셀 |
|---|---|---|---|
| record_use 호출 제거 | 3셀 | **3셀** | `test_a_read_is_refused_when_it_cannot_be_recorded` · `test_reads_under_a_grant_are_recorded_with_the_reason` · `test_the_owner_reads_the_access_log` |
| try/except로 fail-closed 해제 | 1셀 | **1셀** | `test_a_read_is_refused_when_it_cannot_be_recorded`(`RuntimeError not raised`) |
| over-strict(소유자 분기에도 record_use) | 2셀 | **2셀** | `test_the_owners_own_reads_are_not_recorded` · `test_the_owner_reads_the_access_log` |

(구현자의 "뮤테이션 4종" 표는 신규 3종 + "v1.7.77의 6종 그대로 유효" 행이다. 모순 아님.)

### ★ fail-closed — 성질은 양쪽에서 보장, 단 503 face는 app-wide 핸들러에 의존
- `record_use`(`access_grants.py`)가 `self._repo.insert_use(use)`를 **try/except 없이** 부른다.
  docstring이 "★ The caller does not swallow failures"로 못박는다.
- 검증 셀 `test_a_read_is_refused_when_it_cannot_be_recorded`(test_auth_api.py:1383)가
  `self.grants.record_use = _boom`(`RuntimeError`)으로 의존성이 예외를 삼키지 않음을 증명한다.
- **핵심 평가**: 이 셀은 `RuntimeError`를 쓴다. 반면 운영에서 `insert_use` → Mongo 장애는
  `PyMongoError`이고, `main.py` 글로벌 핸들러가 그것을 503로 바꾼다. `RuntimeError`는 핸들러에 안
  걸리므로 테스트는 예외 전파를 관찰하고, 운영은 503를 관찰한다. **"기록 없이 읽기 통과 없음"**
  (fail-closed 성질)은 양쪽 모두에서 보장된다. 다만 record_use 경로 고유의 503 face가 별도 셀로
  핀(pinned)되지는 않는다 — 그것은 app-wide 글로벌 핸들러에 의존한다(선례 `main.py:340`가
  `get_project`에 대해 입증한 패턴). 실제 위험은 없다(Hardening #1로 기록).

### choke point + 자기참조 — 닫혀 있다
- `require_project_owner`의 승격 분기가 기록하는 **유일한 지점**이다. endpoint를 추가해도
  `_REQUIRE_PROJECT_OWNER` dependency를 타므로 우회 불가(재색인 choke point와 같은 형태).
- `GET /projects/{id}/access-log` 자체도 이 dependency를 탄다. 그래서 **관리자가 승격으로
  access-log를 읽으면 그 읽기가 다시 use 행으로 기록된다**(자기참조). 무한루프 아니다 — record_use는
  의존성 안에서 요청당 한 번이고 endpoint가 다시 의존성을 부르지 않는다. docstring이 이를 명시한다.
- 소유자 분기엔 record_use가 없다 → **소유자 자신의 사용은 기록되지 않는다**(L1362 셀이 잠금).
  섞이면 접근 이력이 소유자 활동 로그로 오염돼 C-4의 쓸모가 사라진다.

### 직전 D8-5e Blocking의 완전 폐쇄
- `8f3c52e`가 승격 분기 선두에 `project.owner_id is not None`을 정확히 추가했다(D8-5e 검증의 추천).
- **빈 셀이 채워졌다**: `test_a_grant_does_not_adopt_an_unowned_project`(test_auth_api.py:1316)가
  무소유 project + 승격 → **403**을 단정한다. D8-5e에서 검증자가 지적한 빈 셀이 fix와 함께 잠겼다.
- 이 슬라이스와의 상호작용: owner_id=None은 승격 분기 진입 전 403 → `record_use` 도달 불가 →
  기록 없음. 이것은 결함이 아니라 "접근이 없었으므로 기록도 없다"의 정확한 결과이며, 거부된 접근을
  기록하면 access 로그가 노이즈로 오염되는(L1362 over-strict 셀이 잠그는 바로 그 것) 원칙과 일관한다.

## Issues / Risks

### Blocking (계약 의무 위반)
없음.

### Hardening recommendations (비차단)
1. **record_use 경로 고유의 503 face가 별도 셀로 핀되지 않는다.** L1383은 `RuntimeError`로
   글로벌 핸들러를 우해 의존성이 예외를 삼키지 않음을 증명하지만, record_use → PyMongoError →
   503 경로 자체는 app-wide 글로벌 핸들러에 의존한다. record_use 경로의 503을 직접 핀하는 셀을
   추가하면(`get_project`의 L340 선례처럼) 의존성이 더 완전해진다. 실제 위험은 없다.
2. **access-log 자기기록(grant holder가 access-log를 읽으면 log에 추가)이 별도 셀로 핀되지 않는다.**
   아키텍처적으로 choke point가 닫혀 있어 우회 가능성은 없으나, 이 자기기록 동작 자체를 단정하는
   셀이 있으면 의도가 명시된다.

## Verdict

**합격.** 계약(C-3·C-4·fail-closed)이 코드·테스트·정본에서 일관되게 시행됐고, 뮤테이션 3종이
작업 AI 주장과 정확히 일치하며(3/1/2셀), 직전 D8-5e의 owner_id=None Blocking이 완전히 폐쇄됐다.
Hardening 2건은 비차단이고 실제 위험이 없다.

## Outstanding items

- Hardening #1·#2는 선택 — 작업 AI 판단에 맡긴다.
- D8-5 남은 것: 5-b(전 프로젝트 목록) · 5-d(관리자 화면) · C-6(최초 로그인 비밀번호 변경 강제,
  오너 확정·별개 축·미착수).
- 본 검증은 커밋하지 않은 상태(검증자는 결함을 고치지 않고 보고). 기록·카운트 갱신만.

## Reproduction

```bash
# 회귀(test-mongo 127.0.0.1:27020 선행)
python3 -m pytest -q            # 1881 passed / 4 skipped / 1591 subtests

# tsc
cd frontend && npx tsc --noEmit # exit 0

# 뮤테션 3종(각각 Edit → pytest → 역방향 원복, 커밋 금지)
# 1. record_use 호출 제거 → 3셀 실패
# 2. record_use try/except 삼킴 → test_a_read_is_refused_when_it_cannot_be_recorded 실패
# 3. 소유자 분기에 record_use 추가 → test_the_owners_own_reads_are_not_recorded + test_the_owner_reads_the_access_log 실패

# 직전 Blocking 폐쇄 확인
# test_auth_api.py::AdminAccessGrantTest::test_a_grant_does_not_adopt_an_unowned_project → 403
```
