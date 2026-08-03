# 독립 검증 — Phase 8 Slice 8.0 billable request 경계 (B1~B6=A)

- **날짜**: 2026-08-03
- **요청자**: 오너("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래? B1~B6 = 전부 A로 확정하고 시행까지 마쳤습니다")
- **검증자**: Claude Code(본 세션, 구현에 관여 안 함)
- **대상**: Slice 8.0 — 회원 사용량 1회 = 유료 endpoint 요청 1건으로의 분류 확정 + 전수 가드
- **정본 계약**: [`docs/plans/08-member-request-quota.md`](../../plans/08-member-request-quota.md) §4(슬라이스 8.0)·§5(불변식) + [`docs/plans/08-0-billable-request-boundary-decisions.md`](../../plans/08-0-billable-request-boundary-decisions.md) + [`docs/system-contract-sot.md`](../../system-contract-sot.md) **v1.7.83**
- **검증 대상 소스**: 커밋 `7c9d02b`(브리프)·`c490712`(분류 확정·가드·기록). HEAD `c490712`, 작업 트리 clean.
- **머신**: 베타(GTX 1060 3GB), test-mongo(rs-test, `127.0.0.1:27020`) ON.

## Scope

1. 분류 정본 코드 — `quota/billable_actions.py`(9개 유료 동작 + 조회 집합, counter/ledger/deduct 부재).
2. 전수 가드 — `tests/test_billable_actions.py`(8 cells)가 계약 요구 분기 전부를 양방향으로 다는가.
3. 정본↔코드 일치 — "`llm_call_scope`를 여는가"가 "provider를 부르는가"의 충실한 대리인인가(브리프 B4의 근거).
4. B2 관측 요구 의존성 — 브리프 §3.1이 참조하는 **기존** repair/scope 테스트가 실제로 단정하는가(빈 칸이면 B2 경계 붕괴).
5. 부모 계약 대조 — 슬라이스 8.0 인도물(표·전수 가드·브리프)과 §5 불변식(특히 L79·L83-84)의 충족·자기 모순.
6. 회귀 — 집중(8 cells) 및 전체 backend suite(test-mongo ON).
7. 기록 일관성 — B1=A 핵심 문장("원가 차이는 내부 BM에서 흡수")이 4곳(브리프 §0·모듈 docstring·SoT v1.7.83·CHANGELOG)에서 일치.

## Methodology

계약을 먼저 읽고 경계 매트릭스를 세운 뒤, 각 분기를 코드·테스트·실측로 채웠다. 작업자 주장은 전부 가설로 취급해 직접 재도출했다.

- 라우트 데코레이터 전수: `grep -rn "llm_call_scope("` (main.py 9 + generation_worker 1 + 정의 1 확인) + 동일 정규식으로 독립 파싱해 `opens_scope == BILLABLE_OPERATIONS` 검증.
- 집중 가드: `python3 -m pytest -q tests/test_billable_actions.py`.
- **뮤테이션(양방향, 백업+`diff` 원복)**:
  - M-under — 분류표에서 `context_search` 제거(under-strict) → 가드 실행 → 원복 → `git diff` 0라인 확인.
  - M-over — 무료 `GET …/writing/budget`을 유료로 오분류(over-strict, B4 위반) → 가드 실행 → 원복 → `git diff` 0라인 확인.
- 회귀: `python3 -m pytest -q tests/`(test-mongo ON, 778s).
- diff 범위: `git diff --stat 05286a6..c490712`로 counter/ledger/deduct 코드 누출 확인.
- 기존 테스트 본문 직독: `tests/test_llm_call_scope.py`·`tests/test_llm_call_sites.py`의 repair/scope 셀.

## Findings

### F1. 분류 정본 — 9개 유료 동작, counter/ledger/deduct 0줄

