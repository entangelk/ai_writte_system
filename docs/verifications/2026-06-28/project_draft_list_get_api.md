# project/draft list/get API 독립 검증 (Core SOT round-trip 완성)

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("다음작업 검증해줘")
- **검증자**: Claude (본 세션)
- **대상 커밋**: `d9a023a` — feat: add project/draft list/get API (Core SOT round-trip)
- **정본 spec 참조**:
  - `docs/system-contract-sot.md` **v1.4** §20 (project_id 격리), §113 (archive 보존)
  - `docs/plans/01-core-sot.md` §13-14, §20, §93 (Draft)
- **작업 출처**: committed. working tree clean.
- **검증 입장**: 커밋에 실제로 모든 파일이 포함됐는지(stat 정확성), 정렬이 backend마다 달라 계약 위반이 아닌지, 응답 shape가 기존 create를 regression시키지 않는지, project_id 격리 should-NOT-fire가 lock됐는지를 증명.

## Scope

1. **커밋 무결성**: d9a023a가 main/service/repository/mongo/test 모두 포함하는지
2. **API 엔드포인트 4종**: `main.py` GET /projects, /projects/{id}, /projects/{id}/drafts, /projects/{id}/drafts/{draft_id}
3. **project_id 격리**: §20/§93 — list_drafts 필터, get_draft cross-project NotFound (should-NOT-fire)
4. **응답 shape**: `_project_payload`/`_draft_payload` 헬퍼, 기존 create shape 보존
5. **정렬 일관성**: in-memory insertion order vs Mongo `_id` ASCENDING
6. **실구동**: Mongo replica set 182개 + list mixin 재현

## Methodology

### 1. 커밋 무결성 교차 증명

`git show --stat`(전체) + `git log -S "async def list_projects"` / `"def list_projects"` 로 list 코드가 d9a023a에 추가됐음을 이중 확인.

### 2. Boundary matrix (§13/§14/§20/§93 → 분기 → test)

list/get 엔드포인트의 should-fire(존재→200) / should-NOT-fire(cross-project/없음→404, 다른 project draft 미노출) 분기를 test에 1:1 추적. 빈 칸 점검.

### 3. 독립 실행

```bash
python3 -m unittest discover -s tests                              # 182, 23 skip
# replica set
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest discover -s tests                            # 182, 0 skip
CORE_SOT_TEST_MONGO_URI=... python3 -m unittest tests.test_core_sot_mongo -v  # 23 mixin
```

## Findings

### Surface 1 — 커밋 무결성 (첫 의심 해소)

`git show --stat d9a023a` 전체: `main.py(+48)`, `service.py(+22)`, `repository.py(+4)`, `mongo_repository.py(+8)`, `test_application_api.py(+49)`, `test_core_sot_mongo.py(+21)`, docs 3개. `git log -S`로 `list_projects` 코드가 d9a023a에서 처음 추가됨을 교차 증명. ✓ 작업자 주장과 일치.

### Surface 2 — API 엔드포인트 + 404 처리 (main.py:85-111)

| 엔드포인트 | 동작 | NotFound 매핑 |
|---|---|---|
| `GET /projects` | list, 빈 시 `{"projects": []}` | — |
| `GET /projects/{id}` | 단건 | 404 |
| `GET /projects/{id}/drafts` | project별 list | 404(project 없음) |
| `GET /projects/{id}/drafts/{draft_id}` | 단건 | 404(없음/cross-project) |

NotFound → 404 매핑이 기존 create_draft/save_draft와 동일(`main.py:93-94, 101-102, 109-110`). 상태 코드 일관. ✓

### Surface 3 — project_id 격리 (§20/§93, should-NOT-fire lock)

- **list_drafts**: service `_require_project` + repo filter(`service.py list_drafts`; Mongo `find({"project_id": project_id})`, `mongo_repository.py:139`). query level 격리.
- **get_draft**: `_require_draft`(`service.py:178`)가 `draft.project_id != project_id` 시 NotFound → cross-project 404.

**should-NOT-fire 회귀**:
- `test_draft_list_get_and_project_isolation`(test_application_api.py:62) — `listed_b == []`(B가 A draft 못 봄), 주석로 should-NOT-fire 명시.
- `test_get_draft_cross_project_returns_404`(:80) — cross-project draft → 404, missing project drafts → 404.
- Mongo mixin `test_project_and_draft_list_get_round_trip_with_isolation`(test_core_sot_mongo.py:137) — `list_drafts(project_b.id) == ()`.

boundary matrix: should-NOT-fire 분기가 API + Mongo 양 경로에 lock. 빈 칸 없음(핵심 격리). ✓

### Surface 4 — 응답 shape regression 없음

`_project_payload` = `{id, name, archived}`(`main.py:69-70`), `_draft_payload` = `{id, project_id, title, archived}`(`:72-78`). 이전 커밋의 create_project/create_draft 응답 literal과 동일(헬퍼로 추출만). create_draft도 헬퍼 재사용(`:123`).

**shape 일치 회귀**: `test_project_list_and_get_round_trip`(:55)가 `fetched.json() == created`로 create ↔ get shape 동일 검증, `test_draft_list_get_and_project_isolation`(:78)이 `fetched.json() == draft_a`로 동일. **regression 없음.** ✓

### Surface 5 — 정렬 일관성 (의심 → 작업자 명시적 인지)

- in-memory `list_projects`: `tuple(self.projects.values())` — insertion order.
- Mongo `list_projects`: `.sort("_id", ASCENDING)`(`mongo_repository.py:128`) — ObjectId timestamp+counter 순.

