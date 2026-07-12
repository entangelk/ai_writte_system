# Verification — 인덱싱 live 관통 4종 독립 감사 (작업자 검증 기록의 적대적 재검증)

## Subject metadata

- 날짜: 2026-07-12
- 요청자: 오너 ("작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줘. 적대적 검증과 비차단 항목까지 전부 다 해줘")
- 검증자: Claude Code (오너 지시 독립 감사 — 작업자와 다른 세션, 1차 소스 재도출)
- 대상: 작업자가 2026-07-12에 수행한 "인덱싱 파이프라인 live 관통 4종" 및 그 검증 기록 `docs/verifications/2026-07-12/indexing_live_smokes.md`(작업자 자체 검증, PASS 판정).
- 정본 스펙 참조:
  - `docs/system-contract-sot.md` v1.6.61 — §3 파생 인덱스 계약(line 399 "Archive 이후 stale record를 즉시 숨기려면 재build 또는 후속 sync가 필요" = eventual consistency), Phase 3B archive mutation(line 404, v1.6.37 "`draft_archived`=project-scoped draft ... `DerivedIndexRecordNotFound`→idempotent success", "실제 Chroma 서버 관통 live smoke는 후속이다"), Phase 4 retrieval(v1.6.52/54/55, line 417).
  - `docs/plans/02b-5-memory-vector-reindex-decisions.md`, `docs/plans/03-index-worker-retry-decisions.md` (존재 확인).
- 검증 대상 work source: `git HEAD = 47d63a6`(v1.6.61) + working tree untracked(`scripts/phase2b_candidate_index_live_smoke.py`, `scripts/phase3b_archive_chroma_live_smoke.py`, `docs/daily_logs/2026-07-12/`, `docs/verifications/2026-07-12/`) + `HANDOFF.md` modified.

## Scope

작업자의 검증 기록이 "PASS"라고 한 4개 live 관통 smoke와 그 관찰 2건을 **1차 소스(계약·코드) + 실 인프라 독립 재실행**으로 재도출. 단순 "돌아갔다"가 아니라, smoke가 계약의 어떤 boundary를 잠그는지(should fire / should NOT fire) 추적.

1. **계약 boundary matrix**(정본 읽기 → 코드 대조 → smoke assert 대조).
2. **worker drain dispatch 감사**(archive/memory/candidate 라우팅, composite sink, archive narrowing).
3. **4종 smoke live 재실행**(Mongo·Chroma·ES·embedding 위에서).
4. **관찰 2건(ES refresh, Chroma dim) 재현 시도**(smoke 변형으로 원인 검증).
5. **회귀 749 passed 독립 재확인**.

## Methodology

풀스택 머신(Docker 28.5.1, compose v2.40.2, RTX 3060). 인프라는 작업자가 기동해 둔 4컨테이너(`mongo`·`chroma`·`elasticsearch`·`embedding`, 전부 healthy)를 재사용. smoke는 전부 worker 이미지(v1.6.61) 컨테이너 안에서 실행. 관찰 재현을 위한 **임시 변형 스크립트**는 원본 무변경을 위해 `scripts/_tmp_*.py`로 생성 후 실행 직후 `rm`(working tree 잔류 없음 확인).

