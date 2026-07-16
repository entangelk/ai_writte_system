# 독립 검증 — 백엔드 공개 계약 조이기: 척추 응답 모델(H1) + 이름 검증(H2) (SoT v1.6.95)

## Subject metadata

- 날짜: 2026-07-16
- 요청자: 오너("다음작업 검증해줘. 커밋 2개 + H1·H2 완료 … 46f6009 / 971cbe5 … 트리 clean")
- 검증자: 독립 검증 AI(Claude, 별도 세션 — 구현 미관여)
- 대상 슬라이스/산출물: H1(Product shell 척추 14 endpoint `response_model`) + H2(project/draft `NonBlankName` 입력 검증). D1=A / D2=A / D3=A.
- 정본 계약 참조:
  - `docs/system-contract-sot.md` v1.6.95(행 + 서비스경계 §~183 "타입 계약 동기화의 실제 범위"·"입력 검증 계약")
  - `docs/plans/frontend-api-contract-decisions.md`(Resolved 브리프, D1/D2/D3 + 착수 전 실측 + Deferred)
  - `docs/verifications/2026-07-16/frontend_first_slice.md`(H1/H2 발단)
- 검증 대상 작업 출처: **commit `971cbe5`**(working tree clean). 본 검증은 mutation을 위해 일시적으로 working tree를 더렵히고 매번 `git checkout`으로 복원했다(최종 clean).

## Scope

1. **계약 스코프·자기 모순** — 브리프 잠긴 결정(D1=A/D2=A/D3=A) + SoT v1.6.95 행·서비스경계절이 요구하는 것과 브리프·SoT·코드 간 수치/표현 일치.
2. **H1 적용 범위 실측** — `response_model=`가 실제 몇 endpoint·어떤 것에 붙었는지, "48 coverable / 2 JSONResponse 구멍" 주장의 정확도.
3. **안전망-선-모델 순서의 정당성(핵심)** — `SpineEnvelopeKeyTest`가 exact-key를 잠그는지, 그리고 모델이 필드를 조용히 좁힐 때 안전망만이 잡는지(mutation A).
4. **save/read surface 분리** — 같은 키 이름에 다른 shape인지, 모델이 분리됐는지.
5. **H1 가치 실증(mutation B)** — backend payload 변경이 frontend `tsc`에 잡히는지.
6. **H2(mutation C/D)** — NonBlankName이 strip→min_length 순서로 동작하고, 제약/strip 제거 mutation이 양쪽 bite하는지.
7. **독립 실행 재현** — 백엔드 1111/45/273 · 프론트 10 · schema 재생성 IDENTICAL · 실 컨테이너 live 관통.
8. **정적/구성·문서 일관성**.

## Methodology

```
# 1. 계약 스코프 + 자기 모순
git show --stat 971cbe5 ; git show 971cbe5 -- docs/system-contract-sot.md docs/plans/frontend-api-contract-decisions.md HANDOFF.md docs/daily_logs/2026-07-16/work_log.md
# 2. H1 적용 범위 실측 (코드로 카운트 — 브리프의 "13/48/2" 주장 검증)
grep -n 'response_model=\|NonBlankName\|JSONResponse' services/application/app/main.py
sed -n '883,1024p;3174,3248p;2990,3145p' services/application/app/main.py   # 모델·accept·revise-and-gate
# 3. 안전망 감사
sed -n '1390,1645p' tests/test_application_api.py
# 4~6. mutation (clean tree → mutate → run → git checkout 복원, 매번)
#   A: SnapshotDetailPayload.project_id 제거 → 전체 스위트
#   B: ProjectPayload.archived→is_archived (모델+헬퍼) + gen:api → tsc --noEmit
#   C: NonBlankName→str → BlankNameRejectionTest
#   D: NonBlankName=Annotated[str,StringConstraints(min_length=1)] → BlankNameRejectionTest
# 7. 독립 실행
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
cd frontend && npm test && npm run build
cd frontend && python3 ../scripts/dump_openapi.py > /tmp/o.json && npx openapi-typescript /tmp/o.json -o /tmp/s.d.ts && diff src/api/schema.d.ts /tmp/s.d.ts
# live 관통(격리 네트워크, application in-memory + frontend 컨테이너, trap 정리): padding strip·422·version detail envelope 키·enum·export
# 이미지가 v1.6.95 코드를 반영하는지 사전 확인(grep NonBlankName in image)
# 8. 정적/구성
docker compose config --quiet ; git diff --check
```

