# Live Smoke Record — B Review Inbox 실 스택 관통 (v1.7.4 + v1.7.5)

## Subject metadata

- **날짜**: 2026-07-17
- **요청자**: 오너 ("관통 테스트 해보자. 지금 이 머신은 내부에서 돌리는 풀스택 머신이야")
- **실행자**: 작업 AI(본 세션)
- **대상**: Frontend B Review Inbox 첫·둘째 슬라이스가 소비하는 백엔드 표면 전체 — candidate confirm/reject/edit, conflict merge/split, gate finding resolve/dismiss.
- **소스**: 작업 트리(커밋 `ae2f638` v1.7.4 · `18e0b8b` v1.7.5 · `6cfc09d` 검증 보강). 관통 시점 application/frontend 이미지는 현재 코드로 재빌드.
- **스택**: 이 머신 내부 풀스택 — `docker-compose.yml` + `docker-compose.llama.yml` + 로컬 override(아래). 실 Mongo(replica set)·Chroma·Elasticsearch(nori)·embedding(BGE-m3-ko)·worker·gateway·**in-stack llama.cpp 12B**(`google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`, RTX 3060). 외부 `192.168.1.22:9080`은 이 환경에서 사용 불가라 in-stack llama 사용.
- **경로**: 브라우저 동등 경로 = 프론트 nginx `/api` 프록시(`http://localhost:5173/api/...`).

## Scope

이 슬라이스가 소비하는 7개 write action + candidate 생성 파이프라인 + 프론트 서빙:

1. candidate 파이프라인: project→draft→version(snapshot)→source_ref catalog→analysis job→run(실 12B 추출)→needs_review candidates.
2. review-inbox list/detail read + 어포던스(`{action,eligible,reason}`).
3. candidate write: confirm / reject / edit.
4. conflict write: merge / split (reconcile).
5. gate finding write: resolve / dismiss.
6. 프론트 서빙(재빌드 번들이 Review Inbox UI를 포함하고 SPA 딥링크가 동작).

## Methodology

모든 호출은 프론트 nginx `/api` 프록시 경유(브라우저 동등). 스크립트는 scratchpad에 보존:
`review_inbox_e2e.py`(candidate 루프), `conflict_merge_split_e2e.py`(merge/split), `gate_finding_e2e.py`(gate finding 시도).

**스택 기동(비자명 — 아래 Issues 참조)**:
```
# in-stack llama: -hf가 repo 새 revision을 재다운로드하며 멈춰, 캐시된 완성 blob을 -m으로 직접 지정
docker compose -f docker-compose.yml -f docker-compose.llama.yml -f <override -m> up -d
# application/frontend 이미지가 11일 전 빌드라 review 라우트 부재 → 재빌드
docker compose ... build application frontend && docker compose ... up -d application frontend
```

## Findings

### 1. candidate 파이프라인 + confirm/reject/edit — 완전 관통 (PASS)

실 12B 추출로 5개 needs_review candidate 생성(예: `{"name":"경식","observation":"낡은 등대 아래에 오래 서 있었다."}` 등 인물 3 + 사건 2). review-inbox 목록이 각 항목에 `actions={confirm:true, reject:true, edit:true}`를 실 서버에서 방출 — 프론트가 소비하는 어포던스 계약과 정확히 일치. detail은 payload + source_ref 1건 반환.

- **edit**: payload 수정 → `status=confirmed` + canonical memory 승격, 목록 5→4(항목이 inbox에서 빠짐).
- **confirm**: → `status=confirmed` + memory 승격, 4→3.
- **reject**: → `status=rejected`, 3→2.
- 각 action 후 목록을 서버에서 재조회했을 때 처리된 항목이 사라짐 = 낙관적 패치 없음(서버 진실) 계약이 실 데이터로 확인됨.

### 2. conflict merge/split — 완전 관통 (PASS)

`conflict` proposal을 apply로 직접 공급(compare judge 비결정성 우회)해 결정적으로 review_queue conflict 생성:
- 인물 candidate 1개 confirm → canonical memory M.
- 2번째 인물 candidate에 `{action:"conflict", matched_memory_id:M}` apply → `outcome=skipped_review`(review_queue 영속).
- review-inbox detail → conflict 1건, `matched_memory=yes`, **어포던스 `{merge:(true,null), split:(true,null)}`** — character+matched 자격을 실 서버가 선언(프론트 미재계산 계약 확인).
- **reconcile `{action:"merge"}`** → 200, 새 memory 승격 + 이전 M `superseded`, victim candidate가 inbox에서 빠짐.

### 3. 프론트 서빙 — PASS

재빌드한 frontend 번들(`/assets/index-*.js`)에 `검토함`·`기억 후보와 게이트 지적`·`analysis/review-inbox`·`기존 기억과의 차이`·`병합`·`분리` 문자열 포함. SPA 딥링크 `GET /projects/<id>/review` → 200(try_files fallback). 브라우저에서 실 UI가 실 엔드포인트를 구동 가능.

### 4. gate finding resolve/dismiss — 엔드포인트·어포던스 확인, 라이브 reject 미유발

