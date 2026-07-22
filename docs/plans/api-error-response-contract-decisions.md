# 착수 결정 브리프 — 공개 계약 조이기 H3: 에러 응답 계약 (error-response contract)

상태: `Resolved — D1=A · D2=A · D3=A · D4=A (owner confirmed 2026-07-22)` · 계보: `frontend-api-contract-decisions.md`(H1 응답 모델 · H2 입력 검증, Resolved 2026-07-16, SoT v1.6.95)의 후속

관련 정본:
- `docs/system-contract-sot.md` — v1.6.94("타입 계약 동기화의 실제 범위" 절)가 H1/H2 갭을 기록, v1.6.95에서 H1/H2 확정. 본 브리프는 그 시리즈의 **H3**.
- `docs/plans/frontend-api-contract-decisions.md` — H1(성공 `response_model`)·H2(입력 검증) 선례. spine-first(D1=A) 적용 방식·"silent field loss" 리스크·검증 방법을 그대로 상속.
- 계기: 2026-07-22 dogfood에서 발견한 레거시-데이터 `/drafts` 500 → 503 수정(commit `1f526fe`, `docs/verifications/2026-07-22/legacy_drafts_500_503_integrity_mapping.md`)의 독립 검증 H-2 — "503이 새 public 상태코드인데 SoT/OpenAPI에 미반영, 다음 검증자가 로그에서 유추해야 함". 오너 판단: 부채가 아니라 다음 페이즈로 정면 처리.

---

## Decision needed

H1은 **성공 envelope**(`response_model`)만 spine에 선언했다. **에러 응답**(404/409/400/503/502/504)은 3개 writing endpoint(`generate`·`revise-and-gate`·`accept`)를 제외하고 **어디에도 OpenAPI로 선언되지 않는다**. 즉 공개 계약(OpenAPI = 프론트 `gen:api` 타입 생성원 = 문서 = 외부 소비자 계약)이 "이 endpoint가 어떤 실패를 반환하는가"에 대해 **침묵**한다. 이건 미덕이 아니라 H1이 남긴 **계약의 절반**이다.

착수하려면 오너 결정 4가지가 필요하다 — 전부 공개 계약 표면을 건드리고, 기존 정본에 답이 없다.

---

## 착수 전 실측한 사실 (1차 소스, 이 결정이 딛는 바닥)

`services/application/app/main.py` 직접 조사 (2026-07-22, commit `1f526fe`):

- **endpoint 61개**. `@app.<method>` 데코레이터 기준.
- **`responses=`를 쓰는 endpoint = 3개**지만 **에러 본문 모델을 선언한 건 2개뿐**: `writing/revise-and-gate`(400/404/502/503/504), `writing/accept`(400/404/409/502/503/504). 세 번째 `writing/generate`는 **202 success arm만** 선언하고 **에러 모델은 없다**(그 에러도 H3 대상). 정의는 `services/application/app/writing/http_models.py:257-289`, 에러 본문 모델은 **단일 `ErrorDetailResponse{detail:str}`**(`_DETAIL_ONLY`).
- **나머지 59개 endpoint는 404·409조차 OpenAPI 미선언** — 런타임에는 `raise HTTPException`으로 정확히 반환되지만 계약에는 없다.
- **앱 전체 에러 상태코드 분포**(`raise HTTPException`, multi-line 포함): 404×62, 400×30, 502×19, 503×18, 409×16, 504×7, 그리고 동적 `status_code=status`(ProviderError 매핑)×9(`raise` + partial-envelope `JSONResponse` 혼재). *(202×1은 async-generate의 success arm `JSONResponse`(main.py:3234)이지 에러가 아니라 제외; 502 리터럴 20건 중 1건도 partial `JSONResponse`(3957)라 에러-raise는 19.)*
- **`gen:api` = `openapi-typescript`(타입 전용 생성기)**: `frontend/package.json:11` → `dump_openapi.py > openapi.json && openapi-typescript … -o src/api/schema.d.ts`. **런타임 클라이언트가 아니라 타입만** 뽑는다. 선언된 `responses`는 `schema.d.ts`의 operation 타입에 나타나고, 미선언은 안 나타난다.

### 이 두 사실이 H3의 성격을 규정한다

1. **에러 본문이 균일**(`{detail:str}`)하고 **생성기가 타입 전용**이라 → 선언의 실익은 **새 타입 안전성이 아니라 "계약 정직성/문서화/자기발견성"**이다. 지금 1인 로컬에선 값이 중간이지만, dogfood 보정마다 같은 갭(503처럼 "로그에서 유추")이 재발하므로 **누적 비용을 없애는** 작업이다.
2. H1의 **silent field loss 리스크는 H3엔 거의 없다** — 성공 모델과 달리 에러는 단일 `ErrorDetailResponse`를 재사용하므로 "모델이 payload보다 좁아 필드가 사라지는" 문제 자체가 없다. H3는 H1보다 **안전한 기계적 작업**이다.

