# Slice 1 재검증 폐쇄(R1/R2/R3) + Docker 런타임 독립 검증

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("다음작업 검증하고 의심하고 또 의심해줄래?")
- **검증자**: Claude (본 세션)
- **대상 커밋**:
  - `89153b6` — Core SOT → MongoDB adapter 연결 + 재검증 R1/R2/R3 보강
  - `ddac62f` — Application + MongoDB replica-set Docker 런타임 (HANDOFF Next Task #1)
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.4** §112-114 (Approved)
  - cross-ref: `docs/plans/01-core-sot.md` §75-79
- **선행 검증**: `docs/verifications/2026-06-28/mongo_adapter_recheck.md` (조건부 합격)
- **작업 출처**: 두 커밋 모두 committed (`git log` 확정). working tree clean.
- **검증 입장**: 선행 재검증의 "조건부 합격" load-bearing 조건(R1)이 폐쇄됐는지, R2 사용자 결정이 근거 기반으로 계약에 닫혔는지, Docker 런타임이 실제로 동작하는지를 증명(주장 수용 금지).

## Scope

1. **R1 폐쇄**: `tests/test_core_sot_mongo.py` import guard — pymongo 미설치 시 discovery 회복
2. **R2 계약 폐쇄**: SoT v1.4 §114 single-writer ↔ `mongo_repository.py` docstring/주석 ↔ plan §78 ↔ work_log 사용자 결정 근거 정합
3. **R3 추적**: `source_refs` 보존(§113) HANDOFF/work_log 추적
4. **Docker runtime**: `services/application/Dockerfile`, `docker-compose.yml`, `.dockerignore`, `requirements.txt`
5. **Docker 실구동**: compose build/up → API save/replay idempotency → draft_versions 단일 → down (독립 재현)
6. **문서 일관성**: HANDOFF/CHANGELOG/work_log의 v1.4 bump와 기존 "계약 변경 없음" 모순 해소

## Methodology

### 1. R1 동적 증명 (주장 수용 금지)

pymongo + bson + adapter import chain을 `sys.modules[*] = None`으로 완전 차단한 뒤 **전체** `unittest discover` 실행. errors=0 이면 R1 폐쇄 증명.

### 2. R2 계약 정합 (file:line 교차)

SoT §114 literal ↔ `mongo_repository.py` docstring/주석 ↔ plan §78 ↔ work_log "사용자 결정 option (b)" 근거를 행 단위 비교. SoT §112(요구사항) ↔ §114(적용 범위) 내부 일관성 점검.

### 3. Docker 실구동 (사용자 요약 검증)

```bash
docker compose config -q                       # 검증
docker compose up -d --build                   # 빌드 레이어 순서 확인
# mongo healthy + app /health 대기
# project → draft → save(k1) → save(k1, MUTATED) → mongosh countDocuments
docker compose down -v                         # 정리
```

assert: save1 idempotent_replay=false / save2 idempotent_replay=true / 동일 version id / version_number=1 / blocks=4 / draft_versions count=1.

## Findings

### Surface 1 — R1 load-bearing 조건 폐쇄 (동적 증명)

`test_core_sot_mongo.py:20-36`이 pymongo + `MongoCoreSotRepository` import를 `try/except ImportError`로 감싸고 `_PYMONGO_AVAILABLE` 플래그를 둔다. `_probe_mongo()`(`:60-61`)는 플래그 False 시 즉시 `(False, False)` 반환 → `@skipUnless(False)`로 skip.

**독립 증명** (pymongo/bson/adapter import chain 전부 차단 후 전체 discover):
```text
Ran 168 tests in 0.105s
OK (skipped=17)
errors=0 failures=0 skipped=17 run=168
```
선행 재검증의 R1 regression(`errors=1`)이 **`errors=0`으로 회복**됐음을 증명. service/adapter 코드는 무관(test 파일만). ✓ **R1 폐쇄.**

### Surface 2 — R2 계약 폐쇄 (single-writer, 정합)

- **SoT v1.4 §114**(`system-contract-sot.md:114`): *"non-transaction fallback은 **single-writer 전용**이다. 같은 (project_id, draft_id, idempotency_key)에 대한 동시 draft save는 fallback에서 보장하지 않으며(orphan cleanup이 동시 writer의 committed dependents를 지울 수 있음), 동시성 안전이 필요한 runtime은 transaction 기본 경로를 사용한다."*
- **변경 이력**(`:36`): *"사용자 결정(R2 option b), `docs/verifications/2026-06-28/mongo_adapter_recheck.md`"* — 근거 + 검증 기록 인용 포함. minor bump(v1.3→v1.4) 정당(구현 계약 의미 변경).
- **plan §78**(`plans/01-core-sot.md`): *"fallback은 single-writer 전용이다(SoT v1.4). 같은 save request의 동시 진입은 보장하지 않으며, orphan cleanup/retry guard는 같은 writer의 순차 재시도에만 정의된다."* — SoT와 정합.
- **adapter docstring**(`mongo_repository.py:16-17`): *"**single-writer only**: its orphan cleanup / retry guard are defined for one writer's sequential retries, not for concurrent saves of the same request."*
- **adapter 주석**(`mongo_repository.py:203`): *"writer's sequential retries but would drop a concurrent writer's..."*
- **사용자 결정 근거**(`work_log.md:75-79`): option (b) 선택 + 근거("fallback은 spec상 local/test 제한 경로, production은 transaction path 동시성 안전, 단일 사용자 로컬 MVP에 동시성 복잡도는 과함") 기록 — CLAUDE.md "User Decisions and Rationale" 요구사항 충족.
- **내부 일관**: §112(fallback 요구사항: write order/lookup/orphan cleanup/retry guard) ↔ §114(그 적용 범위: single-writer). 충돌 아님 — §112는 무엇을 가져야 하는지, §114는 어디에 적용되는지. ✓
- **process**: 선행 재검증이 R2를 "사용자 결정 필요"로 남겼고, 본 작업이 사용자 결정 option (b)로 폐쇄. 임의 구현 아님. ✓

✓ **R2 contract 폐쇄.** orphan cleanup 동시성 bug는 이제 spec-silent가 아니라 **명시적 contract-out**(fallback single-writer)으로 닫힘.

### Surface 3 — R3 추적 (scope-out, 정확한 처리)

`source_refs` collection은 여전 미구현(`create_source_ref`는 `SourceRef` 반환만, persist 안 함 — minimal skeleton과 동일). `work_log.md:81-83`와 HANDOFF Next Tasks에 SourceRef persistence slice 추적으로 명시. 본 slice(draft save write set + transaction/fallback) scope 밖이므로 blocking 아님. 선행 재검증이 지적한 "source_refs 보존 ✓" 부정확 표시도 정정 반영. ✓

### Surface 4 — Docker runtime (실구동 증명)

독립 재현 결과(`docker compose up -d --build` → API → `down -v`):

| 단계 | 결과 | 근거 |
|---|---|---|
| `compose config` | OK | `config -q` 무출력 통과 |
| 빌드 레이어 순서 | 캐시 보존 | `[3/5] COPY requirements` → `[4/5] pip install` → `[5/5] COPY sources` (build 로그 `:39-43`). Active Decision(HANDOFF:29) 준수 |
| mongo healthy | after 10s | `rs.initiate` idempotent healthcheck 동작 |
| app `/health` | `{"status":"ok"}` after 20s | `depends_on: mongo service_healthy` 기동 순서 보장 |
| save(k1) | version_number=1, **4 blocks**, idempotent_replay=false | heading/paragraph/scene_marker/paragraph, offset 정확 재구성 |
| save(k1, MUTATED) | **동일 version id**, idempotent_replay=true, version_number=1 | idempotent replay |
| `draft_versions` count | **1** | 중복 version 생성 없음 |
| **ALL ASSERTS** | **PASS=True** | save1 false / save2 true / same id / v1 / 4 blocks / count=1 |

- transaction 경로 실사용: replica set(`--replSet rs0`) + `CORE_SOT_MONGO_TRANSACTIONS=true` + `?replicaSet=rs0` URI. transaction 기본 계약(§112)이 런타임에 실제로 적용됨.
- member host `mongo:27017`(`docker-compose.yml:21`)이 compose 서비스명과 일치 → application 컨테이너가 replica set discovery 성공(host 직결의 `?directConnection=true` 우회 불필요).
- `down -v` 후 잔여 컨테이너/볼륨/네트워크 없음 확인.

### Surface 5 — 문서 일관성

- **HANDOFF 모순 해소**: 이전 Next Task #3의 *"계약 변경은 없었다"*가 `HANDOFF.md:69`에서 *"재검증 R2 결정으로 fallback single-writer 제약이 v1.4로 추가됨"*으로 갱신. `:59`에 R2 사용자 결정, `:67` Next Task #2에 "fallback 동시성 race는 v1.4 single-writer로 contract out", `:106` Verification에 재검증 요약.
- **CHANGELOG**: v1.4 single-writer 항목 + Docker runtime 항목 별도 기록, work_log 링크.
- **단위 스위트**: pymongo 설치 환경에서 `168 tests OK (skipped=17)` 유지.

## Issues / Risks

### 비차단 observation (합격에 영향 없음, 운영 진입 시 권고)

1. **application 서비스 healthcheck 미등록**: `docker-compose.yml`에 application healthcheck가 없다(`/health` 엔드포인트는 존재). `depends_on`이 `mongo: service_healthy`만 검사하므로, application 기동 실패/크래시 탐지가 늦을 수 있다. 로컬 단일 사용자 MVP라 비차단이나, 다중 서비스 확장 시 application healthcheck 등록 권장.
2. **mongo `--bind_ip_all`**(`docker-compose.yml:7`): 외부 인터페이스 바인딩. 로컬 MVP라 비차단. 공유/운영 환경 진입 시 bind 제한 또는 네트워크 격리 권장.
3. **uvicorn 단일 worker**: 단일 프로세스. 로컬 단일 사용자 MVP에 적합. 비차단.

### Blocking

**없음.** R1 load-bearing 조건 폐쇄(동적 증명), R2 contract 닫힘(사용자 결정 + 정합), Docker 런타임 실구동 증명, 문서 모순 해소.

## Verdict

**합격 (Pass)**

**근거:**

1. **R1 폐쇄 (선행 조건부 합격의 load-bearing 조건)**: pymongo/bson/adapter import chain 완전 차단 시 `errors=0, skipped=17, run=168`로 회복 — 동적 증명. 선행 재검증의 조건부 합격이 합격으로 승격될 근거 충족.
2. **R2 contract 폐쇄**: SoT v1.4 §114 single-writer 제약이 SoT/plan/adapter docstring·주석에 행 단위로 정합하고, §112 ↔ §114 내부 일관. 사용자 결정 option (b) 근거가 work_log에 기록되어 임의 구현 아님. 동시성 correctness bug는 명시적 contract-out으로 닫힘.
3. **R3 정확 처리**: source_refs 보존은 SourceRef persistence slice로 추적되고, scope-out이 명시됨.
4. **Docker 런타임 실구동**: compose build/up → mongo healthy → /health ok → transaction 경로 save(version 1, 4 blocks) → 같은 key replay(idempotent_replay=true, 동일 version) → draft_versions=1 → down. ALL ASSERTS PASS. 사용자 요약이 독립 재현으로 정확함.
5. **문서 일관성**: HANDOFF "계약 변경 없음" 모순 해소, CHANGELOG v1.4/Docker 항목, work_log 사용자 결정 근거 모두 정합. 단위 스위트 168개(17 skip) 유지.

## Outstanding Items

1. **커밋 상태**: 두 커밋(89153b6, ddac62f) 모두 committed, working tree clean. 게시(publish)는 소유자 결정 대기.
2. **비차단 권고**: 위 observation 1~3(application healthcheck / bind_ip / worker)은 운영 확장 시 검토. 본 slice 범위 밖.
3. **후속 slice**: SourceRef persistence(R3), gateway compose 편입(work_log:102)이 명시된 다음 작업.

## Reproduction

```bash
# R1 증명 (pymongo 완전 차단 → discovery 회복)
python3 -c "import sys,unittest; \
  [sys.modules.update({m:None}) for m in ('pymongo','pymongo.errors','bson','bson.objectid')]; \
  r=unittest.TextTestRunner(verbosity=0).run(unittest.TestLoader().discover('tests')); \
  print('errors',len(r.errors),'skipped',len(r.skipped),'run',r.testsRun)"
# → errors 0 skipped 17 run 168

# Docker 실구동
docker compose config -q
docker compose up -d --build
# wait: curl -fsS http://localhost:8000/health  → {"status":"ok"}
PID=$(curl -fsS -XPOST localhost:8000/projects -H'Content-Type: application/json' -d'{"name":"N"}' | python3 -c'import sys,json;print(json.load(sys.stdin)["id"])')
DID=$(curl -fsS -XPOST localhost:8000/projects/$PID/drafts -H'Content-Type: application/json' -d'{"title":"E1"}' | python3 -c'import sys,json;print(json.load(sys.stdin)["id"])')
curl -fsS -XPOST localhost:8000/projects/$PID/drafts/$DID/versions -H'Content-Type: application/json' -d'{"raw_text":"# H\n\nP.\n\n---\n\nS.","idempotency_key":"k1"}' | python3 -m json.tool
curl -fsS -XPOST localhost:8000/projects/$PID/drafts/$DID/versions -H'Content-Type: application/json' -d'{"raw_text":"MUT","idempotency_key":"k1"}' | python3 -m json.tool
docker compose exec -T mongo mongosh --quiet ai_writing_system --eval "db.draft_versions.countDocuments({})"  # → 1
docker compose down -v
```