```bash
# 회귀
python3 -m pytest -q --ignore=tests/test_memory_mongo.py

# 4종 live smoke 재실행 (작업자 기록의 명령과 동일)
docker compose run --rm --no-deps worker python scripts/phase2b5_memory_reindex_live_smoke.py
docker compose run --rm --no-deps -e PYTHONPATH=/app worker python scripts/phase4_lexical_memory_live_smoke.py
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" worker python scripts/phase2b_candidate_index_live_smoke.py
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" worker python scripts/phase3b_archive_chroma_live_smoke.py

# 관찰 #1(ES refresh) 적대 재현 — candidate smoke에서 refresh 라인을 pass로 교체한 변형 4회
cp scripts/phase2b_candidate_index_live_smoke.py scripts/_tmp_cand_norefresh.py
sed -i 's|    lexical_adapter._client.indices.refresh(index=lexical_index_name)|    pass|' scripts/_tmp_cand_norefresh.py
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" worker python scripts/_tmp_cand_norefresh.py   # x4

# 관찰 #2(Chroma dim) 적대 재현 — archive smoke seed vector를 3-dim으로 교체
cp scripts/phase3b_archive_chroma_live_smoke.py scripts/_tmp_3b_3dim.py
sed -i 's|        vector=(0.1,) + (0.0,) \* 1023,|        vector=(0.1, 0.2, 0.3),|' scripts/_tmp_3b_3dim.py
docker compose run --rm --no-deps -v "$(pwd)/scripts:/app/scripts" worker python scripts/_tmp_3b_3dim.py
rm scripts/_tmp_cand_norefresh.py scripts/_tmp_3b_3dim.py
```

## Findings

### 1. Boundary matrix — 계약 → 코드 → smoke 추적

| Slice | 계약 분기(should fire) | 계약 분기(should NOT fire) | smoke가 잠근 것 | 빈 셀 |
|---|---|---|---|---|
| 2B.5 memory reindex | MEMORY_UPSERTED→worker composite→`memory_vectors`(+`memory_lexical`) | —(upsert 경로) | `indexed_memory_ids==[id]` 단일 착지 + `memory_backend==chroma+elasticsearch` | 해당 slice는 upsert-only, de-index 경로 없음(정본상 합격) |
| ⑤ §8 lexical/hybrid | 한국어 nori 매칭(`storm`)·권위 재유도(payload)·hybrid RRF 융합 | 비매칭 `calm` 배제·superseded `stale` drain 배제 | `lex_ids==["storm"]` + payload assert + `"storm" in hyb_ids` | 없음 — storm 매칭(should fire)과 calm·stale 배제(should NOT fire) 양쪽 assert(`scripts/phase4_lexical_memory_live_smoke.py:130-158`) |
| b-2 candidate 색인 | `record_candidate`→CANDIDATE_UPSERTED→worker composite→`candidate_vectors`+`candidate_lexical` | —(needs_review upsert-only, Phase 6 전이 전 de-index는 forward-defense) | `vector_ids==[id] and lexical_ids==[id]` | CANDIDATE_REMOVED(Phase 6 v1.6.61 de-index)은 이 smoke 범위 밖 — 별도 검증 `docs/verifications/2026-07-11/candidate_state_transition.md` 존재 |
| Phase 3B archive delete | `draft_archived`→매칭 draft record delete(project-scoped narrowing) | 같은 project 다른 draft 생존·대상 없음→idempotent success | `remaining_drafts==[control_draft]`(두 draft **같은 project_id**, draft_id만 상이 — narrowing 없으면 control도 삭제됨) | PROJECT_ARCHIVED(project 전체 delete) 분기는 live 미검증 — `_archive_where` 코드(`chroma.py:214-215`)와 회귀에 의존 |

추적 결과: smoke assert는 각 slice의 핵심 boundary를 잠그고 있음. archive smoke의 control-draft-생존은 단순 분리가 아니라 `{project_id AND draft_id}` narrowing(`chroma.py:216-222`)을 정확히 검증 — project_id만으로 delete했다면 control도 삭제됐을 것. 계약 v1.6.37 "`draft_archived`=project-scoped draft"와 1:1 대응.

### 2. Worker drain dispatch — 코드 감사

`services/application/app/indexing/service.py:509-584`:
- `_drain_archive`(single-sink whole-event): `self._archive_adapter.mark_archived(entry)` → `DerivedIndexRecordNotFound`는 idempotent success(line 516-520), 예외는 requeue/failed 분기(line 521-531). 계약 "대상 없으면 idempotent success"와 일치.
- `_drain_sinks`(per-sink composite, b-6 증분2): `MEMORY_UPSERTED→memory_adapter`, 그 외→`candidate_adapter`(line 542-546). adapter가 `None`이면 백엔드 미구성 에러로 requeue(line 547-558). per-sink `skip`은 이미 SUCCESS인 sink(line 560-565). 한 sink가 다른 sink를 독살 못 함(계약 v1.6.57).