---

## 스코프 밖 (명시)

- **런타임 동작 변경 없음**: 상태코드·detail 문자열·분기는 그대로. H3는 **선언(문서/타입)만** 추가한다. (예외: `start_next_unit` 500 누수는 실제 결손이라 S5에서 방어 수정 — 아래.)
- **프론트 에러 UX 개선 없음**(D4 참조): 프론트는 이미 숫자 status로 분기한다. 특정 상태(503-migration 등)의 특수 UX는 실사용 근거가 있을 때 별도.
- **입력 검증(H2) 확장 없음**: H2는 이미 확정. H3는 응답 쪽만.
- **동적 `status_code=status`(ProviderError) 9곳의 코드 열거**: upstream 매핑이라 가능한 코드 집합이 넓다. S3~S5에서 endpoint별로 realistic 집합만 선언하고, 전체 열거는 하지 않는다.

---

## D1 — 에러 응답 본문 형태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D1=A. 균일 `ErrorDetailResponse{detail}` 전면 재사용 (추천)** | 기존 2 writing endpoint(revise-and-gate·accept)와 동형으로 모든 에러 응답에 `_DETAIL_ONLY` 모델을 붙인다. | 선례 일치, 최소 변경, 프론트가 이미 status 분기라 충분. silent-field-loss 무관. | 503-migration 같은 상태를 프론트가 문자열 파싱 없이 기계적으로 특수처리하려면 후속 필요. |
| D1=B. 균일 detail + 특정 상태에 `reason` 코드 필드 | `{detail, reason?}`에서 503-migration → `reason:"migration_required"` 등 machine-readable 코드 부여. | 프론트가 detail 문자열 파싱 없이 분기 가능. | 새 계약 리터럴을 **실사용 근거 없이** 도입(Simplicity First 위반 소지). 어느 상태에 코드를 줄지 결정 부담. |
| D1=C. 상태코드별 richer typed error 모델 | 상태마다 별도 에러 스키마. | 최대 표현력. | 균일 detail 대비 과설계. 유지비 급증. |

**추천: D1=A**. 에러 본문은 균일 `{detail}`로 유지. `reason` 코드(D1=B)는 **프론트가 503-migration을 실제로 특수 UX 처리해야 할 근거가 생기면** 그때 additive로 도입 — 지금은 detail 문자열("migration is required")이 이미 실행 가능한 메시지를 담고, 소비자가 오너 1인이라 투기적 코드 필드는 이르다.

## D2 — 슬라이스 범위와 순서

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D2=A. CRUD-family first, 이후 도메인별 (추천)** | H1 spine 14(projects 5+drafts 5+versions 4)에 **직접 인접한 CRUD 형제 6**(brief 4·draft-order·project-export)를 더한 **20**을 먼저, 이후 analysis→memory/source→writing 순. | H1 선례·프론트 실소비 표면 우선. 슬라이스마다 diff 작아 검증 가능. dogfood가 실제 만나는 CRUD부터 정직해짐. 형제 6은 같은 저복잡도 균일-에러 표면이고 project-export가 503(페이즈 동기 endpoint)을 담아 분리 시 동기 집합이 쪼개짐. | 완주까지 여러 슬라이스. |
| D2=B. 61개 전체 한 번에 | 모든 endpoint에 에러 응답 일괄 선언. | 갭이 한 번에 닫힘, 계약 표면 균일. | 큰 기계적 diff + 대량 회귀. 아직 UI가 안 만난 analysis/review envelope까지 지금 고정 → C·B 트랙 변경 시 재작업. 검증 표면이 커 리뷰 부담. |
| D2=C. 프론트 소비 시점에 그때그때 | endpoint를 프론트가 쓸 때만 선언. | 낭비 0. | "계획 없음"과 동일. 페이즈로 다루자는 오너 의도(부채 아님)와 배치. |

**추천: D2=A**. H1이 검증한 방식 그대로. 슬라이스 분해는 아래 참조.

