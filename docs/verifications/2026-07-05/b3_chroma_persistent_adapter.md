# Verification — Phase 4 B.3 Chroma persistent vector adapter (commit b9de408)

## Subject metadata

- 검증일: 2026-07-05
- 요청자: owner ("클로드 작업AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? B.3를 완료·커밋했습니다(b9de408). … 다음: B.4 (wiring) … 바로 B.4로 이어서 진행할까요?")
- 검증자: 독립 검증 AI(Claude, 작업 AI와 다른 세션; `shared_vector_index_slice.md`, `deployed_smoke_rebuild_first.md`, `real_vector_backend_brief_b1_embedding_seam.md`, `b2_embedding_service_container.md`에 이어 동일 세션)
- 대상 slice/artifact: commit `b9de408` "B.3: Chroma persistent vector adapter" — `services/application/app/indexing/chroma.py`(신규, 202행: `ChromaVectorIndexAdapter` + `record_to_chroma`/`record_from_chroma` + `connect_chroma_collection`), `tests/test_chroma_adapter.py`(신규 회귀 9개 273행), `docker-compose.yml`(chroma 서비스 +24, `chroma_data` volume), `services/application/requirements.txt`(`chromadb>=0.5,<0.7`).
- 정본 계약 참조:
  - `docs/plans/04-real-vector-backend-decisions.md`(상태 `Approved (2026-07-05)`) — sub-slice **B.3**(line 102) "기존 `VectorIndexAdapter`/`VectorSearchAdapter` seam 뒤로 real 영속 Chroma adapter(thin client) 구현… base compose 서비스 컨테이너 + persistence volume… skip-aware live Chroma 통합 테스트로 upsert/query/재시작 생존을 잠근다"; §4 인프라(컨테이너 + persistence volume, **base compose 편입**); §5 테스트(skip-aware live + fake 단위); §6 계약 표면(`backend="chroma"` literal은 wiring 시 — B.4, **이 slice 아님**); line 87 범위 제약 "이 slice는 **rebuild write + query read 경로만** real로 올린다"(worker→Chroma archive mutation은 후속).
  - 선행 seam: `services/application/app/indexing/service.py` `VectorIndexAdapter`(line 48, `upsert_records`) + `InMemoryVectorIndexAdapter`(line 236, fake — 동등성 기준) + `_cosine_similarity`(line 642); `services/application/app/context_search/service.py` `VectorSearchAdapter`(line 87, `query_similar` 시그니처).
  - `services/application/app/indexing/models.py` `SourceBlockIndexRecord`/`IndexPointer`/`IndexRecordKind`(직렬화 필드 원천).
  - 직전 B.2 검증 `docs/verifications/2026-07-05/b2_embedding_service_container.md` §Outstanding items "B.3 Chroma persistent adapter" 정의.
- 검증 대상 작업 출처: branch `phase4-slice-4-2-planner` HEAD(`b9de408`), working tree clean(origin 대비 10 ahead, 미푸시).

## Scope

1. **seam 시그니처 일치** — `ChromaVectorIndexAdapter.upsert_records`/`query_similar`/`list_records`가 `VectorIndexAdapter`/`VectorSearchAdapter` Protocol 및 fake의 시그니처·반환형과 일치하는지.
2. **직렬화 완전성** — `record_to_chroma`/`record_from_chroma`가 `SourceBlockIndexRecord`의 모든 필드(pointer 하위 5개 포함, vector 포함)를 보존·복원하는지.
3. **fake 동등성 (boundary matrix)** — project scope / archived(project·draft) 제외 / id 정렬 / cosine ranking / limit / limit<1 ValueError가 fake(`InMemoryVectorIndexAdapter`)와 동일하게 구현됐는지. **모든 "should fire"/"should NOT fire" 분기가 회귀에 매핑되는지**.
4. **회귀 유효성 (mutation testing)** — 회귀가 vacuous하지 않은지 under-strict/over-strict 가드를 경험적으로 증명.
5. **영속 인프라 + skip-aware** — compose chroma 서비스(base 편입, persistence volume, port-open healthcheck), `chromadb` lazy import, live 테스트 skip-aware 동작.
6. **범위 미침범** — stale guard(`validate_source_block_record`), worker→Chroma archive mutation, 기존 service.py/context_search 로직을 건드리지 않았는지(브리프 §6 + line 87).
7. **버전 정합 + suite 카운트 독립 재현**(497 OK / 45 skip, pytest 452 / 45 skip).

