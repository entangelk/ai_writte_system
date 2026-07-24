# 검증 기록 — 저장소 장애 매핑 전역화 (SoT v1.7.38, 전역 503 handler)

## Subject metadata

- **날짜**: 2026-07-24
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증(Claude, 본 슬라이스 비구현)
- **대상 슬라이스/산출물**: `946150d feat(api): 저장소 장애 매핑 전역화 — 48개 endpoint 500 누수 폐쇄 (SoT v1.7.38)`
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.38 (changelog 행) + 본문 §"503 … 정본 저장소 장애(storage)" (≈ §330 영역, 세 얼굴 논의)
- **작업 소스**: 커밋 `946150d` (working tree clean, HEAD)

## Scope (canonical contract scope)

정본에서 이 슬라이스가 건드리는 계약 면만:

1. **SoT v1.7.38 changelog 행** — 형태·실측·선언·우선순위 계약·회귀 수의 전부.
2. **SoT 본문 §"정본 저장소 장애(storage)"** — 503 세 번째 얼굴. v1.7.38이 "매핑은 전역이다 / endpoint 절이 우선한다 / 60개 operation 선언, /health 제외"로 갱신한 3문장.
3. **`services/application/app/main.py`** — `create_app`의 전역 handler 2종, 상수 `_STORAGE_ERRORS`/`_STORAGE_503`/`_AUTO_PROMOTE_503`/`_with_storage_note`, `GET|POST /projects`에 `_ERRORS_STORAGE` 부착.
4. **`services/application/app/writing/http_models.py`** — `_ACCEPT_503` description에 저장소 문장 덧붙임.
5. **`tests/test_application_api.py`** — `CanonicalStoreFailureHandlerTest`(신규 5) + 선언 lock 리스트 4종 전수 갱신.
6. **`frontend/src/api/schema.d.ts`** — `gen:api` 결과.
7. **연쇄 검증(전역 handler가 real Mongo에서도 발화하는가)**: `core_sot/mongo_repository.py`·`analysis/mongo_repository.py`·`memory/service.py`의 `except` 절이 재-raise 하는지.

v1.7.35~37의 partial-envelope 의미론 자체는 이 슬라이스 범위가 아니나, **새 전역 handler가 그 의미론을 깨뜨리지 않는지**는 범위 내(우선순위 계약 검증).

## Methodology

경로: `cd /mnt/d/devel/에베베/ai_writte_system && PYTHONPATH=. python3 …`. pymongo 4.16.0 설치됨(= handler 등록됨, skip-if 테스트 실생행).

1. **정본 changelog/본문 diff**: `git show 946150d -- docs/system-contract-sot.md`
2. **구현 diff**: `git show 946150d -- services/application/app/main.py services/application/app/writing/http_models.py`
3. **OpenAPI 경험적 집계**(중심 주장 "60/61"):
   `create_app().openapi()`에서 (path,method) 전수 순회하며 503 보유/미보유 집계.
4. **저장소→503 발화 다중 엔드포인트 probe**(공식 테스트는 GET /projects 1건만 실생행하므로):
   `InMemoryCoreSotRepository`를 상속해 `get_project`/`list_projects`/`put_project`가 `AutoReconnect`를 raise하게 하고 core_sot/drafts/brief/memory/analysis/writing 트랙 11개 엔드포인트 관통.