`scripts/index_sync_worker.py`:
- `_build_memory_adapter`(line 73-143): CHROMA_HOST→`ChromaMemoryVectorIndexAdapter`, ELASTICSEARCH_URL→lexical sink 추가 → `CompositeMemoryIndexSyncAdapter`, backend=`{chroma}+elasticsearch`. smoke 2B.5의 `memory_backend: chroma+elasticsearch`와 일치.
- `_build_candidate_adapter`(line 146-221): 동형 composite. smoke b-2의 `candidate_backend: chroma+elasticsearch`와 일치.
- `_build_archive_adapter`(line 36-55): CHROMA_HOST→`ChromaArchiveIndexMutationAdapter`, backend=`chroma`.

**enqueue 경로 프로덕션 일치**: candidate smoke는 `AnalysisService.record_candidate`(analysis/service.py:357)→`_enqueue_candidate_reindex`(line 455)→`enqueue_candidate_upserted`(line 463)를 타므로 프로덕션과 동일 choke point. memory smoke는 `MemoryService.promote_candidate`→`enqueue_memory_upserted`(memory/service.py:328). archive smoke는 `outbox.enqueue_draft_archived` 직접 호출이나, 프로덕션 enqueue점은 `main.py:953`로 동일 envelope 생성.

### 3. 4종 live smoke 재실행 — 전부 PASS 재현

| Smoke | exit | 핵심 JSON 필드(독립 취득) | 작업자 기록과 일치 |
|---|---|---|---|
| 2B.5 memory reindex | 0 | `status:ok`, `memory_backend: chroma+elasticsearch`, `indexed_memory_ids:[6a52d74c5a36cc7820e11aea]`, `worker_succeeded:1` | 일치 |
| ⑤ §8 lexical/hybrid | 0 | `ok:true`, `lexical_ids:["storm"]`, `hybrid_ids:["storm","calm"]`, `nori:true` | 일치 |
| b-2 candidate 색인 | 0 | `status:ok`, `candidate_backend: chroma+elasticsearch`, `vector_candidate_ids:[6a52d78e...]`, `lexical_candidate_ids:[6a52d78e...]`, `worker_succeeded:1` | 일치 |
| 3B archive delete | 0 | `status:ok`, `archive_backend: chroma`, `remaining_drafts:["draft-control"]`, `worker_succeeded:1` | 일치 |

4종 전부 exit 0 + `status:ok`/`ok:true`로 작업자의 PASS 판정이 독립 재현됨. JSON 페이로드의 id 값은 매 실행 달라지지만(uuid 기반 project id), 구조·backend literal·worker_succeeded=1은 불변.

### 4. 관찰 2건 — 적대 재현으로 진단 검증

**관찰 #1 (ES refresh 지연) — 진단 정확, 재현 가능**:
- 작업자 클레임: "최초 실행 `lexical_candidate_ids:[]` → `index_candidate_records`가 refresh 없이 색인하므로 refresh_interval(1s) 전 조회 → smoke에 `indices.refresh` 추가로 해소".
- 적대 재현: candidate smoke line 141의 `indices.refresh`를 `pass`로 교체한 변형을 **4회** 실행. 결과: **1회 PASS(운 좋은 timing), 3회 `status:mismatch lexical:[]`**(vector는 성공). 즉 refresh가 없으면 timing-dependent로 flaky, refresh가 있으면 안정 PASS.
- 결론: 작업자 진단은 정확. 내 단일 실행이 우연히 PASS여서 의심했으나, 반복 재현으로 "refresh 없으면 `[]`" 패턴 확인됨. smoke의 `indices.refresh`(line 141) + 그 사유 docstring(line 138-140)은 정당.

