# 2026-07-23 작업 로그

## Task — H3 에러 응답 계약 S1: SoT 전역 HTTP 에러 계약 섹션 신설 (문서 전용, SoT v1.7.29)

### Goals

- 2026-07-22 세션이 남긴 "Next steps (다음 세션) — **S1 착수**"를 처리한다. 브리프 `plans/api-error-response-contract-decisions.md`(D1~D4=A, 독립 검증 조건부 합격 후 F1/F2/F3 정합화 완료)의 첫 슬라이스.
- 목표는 **정본 편집 하나**다: H1(성공 `response_model`, v1.6.95)·H2(입력 검증)가 남긴 **에러 응답**의 전역 의미론을 SoT "확정된 전역 계약"에 명문화하고, 503-migration 경계와 `start_next_unit` 500 누수 부채를 정본에 기록한다.
- **범위 밖(명시)**: endpoint별 `responses=` 선언은 S2부터. 런타임 동작·프론트 에러 UX·`reason` 코드는 이번 슬라이스에서 건드리지 않는다(D4=A/D1=A).

### Completed work

- **신규 섹션 `### HTTP 에러 응답 계약`** — [`docs/system-contract-sot.md`](../../system-contract-sot.md) "확정된 전역 계약"의 `추적성` 다음, `## 서비스별 계약 SoT` 앞.
  - **본문 형태(D1=A)**: 모든 에러 응답은 균일한 단일 키 `{"detail": <string>}`(`ErrorDetailResponse`, `writing/http_models.py:158`). 상태코드별 별도 에러 스키마 없음.
  - **3층 계약**: 상태코드=기계용 의미론 · `detail`=사람용 메시지 · (후속) `reason`=기계용 코드. **`detail` 문자열 자체는 계약이 아님**(클라이언트 패턴 매칭 금지). 기계 분기가 필요해지면 detail 파싱이 아니라 `reason`을 additive로 — D1=B가 스키마 파괴 없이 들어올 자리를 이 구조가 연다(브리프 Follow-up).
  - **422는 계약 밖**: FastAPI/Pydantic 자동 생성이라 본문이 `{"detail": [ …배열… ]}`로 형태부터 다르고 자동 문서화된다.
  - **자기발견성(D3=A)**: endpoint별 realistic 코드 집합은 **OpenAPI `responses=`가 기계적 진실**이고 SoT는 의미론만 고정한다(endpoint×코드 표를 SoT에 두면 61×N 이중 관리 drift). 검증은 `python3 scripts/dump_openapi.py` 재덤프 self-discovery.
  - **상태코드 의미론 표** 400/404/409/422/502/503/504 + 동적 `ProviderError` 매핑. 각 행의 "대표 원인"은 요약이 아니라 실코드에서 재도출한 예외 이름이다.
  - **503의 두 얼굴**: (1) 협력자 미구성(`"<X> is not configured"` — 배포 구성이 바뀌어야 함) (2) 저장 데이터 마이그레이션 필요(`DraftOrderIntegrityError` — 해결책은 `scripts/migrate_ordered_units.py`, 현재 방어 3곳). 공통 규칙 = "요청을 고쳐 성공시킬 수 없고 서버 측 조치가 선행돼야 하며, 그 전의 단순 재시도는 무의미".
  - **`InvalidDraftOrder` 의도적 비대칭 명문화**: reorder(`PUT …/draft-order`)는 서브클래스가 기존 `(Archived, InvalidDraftOrder)` 절에 잡혀 **409 유지**. 지금까지 이 비대칭은 07-22 work_log와 회귀에만 있었고 정본에는 없었다. (초안의 근거 문안["요청이 전체 순열을 실어 오므로 위반이 클라이언트 입력으로 판별된다"]은 입력 오류 face에만 성립해 **독립 검증 H-2로 교정**했다 — 아래 S2 task의 검증 반영 절.)
  - **알려진 결손 명문화**: `intent=start_next_unit` accept 경로의 500 누수(H3 S5에서 503으로 폐쇄 예정)를 "정본이 승인한 동작이 아니다"라고 못박았다.
- **버전 bump**: SoT `v1.7.28 → v1.7.29`, 최근 갱신일 `2026-07-23`, 변경 이력 행 추가.

### Issues found

- 없음(코드 결손 신규 발견 없음). 다만 **브리프의 실측 숫자를 그대로 옮기지 않고 재도출**했으며, 재도출 과정에서 `503×18`의 내부 분해가 브리프에 없다는 것을 확인해 SoT/이력에 **구성 15 + 무결성 3**으로 명시했다(아래 Verification).

### Decisions (구현자 판단)

- **SoT 섹션 배치 = "확정된 전역 계약" 안**(D3=A가 지시한 위치). `구현 기술 결정`의 "타입 계약 동기화의 실제 범위"(H1/H2 기록) 옆이 아니라 전역 계약에 둔 이유: H1/H2 항목은 *어디까지 타입화됐는가*라는 진행 상태 기술이고, 이번 것은 상태와 무관하게 항상 참인 **정책**이다. 대신 섹션 서두에 H1/H2 계보와 계기(07-22 500→503 수정의 검증 H-2)를 적어 두 곳을 잇는다.
- **`구현 기술 결정` 219행(H1/H2 서술)은 수정하지 않았다** — §3 수술적 변경. 그 문단은 성공 응답 타입화 범위를 기술하며 이번 변경으로 거짓이 되지 않는다.
- **버전 bump는 patch가 아니라 신규 계약 항목으로 기록**: "계약 버전 관리"가 정본 계약 항목 추가를 bump 사유로 규정하고, 브리프 슬라이스 표도 S1 산물을 "버전 bump"로 명시한다.

### Verification

문서 전용 슬라이스이므로 CLAUDE.md §4 "Documentation-only changes" 기준 — 링크·참조·수치·우선순위 주장을 확인했다. **브리프 요약을 인용하지 않고 1차 소스(`main.py`/`core_sot/service.py`)에서 재도출**했다.

- **참조 존재 확인**: `plans/api-error-response-contract-decisions.md`, `verifications/2026-07-22/h3_error_response_contract_plan.md`, `scripts/migrate_ordered_units.py`, `scripts/dump_openapi.py` 전부 존재. `ErrorDetailResponse`는 `writing/http_models.py:158`.
- **수치 재도출**(`services/application/app/main.py`): endpoint(`@app.`) **61**, `status_code=` 리터럴 404×**62** · 400×**30** · 502×**20** · 503×**18** · 409×**16** · 504×**7**, 동적 `status_code=status`×**9**. 브리프 F1 정정(502 리터럴 20 중 1건은 partial `JSONResponse`라 에러-raise는 19)과 일치.
- **503×18 분해**(브리프에 없던 축, SoT에 새로 명시): 협력자 미구성 **15**(context search 7 · writing 6[service/gate/report/revision/revise-and-gate/accept] · analysis runner 1 · compare judge 1[`CompareJudgeNotConfigured`, detail이 `str(exc)`라 문자열 grep으로는 안 잡힘]) + 데이터 무결성 **3**(`DraftOrderIntegrityError` — `main.py:1969` list_drafts · `2090` project export · `2136` create_draft). 15+3=18로 총계 일치. **행 번호는 S1 시점(S2 선언 추가 전) 기준**이며, S2 반영 후에는 각각 2012/2139/2186으로 밀린다(독립 검증 기록의 인용과 동일 지점).
- **`start_next_unit` 500 누수 직접 확인**: `_require_ordered_drafts` 호출부 5곳 중 하나가 `core_sot/service.py:737`(= `start_next_unit`, 712행 정의) 이고, `main.py`의 `DraftOrderIntegrityError` catch는 3곳(1965/2087/2133)뿐이며 `writing_accept_endpoint`(3885~)의 except 절에는 없다. `DraftOrderIntegrityError <: InvalidDraftOrder <: CoreSotError`이고 accept가 잡는 것은 `ValueError`·`NotFound`·`Archived`·`StaleWritingBase`·writing 계열이라 **어느 절에도 걸리지 않는다** → 500. 주장 성립.
- **런타임 무변**: `git status --porcelain`이 `M docs/system-contract-sot.md` 단 하나. 코드·OpenAPI·스키마 무변이므로 테스트/`gen:api` 재실행 대상 없음(에러 선언 추가는 S2부터).

### Next steps

- **S2 착수**(아래 Task에서 이어서 완료). 이후 S3(analysis) → S4(memory/source) → S5(writing 잔여 + `start_next_unit` 503 방어).
- 이번 슬라이스는 **오너 dogfood(GATE-1) 갈림길과 무관**하다 — 계약 정직성 작업이라 dogfood와 병행 가능하다.

