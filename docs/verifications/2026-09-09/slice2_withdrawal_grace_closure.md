# Slice 2 종결(세션 45 수령) — 문서·변이·전수 기준선 독립 검증

- 일자: 2026-09-09
- 요청자: 오너("검증하고 의심하고 또 의심")
- 검증자: Claude Code(구현 세션과 다른 세션 — 구현자 보고를 사실로 받지 않고 재측정)
- 대상: Slice 2 종결 커밋 4건 `7e73233`(문서 체크포인트·SoT 순서 문장 정정) · `19e422b`(MS2-7 핀 셀) · `b4b1d7c`(S9 경계 4001→6001) · `5288b7c`(세션 45 기록·기준선). 참조: 오너 세션 정정 `79c065a`(v1.8.48 행 변이 주장 정정).
- 정규 스펙: [`plans/account-withdrawal-implementation-phases.md`](../../plans/account-withdrawal-implementation-phases.md) Slice 2 절 · [`system-contract-sot.md`](../../system-contract-sot.md) v1.8.48 행·§403(생산자 다섯).

## Scope

1. 커밋 4건 diff 내역이 보고 내용과 일치하는지(범위 외 변경 없음).
2. 배선 순서 주장 "인증→소유권→가드→quota"의 코드 실증.
3. 핀 셀 양방향 물림 — 변이 MS2-7(가드를 소유권 앞으로) 재적용 시 기명 재실패.
4. 세션 45 변이 표의 표본 검증(MS2-4·MS2-6 — 방향 각각 순서·under).
5. S9 경계 수정(6001)과 "재현 스크립트=살아있는 인프라" 주장.
6. 증분 산술(+9셀 = 순증 8 + 핀 1, +186 subtests = 초점 +173 + 타 파일 +13).
7. 전수 기준선 2963/1/4086 재현(호스트·test-mongo ON) 및 초점·tsc·문서 가드.
8. 기록 문서 정합성 — 세션 45 work_log·SoT v1.8.48 최종 행·HANDOFF·README 기준선.

## Methodology

환경: WSL2 호스트, `ai_writte_system-test-mongo-1` 실행 중(27020, `rs.status().myState` = 1 PRIMARY 실측), `PYTHONPATH=. python3 -m pytest`(pytest 9.0.2). 전수·초점 모두 `/tmp` 파일로 캡처 뒤 tail·grep 판독(파이프 삼킴 방지).

- 커밋 대조: `git show --stat`·`git show <sha> -- <path>`.
- 배선: `services/application/app/api/dependencies.py` 해당 줄 직독.
- 변이(트리 클린 게이트 `git status --short` 무출력 → Edit 변이 → 초점 실행 → `git checkout -- <path>` 복구 → 무출력 확인, 3회 전부):
  - MS2-7: `_REQUIRE_PROJECT_OWNER`에서 `require_active_user_for_write`를 `require_project_owner` **앞으로** 스왑.
  - MS2-4: `_REQUIRE_PROJECT_OWNER_BILLABLE`을 `[인증, 소유권, enforce_quota, 가드]`로 재배치.
  - MS2-6: `_REQUIRE_ADMIN`에서 가드 항 제거.
- 산술: `git worktree add --detach /tmp/attr_939 939d1e2` 뒤 양쪽 `--collect-only -q` 및 초점 실행(1600 subtests 측정), 종료 후 worktree 제거.
- 소요: 전수 1932초 — 세션 45의 1488초와 다르나 머신-로컬 값이라 비교 대상 아님(HANDOFF 기준선 줄의 경고).

## Findings

**전 주장 재측정 결과, 어긋난 것 없음.**

