# mypy 가드 조건 폐쇄(5182cad) — 독립 재검

## Subject metadata

- **날짜**: 2026-08-20 (베타)
- **요청자**: 오너 — *"작업 AI가 보강한다음 미검증 = 2커밋: cd1d82d(08-16) · 5182cad(조건 폐쇄, 자기 검증뿐). 후자에서 볼 만한 축은 허용 키 집합이 과소한가 — [mypy]에 나중에 정당하게 필요한 키를 못 넣게 되는 방향의 과잉교정입니다. 이걸 요청했는데 한번 해볼래?"*
- **검증자**: 이 세션(첫 검증과 같은 세션 — 폐쇄 커밋 `5182cad` 를 만들지 않았다)
- **대상 슬라이스**: [`mypy_guard_slice.md`](mypy_guard_slice.md) **조건부 합격의 조건(B1)+H1 폐쇄** — 억제·범위 우회 벡터 넷의 잠금
- **대상 커밋**: `5182cad`(코드 — `tests/test_typecheck.py` 유일) · `0741a45`·`d3cc557`(기록·정본 문언 정정)
- **정본 참조**: [`docs/plans/script-rot-guard-decisions.md`](../../plans/script-rot-guard-decisions.md) §착수 조건 말미 **"조용해지는 길을 무엇으로 잠갔는가"**(이번에 다시 쓴 문언) · §후속 고려(확장 트리거)
- **작업 트리 상태**: HEAD `d3cc557`, clean — 뮤테이션 사이마다 `git status --short` 공백 확인

## Scope

1. **폐쇄 실증** — M8~M11(검증자 자체 공격 4종)을 같은 diff 로 재실행해 새 잠금이 무는지.
2. **원 잠금 보존** — 폐쇄가 기존 7셀을 무디게 하지 않았는지(M4~M7 재실행).
3. **과잉교정 방향 재현** — 구현 세션이 자체 추가한 M12(강화 자유)·M13(평범한 주석 오탐 0).
4. **★ 오너 지목 축 — 허용 키 집합 과소**: 정당한 키·범위 확장이 잡히는가(O1·O2), 잡힌다면 그 실패가 무엇이라고 말하는가.
5. **전수 기대치** `2297/1/2520`(HANDOFF 예고값) 실측 확인 · 기록 충실성(I-7 해시 사고 잔류).

M1~M3(accept·lock)은 재판정하지 않았다 — 폐쇄 커밋이 `tests/test_typecheck.py` 한 파일만 고쳐 그 영역을 안 건드렸기 때문이다(첫 검증의 결론이 그대로 이어진다).

## Methodology

- 포커스: `python3 -m pytest tests/test_typecheck.py -q` → **8 passed / 3 subtests**(7→8 셀 주장 일치).
- 뮤테이션 10종(M4~M13): 트리 clean 분기(`git checkout -- <path>`), 사이마다 status 공백 확인. diff 는 첫 검증 기록과 동일 문언.
- **O1(축)**: `mypy.ini` `[mypy]` 에 `warn_unused_ignores = True` 추가 — **가드를 강화하는 키**(쓰이지 않는 억제 주석을 경고한다; 저장소에 억제가 0개라 출력 불변) — 후 설정 셀·저장소 초록 셀 양쪽 구동.
- **O2(축)**: `files = services, scripts, frontend`(`frontend/` 에 `.py` 0개 = 검사 대상 불변) 후 동일.
- 전수: `hello` 로 `rs-test` primary 확인 후 `python3 -m pytest -q`.
- I-7 잔류: `grep -rn "4bd1a3d" --include="*.md"` — 남은 2건이 사고 서술 자체인지 확인.

## Findings

### 1. 폐쇄는 실재한다 — M8~M11 전부 물고, 원 잠금도 무뎌지지 않았다