## Methodology

- 계약 스코프: 브리프 B.3 + §4/§5/§6 + line 87 범위 제약 + seam Protocol 3종 + 모델 + 직전 B.2 검증 §Outstanding items만 종단 독해. B.4(wiring)/B.5(live)는 스코프 밖.
- boundary matrix 구축 후 9개 회귀의 각 assertion을 cell에 수동 매핑 → 빈 cell 식별.
- **경험적 mutation testing**(핵심): `chroma.py`를 `/tmp`에 cp 백업 → 특정 분기를 제거/치환 → `python3 -m unittest tests.test_chroma_adapter...` 재실행 → re-fail(가드 존재) / 통과(under-strict 가드 부재 = 빈 cell) 판정 → cp 복원 → `diff -q`로 byte-identical. 3개 mutation 실행:
  1. `_active_where`에서 `{"draft_archived": False}` 제거 → query_similar 회귀 통과? (under-strict 조사)
  2. `_active_where`에서 `{"project_id": project_id}` 제거 → query_similar 회귀 통과? (under-strict 조사)
  3. `record_to_chroma`에서 `"content_hash"` 제거 → round-trip 회귀 re-fail? (대조군 — 직렬화 가드가 살아있음을 증명)
- seam 시그니처/동등성: service.py(fake) + context_search/service.py(Protocol) + chroma.py(adapter) 직독 비교.
- 모델 필드: models.py 직독으로 record_to_chroma metadata 키 집합과 교차 검증.
- 범위 미침범: `git show b9de408 --stat`로 service.py/context_search/worker/outbox 변경 부재 확인, `git show b9de408 -- services/application/app/indexing/service.py`로 stale guard 미수정 확인.
- 테스트 실행: B.3 회귀 단독, `python3 -m unittest discover tests`, `python3 -m pytest -q`, `py_compile`, `git diff --check`.
- compose: `docker compose config --services`로 chroma 인식 + 전체 config 유효; CHROMA_VERSION default 0.5.23 vs requirements `>=0.5,<0.7` 정합.

사용한 정확한 명령은 §Reproduction에 열거.

## Findings

### 1. seam 시그니처 일치 — 부합

- `VectorIndexAdapter`(write, `service.py:48-49`): `upsert_records(records) -> int`. Chroma `upsert_records`(`chroma.py:122`) 동일 시그니처·반환형.
- `VectorSearchAdapter`(read, `context_search/service.py:87-90`): `query_similar(*, project_id, vector, limit) -> tuple[SourceBlockIndexRecord, ...]`. Chroma `query_similar`(`chroma.py:153`) 키워드 인자·타입 완전 일치.
- `list_records`는 Protocol에 없지만 rebuild summary가 fake의 메서드를 쓰므로 Chroma도 동일하게 제공(`chroma.py:138`, 시그니처·`include_archived` 기본값 `False`까지 fake `service.py:245-246`과 동일). 상류 코드를 안 건드리는 seam 교환 전제 충족.

### 2. 직렬화 완전성 — 부합 (mutation 대조군으로 가드 실증)