## Task — H3 에러 응답 계약 S2: CRUD family 20 endpoint 에러 선언 (SoT v1.7.30)

### Goals

- S1이 정본화한 전역 의미론을 **첫 endpoint 집합**에 적용한다. 대상은 브리프 lock 리스트의 **20**(H1 spine 14 + CRUD 형제 6).
- 목표는 "런타임에는 정확히 반환되지만 공개 계약에는 없던" 404·409·400·503을 OpenAPI와 프론트 생성 타입에 나타나게 하는 것. **런타임 동작은 한 줄도 바꾸지 않는다**(D4=A).

### Completed work

- **`main.py` 에러 선언 상수 7종 신설**(spine 응답 모델 바로 위): `_ERROR = {"model": ErrorDetailResponse}`를 조립한 `_ERRORS_404` · `_ERRORS_400_404` · `_ERRORS_404_409` · `_ERRORS_400_404_409` · `_ERRORS_404_MIGRATION` · `_ERRORS_400_404_MIGRATION` · `_ERRORS_404_409_MIGRATION`. 20 endpoint를 7개 상수로 덮으므로 ad-hoc dict 20개가 생기지 않는다.
  - **`_MIGRATION_503`은 별도 description을 갖는다**: CRUD family의 503은 전부 데이터 무결성 얼굴(`DraftOrderIntegrityError`)이라 "`scripts/migrate_ordered_units.py`를 실행하라, 재시도만으로는 성공할 수 없다"를 선언에 적었다. 상태코드만 적어 두면 이 페이즈가 없애려는 "로그에서 유추" 갭이 그대로 남는다.
  - `ErrorDetailResponse`를 `writing/http_models`에서 import(기존 `ACCEPT_RESPONSES` import 옆). 새 에러 모델을 만들지 않고 **단일 모델 재사용**(D1=A).
- **18개 endpoint에 `responses=` 부착**. `POST /projects`·`GET /projects`는 도메인 에러가 없어 대상 아님(20행 lock 리스트 중 이 둘은 "—"/422 자동) → 선언은 18, lock 대상은 20.
- **회귀 신규 7건**(`tests/test_application_api.py`):
  - `CrudErrorContractDeclarationTest` 4건 — (a) 20 endpoint × 선언 상태 집합 **exact** 일치(subTest 20; under-strict=선언 누락, over-strict=안 던지는 코드 선언 양방향), (b) 선언된 모든 에러 본문이 `#/components/schemas/ErrorDetailResponse` 단일 참조(subTest 30), (c) migration 503 description이 운영 조치를 명시(subTest 3 — 검증 H-3 반영 후), (d) lock 리스트 길이 20 고정.
  - `CrudErrorBodyExactKeyTest` 4건 — 404/409/400/503의 **실제 wire 본문**이 정확히 `{detail}` 단일 키 + non-empty string. 선언이 정직하려면 본문이 그래야 하고, 후속 `reason` 필드(D1=B)는 drift가 아니라 명시 결정으로만 들어와야 한다.

### Issues found

- 없음. 착수 전 브리프의 S2 코드 맵(20행)을 `main.py`에서 **재도출**했고 전 행이 실코드와 일치했다(브리프 독립 검증 결과와도 일치).

### Decisions (구현자 판단)

- **선언 대상에서 422 제외**: FastAPI가 자동 문서화하고 본문 형태(`{"detail": [ … ]}`)가 다르다 — S1이 정본에 못박은 경계를 그대로 따랐다.
- **`responses=` 상수를 `main.py`에 두고 `writing/http_models.py`로 옮기지 않았다**: 후자는 writing 도메인 모듈이고 CRUD 계열이 거기 의존을 늘릴 이유가 없다. 공유하는 것은 `ErrorDetailResponse` 하나뿐이며 이미 그쪽이 정의처다.
- **503 description만 개별화**: 나머지 코드는 전역 의미론(SoT 표)으로 충분하고 endpoint마다 문장을 쓰면 SoT와 이중 관리가 된다. 503은 "서버 측 조치 선행"이라 **어떤 조치인지**가 없으면 실행 불가능한 정보라 예외.

### Verification

- **OpenAPI self-discovery**: `create_app().openapi()`를 재덤프해 20 endpoint의 선언 집합(200/422 제외)이 기대와 정확히 일치함을 확인(mismatch 0). 코드가 emit할 의도가 아니라 실제 스펙을 읽었다.
- **mutation 3종 실증(양방향)**:
  - project-export 선언에서 503 제거 → `test_migration_503_description_names_the_operator_action` SUBFAIL(under-strict).
  - `_ERRORS_404`에 아무도 안 던지는 502 추가 → `test_declared_error_statuses_match_the_lock_list` SUBFAIL(over-strict).
  - `_MIGRATION_503`의 모델을 다른 모델로 교체 → `test_every_declared_error_body_is_the_uniform_detail_model`이 503 3곳에서 SUBFAIL.
- **런타임 불변**: backend 전체 **1379 passed / 41 skipped / 384 subtests**(`CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`). 기존 상태코드 회귀(`LegacyOrderedDraftMigration503Test`의 503 3종·reorder 409 유지 포함) 전부 green.
- **프론트 타입**: `npm run gen:api` → `schema.d.ts` **+270행 / -0행**(순수 additive), `npx tsc --noEmit` clean, `npm run build` 성공(JS 399.03 kB), frontend **194 passed / 13 files**(프론트 소스 무변).
- **변경 표면**: `main.py`(선언만), `tests/test_application_api.py`, `schema.d.ts`(생성물), SoT/HANDOFF/work_log. 서비스 로직·프론트 소스 0줄.

### 오너 독립 검증 PASS + 비차단 hardening 반영

