# 2026-08-08 작업 로그

## Goals

- 라우터 분해 **Slice 1 마무리** — 76 operation 이 전부 `routers/` 로 나가
  `main.py` 가 조립 코드만 남은 상태에서, 이동이 남긴 **미사용 import 21개**를
  정리한다.
- 정리 자체는 기계적이다. **실제 목표는 "지워도 되는 것만 지웠다"를 증명하는 것**이고,
  그 증명은 정적(pyflakes)·구조적(지문)·행위적(뮤테이션·전수 회귀) 셋으로 나눈다.

---

## Task 1 — `main.py` 미사용 import 정리 (Slice 1 마무리)

### User Decisions and Rationale

- 2026-08-07 work_log Task 8 이 Slice 1 종료 뒤를 **"오너가 잡는 두 갈래"**
  (① 미사용 import 정리 ② Slice 2 `create_admin_app()`)로 남겨 두었으므로,
  임의로 고르지 않고 오너에게 물었다. **오너 선택 = ①**.
- 브리프는 만들지 않았다. 두 갈래 모두 2026-08-05 에 이미 결정된 작업(R1·A1)의
  하위 단계이고, ①은 계약·구조를 하나도 정하지 않는 기계적 정리라
  `CLAUDE.md` §1 의 "genuine fork"에 해당하지 않는다.

### 머신 확인 (알파)

- `nvidia-smi` = **RTX 3060 12GB** → 알파 확정(HANDOFF 머신 표의 판별식).
- 착수 시 HEAD `d65a1c9` · `git status --short` **비어 있음**(§6 사전 게이트 통과).
- `docker compose ps` = `frontend`(healthy) · `worker` · `generation_worker` 3개.
  application·mongo·gateway·embedding·chroma·ES 미기동 — **이 슬라이스는 스택이
  필요 없다**(import 정리·정적 검사·회귀뿐). 전수 회귀를 위해 `test-mongo` 만
  `docker-compose.test.yml` 로 올렸다 내렸다.

### ★ 도구 확보 — 알파 호스트에는 pyflakes 가 없고 `pip install` 이 거부된다

출발값 **21** 은 2026-08-07 에 `pyflakes` F401 로 잰 값이라 같은 도구로 재야
비교가 성립하는데, 이 머신에서는 두 단계가 다 막혔다:

- `python3 -m pyflakes` → `No module named pyflakes`
- `python3 -m pip install --user pyflakes` → **PEP 668 `externally-managed-environment`**
  로 거부(`--break-system-packages` 를 강요하는 안내가 뜬다 — 쓰지 않았다).

**해결: scratchpad 에 venv 를 만들어 거기 설치했다**(호스트 파이썬 무오염,
repo 에 남는 것 0). 재현:

```bash
python3 -m venv <scratch>/venv && <scratch>/venv/bin/pip install pyflakes
<scratch>/venv/bin/python -m pyflakes services/application/app/main.py
```

**전 실측 21과 정확히 일치**했다(아래 표) — 즉 3차·4차 이동 이후로 이 값은 움직이지
않았고 출발값 표기가 옳았다.

### Completed work

**미사용 import 21개 제거.** `main.py` **1,860 → 1,840 줄**. 변경 파일은
[`services/application/app/main.py`](../../../services/application/app/main.py) **하나뿐**이다.

| 출처 | 제거한 심볼 | 처리 |
|---|---|---|
| `datetime` | `datetime` | 부분 제거(`timedelta` 는 남는다 — `main.py:393`) |
| `typing` | `Annotated` · `Union` | 부분 제거(`Protocol` 은 남는다 — `main.py:221`) |
| `fastapi` | `Header` | 부분 제거 |
| `pydantic` | `BaseModel` · `ConfigDict` · `Field` · `StringConstraints` · `field_validator` | **문 전체 제거**(pydantic 심볼이 main 에 하나도 안 남았다) |
| `auth.cookies` | `SESSION_COOKIE_NAME` · `cookie_kwargs` | **문 전체 제거** |
| `auth.admin_audit` | `AdminAuditEvent` | 부분 제거 |
| `observability.kpi` | `aggregate_global_kpi` | **문 전체 제거** |
| `quota.billable_actions` | `BILLABLE_ACTION_BY_OPERATION` | **문 전체 제거** |
| `quota.dedupe` | `UnclassifiedBillableAction` · `resolve_dedupe_key` | **문 전체 제거** |
| `quota.enforcement` | `AdmissionUnavailable` · `QuotaRefusalReason` · `QuotaRefused` | 부분 제거 |
| `writing.http_models` | `ErrorDetailResponse` | **문 전체 제거** |
| `core_sot.models` | `BlockKind` | **문 전체 제거** |