- `record_to_chroma`(`chroma.py:51-72`) metadata 키 집합 = {kind, project_id, collection, document_id, version_id, content_hash, snapshot_id, draft_id, block_id, block_index, text, project_archived, draft_archived}. `id`는 반환 튜플 첫 요소, `vector`는 embedding으로 별도 전달.
- `SourceBlockIndexRecord`(`models.py:116-127`) 전 필드(id, kind, pointer 5 하위, snapshot_id, draft_id, block_id, block_index, text, vector, project_archived, draft_archived)가 누락 없이 매핑. 빠진 필드 없음.
- Chroma metadata 타입 제약(str/int/float/bool) 충족: `block_index` int, `*_archived` bool, 나머지 str. `kind`는 `record.kind.value`(StrEnum → str).
- **mutation 3(대조군)**: `record_to_chroma`에서 `content_hash` 제거 시 `test_record_chroma_roundtrip_preserves_all_fields`가 `KeyError: 'content_hash'`로 **re-fail**(errors=2). → 직렬화 회귀가 필드 보존을 실제로 lock함(vacuous 아님). round-trip `assertEqual(rebuilt, record)`가 dataclass eq로 전 필드 비교.
- `test_roundtrip_coerces_embedding_to_float_tuple`: embedding `[1, 0]`(int) → `tuple(float(v) ...) = (1.0, 0.0)` 정규화 lock. Chroma가 int/다른 numeric을 돌려줘도 안전.

### 3. fake 동등성 (boundary matrix) — project_archived/cosine/limit cell은 lock, **project_id·draft_archived cell 2개 빈**

`_active_where`(`chroma.py:99-108`) = `{$and: [{project_id}, {project_archived: False}, {draft_archived: False}]}`. fake `query_similar`(`service.py:261-270`)는 `list_records`(project scope + `not project_archived and not draft_archived`) 결과를 cosine + id tie-break 정렬. 두 구현의 *의도*는 동일하나 **where 구성 경로가 다름**(list는 `{project_id}` + 파이썬 필터, query는 `_active_where` 3조건 $and).

**query_similar boundary matrix:**

| cell | 방향 | lock 회귀 | 상태 |
|---|---|---|---|
| cosine ranking(near > far) | should-fire | `test_query_similar_ranks_by_cosine...` | ✓ |
| project_archived 제외 | should-NOT-fire | 동일(archived_near) | ✓ |
| **project_id scope(타 project 제외)** | **should-NOT-fire** | **(매핑 없음)** | **✗ 빈 cell** |
| **draft_archived 제외** | **should-NOT-fire** | **(매핑 없음)** | **✗ 빈 cell** |
| limit 건수 | should-fire | `test_query_similar_respects_limit` | ✓ |
| limit < 1 → ValueError | should-NOT-fire | `test_query_similar_rejects_nonpositive_limit` | ✓ |

- list_records matrix는 4 cell(project scope / archived 제외 / include_archived=True 전체 / id 정렬) 모두 `test_list_records_*` 2건에 매핑, 빈 cell 없음.
- query_similar는 6 cell 중 **2 cell(project_id scope, draft_archived 제외)이 빈 cell**. 회귀 3건이 모두 단일 project(`project-1`)·단일 archived 종류(project_archived=True인 archived_near)만 사용. draft_archived=True인 레코드가 query 테스트에 아예 없고, 타 project 레코드도 없음.
- 참고: fake `_match`(`test_chroma_adapter.py:75-83`)는 list 경로 회귀에서 `$and`/equality 매칭이 검증되나, adapter가 query와 list에서 **다른 where 구성**을 쓰므로 query의 `_active_where` 구성 자체가 별도 lock 대상. list 경로 동등성이 query 경로를 대신하지 못함.

### 4. 회귀 유효성 (mutation testing) — 직렬화 가드는 살아있으나 query 2분기 under-strict

- **mutation 1(draft_archived 제거)**: `_active_where`에서 `{"draft_archived": False}` 제거 → `ChromaAdapterLogicTest` 6건 **모두 통과**. → query_similar의 draft_archived 제외 분기는 회귀가 잡지 못함(under-strict 가드 부재).
- **mutation 2(project_id 제거)**: `_active_where`에서 `{"project_id": project_id}` 제거 → 6건 **모두 통과**. → query_similar의 project scope 분기도 회귀가 잡지 못함.
- **mutation 3(대조군, content_hash 제거)**: round-trip 회귀 `KeyError` re-fail. → 직렬화 cell은 가드 살아있음.
- 결론: 회귀 스위트는 직렬화·project_archived 제외·cosine·limit·limit<1에 대해 유효하나, query_similar의 project_id·draft_archived 분기에 대해서는 vacuous-in-spirit(통과해도 결함 미검출).

