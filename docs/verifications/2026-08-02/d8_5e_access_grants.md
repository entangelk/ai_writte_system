# 독립 검증 — D8-5e 관리자 승격(access grant)

## Subject metadata

| | |
|---|---|
| 대상 커밋 | `c62944b`(구현) + `7381596`(정본 v1.7.77·기록) |
| 정규 스펙 | `system-contract-sot.md` v1.7.77 §"제품과 프로젝트 경계" · `plans/auth-d8-5-admin-decisions.md` §7(C-1~C-5) |
| 검증자 | 구현자와 **다른 세션**. 일부 항목은 별도 에이전트가 독립 경로로 재현했다 |
| 구현자 재실측 | §"구현자 재실측" — Blocking 을 직접 재현했고, 비차단 지적도 재현해 확정했다 |
| 판정 | **조건부 합격** — Blocking 1건(`owner_id=None` 계약 위반). 조건은 아래 hardening 으로 닫혔다 |

## Findings — 확증된 것

- **회귀 1874 / 4 skipped / 1579 subtests**(104.02s) · `tsc` exit 0 — 정확히 재현
- **뮤테이션 6종 독립 재현**: 읽기 전용 해제 → 3 · 승격 검사 무력화 → 1 · 만료 판정 제거 → 3 ·
  TTL 24h → 4 · **over-strict(소유자 GET 제한) → 정확히 33**. 전부 re-fail 확인
- **C-2 읽기 전용 = HTTP method 설계** — 검증에서도 타당(새 endpoint 가 fail-closed 로 시작)
- **TTL 인덱스 의도적 부재**(`test_there_is_no_ttl_index`) · 1시간 계약 리터럴 · 사유 필수(도메인
  경계) · 만료=판정(삭제 아님) · D8-6 파기 배선 — 코드·테스트 모두 정확
- boundary matrix 11셀(발급·사유·404·승격없음·읽기개방·쓰기거부·만료·감사잔존·scope·non-admin·purge)
- 사고 기록(`git checkout`) · C-3 operation 단위 감사를 명시적 후속으로 남긴 것 — 충실

## 🔴 Blocking — `owner_id=None` 이 승격으로 열렸다 (E1=A 위반)

**정본이 세 곳에서 반대를 단언한다**: v1.7.77 changelog("`owner_id=None`은 승격으로도 열리지
않는다(E1=A 유지)") · §경계("승격은 주인 없는 project 를 입양하지 않는다") ·
`require_project_owner` docstring("keeps denying everyone").

**코드는 안 지켰다.** 두 번째 분기(승격)에 `project.owner_id is not None` 검사가 없었다 —
첫 분기(소유자)에는 있고 승격 분기에만 빠졌다.

**세 경로가 같은 결론에 도달했다**:

| 경로 | 방법 | 실측 |
|---|---|---|
| 검증자 | 무소유 project + 관리자 승격 + GET (임시 테스트) | **200** (403이어야 함) |
| 별도 에이전트 | **강화 뮤테이션** — 두 번째 분기에 `owner_id` 검사를 *추가* | **82 passed, 어떤 셀도 안 깨짐** = 빈 셀의 직접 증거 |
| 구현자 재실측 | 스크립트로 무소유 project 생성 → 승격 발급 → GET | **200**, 승격 없이는 403 |

**왜 안 잡혔나 — 빈 셀.** `AdminAccessGrantTest` 11셀이 **전부 alice 소유 project** 만 써서
"무소유 + 승격" 조합이 **0건**이었다. 가드가 촘촘해 보였지만 그 축에는 아무것도 없었다.

**도달 가능성**: `create_project` 는 owner 를 강제하지만, D8-3 주석이 스스로 인정하듯 무소유 행은
*deletion bug or future migration* 으로 남을 수 있다 — **그것이 E1=A "항상 deny" 가 존재하는
이유**다. 즉 이 분기는 E1=A 가 정확히 방어하려던 상황에서만 뚫린다.

## 비차단 — 뮤테이션 2의 라벨이 과장이었다

구현자가 work_log 에 "`is_admin` 제거 → 비관리자 승격 셀 **+ 인증 격리 셀**"이라 적었으나,
두 번째 실패는 실제로 **크래시**였다:
`AttributeError: 'State' object has no attribute 'access_grants'`. 격리 셀의 probe 앱이
`access_grants` 를 state 에 안 넣기 때문이다. 실패 **건수**(2)는 맞지만 **원인 라벨**이 틀렸다.

**구현자 재실측이 여기서 한 걸음 더 나갔다** — 이 크래시는 라벨 오류일 뿐 아니라 **잠재 취약점**
이다: 격리 셀은 `is_admin` 단락평가가 `access_grants` 접근을 막아 주는 덕에 통과하고 있었다.
분기 순서를 바꾸는 리팩터가 들어오면 그 셀은 **성질을 단정하는 대신 AttributeError 로 죽는다**.

## 구현자 재실측 (검증자 주장에 대한 반증 시도)

지난 슬라이스에서 검증자 주장 2건이 재실측으로 무너졌으므로 이번에도 그대로 받지 않았다.

- **Blocking → 반증 실패, 확증.** 직접 재현에서 `owner_id=None` + 승격 + GET = **200**.
  코드를 읽어도 두 번째 분기에 검사가 없다. 검증자가 옳다.
- **비차단 라벨 → 확증**, 그리고 원인이 예상보다 나쁘다(위 취약점).

## Hardening (이 검증 이후 닫은 것)

| # | 조치 | 커밋 |
|---|---|---|
| Blocking | 승격 분기에 `project.owner_id is not None` 추가 + **빈 셀 회귀** `test_a_grant_does_not_adopt_an_unowned_project`. 테스트 선행(셀이 결함 재현 → 수정 → green), 뮤테이션에서 그 셀만 재실패 | `8f3c52e` |
| 비차단 | probe 앱에 `access_grants` 배선 — 뮤테이션이 이제 **크래시 없이 정확히 1셀**(비관리자 승격)만 문다. 라벨 정정도 work_log 에 반영 | 본 커밋 |

## Verdict

**조건부 합격**, 조건은 위 hardening 2건으로 닫혔다.

구현 자체는 계약에 충실하고 뮤테이션 가드가 양방향으로 든든하다. 그러나 **"가드가 많다"가 "그 축이
덮였다"를 뜻하지 않는다**는 것을 이 슬라이스가 다시 보여 줬다 — 11셀이 있었고 그중 무소유 project
를 쓰는 것은 0건이었다. 빈 셀은 통과하는 테스트로는 보이지 않고, **강화 뮤테이션(고칠 것을 미리
넣어 보고 아무것도 안 깨지는지 확인)** 이 그것을 드러낸 기법이다.

## Outstanding items

- 없음. C-3 operation 단위 감사 · C-4 사후 조회 · 5-b · 5-d · C-6 은 이 슬라이스가 명시적으로
  범위 밖으로 선언한 후속이며 검증 대상이 아니었다.