**`from __future__ import annotations` 는 건드리지 않았다** — pyflakes 가 세지 않는
컴파일러 지시자이고(2026-08-07 work_log:331 이 같은 지적을 한다), 지우면 모든
annotation 이 즉시 평가돼 동작이 바뀐다.

### 제거 안전성 — 정적으로 두 번, 구조적으로 한 번

1. **pyflakes 전/후 diff**: F401 **21 → 0**, F821 **0 → 0**(부작용 없음).
2. **`main` 경유 참조 스윕**: 21개 심볼 각각에 대해
   `from …main import <s>` · `main.<s>` 를 `tests/`·`scripts/`·`services/`·`frontend/`·`docs/`
   전수 grep → **0건**. 실제로 `app.main.<심볼>` 로 patch 하는 자리는 저장소 전체에
   `connect_chroma_collection` · `_build_embedding_provider` · `GatewayGenerateProvider`
   **셋뿐**이고 **제거 대상에 하나도 없다**.
   - 이 확인이 필요한 이유는 HANDOFF 가 적은 그 함정이다 — **테스트가 `main.X` 를
     patch 하는데 X 가 이미 main 에서 안 쓰이면 그 patch 는 이미 조용히 빗나가고
     있다.** 제거하면 그것이 `AttributeError` 로 시끄럽게 바뀐다(개선이지 회귀가
     아니다). 다만 이번 21개에는 해당 자리가 없었다.
3. **공개 표면 지문**: [`repro_router_split.py`](../../verifications/2026-08-05/repro_router_split.py)
   를 `git worktree` 로 뜬 HEAD 트리와 작업 트리에서 각각 돌려 **`diff` 출력 없음
   (pre ≡ post)**. route **76** · order-sensitive pairs **0** · openapi sha
   **`f8b42ef1…`**(Slice 1 내내 고정된 그 값). stdout-only 지문 전체의 sha256 은
   **`c3dfb391…`**.
   - **★ 초판이 여기에 `47d78b68…` 을 적었는데 그것은 재현되지 않는 값이다** —
     독립 검증이 8종을 시도해 전부 불일치. 원인과 교정은 아래 Task 2.

### ★ 함께 본 것 — 조립 전용 잔류 심볼은 지울 게 없었다

2026-08-07 Task 8 이 "`_default_model_capabilities`·`_report_output_cap`·`seed_*`
같은 조립 전용 잔류 심볼도 함께 본다"고 남겼다. 전수 확인 결과 **셋 다 살아 있는
조립 코드**다:

- `_default_model_capabilities` — `main.py:754` 정의, `:1439`·`:1642` 호출.
  게다가 [`test_writing.py:810`·`:871`](../../../tests/test_writing.py) 이
  `patch.object(main_module, …)` 로 **이 심볼을 직접 patch 한다** — 지웠다면
  2 셀이 물었을 자리다.
- `_report_output_cap` — `main.py:770` 정의, `:1440`·`:1643` 호출.
- `seed_*` 7종 — 전부 `_default_prompt_templates` 계열 조립부에서 호출된다.

**즉 이 항목은 "확인 결과 대상 없음"으로 닫힌다.** 미사용이었던 것은 import 21개뿐이다.

### 뮤테이션 (5종)

**순서 준수**: 정리를 먼저 커밋(`3ff4274`) → 뮤테이션 → `git checkout --` 원복 →
매 회 `git status --short` 로 clean 확인(§6 게이트).