5. **mutation 실증**: `app.exception_handlers`에서 `PyMongoError` 키·`MemoryReindexEnqueueFailed` 키를 각각 삭제(`TestClient(..., raise_server_exceptions=False)`)하고 GET /projects가 500으로 회귀하는지 확인.
6. **lock 산술**: 4개 선언 dict의 현재/직전(`git show 946150d^:tests/test_application_api.py`) 503 보유 항목 수.
7. **real-Mongo 재-raise 확인**: `core_sot/mongo_repository.py:237/466`, `analysis/mongo_repository.py:268`의 `except`가 `raise`로 끝나는지 (전역 handler 도달의 전제).
8. **gen:api 타입 손실**: schema.d.ts diff에서 제거된 `interface`/`type`/멤버가 있는지, `-`행이 전부 `@description` JSDoc인지.
9. **회귀**: `pytest tests/test_application_api.py`(전수, in-memory) + `tests/test_memory_api.py`(auto-promote 우선순위 회귀). 구 `500 누수` 동작을 단정하는 테스트가 있는지 `grep "== 500"`.
10. **문서 위생**: work_log(오너 결정·근거), HANDOFF(완료 서사·머신 로컬 관찰 규칙).

## Findings

### 1. 정본 계약 (SoT v1.7.38)

- changelog 행과 본문 3문장이 구현과 일치한다. 본문 §330의 옛 "현재 매핑 지점은 … 1곳이다" 문장이 "매핑은 전역이다 / endpoint 절이 우선한다 / 60개 operation 선언, /health 제외"로 **교체**됐다(중복 적재가 아닌 갱신). `docs/` 전수 grep에서 "매핑 1곳" 잔류 없음(남은 3 hit는 무관 문서/불변 과거 검증 기록).
- **계약 내부 정합성**: "전역 503" 주장과 "endpoint 절 우선" 주장이 모순아님을 확인(우선 조항이 전역 주장의 예외로 작동). 자기모순 없음.

### 2. 중심 주장 "60/61 operation 선언, 유일 제외 /health" — **경험적 재확증**

```
TOTAL operations: 61
WITH 503: 60
WITHOUT 503: 1  -> GET /health (200/422 외 상태 없음)
```
주장 그대로. (`docs/system-contract-sot.md` v1.7.38 changelog; `main.py` handler 등록 `:1696-1714`)

### 3. 전역 handler 발화 — **다중 트랙 관통 확증 (공식 테스트 상회)**

공식 회귀 `test_storage_failure_is_503_with_the_uniform_body`는 GET /projects 1건만 실생행. 검증자 probe로 4개 트랙 11개 엔드포인트 관통:

```
GET  /projects … 503 OK        POST /projects(put_project raise) … 503 {detail}
GET  /projects/p1 … 503        PATCH/DELETE … 503        drafts/brief/memory … 503
analysis/jobs/{id} … 503       writing/loop-audits … 503
```
저장소 장애 → 균일 `{"detail": <str>}` 503. Mongo repo가 raw `PyMongoError`를 raise(감싸지 않음, memory note `mongo-repo-no-pymongo-wrapping` 부합)하므로, endpoint의 좁은 도메인 `except NotFound/Archived/CoreSotError`가 이를 잡지 못하고 전역 handler로 탈출한다.

### 4. `MemoryReindexEnqueueFailed` 별도 handler — **확증**

`memory/service.py:243`에서만 raise(mint를 실어 나름). `main.py:1701-1714`가 별도 handler로 503 매핑. 이 타입은 pymongo 계열이 아니므로 순환 등록에 포함되지 않으며, 없으면 이 경로만 500으로 남는다는 주장의 타당성 확인.

### 5. 우선순위 계약 — **auto-promote partial envelope 보존 확증**

`test_endpoint_level_mapping_still_wins_over_the_handler`: `put_memory`가 `AutoReconnect`를 raise해도 auto-promote endpoint 자체 `except _STORAGE_ERRORS`(`main.py:2738`)가 먼저 잡아 partial envelope `{auto_promotion_threshold, promoted, promotion_error}` 반환. 전역 handler가 이를 균일 본문으로 납작화하지 않는다. `test_memory_api.py` 23 passed(v1.7.35~37 회귀 전수)로 우선순위 계약 회귀 없음 확인.

### 6. mutation 실증 — **3종 각각 해당 회귀만 bite (vacuous 아님)**