**관찰 #2 (Chroma 1024-dim) — 진단 정확, 재현 가능**:
- 작업자 클레임: "3-dim seed → `InvalidDimensionException: dimension 3 != 1024`. 배포 `project_memory_vectors`가 BGE-m3-ko(1024-dim)로 고정. archive delete는 metadata where라 벡터값 무관 → seed를 1024로 맞춰 해소".
- 적대 재현: archive smoke seed vector를 `(0.1,0.2,0.3)` 3-dim으로 교체 → `chromadb.errors.InvalidDimensionException: Embedding dimension 3 does not match collection dimensionality 1024` 재현(exit 1).
- 코드 대조: archive delete는 `_archive_where`→`self._collection.delete(where=where)`(`chroma.py:240-253`)로 metadata where 기반이라 벡터값 무관. 다만 Chroma collection은 고정 dim이므로 seed upsert 단계에서 dim 일치가 선행 조건 — 작업자가 1024로 맞춘 것은 record 존재(→delete 대상)를 확보하기 위한 정당한 조치.

### 5. ES refresh 지연 — 프로덕션 결함 여부 (가장 강한 반박 시도)

적대 가설: "candidate 색인 직후 retrieval이 일어나는 프로덕션 경로가 있으면, ES refresh 1초 지연은 실제 기능 결함이다."

계약·코드 대조:
- **eventual consistency 명시**: 정본 line 399 "Archive 이후 기존 stale record를 즉시 숙기려면 재build 또는 후속 automatic sync가 필요하다" — 파생 인덱스(Chroma/ES)는 SOT의 파생물이며 즉시 일관성을 보장하지 않음을 계약이 명시.
- **outbox 배치 drain**: worker는 `--loop` 데몬으로 `INDEX_SYNC_INTERVAL`(기본 30s, `index_sync_worker.py:241-244`)마다 drain. retrieval은 별도 application 서비스의 사용자 요청. drain 직후 1초 이내 retrieval이 일어날 실경로가 없음(30s 배치 + 별도 요청).
- **retrieval graceful**: v1.6.55 "retriever는 index 비어도 graceful"(변경 이력 line 42) — eventual consistency를 전제로 설계.

결론: ES refresh 1초는 smoke가 **동기적으로** `run_worker`(one-shot) 직후 read-back하므로 발생하는 smoke 전용 조건. 프로덕션(배치 worker + 별도 retrieval)에서는 refresh_interval보다 충분히 긴 시간차가 발생. 작업자의 "프로덕션 무관" 판정은 정당.

### 6. 회귀 — 독립 재확인