## Findings

### 1. H1 적용 범위 — `response_model=`는 정확히 14 endpoint (브리프의 "13"은 틀림)

`grep -c 'response_model=' services/application/app/main.py` = **15**(주석 1 + endpoint 14). 실제 14 endpoint:
- projects 5: POST/GET/GET{id}/PATCH/DELETE `/projects`(main.py:1420,1425,1429,1437,1467)
- drafts 5: PATCH·DELETE draft(1452,1479)·GET drafts(1492)·GET draft(1501)·POST draft(1595)
- versions 4: GET versions(1512)·GET version detail(1525)·GET export(1563)·POST save(1609)

SoT v1.6.95 행·HANDOFF는 "척추 14 endpoint(projects 5·drafts 5·versions 4)"로 정확. **그러나 브리프 `frontend-api-contract-decisions.md` D1=A 행은 "척추 13개(projects 2 + drafts 8 + snapshots 3)"** — 총수(13≠14)도, 서브 분류(척추엔 snapshot endpoint가 아니라 version endpoint가 있음)도 실제 topology와 어긋난다. 정본(SoT)과 코드가 14로 일치하므로 브리프 option 텍스트만 부정확(해결된 브리프의 사소한 stale). 차단 아님.

### 2. "2개 JSONResponse 구멍" 표현은 accept에 대해 부정확 (본질은 맞음)

`JSONResponse`는 5곳(main.py:3005/3039/3081/3112/3226). 소속: 3005·3039·3081·3112는 전부 `/writing/revise-and-gate`(2879)의 **partial-failure 예외 경로**, 3226는 `/writing/accept`(3174)의 `WritingAcceptAnalysisError` 502 경로. 핵심: **두 endpoint 모두 성공 응답은 dict다**(revise-and-gate 성공 dict 3140-3145; accept 성공 dict 3239-3248). 즉 "JSONResponse를 직접 반환해 response_model이 안 먹는다"는 **성공 경로에 대해 부정확** — response_model을 붙이면 성공 dict는 잡히고 partial-failure JSONResponse만 우회한다. 정확한 진술은 "mixed return(dict 성공 + JSONResponse partial-failure)이라 partial-failure envelope이 구조적으로 uncoverable". 결론(→ Writing 슬라이스로 Deferred)은 그대로 옳다(partial envelope이 복잡 + D1=A 범위 밖). 차단 아닌 표현의 정밀도 문제.

### 3. 안전망-선-모델 순서의 정당성 — mutation A로 입증 (이 슬라이스의 핵심, PASS)

`SpineEnvelopeKeyTest`(test_application_api.py:1390) 5개가 척추 전 envelope의 **exact key set**을 잠근다(set 비교, 개별 키 읽기 아님). save(좁음)·read(넓음) 분리도 명시적(test_save_draft_envelope_keys vs test_version_list_and_detail_envelope_keys).

**mutation A(독립 재현)**: `SnapshotDetailPayload.project_id` 제거 → 전체 스위트 **1 failed / 1110 passed**. 실패한 1개는 정확히 `SpineEnvelopeKeyTest::test_version_list_and_detail_envelope_keys`. 즉 필드 유실을 안전망 **한 개만** 잡는다 — 작업자 주장(1104개 중 1개; 본 검증에선 1111개 중 1개로, 본질 동일) 독립 입증. 안전망 없이 모델부터 붙였으면 이 필드 유실이 green으로 배포됐을 것. 순서 결정(안전망 먼저 → 현 payload 통과 확인 → 모델)이 옳았음이 증명됐다.

### 4. save/read 분리 — 실제로 다른 shape, 분리 정당 (PASS)