| # | 방향 | 적용한 diff | file:line | 결과 |
|---|---|---|---|---|
| M1 | under-strict | `from datetime import timedelta` 삭제 | `main.py:7` | **물지 않았다** — `test_app_import_paths.py`·`test_writing.py` 71 passed. 아래 Issues 참조 |
| M2 | under-strict | `from typing import Protocol` 삭제 | `main.py:8` | **collection 단계 `NameError: name 'Protocol' is not defined`** (`test_auth_api.py` — 클래스 정의가 import 시점에 평가된다) |
| M3 | under-strict | `AdminAuditService,` 삭제 | `main.py:20` | **collection 단계 `NameError: name 'AdminAuditService' is not defined`** |
| M4 | under-strict | `LlmCallSite,` 삭제 | `main.py:110` | **8 failed** — `test_llm_call_sites.py::SiteAssemblyIsInstrumentedTest::{test_report_assembly_is_wrapped, test_revision_assembly_is_wrapped, test_writing_retrieval_planner_assembly_is_wrapped}` 외 5(`test_llm_call_scope.py::DefaultAssemblyIsInstrumentedTest::{test_extractor_assembly_instruments_the_provider_it_builds, test_gate_assembly_instruments_the_provider_it_builds}` 포함) |
| M5 | **over-strict** | 제거한 `from …core_sot.models import BlockKind` 를 **되돌려 넣는다** | `main.py:191` | **아무것도 안 문다** — 139 passed. 유일한 신호는 pyflakes F401 **0 → 1** |

**M4 가 이 슬라이스의 핵심 증거다.** `LlmCallSite` 는 `main.py` 안에서 조립부 8곳의
`ObservedProvider(…, call_site=…)` 리터럴로만 쓰여, 모듈 로드로는 안 잡히고
**조립 가드로만** 잡힌다. HANDOFF 가 "감싸기를 빠뜨려도 green 이고 배포에서만
계측이 사라진다"고 적은 그 자리이며, 이번 뮤테이션이 그 가드가 **import 정리에
대해서도** 유효함을 실측했다.

**M2·M3 은 "collection 단계 실패"라 셀 이름이 안 나온다** — 모듈 로드가 죽어
pytest 가 수집 자체를 못 한다. 셀 이름 대신 예외 문구를 적었다.

### Issues found — M1 이 물지 않은 것은 내 변경 탓이 아니라 기존 커버리지 공백이다

- **문제**: 남긴 import `timedelta` 를 지웠는데 회귀가 통과했다. 표면적으로는
  "지워도 되는 것을 남겼나"로 읽힌다.
- **원인**: `timedelta` 의 유일한 사용처가 `main.py:393` 이고, 그 줄은
  **`AUTH_SESSION_TTL_HOURS` env 가 세워졌을 때만 실행되는 분기** 안이다.
  `grep -rn AUTH_SESSION_TTL_HOURS tests/` = **0건** — 이 env 를 세우는 셀이
  저장소에 하나도 없다.
- **★ 그래서 진짜 지적은 import 가 아니라 계약이다.** 2026-07-27 work_log:221 이
  *"`AUTH_SESSION_TTL_HOURS` 가 0 이하면 기동 거부. 조용한 fallback 은 무한 세션을
  만들 수 있고…"* 라고 **보안 근거까지 달아 계약으로 적었는데, 그 계약을 지키는
  셀이 없다.** `main.py:391-392` 의 `raise ValueError` 를 지워도 아무것도 안 문다.
- **처리**: **이번 슬라이스에서 고치지 않았다.** 인증 TTL 계약에 회귀를 신설하는
  것은 import 정리의 범위가 아니고(§3 "모든 변경 줄이 요청으로 추적돼야 한다"),
  계약이 이미 존재하므로 결정 브리프도 필요 없다 — **추적 부채로 올린다.**
  `timedelta` 자체는 실제 사용처가 있으므로 **남기는 것이 옳다**(pyflakes 도
  F401 로 세지 않는다).

