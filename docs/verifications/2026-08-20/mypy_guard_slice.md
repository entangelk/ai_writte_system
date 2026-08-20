# mypy 가드 슬라이스(축 ②) — 독립 검증

## Subject metadata

- **날짜**: 2026-08-20 (베타)
- **요청자**: 오너 — *"작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?"*
- **검증자**: 이 세션(구현 세션과 별개 — `0b1c6f3` 을 만들지 않았다)
- **대상 슬라이스**: 축 ② — 스크립트 부패 가드 결정 **1=B(mypy 단독) · 1-b=가(requirements-dev + 미설치 시 실패)** 의 구현
- **대상 커밋**: `3610fc3`(브리프 확정·docs) · `0b1c6f3`(구현) · `f09097e`(기록·docs)
- **정본 참조**: [`docs/plans/script-rot-guard-decisions.md`](../../plans/script-rot-guard-decisions.md) §★확정(결정 1·1-b) · §착수 조건 1~5("전부 이행됨"이라 적힌 체크리스트) · §산출물(**"억제 주석 0건이며 그것을 잠그는 셀이 따로 있다"**)
- **작업 트리 상태**: HEAD `f09097e`, clean — 검증 시작·뮤테이션 사이마다·종료 시점 `git status --short` 공백 확인

## Scope

1. **착수 조건 1~5의 이행과 셀 매핑(경계 행렬)** — 각 조건이 어느 셀에 잠겼는지 전수 대조.
2. **뮤테이션 재현** — 구현자 보고 7종(M1~M7)을 같은 diff 로 재실행 + **검증자 자체 공격 4종(M8~M11, 억제·범위 우회 벡터)**.
3. **정정 둘의 재도출** — ① 88→111(전체 에러 수) ② 1회차 `12 skipped`(복제셋 미준비).
4. **전수 회귀** `2296/1/2519` 재현(예열 후).
5. **구현자가 "볼 만한 축"으로 남긴 셋** — 좁힘 집합의 표적 커버 · `accept.py` raise 재발생의 호출자 계약 · `lock_mongo` `RuntimeError` 의 8.3 정책 적합성.

## Methodology

- 산출물 읽기: [`requirements-dev.txt`](../../../requirements-dev.txt) · [`mypy.ini`](../../../mypy.ini) · [`tests/test_typecheck.py`](../../../tests/test_typecheck.py) 전문, `git show 0b1c6f3` 의 프로덕션 5파일 diff.
- 포커스: `python3 -m pytest tests/test_typecheck.py tests/test_quota_lock_mongo.py tests/test_writing_accept.py -q` → **88 passed / 22 subtests**.
- 뮤테이션 11종: 트리가 clean 이므로 `git checkout -- <path>` 분기. **뮤테이션 사이마다 `git status --short` 공백 확인(11회 전부).** diff 는 아래 표에 문언 그대로.
- 미설치 거동: `python3 -m venv /tmp/venv_nomypy` 후 그 파이썬으로 `tests/test_typecheck.py` 를 직접 실행(가드 파일은 stdlib 만 import 하므로 pytest 없이 돈다).
- 전체 에러 수 재도출: `git archive 3610fc3` → `/tmp/prefix_snapshot` 에 압출(구현 직전 상태, 트리 불변) 후 중립 설정(`[mypy] mypy_path=. ignore_missing_imports=True`)으로 `services scripts` 측정. 수정 후 트리에서 동일 설정 측정.
- 전수: test-mongo `up -d` 후 **복제셋 `rs-test` primary 도달을 `hello` 로 확인한 뒤**(정정 ②의 함정 회피) `python3 -m pytest -q`.
- 프로덕션 이미지 순수성: `services/{application,embedding,llm_gateway}/Dockerfile` 이 `pip install` 하는 파일 전수 확인 + requirements 파일 전수 탐색(`find`).

## Findings

### 1. 착수 조건 1~5 — 전부 이행, 전부 셀에 매핑됨

