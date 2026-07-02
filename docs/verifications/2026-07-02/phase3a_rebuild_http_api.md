# Phase 3A Explicit Rebuild HTTP API 독립 검증

## Subject metadata

- 검증일: `2026-07-02`
- 요청자: 프로젝트 오너("다음작업 검증해줘 ... Phase 3A explicit rebuild HTTP API를 추가했습니다")
- 검증자: 독립 검증 AI (Claude)
- 검증 대상: Phase 3A 후속 slice — `POST /projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild` endpoint + 3개 회귀 + SoT v1.6.23 갱신
- 정합 스펙 기준:
  - `docs/system-contract-sot.md` v1.6.23(변경 이력 행 + Phase 3 Indexing 단락 신규 bullet)
  - `docs/plans/03-indexing-kickoff-decisions.md` §구현 후속 — explicit rebuild HTTP API
  - `docs/plans/03-indexing.md` 2026-07-02 slice 노트의 HTTP 문장
  - 교차 계약: 직전 slice `scripts/phase3a_rebuild_source_block_index.py`(CLI summary 8-field, SoT v1.6.22), `indexing/service.py::SourceBlockIndexingService.rebuild_snapshot_source_block_index`, `core_sot/service.py` archived/source_ref 허용 정책(SoT v1.6.18)
- 검증 대상 작업 출처: working tree, uncommitted(직전 commit 이후). `git status`로 `services/application/app/main.py`, `tests/test_application_api.py` modified, 6개 doc modified 확인.

## Scope

정합 스펙 스코프를 (1) SoT v1.6.23 changelog 행 + Phase 3 bullet, (2) kickoff 브리프 §구현 후속 HTTP API, (3) `03-indexing.md` slice 노트 HTTP 문장으로 좁혔다. endpoint가 의존하는 indexing rebuild 계약은 직전 slice의 committed 상태를 기준으로 삼고, CLI summary(v1.6.22, 8-field)과의 관계를 교차 점검했다.

검증 surface:

1. 정합 계약(SoT v1.6.23 + 브리프 §구현 후속) 내부 정합성 + JSON summary literal 일치
2. 구현 코드: `main.py::_rebuild_source_block_index_payload`, `rebuild_source_block_index` endpoint, NotFound→404 매핑
3. 교차 정합: CLI summary(8-field)과 HTTP summary(9-field, `backend`)의 의도적 divergence 문서화 여부, archived project/draft 허용 정책 일관성, fake-adapter 비지속성
4. 회귀 테스트: `tests/test_application_api.py` 3개 신규 — public envelope(전 field 동치), archived 집계, 404 경계(missing + cross-project)
5. 작업자 주장 카운트 재현 + 전체 suite + py_compile + `git diff --check`

## Methodology

정합 스펙을 읽어 boundary matrix를 구성한 뒤 코드/테스트에 추적. 작업자 주장을 복사하지 않고 재실행·재도출. 발견은 `TestClient` 실제 호출로 입증.

실행한 명령:

- `git status --short`, `git diff --stat`, `git diff services/application/app/main.py tests/test_application_api.py`(구현 + 테스트 diff)
- `git diff docs/system-contract-sot.md docs/plans/03-indexing*.md CHANGELOG.md`(계약 diff)
- `Read`(serena symbolic 보조)로 `_rebuild_source_block_index_payload`·endpoint 본체, 3개 신규 테스트 본체 열독
- `python3 -m py_compile main.py test_application_api.py`
- `python3 -m unittest tests.test_application_api`(50), `+ script + indexing + core_sot`(89), `discover tests`(375/37) 재실행
- `git diff --check`
- adversarial `TestClient` 실행: archived DRAFT(project 활성) rebuild → query_visible/archived, 같은 snapshot 2회 rebuild 비지속성(누적 여부), `backend` literal·CLI divergence 확인

## Findings

### Surface 1 — 정합 계약 내부 정합성 + literal 일치

- SoT v1.6.23 changelog 행, Phase 3 bullet, kickoff 브리프 §구현 후속, `03-indexing.md` slice 노트가 동일한 endpoint 계약을 서술한다. 모순 없음.
- **endpoint path(양방향)**: `POST /projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild`가 SoT·브리프·코드(`main.py` route decorator)와 정확히 일치.
- **JSON summary literal(양방향)**: SoT v1.6.23이 명시한 9개 field `project_id, snapshot_id, target, backend, records_attempted, records_written, records_indexed, records_query_visible, records_archived`가 `_rebuild_source_block_index_payload` 반환 dict(`main.py:311-322`)와 정확히 일치. 테스트가 전 field 동치로 pin. ✓
- `backend = "in_memory_fake"`(`main.py:318`)가 SoT literal과 일치. 테스트 동치 pin. ✓

### Surface 2 — 구현 코드 vs 스펙/경계