### 5. 영속 인프라 + skip-aware — 부합

- compose `chroma` 서비스(`docker-compose.yml:117-141`): `image: chromadb/chroma:${CHROMA_VERSION:-0.5.23}`, `IS_PERSISTENT: TRUE`, `chroma_data:/data` volume(영속), port `${CHROMA_PORT:-8003}:8000`, healthcheck = port-open liveness(python socket, 8000). **base compose 편입**(브리프 오너 결정 §4 "opt-in override가 아니라 base compose에 서비스로 편입"과 일치 — 브리프 본문 §4의 opt-in 추천은 오너 결정으로 override됨).
- healthcheck port-open 선택: comment "tag and heartbeat path validated at live bring-up (B.5); port-open liveness to stay independent of the API version path" — Chroma 버전별 health endpoint path 차이를 회피. 합리적.
- `chromadb` lazy import(`chroma.py:197`): `connect_chroma_collection` 내부에서만 import. `ChromaVectorIndexAdapter` 자체는 duck-typed collection이라 단위 테스트가 chromadb 없이 동작. **실증**: 본 sandbox(chromadb 미설치)에서 B.3 회귀 9건이 8 fake 통과 + 1 live skip(`CHROMA_TEST_URL`·`chromadb` 부재 skipUnless).
- live 테스트 `test_upsert_query_list_and_restart_survival`(`test_chroma_adapter.py:249`): skipUnless(`_CHROMA_URL and _CHROMADB_INSTALLED`) — sandbox에서 정확히 skip. 재시작 생존은 fresh client/collection handle로 시뮬레이션(`fresh = self._adapter()`).
- `CHROMA_VERSION` default 0.5.23 ∈ `chromadb>=0.5,<0.7`(requirements) — client/server 버전 정합.

### 6. 범위 미침범 — 부합 (브리프 §6 + line 87 준수)

- `git show b9de408 --stat`: 변경 파일 = `chroma.py`(신규) + `test_chroma_adapter.py`(신규) + `docker-compose.yml` + `requirements.txt` + `CHANGELOG.md` + `HANDOFF.md` + `docs/daily_logs/2026-07-05/work_log.md`. **service.py / context_search / worker / outbox 미수정**.
- `git show b9de408 -- services/application/app/indexing/service.py` = 빈. → stale guard(`validate_source_block_record`), `InMemoryVectorIndexAdapter`, `_cosine_similarity` 모두 미건드림. 브리프 §6 "stale guard는 backend와 무관하게 그대로(계약 변경 없음)" + line 87 "rebuild write + query read 경로만 real로 올린다(worker→Chroma archive mutation은 후속)" 준수.

### 7. 버전 정합 + suite 카운트 독립 재현 — 부합

- `python3 -m unittest tests.test_chroma_adapter -v` → Ran 9, OK (skipped=1) — 8 fake + 1 live skip.
- `python3 -m unittest discover tests` → **Ran 497, OK (skipped=45)** — 작업자 주장(45 skip) 재현(직전 488 + B.3 9 = 497, skip 44 + live 1 = 45).
- `python3 -m pytest -q` → **452 passed, 45 skipped** — 작업자 주장(452 passed) 재현(직전 444 + 8 = 452).
- `py_compile` + `git diff --check` 통과(working tree clean).

## Issues / Risks