| 주장(세션 45·사용자 보고) | 검증자 실측 | 일치 |
|---|---|---|
| 배선 인증→소유권→가드→quota | `dependencies.py:382` `_REQUIRE_PROJECT_OWNER_BILLABLE = [*_REQUIRE_PROJECT_OWNER, enforce_quota]` — `_REQUIRE_PROJECT_OWNER`는 인증→소유권→가드 순(`dependencies.py:360`) | ✓ |
| SoT v1.8.48 행 순서 문장 정정(7e73233) | diff에서 "인증 → 소유권 → 탈퇴 가드 → quota"로 기입 확인. §403 생산자 셋→다섯 갱신 동반 | ✓ |
| 핀 셀 = MS2-7 무가드 폐쇄(19e422b) | `test_the_guard_sits_behind_the_ownership_boundary`가 없는 프로젝트 404·남의 프로젝트 403 `detail="forbidden"`까지 단정. MS2-7 재적용 시 **정확히 1 실패** — `AssertionError: 403 != 404`(`test_auth_api.py:235`), 나머지 151 passed / 1205 subtests. 오너 재현(79c065a)과 동일 결과 | ✓ |
| 변이 표 MS2-4 = 11 subtests | 재적용 시 **11 SUBFAILED**(`test_the_grace_guard_precedes_quota_on_every_billable_route` × 11 유료 경로) — 요약행 "11 failed"로도 보임(SUBFAILED 함정 해당 없음) | ✓ |
| 변이 표 MS2-6 = 17 실패 | 재적용 시 **17 실패**(`test_every_protected_operation_declares_the_grace_period_guard` × 17 admin op, SUBFAILED) | ✓ |
| S9 경계 6001(b4b1d7c) | `env.py:39 DRAFT_RAW_TEXT_MAX_CHARS = 6000`(오너 97bc149), 재현 스크립트는 `"가" * 6001`, `tests/test_final_save_analysis.py:18`이 이 파일을 import — "살아있는 인프라" 주장 실증. 전수에서 해당 셀 통과 | ✓ |
| 셀 +9 = 순증 8 + 핀 1 | 수집 2955(939d1e2 worktree)→2964(HEAD). def diff: **추가 10 − 제거 1** — 제거는 `test_neither_operation_declares_a_403`→`test_no_withdrawal_operation_declares_a_403` **몸 무변 개명**(diff에서 def 줄만 교체). 초점 272→281 = +9가 전체 +9와 정확히 같음 → 오너 세션 코드 커밋 +0도 산술로 증명 | ✓ |
| subtest +186 = +173 + 13 | 초점 1600(939d1e2)→1773(HEAD) = **+173** 실측. 전체 3900(종전 기준선, HANDOFF 이력)→4086(이번 실측) = +186 → 잔여 +13은 산술 잔차(세션 45가 파일별 재지 않았다고 명시한 부분 — 끝점 둘 다 실측되므로 성립) | ✓ |
| 전수 2963/1/4086 EXIT=0 | **2963 passed / 1 skipped / 4086 subtests · EXIT=0**(1932초). skip 1 = live Chroma — HANDOFF "skip 수 먼저 볼 것" 기준 양호 | ✓ |
| 초점 281/1773 | **281 passed / 1773 subtests · EXIT=0** | ✓ |
| 문서 가드 24/899 | **24 passed / 899 subtests**(이 기록 작성 전 HEAD) | ✓ |
| tsc rc=0 | `frontend/`에서 `npx tsc --noEmit` → **rc=0** | ✓ |
| 세션 45 기록·HANDOFF·README 기준선 | 세션 45 절 62줄 존재, 함정(§2)·변이 표(§3)·증분 귀속(§4) 수치 전부 위 실측과 일치. `README.md:104` "2,963 / 4,086"·`HANDOFF.md:65` 기준선 줄 정합. push 없음(`main...origin/main [ahead 25]`) | ✓ |
| 다음 작업 = Slice 3 파기 데몬 | `HANDOFF.md:237` "다음은 파기 데몬" + D4(원장 `target_user_id` 개명·마이그레이션) 선행 서술 확인 | ✓ |