```
MUT1 drop PyMongoError handler     -> GET /projects 500  (test_storage_failure_is_503… bites)
MUT2 drop EnqueueFailed handler    -> GET /projects 500  (test_reindex_enqueue_failure… bites)
```
mutation 3(/health 선언 추가)는 `test_health_does_not_declare_the_storage_503`의 단정(미선언 + 200) 구조상 자명.

### 7. lock 산술 — **+47 subtest 전량 설명**

- 4개 선언 dict 현재: Crud 20/20·Analysis 21/21·MemorySource 7/7·Writing 12/12 = **60항목 전부 503 보유**.
- 직전(`946150d^`): 503 보유 **13항목**. 13 → 60 = **47**.
- 본문-균일성 테스트(`test_every_declared_error_body_is_the_uniform_detail_model`)가 (path,method,code)마다 subtest 1개를 내므로 +47 subtest = 47 신규 503 항목과 정확히 일치. 설명되지 않은 증감 0.

### 8. gen:api 타입 손실 — **0**

schema.d.ts `-11`행이 **전부** `/** @description … */` JSDoc(저장소 문장이 덧붙은 버전으로 교체). 제거된 `interface`/`type`/멤버 **0**. `+434`는 `503: { … ErrorDetailResponse … }` 응답 블록. "타입 손실 0" 주장 성립.

### 9. `_AUTO_PROMOTE_503` 분리 / Union 가드 — **현재 상태 정확**

일반 `_STORAGE_503`(=`ErrorDetailResponse`)이 이름 충돌로 auto-promote의 Union 선언을 가릴 수 있었다는 회귀-포착 주장: 현재 `_ERRORS_404_STORAGE = {404: _ERROR, 503: _AUTO_PROMOTE_503}`(`main.py:1116`)이 Union(`Union[AutoPromotePartialResponse, ErrorDetailResponse]`)을 쓰고, `UNION_BODIES` over-strict 가드가 auto-promote 503만 Union·나머지 bare ref를 강제(실행 확인). 분리 결과 정확.

### 10. 상수·자기참조 안전성 — **확증**

- `_MIGRATION_503 = _with_storage_note(_MIGRATION_503)`(`main.py:1111`): 원 정의가 `:1021`에 먼저 존재 → 순서 의존 자기재할당이 안전(NameError 없음).
- `_with_storage_note`는 `_MIGRATION_503`·`_CONFIG_503`(`:1140`)에만 적용. `_STORAGE_503`(저장소 face 자체)·`_AUTO_PROMOTE_503`(이미 저장소 회복 문장 포함)에는 미적용 — 의도 일치.
- `test_migration_503_description_names_the_operator_action`("migrate_ordered_units.py" 포함) still passes — note가 append라 기존 설명 보존.

### 11. real-Mongo 재-raise (전역 handler 도달 전제) — **확증**

- `core_sot/mongo_repository.py:237-241`·`:466-476`: 보상 롤백 후 **`raise`**(swallow 아님).
- `analysis/mongo_repository.py:268-280`: 보상 롤백 후 duplicate→409, else **`raise`**.
- 즉 real Mongo 배포에서도 저장소 장애가 탈출해 전역 handler → 503. work_log "전부 보상 롤백이고 재-raise" 주장 정확.

### 12. 회귀 — **in-memory 전수 green, 구 500 단정 테스트 0건**

- `pytest tests/test_application_api.py`: **117 passed / 0 fail / 0 skip / 255 subtests**(전수 in-memory, Mongo 불필요).
- `pytest tests/test_memory_api.py`: **23 passed**(v1.7.35~37 partial-envelope 회귀 포함).
- `grep "== 500"` (test_application_api.py·test_memory_api.py): **0 hit** — 구 "저장소 장애=500 누수" 동작을 단정하던 테스트가 없어 500→503 전환이 기존 단정을 깨지 않는다.

### 13. 문서 위생