1. **(차단, 조건부 합격 사유) query_similar boundary matrix 빈 cell 2개** — `_active_where`의 `project_id` scope와 `draft_archived` 제외 분기가 query_similar 회귀에 매핑되지 않음. mutation 1/2로 under-strict 가드 부재 실증(둘 다 제거해도 6건 통과). CLAUDE.md "An untraced branch is a blocking finding regardless of the green bar" + "Never reframe a missing over-strict guard as 'future risk'/'후속 보강 후보'" 해당. 실제 결함 경로: 누군가 `_active_where`에서 project_id나 draft_archived 절을 실수로 빼면(리팩토링 등) 회귀가 잡지 못하고 타 project 레코드 또는 draft_archived 레코드가 query 결과에 섞임. **해결(합격 전환 조건)**: query_similar 회귀에 (a) 타 project 레코드가 제외되는 케이스, (b) `draft_archived=True` 레코드가 제외되는 케이스 추가(기존 1건 확장 또는 신규 1건, 수십 줄). fake와의 동등성 lock이 명목상 B.3의 목적(seam 교체)이므로 이 cell은 계약상 의미 있는 분기.

2. **(비차단 관찰, 미사용·깨진 옵션) `include_embeddings=False`** — `ChromaVectorIndexAdapter.__init__`의 `include_embeddings: bool = True` 옵션(`chroma.py:113`)의 `False` 경로가 깨져 있음: `_records_from_get`/`_records_from_query`는 embedding 누락 시 `[None]*len(ids)`를 채우고, `record_from_chroma(... None ...)`이 `tuple(float(v) for v in embedding)`에서 `TypeError`. grep 결과 이 옵션은 chroma.py 본인만 참조, **외부 사용처 없음**(wiring/B.4도 기본값 사용 예정). CLAUDE.md "No flexibility/configurability that wasn't requested" 관점에서 죽은 유연성이며 현재 발현 경로 없음. 권장: B.4 전에 옵션 자체를 제거(단순화)하거나, `False` 경로를 방어. 합격을 뒤집지는 않음(기본값 경로가 정상).

3. **(비차단, sub-slice 계획상 자명) 실서버 관통 미검증** — image tag(0.5.23 실구동), persist path `/data` 실제 Chroma 기본 경로 일치, 서버 HNSW cosine ranking, 재시작 영속, heartbeat path는 sandbox에서 불가 → B.5 live로 연기(작업자 comment·브리프 B.5 명시대로). 코드 레벨에서는 검증 불가.

4. **(비차단 관찰) cosine 동점 시 id tie-break 불일치** — fake는 클라이언트 `_cosine_similarity` + id tie-break(`service.py:268`), Chroma는 서버 HNSW cosine만으로 동점 순서 보장 안 함. 단, 브리프 §B.3은 "cosine ranking"만 요구하고 tie-break를 규정하지 않으며, live test도 near vs far 명확한 차이만 assert. 계약 위반 아님. 다중 동점이 실제 query에서 빈번해지면 B.5 이후 재평가 후보.

5. **(정보) compose base 편입 트레이드오프** — chroma가 base compose에 들어가 미구성(2번째) 환경에서도 `docker compose up` 시 컨테이너가 기동됨. 단 app wiring은 B.4에서 "미구성 시 fake 유지"이므로 컨테이너만 뜨고 app은 fake를 쓰는 상태. 브리프 오너 결정 §4에 명시된 트레이드오프이므로 정상.

## Verdict

**조건부 합격.**

load-bearing 이유(부합):
- seam 시그니처(`upsert_records`/`query_similar`/`list_records`)가 `VectorIndexAdapter`/`VectorSearchAdapter` Protocol 및 fake와 완전 일치 → 상류 코드를 안 건드리는 seam 교환 전제 충족.
- 직렬화가 `SourceBlockIndexRecord` 전 필드를 누락 없이 보존·복원하고, mutation 3 대조군(content_hash 제거 → round-trip re-fail)으로 가드가 살아있음을 실증.
- 영속 인프라(base compose chroma, persistence volume, port-open healthcheck) + lazy import + skip-aware live가 브리프 §4/§5/오너 결정과 일치, sandbox에서 8 fake 통과 + 1 live skip 재현.
- 범위 미침범(stale guard·worker mutation·기존 service.py/context_search 미수정)이 브리프 §6 + line 87을 정확히 준수.
- suite 카운트(497 OK/45 skip, pytest 452/45 skip) 독립 재현, 버전 정합(0.5.23 ∈ [0.5,0.7)).