양쪽 모두 **"생성 순서" 의미**로 대응(in-memory id `project-N` 순차 생성, Mongo ObjectId 시간순). 작업자가 이 차이를 **명시적으로 인지·문서화**(`work_log:133`). 숨기지 않음.

**test 한계**: list test가 `assertIn`(포함)만 검증하고 **다중 element 순서를 검증하지 않음**. → boundary matrix 관점에서 "list 순서" 칸이 spec-silent(plan §13/14가 순서 명시 안 함)이고 test로 lock 안 됨. 다만 의미적 일관(양쪽 생성 순서) + 작업자 명시적 인지이므로 **비차단**.

### Surface 6 — 실구동 재현 (사용자 주장 검증)

| 단계 | 결과 |
|---|---|
| 단위 스위트(Mongo 미연결) | 182 tests, **OK (skipped=23)** |
| replica set 전체 discover | **182 tests, OK (0 skipped)** |
| list mixin(fallback+transaction) | `test_project_and_draft_list_get_round_trip_with_isolation` 양 경로 **ok**; 총 23개 **OK** |

사용자 주장(182 / 23 skip / 연결 시 전부 통과) 정확. ✓

### Surface 7 — SoT 변경 없음 주장

plan 01 §13-14 "조회·목록" 구현, §20/§93 project_id 격리 충족. 신규 public literal 없음 → SoT 변경 불필요. 주장 타당. ✓

## Issues / Risks

### 비차단 observation (합격에 영향 없음)

1. **다중 element list 정렬 순서 test 부재**: list test가 포함(`assertIn`)만 검증, 다중 project/draft 순서 미검증. plan §13/14가 순서를 명시하지 않으므로 spec-silent이고, 작업자가 in-memory(insertion)/Mongo(`_id` ASC) 차이를 명시적으로 인지(`work_log:133`). 양쪽 "생성 순서"로 의미 일관 → 비차단. 단, 순서가 후속 Phase에서 계약의 일부가 되면 explicit sort order(예: created_at) 명시 + 회귀 필요.
2. **archive된 project/draft의 list/get 동작 test 부재**: `_require_project`/`_require_draft`가 archived를 차단하지 않아 archive된 project/draft도 list/get 조회 가능. 이것은 §113 보존 계약(archive = 쓰기 차단 + 읽기 허용)과 일관하나, **명시적 test 없음**. spec-silent(archive 후 list/get 동작 plan/SoT 미명시). 비차단 — 보존 계약상 자연스럽지만 boundary lock 차원 권고.
3. **`GET /projects/{id}/drafts/{draft_id}` "존재하지 않는 draft_id → 404" 별도 test 없음**: cross-project 경로(:80)만 검증, "draft 자체 부재" 경로는 별도 test 없음. `_require_draft` NotFound 매핑이 자명하므로 비차단이나 completeness 권고.

### Blocking

**없음.** 커밋 무결성, project_id 격리 should-NOT-fire lock(API+Mongo), 응답 shape regression 없음, 404 일관, Mongo 양 경로 182/23 재현.

## Verdict

**합격 (Pass)**

**근거:**

1. **커밋 무결성**: d9a023a가 main/service/repository/mongo/test 전부 포함(stat + `git log -S` 교차 증명). 작업자 주장 정확.
2. **project_id 격리 (§20/§93)**: list_drafts query-level filter + get_draft cross-project NotFound가 API + Mongo 양 경로 should-NOT-fire 회귀로 lock.
3. **응답 shape regression 없음**: `_project_payload`/`_draft_payload` 헬퍼가 기존 create shape을 그대로 보존, round-trip equality test로 검증.
4. **404 일관**: missing project / cross-project draft / missing project drafts 모두 404, 기존 endpoint 매핑과 동일.
5. **정렬 인지**: 작업자가 in-memory/Mongo 정렬 차이를 명시적으로 문서화(work_log:133), 양쪽 "생성 순서"로 의미 일관.
6. **Mongo 실구동**: 단일 노드 replica set에서 182개(0 skip) + list mixin 양 경로 재현.
7. **SoT 변경 없음**: plan §13-14/§20/§93 구현 충족.

## Outstanding Items

1. **커밋 상태**: d9a023a committed, working tree clean. 게시는 소유자 결정 대기.
2. **비차단 추적**: observation 1(정렬 순서)·2(archive list/get)·3(missing draft 404)은 명시적 boundary lock이 권고되나 본 slice 합격에 영향 없음. 후속 rename/version-read slice에서 회귀 추가 제안.
3. **후속 slice(작업자 명시)**: rename(수정) API, version read API, plan 01 최소 산출물 #7(fixture), gateway compose 편입.

## Reproduction

```bash
# 단위 스위트 (Mongo 미연결)
python3 -m unittest discover -s tests                                    # 182, skipped=23

# Mongo replica set 전체 + list mixin
docker run -d --name coresot-mongo-test -p 27018:27017 mongo:7 --replSet rs0
# wait myState==1
docker exec coresot-mongo-test mongosh --quiet --eval 'rs.initiate()'
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest discover -s tests                                  # 182, 0 skip
CORE_SOT_TEST_MONGO_URI="mongodb://localhost:27018/?directConnection=true" \
  python3 -m unittest tests.test_application_api tests.test_core_sot_mongo -v
docker rm -f coresot-mongo-test

# 커밋 무결성 교차 확인
git show --stat d9a023a | grep -E "main.py|service.py|repository.py"
git log --oneline -1 -S "async def list_projects" -- services/application/app/main.py
```