| # | 뮤테이션 | 결과 |
|---|---|---|
| M8 | 위치 인자 + `#type:ignore[call-arg]`(공백 없음) | ✅ `test_no_suppression_comment_carries_the_guard` 재실패 |
| M9 | 위치 인자 + 1행 `# mypy: ignore-errors` | ✅ 같은 셀 재실패 |
| M10 | 위치 인자 + `[mypy-scripts.…] ignore_errors = True` | ✅ `test_the_config_cannot_be_quietly_weakened`(신규) 재실패 |
| M11 | 위치 인자 + `files = services` | ✅ 같은 셀 재실패 |
| M4 | 위치 인자 복원 | ✅ 저장소 초록 셀 재실패(원 잠금 보존) |
| M5 | disable 에 `call-arg` 추가 | ✅ **탐침 + 설정 셀 2개** 재실패(폐쉬 전엔 탐침 1개 — 방어 심화) |
| M6 | disable 에 `misc` 추가 | ✅ **함정 + 설정 셀 2개** 재실패(〃) |
| M7 | 위치 인자 + `# type: ignore[call-arg]` | ✅ 억제 셀 재실패 |
| M12 | disable 에서 `arg-type` **제거**(강화) | ✅ **설정 셀 통과** · 저장소 초록 셀만 실패(140.99s — 50건급 `arg-type` 드러남) = 확장 트리거 안 막힘 |
| M13 | `# mypy 가 … type ignore 는 쓰지 않는다`(평범한 주석) | ✅ 억제 셀 통과 — 오탐 0 |

구현 세션 재검 표(6종)와 결과가 전부 일치한다. **B1·H1 은 닫혔다.**

### 2. ★ 오너 지목 축 — "허용 키 집합이 과소한가" 는 **사실이다**(단 계약 위반은 아니다)

**O1 — `warn_unused_ignores = True` 를 넣으면:**

