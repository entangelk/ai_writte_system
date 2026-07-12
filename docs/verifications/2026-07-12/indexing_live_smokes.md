# Verification — 인덱싱 파이프라인 live 관통 (full-stack, sandbox-external)

## Subject metadata

- 날짜: 2026-07-12
- 요청자: 오너 ("핸드오프·데일리 로그 읽고 다음 작업 진행 … 여기는 테스트도 가능한 머신이니 확인해서 진행")
- 검증자: Claude Code (풀스택 머신 live 실행 + 독립 대조)
- 대상: HANDOFF Next Tasks #2/#3의 "코드 완료, sandbox 밖 막힘" live 관통 항목 —
  2B.5 memory reindex, ⑤ §8 ES lexical/hybrid retrieval, b-2 candidate 색인, Phase 3B archive→Chroma delete.
- 정본 스펙 참조:
  - `docs/plans/02b-5-memory-vector-reindex-decisions.md` (2B.5 outbox→worker 트리거, D3=B)
  - `docs/system-contract-sot.md` v1.6.52(§8 lexical/hybrid), v1.6.54/55(candidate 색인·retriever), v1.6.53(compose ES), v1.6.56/57(worker compose·per-sink), v1.6.37(Phase 3B archive mutation)
- 검증 대상 work source: `git HEAD = 47d63a6` (SoT v1.6.61), working tree — 신규 smoke 스크립트 2개(아래)를 제외하면 프로덕션 코드 무변.

## Scope

이 검증은 **live 인프라 관통**이다: 이미 회귀로 잠긴(749 passed) 코드가 실 Mongo·Chroma·Elasticsearch·embedding(BGE-m3-ko) 위에서 실제로 관통하는지를 확인한다. 계약/코드/테스트 감사는 각 slice의 기존 검증 기록이 담당하며, 여기서는 재수행하지 않는다.

1. **인프라 스택 bring-up**: base `docker-compose.yml`의 mongo(replica set)·chroma·elasticsearch(nori)·embedding.
2. **2B.5 memory reindex**: promote→CANDIDATE 아닌 MEMORY_UPSERTED outbox→worker composite drain→실 Chroma `memory_vectors`(+ES lexical) 적재.
3. **⑤ §8 lexical/hybrid**: 실 ES nori 인덱스에 canonical memory drain→`LexicalCanonicalMemoryRetriever` 한국어 매칭·superseded 배제→`HybridCanonicalMemoryRetriever` RRF.
4. **b-2 candidate 색인**: record_candidate→CANDIDATE_UPSERTED outbox→worker composite drain→실 Chroma `candidate_vectors` + 실 ES `candidate_lexical` 적재.
5. **Phase 3B archive**: 실 Chroma source-block 레코드 seed→DRAFT_ARCHIVED outbox→worker archive mutation adapter drain→실 Chroma delete(draft 단위 narrowing).

## Methodology

풀스택 머신(Docker 28.5.1 + compose v2.40.2, RTX 3060). smoke는 전부 **worker 이미지 컨테이너 안에서** 실행(정확한 의존성 버전 + in-network DNS + 호스트 무오염). 신규 스크립트 2개는 `-v $(pwd)/scripts:/app/scripts` bind mount로 재빌드 없이 주입.

```bash
# 이미지 (worker=현재 코드 v1.6.61, elasticsearch=official 8.13.4 + analysis-nori)
docker compose build worker elasticsearch
# 인프라 기동 (embedding 모델은 embedding_cache 볼륨에 2.1G 캐시됨 → 재다운로드 없음)
docker compose up -d mongo chroma elasticsearch embedding   # 전부 healthy

# 2B.5 memory reindex (기존 스크립트)
docker compose run --rm --no-deps worker \
  python scripts/phase2b5_memory_reindex_live_smoke.py

# ⑤ §8 lexical/hybrid (기존 스크립트, sys.path 미삽입이라 PYTHONPATH 필요)
docker compose run --rm --no-deps -e PYTHONPATH=/app worker \
  python scripts/phase4_lexical_memory_live_smoke.py

# b-2 candidate 색인 (신규 스크립트)
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" worker \
  python scripts/phase2b_candidate_index_live_smoke.py

# Phase 3B archive→Chroma delete (신규 스크립트)
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" worker \
  python scripts/phase3b_archive_chroma_live_smoke.py
```