- endpoint(`main.py:585-595`)는 `_rebuild_source_block_index_payload`를 호출하고 `NotFound` → `HTTPException(404)`로 매핑. missing/cross-project snapshot이 `get_snapshot`(`snapshot.project_id != project_id` 또는 snapshot 없음)에서 `NotFound`로 나는 경로와 일치.
- payload 함수는 fresh `InMemoryVectorIndexAdapter`를 만들어 `SourceBlockIndexingService.rebuild_snapshot_source_block_index`로 rebuild한 뒤 `list_records(include_archived=True/False)`로 6개 count field를 채운다.
- **archived project/draft 허용(양방향 입증)**: rebuild는 `get_snapshot`/`get_project`/`get_draft`만 쓰고 이들은 archived 여부로 거부하지 않으므로 archived project/draft에서도 200으로 rebuild된다. 이는 SoT v1.6.18 "archived project에서도 source_ref 생성·조회 허용" 정책과 동일한 read-allowed archive semantics. adversarial로 archived DRAFT(project 활성) rebuild → 200, `records_query_visible=0`, `records_archived=2` 확인.

### Surface 3 — 교차 정합(CLI vs HTTP, 비지속성)

- **CLI/HTTP summary divergence는 문서화됨**: CLI(v1.6.22) summary는 8-field(`backend` 없음), HTTP(v1.6.23) summary는 9-field(`backend="in_memory_fake"` 포함). 양쪽 shape이 SoT에 정확히 pin돼 있어 divergence는 의도적·문서화됨. HTTP가 public API caller에게 serving backend를 알리는 목적이라 정합. (O2 참조)
- **fake-adapter 비지속성(양방향 입증)**: endpoint는 호출마다 fresh `InMemoryVectorIndexAdapter`를 만들고 응답 후 폐기한다. 같은 snapshot 2회 rebuild → `records_indexed=1/1`로 누적 없음 확인. SoT가 "Persistent vector backend와 automatic sync는 후속"이라 명시하므로 현재 endpoint는 "rebuild 결과를 계산해 보고"하는 dry-run 성격이며, 빌드된 인덱스를 나중에 query할 HTTP surface는 아직 없다. 문서화된 fake-adapter 동작. (R1 참조)

### Surface 4 — 회귀 테스트가 public 표면을 pin 하는지

- `test_source_block_index_rebuild_endpoint_returns_fake_adapter_summary`: 응답 전체 동치(9 field 포함). envelope을 완전히 pin. ✓
- `test_source_block_index_rebuild_filters_archived_project_records`: `DELETE /projects/{id}`(archive) 후 rebuild → `records_indexed=2`, `records_query_visible=0`, `records_archived=2`. archived 집계 양방향 pin. ✓
- `test_source_block_index_rebuild_rejects_missing_and_cross_project_snapshot`: missing snapshot(`nope`) 404 + cross-project snapshot 404. 404 경계 양쪽 pin. ✓
- 보충: archived DRAFT 집계와 missing-project(순수) case는 HTTP 테스트에 명시적이 않지만, draft 분기는 indexing layer 회귀로 잠겨 있고(`test_archived_draft_records_are_filtered_without_project_archive`), missing-project는 `get_snapshot`의 `project_id != project_id` NotFound 경로로 구조적 커버. adversarial로 둘 다 정상 동작 확인.

### Surface 5 — 작업자 주장 카운트 재현

- `py_compile main.py test_application_api.py` → OK
- `tests.test_application_api` → **50 OK**(주장 일치; 직전 47 + 3 신규)
- `+ script + indexing + core_sot` → **89 OK**(주장 일치)
- `discover tests` → **375 OK (skipped=37)**(주장 일치)
- `git diff --check` → 종료 0(주장 일치)

## Issues / Risks

블로킹 이슈 없음. 비블로킹 관찰:

### O1 — summary 빌드 로직이 CLI와 HTTP에 중복(비블로킹, DRY · 권장)

`_rebuild_source_block_index_payload`(`main.py:298-323`)가 CLI `rebuild_source_block_index`(`scripts:61-92`)와 동일한 rebuild+summary 계산(fresh adapter 생성 → service build → rebuild → `list_records` 2회 → 6개 count field)을 복제하고, HTTP만 `backend`를 추가한다. 공유 helper가 없어 summary semantics가 바뀌면 양쪽을 동기화해야 한다. 정리 방향: 공통 rebuild+summary를 `indexing/service.py`로 추출하고 CLI/HTTP가 표면 고유 필드(`backend` / exit code)만 더하도록 구성. 단 HTTP가 `scripts/`를 import하면 안 되므로(layering) 추출 대상은 indexing domain이다. 두 surface가 독립 테스트(8-field vs 9-field)라 drift를 한쪽만 잡는 경우 대비가 안 돼 있어, 추출이 가장 시급한 비블로킹 권고다.

### O2 — `backend` field/value 공간이 미정의(비블로킹, future)

HTTP `backend="in_memory_fake"`는 bare string이고 허용 값 집합(enum)이 계약에 없다. 단일 backend 첫 slice라 bare string이 수용 가능하나, real Chroma/ES backend가 도입되면 `backend` 값이 바뀌고 허용 enum을 SoT에 정의해야 한다. CLI에는 `backend`가 아예 없다는 divergence도 함께 문서화돼 있으므로, 후속에서 enum 정의 시 CLI 표출 여부도 함께 결정할 것.