- read(`DraftVersionDetailResponse`, main.py:948-951): `draft_version`(5키)·`snapshot`(6키)·`blocks`(8키).
- save(`SaveDraftResponse`, main.py:978-982): `draft_version`(3키: id·version_number·snapshot_id)·`snapshot`(2키)·`blocks`(4키)·`idempotent_replay`.
- 같은 키 이름(draft_version/snapshot/blocks)에 save가 확실히 좁다. live 관통(§7)에서도 read surface 5/6/8키·save surface 3/2/4키로 정확히 확인. 분리가 강제됨이 맞다. (main.py:954-957 주석이 "공유하면 save 응답에서 필드가 사란다"고 한 mechanism 묘사는 방향이 약간 느슨하다 — 넓은 read 모델을 좁은 save에 씌우면 검증 *에러*지 silent delete가 아니다. 결론은 동일. 매우 사소한 주석 정밀도.)

### 5. H1 가치 실증 — mutation B로 입증 (PASS)

**mutation B(독립 재현)**: `ProjectPayload.archived`→`is_archived`(모델+헬퍼) + `gen:api` 재생성 → schema.d.ts의 ProjectPayload가 `{id; is_archived; name}`로 바뀌고, 프론트 `tsc --noEmit`이 정확히 `ProjectList.tsx(71,24)`에서 실패:
```
error TS2339: Property 'archived' does not exist on type '{ id: string; is_archived: boolean; name: string; }'.
```
`client.ts`가 손선언을 버리고 `Project = components["schemas"]["ProjectPayload"]`를 소비(client.ts:49)하므로 백엔드 payload 변경이 schema를 타고 tsc에 도달한다. v1.6.94(응답 무타입·손선언)였으면 조용히 빌드되고 런타임에 깨졌을 변경. **H1의 존재 이유가 척추 구역에서 닫혔음이 입증됐다.** (v1.6.94 검증 H5 — 경로 타입 call-site 미소비 — 도 client.ts가 `ProjectListResponse`까지 소비하며 자연 해소.)

### 6. H2 — mutation C/D로 양쪽 guard 입증 (PASS)

`NonBlankName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`(main.py:1003)를 create·rename project/draft 4종 요청 모델에 적용(1007/1016/1020/1024). strip이 min_length보다 먼저.

- **mutation C(독립 재현)**: `NonBlankName=str`(제약 제거) → `BlankNameRejectionTest` **12 failed / 4 passed**. 작업자 주장(12)과 정확 일치.
- **mutation D(독립 재현)**: `min_length=1`만(strip 제거) → **10 failed / 4 passed / 6 subtests passed**. 작업자 주장(10)과 정확 일치. min_length만으로는 `"   "`(3칸) 같은 padding blank를 못 잡아 strip 순서가 필수임이 입증.
- 테스트는 양방향: under-strict(공백 422·padding은 strip not reject) + over-strict(일반 이름 통과·내부 공백 보존·거부 시 store에 안 닿음). Core SOT `create_project`(service.py:195)는 여전히 검증 없음 — HTTP 경계에서만 닫힘(D3=A, 정본 계약 무변).

### 7. 독립 실행 — 정량 주장 전부 재현 (PASS)

| 항목 | 작업자 주장 | 독립 재현 |
|---|---|---|
| 백엔드 | 1111 passed / 45 skipped / 273 subtests | **1111 / 45 / 273 (35.13s)** |
| 프론트 회귀 | 10 passed | **10 passed** |
| 프론트 빌드 | tsc+vite | **31 modules, 195.14/61.64 kB** |
| schema 재생성 | IDENTICAL | **IDENTICAL** (committed `schema.d.ts` == 현 backend 재생성) |
| compose config | --quiet 통과 | **CONFIG OK** |
| git diff --check | clean | **CLEAN** |

추가 정적 확인: `ProjectPayload`가 schema.d.ts에서 실제 응답 타입(`archived: boolean` 등 — v1.6.94의 빈 `[key:string]:unknown`에서 실체로). application 이미지가 v1.6.95 코드를 반영(이미지 내 main.py `NonBlankName`=5·`response_model=`=15·`SnapshotDetailPayload`=2 = working tree 동일).

