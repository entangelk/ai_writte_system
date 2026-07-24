# 검증 기록 — `auto_promote_job` 503 partial envelope (SoT v1.7.35)

## Subject metadata

- **날짜**: 2026-07-24
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래")
- **검증자**: Claude (독립 검증, 구현자와 무관)
- **대상 슬라이스**: `auto_promote_job` 부분 실패 의미론 — 503 partial envelope. SoT v1.7.34 → v1.7.35.
- **정본(계약) 참조**: `docs/system-contract-sot.md` v1.7.35 — 상태코드 의미론 §(503의 세 얼굴), D1=A 균일 본문 조항(partial envelope 예외), v1.6.40 `promoted[]` 조항.
- **검증 대상 작업 출처**: working tree, 미커밋(git status `M` 8개 + 신규 2개). HEAD = `188107f`. 브리프 `docs/plans/auto-promote-partial-failure-decisions.md`(상태 `Approved — 2026-07-24 (D1=B · D2=A · D3=404)`).

## Scope (정본 계약 범위 — 열기 전에 확정)

계약 읽기 전, 이 슬라이스가 지배하는 표면만 좁혔다:

1. **브리프** `docs/plans/auto-promote-partial-failure-decisions.md` 전문(D1~D3 + Follow-up considerations — 특히 #2 "outbox enqueue 실패… 메시지에 어느 단계에서 실패했는지 남긴다").
2. **SoT v1.7.35 변경점**: 상태코드 표 503 행 · "503의 세 얼굴" 절(신규 3번 + 502가 아닌 이유 / 500 안 만드는 이유 / 범위 문장) · 공통 규칙 문장 · D1=A 조항의 partial envelope 예외("정확히 6곳") · v1.6.40 `promoted[]` 조항의 부분실패 추가문.
3. **구현**: `services/application/app/main.py` 의 `auto_promote_job` 루프 + `_STORAGE_ERRORS` seam + `AutoPromotePartialResponse` + `_STORAGE_503`/`_ERRORS_404_STORAGE` + 선언.
4. **회귀**: `tests/test_memory_api.py::AutoPromoteStorageFailureTest`(5) · `tests/test_application_api.py::AnalysisErrorContractDeclarationTest`(신규 1 + 갱신 2).
5. **공개 envelope/타입**: `frontend/src/api/schema.d.ts` (+20) 와 OpenAPI anyOf.
6. **의존 계약**: `memory/service.py` 의 `promote_candidate`/`auto_promote_candidate`/`_enqueue_reindex` · `mongo_repository.put_memory` · `indexing/service.py::IndexSyncOutboxService._enqueue_event`.

범위 밖: 다른 endpoint의 저장소 매핑(별도 슬라이스로 추적 부채), 임계값 캘리브레이션, 프론트 에러 UX.

## 경계 매트릭스 (정본이 요구하는 분기 — 코드/테스트가 채워야 할 lock list)

| # | 분기 (정본 요구) | 기대 결과 | 구현 | 회귀 |
|---|---|---|---|---|
| 1 | 루프 중간, `put_memory` 저장 **전** 저장소 예외 | 503 + partial, `promoted[]` = 직전까지 mint | ✓ main.py | ✓ `test_store_failure_mid_loop…` |
| 2 | 루프 중간, `put_memory` 저장 **후** outbox enqueue 예외 | 503 + partial — **정본 주장: `promoted[]` = "그때까지 이 호출이 새로 mint한 것", 저장 상태와 불일치 없음** | ⚠ 위반(아래 Findings B1) | ✗ **빈 칸** — 회귀 없음 |
| 3 | 위 2 모드에서 "저장소 복구 후 같은 요청 재시도" | 남은 것만 승격(복구 유효) | ⚠ put-모드는 OK, enqueue-모드는 재색인 유실(아래 B1) | ⚠ put-모드만(`test_retrying…`) |
| 4 | 루프 중간 `MemoryNotFound` | 404 | ✓ | ✓ `test_memory_not_found_mid_loop_is_404` |
| 5 | 무관한 예외(`RuntimeError`) | 503 재분류 아님(전파) | ✓ | ✓ `test_unrelated_failure…` |
| 6 | 정상 | 200 + 성공 봉투 키 집합 | ✓ | ✓ `test_healthy_auto_promote…` |
| 7 | 선언 집합 `{404,503}`, 503 body = Union(partial, ErrorDetailResponse), 404 = 단일 `$ref` | OpenAPI에 정확히 노출 | ✓ | ✓ `AnalysisErrorContractDeclarationTest` |
| 8 | analysis 트랙 Union 허용 지점 = auto-promote 503 **1곳**만(drift 금지) | over-strict 가드 | ✓ | ✓ `test_union_bodies_appear_only…` |

**빈 칸 = 차단 사유**: 행 2(그리고 행 3의 enqueue 모드)는 정본이 **무조건적 단정**으로 요구하는 분기인데 회귀가 없고, 실제 동작은 그 단정과 **반대**다(아래 Findings).

## Methodology (재현 가능한 명령)

```bash
# 정본/구현/테스트 1차 소스 직독
git diff docs/system-contract-sot.md services/application/app/main.py \
  tests/test_application_api.py tests/test_memory_api.py frontend/src/api/schema.d.ts
git diff --stat   # docker-compose.yml 포함 변경 범위 확인

# 신규 회귀가 skip 아닌 실 실행인지(pymongo 설치 여부)
python3 -m pytest tests/test_memory_api.py::AutoPromoteStorageFailureTest \
  tests/test_application_api.py::AnalysisErrorContractDeclarationTest -v -rs

# outbox-이후-mint 실패 모드 재현(결정적 반증)
python3 docs/verifications/2026-07-24/repro_outbox_after_mint.py
# 재시도-복구 경로 재현(확장)
python3 docs/verifications/2026-07-24/repro_outbox_retry.py

# 전체 백엔드 스위트(test-mongo 27020 RS 기동 후)
docker compose -f docker-compose.test.yml up -d
python3 -m pytest -q
```

각 표면은 위 명령으로 독립 재도출했다. 구현자의 work_log/CHANGELOG 서술은 검증 대상이지 진실원천이 아니다.

## Findings

### F1. 구현/상태코드/선언 — 정본과 정합 (POSITIVE)

- **500 누수 폐쇄(put-모드)**: 루프가 모든 `try` 밖이던 것을 `except _STORAGE_ERRORS → 503` 로 감쌈(main.py:2645-2671). under-strict(절 제거 시 500 재발)와 over-strict(절 폭 `except Exception` 시 `RuntimeError` 오분류) 양방향 가드가 회귀로 못박혀 있다.
- **seam은 저장소·outbox 양쪽을 상태코드 수준에서 덮는다**: `_STORAGE_ERRORS = (PyMongoError,)` 는 `put_memory`(`insert_one`, mongo_repository.py:88-94 — `DuplicateKeyError`만 wrapping하고 나머지 누수) 와 `_enqueue_reindex`→`IndexSyncOutboxService._enqueue_event`(get/next/put 3개 Mongo op, indexing/service.py:396-427) 양쪽의 pymongo 예외를 한 지점에서 503로 매핑한다. 구현자의 "outbox까지 한 지점에서 덮는다" 주장은 **상태코드 매핑 한정에서 참**(F2 참조).
- **503=세 번째 얼굴 논리 정합**: 502(상류)와의 구분, 계약된 500을 안 만드는 이유(H3 가드 약화)가 SoT에 명문화됐고, 503 정의문("지금 수행할 수 없다/요청을 고쳐서는 해결되지 않는다")에 부합. 공통 규칙 문장도 "저장소 face는 조치 **후** 재시도가 유효"로 정밀화.
- **"5곳 → 6곳" 셀 단위 카운트 정합**: partial-envelope Union 허용 지점은 (path, method, code) 셀 단위. writing 트랙 `UNION_BODIES` = `revise-and-gate`(400/502/503/504) 4 + `accept`(502) 1 = 5(test_application_api.py:2712-2715 직독 확인), v1.7.35 가 auto-promote(503) 1개를 더해 6. v1.7.33의 "정확히 5곳"과 충돌 없이 "명시 결정으로만 늘어난다" 성질 유지.
- **analysis 트랙 over-strict Union 가드 신설**: `AnalysisErrorContractDeclarationTest.UNION_BODIES` + `test_union_bodies_appear_only_where_the_contract_allows` 가 analysis 트랙 전체의 Union drift를 잡는다(실행됨, PASS).
- **D3 MemoryNotFound → 404**: 형제 수동 promote(main.py:2885 `except MemoryNotFound`)와 동일 매핑. 선언 집합 무변({404} 안에 이미 있음). 회귀 `test_memory_not_found_mid_loop_is_404` 로 lock.
- **지연 seam 정합**: pymongo 지연 임포트(모듈 최상단 import 불가 — in-memory 경로가 드라이버 없이 떠야 함)를 `_resolve_storage_error_types()` 로 해결, 드라이버 부재 시 `()` → `except ()` 는 무매칭(Mongo 없는 배포에 분류할 Mongo 장애도 없음). 브리프 Follow-up "단일 seam" 충족.
- **선언/타입**: `responses=_ERRORS_404` → `_ERRORS_404_STORAGE`; OpenAPI 503 = `anyOf[AutoPromotePartialResponse, ErrorDetailResponse]`, 404 = 단일 `$ref`(덤프 실물 직독, `test_every_declared_error_body…` 로 lock). `schema.d.ts` **+20/-0 순수 추가**(`AutoPromotePartialResponse` 컴포넌트 + 503 anyOf arm). 직독 확인.
- **신규 회귀 10건 전부 실행·통과, skip 0**: `AutoPromoteStorageFailureTest`(5) + `AnalysisErrorContractDeclarationTest`(5, 신규 1 포함). pymongo 설치됨 → `@skipIf` 2건도 실 실행됨. (재현: `python3 -m pytest … -v -rs` → `10 passed, 60 subtests passed`.)

### F2. 백엔드 스위트 — 카운트 검증 (부분 검증, 솔직 공시)

- **절대 카운트(1459/1/526)는 작업자 self-report 이며 본 검증에서 재현하지 못했다.** test-mongo(27020 RS) 기동 후 `timeout 540 python3 -m pytest -q` 를 백그라운드로 돌렸으나 이 WSL2 머신에서 540s 안에 끝나지 않아 `timeout` 이 SIGTERM(exit 143). pytest -q 가 종료까지 출력을 버퍼링하므로 부분 집계도 얻지 못했다(출력 = "Terminated" 11바이트). 모니터(420s)로 재대기해도 완료 안 됨.
- **증분(dalta)은 검증됨**: 신규/변경 10건 전부 PASS, skip 0(F1).
- **광범위 보조 검증**: 슬라이스가 직접 건드린 두 파일 전체 `python3 -m pytest tests/test_memory_api.py tests/test_application_api.py -q --tb=line` → **132 passed / 208 subtests / 0 failures**(30.8s). 두 파일 안에서 회귀 없음. (수집 경고 2건은 기존 `TestClient.__init__` 것, 무관.)
- 결론: 카운트 자체는 미검증이나, **B1-B3 차단 사유는 카운트와 무관하게 재현으로 확정**됐으므로 판정에 영향 없음. 오너가 절대 카운트를 원하면 타임아웃 늘려 재실행 필요(이 머신에서 9분+ 소요).

### F3. **outbox-enqueue-이후-mint 실패 모드: 부분 봉투가 저장 상태와 어긋난다 (BLOCKING)**

정본 v1.6.40/v1.7.35 조항은 **무조건적 단정**으로 서술한다:

> "`promoted[]`는 여기서도 **그때까지 이 호출이 새로 mint한 것**만 담는다. mint는 append-only이고 되돌리지 않으므로 **응답이 실제 저장 상태와 어긋나지 않는다**."

이 단정은 `put_memory` 저장 **전** 실패(행 매트릭스 #1)에서만 참이다. `promote_candidate`(service.py:148-195)의 순서는:

1. `self._repo.put_memory(entry)` — memory 저장(**WRITE 1**, mongo `insert_one`)
2. `self._enqueue_reindex(entry)` (service.py:194) — 별도 Mongo write(**WRITE 2**, outbox)

`_enqueue_reindex` 가 pymongo 예외로 실패하면 memory는 **이미 저장됐지만**, main.py 루프의 `promoted.append(_memory_payload(...))` 는 `auto_promote_candidate` 반환 **후**에 실행되므로 그 candidate는 `promoted[]` 에 **빠진다**.

**경험적 재현**(`/tmp/repro_outbox_after_mint.py` — InMemory repo + `_FailingOutbox` 가 2번째 enqueue에서 `AutoReconnect` raise):

```
status: 503
promoted source_candidate_ids: ['analysis-candidate-1']
STORED source_candidate_ids:      ['analysis-candidate-1', 'analysis-candidate-2']
response.promoted == stored state?: False
```

candidate-2 의 memory는 put_memory 에서 **실제 mint**(저장소에 존재)됐으나, enqueue 실패로 503 로 빠지며 `promoted[]` 에서 누락. **정본 단정 위반.**

- 이 경로는 production(Mongo)에서 도달 가능하다(outbox의 get/next/put 3 op 중 어느 하나의 일시적 장애). 테스트 하네스는 `_reindex_outbox=None` no-op outbox를 쓰므로 **테스트에서만 보이지 않는다** — 그래서 출하된 회귀 `test_store_failure_mid_loop…`(행 #1 모델링)는 통과하면서 이 모순을 놓친다.
- **정본 자기모순**: 브리프 D2 도달성 표는 이 경로를 "memory는 있는데 재색인이 유실된다"로 명시(인지했음). 그런데 SoT 조항은 "응답이 저장 상태와 어긋나지 않는다"로 단정. **슬라이스 내 두 계약 문서가 서로 다르다.** CLAUDE.md 기준 내부 계약 모순 = 차단.
- **회귀 빈 칸**: 행 매트릭스 #2 는 정본이 요구하는 분기인데 lock 이 없다.

### F4. **재시도-복구 약속이 enqueue-모드에서 거짓이다 — mint된 memory가 영구 비색인 (BLOCKING, 데이터 무결성)**

503 description 과 SoT/브리프는 "저장소 복구 후 같은 요청 재시도 = 유효한 복구, 남은 것만 승격" 을 약속한다. 이 약속은 put-모드(행 #3)에서만 참이다.

`promote_candidate` 는 이미 승격된 candidate를 **idempotent replay** 로 처리하며, 이때 `find_memory_by_candidate` 가 존재하면 `_enqueue_reindex` **전에** early-return 한다(service.py:158-163 vs :194). 즉 mint-됐으나-enqueue-유실된 candidate를 재시도로 다시 부르면 **replay로 취급돼 재색인이 건드려지지 않는다.**

**경험적 재현**(`/tmp/repro_outbox_retry.py`):

```
1st call: 503  promoted=['analysis-candidate-1']  enqueued=['memory-1']
retry   : 200  promoted=[]                        enqueued=['memory-1']   # 변화 없음
STORED: ['analysis-candidate-1','analysis-candidate-2']
memory_ids ever enqueued for reindex: ['memory-1']   # memory-2(c2) 영구 비색인
=> retry recovered the lost reindex? NO
```

c2의 memory는 Mongo 에 존재하지만 **한 번도 색인 enqueue가 일어나지 않았고, 재시도에도 회복되지 않는다** → canonical memory 가 저장소엔 있고 벡터 색인엔 없는 조용한 데이터 무결성 구멍. Phase 2B.5(D3=B "단일 choke point — 어떤 write 경로도 색인을 잊지 않는다")가 막으려 한 바로 이것이다.

- 회귀 `test_retrying_after_recovery_promotes_only_what_is_left` 는 put-모드(c2 미-mint → 재시도가 c2 를 fresh mint+enqueue)만 검증한다. enqueue-모드에서 재시도가 빈 `promoted[]` 와 200 을 주는 것까지는 통과하지만, **유실된 재색인이 회복되지 않는다는 점은 잡지 못한다.**
- 재현 코드-동작(replay-skip-enqueue) 자체는 pre-existing 이나, **이 슬라이스가 "재시도=복구" 를 명시적 계약(SoT + OpenAPI description)으로 세웠으면서 그 계약이 enqueue-모드에서 거짓인지 검증하지 않았다.** 행 매트릭스 #3 의 enqueue 모드 = 빈 칸.

### F5. 브리프 Follow-up #2 미충족 — `promotion_error` 가 실패 단계를 기록하지 않는다 (BLOCKING)

브리프 Follow-up considerations #2 가 정확히 F3/F4 의 사례를 겨냥해 요구한다:

> "outbox enqueue 실패는 `put_memory` 성공 이후다… `promotion_error` 문자열이 이 구분을 삼키지 않도록 **메시지에 어느 단계에서 실패했는지 남긴다**."

구현은 `"promotion_error": str(exc)`(main.py:2667) 만 쓴다. pymongo 예외의 `str()` 은 "어느 단계(저장 write vs 재색인 enqueue)에서 실패, memory 가 저장됐는지 여부" 를 전달하지 않는다. 즉 호출자/운영자는 503 본문만 보고는 `promoted[]` 가 완전한지(mint 가 누락됐는지) 판단할 수 없다. **F3 의 근인(F3 발화 시 유일한 완화 수단)이면서 브리프가 이 슬라이스에 명시한 요구사항인데 미구현.**

### F6. 범위/문서 충실도 — 대체로 정직 (POSITIVE, 정정 1)

- **docker-compose.yml(+23)은 별도 정식 Task**(초회 의혹 "미문서화 scope creep" → **철회**). work_log 의 `## Task — 배포 스택 fd 한계 폐쇄` 헤더가 오너 지시("작은 것부터")와 2026-07-23 추적 부채 근거로 상세 기록. 검증자 verbal summary 에 빠졌을 뿐, 문서화된 정당 범위.
- **범위 한계 정직 공시**: SoT 503 절과 HANDOFF(추적 부채) 가 "저장소 매핑은 이 endpoint 1곳뿐, 나머지는 여전히 500 누수" 를 명시적 범위 문장으로 적고, 교체 지점(`_STORAGE_ERRORS` 단일 seam)을 남김. 이것은 합법적 추적 부채(별도 taxonomy 슬라이스)이며 차단 사유 아님.
- **정정(초회 의혹)**: CHANGELOG 의 "D1=A 균일 `{detail}` 의 Union 예외 지점이 5곳 → 6곳" 표현은 dense 하나 모순 아님 — "D1=A 규칙의 Union-예외 지점(에러 arm 은 단일 `ErrorDetailResponse` 라 위반 아님)" 의 뜻이고, SoT 본 조항이 더 명확히 서술. 카운트 셀 단위 정합(F1).

## Issues / Risks

### Blocking (계약 의무)

- **B1 (F3)** — outbox-enqueue-이후-mint 실패 시 부분 봉투 `promoted[]` 가 저장 상태와 어긋난다. SoT 무조건 단정 위반 + 브리프 D2 표와 SoT 조항의 내부 모순 + 회귀 빈 칸(매트릭스 #2). 경험 재생됨.
- **B2 (F4)** — "재시도=복구" 약속이 enqueue-모드에서 거짓. mint된 memory 가 영구 비색인(데이터 무결성 구멍). 회귀 빈 칸(매트릭스 #3 enqueue 모드). 경험 재생됨.
- **B3 (F5)** — 브리프 Follow-up #2 미충족. `promotion_error = str(exc)` 는 실패 단계를 기록하지 않는다.

> 세 건은 **동일 근인**(seam 이 outbox 예외를 잡게 되면서, 부분 봉투·재시도 논리가 "실패가 mint 이전에 났다"고 가정하게 됨)의 세 표면이다. 따라서 해법도 일관되게 잡을 수 있다.

### Hardening recommendations (비차단)

- H1 — `AutoPromotePartialResponse.promoted` 를 `list[dict[str, object]]` 로 둔 구현자 판단(work_log:143)은 타당(성공 arm 이 무타입 dict). 다만 후속 memory payload 타입화 슬라이스에서 partial 도 같이 좁히면 wire 일관성이 올라간다.
- H2 — 503 description 에 "이 endpoint 1곳만 매핑" 범위 문장은 SoT 에 있으나 OpenAPI description 에는 없다. 프론트 소비자가 0인 지금은 비차단이나, dogfood UI 부착 전 description 에도 한 줄로 남기면 추측을 줄인다.
- H3 — `test_retrying_after_recovery…` 의 이름이 "recovers" 를 암시하나 실제로는 put-모드 한정. enqueue-모드 회귀가 추가되면 이 테스트의 범위도 docstring 에 명시할 것.

## Verdict — 조건부 합격 (conditional pass)

슬라이스의 **1차 목표(H3 잔여 미매핑 500 누수를 503 partial envelope 로 폐쇄)**는 put-모드에서 정확히 달성됐고, 상태코드 의미론·선언·타입·analysis 트랙 가드·문서 공시는 모두 정본과 정합(F1, F6). 따라서 "불합격"이 아니다.

그러나 **"합격"도 아니다**. seam 이 이제 outbox 예외까지 잡으면서, 부분 봉투·재시도 논리가 전제하는 "실패는 mint 이전" 가정이 enqueue-모드에서 깨지고, 정본은 그 모드를 **무조건 단정**(응답=저장상태 / 재시도=복구)으로 서술했기 때문이다:

- **B1**: enqueue-모드에서 `promoted[]` 가 저장 상태와 어긋남(정본 단정 위반 + 내부 모순 + 회귀 빈 칸).
- **B2**: 같은 모드에서 "재시도=복구" 가 거짓 → mint된 canonical memory 영구 비색인(데이터 무결성).
- **B3**: 브리프가 이 슬라이스에 명시한 완화 요구(실패 단계 메시지 기록) 미충족.

**합격 조건(오너 결정으로 둘 중 하나)**:

- **(경로 A — 계약 보정, 동작 유지)** SoT v1.6.40 조항과 503 description 의 무조건 단정을 **enqueue-모드를 인정하도록** 정정(promoted = "mint+enqueue 모두 완료된 것", 재시도는 남은 mint만 회복하되 **유실된 재색인은 별도 복구가 필요**함을 명시) + Follow-up #2 충족(`promotion_error` 에 단계 기록) + 매트릭스 #2/#3 enqueue-모드 회귀 추가.
- **(경로 B — 코드 보정, 계약 유지)** enqueue 실패 시에도 `promoted[]` 가 저장 상태와 일치하도록(mint 후 enqueue 전 실패를 분기해 해당 candidate를 보고) + 재시도가 유실 재색인을 회복하도록(replay 경로에서 누락 enqueue를 재시도) 수정 + 그 동작을 lock 하는 회귀 추가.

B2(비색인 canonical memory)는 미용적이지 않고 기능적 데이터 무결정이므로, 경로 A 를 택하더라도 "재시도만으로는 재색인이 회복되지 않는다"는 사실이 정본에 명시돼야 추적 부채로 살아남는다.

## Outstanding items (오너 다음 단계에 영향)

- **미커밋 working tree**: 슬라이스 전체가 커밋 안 됨(지시 없음). 위 차단 사유(B1-B3) 해소 전 커밋은 보류 권장.
- **백엔드 풀스위트 카운트**: 본 검증에서 **미검증**(540s timeout 초과, SIGTERM). 작업자 보고 1459/1/526 은 self-report. 증분은 검증됨(신규 10건 PASS/skip 0) + 두 파일 132/208 무실패. 절대 카운트 필요 시 타임아웃 연장 재실행.
- **재현 스크립트** `docs/verifications/2026-07-24/repro_outbox_after_mint.py`(B1) · `repro_outbox_retry.py`(B2) — 본 검증과 함께 보관. 두 스크립트 모두 새 위치에서 재실행해 동일 결과를 확인했다(B1: agrees=False / B2: retry 미회복).
- test-mongo(27020) 컨테이너를 본 검증에서 기동함. 종료 시 `docker compose -f docker-compose.test.yml down`.

## Reproduction (끝까지 재실행하는 최소 순서)

```bash
cd /mnt/d/devel/에베베/ai_writte_system

# (1) B1 — 부분 봉투가 저장 상태와 어긋남
python3 docs/verifications/2026-07-24/repro_outbox_after_mint.py
# 기대: status 503, promoted=[c1], STORED=[c1,c2], agrees=False

# (2) B2 — 재시도가 유실 재색인을 회복하지 못함
python3 docs/verifications/2026-07-24/repro_outbox_retry.py
# 기대: retry 200 promoted=[] enqueued 여전히 [memory-1], c2 영구 비색인

# (3) 회귀가 put-모드만 커버하는지(enqueue-모드 빈 칸 확인)
python3 -m pytest tests/test_memory_api.py::AutoPromoteStorageFailureTest -v -rs

# (4) 정본 단정 원문 직독
grep -n "어긋나지 않는다\|남은 candidate만 승격" docs/system-contract-sot.md
```