- work_log: Goals·**User Decisions and Rationale**(오너 "전역 handler + 선언 동시" 채택, 근거 D3=A 계약 정합 우선)·착수 전 실측·Completed·Verification·Decisions(why not wrapping)·Next 전 절 구비.
- HANDOFF: 해소된 추적 부채("auto-promote 1곳만 매핑")와 오너 결정("taxonomy 착수 여부") 행을 **삭제**(완료 서사 append 아님 — CLAUDE.md 규칙 준수). 머신 로컬 스택 상태는 "이 머신, 2026-07-24 기준"으로 명시 표기.

## Issues / Risks

### Blocking (계약 의무) — **없음**

- wire 계약 분기(storage→503 전역 / EnqueueFailed→503 / /health 미선언 / endpoint 절 우선 / 60개 선언) 전부 committed 회귀로 trace. boundary matrix의 wire-cell 빈 칸 없음.
- 선언 거짓 부분 없음: 503을 선언한 60개 operation 모두 503이 실제 도달 가능(run의 503은 config face로 도달, 아래 H3).
- opaque 500 누수 0(목표 달성).

### Hardening recommendations (non-blocking, spec을 넘는 보강 후보)

- **H1 — 드라이버 부재 분기 미검증**. `_STORAGE_ERRORS = ()`(pymongo 미설치) 시 PyMongoError handler 등록이 건너뛰어지는 분기(`main.py:1696` 순환이 0회)에 committed 회귀가 없다. wire 계약은 with-driver 케이스이므로 차단은 아니나, `create_app()`이 handler 없이도 crash 없이 뜨고 `/health`가 200임을 잠그는 1건의 가드(예: `_STORAGE_ERRORS`를 ()로 monkeypatch 후 `exception_handlers`에 `PyMongoError` 키 없음 단정)가 robustness를 확정한다.
- **H2 — runtime storage→503 committed 커버리지가 GET /projects 1건**. 선언 breadth는 60/60으로 잠겨 있으나, **runtime** 발화는 `/projects` 1건만 committed(본 검증 probe는 11개 but 비committed). 향후 어떤 endpoint가 광의 `except`로 저장소 예외를 삼키면 선언 테스트는 green인 채 500이 새고, committed runtime 테스트는 이를 잡지 못한다. parametrize 또는 트랙별 1건 샘플링 runtime 가드가 drift를 잠근다.
- **H3 — `run` endpoint의 광의 `except → 502`가 저장소 장애를 502로 재분류** (`main.py:2584-2585`, pre-existing, 본 슬라이스 비접촉). v1.7.35 D2=A가 "저장소는 502가 아닌 503, 502는 상류 실패"라고 정한 이유와 정반대 방향의 분류이나 — (a) pre-existing, (b) run은 48개 누수 대상이 아님(이미 502/503 선언), (c) opaque 500 누수 아님(502로 분류), (d) SoT 우선순위 조항("endpoint 절 우선")이 추상적으로 회복. SoT v1.7.38의 "전역 503" 주장이 run을 명시적으로 예외로 열거하지 않아 정밀도 갭이 존재한다. 권고: SoT에 run 예외 한 줄 명시, 또는 후속 슬라이스에서 `run`의 광의 catch를 좁혀 저장소→503로 통일.
- **H4 — 503 본문 `str(exc)`가 pymongo topology/연결 문자열을 노출 가능**. 프로젝트 기존 "detail=사람용" 계약 및 타 endpoint의 `str(exc)` 관행과 일치하므로 신규 위반은 아니나, 저장소 장애 detail이 내부 토폴로지를 담을 수 있음은 운영 인지 권.

## Verdict

**합격 (PASS).**