**live 관통(격리 네트워크, application in-memory + frontend 컨테이너, trap 정리)**:
- padding strip: `POST {"name":"  겨울 이야기  "}` → `{"name":"겨울 이야기"}` HTTP 200 ✓
- 공백-only: `POST {"name":"   "}` → HTTP **422** (`string_too_short` at `body.name`) ✓
- version detail **read surface** 키: `draft_version`{5}·`snapshot`{6}·`blocks`{8} — SpineEnvelopeKeyTest 및 작업자 주장(5/6/8)과 **정확 일치** ✓
- **save surface** 키: `draft_version`{3}·`snapshot`{2}·`blocks`{4}+`idempotent_replay` — 테스트와 정확 일치 ✓
- enum: `blocks[0].kind` = `"heading"`(문자열 직렬화) ✓
- export: body = `'# 제목\n\n본문.'`(원문), 10키 ✓

## Issues / Risks

### Blocking (계약 의무)

**없음.** H1(14 응답 모델)·H2(4 입력 제약)가 계약·코드·회귀·live 모두에서 정합하고, 안전망-선-모델 순서가 mutation으로 입증됐으며, 안전망 매트릭스에 빈 셀이 없다(척추 전 envelope exact-key + H2 양방향). client.ts 손선언 제거로 v1.6.94의 "컴파일 타임 미검출"이 척추에서 해소됐음이 mutation B로 확인.

### Hardening recommendations (비차단)

- **H1-d1 — 브리프 D1=A 행 "척추 13개(projects 2+drafts 8+snapshots 3)" 정정**: 실제는 14(projects 5+drafts 5+versions 4). SoT·HANDOFF·코드는 14로 정확하나 브리프 option 텍스트만 부정확. 해결된 브리프의 한 줄 정정 권장(계약 영향 없음).
- **H1-d2 — "2개 JSONResponse 구멍" 표현 정밀화**: accept·revise-and-gate 둘 다 성공은 dict, partial-failure만 JSONResponse. 진술을 "partial-failure envelope이 uncoverable"로 좁히면 정확(결론·Deferred는 불변). HANDOFF Owner Decisions의 (a)/(b) fork 서술이 이미 본질을 담고 있어 긴급 아님.
- **H1-d3 — main.py:954-957 주석 mechanism 묘사**: "공유하면 save 응답에서 필드 사라짐"은 방향이 느슨(넓은 모델을 좁은 payload에 쓰면 검증 에러). 결론(분리)은 옳. 사소.
- **422 detail 표시(기존 follow-up)**: 422 detail은 FastAPI validation 배열이라 프론트 `readDetail`이 JSON.stringify로 떨어뜨린다. 지금은 프론트 trim+disable로 사용자가 안 본다. 사용자 문구가 필요해지면 그때 매핑(work_log·브리프에 이미 기록).

## Verdict

**합격(PASS, 조건 없음).**

이유:
1. **안전망-선-모델 순서의 정당성이 mutation A로 입증됐다**(§3) — `snapshot.project_id` 제거가 전체 1111개 중 안전망 1개만 bite. 이것이 "모델부터 붙였으면 필드 유실이 green으로 배포됐을 것"이라는 작업자의 핵심 주장의 독립 증거.
2. **H1이 실제로 값을 낸다**가 mutation B로 입증됐다(§5) — `archived`→`is_archived`가 `tsc` ProjectList.tsx(71,24)에서 정확히 bite. 척추 구역에서 v1.6.94의 "컴파일 타임 미검출" 해소.
3. **H2 양방향 guard**가 mutation C(12)/D(10)로 입증됐다(§6) — 제약·strip 각각 제거 시 정확히 주장된 수만큼 bite.
4. 작업자의 정량 주장 전부(1111/45/273·프론트 10·schema IDENTICAL·mutation 4종 수치·live envelope 키 5/6/8·3/2/4)를 독립 재현했다(§7).
5. 안전망 매트릭스 빈 셀 없음 — 척추 전 envelope exact-key + H2 under/over-strict.
6. Core SOT 정본 계약 무변(D3=A, HTTP 경계) 확인 — service.py:195 `create_project`는 여전히 검증 없음, 입력 검증은 경계에만.