### Issues found — 이 정리에는 회귀 가드가 원리적으로 없다 (M5)

- M5 가 보여주듯 **미사용 import 를 되돌려 넣어도 회귀는 전부 green** 이다.
  유일한 신호가 linter 인데 **linter 는 스위트 안에 없다**(위 도구 절 — 호스트에
  설치조차 안 돼 있었다).
- **가드를 신설하지 않은 이유**: ① repo 전체 F401 가드는 **즉시 실패한다** —
  `main.py` 밖에 기존 F401 이 3자리 있다(아래). ② `main.py` 만 0 으로 잠그는 셀은
  기준이 자의적이다. ③ pyflakes 를 테스트 의존성으로 들이면 이 저장소가 피해 온
  "요청 안 한 인프라"가 된다. **판단 사안이라 추적 부채로 올리고 선택지를 적었다.**

### Issues found — `main.py` 밖의 기존 미사용 import 3자리 (건드리지 않음)

`pyflakes services/ scripts/` 전수에서 나온 것들이다. **내 변경이 만든 것이 아니므로
§3 대로 언급만 한다**:

| 위치 | 심볼 |
|---|---|
| [`services/application/app/indexing/chroma.py:27`](../../../services/application/app/indexing/chroma.py#L27) | `MEMORY_VECTOR_COLLECTION` |
| [`scripts/gateway_generate_live_smoke.py:30`](../../../scripts/gateway_generate_live_smoke.py#L30) | `sys` |
| [`scripts/report_budget_measure.py:45`](../../../scripts/report_budget_measure.py#L45) | `ContextBudget` · `ContextSearchPurpose` · `ContextSearchRequest` |

### Verification

| 검사 | 결과 |
|---|---|
| pyflakes F401 (`main.py`) | **21 → 0** |
| pyflakes F821 (`main.py`) | **0 → 0** |
| `repro_router_split.py` 지문 (HEAD worktree vs 작업 트리) | **`diff` 출력 없음(pre ≡ post)** · route 76 · order-pairs 0 · openapi sha `f8b42ef1…` |
| `main` 경유 참조 스윕 (21 심볼) | **0건** |
| 조립 전용 잔류 심볼 3계열 | **전부 사용 중 — 제거 대상 없음** |
| 뮤테이션 | 5종(under 4 · over 1). M2·M3·M4 물림, M1 은 기존 공백, M5 는 설계상 무가드 |
| 전수 회귀 (test-mongo ON) | 아래 |

### 회귀 기준선

**실측(알파, test-mongo ON, `3ff4274`)**:

```
2197 passed, 4 skipped, 2168 subtests passed in 193.92s
```

**★ 기준선 `2200/1/2168` 과 숫자가 다르다 — 그러나 코드 차이가 아니다.** HANDOFF 가
예고한 그 드리프트이며 `-rs` 로 사유를 확인했다:

| skip | 사유 |
|---|---|
| `test_chroma_adapter.py:490` | live Chroma — 호스트에서 **구조적으로 항상 skip**(기준선의 그 1건) |
| `test_context_search_memory_lexical_retrieval.py:324`·`:336`·`:341` | **`elasticsearch` package not installed** — 이 셸에 패키지가 없다 |

**환경 보정하면 `2197 + 3 = 2200 passed` · `4 − 3 = 1 skipped` 로 기준선과 같다.**
즉 **셀 증감 0** — 미사용 import 21개 제거가 셀을 하나도 더하거나 빼지 않았다.

**subtests 2168 = 직전 2167 + 1**, 그리고 **+1 은 코드와 무관하다** — 2026-08-07
4차 검증 기록(`5e19867`)이 `test_docs_indexes.py` 의 판정 열 전수 셀을 1 subtest
늘린 것이고, 그날 검증자가 *"다음 회귀는 2167 → 2168"* 로 **미리 예고한 값과 정확히
일치**한다.

**★ 다음 작업자에게 — 알파의 skip 은 1이 아니라 4가 정상이다.** `elasticsearch`
패키지 유무는 머신마다 다르고 HANDOFF 가 이 드리프트로 여러 번(양방향으로) 헷갈린
자리다. 알파에서 `2197/4` 를 보고 "3건 깨뜨렸나"로 오독하지 말 것 — `-rs` 가 30초에
답한다.

### 아직 안 한 것 (의도)

- **`main.py` 밖의 F401 3자리** — 내 변경이 만든 것이 아니다(§3).
- **`AUTH_SESSION_TTL_HOURS` 계약 회귀** — 추적 부채로 올렸다.
- **미사용 import 가드 신설** — 판단 사안이라 선택지만 적었다.
- **Slice 2(`create_admin_app()`)** — 두 갈래 중 오너가 ①을 골랐다. 선행은 여전히
  H-2(shim drift 가드) 하나뿐이며 이 정리로 달라진 것은 없다.

### Next steps

1. **Slice 2 — `create_admin_app()`** (A1=ⓑ 별도 compose 서비스). `main.py` 가
   1,840 줄 조립 코드만 남아 앱 분리를 다루기에 가장 좋은 상태다. 선행 = H-2.
2. **Phase 9 A1~A8 오너 결정** — 라우터 정리가 끝나 A7 가드가 `main.py` 를 파일로
   읽어야 할 이유가 완전히 없어졌다.
3. 이번 슬라이스가 올린 추적 부채 2건(TTL 계약 회귀 · 미사용 import 가드).

---

## Task 2 — 독립 검증 반영 (`b9fca77` 대상) · 비차단 1건 폐쇄 + 가드 복구

독립 세션이 **합격 · Blocking 0** 으로 검증했다
([기록](../../verifications/2026-08-08/main_unused_import_cleanup.md)).

### User Decisions and Rationale

- 오너 지시: *"검증기록 확인해서 보강해."* 판정이 **합격**이므로 되돌림은 없고
  **비차단 지적을 닫는 것**이 작업 범위다.

### Completed work

| 지적 | 처리 |
|---|---|
| ① **인용한 지문 해시 `47d78b68…` 가 재현되지 않는다**(검증자가 8종 시도 — 전체 sha256 `c3dfb391…`·개행제거·`git hash-object`·필드별·compact·md5 전부 불일치). 1~4차 기록의 관례(`openapi_sha256` + "diff empty")에서 벗어난 orphan 토큰 | **원인 규명 후 교정.** work_log 두 곳·HANDOFF 을 관례대로 **`diff` 출력 없음(pre ≡ post) + openapi sha `f8b42ef1…`** 로 바꿨다. stdout-only 지문의 sha256 `c3dfb391…` 도 함께 적었다 |
| ② 검증자 커밋(`b9fca77`)이 기록만 추가하고 **건수 주장을 갱신하지 않아 `test_docs_indexes.py` 가 7 failed** | **복구.** 인덱스 행 신설 + 건수 4자리 갱신(아래) |

### ★ ① 의 원인 — `2>&1` 이 지문 파일을 오염시켰다

검증자는 "재현 불가"까지 정확히 짚었고, **원인은 내 명령줄에 있었다**. 실측:

```
A: repro_router_split.py > f.json          → 27,652 B · sha256 c3dfb391…   (검증자 값)
B: repro_router_split.py > f.json 2>&1     → 35,318 B · sha256 47d78b68…   (내가 쓴 값)
차이 = 7,666 B = stderr
```

[`repro_router_split.py`](../../verifications/2026-08-05/repro_router_split.py) 는
**JSON 지문을 stdout 으로, 사람용 요약표(`routes=76 order-sensitive-pairs=0` +
route→모듈 76행)를 stderr 로** 낸다. 내가 `2>&1` 로 받아 두 스트림을 한 파일에
합쳤고, 그래서 내 해시는 **"지문 + stderr 로그"의 해시**였다.

**★ 무변 주장 자체는 손상되지 않았다** — pre·post 를 **둘 다 같은 방식**으로 받아
`diff` 했으므로 비교는 유효하고, 오히려 stderr 의 route→모듈 표까지 대조해
**더 엄격했다**. 검증자도 clean stdout 으로 pre ≡ post 를 독립 확인했다. **틀린 것은
인용 토큰 하나뿐이다.**

**재발 방지**: 해시를 인용할 값과 비교에 쓸 파일을 섞지 않는다. 이 함정은 Slice 2 에서
같은 스크립트를 또 돌릴 사람에게 그대로 걸리므로 **HANDOFF 의 재검증법 항목에 적었다**.

### ② 가드 복구 — 검증 기록 1건이 건수 주장 5자리를 움직인다

검증자가 `docs/verifications/README.md` 머리말만 227건으로 고치고 **인덱스 행과
나머지 건수 주장을 안 고쳐** `VerificationCountClaimsTest` 등 **7 셀이 실패**하고 있었다.

| 위치 | 고친 것 |
|---|---|
| [`docs/verifications/README.md`](../../verifications/README.md) | **`### 2026-08-08` 절과 인덱스 행 신설**(판정 열 `합격`) |
| [`README.md:89`](../../../README.md#L89) | `226건 / 44일치` → **`227건 / 45일치`** |
| [`README.md:93`](../../../README.md#L93) | 분포 `합격 158` → **`합격 159`**(조건부 66·불합격 2 무변, 조건부 비율 29% 유지) |
| [`README.md:177`](../../../README.md#L177) | `(226건)` → **`(227건)`** |
| [`docs/README.md:11`](../../README.md) | `226건` → **`227건`** |

**결과**: `test_docs_indexes.py` **7 failed → 13 passed / 237 subtests**
(236 → 237 은 새 기록 1건의 판정 열 subtest — 코드 무관).

**★ 다음 검증자에게**: 기록을 하나 추가하면 **디스크에 묶인 건수 주장이 다섯 자리**
움직인다(위 표). 가드가 전부 잡아 주므로 조용히 새지는 않지만, **기록 커밋 직후
`python3 -m pytest -q tests/test_docs_indexes.py` 를 한 번 돌리는 것이 관례**다.

### 검증이 채운 것 (내가 안 잰 축)

- **`AUTH_SESSION_TTL_HOURS` 계약이 살아 있음을 라이브로 증명했다** — 나는 "커버리지가
  없다"까지만 봤는데, 검증자가 `-1`/`0`/`abc` 를 주입해 **전부 `ValueError`**,
  `=2`/unset 은 정상 빌드임을 확인했다. **즉 부채의 정확한 모양은 "계약이 죽었다"가
  아니라 "계약은 살아 있는데 지키는 셀이 0건"이다.** 추적 부채 문구가 이미 그 형태라
  수정할 것은 없고, 라이브 증명이 붙어 더 강해졌다.
- **정적 축을 1차 소스에서 재현했다** — 나는 작업 트리에서만 pyflakes 를 돌렸는데,
  검증자는 `git show d65a1c9:…main.py` 로 **OLD 를 직접 떠서 21** 을 재현하고
  pyflakes 와 무관한 **독립 잔류 grep** 으로 교차 확인했다.
- **다중줄 import 오탐 1건을 스스로 해소했다**(`test_observability_kpi.py:44` 의
  `aggregate_global_kpi` 가 main 경유로 보였으나 출처 모듈 직수). **내 단일줄 grep 이
  다중줄 import 를 놓칠 수 있는 자리**이며, 이번 21개에는 해당 자리가 없었다 —
  다음에 심볼을 지울 때는 스윕 패턴을 다중줄까지 넓히는 것이 안전하다.

### 아직 안 한 것 (의도)

- **검증 기록 본문은 고치지 않았다.** 남의 산출물이고 판정·근거가 정확하다.
  ①의 원인 규명은 **내 기록 쪽**(이 Task)에 적었다.
- **추적 부채 2건은 그대로 둔다** — 검증자도 "이 슬라이스 범위 외"로 동의했다.

### Next steps

1. **Slice 2 — `create_admin_app()`**. 선행 = H-2(shim drift 가드).
2. 추적 부채 2건(TTL 계약 회귀는 인증 슬라이스에서 · 미사용 import 가드는 ⓐ 유지).