## Findings

### 1. 인프라 스택 — PASS

`docker compose ps` → mongo·chroma·elasticsearch·embedding 전부 `healthy`. mongo replica set은 기존 볼륨에서 이미 초기화, embedding은 `dragonkue/BGE-m3-ko`가 `ai_writte_system_embedding_cache`(2.1G)에 캐시돼 재다운로드 없이 즉시 ready. elasticsearch는 자체 `services/elasticsearch/Dockerfile`(nori) 빌드 후 cluster health 응답.

### 2. 2B.5 memory reindex — PASS

```json
{"status": "ok", "memory_backend": "chroma+elasticsearch",
 "promoted_memory_id": "6a52d3b0cd33063f67c545c4",
 "indexed_memory_ids": ["6a52d3b0cd33063f67c545c4"], "worker_succeeded": 1}
```
promote한 canonical memory가 MEMORY_UPSERTED outbox→worker→실 embedding→실 Chroma `memory_vectors`에 착지(정확히 1건). backend `chroma+elasticsearch`이므로 worker composite drain이 벡터 sink와 lexical sink 양쪽을 fan-out했음을 실증(v1.6.56/57 per-sink 경로). read-back 후 Chroma record cleanup 완료.

### 3. ⑤ §8 ES lexical/hybrid — PASS

```json
{"ok": true, "lexical_ids": ["storm"], "hybrid_ids": ["storm", "calm"], "nori": true}
```
한국어 질의 "폭풍"이 nori 형태소 분석으로 `storm`("폭풍이 항구를 덮쳤다") 매칭, `calm`·superseded `stale`는 배제(권위 재유도 = store payload 확인). `HybridCanonicalMemoryRetriever` RRF가 fake vector + 실 lexical 융합에서 lexical 매칭을 표면화. ephemeral 인덱스는 finally에서 삭제(잔여 0).

### 4. b-2 candidate 색인 — PASS

```json
{"status": "ok", "candidate_backend": "chroma+elasticsearch",
 "candidate_id": "6a52d477f5a9efa33d869fc4",
 "vector_candidate_ids": ["6a52d477f5a9efa33d869fc4"],
 "lexical_candidate_ids": ["6a52d477f5a9efa33d869fc4"], "worker_succeeded": 1}
```
record_candidate→CANDIDATE_UPSERTED outbox→worker composite drain→실 Chroma `candidate_vectors` + 실 ES `candidate_lexical` 양쪽 착지. nori lexical `search`(status=needs_review 필터)가 candidate 매칭. read-back 후 양쪽 record cleanup.

- **관찰(비결함)**: 최초 실행에서 `lexical_candidate_ids: []` mismatch. 원인은 파이프라인 결함이 아니라 **ES refresh 지연** — `index_candidate_records`는 프로덕션 정상 동작대로 `refresh` 없이 색인(검색은 생성 시점에 일어나지 색인 직후 μs가 아님)하므로, 색인 직후 즉시 read-back하는 smoke가 refresh_interval(기본 1s) 전에 조회. smoke에 명시적 `indices.refresh`를 추가하니 PASS(phase4 lexical smoke가 이미 쓰는 동일 패턴). 프로덕션 코드·계약 무변.
  - **재현성(오너 독립 감사 보강)**: 이 mismatch는 단일 사건이 아니라 **timing-dependent flaky**다. 오너 독립 감사가 `indices.refresh`를 제거한 변형을 4회 실행 → **3회 `[]` mismatch, 1회 우연 PASS**(refresh_interval 경계의 timing 의존)로 재현. 즉 refresh 없으면 flaky, 있으면 안정 PASS. 진단 결론(refresh 필요)은 불변이나 재현이 운 의존적임을 명시.

### 5. Phase 3B archive→Chroma delete — PASS (2단계: DRAFT + PROJECT archived)