근거(loading-bearing):
1. 중심 주장 "60/61 operation, 유일 제외 /health"를 OpenAPI에서 경험적 재확증.
2. 전역 handler가 4개 트랙 다수 엔드포인트에서 균일 503 본문으로 발화함을 probe로 확증(공식 1건 상회).
3. real Mongo repo의 `except`가 전부 재-raise → real 배포에서도 전역 handler 도달 확증.
4. wire 계약 분기 전부 committed 회귀로 trace; mutation 3종 각 해당 회귀만 bite(vacuous 아님).
5. 선언 거짓 0, opaque 500 누수 0, gen:api 타입 손실 0, 기존 회귀 green(117+23), 구 500 단정 테스트 0건.
6. SoT 자기모순 없음(전역 vs 우선순위 조항 양립).

H1~H4는 모두 **non-blocking hardening/정밀도** 권고(드라이버-부재 가드·runtime 다중 가드·run 예외 명시·str(exc) 인지). 어느 것도 본 슬라이스가 만든 결함이 아니며 wire 계약을 위반하지 않는다.

## Outstanding items

- 본 슬라이스 working tree clean, HEAD `946150d`(게시 미승인 — `origin/main`보다 4 commit ahead; 오너 게시 결정 필요).
- **전체 backend suite의 1467/1/573 수치 미재실측**: 본 검증은 Mongo-의존 전수(test-mongo 기동 ~11분)를 돌리지 않았다. 단, 슬라이스-relevant 범위(`test_application_api.py` 117·`test_memory_api.py` 23, 전수 in-memory)는 green이고 슬라이스 변경이 transaction/비저장소 경로를 건드리지 않아 전수 회귀 위험은 낮다. 정본 수치 1467은 작업자 보고치(미재검증).
- dogfood 착수(GATE-1)가 남은 유일 갈림길 — 기술적 선행 조건 없음, 오너 실제 집필 필요.

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
git checkout 946150d

# 1) 중심 주장 60/61
PYTHONPATH=. python3 -c "
from services.application.app.main import create_app
s=create_app().openapi()
ops=[(p,m) for p,ms in s['paths'].items() for m in ms]
print('total',len(ops),'with503',sum(1 for p,m in ops if '503' in s['paths'][p][m]['responses']))
print('no503',[(p,m) for p,m in ops if '503' not in s['paths'][p][m]['responses']])
"

# 2) 다중 엔드포인트 저장소→503 발화 (failing core_sot)
PYTHONPATH=. python3 -c "
from pymongo.errors import AutoReconnect
from fastapi.testclient import TestClient
from services.application.app.main import create_app
from services.application.app.core_sot.service import CoreSotService
from tests.test_application_api import InMemoryCoreSotRepository
class F(InMemoryCoreSotRepository):
    def get_project(self,*a,**k): raise AutoReconnect('down')
    def list_projects(self,*a,**k): raise AutoReconnect('down')
c=TestClient(create_app(service=CoreSotService(F())))
for m,p in [('GET','/projects'),('GET','/projects/p1'),('GET','/projects/p1/drafts'),('GET','/projects/p1/memory'),('GET','/projects/p1/analysis/jobs/j1')]:
    r=c.request(m,p); print(m,p,'->',r.status_code, set(r.json()) if r.status_code!=422 else 422)
"

# 3) mutation 2종 (handler 제거 → 500 회귀)
PYTHONPATH=. python3 -c "
from pymongo.errors import PyMongoError, AutoReconnect
from fastapi.testclient import TestClient
from services.application.app.main import create_app
from services.application.app.core_sot.service import CoreSotService
from services.application.app.memory.service import MemoryReindexEnqueueFailed
from tests.test_application_api import InMemoryCoreSotRepository
class F(InMemoryCoreSotRepository):
    def list_projects(self,*a,**k): raise AutoReconnect('down')
a=create_app(service=CoreSotService(F()))
[a.exception_handlers.pop(k) for k in list(a.exception_handlers) if k is PyMongoError]
print('drop-pymongo:', TestClient(a, raise_server_exceptions=False).get('/projects').status_code)
"

# 4) 회귀 (in-memory 전수)
PYTHONPATH=. python3 -m pytest tests/test_application_api.py tests/test_memory_api.py -q
```