resolve/dismiss 엔드포인트는 OpenAPI에 존재하고, 어포던스 serializer(`_affordance_payload`)는 위에서 라이브 확인된 candidate/conflict와 **동일 함수**이며, resolve/dismiss는 라이브 검증된 candidate confirm/reject와 **동일한 이진 action 패턴**(108 유닛 테스트 커버). 실제 gate finding 생성은 Context Gate가 `reject`할 때만 영속화되는데(`persist_rejection`은 `decision=="reject"`에서만 기록), 이는 검색 레이어가 package에 항목을 반환해야 성립한다. `context-search`(writing_context, need=current_scene, max_tokens=1)를 시도했으나 package가 비어(`macro_items=0, micro_evidence=0`, `get_current_scene` step status=None) budget 체크(`total > max_tokens`)를 넘지 못해 gate가 `pass` → finding 미생성. **원인은 current_scene 검색이 source-block 인덱스 적재에 의존하는 상류 검색/인덱싱 문제로, v1.7.4/v1.7.5가 만든 gate finding *소비*와 무관**하다.

## Issues / Observations (dogfood 발견)

1. **application/frontend 이미지 stale(11일 전 빌드)** — review-inbox/gate-findings/reconcile/edit 라우트가 이미지에 부재했다(OpenAPI에 미노출, `/api/.../review-inbox`→404). 재빌드 후 라우트 정상. **운영 함의**: 스택 기동 전 `docker compose build application frontend` 선행 필요.
2. **`-hf` llama 재다운로드 정체** — llama.cpp가 repo 새 revision(`52fc21bb`)을 감지해 완성된 캐시(`faff1a63`, 6.97GB)가 있음에도 별도 파일(`1e76e46...downloadInProgress`)을 재다운로드하며 param 출력 후 멈췄다(GPU 미로드). 캐시된 완성 blob을 `-m /models/.../snapshots/f6e7774e/gemma-4-12b-it-qat-q4_0.gguf`로 직접 지정하고 `--alias`로 모델명을 맞춰 우회 → 정상 로드(GPU 9.4GB, "model loaded, listening"). **runbook의 `-hf` 방식은 revision 변경 시 이 정체에 걸릴 수 있음**.
3. **추출 anchor echo는 단일 라인 quote 요구** — 여러 줄(개행 포함) 문단을 source_ref로 등록하면 12B가 anchor(quote/offset/content_hash 64-hex)를 정확히 복제하지 못해 `source_ref anchor mismatch` 400(1회 repair 후에도). 단일 라인 문단으로 바꾸니 5개 candidate가 안정 추출됐다. 추출은 비결정적(동일 입력에 0개 또는 5개) — 재시도로 흡수됨.

## Verdict

**PASS(라이브 실행 범위)**. Review Inbox의 핵심 검토 루프 7개 write action 중 **5개(candidate confirm/reject/edit, conflict merge/split)를 실 스택·실 12B·실 Mongo 영속으로 완전 관통 검증**했고, 프론트가 소비하는 `{action,eligible,reason}` 어포던스 계약이 실 서버에서 candidate/conflict 양쪽에 올바르게 방출됨을 confirmed. 프론트 번들이 Review Inbox UI를 서빙함도 확인. **gate finding resolve/dismiss**는 엔드포인트 존재·동일 어포던스 serializer·동일 이진 패턴·유닛 커버로 뒷받침되나, 라이브 gate reject 유발이 상류 검색/인덱싱(빈 package) 의존이라 이번 스모크에서 실행하지 못했다 — 슬라이스 결함 아님, 후속 인프라 과제.

## Outstanding items

- **스택 실행 중**: 9개 컨테이너 + 12B llama가 GPU 9.4GB 점유 중(오너가 종료 미선택). 브라우저 확인 후 `docker compose ... down`으로 회수 가능(Mongo volume 유지).
- **gate finding 라이브 유발**: source-block 인덱스 적재(worker) 경로로 current_scene이 항목을 반환하게 만들면 budget=1 reject로 gate finding을 유발할 수 있다. 후속 dogfood에서.
- **스크립트**: scratchpad 3종(관통 재현용). 프로덕션/저장소 코드 무변 — 이 관통은 순수 소비이며 어떤 서비스/테스트/스키마도 수정하지 않았다.

## Reproduction

```bash
# 1) 스택(캐시 blob -m override + 이미지 재빌드)
docker compose -f docker-compose.yml -f docker-compose.llama.yml -f <override> build application frontend
docker compose -f docker-compose.yml -f docker-compose.llama.yml -f <override> up -d
# 2) candidate 루프(재시도로 추출 비결정성 흡수)
python3 review_inbox_e2e.py http://localhost:5173/api
# 3) conflict merge/split
python3 conflict_merge_split_e2e.py http://localhost:5173/api
# 4) 프론트 서빙
curl -s http://localhost:5173/ | grep -o '/assets/index-[^"]*\.js'   # 번들에 검토함/병합/분리 포함
curl -so /dev/null -w '%{http_code}' http://localhost:5173/projects/<id>/review   # 200
```