[`quota/billable_actions.py:40-91`](../../../services/application/app/quota/billable_actions.py#L40)는 `BillableAction` 리터럴 9개 + `BILLABLE_OPERATIONS` 조회 집합만 있고, 카운터·저장·차감 코드는 한 줄도 없다. `git diff --stat 05286a6..c490712`에서 코드 변경은 `billable_actions.py`(신규)·`tests/test_billable_actions.py`(신규)·`quota/__init__.py`(docstring 1줄)가 전부 — 시행 코드는 어디에도 없다. 핸드오프 조건("카운터 코드 0줄") 충족.

### F2. 정본↔코드 일치 — "scope 개방" 대리인은 현재 표면에서 충실하다

독립 스윕: `llm_call_scope(` 개방은 **main.py 9곳**(L3643·3991·4450·4726·4922·5018·5095·5233·5569) + **generation_worker.py 1곳**(L97) + 정의 1곳이 **전부**. 헬퍼 파일에서 scope를 여는 곳은 없다 → route가 scope를 인라인으로 열므로 "route 본문에 `llm_call_scope(`가 있다"는 provider 호출의 충실한 대리인이다.

동일 정규식(`_ROUTE`)으로 재파싱한 `opens_scope` 집합(9개)이 `BILLABLE_OPERATIONS`(9개)과 **정확히 동일**(`opens_scope - table == ∅`, `table - opens_scope == ∅`). retry endpoint는 파싱되며 scope를 열지 않는다. 총 75 operation(브리프 §1.1 주장과 일치).

### F3. 전수 가드 — 경계 매트릭스 빈 칸 없음, 양방향으로 문다

계약 요구 분기 → 셀 대응(전부 추적됨):

| 계약 분기 | 방향 | 셀 |
|---|---|---|
| scope 여는 route 전부 분류 | under-strict | `test_every_provider_calling_operation_is_classified`(집합 동치, [`:78-89`](../../../tests/test_billable_actions.py#L78)) |
| 무료 route는 scope 안 엶 | over-strict(B4) | `test_free_operations_never_open_a_provider_scope`([`:100-107`](../../../tests/test_billable_actions.py#L100)) + 위 동치 셀 |
| 분류 경로는 실존 operation | 오타/삭제 | `test_every_classified_action_is_a_live_operation`([`:91-98`](../../../tests/test_billable_actions.py#L91)) |
| action 리터럴 9개 고정 | 개명 | `test_action_literals_are_unique_and_pinned`([`:109-117`](../../../tests/test_billable_actions.py#L109)) |
| fan_out 표시(compare만) | B3 | `test_the_fan_out_marking_matches_the_measured_paths`([`:119-124`](../../../tests/test_billable_actions.py#L119)) |
| generation_worker 관측·비과금 | B5 | `test_the_generation_worker_is_observed_but_not_billed`([`:134-143`](../../../tests/test_billable_actions.py#L134)) |
| retry 비과금·scope 미개방 | B5 | `test_retrying_a_failed_generation_is_not_a_new_billable_request`([`:145-152`](../../../tests/test_billable_actions.py#L145)) |
| 정적 파싱==app.routes | 가드의 가드 | `test_the_static_parse_sees_exactly_the_registered_operations`([`:73-76`](../../../tests/test_billable_actions.py#L73)) |

**뮤테이션 실측(내가 직접)**:
- M-under(`context_search` 분류 삭제) → **3 failed**(동치·literals·free-scope). 백업 원복 후 `git diff` **0라인**.
- M-over(무료 `GET …/writing/budget` 유료 오분류) → **2 failed**(동치·literals). 백업 원복 후 `git diff` **0라인**.
- 원복 뒤 **8 passed / 75 subtests**로 green 복귀.

양방향 모두 확실히 문다. 작업자 뮤테이션 표(M1=3·M2=2)와 일치.

### F4. B2 관측 요구 — 기존 테스트에 의존, 의존처는 진짜 단정한다

브리프 §3.1은 repair 관측을 **기존** 셀에 위임한다. 본문 직독으로 의존처가 이름만이 아님을 확인:

- [`test_llm_call_scope.py:410-424`](../../../tests/test_llm_call_scope.py#L410) `test_a_repaired_extraction_leaves_two_records_not_one` — repair 시 `len(calls)==2`(둘 다 관측)·동일 call_site·동일 correlation·둘 다 SUCCESS. 짝 [`:426-433`](../../../tests/test_llm_call_scope.py#L426)이 over-strict(clean 호출은 1행)로 양방향.
- [`test_llm_call_sites.py:219-229`](../../../tests/test_llm_call_sites.py#L219) `test_a_repaired_verdict_leaves_two_records_both_successful` — 동일 구조(`len==2` + over-strict 짝 [`:231`](../../../tests/test_llm_call_sites.py#L231)).
- 보너스: [`test_llm_call_sites.py:481`](../../../tests/test_llm_call_sites.py#L481) `EndpointOpensAScopeTest`/`:872` `GenerationWorkerOpensAScopeTest` — 기존 9 endpoint가 scope를 열면 호출이 기록됨을 per-endpoint로 단정(docstring: "어느 endpoint에서든 `with`를 지우면 정확히 그 테스트가 실패한다").

B2 "repair 포함 내부 호출 전부 관측"은 빈 칸이 아니다. "알려진 공백 1건"(루프 내부 gate 레코드의 `decision`/`gate_quality_score` 부재, v1.7.47)은 호출 수가 아닌 파생 필드 공백이라 관측 요구와 무관 — 브리프 분류대로.

`generation_worker.py:97-98`은 `project_id=job.project_id, correlation_id=job.request_id`로 scope를 열어 같은 논리 요청으로 상관시킨다(직독 확인).

### F5. 부모 계약 대조 — 인도물·불변식 모두 충족, 자기 모순 없음

- [`08-member-request-quota.md:65`](../../plans/08-member-request-quota.md#L65) 슬라이스 8.0 인도물 "billable-action 표·호출 경로 전수 가드·decision brief" → 3종 전부 존재.
- [:79](../../plans/08-member-request-quota.md#L79) "새 AI 경로가 분류 없이 조용히 열리면 테스트가 실패" → B6 가드(M-under로 실증).
- [:80](../../plans/08-member-request-quota.md#L80) "재전송·worker 재처리를 같은 논리 요청을 여러 번 세지 않는다" → B5(worker·retry 표外, 테스트됨).
- [:83-84](../../plans/08-member-request-quota.md#L83) "`llm_call_audits`의 호출 수를 사용 횟수로 간주하거나 그 컬렉션을 과금 정본으로 재사용하지 않는다" → 본 슬라이스는 분류 정본을 **별도**(`billable_actions.py`)로 두어 위반하지 않으며, 브리프 B1=B 기각 근거로 이 불변식을 정확히 인용.

### F6. 회귀 — 작업자 주장과 정확히 일치

- 집중: **8 passed / 75 subtests**.
- 전체 backend(test-mongo ON): **1922 passed / 1 skipped / 1700 subtests**(778.36s, exit 0). 작업자 주장(1922/1/1700)과 정확히 일치. 알파 기준선 1911/4/1625 대비 Δ=+11 passed(신규 8 + 알파 skip 3건 베타 실행)·−3 skipped·+75 subtests. 남은 skip 1건은 호스트 구조적 live Chroma 셀. **회귀 0건.**

### F7. 기록 일관성 — B1 핵심 문장 4곳 일치

"동작별 원가 차이는 요금 단위로 옮기지 않고 내부 BM에서 흡수한다"가 ① 브리프 §0([`08-0…:22-26`](../../plans/08-0-billable-request-boundary-decisions.md#L22)) ② 모듈 docstring([`billable_actions.py:9-11`](../../../services/application/app/quota/billable_actions.py#L9)) ③ SoT v1.7.83([`system-contract-sot.md:36`](../../system-contract-sot.md#L36)) ④ CHANGELOG(줄 4)에 같은 뜻으로 일치. 가중치안(C)이 "유예"가 아니라 "채택 안 함"으로 명시되어 8.1+ 작업자가 오해할 여지가 없다. HANDOFF도 결정 완료·기준선 1922·Next Tasks 1(8.1)·"8.2 원장에 action 리터럴 필수"를 정확히 반영.

## Issues / Risks

### Blocking (계약 의무)

- **없음.** 경계 매트릭스에 빈 칸이 없고, 양방향 뮤테이션이 물며, 정본↔코드가 일치하고, 부모 불변식을 위반하지 않는다.

### Hardening recommendations (비차단)

- **H1 — B6 under-strict 보장은 "scope를 여는 route"까지지, "provider를 부르는 route"까지는 아니다.** [`llm_call_scope.py:209-215`](../../../services/application/app/observability/llm_call_scope.py#L209) `ObservedProvider.generate`는 scope가 None이면 **호출을 미기록 전달**한다(주석상 worker 진입점·script·직접 서비스 사용이 허용 대상). 즉 미래에 *provider를 부르되 scope를 안 여는* route가 열리면 그 route는 (a) 미관측이고 (b) `llm_call_scope(` 문자열이 없어 B6 가드에 잡히지 않아 미분류로 빠진다. 계약(B4)이 기준을 "scope 개방"으로 정했으므로 가드는 **계약에 충실**하지만, 브리프 "기계적으로 확인된다"/"강제"의 표현은 현재 9개에 대해 참이어도 *임의의 미래 route*에 대해 무조건 참은 아니다. 완화층이 있다: 기존 9 endpoint는 `EndpointOpensAScopeTest`가 per-endpoint로 scope 개방을 단정(삼중 잠금). 그러나 **"provider 호출은 반드시 scope 안에서"를 정적으로 강제하는 셀은 없다.** 이는 본 슬라이스가 만들거나 악화시킨 것이 아니라 기존 관측 불변식의 잔존 한계(관습 + known-list). 후속 강화 후보로만 남긴다: 예컨대 route 본문에서 scope 블록 밖의 provider 호출을 정적 탐지하거나, ObservedProvider의 scope-None 경로를 진단 메트릭으로 노출.
- **H2 — `test_the_generation_worker_is_observed_but_not_billed`는 worker 소스에 `llm_call_scope(` 문자열이 있는지만 본다.** "어떤 상관키로 scope를 여는가(같은 논리 요청 귀속)"는 이 셀 범위 밖이며, 본 검증이 [`generation_worker.py:97-98`](../../../services/application/app/writing/generation_worker.py#L97)에서 직독으로 참임은 확인했으나 셀로 못박혀 있지는 않다. `GenerationWorkerOpensAScopeTest`가 관측 단정을 이미 들고 있어 경계는 뚫리지 않는다(비차단).
- **H3 — "N일치" 일수가 가드에 잡히지 않아 39로 얼어 있다(검증 레코드 추가 과정에서 발견).** `docs/verifications/` 아래 실제 날짜 디렉토리는 **40개**(2026-06-24 ~ 2026-08-03)이지만, `docs/verifications/README.md`·`README.md`는 "39일치"로 적고 있다. 원인은 `VerificationCountClaimsTest`의 패턴이 `39일치 · (\d+)건`·`(\d+)건 / 39일치`에서 **"39일치"를 리터럴로 고정**하고 `(\d+)건`만 포착한다는 것 — 일수는 가드 대상이 아니라 누군가 40으로 고치면 오히려 이 패턴이 매칭에 실패해 테스트가 깨진다(D8-5b "링크는 잡는데 숫자는 못 잡는다"의 잔존 사례). 본 검증에서는 레코드 1건 추가로 건수를 211로 맞추면서 **일수는 이 레포 관행(테스트가 동결한 값)을 존중해 39로 유지**했다. 강화 후보: 패턴을 `(\d+)일치 · (\d+)건`으로 바꿔 일수도 디스크에서 유도하게 만들면 이런 부동(불변) 화가 사라진다. 본 슬라이스 비관여·비차단.
- **H4 — 최상위 `README.md`의 회귀 기준선·SoT 버전 표기가 슬라이스 8.0 이후 갱신 안 됨(비차단, 본 슬라이스가 만든 드리프트).** [`README.md:88`](../../../README.md#L88)이 "1,911 passed / 1,625 subtests", [`README.md:90`](../../../README.md#L90)이 "v1.7.82"로 되어 있으나 실제는 **1922 passed / 1700 subtests**·**v1.7.83**이다(HANDOFF·CHANGELOG·SoT는 이미 최신). 구현자가 README 표는 놓친 것으로 보인다. 가드가 없는 표기라 본 검증이 조용히 고치지 않고 표면화한다.

## Verdict

**합격(PASS).**

하중 이유: ① 분류 정본이 9개 유료 동작을 정확히 담고 시행 코드 0줄 ② "scope 개방" 대리인이 현재 표면에서 충실(독립 스윹 10개 개방 = 9 route + worker) ③ 경계 매트릭스에 빈 칸 없음, 뮤테이션 양방향 실증(M-under 3 fail·M-over 2 fail) ④ B2 관측 의존처가 진짜 단정 ⑤ 부모 §5 불변식 충족·자기 모순 없음 ⑥ 회귀 1922/1/1700, 회귀 0건 ⑦ B1 핵심 문장 4곳 일치. H1·H2는 모두 비차단 강화 후보(본 슬라이스 비관여).

## Outstanding items

- **test-mongo를 검증을 위해 올렸다**(`docker compose -f docker-compose.test.yml up -d`, `127.0.0.1:27020` PRIMARY). 작업자는 슬라이스 종료 시 내렸으므로, 검증 종료 후 본 검증자가 동일하게 내린다(아래 재현 단계 뒤). 내려 있는 것이 곧 본 검증의 종료 상태다.
- 커밋 `7c9d02b`·`c490712`는 push되지 않았다(오너 push 규칙).
- 분류는 확정됐고 시행은 없다 — 다음은 HANDOFF Next Tasks 1의 **8.1 정책 모델 브리프**(기간·기본 한도·override·무제한/정지·효력 시점).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# test-mongo replica set
docker compose -f docker-compose.test.yml up -d      # 127.0.0.1:27020, rs-test

# 1. 집중 가드
python3 -m pytest -q tests/test_billable_actions.py   # 8 passed / 75 subtests

# 2. 전체 회귀
python3 -m pytest -q tests/                            # 1922 passed / 1 skipped / 1700 subtests

# 3. 양방향 뮤테이션(백업 후 원복, diff로 확인)
BA=services/application/app/quota/billable_actions.py
cp "$BA" /tmp/ba.bak
# under-strict: context_search 분류 삭제 → 3 failed → cp /tmp/ba.bak "$BA"
# over-strict : GET …/writing/budget 유료 오분류 추가 → 2 failed → cp /tmp/ba.bak "$BA"
git diff -- "$BA" | wc -l                              # 0

# 4. 독립 스윕: scope 개방이 9 route + worker 뿐인지
grep -rn "llm_call_scope(" --include='*.py' services | grep -v test_

# 5. test-mongo 내리기(작업자 종료 상태로 복원)
docker compose -f docker-compose.test.yml down
```