## Issues / Risks

### Blocking (계약 의무)

없음 — 경계 행렬(계획서 Slice 2 검증 목록 전 항)이 기명 셀에 대응하고, 표본 변이 3종(방향 under·over·순서 각 1)이 전부 주장 수치로 재실패했다.

### Hardening (비차단)

1. **`core_sot/service.py:102` 주석 낡음** — "원고 본문 상한(`env.DRAFT_RAW_TEXT_MAX_CHARS` = **4000**)의 **3배**"라고 적혀 있으나 오너 97bc149(2026-09-08) 이후 실제 값은 6000이고 12000은 이제 2배다. 값 12000 자체는 오너 결정 그대로이며 `tests/test_scene_notes.py:13` 독스트링이 "배수는 2가 됐다·근거는 물려받지 않았다"로 이미 올바르게 문서화하고 있다 — **주석 한 줄만 뒤처진 것**(97bc149의 후폭풍이지 이 슬라이스 종결 커밋의 결함 아님). 주석은 가드가 못 보는 면이라 다음 사람이 `service.py` 주석만 읽으면 근거를 잘못 인용할 여지가 있다.
2. **검증 인덱스 단면 라벨 지연(등재 시 정리함)** — 이 검증 등재 전 `docs/verifications/README.md`의 "### 2026-09-07" 단면 아래에 2026-09-08 기록 둘(slice0·slice1)이 끼어 있었다. 가드(`test_every_verification_record_is_reachable_from_the_index`)는 도달성만 검사해 단면 날짜와 파일 날짜의 일치는 못 본다. 이 기록을 등재하며 09-08 단면을 분리해 바로잡았다 — 같은 지연이 다시 생기지 않게 하는 가드(단면 날짜 ↔ 디렉터리 날짜 일치)는 하드닝 후보다.

## Verdict

**합격**

- 종결 4커밋의 서술·수치가 전부 재측정으로 확정됐고(표 참조), 어긋난 주장 0건.
- 이 종결의 핵심 기여 두 개가 실증으로 닫혀 있다: ① MS2-7 무가드 발견(핀 셀 물림 재확인 — 오너 독립 재현과 동일한 1실패) ② S9 회귀(전수가 잡았고 경계 6001이 살아있는 인프라에서 통과).
- 증분 귀속 산술(+9셀·+186 subtests)이 worktree 양단 실측으로 성립 — "기준선 갱신은 셀을 더한 슬라이스의 몫" 규칙의 이행도 확인.

## Outstanding items

- 없음(차단 0). 하드닝 1건(위)은 주석 수정 한 줄로 닫을 수 있고 언제든 가능하다 — 오너 판단에 맡긴다.
- 다음 작업은 HANDOFF 순서대로 **Slice 3 파기 데몬**(D4 원장 개명·마이그레이션 선행).

## Reproduction

```bash
git status --short                        # 무출력 확인(변이 전 게이트)
# 초점·문서가드·전수(전수는 배경 권장, /tmp 캡처)
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py tests/test_application_api.py -q   # 281/1773
PYTHONPATH=. python3 -m pytest tests/test_docs_indexes.py tests/test_repo_hygiene.py -q  # 24/899
PYTHONPATH=. python3 -m pytest tests/ -q   # 2963 passed / 1 skipped / 4086 subtests
(cd frontend && npx tsc --noEmit)          # rc=0
# 변이 MS2-7: dependencies.py _REQUIRE_PROJECT_OWNER 에서 가드 Depends 를 소유권 앞으로 스왑
PYTHONPATH=. python3 -m pytest tests/test_auth_api.py -q   # 1 failed: 403 != 404 (핀 셀)
git checkout -- services/application/app/api/dependencies.py && git status --short  # 무출력
# 증분 산술: git worktree add --detach /tmp/attr_939 939d1e2 뒤 양쪽 collect-only(2955/2964)·초점(1600)
```