- **오너 독립 검증 합격(조건 없음)**: `docs/verifications/2026-07-23/h3_error_response_contract_s1_s2.md`. 경계 매트릭스 빈 cell 없음. 검증자가 **18 endpoint 선언 == 실제 raise 집합을 endpoint 본문 직독으로 양방향 재확인**했고(테스트는 OpenAPI==EXPECTED만 pin하므로 EXPECTED 자체의 정확성은 코드 직독이 authority), 503×18의 15+3 분해·`InvalidDraftOrder` 비대칭 실재·`start_next_unit` 500 누수 실재·SoT 동기부여 수치 7종·런타임 무변 수치를 전부 1차 소스에서 재도출해 성립을 확인했다.
- **H-1(문서 오기) 반영**: body-model 테스트 subTest 수를 27→**30**으로 정정(총 52는 정확했다). 실측 재확인: 선언 exact 20 + body-model 30 + migration description 3 = **53**(H-3 반영 후).
- **H-2(근거 정밀도) 반영 — SoT 문안 교체**: reorder 비대칭의 원 근거("위반이 클라이언트가 보낸 순열로 판별")는 **입력 오류 face에만** 성립한다. `reorder_drafts`는 `_require_ordered_drafts(current)`를 **순열 검사보다 먼저** 호출하므로([core_sot/service.py:504](../../../services/application/app/core_sot/service.py#L504)) legacy 데이터에서는 입력과 무관하게 무결성 에러가 먼저 발생하고 기존 절에 흡수되어 409가 된다. SoT 문안을 "reorder의 409는 입력 오류 face에 대해서만 정확한 의미론이고, 무결성 face에서는 07-22 수정이 500 누수만 닫는 수술적 범위를 지킨 **무변경의 결과**이며, 503 재분류는 별도 개정 사항"으로 좁혔다. **행동·선언은 원래 정확했고 바뀌지 않았다** — 다음 검증자의 오독을 막는 근거 문안 교정이다.
- **H-3(테스트 보강) 반영**: migration description subTest가 list/export 2곳만 직접 pin하고 create는 같은 상수를 쓴다는 이유로 간접 검증이었다. `(path, method)` 쌍으로 바꿔 **`POST …/drafts`를 3번째로 직접 pin**했다(subTest 2→3). 상수 공유는 구현 세부이지 계약이 아니므로, 계약이 요구하는 3곳은 3곳 다 명시적으로 잠근다.
- **H-4(구조 관찰)**: 조치 없음. "EXPECTED == 실제 raise"를 AST로 자동 대조하는 것은 현재 20 endpoint 규모에서 과설계이고(§2), 검증자도 "현재 충분"으로 판단했다. S3~S5로 대상이 늘어 직독 대조 비용이 커지면 그때 재평가한다.

### Next steps

- **S3(analysis 트랙)**: analysis jobs/candidates/context/compare/apply/review-queue/review-inbox/gate-findings. S2와 달리 **동적 `ProviderError` 매핑 지점이 섞여** 있어 endpoint별 realistic 집합만 선언하고 전체 열거는 하지 않는다(브리프 스코프 밖 명시).
- 이후 S4(memory/source) → S5(writing 잔여 + `start_next_unit` 503 방어 = SoT v1.7.29가 "알려진 결손"으로 기록한 500 누수 폐쇄).
- **주의**: S3 이후 구역은 `response_model`이 없는 무타입 endpoint가 많다(아래 Mongo skip 규명 task 이후에도 동일).(`dict[str, object]`). 에러 선언은 성공 모델과 독립이므로 `response_model` 부착을 함께 하려는 유혹을 피할 것 — 그건 H1의 잔여 범위이고, 섞으면 silent field loss 위험(§v1.6.95)이 이 페이즈로 들어온다.

## Task — 백엔드 스위트 Mongo skip 41건 원인 규명 (오너 질문: "포트 고정이 안 되었나?")

### Goals

- 오너가 "skip 나는 건 포트 번호 고정으로 처리했던 기억"이라고 지적. 실제로 무엇이 왜 skip되는지 **사유를 직접 뽑아** 확인하고, 고정이 풀린 것인지 다른 축인지 판별한다.

### Issues found

- **문제**: 백엔드 전체 실행이 계속 `41 skipped`. 기존 관행 URI(`CORE_SOT_TEST_MONGO_URI=mongodb://localhost:27018`)를 써도 그대로였다.
- **원인 — 축이 두 개인데 하나로 섞여 있었다**(`pytest -rs`로 사유 집계):
  - **41 = replica set 필요 40 + Chroma live 1**. Mongo가 압도적이라는 오너 직감은 정확했다.
  - **축 1(인증)**: 기본 27017 = `shared-mongo`(외부 프로젝트 컨테이너)는 인증 필수라 `test_memory_mongo`가 write `Unauthorized(code 13)`로 **FAILED**했다. **27018 고정이 고친 것이 이 축이고, 지금도 유효하다**(failed 0).
  - **축 2(replica set)**: 27018(`agent-memory-mongodb`)은 `db.hello().setName`이 없는 **standalone**이라 트랜잭션 미지원 → `test_core_sot_mongo.py`/`test_analysis_mongo.py` **40건이 skip**. **포트를 고정해도 standalone인 한 이 축은 안 풀린다** — 고정이 풀린 게 아니라 애초에 다른 문제를 고친 것이었다.
  - **HANDOFF에 적혀 있던 RS 절차가 이 머신에서 막힌 이유**: RS를 주는 것은 프로젝트 자신의 `mongo` 서비스(`--replSet rs0`)인데 그 멤버가 **`mongo:27017`로 광고**돼, 호스트에서 붙으려면 27017 게시 + `/etc/hosts`에 `mongo`→127.0.0.1이 필요하다. 실측: 호스트 **27017은 `shared-mongo`가 점유**, `/etc/hosts`에 `mongo` 매핑 **없음**, 프로젝트 `mongo` 컨테이너 **미기동**. 세 조건이 겹쳐 RS 경로가 성립하지 않았고, 그래서 27018 standalone이 관행이 되며 skip 40이 상수처럼 남았다.

### Completed work

- **작동하는 우회 확인**(기존 컨테이너·프로젝트 `mongo_data` 볼륨 **무손상**): 멤버를 `localhost:PORT`로 광고하는 **일회용 단일노드 RS**를 빈 포트(27020)에 띄우면 `/etc/hosts`도 27017도 필요 없다.

  ```bash
  docker run -d --name awt-test-rs -p 27020:27020 mongo:7 --replSet rs1 --bind_ip_all --port 27020
  docker exec awt-test-rs mongosh --quiet --port 27020 --eval \
    'rs.initiate({_id:"rs1", members:[{_id:0, host:"localhost:27020"}]})'
  CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27020/?replicaSet=rs1" python3 -m pytest -q -p no:cacheprovider
  ```

- **결과**: **1419 passed / 1 skipped / 0 failed / 384 subtests**(9분 15초). 27018 대비 **+40 passed**. 남은 skip 1건은 Chroma live 테스트로, 서버는 8001에 떠 있으나 **호스트에 `chromadb` 패키지가 없고 `CHROMA_TEST_URL`도 미설정**이라 나는 것이다(패키지 설치는 요청 범위 밖이라 손대지 않음).
- **부수 효과(검증 강화)**: H3 S1/S2 검증 당시 수치(1379/41)는 트랜잭션 40건이 **미실행**인 상태였다. 이번 실행으로 그 40건까지 포함해 **전부 green**임이 확인됐다 — S2의 선언 추가가 트랜잭션 경로에 영향 없음을 실측으로 닫았다.
- HANDOFF에 "백엔드 테스트 Mongo — skip 0으로 돌리는 법" 항을 신설하고, 막혀 있던 종전 절차(W3 live 축 항의 `27017/?replicaSet=rs0`)를 그 항으로 리다이렉트했다.

### Decisions (구현자 판단)

- **프로젝트 `mongo` 서비스의 `rs0`를 `localhost`로 `rs.reconfig`하지 않았다**: 그 설정은 `mongo_data` 볼륨에 **영속**되어 이후 compose 스택(application이 `mongo:27017`로 접속)이 깨진다. 일회용 컨테이너는 그 위험이 없고 `docker rm -f`로 원상복구된다.
- **`shared-mongo`를 내리지 않았다**: 이 프로젝트 소유가 아닌 컨테이너라 임의 중단은 범위 밖이다.
- **`chromadb` 설치·`scripts/` 헬퍼 추가는 하지 않았다**(§2 — 요청 없는 인프라/의존성 추가 없음). 절차를 HANDOFF에 고정하고 스크립트화 여부는 오너 판단으로 남겼다.

### Next steps

- **오너 판단 대기**: 이 RS 절차를 `docker-compose.test.yml`이나 `scripts/`로 고정할지. 고정하면 "skip 41"이 매 세션 재발하지 않는다.
- 일회용 컨테이너 `awt-test-rs`는 **현재 떠 있다**. 불필요하면 `docker rm -f awt-test-rs`.
- Chroma live 1건을 0으로 만들려면 호스트에 `pip install chromadb` + `CHROMA_TEST_URL=http://localhost:8001`가 필요하다(오너 결정 사항).

## Task — 테스트 Mongo 고정: 전용 포트 단일노드 RS를 compose로 승격 (오너 결정 "고정해버려")

### Goals

- 앞 task가 규명한 replica-set 축을 **일회성 우회가 아니라 리포지토리 자산으로 고정**한다. 오너 결정: "고정해버려. 포트 변경하는게 큰 문제는 아니니까. 별도 포트 사용하면 뭐 더 좋지. 다른 프로젝트랑 안겹칠꺼아녀" — 전용 포트 채택.
- 성공 기준: **env 변수 없이 `python3 -m pytest -q`만으로 Mongo skip 0**.

### User Decisions and Rationale

- **오너 결정 = 전용 포트로 영구 고정**. 근거(오너): 포트 변경 비용이 작고, 전용 포트를 쓰면 다른 프로젝트(`shared-mongo`·`agent-memory-mongodb`)와 구조적으로 겹치지 않는다. 이 결정으로 "27017을 누가 점유했나"에 의존하던 취약한 절차가 사라진다.

### Completed work

- **신규 [`docker-compose.test.yml`](../../../docker-compose.test.yml)** — `test-mongo` 서비스:
  - `mongo:7`, `--replSet rs-test --bind_ip_all --port ${TEST_MONGO_PORT:-27020}`, **컨테이너 포트 = 게시 포트**(멤버가 `localhost:<port>`로 등록되므로 discovery 후 호스트 드라이버가 재접속하는 주소와 일치해야 한다).
  - healthcheck가 `rs.initiate`를 **멱등** 수행하고 **writable PRIMARY일 때만 healthy**를 보고한다(`quit(db.hello().isWritablePrimary ? 0 : 1)`). `rs.initiate()`는 선거 완료 전에 ok=1을 돌려주므로, 그것만 보고 healthy를 주면 write가 `NotWritablePrimary`로 깨지는 창이 생긴다.
  - **볼륨 없음**(의도): 테스트 DB는 throwaway라 컨테이너 레이어로 충분하고, `down`이 잔여물을 남기지 않으며 배포 스택의 `mongo_data`와 충돌할 수 없다.
  - **오버레이가 아니라 독립 파일**: 테스트 인프라는 배포의 일부가 절대 아니므로 `-f docker-compose.test.yml`을 명시해야만 뜬다(`docker compose up`으로 실수 기동 불가). 선례 = `docker-compose.llama.yml`.
- **테스트 기본 URI 변경** — `tests/test_core_sot_mongo.py`·`test_analysis_mongo.py`·`test_memory_mongo.py`의 기본값을 `mongodb://localhost:27017` → **`mongodb://localhost:27020/?replicaSet=rs-test`**로, 기본값이 아예 없던 `test_indexing_mongo.py`에도 동일 기본값을 부여했다. **env 변수를 기억할 필요가 없어진 것이 이번 고정의 본질**이다(`CORE_SOT_TEST_MONGO_URI`는 override로 계속 동작). `test_core_sot_mongo.py` 모듈 docstring도 새 절차와 "standalone을 가리키면 40건이 조용히 skip된다"는 함정을 명시하도록 갱신.

### Issues found

- **fd 한도 1024 → mongod 실행 중 fatal crash**: 고정 직후 재현 실행에서 `19 failed / 1 error`가 났다. 원인은 코드가 아니라 **`Too many open files`(EMFILE)** — 스위트가 테스트마다 throwaway DB를 만들고 지워 WiredTiger가 파일 핸들을 대량으로 돌리는데, Docker 기본 soft `nofile`이 1024다. mongod 자신이 기동 시 `Soft rlimits for open file descriptors too low (currentValue 1024, recommendedMinimum 64000)`를 경고하고 있었고, 한도에 닿자 `WT_PANIC: __posix_directory_sync … Too many open files` → `fassert` → **exit 14로 프로세스 사망**했다.
  - **이 함정의 위험은 증상이 skip이 아니라 failure라는 점**이다. 인프라 한도 문제인데 코드 회귀처럼 보인다.
  - **조치**: `test-mongo`에 `ulimits.nofile {soft: 64000, hard: 64000}` 명시(주석에 근거 기록). 적용 후 컨테이너 내부 `ulimit -Sn` = 64000, mongod 경고 **0건**.
- **[패턴 스윕 → 추적 부채] 배포 `mongo` 서비스에도 `ulimits`가 없다**(`docker-compose.yml`의 `mongo:`). 같은 1024 soft 한도라 **같은 fatal 크래시 조건을 구조적으로 공유**한다. 배포는 DB가 하나뿐이라 아직 도달하지 않았을 뿐이며, dogfood가 길어지거나 색인/분석이 쌓이면 재현 가능하다. 4줄로 닫히지만 **실행 중 스택의 컨테이너 재생성**이 필요해 이번 범위에서 제외하고 HANDOFF에 부채로 등록했다 — 오너 판단 사항.

### Verification

- **성공 기준(env 없이 skip 0)**: `python3 -m pytest -q -p no:cacheprovider` → **1419 passed / 1 skipped / 0 failed / 384 subtests**. 종전 27018(standalone) 대비 **+40 passed**이며, 남은 skip 1건은 Chroma live(호스트에 `chromadb` 미설치 + `CHROMA_TEST_URL` 미설정)다.
- **양방향 확인 — 미기동 시 실패가 아니라 skip**: `docker compose -f docker-compose.test.yml down` 상태에서 두 mongo 테스트 파일을 돌려 **61 skipped / 0 failed**를 확인했다. 인프라 부재가 회귀로 오인되지 않는다는 기존 계약(모듈 docstring)이 새 기본값에서도 유지된다.
- **healthcheck 계약**: healthy 도달 시점에 `db.hello().isWritablePrimary` = true, `setName` = `rs-test`, primary = `localhost:27020`.
- **fd 조치 확인**: 컨테이너 `ulimit -Sn` 64000, mongod 기동 경고 0건, 조치 후 전체 스위트에서 컨테이너 사망·재시작 0.
- `docker compose -f docker-compose.test.yml config --quiet` 통과. 배포 `docker-compose.yml`은 **무변**.

### Decisions (구현자 판단)

- **배포 `mongo`의 호스트 게시 포트는 바꾸지 않았다**: 앱 컨테이너는 도커 네트워크 내부에서 `mongo:27017`로 접속하므로 테스트용 포트와 무관하고, 게시 포트 변경은 이번 문제를 풀지 않는다(§3 수술적). `shared-mongo`와의 27017 충돌은 필요할 때 `MONGO_PORT`로 조정한다.
- **`chromadb`를 설치하지 않았다**: 호스트 의존성 추가는 요청 범위 밖이며 skip 1건은 정직한 신호다(§2).
- **테스트 기본값을 바꾼 것이 핵심**이고 compose 파일만 추가하는 것으로는 부족하다고 판단했다 — 재발 원인이 "절차를 기억해야 한다"였기 때문이다. 이제 잊어도 skip일 뿐 잘못된 green이 되지 않는다.

### Next steps

- **오너 판단 대기**: 배포 `mongo`에도 `ulimits.nofile`을 넣을지(위 추적 부채). 넣는다면 스택 재기동이 필요하다.
- Chroma live 1건을 0으로 만들려면 `pip install chromadb` + `CHROMA_TEST_URL=http://localhost:8001`.
- 이제 백엔드 회귀 보고의 기준선은 **1419 passed / 1 skipped**다. 이전 로그의 "1379 passed / 41 skipped"는 standalone 기준이므로 직접 비교하지 말 것.

---

## Task — H3 에러 응답 계약 S3: analysis 트랙 21 endpoint 에러 선언 (SoT v1.7.31)

### Goals

- S2가 CRUD family에 적용한 관용구를 **analysis 구역**에 확장한다. 대상은 브리프 S3 행의 트랙 전체 — jobs/candidates/context/compare/apply/review-queue/review-inbox/gate-findings.
- 런타임은 한 줄도 바꾸지 않는다(D4=A). 선언만 추가해 404·409·400·**502·503**이 OpenAPI·프론트 생성 타입에 나타나게 한다.

### Completed work

- **대상 21 endpoint 확정 — 브리프가 아니라 `main.py` 본문 직독으로 도출**. 각 endpoint의 `except` 절을 읽어 realistic 집합을 세웠다:
  - `{404}` 11곳 (jobs create/get/candidates·auto-promote·context·promote·review-queue·review-inbox 2·gate-findings 2)
  - `{404,409}` 6곳 (jobs retry·confirm·reject·reconcile·gate-finding resolve/dismiss)
  - `{400,404,409}` 1곳 (candidate edit) · `{400,404}` 1곳 (apply)
  - `{404,502,503}` 1곳 (compare) · `{400,404,409,502,503}` 1곳 (run)
- **신규 상수 3종**: `_CONFIG_503` + `_ERRORS_404_502_CONFIG`(compare) + `_ERRORS_400_404_409_502_CONFIG`(run). **나머지 19곳**은 S2 상수를 그대로 재사용했다(`_ERRORS_404` 11 · `_ERRORS_404_409` 6 · `_ERRORS_400_404_409` 1 · `_ERRORS_400_404` 1 = 19, 신규 상수 endpoint 2곳을 더해 21).
- **503 두 얼굴의 description 분리**: S1이 정본화한 구분(구성 15곳 vs 무결성 3곳)이 이번에 처음으로 **선언 표면에서** 갈린다. `_CONFIG_503`은 "협력자 미구성 → 배포 환경에서 구성하라"를 적고 `migrate_ordered_units.py` 문안을 쓰지 않는다.
- **회귀 신규 9건**(`tests/test_application_api.py`):
  - `AnalysisErrorContractDeclarationTest` 4건 — (a) 21행 exact lock(subTest 21, 양방향), (b) **트랙 전수 선언**(spec의 `/analysis/` operation 중 lock 리스트에 없는 것이 0), (c) 본문 단일 `ErrorDetailResponse` 참조(subTest **36** = 21행의 선언 코드 총합), (d) config 503 description 문안(subTest 2 — present 2 + migration 문안 부재). 합계 21+36+2 = **59 subtest**.
  - `AnalysisErrorBodyExactKeyTest` 5건 — 404/409/400/**502**/**503**의 실제 wire 본문이 정확히 `{detail}` 단일 키. S2가 닿지 못한 502·503-config를 이번에 잠갔다.

### Issues found

- 없음. 다만 브리프의 S3 경고("동적 `ProviderError` 매핑이 섞여 있다")는 **analysis 구역에는 실제로 해당하지 않았다** — 이 구역의 `ProviderError`는 `run`·`compare` 두 곳 모두 **명시 502 분기**이고, `status_code=status` 동적 매핑 9곳은 전부 writing 구역(S5)에 있다. 실코드 확인 결과이며 스코프 축소가 아니라 경고가 발화하지 않은 것이다.

### Decisions (구현자 판단)

- **`_CONFIG_503` 상수 1개를 두 endpoint가 공유**한다(endpoint별 문안으로 쪼개지 않음): 어떤 협력자가 빠졌는지는 런타임 `detail`이 이미 이름을 대고, 운영 조치("배포 환경에서 구성")는 두 곳이 동일하다. S2가 503만 개별화한 근거는 "조치가 없으면 실행 불가능한 정보"였는데 그 조치가 같으면 문안을 나눌 이유가 없다.
- **트랙 전수 선언 테스트를 추가**했다(S2에는 없던 축). S2는 20행 lock으로 충분했지만, S3는 "트랙을 닫았다"는 주장을 하므로 **lock 리스트 자체의 over-strict 가드**가 필요하다 — 신규 analysis endpoint가 선언 없이 실리면 21행은 여전히 green이지만 closure 주장은 거짓이 된다.
- **성공 `response_model`을 붙이지 않았다**: 이 구역은 무타입 endpoint(`dict[str, object]`)가 대부분이라 유혹이 크지만 H1 잔여 범위이고, 섞으면 silent field loss 위험(v1.6.95)을 이 페이즈로 끌어온다. S2 work log의 경고를 그대로 지켰다.

### Verification

- **OpenAPI self-discovery**: `create_app().openapi()` 재덤프로 21 endpoint의 선언 집합(200/422 제외)이 코드 직독 도출과 정확히 일치함을 확인(mismatch 0).
- **mutation 4종 실증(양방향)**:
  - compare의 `responses=` 삭제 → 선언 exact·본문 모델·config description 3개 회귀가 해당 endpoint에서만 SUBFAIL(under-strict).
  - `_ERRORS_404_502_CONFIG`에 아무도 안 던지는 504 추가 → `test_declared_error_statuses_match_the_lock_list`가 compare에서 SUBFAIL(over-strict).
  - `_CONFIG_503` 모델을 `dict`로 교체 → 본문 단일 모델 회귀가 run·compare 두 503에서 SUBFAIL.
  - lock 리스트에 없는 `/analysis/brand-new` endpoint 추가 → `test_the_whole_analysis_track_is_declared` FAIL(트랙 전수 가드가 실제로 문다).
- **런타임 불변**: backend 전체 **1428 passed / 1 skipped / 0 failed / 443 subtests**(전용 `docker-compose.test.yml` test-mongo 27020 RS). 직전 기준선 1419/1/384 대비 +9 test·+59 subtest = 이번 신규분과 정확히 일치하고, analysis 상태코드 회귀(run의 400/409/502/404/503 5종 등) 전부 green.
- **프론트 타입**: `npm run gen:api` → `schema.d.ts` **+324행 / -0행**(순수 additive), `npx tsc --noEmit` clean, `npm run build` 성공(JS 399.03 kB — S2와 동일, 프론트 소스 무변), frontend **194 passed / 13 files**.
- **변경 표면**: `main.py`(선언·상수만), `tests/test_application_api.py`, `schema.d.ts`(생성물), SoT/HANDOFF/work_log. 서비스 로직·프론트 소스 0줄.

### Next steps

- **S4(memory/source)**: memory read 2, snapshots/source-refs/index-rebuild, context-search.
- 이후 **S5**(writing 잔여 + `start_next_unit` 503 방어 = SoT v1.7.29가 "알려진 결손"으로 기록한 500 누수 폐쇄). **동적 `ProviderError` 매핑 9곳은 전부 이 구역에 있다** — 브리프의 "realistic 집합만 선언" 경고가 실제로 발화하는 곳은 S5다.

### 오너 독립 검증 PASS + 비차단 반영

- **오너 독립 검증 합격(조건 없음)**: `docs/verifications/2026-07-23/h3_s3_analysis_error_responses.md`. 경계 매트릭스 **21/21 빈 cell 없음**. 검증자가 지적한 authority 관계가 정확하다 — D3=A라 SoT엔 endpoint×코드 표가 없고, 테스트는 `OpenAPI == EXPECTED`만 pin하므로 **EXPECTED 자체의 정확성은 endpoint 본문 직독이 권위**다. 검증자가 21 endpoint를 전수 직독해 선언 집합 == 실제 매핑 raise 집합을 양방향 재확인했고, mutation 4종·OpenAPI self-discovery·수치(1428/1/443 · +324/-0 · 399.03 kB · 194/13)를 전부 재실행해 일치를 확인했다.
- **비차단 1 반영 — 문서 수치 오기 2건 정정**(코드·테스트·스키마는 정확했고 aggregate도 맞았다):
  - "나머지 **18** endpoint 재사용" → **19**. 재도출: `_ERRORS_404` 11 + `_404_409` 6 + `_400_404_409` 1 + `_400_404` 1 = 19, 신규 상수 2(run·compare) = 21. work_log·SoT changelog 양쪽 정정.
  - "body-model subTest **31**" → **36**(= 21행의 선언 코드 총합 11+12+3+2+3+5). 31이면 총계가 54가 되어 실측 59와 모순됐다. work_log 정정 + 21+36+2=59 산식을 명시.
- **비차단 2 반영 — 사전 존재 미매핑 500 경로를 추적 부채로 등록**: `auto_promote_job` 승격 루프·일부 list 호출이 `try` 밖이라 예외 시 500이 샌다. **S3 비관여**(선언만 추가, 구조 무변; SoT가 500을 "승인 안 된 알려진 결손"으로 분류하므로 선언 계약 위반 아님)이나 `start_next_unit` 500 누수와 동일 부류라 HANDOFF 추적 부채에 **S5 점검 후보**로 등록했다. 검증자 판단대로 이번 슬라이스에서 고치지 않았다 — 구조 변경은 S3 스코프(D4=A 선언 전용) 밖이다.

---

## Task — H3 에러 응답 계약 S4: memory/source 트랙 7 endpoint 에러 선언 (SoT v1.7.32)

### Goals

- 브리프 S4 행(memory read 2 · snapshots/source-refs · index-rebuild · context-search)에 S2/S3 관용구를 적용한다.
- 런타임 0줄 변경(D4=A). 선언만 추가해 400·404·502·503·**504**가 OpenAPI·프론트 생성 타입에 나타나게 한다.

### Completed work

- **대상 7 endpoint 확정 — `main.py` 본문 직독으로 도출**:
  - `{404}` 5곳 (memory list/get · source-ref list/get · index rebuild)
  - `{400,404}` 1곳 (source-ref create — `except NotFound` 뒤 `except CoreSotError → 400` 순서라 두 갈래가 실제로 분기한다)
  - `{400,404,502,503,504}` 1곳 (context-search)
- **신규 상수 1종만**: `_ERRORS_400_404_502_504_CONFIG`. 나머지 6곳은 기존 상수 재사용(`_ERRORS_404` 5 · `_ERRORS_400_404` 1). context-search의 503은 구성 얼굴이라 S3의 `_CONFIG_503`을 그대로 쓴다.
- **504가 writing 밖 endpoint로는 처음 선언된다**: `context-search`는 writing 트랙 밖에서 자기 예산을 소진할 수 있는 유일한 endpoint(`ContextSearchBudgetExceeded` → 504)다. **504 선언 자체가 처음인 것은 아니다** — `writing/accept`·`writing/revise-and-gate`는 H3 이전부터 에러 본문 모델과 함께 504를 선언해 왔다(브리프 "에러 본문 모델을 선언한 건 2개뿐" 항).
- **회귀 신규 9건**:
  - `MemorySourceErrorContractDeclarationTest` 4건(`tests/test_application_api.py`) — (a) 7행 exact lock(subTest 7, 양방향), (b) **트랙 전수 선언 가드**(`/memory`·`/snapshots/`·`/source-refs`·`/context-search` 경로 중 lock 리스트 밖 operation이 0), (c) 본문 단일 모델(subTest 12), (d) context-search 503이 구성 얼굴 문안이고 migration 문안을 차용하지 않음.
  - `MemorySourceErrorBodyExactKeyTest` 2건(동 파일) — 404·400 wire 본문 `{detail}` 단일 키.
  - **`ContextSearchErrorBodyExactKeyTest` 3건**(`tests/test_context_search_api.py`) — 502·503·**504** 본문.

### Issues found

- 없음.

### Decisions (구현자 판단)

- **502/503/504 본문 락을 `test_context_search_api.py`에 두고 `test_application_api.py`로 모으지 않았다**: 이 셋을 발화시키려면 planner·clock·budget 픽스처(`_fixture`/`_FailingPlanner`/`_AdvancingClock`)가 필요한데 그 하네스는 이미 그 파일에 있다. S4 락을 한 파일에 모으려고 하네스를 복제하는 것이 더 나쁜 거래라고 판단했다(§2·§3). 선언 테스트는 `openapi()`만 있으면 되므로 S2/S3 옆에 그대로 뒀다.
- **`index/source-blocks/rebuild`는 `{404}`만 선언**: `_rebuild_source_block_index_payload`가 vector index·embedding 협력자를 쓰지만 endpoint가 잡는 것은 `NotFound` 하나뿐이라 나머지는 500이다. 안 잡는 코드를 선언하면 over-strict 거짓말이 된다(D4=A는 선언만 추가하지 매핑을 새로 만들지 않는다). 미매핑 500은 S5 점검 부채와 같은 부류로 남는다.
- **`create_source_ref`의 400을 확인하고 선언했다**: `except NotFound`가 `except CoreSotError`보다 먼저라 NotFound는 404로 빠지고 나머지 `CoreSotError`(범위 초과 offset 등)가 400이 된다. 순서가 뒤집히면 400이 도달 불가가 되므로 wire 본문 테스트가 실제 400을 발화시켜 이를 잠근다.

### Verification

- **OpenAPI self-discovery**: `create_app().openapi()` 재덤프로 7 endpoint의 선언 집합(200/422 제외)이 코드 직독 도출과 정확히 일치(mismatch 0).
- **mutation 4종 실증(양방향)**:
  - context-search `responses=` 삭제 → 선언 exact·본문 모델·503 문안 회귀가 SUBFAIL/FAIL(under-strict).
  - `GET …/memory`가 안 던지는 409 선언 → `test_declared_error_statuses_match_the_lock_list`가 memory에서만 SUBFAIL(over-strict).
  - context-search 503을 `_MIGRATION_503`으로 교체 → `test_context_search_503_uses_the_configuration_face` FAIL(두 얼굴 혼입 차단이 실제로 작동).
  - lock 리스트에 없는 `/projects/{id}/memory-stats` 추가 → 트랙 전수 가드 FAIL.
  - 각 mutation 후 revert·잔류 0 확인(`grep`으로 mutation 시그니처 0건).
- **런타임 불변**: backend 전체 **1437 passed / 1 skipped / 0 failed / 462 subtests**. 직전 기준선 1428/1/443 대비 +9 test·+19 subtest = 이번 신규분과 정확히 일치. 기존 context-search 상태코드 회귀(400/404/502/503/504)는 전부 사전 존재분이며 그대로 green.
- **프론트 타입**: `gen:api` → `schema.d.ts` **+108행 / -0행**(순수 additive), `npx tsc --noEmit` clean, `npm run build` 성공(JS 399.03 kB, S2/S3와 동일 — 프론트 소스 무변), frontend **194 passed / 13 files**.
- **변경 표면**: `main.py`(선언·상수만), `tests/test_application_api.py`, `tests/test_context_search_api.py`, `schema.d.ts`(생성물), SoT/HANDOFF/work_log. 서비스 로직·프론트 소스 0줄.

### Next steps

- **S5(마지막 슬라이스)**: writing 잔여(generate[202 success만 선언됨]·generation-jobs·gate·report·revise·loop-audits·scratch — 에러 본문 기선언 2[revise-and-gate·accept]는 제외) **+ `start_next_unit` 503 방어**(SoT v1.7.29가 "알려진 결손"으로 기록한 500 누수 폐쇄).
- **S5에서 처음 실제로 발화하는 것들**: (1) 동적 `ProviderError` 매핑 9곳이 전부 이 구역이라 "realistic 집합만 선언, 전체 열거 안 함" 스코프가 여기서만 의미를 갖는다. (2) S3 검증이 남긴 미매핑 500 부채(`auto_promote_job` 등)와 S4의 index-rebuild 미매핑 경로를 `start_next_unit` 방어와 함께 점검한다.

### 오너 독립 검증 PASS + 비차단 반영

- **오너 독립 검증 합격(조건 없음)**: `docs/verifications/2026-07-23/h3_s4_memory_source_error_responses.md`. 경계 매트릭스 **7/7 빈 cell 없음**(7 endpoint 본문 직독으로 선언 집합 == 실제 매핑 raise 집합 양방향 재확인). mutation(over-strict 409·트랙 closure)·OpenAPI self-discovery(**TRACK 조각이 정확히 7개만 매칭** — 과잉/과소 없음을 별도로 확인)·수치(1437/1/462 · +108/-0 멱등 · 399.03 kB · 194/13) 전부 재실행 일치. 구현자 판단 2건(rebuild `{404}`-only, 본문 락 파일 배치)도 건전 판정.
- **비차단 1 반영 — "504 처음" 과장 문안 정정**: 검증자 지적이 맞다. `writing/accept`·`writing/revise-and-gate`는 **H3 이전부터** 에러 본문 모델과 함께 504를 선언해 왔다(브리프 "에러 본문 모델을 선언한 건 2개뿐" 항). OpenAPI 덤프에서 504 선언 endpoint가 이 둘 + context-search **3개**임을 직접 재확인했다. 정확한 문장은 **"writing 트랙 밖 endpoint로는 처음"**이며 SoT changelog·HANDOFF·work_log 3곳을 그렇게 고쳤다. **실질 주장(context-search = writing 밖 유일 예산 endpoint)과 선언 자체는 처음부터 정확했다** — 문안만 과장이었다.
  - **커밋 메시지(f0b1d15)는 고치지 않았다**: amend는 해시를 바꿔 검증 기록이 인용한 `f0b1d15`를 무효화한다. 히스토리를 다시 쓰는 대신 정정을 후속 커밋과 이 항목에 남기는 쪽이 감사 추적에 정직하다.
- **비차단 2 — rebuild 미매핑 500**: 사전 존재이고 S3의 `auto_promote_job`과 동일 부류다. HANDOFF 추적 부채에 이미 등록돼 있으며 S5에서 `start_next_unit` 방어와 함께 점검한다. 이번 슬라이스에서 고치지 않은 이유는 위 Decisions 항(D4=A 선언 전용 스코프)과 같다.

---

## Task — H3 에러 응답 계약 S5: writing 트랙 12 endpoint + `start_next_unit` 500 누수 폐쇄 (SoT v1.7.33) — **페이즈 종료**

### Goals

- 브리프 S5 행을 처리해 H3 페이즈를 닫는다: writing 잔여 10 endpoint 선언 + 기선언 2를 포함한 트랙 12 잠금.
- **이 페이즈에서 유일하게 런타임을 바꾼다**(브리프 명시 예외): `start_next_unit`의 500 누수를 503으로 폐쇄.

### Completed work

- **런타임 수정 — `writing_accept_endpoint`에 `except DraftOrderIntegrityError → 503`**([`main.py`](../../../services/application/app/main.py)). v1.7.29가 "알려진 결손, 정본이 승인한 동작 아님"으로 기록한 500 누수를 닫았다. 무결성 face 방어 지점 3곳 → **4곳**.
  - **절 위치는 400 그룹 위**. 오늘은 상속 관계가 없어 순서가 결과를 안 바꾸지만, 400 그룹(`WritingAcceptError`·`WritingGateError`·`InvalidContextSearchRequest`)은 "잘못된 요청" 광의 버킷이라 그 아래 두면 훗날의 재상속이 **서버 데이터 문제를 조용히 호출자 잘못으로 재분류**한다. 회귀가 legacy 데이터에서도 binding 오류=400 / 무결성=503임을 양방향으로 잠근다.
- **`accept`의 503이 앱에서 유일하게 두 얼굴을 함께 갖게 됐다**(구성 미비 + 데이터 무결성). 신규 `_ACCEPT_503`(`writing/http_models.py`)이 **두 운영 조치를 모두 명시**한다 — 한쪽만 적으면 "어느 쪽에 걸렸는지 로그에서 유추"가 남고 그게 H3가 없애려는 갭이다. 상수를 `http_models.py`에 둔 것은 `ACCEPT_RESPONSES`가 이미 거기 있기 때문이다(writing 도메인 응답 맵의 정의처; S2가 `_ERRORS_*`를 `main.py`에 둔 것과 같은 기준의 반대편 적용).
- **10 endpoint 선언 부착**(generate·generation-jobs get/retry·gate·report·revise·loop-audits 2·scratch 2). 기선언 2를 합쳐 트랙 12 전체가 lock 대상.
  - **신규 에러 상수 0**: S4의 `_ERRORS_400_404_502_504_CONFIG`가 generate/gate/report/revise 4곳에 그대로 맞았다. generate는 `{**GENERATE_ASYNC_RESPONSES, **_ERRORS_400_404_502_504_CONFIG}`로 202 success arm과 병합.
- **회귀 신규 13건**:
  - `WritingErrorContractDeclarationTest` 6(`test_application_api.py`) — 12행 exact lock(subTest 12) · 트랙 전수 선언 가드 · 본문 uniform-detail(subTest 38, `$ref` 또는 `anyOf` arm) · **Union 허용 지점 exact**(5곳 고정) · accept 503 두 조치 명시 · **502/504 동적 쌍 동반 선언**(subTest 12).
  - `WritingErrorBodyExactKeyTest` 3(동 파일) — 404·503-config·400 wire 본문.
  - **`StartNextUnitLegacyDataTest` 4**(`test_writing_accept.py`) — 런타임 수정의 양방향 잠금(아래 Verification).

### Issues found

- **자초한 사고 1건(복구 완료)**: mutation 실험을 되돌릴 때 `git checkout tests/test_application_api.py`를 써서 **커밋 안 된 S5 테스트 추가분을 통째로 날렸다**. 백업 파일로 되돌린 다른 mutation과 달리 이 파일은 작업분이 uncommitted 상태였다. 즉시 재작성해 복구했고 S2~S5 선언 테스트 31건/193 subtest green을 재확인했다. **교훈: 작업 트리에 uncommitted 변경이 있는 파일에 `git checkout`을 mutation revert 수단으로 쓰지 말 것** — mutation 대상 파일은 반드시 `cp` 백업/복원으로 다룬다.

### Decisions (구현자 판단)

- **partial envelope Union을 D1=A 위반으로 보지 않았다**: `revise-and-gate`(400/502/503/504)·`accept`(502)는 H3 이전부터 `Union[<partial>, ErrorDetailResponse]`를 선언한다. 에러 arm이 여전히 단일 `ErrorDetailResponse`라 "균일 에러 본문" 계약은 유지된다. 다만 이 예외를 **묵인하지 않고 회귀로 고정**했다 — `UNION_BODIES`가 Union 허용 지점을 정확히 그 5곳으로 잠가, 새 Union이 아무도 결정하지 않은 채 drift로 생기는 것을 막는다.
- **`test_writing_endpoints_declare_the_dynamic_provider_pair_together`를 live spec 기준으로 고쳤다**: 처음엔 `EXPECTED`(하드코딩 lock 리스트)를 순회하도록 썼는데, 그러면 **내 lock 리스트의 자기 정합성만 증명**하고 코드 변경으로는 절대 실패할 수 없다. mutation(gate의 504를 코드·lock 리스트 양쪽에서 제거)으로 이 맹점을 실증한 뒤 `self._declared(...)`를 읽도록 바꿔 실제 drift에도 물게 했다.
- **누적 미매핑 500 부채 2건(`auto_promote_job`·`index/source-blocks/rebuild`)은 고치지 않았다**: 브리프의 런타임 변경 예외는 `start_next_unit` **하나만** 명시한다. 두 건은 H3 이전부터 존재했고 이 페이즈의 계약 위반이 아니므로, 여기서 함께 고치면 오너가 승인한 스코프를 구현자가 넓히는 것이 된다. HANDOFF 추적 부채에 유지하고 별도 슬라이스 후보로 남긴다.

### Verification

- **OpenAPI self-discovery**: 12 endpoint 선언 집합이 코드 직독 도출과 정확히 일치(mismatch 0).
- **런타임 수정의 양방향 실증**:
  - **under-strict**: `except DraftOrderIntegrityError` 절을 제거하면 `test_start_next_unit_on_legacy_data_is_503`이 `DraftOrderIntegrityError`가 endpoint 밖으로 새며 재실패(= 폐쇄한 그 500). 절 복원 후 4/4 green.
  - **over-strict 3종**: legacy 없는 프로젝트는 `start_next_unit` **200** 유지 · `append_current`는 legacy가 있어도 **200**(이 경로는 `_require_ordered_drafts`를 안 탄다 = 07-22 수정의 수술적 범위 보존) · legacy 상태에서도 binding 오류는 **400**(절 순서 계약).
- **선언 mutation 5종(양방향)**: report 선언 삭제(under) · scratch에 안 던지는 409(over) · accept 503의 두-얼굴 description 제거 · plain-error 상태에 partial Union 누출 · gate가 502만 선언하고 504 누락. **+ 6번째**: gate의 504를 코드·lock 리스트 **양쪽**에서 제거 → 수정된 동적 쌍 테스트가 bite(수정 전이었다면 통과했을 시나리오).
- **런타임 불변(선언분)**: backend 전체 **1450 passed / 1 skipped / 0 failed / 524 subtests**. 직전 기준선 1437/462 대비 +13 test·+62 subtest = 신규분과 정확히 일치. 기존 writing 상태코드 회귀 전부 green.
- **프론트 타입**: `gen:api` → **+244행 / -1행**. **유일한 삭제 라인은 accept 503의 JSDoc `@description Service Unavailable`이 두-얼굴 문장으로 교체된 것**이며 diff를 직접 읽어 타입·필드 손실이 0임을 확인했다(S2~S4의 `-0`과 다른 유일한 지점이라 명시 확인 대상이었다). `tsc` clean, build JS 399.03 kB, frontend **194 passed / 13 files**.

### Next steps

- **H3 페이즈 종료.** 누적 60 endpoint 선언(CRUD 20[선언 18]·analysis 21·memory/source 7·writing 12[신규 10]). 브리프의 Deferred는 그대로 열려 있다: 프론트 에러 UX(D4=A로 분리)·`reason` 기계 코드(D1=B, 실사용 근거 시 additive)·외부 소비자 에러 카탈로그.
- **남은 미매핑 500 부채 2건**(`auto_promote_job` 승격 루프 · `index/source-blocks/rebuild` 협력자 장애)은 별도 슬라이스 후보. 둘 다 `start_next_unit`과 같은 부류이고 같은 해법(`except` 절 + 회귀)이지만, 어느 상태코드로 매핑할지는 각각 판단이 필요하다(전자는 부분 성공 의미론, 후자는 협력자 구성 face).
- **다음 큰 갈림길은 여전히 오너 dogfood 착수(GATE-1)**다 — H3는 계약 정직성 작업이라 dogfood와 병행 가능했고, 이제 그 트랙이 비었다.

### 오너 독립 검증 PASS + 비차단 반영 (S5)

- **오너 독립 검증 합격(조건 없음)**: `docs/verifications/2026-07-23/h3_s5_writing_error_responses.md`. boundary matrix **12/12 빈 cell 없음**. 검증자가 특히 값진 축 하나를 닫았다 — **기선언 2개(`revise-and-gate`·`accept`)의 lock 리스트 값이 선언에서 복사한 순환값이 아님**을 502/504 실제 raise 근거로 입증했다(내 lock 리스트는 그 둘에 대해 기존 선언을 읽고 적은 것이라 자기참조 위험이 실재했다). 런타임 수정 under-strict mutation·수치 전부(1450/1/524 · 194/13 · +244/-1 numstat · 399.03 kB)·`schema.d.ts` 재생성 diff 0행(수동 편집 drift 없음)도 재실행 일치.
- **비차단 1 반영 — 독스트링의 mutation 주장 과장 정정**: `StartNextUnitLegacyDataTest` 독스트링이 "`InvalidDraftOrder` 전체로 widening하면 over-strict 2건이 깨진다"고 썼는데, **직접 돌려 보니 4건 전부 통과한다**(검증자 지적 재현 완료). 이유까지 1차 소스에서 확인했다: accept 경로에서 도달 가능한 `InvalidDraftOrder`는 무결성 서브클래스뿐이다 — 부모는 `start_next_unit`의 잘못된 `unit_kind`에서도 발생하지만([`core_sot/service.py:734`](../../../services/application/app/core_sot/service.py#L734)), endpoint가 서비스 호출 **전에** `UnitKind(body.next_unit.unit_kind)`로 강제 변환하므로([`main.py:4012`](../../../services/application/app/main.py#L4012)) 그 분기는 이미 HTTP 경계에서 400이고 여기 도달하지 않는다.
  - **테스트를 추가하지 않고 독스트링을 고쳤다**: widening이 이 endpoint를 통해서는 **관측 가능한 효과가 없으므로** 이 층위에서 잠글 대상 자체가 없다. 억지로 쓰려면 서비스를 직접 호출해야 하는데 그건 endpoint의 매핑을 검증하는 게 아니다. 대신 독스트링에 (a) 이 테스트들이 못 잡는 것이 무엇인지, (b) 왜 못 잡는지, (c) 나중에 `UnitKind` 강제 변환이 사라지는 등으로 부모가 도달 가능해지면 그때 잠가야 한다는 것을 명시했다. **좁은 catch는 여전히 의도 표명**("서버 측 데이터 문제가 503이지 호출자의 순서 실수가 아니다")이다.
  - 이 정정은 계약·코드·산출물 무변이며 테스트 4건은 그대로 green이다.

---

## Task — 임베딩 실패 500 누수 폐쇄: source-block rebuild 502 매핑 (SoT v1.7.34)

### Goals

- 오너 지시 "다음 작업 작은 것부터". H3 S5가 별도 슬라이스 후보로 남긴 **미매핑 500 부채 2건** 중 판단이 명확한 쪽을 닫는다.
- 착수 전 **HANDOFF 추적 부채가 stale**임을 발견해 함께 정리한다.

### Completed work

- **[stale 문서 정리] `start_next_unit` 500 부채 항목 삭제**: HANDOFF 추적 부채 첫 항목이 여전히 "**미수정**, 추적 부채"로 적혀 있었는데 **S5(v1.7.33)가 이미 닫았다**. 다음 작업자가 이미 고친 결함을 다시 조사하게 만드는 항목이라 제거했다(같은 내용은 Current Status의 S5 항과 SoT v1.7.33에 정확히 남아 있다).
- **런타임 수정 — `rebuild_source_block_index`에 `except EmbeddingProviderError → 502`**: 이 endpoint는 모든 source block을 임베딩하는데 `NotFound`만 잡고 있었다. 구성돼 있지만 실패하는 임베딩 서비스(timeout·연결 불가·비정상 응답이 전부 `EmbeddingProviderError`)가 opaque 500으로 샜다.
- **선언 갱신**: `{404}` → **`{404,502}`**(신규 `_ERRORS_404_502`). S4의 `MemorySourceErrorContractDeclarationTest` lock 리스트도 동반 갱신했다 — 선언은 코드를 따라간다.
- **회귀 신규 3건**(`SourceBlockRebuildEmbeddingFailureTest`): 실패 시 502 + `{detail}` 단일 키 · 정상 rebuild 200 유지 · **절 폭 over-strict 가드**.

### Issues found

- **`EmbeddingProviderError`는 앱 어디에서도 잡히지 않고 있었다**(caller 0). 즉 이건 rebuild endpoint만의 결손이 아니라 **타입 전체가 무방비**였다. 패턴 스윕(§4)으로 `.embed()` 호출 지점 9곳을 훑은 결과:
  - **HTTP 도달 경로는 이 endpoint가 실질적으로 유일**하다. context search 주 경로는 `_run_vector_step`이 광의 `except Exception`으로 이미 잡아 `BACKEND_ERROR`→502로 표면화하고, `candidate_index`·`memory_index`·`indexing/service`는 worker 경로다.
  - **[추적 부채] `context_search/service.py`의 `retrieve` 2곳(:199·:406)은 같은 무방비 패턴**이나 HTTP 도달성을 확인하지 못했다. 30초 스윕 예산을 넘는 조사라 부채로 등록했다(§4 "발견 시 인라인 수정 또는 file:line 부채 등록, 조용히 넘어가지 않는다").

### Decisions (구현자 판단)

- **502이지 503이 아니다**. 처음 HANDOFF에 부채를 적을 때 나는 이걸 "협력자 구성 face(503)에 가깝다"고 썼는데 **틀렸다**. 503은 협력자가 **없는** 것이고, 여기서는 임베딩 서비스가 **구성돼 있는데 실패**한다. SoT 502 행("상류가 실패")에 정확히 해당하고, 코드 내 선례와도 일치한다 — context search의 vector step이 임베딩 실패를 이미 502로 표면화한다. **오너 브리프를 만들지 않은 이유가 이것**이다: 기존 계약과 선례가 답을 이미 정하고 있어 진짜 갈림길이 아니다.
- **SoT 502 행에 502/503 구분 규칙을 문장으로 못박았다**: "협력자가 없는 것(503)이 아니라 있는데 실패한 것이 502다". 내가 방금 틀린 구분이면 다음 사람도 틀린다.
- **`auto_promote_job`은 손대지 않았다**: 남은 부채 1건은 코드 매핑이 아니라 **계약 질문**이다(일부 승격 성공 후 실패하면 무엇을 반환하는가 — 부분 성공 봉투인가, 전체 실패인가). 이건 오너 판단이 필요한 진짜 갈림길이라 임의로 고르지 않았다.

### Verification

- **mutation 2종(양방향)**:
  - **under-strict**: `except EmbeddingProviderError` 절 제거 → `test_embedding_failure_is_502_with_the_uniform_body`가 예외가 endpoint 밖으로 새며 재실패(= 폐쇄한 그 500).
  - **절 폭 over-strict**: `except Exception`으로 확대 → `test_unrelated_failure_is_not_relabelled_as_502` FAIL. **이 가드는 mutation이 먼저 부재를 드러내서 추가한 것**이다 — 처음 3건만 있을 때 bare-`Exception` 변형이 전부 통과했고, 그건 무관한 프로그래밍 오류를 "상류 실패"로 오분류해 **운영자에게 멀쩡한 임베딩 서비스를 점검하라고 시키는** 종류의 거짓말이라 잠글 가치가 있었다.
- **런타임 불변(그 외)**: backend 전체 **1453 passed / 1 skipped / 0 failed / 525 subtests**. 직전 기준선 1450/524 대비 **+3 test·+1 subtest**과 정확히 일치한다 — 신규 3건은 subTest를 쓰지 않고, +1은 S4 body-model 루프가 rebuild의 선언 코드 1개(502)를 더 돌기 때문이다(12→13). *(초안에 +2/526으로 잘못 적었다가 실측 후 정정.)*
- **프론트 타입**: `gen:api` **+9행 / -0행**(rebuild endpoint의 502 응답만), tsc clean, build JS 399.03 kB, frontend **194 passed / 13 files**.

### Next steps

- **남은 미매핑 500 부채 1건 = `auto_promote_job`** — 오너 판단 필요(부분 성공 의미론).
- **신규 추적 부채**: `context_search/service.py:199`·`:406`의 무방비 `embed()` — HTTP 도달성 확인이 선행돼야 한다.
- 큰 갈림길은 여전히 **오너 dogfood 착수(GATE-1)**.

### 오너 독립 검증 PASS + 비차단 반영 (rebuild 502)

- **오너 독립 검증 합격(조건 없음)**: `docs/verifications/2026-07-23/rebuild_embedding_failure_502.md`. 502 매핑이 계약(SoT 502 행)·선례(`_run_vector_step`) 양쪽에서 정당함을 재확인했고, mutation 2종이 양방향으로 무는 것과 수치(1453/1/525 · +9/-0 · 399.03 kB)를 재실행 일치로 확인했다.
- **비차단 1 반영 — `:199`/`:406` 부채 설명 정정**: 내가 "무방비 `embed()`, **HTTP 도달성 미확인**"으로 등록했는데, 검증자가 직독으로 **둘 다 도달 가능하며 이미 보호되고 있음**을 밝혔다. 1차 소스에서 재확인 완료: `VectorCanonicalMemoryRetriever.retrieve`·`VectorCandidateMemoryRetriever.retrieve`는 각각 step runner(`service.py:752`·`:835`)에서 호출되고 그 호출부가 광의 `except Exception` → `BACKEND_ERROR` → `ContextSearchFailed` → **502**로 수렴시킨다.
  - **부채 성격을 다시 씀**: "도달성 미확인"(= 다음 사람이 재조사해야 함) → **"도달은 하나 호출자 광의 catch로 보호됨 — 그 catch가 좁아지면 누수로 전환"**(= 재조사 불요, 그 catch를 건드릴 때만 주의). 검증자 지적대로 후자가 다음 작업자의 비용을 실제로 줄인다.
  - **내 스윕이 30초 예산에서 멈춘 지점이 정확히 여기였다**: 호출자까지 한 단계 더 올라갔으면 나왔을 결론이다. 스윕 예산은 §4가 의도한 것이지만, "미확인"으로 등록할 때는 **무엇을 확인하면 닫히는지**를 함께 적어야 다음 사람이 같은 지점에서 다시 멈추지 않는다.
  - 코드·계약·산출물 무변(문서 정밀화만).