## D3 — SoT 반영 방식

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D3=A. 전역 에러 계약 섹션 1개 + endpoint별 OpenAPI 선언 (추천)** | SoT "확정된 전역 계약"에 HTTP 에러 상태코드 **의미론 정책**을 명문화(404/409/400/503/502/504 각각이 "무엇을 뜻하는가"), 개별 endpoint의 realistic 코드 집합은 OpenAPI(`responses=`)가 기계적 진실. | 전역 정책이 반복을 없애고 일관 기준 제공. per-endpoint는 OpenAPI가 자기발견(schema introspection)으로 커버. "로그에서 유추" 갭 종결. | 전역 정책 문안을 오너와 합의 필요. |
| D3=B. per-endpoint SoT 표 | SoT에 endpoint×상태코드 표를 직접 유지. | SoT만 봐도 전부 파악. | OpenAPI와 이중 관리(drift 위험). 61×N 표 유지비. |
| D3=C. 전역 정책만, OpenAPI 미반영 | SoT 정책 섹션만. | 최소. | 프론트 타입/문서엔 여전히 없음 — H3의 핵심 미달성. |

**추천: D3=A**. 전역 정책(의미론)은 SoT, endpoint별 열거는 OpenAPI. 각 슬라이스는 OpenAPI에 리터럴이 실제로 나타나는지 `openapi.json` 재덤프로 self-discovery 확인(CLAUDE.md "schema self-discovery").

## D4 — 프론트 동작 변경 포함 여부

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **D4=A. 계약 선언 + 타입 재생성만, 프론트 에러 UX 불변 (추천)** | `responses=` 추가 → `schema.d.ts` 재생성 → tsc/build 통과 확인. 프론트 분기 로직 무변경. | 선언은 additive라 프론트 무영향. 페이즈 경계 깨끗. | 503-migration 등 UX 개선은 별도. |
| D4=B. 특정 상태 프론트 특수 UX 포함 | 503-migration에 "데이터 마이그레이션 필요" 안내 등 프론트 처리도 이번에. | 사용자 대면 개선 즉시. | 계약 작업 + UX 작업이 한 슬라이스에 섞여 경계 흐려짐. 실사용 근거(어떤 UX?)가 아직 약함. |

**추천: D4=A**. 이번 페이즈는 계약/타입만. 프론트 에러 UX는 dogfood 근거가 쌓이면 별도 슬라이스.

---

## 슬라이스 분해 (D2=A 채택 가정)

| 슬라이스 | 범위 | 산물 | 규모 |
|---|---|---|---|
| **S1** (문서) | SoT 전역 HTTP 에러 계약 섹션 신설 + 503-migration 경계·`start_next_unit` 부채 명문화 | `system-contract-sot.md` 버전 bump | 소 (문서) |
| **S2** (CRUD family) | **H1 spine 14** (projects 5[create/list/get/rename/archive] + drafts 5[create/list/get/rename/archive] + versions 4[list/detail/save/export]) **+ CRUD 형제 6** (brief 4[get/put/versions/versions-detail] + draft-order 1 + project-export 1) = **20** 에 realistic `responses=` 선언 | `main.py`/`http_models.py`, `schema.d.ts` 재생성, exact-key 회귀 | 중 |
| **S3** (analysis) | analysis jobs/candidates/context/compare/apply/review-queue/review-inbox/gate-findings 트랙 | 동상 | 중~대 |
| **S4** (memory/source) | memory read 2, snapshots/source-refs/index-rebuild, context-search | 동상 | 중 |
| **S5** (writing 잔여) | writing generate(에러 미선언 — 202 success만 있음)/generation-jobs/gate/report/revise/loop-audits/scratch (**에러 본문 기선언 2**[revise-and-gate·accept]만 제외) **+ `start_next_unit` 503 방어 수정**(실제 500 누수, 추적 부채) | 동상 + accept 경로 방어 | 중 |

### S2(CRUD family = spine 14 + 형제 6 = 20) 실측 에러 코드 맵 (이 슬라이스의 lock 리스트)

| endpoint | 코드 |
|---|---|
| `POST /projects` | (검증 실패 422는 FastAPI 자동) |
| `GET /projects` | — |
| `GET /projects/{id}` | 404 |
| `PATCH /projects/{id}` (rename) | 404, 409 |
| `DELETE /projects/{id}` (archive) | 404 |
| `GET /projects/{id}/brief` | 404 |
| `PUT /projects/{id}/brief` | 404, 409 |
| `GET …/brief/versions`, `…/brief/versions/{v}` | 404 |
| `POST …/drafts` (create) | 404, 409, **503** |
| `GET …/drafts` (list) | 404, **503** |
| `GET …/drafts/{id}` | 404 |
| `PATCH …/drafts/{id}` (rename) | 404, 409 |
| `DELETE …/drafts/{id}` (archive) | 404 |
| `GET …/drafts/{id}/versions`, `…/versions/{v}` | 404 |
| `GET …/versions/{v}/export` | 400, 404 |
| `GET …/export` (project) | 400, 404, **503** |
| `PUT …/draft-order` (reorder) | 404, 409 |
| `POST …/versions` (save_draft) | 404, 409, 400 |