```json
{"status": "ok", "archive_backend": "chroma",
 "remaining_after_draft_archived": ["draft-control"],
 "remaining_after_project_archived": [],
 "draft_archived_worker_succeeded": 1, "project_archived_worker_succeeded": 1}
```
같은 project에 2개 draft의 source-block record를 실 Chroma에 seed한 뒤 두 분기를 모두 관통:
- **Phase 1 (DRAFT_ARCHIVED)**: `draft-archived`에 outbox→worker `ChromaArchiveIndexMutationAdapter` drain→해당 draft record만 삭제, `draft-control`은 생존(`remaining_after_draft_archived == ["draft-control"]`). `_archive_where`의 `{project_id AND draft_id}` narrowing이 실 Chroma에서 정확히 동작(project_id-only delete였다면 control도 삭제됐을 것)함을 실증.
- **Phase 2 (PROJECT_ARCHIVED)**: 같은 project에 outbox→worker drain→남은 record 전부 삭제(`remaining_after_project_archived == []`). 프로젝트 전체 wipe 분기 실증.

2026-07-05 mutation/코드 감사(`worker_real_chroma_archive_mutation.md`)의 live 후속 공백을 채우고, **오너 독립 감사가 비차단으로 지적한 PROJECT_ARCHIVED live 미검증 gap을 Phase 2 추가로 닫음**(종전엔 DRAFT_ARCHIVED만 live, PROJECT_ARCHIVED는 회귀 의존이었음).

- **관찰(비결함)**: 최초 실행에서 `InvalidDimensionException: Embedding dimension 3 does not match collection dimensionality 1024`. 배포 `project_memory_vectors` 컬렉션이 실 BGE-m3-ko(1024-dim)로 이미 고정돼 있어 3-dim seed 거부. archive 삭제는 metadata where-clause 기반이라 벡터값 무관 → seed 벡터를 1024-dim으로 맞추니 PASS. 프로덕션 무관(smoke seed 데이터만). 오너 독립 감사가 3-dim 교체로 이 예외를 재현(진단 정확).

## Issues / Risks

- 결함 없음. 관찰 2건(§4 ES refresh, §5 Chroma dim)은 모두 **smoke 스크립트의 read-back 조건**이었고 프로덕션 코드/계약과 무관하며 스크립트 수정으로 해소.
- live 데이터는 전용 project id(`smoke-2b5-*`/`smoke-b2-*`/`smoke-3b-*`, ephemeral ES 인덱스) 아래에만 기록되고 각 smoke가 자체 index cleanup. Mongo memory/candidate 문서는 무해하게 잔존(project scope 격리 → 타 프로젝트 retrieval 미노출). **ops 관심사(오너 독립 감사 지적)**: 영속 Mongo에 `smoke-*` 문서가 누적되므로 주기적 cleanup 스크립트 유무는 운영 판단 사항(현재 결함 아님).

## Verdict

**PASS** — HANDOFF Next Tasks #2/#3가 "코드 완료, sandbox 밖 막힘"으로 남겨둔 4개 인덱싱 live 관통이 풀스택 실 인프라 위에서 전부 관통 확인됨. worker composite(vector+lexical) drain이 MEMORY·CANDIDATE 양 이벤트에서, archive delete가 실 Chroma에서 실증됨.

## Outstanding items

- **미커밋**: 신규 smoke 스크립트 2개(`scripts/phase2b_candidate_index_live_smoke.py`, `scripts/phase3b_archive_chroma_live_smoke.py`) untracked. 프로덕션 코드·계약·SoT 무변이라 SoT bump 없음. 커밋은 오너 지시 대기(작업자 임의 커밋 안 함).
- **여전히 sandbox 밖 남은 것**: 2B.6 semantic threshold 실 캘리브레이션(실 embedding 유사/비유사 cosine 분포 관찰 필요 — 이번 검증 범위 아님), compare judge / context_search planner live smoke(실 llama 12B gateway 필요 — 이번엔 gateway 미기동), (b-4) hybrid 튜닝(실 데이터).

## Reproduction

위 Methodology의 명령을 순서대로 실행. 각 smoke의 exit 0 + JSON `"status":"ok"`/`"ok":true`가 통과 신호. 인프라는 `docker compose up -d mongo chroma elasticsearch embedding`로 기동(embedding 모델 최초 1회 다운로드 후 캐시).