조건(합격 전환):
- **Issue #1 해결**: query_similar 회귀에 project_id scope(타 project 제외)와 draft_archived 제외 over-strict 가드 추가. mutation 1/2로 증명된 2개 빈 cell 채우기. 회귀 1-2건(수십 줄)으로 충분.

비차단 관찰(Issue #2~#5)은 합격을 뒤집지 않으나, Issue #2(`include_embeddings=False` 깨진 옵션)는 B.4 wiring 전에 단순화(옵션 제거)를 권장.

## Outstanding items

- **(owner 결정 필요) B.4 진행 순서**: 작업자가 "바로 B.4로 이어서 진행할까요?"로 대기 중. 본 검증이 조건부 합격이므로, (a) Issue #1 빈 cell 2개를 **B.4 직전에 먼저** 보강(권장 — 회귀 수십 줄, B.4 wiring이 의존하는 seam 동등성을 확정 잠그므로), 또는 (b) B.4 회귀에 빈 cell 보강을 함께 포함, 또는 (c) list 경로 동등성으로 수용하고 그대로 B.4 진행 중 택일. 권장은 (a).
- **Issue #2 처리**: `include_embeddings=False` 옵션 제거(B.4에서 기본값만 쓰므로 단순화) 또는 `False` 경로 방어 — B.4 착수 전 점검.
- **B.5 live**: image tag/persist path/서버 cosine/재시작 영속 실서버 관통은 LLM 가능 환경에서 B.5 deployed smoke로 연기.
- **origin 미푸시**: branch가 origin 대비 10 ahead. 요청 시 push.

## Reproduction

```bash
# 1. B.3 회귀 단독 (chromadb 없으면 8 fake + 1 live skip)
python3 -m unittest tests.test_chroma_adapter -v   # Ran 9, OK (skipped=1)

# 2. 전체 suite (497 OK / 45 skip, pytest 452 / 45 skip)
python3 -m unittest discover tests                 # Ran 497, OK (skipped=45)
python3 -m pytest -q                               # 452 passed, 45 skipped

# 3. 컴파일 + whitespace
python3 -m py_compile services/application/app/indexing/chroma.py tests/test_chroma_adapter.py
git diff --check                                   # clean

# 4. compose config 유효 + chroma 인식 + 버전 정합
docker compose config --services                   # application chroma embedding gateway mongo
grep CHROMA_VERSION docker-compose.yml             # chromadb/chroma:${CHROMA_VERSION:-0.5.23}
grep chromadb services/application/requirements.txt # chromadb>=0.5,<0.7

# 5. 범위 미침범 확인 (service.py/context_search/worker/outbox 미수정)
git show b9de408 --stat | grep -E "service\.py|context_search|worker|outbox"   # (no output)
git show b9de408 -- services/application/app/indexing/service.py              # (empty)

# 6. mutation testing — query_similar under-strict 가드 부재 증명
cp services/application/app/indexing/chroma.py /tmp/chroma.py.bak
# (a) _active_where 에서 {"draft_archived": False}, 제거 → 6건 통과(under-strict)
# (b) _active_where 에서 {"project_id": project_id}, 제거 → 6건 통과(under-strict)
python3 -m unittest tests.test_chroma_adapter.ChromaAdapterLogicTest -v        # Ran 6, OK
cp /tmp/chroma.py.bak services/application/app/indexing/chroma.py
# (c) 대조군: record_to_chroma 에서 "content_hash" 줄 제거 → round-trip re-fail
python3 -m unittest tests.test_chroma_adapter.ChromaSerializationTest -v       # FAILED (errors=2, KeyError: 'content_hash')
cp /tmp/chroma.py.bak services/application/app/indexing/chroma.py
diff -q /tmp/chroma.py.bak services/application/app/indexing/chroma.py         # identical
rm -f /tmp/chroma.py.bak
```