(총 20 endpoint = H1 spine 14 + 형제 6. 422 검증 오류는 FastAPI가 자동 문서화하므로 선언 대상 아님. spine 14는 H1이 성공 모델을 이미 선언한 표면이라 성공/실패 계약을 같은 자리에서 완성하고, 형제 6[brief 4·draft-order·project-export]은 H1 spine 밖이지만 같은 CRUD 패밀리라 함께 잠근다.)

### 슬라이스별 검증 방법 (공통)

CLAUDE.md "Minimum Verification by Artifact Type — Public interfaces/structured contracts" 준수:
1. **런타임 불변 회귀**: 각 endpoint의 실제 상태코드가 그대로임을 기존/신규 테스트로 확인(선언은 동작을 안 바꿈).
2. **schema self-discovery**: `python3 scripts/dump_openapi.py` 재덤프 → 해당 operation의 `responses`에 선언한 코드가 **실제로 나타나는지** 확인(코드가 emit하는 것만 믿지 않음).
3. **프론트 타입 재생성**: `gen:api` → `schema.d.ts` diff가 additive인지, `tsc` clean, build 통과.
4. **exact-key**: 에러 본문이 `{detail}` 단일 키임을 회귀로 핀(H1의 exact-key 관용구 상속).

---

## Deferred / out of scope (이번 페이즈에서 결정 안 함)

- 프론트 에러 UX 개선(503-migration 안내 화면 등) — D4=A로 분리.
- `reason`/`code` machine-readable 에러 필드 — D1=A로 분리(실사용 근거 시 additive).
- ProviderError 동적 코드 9곳의 완전 열거 — endpoint별 realistic 집합만.
- 외부 소비자용 에러 카탈로그/문서 사이트 — 로컬 1인 단계 밖.

## Follow-up considerations (열어둘 문)

- 전역 에러 정책 섹션(D3=A)은 향후 `reason` 코드(D1=B)를 **추가할 자리**를 남겨둔다 — 정책에 "상태코드 = 의미론, detail = 사람용 메시지, (후속) reason = 기계용 코드" 3층으로 명기해 두면 D1=B 도입이 스키마 파괴 없이 additive.
- S5의 `start_next_unit` 방어는 이번 500-fix(commit `1f526fe`)와 동일 근본원인(`DraftOrderIntegrityError`)이라, S5에서 `writing_accept_endpoint`에 `except DraftOrderIntegrityError → 503`를 추가하며 추적 부채를 함께 닫는다.

---

## 오너에게 (요약)

- 4개 결정(D1~D4) 모두 **A** 확정: 균일 detail 유지 · CRUD-family-first · 전역정책+OpenAPI · 계약/타입만.
- **S1(SoT 전역 에러 계약 섹션)부터** 착수 — 방금 500-fix의 검증 H-2 갭을 정본에 닫는 게 첫 슬라이스. 이후 S2(CRUD family 20)부터 각각 별도 커밋.

## 독립 검증(조건부 합격) 반영 — 2026-07-22

`docs/verifications/2026-07-22/h3_error_response_contract_plan.md` (S2 lock 리스트 20 endpoint 전부 실코드 일치·D1~D4 건전 확인). 비차단 3건 정정:
- **F1**: 동기부여 절 분포 숫자 정밀화 — 502 20→**19**(1건은 partial `JSONResponse`), **202×1은 에러 아님**(async-generate success arm `JSONResponse`)으로 제외, 동적×9는 `raise`+`JSONResponse` 혼재 명시. (404×62/400×30/503×18/409×16/504×7은 검증에서 정확 확인.)
- **F2**: "에러 선언 3개" → **에러 본문 모델 선언은 2개**(revise-and-gate·accept). generate는 202 success만 선언·에러 모델 없음(H3 대상). 미선언 58→**59**.
- **F3**(S2 범위 자기모순): lock 리스트가 20을 나열하면서 라벨은 "spine 14"였음. **결정: 20으로 재라벨**(H1 spine 14 + CRUD 형제 6). 14로 줄이지 않은 이유 = 형제 6은 같은 저복잡도 균일-에러 CRUD 표면이고 project-export가 503(페이즈 동기 endpoint)을 담아 분리 시 동기 집합이 쪼개짐. D2=A·S2 행·lock 헤딩·S5 문구 전부 정합화.