Hardening 4건은 전부 비차단(브리프/주석의 표현 정밀도·이미 기록된 422 follow-up). 그중 H1-d1(브리프 13→14)이 가장 정정 가치가 크나 계약 영향은 없다.

## Outstanding items

- 작업물은 **commit `971cbe5`(+ `46f6009`)**로 반영됐고 working tree는 clean(본 검증의 mutation은 전부 복원 확인).
- **Deferred(옳은 이월)**: 나머지 34 endpoint 응답 모델(해당 UI 슬라이스에서) · `/writing/revise-and-gate`·`/writing/accept` partial-failure envelope(Working C 슬라이스에서 (a) 성공 모델+에러 `responses={}` vs (b) 손선언 결정) · `raw_text`/`idempotency_key` 제약(에디터 슬라이스).
- HANDOFF가 "response_model 취급 규칙" 절을 새로 남겨, 다음 슬라이스가 척추 패턴(안전망-선-모델)을 따르도록 했다 — 좋은 선례화.
- 다음 슬라이스 = 원고 목록 → 에디터(척추 응답 타입이 이미 잠겨 drafts/versions도 생성 타입으로 바로 붙음; `idempotency_key` 계약·프로젝트 상세 라우팅이 처음 붙음).

## Reproduction

```
# 정본 계약 스코프 + 자기 모순
git show --stat 971cbe5
git show 971cbe5 -- docs/plans/frontend-api-contract-decisions.md docs/system-contract-sot.md
grep -c 'response_model=' services/application/app/main.py          # 15 = 주석1 + endpoint14

# 백엔드·프론트·schema
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider   # 1111/45/273
cd frontend && npm test && npm run build                                       # 10 / build ok
cd frontend && python3 ../scripts/dump_openapi.py > /tmp/o.json \
  && npx openapi-typescript /tmp/o.json -o /tmp/s.d.ts \
  && diff src/api/schema.d.ts /tmp/s.d.ts                                      # 빈 = IDENTICAL

# mutation A (안전망 고유 가치): SnapshotDetailPayload.project_id 제거 후
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider   # 1 failed (SpineEnvelopeKeyTest) / 1110 passed
git checkout services/application/app/main.py

# mutation B (H1 가치): ProjectPayload.archived→is_archived(모델+헬퍼) 후
cd frontend && python3 ../scripts/dump_openapi.py > openapi.json && npx openapi-typescript openapi.json -o src/api/schema.d.ts && npx tsc --noEmit
# → error TS2339 ProjectList.tsx(71,24) Property 'archived' does not exist
cd .. && git checkout services/application/app/main.py frontend/src/api/schema.d.ts && rm -f frontend/openapi.json

# mutation C/D (H2): NonBlankName=str / =Annotated[str,StringConstraints(min_length=1)]
python3 -m pytest tests/test_application_api.py::BlankNameRejectionTest -q -p no:cacheprovider   # C=12 failed / D=10 failed
git checkout services/application/app/main.py

# live 관통(격리 네트워크, trap 정리)
docker network create fsmoke2
docker run -d --name fsmoke2-app --network fsmoke2 --network-alias application ai_writte_system-application:latest
docker run -d --name fsmoke2-fe  --network fsmoke2 -p 8014:80 ai_writte_system-frontend:latest
# /api/health 200 대기 후:
curl -s -XPOST -H 'Content-Type: application/json' -d '{"name":"  겨울 이야기  "}' -w '\n%{http_code}\n' http://localhost:8014/api/projects   # {"name":"겨울 이야기"} 200
curl -s -XPOST -H 'Content-Type: application/json' -d '{"name":"   "}' -w '\n%{http_code}\n' http://localhost:8014/api/projects               # 422
# draft 생성 → version save(idempotency_key) → GET version detail 의 key set / blocks[0].kind=="heading" / export body 원문 확인
docker rm -f fsmoke2-app fsmoke2-fe ; docker network rm fsmoke2
```