| 조건(정본) | 이행 | 잠근 셀 |
|---|---|---|
| 1. `requirements-dev.txt` 신설, 프로덕션에 안 섞기 | ✓ mypy 단일([`requirements-dev.txt:10`](../../../requirements-dev.txt#L10) `mypy>=2.3,<3` — 실측 2.3.1) | `test_the_dev_requirements_file_declares_it_and_production_does_not`(subtest 3종) |
| 2. 좁힘 설정 고정(`call-arg`+`misc`, `misc` 함정) | ✓ [`mypy.ini:43-51`](../../../mypy.ini#L43) disable 8종에 `misc` 없음 | `test_disabling_misc_would_hide_the_target_defect` ②ini 문언 단정 |
| 3. 5건 처리(잠재 결함 2는 회귀 셀 먼저) | ✓ 프로덕션 5파일 38줄(stat 합 일치). `calibrate_…` 는 시그니처만(`sys.path` 부트스트랩 미손대 — 결정 4=A 경계 준수, diff 로 확인) | accept 2셀 · lock 1셀(+기존 `test_a_conflict_that_never_resolves_fails_closed`[:283] 이 over-strict 담당) |
| 4. 미설치 시 실패 + 메시지가 설치법 | ✓ **실증**: mypy 없는 venv 에서 `Ran 7 tests … FAILED (failures=3)`, 가용성 셀 메시지가 `pip install -r requirements-dev.txt` 를 말함 | `test_mypy_is_installed_and_says_how_to_get_it_when_it_is_not` |
| 5. 양방향 3종 | ✓ 아래 뮤테이션 표 | 탐침 3셀 |

- **억제 주석 0건**: `grep -rn "type: ignore" services/ scripts/` → 0건 ✓. 단 **그 잠금의 사각지대는 Issues B1.**

### 2. 뮤테이션 11종 — 구현자 보고 7종은 전부 그대로 재현, 자체 4종 중 4종이 새 구멍

| # | 적용한 diff | file:line | 결과 |
|---|---|---|---|
| M1 | `if replay is None: raise` 블록 제거(원 결함) | `accept.py:134` | ✅ `test_an_unreadable_receipt_fails_closed_instead_of_type_error` 재실패(1 failed) |
| M2 | `if replay is None:` → `if True:`(과잉교정) | `accept.py:137` | ✅ `test_a_readable_receipt_still_converges_through_the_same_branch` 재실패 |
| M3 | `if conflict is None:` 블록 9줄 제거 | `lock_mongo.py:99` | ✅ `test_zero_attempts_fails_closed_with_a_stated_reason` 재실패 |
| M4 | `base_url=` 제거(위치 인자 복원) | `calibrate_…:20` | ✅ **저장소 초록 셀** 재실패 / 탐침 셀은 초록(독립성 확인 — 비대칭이 주장 그대로) |
| M5 | disable 목록에 `call-arg` 추가 | `mypy.ini` | ✅ 탐침 under-strict 셀 재실패 / **저장소 초록 셀은 여전히 초록**(주장된 비대칭 재현) |
| M6 | disable 목록에 `misc` 추가 | `mypy.ini` | ✅ misc-함정 셀 + 탐침 셀 2개 재실패 |
| M7 | 위치 인자 복원 + `  # type: ignore[call-arg]` | `calibrate_…:20` | ✅ **mypy 자체는 통과**(저장소 초록 셀 초록) / 억제 금지 셀 재실패 |
| **M8** | 위치 인자 복원 + `  #type:ignore[call-arg]`(**공백 없음**) | `calibrate_…:20` | ❌ **7셀 전부 초록, 결함 생존** — mypy 는 무공백 주석도 억제로 받고, 셀의 `"type: ignore" in line` 문자열 매칭은 못 본다 |
| **M9** | 파일 1행에 `# mypy: ignore-errors` 프라그마 + 위치 인자 복원 | `calibrate_…:1` | ❌ **7셀 전부 초록, 결함 생존** — 파일 단위 억제 벡터, 문자열 매칭 사각 |
| **M10** | mypy.ini 말미에 `[mypy-scripts.calibrate_character_identity_threshold]\nignore_errors = True` + 위치 인자 복원 | `mypy.ini` | ❌ **7셀 전부 초록, 결함 생존** — 설정 단위 억제("억제 목록")를 검사하는 셀 없음 |
| **M11** | `files = services, scripts` → `files = services` + 위치 인자 복원 | `mypy.ini:28` | ❌ **7셀 전부 초록, 결함 생존** — 범위 축소를 잠그는 셀 없음 |

- M4~M7 의 셀 페어링은 구현자 표와 한 치도 다르지 않게 재현됐다.
- **M8~M11 은 이 검증의 새 결과다.** 넷 전부 "요약줄 초록 + 표적 결함 생존" 이라는, 이 슬라이스가 막으려던 바로 그 상태를 만든다.

### 3. 정정 둘 — 둘 다 실측으로 뒷받침됨

- **① 88 → 111**: 구현 직전 커밋(`3610fc3`) 스냅샷을 이 호스트(런타임 의존 설치됨)에서 중립 설정으로 측정 → **`Found 111 errors in 40 files (checked 193 source files)`** — 정정값과 정확히 일치. 수정 후 현재 트리에서 같은 측정 → 102/38(5건 직접 수정 + 같은 라인의 타 코드 에러 4건 소거, 111−9=102 로 정합). **좁힌 설정**은 현재 트리에서 `Success: no issues found in 193 source files` ✓("193 source files" 문언도 일치).
- **② 12 skipped**: 예열 후 이 트리에서 **`2296 passed / 1 skipped / 2519 subtests`(899.64s)** — 구현자 보고와 수치 완전 일치. 냉시작 `12 skipped` 상태 자체는 재현하지 않았으나(전수 1회 추가 비용) — (a) 산술이 맞는다(2285+11=2296, 12−11=1), (b) 규약이 실재한다([`test_core_sot_mongo.py:3-13`](../../../tests/test_core_sot_mongo.py#L3): 도달 불가 시 skip, 복제셋 아닌 경우 조용한 skip), (c) skip 1건(live Chroma) 경계도 이번 실측으로 확인했다.

### 4. 구현자가 남긴 "볼 만한 축" 셋

- **accept 의 `raise` 재발생**: `DuplicateWritingAcceptReceipt` 를 HTTP 층에서 매핑하는 곳은 없다(grep — 정의·발생지·accept 의 except 절뿐). 수정 전 `TypeError` 도 수정 후 도메인 예외도 **둘 다 500** — HTTP 계약은 불변이고 실패의 가독성·재시도 판단 가능성만 개선됐다. 위반 아님.
- **lock 의 `RuntimeError`**: 인접 fail-closed 경로(`raise conflict`)도 raw `DuplicateKeyError`(비-택소노미)를 그대로 올리며, 이 분기는 `CLAIM_ATTEMPTS=3`([`lock_mongo.py:48`](../../../services/application/app/quota/lock_mongo.py#L48)) 상수 하에 도달 불가다. 8.3 상태코드 정책과의 충돌 없음.
- **`_headroom_rows` 호출자 전수**: unpack 1곳(`_thin_headroom`) + `len()` 2곳([`kpi.py:256,282`](../../../services/application/app/observability/kpi.py#L256)) — 튜플 반환 전환이 전 호출자에서 안전함을 확인.

### 5. 기록·인덱스 충실성

- 프로덕션 이미지 순수성: 3개 Dockerfile 모두 `services/*/requirements.txt` 만 설치( requirements-dev 는 어떤 이미지에도 안 들어간다) — 셀의 3파일 검사보다 한 층 깊은 배선까지 확인.
- `f09097e`: CHANGELOG 1행 · HANDOFF(기준선 갱신 + 함정 2건 + 선행조건 문언 + 미검증 목록) 반영 — 보고 내용과 일치.
- 프로덕션 델타 "5파일 38줄" — `git show --stat` 합계 일치(2+4+14+8+10).

## Issues / Risks

### Blocking

**B1. 억제 잠금 셀이 실제 우회 벡터를 못 본다 — 계약 산출물 문언("억제 주석 0건이며 그것을 잠그는 셀이 따로 있다")이 잠금의 실제 범위보다 넓다.**

- `test_no_suppression_comment_carries_the_guard`([`test_typecheck.py:87-96`](../../../tests/test_typecheck.py#L87))는 `services/`·`scripts/` 의 `.py` 행에서 문자열 `"type: ignore"` 를 찾는다. **M8(무공백 `#type:ignore[call-arg]`)·M9(`# mypy: ignore-errors` 프라그마)·M10(mypy.ini 퍼모듈 `ignore_errors = True`)은 전부 mypy 가 억제로 받아들이는 벡터인데 셋 다 이 검사를 통과한다** — 그리고 그 상태에서 저장소는 7셀 전부 초록인 채 표적 결함이 살아 있다(위 표).
- M8 은 "억제 **주석**" 계약 문언을 정면으로 반박한다(무공백 주석도 주석이다). M10 은 브리프가 스스로 경고한 **"억제 목록이 부채가 된다"** 의 정확한 형태다 — 임시 조용화를 위해 per-module 섹션 하나를 넣는 길이 아무 셀에 안 걸린다.
- 폐쇄 방향(작다): 검사 정규식을 `#\s*type:\s*ignore` 로 넓히고 + `# mypy: ignore-errors` 프라그마 + `mypy.ini` 전문에서 `ignore_errors`·`disable_error_code` 신규 섹션·`files`/`exclude` 행을 잠그는 셀 하나. **또는** 산출물 문언·셀 docstring 을 실제 잠긴 범위(정준형 `# type: ignore` 만)로 좁혀 기록.

### Hardening recommendations (비차단)

- **H1(M11)**. `files = services, scripts` 범위 축소에 7셀 전부 묵문이다. 정본 §후속 고려가 "가드 셀의 범위를 `scripts/` 로 좁히지 말 것" 이라 적지만(반대 방향 서술) 범위 무결성은 셀로 잠긴 적이 없다. B1 폐쇄에 `files` 행 단정을 얹으면 같이 닫힌다.
- **H2**. mypy 미설치 환경에서 7셀 중 4셀이 **공허하게 초록**이다(빈 출력에 `assertNotIn` 이 통과). 스위트 전체는 가용성 셀이 빨갛게 만들므로 실해는 없으나, 셀 단독으로는 "돌지 않아서 통과" 와 "진짜 통과" 를 구분 못 한다.
- **H3**. `phase6_gate_finding_live_smoke.py:282` 수정이 비-문자열 `check` 값을 조용히 버린다(종전엔 `None` 이 리스트에 남았다). live smoke 라 셀이 없는 것이 설계이고 브리프 분류("경미")와 부합 — 행동 변화만 기록해 둔다.

## Verdict

**조건부 합격** — 억제 잠금 셀의 우회 벡터 셋(무공백 `#type:ignore` · `# mypy: ignore-errors` 프라그마 · mypy.ini 퍼모듈 `ignore_errors`)을 닫거나, 산출물 문언을 실제 잠긴 범위로 좁혀 기록할 것.

- 착수 조건 1~5는 전부 이행됐고 구현자가 보고한 뮤테이션 7종은 전부 독립 재현됐으며(페어링 포함), 정정 둘·전수 회귀 `2296/1/2519`·미설치 거동까지 전부 실측과 일치한다. **이 슬라이스의 핵심 주장 — "한 달 넘게 못 잡던 결함을 이제 저장소가 스스로 잡는다"(M4) — 은 참이다.**
- 조건이 B1 하나인 이유: 이 슬라이스가 세운 "무엇을 보고 있다를 단정하는 셀" 이 그 자신의 주장("억제로 초록을 만들지 않는다")에 대해 4개 벡터 중 1개만 실제로 보고 있다. 이 저장소 판정 선례(2026-08-15 B1 — "잠그는 셀 0건" 이 조건부 합격)와 같은 부류·같은 무게다.

## 조건 폐쇄 — **B1·H1 둘 다 닫힘 (2026-08-20, 구현 세션 `5182cad`)**

> 이 절은 **검증자가 아니라 구현 세션이 나중에 추가한 것**이다. 위 Findings·Verdict 는
> 검증 시점 그대로 두었다 — 판정을 사후에 고쳐 쓰면 기록이 아니라 변명이 된다.

**폐쇄 방식은 검증자가 제안한 둘 중 첫째다** — *"산출물 문언을 실제 잠긴 범위로 좁혀
기록" * 하지 않고 **검사를 문언에 맞춰 넓혔다.** 지적의 핵심이 *"계약 문언이 실제 잠금
범위보다 넓다"* 였으므로, 문언을 줄이면 **계약이 약해진 채 합의된다.** 이 슬라이스가
막으려는 것이 정확히 그 모양이라 반대 방향을 골랐다.

**벡터를 하나씩 막지 않았다.** M8~M11 은 넷이지만 같은 병의 네 얼굴이고, 다섯째·여섯째가
있을 것이 뻔하다(예: `exclude`, `follow_imports = skip`). 그래서 **허용된 것만 남기는**
형태로 바꿨다.

| | 폐쇄 수단 | 잠근 셀 |
|---|---|---|
| M8 무공백 `#type:ignore` | 정규식 `#\s*(type:\s*ignore\|mypy:)` | `test_no_suppression_comment_carries_the_guard` |
| M9 `# mypy: ignore-errors` 프라그마 | 같은 정규식 | 〃 |
| M10 퍼모듈 `ignore_errors` | **섹션은 `[mypy]` 하나** · **키는 넷만** 허용 | `test_the_config_cannot_be_quietly_weakened`(신규) |
| M11 `files` 범위 축소 | `files` 가 정확히 `{services, scripts}` | 〃 |
| (선제) `exclude`·`follow_imports` 등 | 허용 키 밖은 전부 실패 | 〃 |

**★ disable 목록은 부분집합만 단정한다 — 이것이 과잉교정 방지의 핵심이다.** 코드를
**더하는 것**(약화)은 실패하지만 **빼는 것**(강화·브리프 §후속 고려의 확장 트리거)은
자유다. 고정 일치로 잠갔으면 **이 셀이 확장 트리거 자체를 막았을 것**이다.

**재검(구현 세션 자체 실행, 트리 clean 분기)**

| # | 뮤테이션 | 결과 |
|---|---|---|
| M8 | 위치 인자 + `#type:ignore[call-arg]` | ✅ `test_no_suppression_comment_carries_the_guard` 재실패 |
| M9 | 위치 인자 + 1행 `# mypy: ignore-errors` | ✅ 같은 셀 재실패 |
| M10 | 위치 인자 + 퍼모듈 `ignore_errors = True` | ✅ `test_the_config_cannot_be_quietly_weakened` 재실패 |
| M11 | 위치 인자 + `files = services` | ✅ 같은 셀 재실패 |
| **M12** | `arg-type` 를 disable 목록에서 **제거**(= 가드 강화) | ✅ **설정 셀은 통과**하고 저장소 초록 셀만 실패 — 넓히기를 막지 않는다 |
| **M13** | `# mypy 가 이 줄을 잡았다 … type ignore 는 쓰지 않는다` (억제 아닌 평범한 주석) | ✅ **8 passed** — 오탐 없음 |

**M12·M13 은 검증자 목록에 없던 과잉교정 점검이다.** 억제 검사를 넓히면 **정상적인
강화와 평범한 주석을 무는 것**이 새 실패 모양이 되므로, 좁히는 방향만 재면 반쪽이다.

## Outstanding items

- ~~**B1 조건 폐쇄 대기**~~ — **닫혔다(2026-08-20 `5182cad`)**. 위 §조건 폐쇄 참조. 셀 1개 확장이 아니라 **셀 1개 확장 + 신규 셀 1개**가 됐다(주석 축과 설정 축이 다른 검사라 한 셀에 묶으면 무엇이 깨졌는지 안 보인다). **H1(M11)도 같은 셀로 함께 닫혔다.**
- **미검증 잔여 = 1커밋**(`cd1d82d`, 2026-08-16) — 이 기록으로 `0b1c6f3`(과 docs 셋 `3610fc3`·`f09097e`)은 커버됐다.
- 다음 전수 회귀 기대값: 이 기록 등재로 판정 열 전수 subtest +1 → **`2296 passed / 1 skipped / 2520 subtests`**(코드 무관 — 검증 기록 수가 subtest 를 올리는 자리, HANDOFF 규칙).

## Reproduction

```bash
git status --short                       # 공백이어야 함
python3 -m pytest tests/test_typecheck.py tests/test_quota_lock_mongo.py tests/test_writing_accept.py -q
# → 88 passed / 22 subtests

# 뮤테이션(트리 clean 분기 — 적용 → 셀 구동 → git checkout -- <path> → status 공백 확인)
# M4: calibrate:20 위치 인자 복원      → 저장소 초록 셀 1 failed
# M5: mypy.ini disable 에 call-arg 추가 → 탐침 셀 1 failed(저장소 초록 셀은 통과)
# M7: 위치 인자 + "# type: ignore[call-arg]" → 억제 금지 셀 1 failed(mypy 자체는 통과)
# M8: 위치 인자 + "#type:ignore[call-arg]"(공백 없음) → 7셀 전부 통과(구멍)
# M10: mypy.ini 말미 [mypy-scripts.calibrate_character_identity_threshold] ignore_errors = True + 위치 인자 → 7셀 전부 통과(구멍)

# 미설치 거동
python3 -m venv /tmp/venv_nomypy && /tmp/venv_nomypy/bin/python tests/test_typecheck.py
# → FAILED (failures=3), 메시지가 pip install -r requirements-dev.txt 를 말함

# 전체 에러 수(정정 ①)
git archive 3610fc3 | tar -x -C /tmp/prefix_snapshot && cd /tmp/prefix_snapshot
printf '[mypy]\nmypy_path = .\nignore_missing_imports = True\n' > /tmp/mypy_neutral.ini
python3 -m mypy --config-file /tmp/mypy_neutral.ini services scripts | tail -1   # Found 111 errors in 40 files

# 전수(예열 후 — up -d 직후가 아니라 hello 로 primary 확인 뒤)
docker compose -f docker-compose.test.yml up -d   # …replica set ready 확인…
python3 -m pytest -q                               # 2296 passed / 1 skipped / 2519 subtests
```