### O3 — HTTP 에러 표면이 CLI보다 좁음(비블로킹, latent)

HTTP는 `NotFound`만 `except`→404. CLI은 모든 `ValueError`(`NotFound`/`Archived`/...) → exit 2. 현재 `rebuild_snapshot_source_block_index`는 `NotFound`만 raise하므로(`get_snapshot`/`get_project`/`get_draft`가 archived로 거부 안 함) 실제 500은 발생하지 않는다. 하지만 rebuild가 다른 `CoreSotError`를 raise하는 경로가 생기면 HTTP는 500, CLI은 exit 2로 갈라진다. 현재 동작 기준으론 안전.

### R1 — 현재 rebuild는 비지속적 dry-run(비블로킹, 설계적)

endpoint는 fake adapter로 summary를 계산해 반환하지만 인덱스를 persist하지 않는다(호출마다 fresh adapter, 응답 후 폐기). SoT가 "Persistent vector backend는 후속"이라 명시하므로 문서화된 동작이다. 다만 endpoint 이름 "rebuild"를 보고 나중에 query 가능한 인덱스가 쌓인다고 가정할 수 있으므로, persistent backend 후속 slice 전까지는 이 endpoint가 dry-run/contract-demo임을 소비자가 인지해야 한다.

## Verdict

**합격(pass).**

이유:

- 블로킹 이슈가 없다. endpoint path·9-field summary·`backend="in_memory_fake"` literal·404 경계가 SoT v1.6.23과 정확히 일치하고, 구현이 해당 계약을 충실히 반영한다.
- public envelope가 전-field 동치 테스트로 pin돼 있고, archived project 집계(query_visible 0 / archived 2)와 404 양쪽 경계(missing + cross-project)가 회귀로 잠겨 있다. archived DRAFT 분기도 indexing layer 회귀 + adversarial HTTP 확인으로 커버된다.
- 작업자 주장 카운트(50/89/375+37)·py_compile·`git diff --check`가 정확히 재현됐다.
- CLI(v1.6.22, 8-field)과 HTTP(v1.6.23, 9-field)의 `backend` divergence가 양쪽 SoT에 정확히 pin돼 있어 의도적이며 문서화됐다.

O1(summary 로직 중복 → indexing domain 추출 권장)·O2(`backend` enum 미정의)·O3(HTTP 에러 표면 좁음, 현재 안전)·R1(비지속 dry-run, 설계적)은 모두 비블로킹이다. O1이 가장 실행 가능한 권고(두 surface의 drift 방지).

## Outstanding items

- 작업 트리에 uncommitted(오너 커밋 승인 전). 본 검증은 working tree 기준.
- 권장(비블로킹, 합격 불변): (a) 공통 rebuild+summary를 `indexing/service.py`로 추출해 CLI/HTTP 중복 제거(O1), (b) 후속 backend 도입 시 `backend` enum 정의(O2).
- 후속 slice 후보(HANDOFF/SoT에 반영): persistent vector backend, automatic sync, rebuild 결과를 query하는 search endpoint.

## Reproduction

```bash
# 카운트 재현(작업자 주장과 동일)
python3 -m py_compile services/application/app/main.py tests/test_application_api.py
python3 -m unittest tests.test_application_api                                            # 50
python3 -m unittest tests.test_application_api tests.test_phase3a_rebuild_source_block_index_script \
    tests.test_indexing_phase3a tests.test_core_sot                                       # 89
python3 -m unittest discover tests                                                        # 375, skipped=37
git diff --check                                                                          # clean

# archived DRAFT via HTTP + 비지속성 + backend divergence adversarial 확인
python3 -c "
from fastapi.testclient import TestClient
from services.application.app.main import create_app
c = TestClient(create_app())
# archived draft (project active)
p=c.post('/projects',json={'name':'N'}).json(); d=c.post(f'/projects/{p[\"id\"]}/drafts',json={'title':'E'}).json()
sv=c.post(f'/projects/{p[\"id\"]}/drafts/{d[\"id\"]}/versions',json={'raw_text':'문장 하나.\n\n문장 둘.','idempotency_key':'k'}).json()
c.delete(f'/projects/{p[\"id\"]}/drafts/{d[\"id\"]}')
r=c.post(f'/projects/{p[\"id\"]}/snapshots/{sv[\"snapshot\"][\"id\"]}/index/source-blocks/rebuild')
print('archived draft:', r.status_code, r.json()['records_query_visible'], r.json()['records_archived'])
# non-persistence (2 calls, no accumulation)
p2=c.post('/projects',json={'name':'M'}).json(); d2=c.post(f'/projects/{p2[\"id\"]}/drafts',json={'title':'E'}).json()
sv2=c.post(f'/projects/{p2[\"id\"]}/drafts/{d2[\"id\"]}/versions',json={'raw_text':'오직 한 문장.','idempotency_key':'k2'}).json()
url=f'/projects/{p2[\"id\"]}/snapshots/{sv2[\"snapshot\"][\"id\"]}/index/source-blocks/rebuild'
print('non-persistent:', c.post(url).json()['records_indexed'], c.post(url).json()['records_indexed'])
"
```