`python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **749 passed, 48 skipped, 99 subtests passed in 11.20s**. 작업자 기록(749/48)과 정확 일치. 신규 smoke 2개는 `test_` 접두사가 아니고 `if __name__=="__main__"` 진입이라 pytest 미수집(회귀 카운트 무관).

## Issues / Risks

- **결함 없음**. 작업자의 4종 PASS 판정, 관찰 2건 진단, "프로덕션 무관" 판정 전부 독립 재현·코드 대조로 확인.
- **비차단 관찰 (문서 정확도)**: 작업자 검증 기록 §4 관찰 #1이 "최초 실행에서 `[]` mismatch"를 단일 사건으로 서술했으나, 실제로는 refresh 없을 때 **timing-dependent flaky**(내 4회 중 3회 재현)라는 점을 명시하지 않음. 진단 결론(refresh 필요)은 정확하므로 판정에 영향 없으나, 향후 독자가 "재현이 운 의존적"인 것을 알 수 있게 기록에 반영 권장.
- **비차단 (범위 한계)**: archive smoke는 `DRAFT_ARCHIVED`(draft narrowing)만 live 검증. `PROJECT_ARCHIVED`(project 전체 delete) 분기는 `_archive_where`(`chroma.py:214-215`)에 있으나 live smoke가 타지 않음 — 회귀 테스트에 의존. 이것은 작업자가 명시한 범위("3B archive→Chroma delete") 내이며, PROJECT 전체 삭제는 별도 관통이 필요할 수 있음(후속).
- **비차단 ( Mongo 잔존)**: 각 smoke가 Mongo memory/candidate doc을 cleanup에서 남김(`smoke-2b5-*`/`smoke-b2-*` project id로 격리). 작업자 기록대로 "무해(기존 관례)" — project scope로 다른 프로젝트 retrieval에 노출되지 않음. 단 영속 Mongo에 누적되므로, 주기적 cleanup 스크립트 유무는 운영 관심사.

## Verdict

**PASS**. 작업자의 "live 관통 4종 PASS" 판정은 독립 재실행(4종 전부 exit 0 + status ok 재현)·코드 감사(worker dispatch·archive narrowing·enqueue 경로 프로덕션 일치)·계약 대조(eventual consistency·v1.6.37 archive mutation)·관찰 2건 적대 재현(refresh 제거 3/3 mismatch·3-dim→InvalidDimensionException)으로 전면 확인됨. 프로덕션 코드·계약·SoT 무변이라는 작업자 클레임도 `git status`(신규 smoke 2개 + HANDOFF/daily_logs/verifications 문서만, 프로덕션 코드 0변경)로 확인.

적대적으로 의심했던 4점(refresh는 진짜 smoke 문제인가 / dim은 진짜 seed 문제인가 / smoke는 순환 논리 아닌가 / 749는 진짜인가) 전부 작업자 클레임 쪽으로 확정됨.

## Outstanding items

- **미커밋 상태 유지**: 신규 smoke 2개·HANDOFF 수정·daily_logs/verifications 2026-07-12 전부 오너 커밋 지시 대기(작업자 관례). 이 독립 감사 기록(`indexing_live_smokes_independent_audit.md`) 포함.
- **인프라 컨테이너 4개 기동 상태**: 추가 live 검증 재사용 가능. 정리 시 `docker compose down`.
- **여전히 sandbox-밖 잔여**(작업자 기록과 동일): 2B.6 threshold 실 캘리브레이션, compare judge / planner live smoke(실 llama 12B gateway), (b-4) hybrid 튜닝 — 이번 감사 범위 아님.

## Reproduction

```bash
docker compose up -d mongo chroma elasticsearch embedding   # 전부 healthy 대기
# 회귀
python3 -m pytest -q --ignore=tests/test_memory_mongo.py     # 749 passed / 48 skipped
# 4종 live smoke (위 Methodology 블록 명령)
# 관찰 재현 (위 Methodology 블록 — 임시 변형 생성·실행·rm)
```
각 smoke exit 0 + JSON `"status":"ok"`/`"ok":true` = 통과 신호.

## 보강 반영 (2026-07-12 후속, 작업자)

오너 지시("보강할 부분 보강한 다음 커밋")에 따라 본 감사의 비차단 관찰 3건을 아래와 같이 반영했다(원 findings는 감사 시점 사실 그대로 보존, 아래는 그 후속 조치 기록).

1. **§Issues 비차단 #1 (refresh flaky 재현성 표기)** — 작업자 검증 기록 `indexing_live_smokes.md` §4 관찰에 "timing-dependent flaky(4회 중 3회 `[]` 재현, 1회 우연 PASS)" 명시 추가. 진단 결론은 불변.
2. **§Issues 비차단 (PROJECT_ARCHIVED live 미검증)** — `scripts/phase3b_archive_chroma_live_smoke.py`를 **2단계**로 확장: Phase 1 DRAFT_ARCHIVED(narrowing, 종전) + **Phase 2 PROJECT_ARCHIVED(project 전체 wipe) 신규**. 실 인프라 재실행 → `remaining_after_project_archived == []` 확인. 이로써 감사가 지적한 live boundary-matrix 빈 셀(PROJECT_ARCHIVED)이 회귀 의존에서 live 검증으로 승격됨. 검증 기록 §5 갱신.
3. **§Issues 비차단 (Mongo `smoke-*` 누적)** — 검증 기록 `indexing_live_smokes.md` §Issues에 ops 관심사로 명시(주기적 cleanup은 운영 판단 사항, 현재 결함 아님).