- **저장소 초록 셀은 그대로 통과**(76.94s) — 이 키는 조용해지는 길이 아니라 **역방향(억제 잔여물 경고)** 이고, 억제가 0개라 출력도 불변이다. **불령임이 실증됐다.**
- 그런데 **설정 셀은 실패**하며 이렇게 말한다([`test_typecheck.py:151`](../../../tests/test_typecheck.py#L151)):

> `AssertionError: {'files', 'disable_error_code', 'mypy_path', 'warn_unused_ignores', 'ignore_missing_imports'} not less than or equal to frozenset({…}) : 이 키들 밖은 전부 조용해지는 길이다(ignore_errors·exclude·follow_imports 등)`

**"이 키들 밖은 전부 조용해지는 길이다" 는 거짓 보편문이다.** `warn_unused_ignores`(강화) · `python_version` · `cache_dir` · `plugins`(예: pydantic) · `explicit_package_bases` 는 조용해지는 길이 아니다. `_ALLOWED_KEYS` 주석([`test_typecheck.py:43`](../../../tests/test_typecheck.py#L43))이 같은 거짓 문언을 갖고 있다.

**O2 — `files` 에 `frontend` 추가(불령 확대):** 설정 셀의 **등가 단정**이 거부한다. 메시지는 "범위를 줄이지 않는다" 인데 **줄이지도 않았다 — 늘렸다.** (같은 트리에서 저장소 초록 셀도 실패했으나 이는 mypy 자신이 `There are no .py[i] files in directory 'frontend'` 를 내는 것 — 설정 셀의 거부와는 무관하다.)

**심각도 판정**: 화이트리스트 트립와이어 설계 자체는 정당하다 — mypy 의 조용해지는 키는 셀 수 없이 많아(`ignore_errors`·`exclude`·`follow_imports = skip`·`no_warn_unused_ignores`…) 하나씩 막으면 "다섯째 벡터" 가 반드시 생기고, 허용집합 방식만이 그 클래스를 닫는다. 정본(결정 문서)도 이번에 다시 쓴 문언에서 **정확하게** 서술했다("키는 넷만"). **계약이 약속한 확장 자유(에러 코드 빼기 = M12)는 열려 있음을 실증했다.** 남는 결함은 **셀 안의 세 문언**(주석·메시지 2)이 잠금의 실제 성격(억제 키와 무해 키를 구분하지 않는 트립와이어)보다 넓게 주장한다는 것 — 첫 검증 B1("계약 문언이 잠금보다 넓다")과 같은 병의 축소판이되, 이번엔 정본이 아니라 테스트 파일 안에 있다. 완화 사실도 함께 적는다: **단정 출력 자체가 어느 키가 문제인지 정확히 보여주므로** 오해의 지속 시간은 짧다.

### 3. 전수 기대치 일치 · 기록 충실성

- 전수(예열 후): **`2297 passed / 1 skipped / 2520 subtests`(1429.44s)** — HANDOFF:75 예고값(`셀 +1` = 설정 셀, `subtest +1` = 첫 검증 기록)과 정확히 일치. skip 1 = live Chroma.
- I-7(해시 사고): `4bd1a3d` 잔류 참조 0건 — 남은 2건은 사고 서술 자체(`work_log.md:247,251`).
- 구현 세션이 첫 검증 기록에 단 §조건 폐쇄 추기를 달았고 **원 판정은 고쳐 쓰지 않았다** — 이 재검이 승격을 담당한다(아래 Verdict).

## Issues / Risks

### Blocking

없음.

### Hardening recommendations (비차단)

- **H4(축의 실체)**. `_ALLOWED_KEYS` 주석·설정 셀 실패 메시지의 **"이 키들 밖은 전부 조용해지는 길이다"** 를 트립와이어에 맞는 문언으로 고칠 것 — 예: *"허용 목록 밖 키는 일단 실패한다(억제 키도, 무해한 키도). 정당한 키면 `_ALLOWED_KEYS` 에 의식적으로 추가한다."* 결정 1-b② 의 같은 논리다(*"실패가 원인을 안 말하면 다음 사람이 셀을 지운다"*) — 지금 메시지는 원인을 **거짓으로** 말한다.
- **H5**. `files` 등가 단정은 **확대도 거부**하는데 메시지는 "범위를 줄이지 않는다" 만 말한다. 확대가 정당해지는 날(예: `tests/` 편입 트리거) 이 셀을 고치고 감 — 그 사실을 메시지에 한 줄로 적어 두면 좋다.

## Verdict

**합격** — B1·H1 폐쇄가 실증됐고(재검 10종 전부 의도대로), 오너 지목 축(허용 키 과소)은 실재하나 **계약 위반이 아닌 문언 정련 사안**(H4·H5)이라 조건을 더 달지 않는다.

- 화이트리스트 설계는 "다섯째 벡터" 를 원천적으로 닫는 유일한 형태이고, 정본이 약속한 유일한 확장 자유(에러 코드 제거)는 M12 로 열려 있음을 확인했다.
- **첫 검증 기록([`mypy_guard_slice.md`](mypy_guard_slice.md))의 판정을 `조건부 합격` → `합격` 으로 승격한다** — 08-10 accept 선례(보강 검증이 원 판정을 승격)와 같은 형태다. 원 문구는 발행 시점 그대로 둔다.

## Outstanding items

- **미검증 = 1커밋**(`cd1d82d`, 2026-08-16) — 이 재검으로 `5182cad`(과 docs `0741a45`·`d3cc557`)는 커버됐다.
- **H4·H5 권고 대기** — 셀 문언 3줄 수준의 수정으로, 축 ① 착수와 무관하다.
- 다음 전수 기대값: 이 기록 등재로 판정 열 전수 subtest +1 → **`2297 passed / 1 skipped / 2521 subtests`**(코드 무관 자리).

## Reproduction

```bash
git status --short                       # 공백이어야 함
python3 -m pytest tests/test_typecheck.py -q        # 8 passed / 3 subtests

# 폐쇄 확인(각각 적용 → 셀 구동 → git checkout -- <path>):
# M8/M9: calibrate:20 위치 인자 + (무공백 ignore | 1행 프라그마) → 억제 셀 1 failed
# M10/M11: + (ini 퍼모듈 ignore_errors | files=services) → 설정 셀 1 failed

# 축(O1):
#   mypy.ini [mypy] 에 warn_unused_ignores = True 추가
#   → 설정 셀 1 failed("이 키들 밖은 전부 조용해지는 길이다") · 저장소 초록 셀 1 passed(불령 실증)
# O2: files 에 frontend 추가(.py 0개) → 설정 셀 1 failed(등가 단정)

# M12: disable 목록에서 arg-type 제거 → 설정 셀 1 passed · 저장소 초록 셀 1 failed
# M13: lock_mongo.py 에 "# mypy 가 … type ignore 는 쓰지 않는다" 주석 → 억제 셀 1 passed

# 전수(예열 후):
docker compose -f docker-compose.test.yml up -d   # hello 로 rs-test primary 확인
python3 -m pytest -q                               # 2297 passed / 1 skipped / 2520 subtests
```
