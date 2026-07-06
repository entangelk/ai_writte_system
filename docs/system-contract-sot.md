# 시스템 정본 계약 SoT

상태: `Approved`  
계약 버전: `v1.6.40`
승인일: `2026-06-26`  
최근 갱신일: `2026-07-05`
목적: 흩어진 계획 문서의 확정된 계약과 서비스 경계를 한 곳에서 추적한다.  
적용 범위: 제품 경계, 서비스 책임, 데이터 정본, Gateway, AgentLoopRunner, Gate 합성, 검증 기록.

이 문서는 세부 Phase 계획을 대체하지 않는다. 대신 구현자가 먼저 확인해야 할 **정본 계약 인덱스**다. 아래 계약과 세부 계획이 충돌하면 이 문서의 [문서 우선순위](#문서-우선순위)에 따라 조정한다.

## 문서 우선순위

1. 사용자가 명시 승인했고 이 문서 또는 해당 Phase 계획에 반영된 결정
2. `Approved` 상태의 본 SoT와 Phase 계획
3. `Draft` 상태이지만 구현·검증·커밋으로 잠긴 계약 문서
4. `docs/plans/`의 미구현 Phase 계획
5. `docs/` 루트의 아이디에이션 문서

동일 우선순위 문서끼리 충돌하면 구현하지 않는다. 충돌을 작업 로그와 해당 문서에 기록하고 사용자에게 어느 쪽이 canonical인지 확인한다.

이 문서의 `Approved` 상태는 정본 계약 인덱스와 문서 우선순위의 승인을 뜻한다. 아래 "미확정" 항목은 이 승인으로 확정되지 않으며, 사용자 결정 또는 별도 승인된 Phase 계획 없이는 추측해 구현하지 않는다.

## 계약 버전 관리

- 이 문서의 계약 버전은 사용자 결정으로 정본 계약, 문서 우선순위, 서비스 경계, public literal, 미확정 항목의 상태가 바뀔 때 올린다.
- 호환 가능한 명확화, 링크 보정, 검증 근거 추가는 patch 수준으로 기록한다.
- 구현 계약이나 public literal 의미가 바뀌면 minor 이상으로 기록하고, 영향받는 계획 문서·테스트·검증 기록을 함께 갱신한다.
- 기존 승인 결정과 충돌하는 새 요청이 들어오면 구현 전에 충돌을 명시하고 어느 쪽이 canonical인지 사용자에게 확인한다.
- 상세 작업 이력은 `docs/daily_logs/`에 남기고, 이 문서에는 현재 정본에 영향을 주는 변경만 기록한다.

## 계약 변경 이력

| 버전 | 날짜 | 변경 | 근거 |
|---|---|---|---|
| v1.6.44 | 2026-07-06 | Phase 2B.4(proposal→실제 memory versioned upsert) 첫 code slice를 구현했다(브리프 `plans/02b-4-memory-versioned-upsert-decisions.md` Resolved). **D1=A** compare와 분리된 명시 apply: `services/application/app/analysis/apply.py`의 `MemoryApplyService.apply_proposals`가 `ActionProposal`을 결정적 memory 쓰기로 반영한다(LLM 없음, 라벨은 이미 확정). `create`→새 canonical(2B.1 승격 재사용, version=1), `update`→새 version(payload=candidate 교체), `add_evidence`→새 version(payload 보존), `no_change`→쓰기 없음, `conflict`→review-only skipped(D7, merge/split은 2B.3 미산출). **D2=A** append-only: `MemoryStatus.SUPERSEDED` 도입 + `MemoryEntry.supersedes` 필드, versioned upsert는 새 canonical(version=prev+1, supersedes=prev.id)을 먼저 삽입하고 이전 entry를 `superseded`로 전이(이전 version 불변 보존). canonical-only prior 필터가 superseded 자연 제외 → **2B.2 O1 폐쇄**(`test_superseded_memories_excluded_from_prior_memory`, 필터 mutation 재실증). **D3** `update`=payload 교체·source_ref_ids union·confidence=candidate·provenance=candidate / `add_evidence`=payload 보존·source union·confidence=max(prev,candidate)·provenance=prev. **D4=A** memory→vector 재색인은 분리(2B.5) — memory 색인 자체가 미존재라 독립 설계 필요. **D5=A** idempotency `(project_id, source_candidate_id)`(한 candidate=한 반영, 재적용 replay). 타입 불일치·non-canonical target·candidate 부재는 거절. **D6=A HTTP** `POST /projects/{id}/analysis/jobs/{job_id}/apply`(검토한 proposal을 body로 받아 반영, action별 결과 요약; unknown action/candidate 400, missing matched memory·cross-project 404). 회귀 23개(`tests/test_memory_apply.py` 13 + `tests/test_analysis_apply_api.py` 9 + context O1 1; 독립 검증 조건부 합격 후 **non-canonical target 거절 회귀**(boundary matrix 빈 셀)·update conf over-strict(prior>candidate)·add_evidence replay·MissingMatchedMemory HTTP 보강, mutation 재실증) + live Mongo versioned upsert round-trip 1(throwaway mongo 통과). Mongo `update_memory`(replace_one)·`supersedes` round-trip 추가. pytest 565 passed/45 skip(mongo env 제외). | 사용자 결정(D1~D7), `plans/02b-4-memory-versioned-upsert-decisions.md`, `tests/test_memory_apply.py`, `tests/test_analysis_apply_api.py`, `tests/test_memory_mongo.py` |
| v1.6.43 | 2026-07-06 | Phase 2B.3.2(실제 Gateway 터미널-JSON compare judge)를 구현했다 — 2B.3의 `CompareJudge` seam을 실 adapter로 채웠다(4.1→4.2→2B.3→2B.3.2 리듬). `services/application/app/analysis/compare_judge.py`의 `TerminalJsonCompareJudge`(async)가 versioned prompt `analysis_compare_v1`(task_type `analysis_compare`, 기존 `prompt_templates` 저장소 재사용)로 매칭 (candidate payload + 기존 memory payload)을 Gateway `/v1/generate` 1-turn에 보내고 `{"action","rationale"}` JSON을 strict parse한다. malformed/fenced/out-of-set이면 1회 repair, 그래도 실패면 `InvalidJudgeResult`(→HTTP 502). 허용 action은 matched-pair 4종(update/add_evidence/no_change/conflict)뿐이고 **`create`는 judge 출력에서 거절**(no-match 결정적 전용) — `AnalysisCompareService`의 `JUDGE_ACTIONS` guard는 fake seam 방어로 유지. `create_app`은 `_default_compare_service(memory)`로 env `LLM_GATEWAY_BASE_URL` 있으면 이 judge를 wiring하고(`ANALYSIS_COMPARE_MAX_TOKENS` 기본 512), 없으면 종전대로 judge 미주입(매칭 pair 503). 판정 경계(update↔add_evidence↔no_change↔conflict)는 프롬프트 action 정의로 안내하고 fixture는 adapter parse/repair를 잠근다. live smoke `scripts/phase2b3_compare_judge_live_smoke.py`(sandbox 밖 실행). 회귀 13개(`tests/test_analysis_compare_judge.py` 11 + env 기본 factory wiring 2). pytest 541 passed/45 skip(mongo 제외). | 사용자 결정(D1=A), `plans/02b-3-analysis-compare-action-decisions.md`, `tests/test_analysis_compare_judge.py` |
| v1.6.42 | 2026-07-06 | Phase 2B.3(candidate↔canonical 대조 + action proposal) 첫 code slice를 구현했다(브리프 `plans/02b-3-analysis-compare-action-decisions.md` Resolved). **D2=A 결정적 scope key**: `services/application/app/memory/scope.py`의 `MemoryScope(scope_type, scope_id)` + `derive_scope(memory_type, payload)` — character만 `scope_type="character", scope_id=정규화(name)`(공백 collapse + casefold), event/open_question은 엔티티 id 부재로 `None`(identity 대조 제외, semantic은 후속 seam). `MemoryEntry`에 `scope` 필드 추가, 2B.1 승격이 candidate→memory 시 산출(D5=A, Mongo round-trip·`_memory_payload` 포함). `PriorMemoryItem`에 `scope` 추가로 **§8 ⑧ 완전 완성**(memory type/scope/status/version/검색 이유). **compare(D1=A 터미널 JSON seam·D3=A 하이브리드)**: `services/application/app/analysis/compare.py`의 `CompareAction`(create/update/add_evidence/no_change/conflict), `ActionProposal`, `CompareJudge` 주입 seam, `AnalysisCompareService`. 결정적 scope 매칭으로 후보를 좁혀 (a) 매칭 없음→`create`(결정적, event/question 포함), (b) 정확히 1개→주입 judge가 update/add_evidence/no_change/conflict 라벨(judge가 `create` 반환은 `InvalidJudgeResult`), (c) 복수 canonical 동일 identity(2B.1 허용 중복)→결정적 `conflict`. **D6 self-exclusion 확정**: `analysis_job_id == 대상 job`인 memory 제외(같은 job 승격분은 항상 no_change 노이즈라 유지). **D4=A proposal only**(memory 쓰기 없음, 2B.4). **D7=A HTTP** `POST /projects/{id}/analysis/jobs/{job_id}/compare`(job candidate별 proposal 반환, 매칭인데 judge 미구성 시 503, `InvalidJudgeResult` 502, missing project/job 404). 실제 Gateway 터미널-JSON judge adapter + versioned prompt + live smoke는 다음 증분(2B.3.2). 회귀 21개(`tests/test_memory_scope.py` 5 + `tests/test_analysis_compare.py` 9 + `tests/test_analysis_compare_api.py` 7, self-exclusion·judge-create 거절(service+HTTP 502)·중복 conflict·다른 identity→create 양방향). pytest 528 passed/45 skip(mongo 제외). | 사용자 결정(D1~D7), `plans/02b-3-analysis-compare-action-decisions.md`, `tests/test_memory_scope.py`, `tests/test_analysis_compare.py`, `tests/test_analysis_compare_api.py` |
| v1.6.41 | 2026-07-06 | Phase 2B.2(prior-memory 검색 + Analysis 비교용 ContextPackage, §8 ⑧) 첫 code slice를 구현했다(`services/application/app/context_search/prior_memory.py`, 브리프 `plans/02b-2-analysis-context-package-decisions.md` Resolved). 신설 literal: `ContextSearchPurpose.ANALYSIS_CONTEXT`, `ContextNeed.PRIOR_MEMORY`. **D1=A(검색+패키징, 판정은 2B.3)**: 이 slice는 coarse 후보군(같은 project·같은 `memory_type`의 canonical `MemoryEntry`)을 결정적으로 조회·패키징만 하고, 동일성/action 판정과 scope key 정밀화는 2B.3다. **D2=A + semantic seam**: `PriorMemoryBackend` Protocol 주입 seam(현재 `DeterministicPriorMemoryBackend`=결정적 key 조회, 후속 semantic 검색이 같은 인터페이스로 교체). **D3=A**: 단일 ContextPackage schema에 `PriorMemoryItem`(memory_id/memory_type/value/status/version/source_ref_ids/match_reason) 추가 — taxonomy 5필수(값·상태·source·version·비교 이유) 충족. `value`는 MemoryEntry의 `payload`(Mapping, F3). `scope`는 MemoryEntry 부재라 담지 않음 → §8 ⑧ 추적은 2B.3까지 열림(D1=A 위임). ContextPackage에 `prior_memories` field 추가, `trace`는 optional(analysis_context는 planner/plan 없어 `None`). **D4=B(A 포함 hybrid)**: 검색 primitive는 `memory_types` 파라미터화(`AnalysisContextRequest`), 진입면은 job-aware(HTTP가 job candidate types → coarse memory_type 집합 유도). 빈 `memory_types`=빈 package(비교 대상 없음, 절대 전체 아님). **F4 self-exclusion**: `exclude_job_id`로 그 job이 승격한 memory 제외(HTTP는 `exclude_job_id=job.id`) — 오너 승인 잠정값, 2B.3 compare 상호작용 관찰 후 확정. **D5=A(purpose별 Gate 분기)**: `evaluate_analysis_context_gate`는 analysis_context 전용 — candidate 금지는 무적용(대상이 canonical), Writing item(macro/micro) 누출만 차단. cross-project 격리는 project-scoped 조회 계약이 보장(F5, PriorMemoryItem에 project_id 없음). MemoryStatus가 canonical 단일이라 non-canonical guard는 미도입(불가능 시나리오 방어 회피). **D6=B**: HTTP `POST /projects/{project_id}/analysis/jobs/{job_id}/context`. `/context-search`(Writing 전용)는 이제 `analysis_context` purpose를 400으로 거절(purpose 표면 분리). 회귀 17개(`tests/test_analysis_context.py` 10 + `tests/test_analysis_context_api.py` 7 — 독립 검증 후속 O6 다중-type 합집합/중복제거 1개 포함). 검증 후속으로 HTTP endpoint의 도달 불가 `InvalidAnalysisContextRequest→400` dead-code를 제거했다(request 검증은 service layer 소유). | 사용자 결정, `plans/02b-2-analysis-context-package-decisions.md`, `tests/test_analysis_context.py`, `tests/test_analysis_context_api.py` |
| v1.6.40 | 2026-07-05 | Phase 2B.1(canonical `MemoryEntry` store + candidate 승격) 첫 code slice를 구현했다(`services/application/app/memory/`). `MemoryEntry`는 canonical 저장 단위로 status `canonical`(단일 literal), 승격된 candidate의 `payload`/`provenance`/`source_ref_ids`/`confidence`를 보존하고 첫 `version=1` + 감사 필드(`analysis_job_id`/`source_candidate_id`/`promotion_mode`/`applied_threshold`)를 가진다. `memory_type`/`provenance`는 2A enum을 재사용한다(D5=A: 2A 3종 유지). 승격 두 경로: (1) 수동 승인 `promotion_mode="manual"`은 confidence 무관 항상 `canonical`; (2) 결정적 threshold gate `promotion_mode="auto_threshold"`는 `threshold is not None and confidence >= threshold`일 때만 승격하고 미만은 candidate `needs_review` 유지(수동 경로 보존). 자동 승격 threshold는 주입값 `MEMORY_AUTO_PROMOTION_THRESHOLD`이며 기본 `None`(off) — 품질 fixture 전까지 추측값으로 canon 미양산(D2=B). 승격 idempotency는 `(project_id, source_candidate_id)` unique index(`uniq_memory_candidate_promotion`, 같은 candidate 재승격=동일 memory). HTTP: `POST /projects/{id}/analysis/candidates/{cid}/promote`(수동), `POST /projects/{id}/analysis/jobs/{jid}/auto-promote`(gate 적용), `GET /projects/{id}/memory[/{mid}]`(조회, project 격리). **2B.1 slice 경계(작업자, 오너 확인 대상)**: D3 entity/scope key 매칭·충돌 해소는 compare(2B.3) 소관이라 여기서 구현하지 않는다 — 2B.1은 create-only/`version=1`이고 유일성은 `source_candidate_id`로만 잡으며, scope key 산출·같은 entity 중복 canonical의 update/merge는 2B.3에 위임한다(브리프 "이후 update는 2B.3 upsert 연결"과 정합). `memory_entries`는 운영 collection에 추가. | `tests/test_memory_phase2b.py`, `tests/test_memory_api.py`, `tests/test_memory_mongo.py`, `plans/02b-analysis-compare-kickoff-decisions.md` |
| v1.6.39 | 2026-07-05 | Phase 2B(기존 기억 대조·canonical memory) 착수 결정 브리프를 승인했다(`plans/02b-analysis-compare-kickoff-decisions.md`). **D1=A**: 첫 sub-slice(2B.1)는 canonical memory store(`MemoryEntry`) + `needs_review` candidate 승격을 세우고 compare/action은 후속(대조 상대를 먼저 확보, Phase 4 ⑤/⑧ 종속의 토대). **D2=B**: confidence 기반 자동 승격을 채택하되, **AI가 아니라 결정적 시스템 threshold gate가 승격**한다(Analysis AI 경계 "canon 확정 금지" 유지, 문구 개정 없음) — threshold 이상만 자동 `canonical`, 미만은 `needs_review` 유지 + 수동 승인 경로 보존. threshold는 품질 fixture/benchmark 근거(SoT v1.6.13 budget 선례)이며 그 전까지 보수적 주입 설정값(추측값으로 canon 양산 금지). 승격 MemoryEntry는 승격 근거(confidence/threshold/source_refs/provenance/job_id) 기록. **D3=A**: entity resolution은 결정적 key(`memory_type + scope_type + scope_id` + 정규화 name) 완전일치만, 별칭/동명이인은 `merge/split` review 후보(자동 병합 없음). **D4=A**: action literal `create/update/add_evidence/no_change/conflict` + `merge/split`(review-only); 판정 경계는 2B.3 fixture로 확정. **D5=A**: taxonomy는 2A 3종 유지. ⑧ Analysis 비교용 package(`analysis_context` purpose)와 ⑤ Writing canonical 포함은 각 후속 slice 종속으로 명문화. 이 브리프는 결정만이며 코드는 2B.1부터. | 사용자 결정, `plans/02b-analysis-compare-kickoff-decisions.md`, `plans/02-analysis-pipeline.md` §Phase 2B, `plans/analysis-memory-taxonomy.md` |
| v1.6.38 | 2026-07-05 | Phase 4 ContextPackage 완성(⑤ candidate 포함 §5 B / ⑧ Analysis 비교용 뷰 §8 C)이 Phase 2B에 종속됨을 오너 결정으로 확정했다(브리프 `plans/04-context-package-completion-decisions.md`, D1=B). `needs_review` candidate 포함은 지금 하지 않고 승인/canonical 승격 경로가 생기는 Phase 2B로 미룬다 — canonical store 부재 상태의 "지금 포함"은 미검증 후보를 Writing 근거로 흘려보내는 것이라 `evaluate_context_gate`의 candidate 라벨 금지(Writing-안전성 방어선)를 근거 없이 완화하게 된다. 따라서 D2/D3/D4(candidate 검색 경로·`prior_memory` need 신설·Gate 완화)는 열지 않는다. ⑧ Analysis 비교용 확장 필드는 착수 브리프 §8대로 Phase 2B 착수 브리프가 확정한다. Phase 4는 현재가 합리적 정지점이다(Writing용 ContextPackage는 Phase 5 MVP에 충분, candidate 미포함, Gate가 candidate 금지 유지). 코드/public literal 변경 없음 — 미확정 항목의 상태만 "Phase 2B 종속"으로 확정. | 사용자 결정, `plans/04-context-package-completion-decisions.md`, `plans/04-agentic-search-kickoff-decisions.md` §5·§8 |
| v1.6.37 | 2026-07-05 | Phase 3B index sync worker를 real Chroma archive mutation에 배선했다(Next Tasks worker→real Chroma). `ChromaArchiveIndexMutationAdapter`(`services/application/app/indexing/chroma.py`)는 archive event를 real Chroma delete로 처리한다: `project_archived`는 `{project_id}` 매칭 derived source-block record 전부, `draft_archived`는 project-scoped `{project_id, draft_id}` 매칭 record만 삭제한다(`entry.source.mongo_id`가 draft id). derived record는 SOT에서 rebuild 가능하므로 cleanup은 tombstone이 아니라 **delete**다. 삭제 대상이 이미 없으면 목표 상태(archived 콘텐츠가 derived index에 없음)가 달성된 것으로 보고 `DerivedIndexRecordNotFound`를 raise → worker가 idempotent success로 처리한다(브리프 §8.2). 삭제 전 `get(where, include=[])`로 존재를 확인하고, `ids` 길이가 0이면 delete를 호출하지 않는다(numpy-like truthiness 회피 위해 truthiness 대신 `len()` 사용). `ChromaCollection` protocol에 `delete(where)`가 추가됐다. worker command `scripts/index_sync_worker.py`는 `CHROMA_HOST` 설정 시 `ChromaArchiveIndexMutationAdapter`(`connect_chroma_collection`, `CHROMA_PORT`/`CHROMA_COLLECTION` env는 create_app B.4 규약과 동일)를, 미설정 시 종전 `RecordingArchiveIndexMutationAdapter`를 쓴다. worker summary JSON에 `archive_backend`(`chroma`/`in_memory_fake`)가 추가됐다. claim/retry/backoff/terminal-move lifecycle은 v1.6.29 그대로다. 실제 Chroma 서버 관통 live smoke는 후속이다. | Next Tasks(worker→real Chroma), `plans/03-index-worker-retry-decisions.md` §8, `tests/test_chroma_adapter.py`, `tests/test_index_sync_worker_script.py` |
| v1.6.36 | 2026-07-05 | Phase 4 real 영속 vector 백엔드(후보 B)를 wiring했다(브리프 `plans/04-real-vector-backend-decisions.md`, Approved). `create_app`은 env 기반으로 vector 백엔드를 선택한다: `CHROMA_HOST`가 있으면 real 영속 `ChromaVectorIndexAdapter`(재시작 생존, rebuild summary `backend="chroma"`), 없으면 종전 `InMemoryVectorIndexAdapter`(`backend="in_memory_fake"`)다. embedding은 `EMBEDDING_SERVICE_URL`이 있으면 real `RemoteEmbeddingProvider`(별도 embedding 서비스 컨테이너의 `dragonkue/BGE-m3-ko`, 1024-dim, `expected_dimensions=1024` 차원 guard armed), 없으면 `DeterministicFakeEmbeddingProvider`다. 주입된 `vector_index`(테스트)는 항상 fake backend label을 유지한다. embedding 서비스는 llama gateway와 분리된 컨테이너라 vector 백엔드는 LLM 게이트와 독립이다. stale guard는 backend 무관하게 SOT를 재조회하므로 Chroma hit도 정본 재확인 후에만 ContextItem이 된다. `backend` literal enum에 `chroma`가 추가됐다. 실제 Chroma 서버/embedding 모델 관통(1024-dim assert, 재시작 vector hit 생존)은 B.5 live 검증이다. | 사용자 결정, `plans/04-real-vector-backend-decisions.md`, `tests/test_real_vector_backend_wiring.py` |
| v1.6.35 | 2026-07-05 | Phase 4 공유 in-process vector index를 도입했다. `create_app`이 단일 `InMemoryVectorIndexAdapter`(+ `DeterministicFakeEmbeddingProvider`)를 소유하고, source-block rebuild endpoint는 여기에 write하며 기본 wiring된 context search는 여기서 read한다 — 같은 프로세스에서 rebuild 후 context search를 하면 `source_quote` 등 vector need가 stale guard + SOT 재조회를 통과한 실제 hit을 반환한다. 이 공유 index는 프로세스 수명 in-memory이고 비durable이며(재시작 시 소실) `backend` literal은 여전히 `in_memory_fake`다. 공유 index는 `LLM_GATEWAY_BASE_URL` 유무와 무관하게 생성돼 rebuild가 채우고, planner 미구성 시 `/context-search`만 종전대로 503이다. rebuild HTTP/CLI summary count(`records_indexed`/`records_query_visible`/`records_archived`)는 해당 rebuild의 `snapshot_id`로 scope해 per-rebuild(누적 없음) 의미와 v1.6.22/v1.6.23 계약을 그대로 유지한다 — 누적은 뒤에서만 일어난다. real ChromaDB/ES persistent backend는 계속 후속이다. | 사용자 결정, `plans/04-shared-vector-index-decisions.md`, `tests/test_context_search_shared_index.py` |
| v1.6.34 | 2026-07-04 | Phase 4 Slice 4.3 context search HTTP API + async wiring을 구현했다. `ContextSearchService.build_context_package`가 async가 됐고(planner 결과를 `inspect.isawaitable`로 await — Slice 4.1 sync fake planner와 Slice 4.2 async 터미널 JSON planner가 같은 seam에 꽂힌다), `evaluate_context_gate`는 sync 유지다. `POST /projects/{project_id}/context-search`가 ContextPackage(macro/micro/constraints/do_not_use/trace)와 독립 Context Gate 결정을 직렬화해 반환한다. 오류 매핑: 미지원 purpose/need literal·미요청 need 등 invalid request는 400, wall-clock 초과는 504, `ContextSearchFailed`(llm_error/backend_error/system_error/sot_error)는 502, missing project는 404, planner 미구성(`LLM_GATEWAY_BASE_URL` 부재)은 503이다. create_app이 env 기반 `_default_context_search_service`로 TerminalJsonSearchPlanner를 wiring한다. deployed vector adapter는 여전히 non-persistent fake라 vector need는 hit이 없고 Mongo-direct need(current/recent scene)만 서빙한다(real Chroma 후속). | 사용자 결정, `plans/04-agentic-search-kickoff-decisions.md` §9.3, `tests/test_context_search_api.py` |
| v1.6.33 | 2026-07-04 | Phase 4 Slice 4.2 터미널 JSON LLM planner adapter를 구현했다. `services/application/app/context_search/planner.py`가 versioned prompt template `context_search_plan_v1`(task_type `context_search_plan`, 기존 `prompt_templates` 저장소 재사용)과 `TerminalJsonSearchPlanner`를 제공한다. planner는 Gateway `/v1/generate` 1-turn 호출로 SearchPlan JSON을 strict parse하고, malformed/out-of-set output이면 1회 repair, 그래도 실패하면 `ContextSearchFailed(llm_error)`다. adapter는 enum literal(need/tool) 멤버십만 검증하고, plan 의미 검증(미요청 need, need별 불허 tool, project 일치)은 `ContextSearchService._validate_plan`이 계속 소유한다. `project_id`는 모델이 아니라 request에서 주입한다. provider가 async라 adapter도 async이며(Phase 2A extraction 패턴), Slice 4.1의 sync `SearchPlanner` Protocol/`build_context_package`는 fake 주입 seam으로 유지된다 — async planner의 service 통합은 HTTP wiring slice로 미룬다. | 사용자 결정, `plans/04-agentic-search-kickoff-decisions.md` §9.2, `tests/test_context_search_planner.py` |
| v1.6.32 | 2026-07-03 | Phase 4 Slice 4.1 독립 검증(조건부 합격)의 차단 조건을 폐쇄했다. `sot_error`의 범위를 명문화: SOT reload 호출(position reload, vector stale-guard 검증, hit 재조회, Gate 재검증)에서 탈출하는 모든 non-NotFound 예외(실가동 pymongo 장애 포함)는 원형 전파 없이 `ContextSearchFailed(sot_error)` 전체 실패다. NotFound는 경로별 의도 분기다 — vector hit snapshot NotFound는 `snapshot_missing` soft stale 제외, Mongo position NotFound는 `sot_error` 전체 실패. `system_error`는 발화 경로가 생길 때 회귀와 함께 여는 예약 literal이다. toggle repo로 진짜 백엔드 예외를 주입하는 양방향 회귀 4개를 추가했고 변이 증명(catch 축소 시 5개 재실패)으로 잠갔다. | `docs/verifications/2026-07-03/context_search_slice_4_1.md`, `plans/04-agentic-search-kickoff-decisions.md`, `tests/test_context_search.py` |
| v1.6.31 | 2026-07-03 | Phase 4 Slice 4.1 context search를 구현했다. `services/application/app/context_search/`가 purpose/need/tool/status/error literal, `ContextSearchRequest`/`SearchPlan`/`ContextItem`/`ContextPackage`/`GateDecision` 계약, planner 주입형 `ContextSearchService`, 독립 `evaluate_context_gate()`를 제공한다. vector hit는 Phase 3A stale guard와 Mongo SOT 재조회를 거친 뒤에만 ContextItem이 되고 index text는 근거로 쓰지 않는다. `current_scene`/`recent_scenes`는 SOT block kind 기반 deterministic 경계다. retriever step 실패는 `degraded=true` + 계열 error type으로 trace에 남고, SOT reload 실패는 `sot_error` 전체 실패다. package는 persist하지 않고 응답 단위 trace를 포함한다. `InMemoryVectorIndexAdapter.query_similar()`가 project-scoped cosine 유사도 query 표면으로 추가됐다. LLM planner adapter(Slice 4.2), HTTP surface, ES lexical, candidate 포함은 후속이다. | 사용자 결정, `plans/04-agentic-search-kickoff-decisions.md`, `tests/test_context_search.py` |
| v1.6.30 | 2026-07-03 | Phase 4 agentic search 착수 브리프를 승인했다. purpose는 `writing_context` 1종, need는 `current_scene`/`recent_scenes`/`event_context`/`source_quote` 4종으로 시작하고 후속 확장 가능하다. planner는 터미널 JSON LLM planner를 즉시 채택한다 — LLM이 versioned prompt 기반 1-turn 호출로 SearchPlan JSON을 생성하고(strict parse + 1회 repair), tool-call flat loop planner는 Gateway tool-call wire 계약 해소 후 전환 계획(브리프 §2.1)으로 추적한다. retrieval은 Phase 3A fake vector + Mongo direct 순차 실행, ranking/budget은 deterministic 최소 규칙이다. `needs_review` candidate는 첫 slice에서 제외하되 `candidate`/`canonical` status 라벨 필드는 처음부터 계약에 연다. retriever step 실패는 degraded + 계열 구분 error taxonomy(`backend_error`/`system_error`/`llm_error`/`sot_error`, enum 확장 가능)로 기록하고 Mongo SOT reload 실패는 전체 실패다. ContextPackage는 첫 slice에서 persist하지 않는다. package는 단일 schema + purpose literal로 시작하되 이후 slice에서 Writing용/Analysis 비교용 모두 완성해야 한다(추적 의무). | 사용자 결정, `plans/04-agentic-search-kickoff-decisions.md`, `plans/04-agentic-search.md` |
| v1.6.29 | 2026-07-03 | Phase 3B one-shot index sync worker 첫 slice를 구현했다. Worker는 `pending` 또는 10분 이상 지난 stale `running` outbox entry를 claim해 recording-only fake archive mutation을 실행하고, attempt result를 `index_sync_logs`에 append한다. Claim lease는 `claimed_at` UTC datetime/BSON Date로 저장한다. Backoff는 `max_attempts=3` 기준 1분 → 5분 → terminal `failed`다. Terminal-location/index 전략은 terminal 이동을 채택해 `success|failed`가 되면 active outbox entry를 제거하고 terminal history는 `index_sync_logs`가 소유한다. Archive worker-time `not_found`는 idempotent success로 처리한다. | 사용자 결정, `plans/03-index-worker-retry-decisions.md`, `tests/test_indexing_phase3a.py`, `tests/test_index_sync_worker_script.py` |
| v1.6.28 | 2026-07-03 | Phase 3B worker/retry 실행 경계 브리프를 조건부 승인 상태로 추가했다. 첫 worker는 one-shot command로 구현하고 장기적으로 UI-triggered background/daemon이 같은 service를 재사용할 수 있게 둔다. Claim timeout은 10분이며, stale running 판정을 위해 `claimed_at` lease timestamp가 필요하다. Backoff는 `max_attempts=3` 기준 1분 → 5분 → terminal `failed`다. `backend_error`와 query-time `not_found`는 둘 다 최대 3회 시도한다. Dedup은 `pending|running` active entry에만 적용한다. 독립 검증 후 terminal-location/index 전략과 archive worker-time `not_found` 처리는 구현 전 오너 결정으로 분리됐다. | 사용자 결정, `plans/03-index-worker-retry-decisions.md`, `docs/verifications/2026-07-03/phase3b_worker_retry_brief.md` |
| v1.6.27 | 2026-07-03 | Phase 3B archive outbox 독립 검증 후속 보강을 반영했다. `index_sync_outbox`를 `mongo_collections.md` 운영 collection 레지스트리에 추가하고, `index_sync_logs`와 `sync_request_id`로 조인되는 pending request collection임을 명시했다. Mongo repository의 outbox document 직렬화/역직렬화는 fake collection round-trip 회귀로 잠갔고, `analysis_completed` event가 아직 code enum에 열리지 않았음을 명시 회귀로 고정했다. | `docs/verifications/2026-07-03/phase3b_archive_outbox_slice.md`, `tests/test_indexing_mongo_indexes.py`, `tests/test_indexing_phase3a.py` |
| v1.6.26 | 2026-07-03 | Phase 3B archive outbox 첫 code slice를 구현했다. `IndexSyncOutboxEntry`는 `project_id`, nullable `user_id`, event(`project_archived`, `draft_archived`), source(`mongo_collection`, `mongo_id`, optional `mongo_version`), canonical `targets.chroma.status`, `targets.chroma.backend="in_memory_fake"`, status(`pending|running|success|failed`), retry metadata(`attempt_count`, `max_attempts=3`, `next_attempt_at`, `last_error`)를 가진다. 서버/backend 계열 오류와 데이터 없음/not-found 계열 오류는 각각 `backend_error`, `not_found`로 분리한다. Application archive endpoint는 Core SOT archive 성공 후 `index_sync_outbox` pending entry를 idempotent하게 생성한다. Dedup key는 `(project_id, event, source.mongo_collection, source.mongo_id)`이고 outbox/log는 `sync_request_id`로 조인 가능하다. Worker execution, retry 실행/backoff 숫자, actual ChromaDB/Elasticsearch mutation, `analysis_completed` wiring은 후속이다. | 사용자 결정, `tests/test_indexing_phase3a.py`, `tests/test_application_api.py`, `tests/test_indexing_mongo_indexes.py` |
| v1.6.25 | 2026-07-03 | Phase 3B automatic sync/outbox 브리프를 승인·수정했다. 첫 automatic event source는 archive events(`project_archived`, `draft_archived`)로 시작하되, 오너가 장기적으로 더 맞는 흐름으로 본 `analysis_completed`를 후속 확장 경로로 열어 둔다. Delivery는 로컬 1인 프로젝트 기준 외부 queue 없이 Mongo outbox/polling을 사용한다. 저장 단위는 단일 `index_sync_logs`가 아니라 `index_sync_outbox` + `index_sync_logs` 분리를 채택하고, 두 collection은 `sync_request_id`로 조인한다. 첫 slice는 archive event outbox entry 생성만 다루며 worker/adapter execution, ChromaDB/Elasticsearch mutation, retry 실행은 후속이다. Persistent envelope는 canonical `targets` shape와 `backend="in_memory_fake"`를 사용하고, `user_id`는 user model 확정 전까지 nullable이다. | 사용자 결정, `plans/03-index-sync-outbox-decisions.md` |
| v1.6.24 | 2026-07-02 | Phase 3A source-block index hit의 explicit stale validation을 추가했다. `SourceBlockIndexingService.validate_source_block_record(record)`는 Core SOT를 재조회해 hit 사용 가능 여부와 stale reason literal(`project_archived`, `draft_archived`, `snapshot_missing`, `draft_mismatch`, `content_hash_mismatch`, `block_missing`)을 반환한다. `snapshot_missing`은 정본 snapshot이 없어 후속 draft/hash/block 검사를 진행할 수 없으므로 단독 reason으로 short-circuit한다. Drift 판정은 `version_id`가 아니라 snapshot `content_hash`와 block/draft pointer 정합성 기준이다. 이 검증은 archive 이후 기존 materialized record를 자동으로 숨기는 sync가 아니라, query/Context Gate 계층이 hit 사용 전에 정본 상태를 재확인하는 방어선이다. Automatic sync/outbox와 persistent vector backend는 후속이다. | `tests/test_indexing_phase3a.py` |
| v1.6.23 | 2026-07-02 | Phase 3A explicit source-block index rebuild를 Application HTTP API로 노출했다. `POST /projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild`는 현재 deterministic fake vector adapter를 사용해 rebuild summary(`project_id`, `snapshot_id`, `target`, `backend`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`)를 반환한다. `backend`는 `in_memory_fake`이고, missing/cross-project snapshot은 404다. Persistent vector backend와 automatic sync는 후속이다. | `tests/test_application_api.py` |
| v1.6.22 | 2026-07-02 | Phase 3A explicit source-block index rebuild script를 추가했다. `scripts/phase3a_rebuild_source_block_index.py --project-id ... --snapshot-id ...`는 `CORE_SOT_MONGO_URI` 또는 `--mongo-uri`로 Core SOT MongoDB를 읽고 deterministic fake vector adapter로 rebuild를 실행한 뒤 JSON summary(`project_id`, `snapshot_id`, `target`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`)를 출력한다. Exit code는 full write 성공 0, partial write 1, usage/config/domain error 2다. Application HTTP API endpoint와 persistent vector backend는 후속이다. | `tests/test_phase3a_rebuild_source_block_index_script.py` |
| v1.6.21 | 2026-07-02 | Phase 3A source block indexing 독립 검증 후속 보강을 반영했다. Phase 3A `IndexSyncRequest(project_id, snapshot_id, target)`와 `IndexSyncResult(request, records_attempted, records_written)`는 explicit rebuild용 in-process 축소 계약이며, `contracts.md` §7.3의 persistent sync log/outbox envelope(`sync_result_id`, `sync_request_id`, target별 결과, timestamps)는 후속 sync log slice 전까지 구현 대상이 아니다. Archived project/draft query exclusion은 explicit rebuild가 materialize한 record metadata 기준으로 적용되며, archive 이후 stale record를 즉시 숨기려면 재build 또는 후속 automatic sync가 필요하다. Draft-only archive 제외 분기는 회귀로 잠갔다. | `docs/verifications/2026-07-02/phase3a_source_block_index.md`, `tests/test_indexing_phase3a.py` |
| v1.6.20 | 2026-07-02 | Phase 3A source block indexing 첫 slice를 승인·구현했다. 첫 index target은 Core SOT source block only, backend는 Chroma-like vector contract with deterministic fake adapter, embedding은 fake provider only, delivery는 explicit snapshot rebuild, archive/delete 반영은 status/version filter다. Index record는 `project_id`, collection, document/block id, version id, content hash를 가진 Mongo pointer를 포함하며, archived project/draft record는 query 결과에서 제외한다. Adapter failure는 Core SOT save를 rollback하지 않는다. | 사용자 승인, `plans/03-indexing-kickoff-decisions.md`, `tests/test_indexing_phase3a.py` |
| v1.6.19 | 2026-07-01 | Phase 2A repair retry가 valid JSON이지만 source_ref catalog anchor literal을 보존하지 못한 출력도 1회 repair 대상으로 삼도록 보강했다. Adapter는 parsed candidate의 `source_ref_id`, span, quote, content_hash를 입력 catalog와 대조하고 mismatch가 있으면 parser/schema repair와 같은 prompt 경로로 재호출한다. repair 후에도 catalog mismatch가 남으면 성공으로 보정하지 않고 기존 runner/source validation 경계가 `source_invalid`를 보존한다. | `tests/test_analysis_extractor_schema.py`, `scripts/phase2a_provider_live_smoke.py` |
| v1.6.18 | 2026-07-01 | Phase 2A source_ref catalog 준비를 위한 Application HTTP surface를 추가했다. `POST /projects/{project_id}/snapshots/{snapshot_id}/source-refs`는 immutable snapshot span으로 source_ref를 non-idempotent 생성하고, `GET /projects/{project_id}/snapshots/{snapshot_id}/source-refs`와 `GET /projects/{project_id}/source-refs/{source_ref_id}`는 같은 project의 catalog/ref만 읽는다. invalid span은 400, missing/cross-project snapshot/ref는 404이며, archived project에서도 source_ref 생성·조회는 허용된다. | `tests/test_application_api.py`, `scripts/phase2a_provider_live_smoke.py` |
| v1.6.17 | 2026-07-01 | Phase 2A live provider output 원인 분석 뒤 Application-side JSON repair retry를 추가했다. `/v1/generate` 경로는 유지하고, `VersionedPromptAnalysisExtractionAdapter`가 첫 provider content를 strict parser로 검증한 뒤 실패 시 원문 output과 parser error, 원래 prompt payload를 포함한 repair prompt를 1회만 재호출한다. repair 출력도 같은 strict parser/source validation/candidate schema를 통과해야 하며, 실패하면 기존처럼 `schema_invalid`로 job failure가 보존된다. | 사용자 결정, `tests/test_analysis_extractor_schema.py`, `scripts/phase2a_provider_live_smoke.py` |
| v1.6.16 | 2026-07-01 | Phase 2A provider/Gateway runner factory wiring의 첫 구현 slice를 추가했다. Core SOT는 snapshot별 source_ref catalog read surface를 제공하고 Mongo required index `source_refs_by_project_snapshot`을 설치한다. Prompt template은 `prompt_templates` 저장소에 `task_type + version` unique contract로 seed/fetch하며 `analysis_extract_v1`을 기본 seed한다. Prompt builder는 snapshot과 source_ref catalog를 Gateway `ChatCompletionRequest`로 조립한다. Application은 `LLM_GATEWAY_BASE_URL`이 설정된 경우 `/v1/generate` 기반 `GatewayGenerateProvider`와 `VersionedPromptAnalysisExtractionAdapter`로 기본 analysis runner를 구성하고, env가 없으면 기존처럼 503을 반환한다. `{"candidates":[]}`는 유효한 빈 extraction으로 처리한다. | `tests/test_core_sot.py`, `tests/test_prompt_templates.py`, `tests/test_analysis_prompt_builder.py`, `tests/test_analysis_gateway_provider.py`, `tests/test_analysis_extractor_schema.py`, `tests/test_analysis_runner.py`, `tests/test_application_api.py` |
| v1.6.15 | 2026-07-01 | Phase 2A provider/Gateway wiring pre-implementation 결정을 승인했다. 첫 실제 provider wiring은 tool-call 없는 terminal JSON extraction으로 진행하고, 모델은 새 source_ref를 생성하지 않고 입력 source_ref catalog의 id를 선택한다. Prompt template은 DB에 저장해 versioned 관리하며 첫 literal은 `analysis_extract_v1`, task_type은 `analysis_extract`다. Gateway 호출 surface는 구현 전 비용 확인으로 `/v1/generate` 임시 사용과 `/v1/generate-structured` 최소 구현 중 선택한다. | 사용자 결정, `plans/02-analysis-provider-wiring-decisions.md` |
| v1.6.14 | 2026-06-30 | 첫 export 형식을 plain text + Markdown으로 확정하고 Slice 1 draft version export 계약을 추가했다. `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export?format=txt\|markdown`은 선택 version snapshot의 `raw_text`를 verbatim body로 내보내고(AI metadata 미주입, Markdown 합성/제거 없음, 두 형식 body 동일), `format`은 content_type/확장자만 가른다. payload에 version 추적 필드 포함. unsupported format 400, missing/cross-project version 404, archived도 export 허용. 사용자 결정: 막힌 Next Tasks 대신 export 진행, 형식은 plain text + Markdown. | 사용자 결정, `tests/test_core_sot.py`, `tests/test_application_api.py` |
| v1.6.13 | 2026-06-30 | Gemma Q4_0 llama.cpp live benchmark를 실행하고 AgentLoopRunner task profile의 초기 production budget/retry 숫자 기본값을 확정했다. Report는 `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`이며, `flat-loop-gate.md`가 `analysis_compare`, `context_search`, `writing_generate` 기본 policy를 소유한다. | 사용자 요청, `scripts/benchmark_llm_provider.py`, `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json` |
| v1.6.12 | 2026-06-30 | Phase 2A analysis run endpoint 계약을 승인·구현했다. `POST /projects/{project_id}/analysis/jobs/{job_id}/run`은 pending job만 runner dependency로 실행하고 요청 안에서 await해 terminal job과 candidate 목록을 반환한다. `running`/`succeeded`/`failed` job은 재실행하지 않고 `idempotent_replay=true`로 현재 job과 저장된 candidate를 반환한다. pending job에서 runner가 구성되지 않았으면 503, missing/cross-project 및 `snapshot_not_found`는 404, `schema_invalid`/`source_invalid` 계열은 400, `duplicate_conflict`는 409, provider/기타 실행 오류는 502로 표면화한다. source_ref 자동 생성과 Gateway runtime wiring은 제외다. | 사용자 요청, `tests/test_application_api.py`, `tests/test_analysis_runner.py` |
| v1.6.11 | 2026-06-30 | Phase 2A analysis job/candidate HTTP read surface를 추가했다. Application API는 `POST /projects/{project_id}/analysis/jobs`로 job을 idempotent 생성/replay하고, `GET /projects/{project_id}/analysis/jobs/{job_id}`와 `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`로 job 상태와 candidate를 조회한다. 이 API는 runner/gateway 실행을 시작하지 않으며, 존재하지 않는 project 또는 cross-project job/candidate 접근은 404다. | `tests/test_application_api.py` |
| v1.6.10 | 2026-06-29 | Phase 2A job all-or-nothing 범위를 명확화했다. all-or-nothing은 candidate write에 한정되며, job/task 생성은 idempotent setup이라 실패 후에도 남을 수 있다(롤백 대상 아님). 동작 변경 없음, runner slice 2 검증의 비차단 오해 여지 해소. | `verifications/2026-06-29/analysis_job_state_runner_slice2.md` |
| v1.6.9 | 2026-06-29 | Phase 2A job 상태 전이와 실패 상태 저장 계약을 승인했다. 상태는 `AnalysisJob`에만 두고(Task 무상태), `pending→running→succeeded|failed` 전이만 허용하며 terminal은 불변이다. runner는 새 job(`pending`)만 실행하고 기존 job은 replay로 반환하며, `failed`는 terminal이라 재실행은 새 `idempotency_key`로 한다. `failed`는 닫힌 `failure_reason` enum(`snapshot_not_found`, `source_invalid`, `schema_invalid`, `provider_error`, `duplicate_conflict`) + free-text `failure_detail`로 저장한다. | 사용자 결정, `plans/02-analysis-job-state-decisions.md` |
| v1.6.8 | 2026-06-29 | Phase 2A candidate write의 write-error 분류를 정밀화했다. duplicate-key(code `11000`) 충돌만 `DuplicateAnalysisCandidateRequest`로 표면화하고, 그 외 `BulkWriteError`/`PyMongoError`는 원본 타입을 보존해 인프라 오류 오표기를 막는다. fallback은 매핑 여부와 무관하게 이번 시도 candidate `_id`를 먼저 정리한다. | `verifications/2026-06-29/analysis_mongo_persistence_hardening.md` |
| v1.6.7 | 2026-06-29 | Phase 2A service batch API의 intra-batch idempotency를 명시했다. 같은 batch 안의 동일 `project_id + task_id + logical_key` request는 첫 candidate를 만들고 이후 항목은 idempotent replay로 정규화하며, 다른 logical_key는 별도 candidate로 유지한다. Mongo bulk duplicate는 stable `DuplicateAnalysisCandidateRequest`로 표면화한다. | `verifications/2026-06-29/analysis_mongo_persistence.md` |
| v1.6.6 | 2026-06-29 | Phase 2A Analysis Mongo persistence 계약을 명시했다. `analysis_jobs`, `analysis_tasks`, `analysis_candidates`를 저장하고 job/task/candidate idempotency는 unique index로 강제한다. Candidate batch write는 transaction 경로에서 한 트랜잭션으로 commit하고, non-transaction fallback은 single-writer local/test 경로로 실패 시 이번 시도 candidate만 rollback한다. | `plans/02-analysis-pipeline.md` |
| v1.6.5 | 2026-06-29 | Phase 2A runner는 source validation이 구성된 `AnalysisService`만 받도록 명시하고, 같은 run의 duplicate `(task_id, logical_key)` draft는 result/write에서 1개로 정규화한다. Mongo persistence slice에서는 runner all-or-nothing의 transaction/fallback 보존을 별도 검증한다. | `verifications/2026-06-29/analysis_phase2a_slice4.md` |
| v1.6.4 | 2026-06-29 | Phase 2A extraction runner 계약을 명시했다. Runner는 job을 idempotent 생성/재사용하고, snapshot 로드→provider extraction→task 생성/재사용→전체 draft 사전 검증→candidate 저장 순서로 실행한다. Task는 `project_id + job_id + candidate_type`으로 재사용하며, candidate write는 모든 draft의 logical_key/source/schema 검증 뒤 시작한다. | `plans/02-analysis-pipeline.md` |
| v1.6.3 | 2026-06-29 | Phase 2A `source_anchors` identity를 unordered set으로 명확화했다. 같은 anchor 중복은 identity와 parsed draft에서 하나로 정규화하며, ordered evidence chain이 필요해지면 순서 의미를 별도 필드(`sequence`/`evidence_order` 등)로 계약화한다. | `verifications/2026-06-29/analysis_phase2a_slice3.md` |
| v1.6.2 | 2026-06-29 | Phase 2A logical_key derivation에서 같은 `source_anchors` set은 순서와 무관하게 같은 key를 만든다고 명시했다. Anchor 내용이 다르면 별도 candidate identity다. | `verifications/2026-06-29/analysis_phase2a_slice2.md` |
| v1.6.1 | 2026-06-29 | Phase 2A source validation 이후 최소 taxonomy schema와 fake-provider extraction adapter 계약을 명시했다. Payload는 `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`이고 모든 field는 non-empty string이다. Provider extraction output은 top-level `{candidates: [...]}` JSON object이며, logical_key는 `candidate_type + payload + source_anchors` canonical JSON SHA-256으로 파생한다. | `plans/02-analysis-kickoff-decisions.md`, `plans/02-analysis-pipeline.md` |
| v1.6 | 2026-06-29 | Phase 2A 착수 최소 계약 승인: taxonomy 3종(`character_observation`, `event_observation`, `open_question_observation`), provenance `source_observed`/`ai_inferred`, candidate action `create` only, status `needs_review`, confidence range만 강제, `create_source_ref` primitive non-idempotent 유지 + candidate/job 저장층 retry idempotency 소유, 2A/2B milestone 분리. 같은 날 검증 보강으로 confidence NaN 거절, action≠`create` 회귀, `logical_key` 임시 identity 계약을 명시했다. | 사용자 결정, `plans/02-analysis-kickoff-decisions.md`, `verifications/2026-06-29/analysis_phase2a_slice1.md` |
| v1.5.1 | 2026-06-28 | Core SOT Mongo adapter setup 계약 명확화: query path를 지탱하는 required index는 `uniq_save_request`와 `blocks_by_snapshot`이며, MongoDB가 required index 생성을 거부하면 `MongoRepositorySetupError`로 표면화한다. 현재 query path가 없는 `source_refs_by_snapshot` 인덱스는 required contract에서 제외한다. | `docs/verifications/2026-06-28/mongo_index_setup.md` O1/O2 |
| v1.5 | 2026-06-28 | archive를 읽기 전용 상태로 명문화: 읽기 허용, 본문 쓰기(draft 생성·version 저장)+메타데이터 수정(rename) 차단(409), SOT 본문은 archive 무관 불변, 상태 전이(unarchive)와 source_ref/분석 후보 archived 정책은 범위 밖. 기존 구현·회귀와 정합하는 문서 명문화. (같은 날 비의미 명확화: archived project 하위 draft를 archive하는 것은 상태 전이이므로 하위 draft 쓰기 차단의 예외임을 명시 — `archive_api_endpoint.md` Issue #1.) | 사용자 결정, `docs/verifications/2026-06-28/rename_api.md` R1 |
| v1.4 | 2026-06-28 | non-transaction fallback을 single-writer 전용으로 명시. 동시성 안전은 transaction 기본 경로가 담당하고, fallback의 orphan cleanup/retry guard는 같은 writer의 순차 재시도에만 정의됨. | 사용자 결정(R2 option b), `docs/verifications/2026-06-28/mongo_adapter_recheck.md` |
| v1.3 | 2026-06-26 | Core SOT persistence/retention 계약 승인: Mongo transaction 기본, 제한적 non-transaction fallback, explicit version save only, save idempotency key 필수, project/draft archive와 snapshot/version/source_ref 보존. | 사용자 승인 |
| v1.2 | 2026-06-26 | Core SOT text/reference 계약 승인: raw snapshot 기준, Unicode code point offset, raw UTF-8 SHA-256 content hash, deterministic MVP source block split. Adaptive/length-based chunking은 파생 index layer 후속 후보로 분리. | 사용자 승인 |
| v1.1 | 2026-06-26 | Slice 1 실행 경계 승인: monorepo+독립 LLM Gateway, FastAPI Application API, 느슨하게 분리 가능한 Worker 경계. frontend framework 최종 선택은 보류. | 사용자 승인 |
| v1.0 | 2026-06-26 | SoT를 정본 계약 인덱스로 승인. 미확정 항목은 계속 추측 구현 금지. | 사용자 승인, `docs/verifications/2026-06-25/system_contract_sot.md` |

## 문서 역할

| 문서 | 역할 | 지위 |
|---|---|---|
| 이 문서 | 서비스/계약 SoT 인덱스와 우선순위 | Approved SoT v1.6.43 |
| [`plans/README.md`](plans/README.md) | 계획 문서 진입점과 Phase/MVP 관계 | Draft |
| [`plans/00-foundations.md`](plans/00-foundations.md) | 전역 원칙과 제품 경계 | Draft |
| [`plans/implementation-plan.md`](plans/implementation-plan.md) | 구현 순서, slice 상태, 검증 gate | Draft |
| [`plans/llm-gateway.md`](plans/llm-gateway.md) | LLM Gateway 계약과 Gemma Q4 검증 | Proposed |
| [`plans/flat-loop-gate.md`](plans/flat-loop-gate.md) | AgentLoopRunner decision/tool/budget/completion 계약 | Draft, 일부 구현 검증됨 |
| [`plans/product-shell.md`](plans/product-shell.md) | 사용자 제품 표면 | Draft |
| [`plans/01-core-sot.md`](plans/01-core-sot.md) | MongoDB 정본 저장 계약 | Draft |
| [`plans/02-analysis-kickoff-decisions.md`](plans/02-analysis-kickoff-decisions.md) | Phase 2A 착수 최소 결정 | Approved for Phase 2A kickoff |
| [`plans/02-analysis-job-state-decisions.md`](plans/02-analysis-job-state-decisions.md) | Phase 2A job 상태 전이 결정 | Approved for Phase 2A job-state slice |
| [`plans/02-analysis-provider-wiring-decisions.md`](plans/02-analysis-provider-wiring-decisions.md) | Phase 2A provider/Gateway wiring 결정 | Approved for Phase 2A provider wiring pre-implementation |
| [`plans/02-analysis-pipeline.md`](plans/02-analysis-pipeline.md) | 분석 후보와 Analysis Gate | Draft |
| [`plans/03-indexing.md`](plans/03-indexing.md) | Chroma/ES 파생 인덱스 | Draft |
| [`plans/04-agentic-search.md`](plans/04-agentic-search.md) | ContextPackage와 Context Gate | Draft |
| [`plans/05-writing-ai.md`](plans/05-writing-ai.md) | WritingCandidate와 Writing Gate | Draft |
| [`plans/06-review-ui.md`](plans/06-review-ui.md) | 후보 검토와 상태 전이 UI | Draft |
| [`contracts.md`](contracts.md) | 초기 계약 아이디에이션 | Reference only |

## 시스템 경계

처음에는 monorepo 안에서 서비스 경계를 나눈다. 본격 MSA는 전제하지 않는다.

| 구성요소 | 소유 책임 | 소유하지 않는 것 |
|---|---|---|
| Product Shell | 프로젝트/원고 작업 공간, 처리 상태, 내보내기 | 기억 정본, AI 판정 |
| Application API | 제품 API, domain service, Gate 합성, request context | 모델 lifecycle, 벡터/lexical 정본 판정 |
| Worker | 분석/색인/검색 job 실행, AgentLoopRunner 실행 | 사용자 UI, LLM Gateway 내부 transport |
| MongoDB | 원문, snapshot, source_ref, 상태, version, 구조화 기억의 정본 | 의미 검색 또는 lexical ranking |
| ChromaDB | semantic retrieval cache | canonical memory |
| Elasticsearch | lexical/metadata retrieval index | canonical memory |
| LLM Gateway | model load, inference, provider error, usage/timing | Mongo/Chroma/ES 접근, project memory lookup, domain tool 실행 |
| AgentLoopRunner | bounded flat loop, tool allowlist, budget, terminal decision | domain Gate 통과 여부, memory update |
| Gate | 후보 검증과 처분 | 사용자 의도 최종 확정, loop 종료 원인 |
| Review UI | 승인/거절/수정 UX | 자동 canon 승격 규칙의 독자 소유 |

## 구현 기술 결정

- 저장소 구조는 monorepo를 유지한다.
- LLM Gateway는 같은 repo에서 계약을 맞추되 독립 프로세스/컨테이너 경계를 유지한다.
- Application API의 backend framework는 FastAPI를 사용한다.
- frontend framework 최종 선택은 보류한다. 개인 로컬 시스템의 단일 서비스 UI로 충분할 수 있으므로, standalone frontend가 필요해질 때 React 또는 Vue를 기본 후보로 검토한다.
- Worker는 Application과 코드·계약을 공유하되, 나중에 별도 entrypoint나 프로세스로 분리할 수 있게 느슨하게 연결한다.
- 초기 local/personal runtime에서는 외부 queue 제품을 전제하지 않고 단순한 in-process/background boundary로 시작한다. 더 강한 queue가 필요하다는 증거가 생기면 별도 결정으로 승격한다.

## 확정된 전역 계약

### 제품과 프로젝트 경계

- MVP는 계정/인증이 없는 단일 사용자 시스템이다.
- 그래도 모든 저장·검색·Gate·tool handler는 `project_id`를 강제한다.
- 향후 다중 사용자를 위해 `user_id`를 지금 억지로 넣지 않는다.
- Product Shell은 프로젝트/원고 작업 표면이며 AI 기억의 정본을 별도로 소유하지 않는다.

### Source of Truth

- MongoDB가 원문과 구조화 기억의 SOT다.
- 원문 snapshot은 primary SOT다.
- 원문 snapshot의 `raw_text`는 저장 후 변경하지 않는다.
- `source_ref` offset은 `raw_text` 기준 Unicode code point index로 계산한다.
- MVP `source_ref` span은 하나의 `source_block` 안에 포함되어야 한다. 여러 block을 가로지르는 인용은 후속 후보/review 계약에서 별도로 다룬다.
- `content_hash`는 `raw_text`의 UTF-8 bytes에 대한 SHA-256이다.
- `normalized_text_hash`는 v1 필수 계약이 아니다. 정규화 기반 dedupe/search가 필요해질 때 별도 계약으로 추가한다.
- MVP `source_blocks`는 deterministic source reference 단위다. Markdown heading, 명시 scene marker, paragraph boundary 기반으로 만들며 AI 추론으로 block을 나누지 않는다.
- 사용자가 승인한 설정은 canonical SOT다.
- 분석 결과는 저장되더라도 derived SOT이며 상태와 근거가 필요하다.
- ChromaDB와 Elasticsearch는 MongoDB로 재생성 가능한 파생 인덱스다.
- adaptive chunking, semantic chunking, 길이 기반 episode/section chunking은 검색 품질을 위한 파생 index 후보이며 MongoDB raw snapshot/source_ref 정본을 대체하지 않는다.
- 검색 hit는 MongoDB pointer/version/hash로 재조회하기 전까지 정본 사실이 아니다.
- draft save는 명시적 version save만 지원한다. autosave는 MVP 범위가 아니며, 필요성이 확인될 때 별도 사용자 결정으로만 추가한다.
- draft save request는 `idempotency_key`를 필수로 가진다. 같은 `project_id + draft_id + idempotency_key` 재시도는 같은 `draft_version`을 반환해야 한다.
- Mongo adapter는 required query indexes `uniq_save_request`(`project_id`, `draft_id`, `idempotency_key`, unique)와 `blocks_by_snapshot`(`snapshot_id`, `block_index`)를 설치해야 한다. MongoDB가 required index 생성을 거부하면 setup failure는 `MongoRepositorySetupError`로 표면화한다. 현재 `source_refs` 조회는 `_id` 기준이므로 by-snapshot source_ref index는 required contract가 아니다.
- Docker 기반 정상 runtime은 MongoDB transaction을 기본으로 사용한다. non-transaction fallback은 transaction을 사용할 수 없는 local/test 환경의 제한적 경로이며, write order, idempotency lookup, orphan cleanup/retry guard를 요구한다.
- non-transaction fallback은 **single-writer 전용**이다. 같은 `(project_id, draft_id, idempotency_key)`에 대한 동시 draft save는 fallback에서 보장하지 않으며(orphan cleanup이 동시 writer의 committed dependents를 지울 수 있음), 동시성 안전이 필요한 runtime은 transaction 기본 경로를 사용한다. fallback의 orphan cleanup/retry guard는 같은 writer의 순차 재시도에 대해서만 정의된다.
- project/draft 삭제는 MVP에서 archive로 처리한다. `source_snapshots`, `draft_versions`, `source_blocks`, `source_refs`는 보존한다.
- archive는 보존이자 **읽기 전용 상태**다. archived project/draft에 대해:
  - 읽기(project/draft get·list, version/snapshot/block 재조회)는 허용한다.
  - 본문 쓰기(draft 생성, version 저장)와 메타데이터 수정(project/draft rename)은 차단한다(409 Archived). project archive는 그 하위 draft 쓰기까지 차단한다.
  - SOT 본문(`source_snapshots`, `draft_versions`, `source_blocks`)은 archive 여부와 무관하게 생성 후 불변이다. 따라서 "archived 본문 수정"이라는 연산은 존재하지 않는다.
  - archive/unarchive 같은 상태 전이는 본 쓰기 차단의 대상이 아니다. 여기에는 archived project 하위 draft를 archive하는 것도 포함되므로(상태 전이), "하위 draft 쓰기 차단"의 예외로서 archived project에서도 허용한다. unarchive는 MVP 범위가 아니므로 본 계약은 "archived인 동안 차단"으로 한정하며 영구 불변을 규정하지 않는다.
  - `source_refs` 생성은 보존된 immutable snapshot에 대한 파생 주석이므로 archived 상태에서도 **허용한다**(사용자 결정). 이는 본문/메타데이터 쓰기 차단의 예외다.
- `create_source_ref` primitive는 non-idempotent다. 같은 span 재호출은 새 ref를 만들 수 있다. Phase 2A candidate/job 저장층이 같은 logical candidate retry 중복 방지 idempotency를 소유한다.
- Phase 2A candidate retry identity는 `project_id + task_id + logical_key`다. `logical_key`는 비어 있지 않은 문자열이어야 한다. schema/extraction slice의 기본 derivation은 `candidate_type + payload + source_anchors` canonical JSON의 SHA-256이며, 같은 provider retry payload는 같은 key가 되고 payload 또는 anchor set이 다른 관찰은 별도 candidate가 된다. `source_anchors`는 identity에서 unordered set으로 취급하므로 provider 출력 순서와 동일 anchor 중복은 같은 identity로 정규화한다. 순서 의미가 필요한 ordered evidence chain은 후속 schema에서 `sequence`/`evidence_order` 같은 명시 필드를 추가해 계약화한다.
- archive/delete 이후 파생 인덱스는 stale 처리, version filter, rebuild 대상으로 다루며 MongoDB 정본 보존을 되돌리지 않는다.
- 분석 후보의 부분 승인, 부분 저장, 나머지 retry는 Phase 2/6 review action idempotency 계약에서 다룬다. Slice 1 draft save idempotency와 섞지 않는다.

### Candidate 원칙

- 모든 AI 출력은 candidate다.
- Writing AI 출력은 `draft_candidate`다.
- Analysis AI 출력은 `analysis_candidate`다.
- Agentic Search 출력은 `context_candidate`다.
- candidate는 Gate 또는 사용자 승인 없이 canonical 상태가 되지 않는다.
- 후보 상태와 loop 종료 decision은 다른 층위다. 예: Analysis candidate `needs_review`와 Loop decision `awaiting_review`는 같은 뜻이 아니다.

### 추적성

- 구조화 기억에는 `project_id`, 상태, version, `source_ref`가 필요하다.
- `source_ref`는 snapshot/block/span/quote/hash로 원문을 다시 찾을 수 있어야 한다.
- 검색 결과와 ContextPackage 항목은 MongoDB pointer로 SOT를 다시 읽고 version/hash를 확인해야 한다.
- trace에는 provider error detail, loop decision, tool call, Gate finding의 원인을 보존한다.

## 서비스별 계약 SoT

### LLM Gateway

정본 세부 문서: [`plans/llm-gateway.md`](plans/llm-gateway.md)

확정된 구현 계약:

- Gateway는 같은 repo에 두되 독립 프로세스/컨테이너로 실행한다.
- Application은 모델 파일 경로, CUDA 설정, inference engine 세부를 알지 않는다.
- Gateway는 MongoDB/ChromaDB/Elasticsearch에 접근하지 않는다.
- Gateway는 domain tool registry나 AgentLoopRunner terminal decision을 소유하지 않는다.
- 현재 provider error literal은 다음 5종이다.

```text
provider_unavailable
provider_timeout
provider_overloaded
provider_invalid_response
provider_request_rejected
```

- HTTP/text completion 성공 응답은 `model`, 첫 choice `message.content`, `finish_reason`, `usage.prompt_tokens`, `usage.completion_tokens`를 모두 유효값으로 가져야 한다.
- `usage` 또는 token count 누락/invalid는 0으로 보정하지 않고 `provider_invalid_response`다.
- 명시적 token count 0은 유효하다.
- `HttpxJsonTransport`는 `trust_env=false`가 기본이며, proxy는 필요할 때만 opt-in한다.
- 실제 tool-call parsing은 아직 미구현이다.

검증 근거:

- Slice 0.1~0.6 unit/contract 회귀
- [`verifications/2026-06-24/llm_gateway_f1_f2_closure.md`](verifications/2026-06-24/llm_gateway_f1_f2_closure.md)
- [`verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md`](verifications/2026-06-24/llm_gateway_slice_0_6_httpx.md)

### AgentLoopRunner

정본 세부 문서: [`plans/flat-loop-gate.md`](plans/flat-loop-gate.md)

확정된 구현 계약:

- Loop는 Application/Worker 소유다.
- sub-agent spawn, delegate tool, nested AgentLoopRunner 호출, 임의 code/shell tool은 지원하지 않는다.
- 한 run은 정확히 하나의 terminal decision으로 종료한다.

```text
completed
awaiting_review
blocked
budget_exhausted
invalid_tool_arguments
tool_error
provider_error
```

- Gateway의 5 provider literal은 Loop decision으로 승격하지 않고 `provider_error` trace detail로 보존한다.
- domain Gate 결과와 Loop decision은 직교한다.
- `completed`는 loop 종료 상태일 뿐 domain Gate 통과가 아니다.
- `budget_exhausted`는 성공이 아니다.
- provider 응답 content는 JSON object이며 loop 종료 채널은 top-level `self_report` field다.
- `self_report` 허용값은 정확히 `finalize` 또는 `defer`다. 누락·오타·대소문자 변형·non-string·산출물 내부 nested `self_report`는 provider output 오류다.

Budget 계약:

- 필수 차원은 `max_iterations`, `max_wall_clock_ms`, `max_total_tokens`, `max_tool_calls`, `max_repeated_calls`다.
- `max_iterations`, `max_wall_clock_ms`, `max_total_tokens`는 1 이상이다.
- tool 사용 profile의 `max_tool_calls`, `max_repeated_calls`는 1 이상이다.
- tool 없는 `writing_generate`는 tool budget 2종을 0으로 둔다.
- token은 post-accounting 차원이다. 누적 `== limit`은 완료 가능, `> limit`은 `budget_exhausted`다.
- retry는 free path가 아니며 기존 budget을 소비한다.

Tool registry 계약:

- v1 public tool literal은 6종이다.

```text
search_memory
load_memory
load_snapshot
compare_memory
validate_candidate
validate_context
```

- `analysis_compare` allowlist: `search_memory`, `load_memory`, `load_snapshot`, `compare_memory`, `validate_candidate`
- `context_search` allowlist: `search_memory`, `load_memory`, `validate_context`
- `writing_generate` allowlist: 없음
- 모델 arguments는 `project_id`, task/trace identity, deadline을 소유할 수 없다.
- raw arguments는 JSON으로 정확히 한 번 parse한다. parse 실패를 `{}`로 바꾸지 않는다.
- A2 validator 범위는 `required`, type, `additionalProperties: false`, array `items`다.
- `enum`/bounds(`minimum`/`maximum`)는 이 keyword를 선언하는 tool schema가 처음 등록될 때 검증과 양방향 회귀를 추가한다. 그전까지 명시적 deferral이다.
- valid tool call signature는 `tool name + canonical JSON arguments`다. canonical JSON은 key sort와 JSON type/value 보존을 사용한다.

검증 근거:

- [`verifications/2026-06-24/agent_loop_a1_decision_budget.md`](verifications/2026-06-24/agent_loop_a1_decision_budget.md)
- [`verifications/2026-06-25/agent_loop_a2_registry.md`](verifications/2026-06-25/agent_loop_a2_registry.md)
- [`verifications/2026-06-25/agent_loop_a3_completion_resolution.md`](verifications/2026-06-25/agent_loop_a3_completion_resolution.md)
- [`verifications/2026-06-25/self_report_parser.md`](verifications/2026-06-25/self_report_parser.md)
- [`verifications/2026-06-25/agent_loop_provider_runner.md`](verifications/2026-06-25/agent_loop_provider_runner.md)

## Gate 합성 계약

Loop Gate, Analysis Gate, Context Gate, Writing Gate는 같은 decision으로 합치지 않는다.

| Gate | 질문 | 대표 결과 |
|---|---|---|
| Loop Gate | loop run이 왜 끝났나 | terminal decision 7종 |
| Analysis Gate | 분석 후보를 어떻게 처분할까 | `create/update/add_evidence/no_change/conflict` 및 job 상태 |
| Context Gate | package를 AI에 전달해도 되나 | project/SOT/pointer/version/stale/budget 검사 |
| Writing Gate | writing candidate를 editor에 제안해도 되나 | hard constraint/POV/continuity/finding |

합성 순서:

```text
AgentLoopRunner terminal decision
→ 산출물 존재 시 domain Gate 실행
→ Gate finding과 후보 상태 저장
→ 사용자 검토 또는 후속 service action
```

Loop decision이 `completed`여도 domain Gate가 reject할 수 있다. 반대로 domain candidate가 `needs_review` 상태여도 loop는 완결된 산출을 제출했다면 `completed`일 수 있다.

## Phase 계약 인덱스

### Product Shell

정본 세부 문서: [`plans/product-shell.md`](plans/product-shell.md)

- 단일 사용자 제품 표면이다.
- 프로젝트 CRUD, 원고 작업 공간, 처리 상태, 내보내기를 제공한다.
- 첫 export 형식은 plain text와 Markdown으로 확정했다(v1.6.14). DOCX/PDF/EPUB은 후속 검토다.
- 보관/삭제 정책, draft/chapter/scene 계층은 미확정이다.

### Phase 1. Core SOT

정본 세부 문서: [`plans/01-core-sot.md`](plans/01-core-sot.md)

- `projects`, `drafts`, `draft_versions`, `source_snapshots`, `source_blocks`, `source_refs` 계약을 만든다.
- snapshot은 생성 후 수정하지 않는다.
- text/reference와 persistence/retention 계약은 v1.2~v1.3에서 승인됐다.
- Application API는 `GET /projects/{project_id}/drafts/{draft_id}/versions/{version_id}/export?format=txt|markdown`으로 선택한 draft version을 내보낸다. export `body`는 그 version snapshot의 `raw_text`를 verbatim으로 내보내며 AI 분석 metadata를 본문에 주입하지 않고 Markdown을 합성·제거하지 않는다(두 형식 body 동일). `format`은 `content_type`(`text/plain`/`text/markdown`)과 filename 확장자(`.txt`/`.md`)만 가른다. payload는 `version_id`/`version_number`/`snapshot_id`/`content_hash` 추적 필드를 포함한다. 지원하지 않는 format은 400, missing/cross-project version은 404다. archive는 read를 막지 않으므로 export는 archived에서도 가능하다.

### Phase 2. Analysis Pipeline

정본 세부 문서: [`plans/02-analysis-pipeline.md`](plans/02-analysis-pipeline.md)

- Phase 2A는 prior memory 없이 snapshot 근거 기반 후보를 만든다.
- Phase 2A 최소 taxonomy는 `character_observation`, `event_observation`, `open_question_observation` 3종으로 시작하며 후속 확장을 막지 않는 구조로 구현한다.
- Phase 2A provenance literal은 `source_observed`와 `ai_inferred`만 허용한다. `user_declared`는 WritingBrief/Product Shell 입력 계약 이후로 미룬다.
- Phase 2A candidate action은 `create` only이고 status는 `needs_review`로 고정한다.
- Phase 2A confidence는 `0.0 <= confidence <= 1.0`만 강제하고 자동 reject threshold는 후속 품질 fixture 이후 결정한다. NaN은 이 범위 밖이므로 거절한다.
- Phase 2A source validation은 `CandidateSourceAnchor(source_ref_id, start_offset, end_offset, quote, content_hash)`를 같은 project의 Core SOT `SourceRef`와 대조한다. source_ref가 없거나 다른 project에 속하거나 span/quote/hash가 다르면 candidate 저장을 거절한다.
- Phase 2A Snapshot Loader는 같은 project의 Core SOT snapshot raw text, content hash, source block ids를 analysis 입력으로 로드한다. 다른 project의 snapshot은 찾을 수 없는 것으로 처리한다.
- Phase 2A 최소 payload schema는 `character_observation {name, observation}`, `event_observation {event}`, `open_question_observation {question}`이다. 모든 payload field는 non-empty string이며 추가 field와 누락 field는 malformed payload로 거절한다.
- Phase 2A fake-provider extraction adapter는 provider content를 top-level `{candidates: [...]}` JSON object로 파싱하고, 각 candidate의 approved type/provenance/confidence/source_anchors/payload를 검증한 뒤 candidate draft를 만든다.
- Phase 2A extraction runner는 source validation이 구성된 `AnalysisService`만 받는다. Runner는 `AnalysisJob`을 `project_id + snapshot_id + idempotency_key`로 idempotent 생성/재사용하고, Snapshot Loader → provider extraction → `AnalysisTask` 생성/재사용 → 전체 draft 사전 검증 → candidate 저장 순서로 실행한다. Task는 `project_id + job_id + candidate_type`으로 재사용한다. 한 run의 candidate write는 모든 draft가 logical_key/source/schema 검증을 통과한 뒤 시작한다. 같은 run의 duplicate `(task_id, logical_key)` draft는 1개로 정규화한다. Job 상태 전이와 실패 상태 저장 계약은 아래 job-state 조항(v1.6.9)에서 정의했으며 구현은 job-state slice다.
- Phase 2A service batch API는 같은 batch 안의 동일 `project_id + task_id + logical_key` candidate request를 idempotent replay로 정규화한다. 첫 request는 candidate를 만들고 이후 동일 request는 같은 candidate를 반환한다. 같은 batch 안에서도 logical_key가 다르면 별도 candidate로 유지한다.
- Phase 2A Mongo persistence는 `analysis_jobs`, `analysis_tasks`, `analysis_candidates`를 저장한다. Required idempotency indexes는 `uniq_analysis_job_request`(`project_id`, `snapshot_id`, `idempotency_key`, unique), `uniq_analysis_task_request`(`project_id`, `job_id`, `candidate_type`, unique), `uniq_analysis_candidate_request`(`project_id`, `task_id`, `logical_key`, unique)다. Candidate list query는 `analysis_candidates_by_job`(`project_id`, `job_id`) index를 사용한다. MongoDB가 required index 생성을 거부하면 setup failure는 `MongoAnalysisRepositorySetupError`로 표면화한다.
- Phase 2A candidate batch write는 transaction 경로에서 한 트랜잭션으로 commit한다. Non-transaction fallback은 Core SOT fallback과 같이 **single-writer local/test 전용**이며, 실패하면 이번 시도에서 새로 쓴 candidate `_id`만 삭제해 candidate 부분 저장을 남기지 않는다. 동시성 안전이 필요한 runtime은 transaction 경로를 사용한다.
- Phase 2A candidate write의 duplicate 충돌만 stable `DuplicateAnalysisCandidateRequest`로 표면화한다. `insert_many`가 unique index를 위반하면 pymongo는 duplicate-key code `11000`을 담은 `BulkWriteError`를 던지므로 양 경로(transaction/fallback)는 이를 `DuplicateAnalysisCandidateRequest`로 매핑한다. duplicate가 아닌 다른 `BulkWriteError`/`PyMongoError`(예: document validation, write concern)는 원본 예외 타입을 보존해 인프라 오류가 duplicate request로 오표기되지 않게 한다. fallback은 매핑 여부와 무관하게 이번 시도 candidate `_id`를 먼저 정리한다.
- Phase 2A job 상태는 `AnalysisJob`에만 둔다. `AnalysisTask`는 status가 없다(candidate_type 파티션이며 독립 lifecycle 없음). job 상태는 `pending`(생성, 미실행) → `running`(추출/검증/저장 진행) → `succeeded`(이번 run candidate 모두 저장) | `failed`(실패, candidate 미저장)다. 허용 전이는 `pending→running`, `running→succeeded`, `running→failed`뿐이고 그 외는 `InvalidJobStateTransition`이다. terminal 상태(`succeeded`/`failed`)는 불변이다.
- Phase 2A runner는 새로 생성한 job(`pending`)일 때만 추출을 실행한다. `find_job_request`가 기존 job(상태 무관)을 찾으면 idempotent replay로 그대로 반환하고 재실행하지 않는다. `failed`는 terminal이며 같은 snapshot 재분석은 새 `idempotency_key`(새 job)로 한다. crash 등으로 비terminal에 멈춘 stale job의 자동 복구/재개는 MVP 범위 밖이다.
- Phase 2A `failed` job은 닫힌 `failure_reason` enum과 free-text `failure_detail`을 저장한다. `failure_reason`은 `snapshot_not_found`(snapshot 로드 실패), `source_invalid`(source_ref/anchor 검증 실패), `schema_invalid`(payload/logical_key/provider content malformed), `provider_error`(provider extraction 호출 실패, Gateway `provider_error` umbrella와 정렬), `duplicate_conflict`(candidate 저장 `DuplicateAnalysisCandidateRequest`)다. `succeeded`/비terminal 상태에서는 `failure_reason`/`failure_detail`이 비어 있어야 한다. 실패는 성공으로 위장하지 않으며 candidate를 저장하지 않는다. all-or-nothing은 candidate write에 한정되고, job/task 생성은 idempotent setup이라 실패 후에도 남을 수 있다(롤백 대상 아님).
- Phase 2A Application API는 `POST /projects/{project_id}/analysis/jobs`로 job을 `project_id + snapshot_id + idempotency_key` 기준 idempotent 생성/replay하고, `GET /projects/{project_id}/analysis/jobs/{job_id}`로 job 상태를 읽고, `GET /projects/{project_id}/analysis/jobs/{job_id}/candidates`로 저장된 candidate를 읽는다. 존재하지 않는 project 또는 다른 project의 job/candidate 접근은 404로 처리한다.
- Phase 2A Application API는 `POST /projects/{project_id}/analysis/jobs/{job_id}/run`으로 기존 job 실행을 시작할 수 있다. 이 endpoint는 `pending` job만 실행하며, runner dependency를 주입받아 요청 안에서 async runner를 await한다. `running`/`succeeded`/`failed` job은 재실행하지 않고 현재 job과 저장된 candidate를 `idempotent_replay=true`로 반환한다. pending job에서 runner가 구성되지 않았으면 503이다. 실패 HTTP mapping은 `snapshot_not_found` 404, `schema_invalid`/`source_invalid` 계열 400, `duplicate_conflict` 409, provider/기타 실행 오류 502다. 실패 job은 이후 `GET`으로 조회 가능해야 한다. source_ref 자동 생성과 Gateway runtime wiring은 이 endpoint 범위가 아니다.
- Phase 2A Application API는 `POST /projects/{project_id}/snapshots/{snapshot_id}/source-refs`로 source_ref catalog 항목을 생성하고, `GET /projects/{project_id}/snapshots/{snapshot_id}/source-refs`로 snapshot catalog를 source order로 조회하며, `GET /projects/{project_id}/source-refs/{source_ref_id}`로 단일 ref를 조회한다. create request는 `start_offset`, `end_offset`만 받으며 Core SOT가 quote/block/content_hash를 snapshot에서 계산한다. invalid span은 400, missing/cross-project snapshot/ref는 404다. source_ref는 immutable snapshot의 파생 주석이므로 archived project에서도 생성·조회가 허용된다.
- Phase 2A 실제 provider wiring 첫 slice는 tool-call 없는 terminal JSON extraction으로 진행한다. source_ref 후보는 Application/Worker가 static/mechanical anchor catalog로 준비하고, 모델은 새 source_ref를 생성하지 않고 입력 catalog의 `source_ref_id`만 선택한다. Core SOT는 `project_id + snapshot_id`로 source_ref catalog를 source order로 읽는 surface를 제공하며, Mongo required index는 `source_refs_by_project_snapshot`이다. Prompt template은 DB에 저장해 versioned 관리하며, `prompt_templates` 저장소는 `task_type + version` unique contract를 가진다. 첫 prompt version literal은 `analysis_extract_v1`, task_type은 `analysis_extract`다. Prompt builder는 snapshot metadata/raw_text와 source_ref catalog를 Gateway `ChatCompletionRequest`로 조립한다. Application runtime은 `LLM_GATEWAY_BASE_URL`이 설정된 경우 `/v1/generate` 기반 provider adapter와 versioned prompt extractor로 기본 analysis runner를 구성한다. env가 없으면 기존처럼 pending `run`은 runner 미구성 503이다. `{"candidates":[]}`는 유효한 빈 extraction 결과다.
- Phase 2A versioned provider extraction은 strict parser를 기본으로 유지한다. 첫 provider content가 malformed JSON, markdown-fenced JSON, 또는 candidate schema mismatch로 실패하면 Application adapter가 원문 output, parser error, 원래 prompt payload를 포함한 repair prompt를 같은 provider에 1회만 재호출한다. 첫 provider content가 JSON/schema는 통과했지만 `source_ref_id`, span, quote, content_hash가 입력 source_ref catalog와 정확히 일치하지 않는 경우도 같은 1회 repair 대상이다. repair output도 top-level `{candidates:[...]}` JSON object와 Phase 2A candidate/source schema를 통과해야 한다. repair 실패 또는 output truncation은 성공으로 보정하지 않고 기존 runner failure mapping에 따라 보존한다. repair 후에도 source_ref catalog mismatch가 남으면 기존 source validation 경계가 `source_invalid`로 실패를 보존한다.
- Phase 2A와 2B는 별도 milestone이다.
- Phase 2B는 Phase 3~4 이후 prior memory를 검색해 `create/update/add_evidence/no_change/conflict` 후보를 만든다(action literal + `merge/split` review-only는 v1.6.39 D4로 확정).
- Analysis AI는 canon을 확정하지 않고 기존 기억을 직접 덮어쓰지 않는다. v1.6.39 D2=B로 자동 승격을 도입하되 **AI가 아니라 결정적 시스템 threshold gate**가 승격하므로 이 경계는 유지된다.
- v1.6.39로 착수 결정 확정: 첫 sub-slice(2B.1)는 canonical memory store(`MemoryEntry`) + candidate 승격(D1=A). 자동 승격은 confidence threshold gate(threshold 이상 자동 `canonical`, 미만 `needs_review`+수동), threshold는 fixture/benchmark 근거·그 전까지 보수적 주입 설정값(D2=B). entity resolution은 결정적 key만(D3=A). taxonomy는 2A 3종 유지(D5=A). **미확정으로 남은 것**: 자동 승격 threshold 실제 수치(품질 fixture 후), ⑤ Writing canonical 포함(후속), compare judge live smoke 실행(sandbox 밖)·판정 경계 심화 fixture, memory→vector 재색인(2B.5), event/open_question 의미적 resolution, 중간 status(`confirmed`)·taxonomy 확장, conflict/merge/split review queue 영속화. (⑧ `scope`는 v1.6.42, compare judge adapter+prompt는 v1.6.43, versioned upsert 실쓰기는 v1.6.44로 닫힘.)
- v1.6.40으로 2B.1이 구현됐다(`services/application/app/memory/`). `MemoryEntry`(status `canonical` 단일 literal)는 승격된 candidate의 payload/provenance/source_ref_ids/confidence를 보존하고 `version=1` + 감사 필드(analysis_job_id/source_candidate_id/promotion_mode/applied_threshold)를 가진다. 수동 승격(`manual`)은 confidence 무관 항상 canonical, 결정적 threshold gate(`auto_threshold`)는 `threshold is not None and confidence >= threshold`만 승격하고 미만은 candidate `needs_review` 유지. threshold는 `MEMORY_AUTO_PROMOTION_THRESHOLD` 주입값·기본 `None`(off). 승격 idempotency는 `(project_id, source_candidate_id)` unique index. HTTP는 candidate promote/job auto-promote/memory 조회. job auto-promote 응답의 `promoted[]`는 **이번 호출에서 신규 승격된 memory만** 담는다(같은 job 재호출은 idempotent replay라 재보고하지 않으며 저장 memory 수는 불변). **2B.1 경계**: D3 scope key 매칭·충돌 해소(같은 entity 중복 canonical의 update/merge)는 compare(2B.3)에 위임하고 2B.1 유일성은 source_candidate_id로만 잡는다(create-only/version=1). 이 slice 경계는 오너 확인 대상이다.
- v1.6.41로 2B.2가 구현됐다(`services/application/app/context_search/prior_memory.py`). prior-memory 검색+패키징 slice로 판정(2B.3)은 켜지 않는다(D1=A). 신설 literal `ContextSearchPurpose.ANALYSIS_CONTEXT`/`ContextNeed.PRIOR_MEMORY`. `DeterministicPriorMemoryBackend`가 같은 project·같은 `memory_type`의 canonical `MemoryEntry`를 결정적 조회하고(`PriorMemoryBackend` 주입 seam=후속 semantic 검색 교체점, D2=A), `AnalysisContextService`가 `ContextPackage`(purpose=analysis_context, `prior_memories`=`PriorMemoryItem[]`, macro/micro/trace 비움)로 묶는다. `PriorMemoryItem`은 taxonomy 5필수(value=payload/status/source_ref_ids/version/match_reason)를 담고 scope는 미포함(2B.3, §8 ⑧ 추적 유지). 진입면은 job-aware(HTTP `POST /projects/{id}/analysis/jobs/{job_id}/context`가 job candidate types→coarse memory_type 집합 유도, D4=B), 빈 memory_types=빈 package. F4 self-exclusion(`exclude_job_id`=그 job)은 오너 승인 잠정값(2B.3 관찰 후 확정). Gate는 purpose 분기(`evaluate_analysis_context_gate`): candidate 금지 무적용, Writing item 누출만 차단, cross-project는 조회 격리가 보장(D5=A/F5). `/context-search`는 Writing 전용으로 `analysis_context` purpose를 400 거절.
- v1.6.42로 2B.3(compare→action proposal + D3 scope key)이 구현됐다. `memory/scope.py`의 `derive_scope`가 character만 결정적 `MemoryScope(character, 정규화 name)`을 내고 event/open_question은 None(D2=A). `MemoryEntry.scope`·`PriorMemoryItem.scope` 추가(승격 시 산출, §8 ⑧ 완전 완성, D5=A). `analysis/compare.py`의 `AnalysisCompareService`가 결정적 scope 매칭으로 후보를 좁혀 매칭 없음→`create`, 1개→주입 `CompareJudge`(터미널 JSON seam, D1=A)가 update/add_evidence/no_change/conflict 라벨(judge의 `create` 반환은 거절), 복수 canonical 동일 identity→결정적 `conflict`(2B.1 중복 canonical 경계 표면화). D6 self-exclusion(같은 job 승격분 제외) 확정. proposal only(D4=A, 쓰기는 2B.4). HTTP `POST .../jobs/{job_id}/compare`(D7=A, 매칭인데 judge 미구성 503).
- v1.6.43로 2B.3.2(실제 Gateway 터미널-JSON compare judge)가 구현됐다. `analysis/compare_judge.py`의 `TerminalJsonCompareJudge`가 versioned prompt `analysis_compare_v1`로 매칭 pair를 Gateway `/v1/generate` 1-turn에 보내 `{action, rationale}` JSON을 strict parse(+1회 repair, 실패 `InvalidJudgeResult`→502)한다. matched-pair 4종만 허용하고 `create`는 judge 출력에서 거절. `create_app`은 `_default_compare_service`로 env `LLM_GATEWAY_BASE_URL` 있을 때 wiring, 없으면 종전 503. live smoke는 `scripts/phase2b3_compare_judge_live_smoke.py`(sandbox 밖). 판정 경계 fixture 심화·live 실행은 후속.

### Phase 3. Indexing

정본 세부 문서: [`plans/03-indexing.md`](plans/03-indexing.md)

- ChromaDB와 Elasticsearch는 MongoDB pointer/version/status를 가진 파생 인덱스다.
- index hit는 SOT 재조회 전까지 정본이 아니다.
- Phase 3A 첫 slice는 Core SOT source block only를 Chroma-like vector contract에 색인한다. `IndexPointer`는 `project_id`, Mongo collection/document id, version id, content hash를 가진다. `IndexSyncRequest(project_id, snapshot_id, target)`와 `IndexSyncResult(request, records_attempted, records_written)`는 explicit rebuild용 in-process 축소 계약이다. `contracts.md` §7.3의 persistent sync log/outbox envelope(`sync_result_id`, `sync_request_id`, target별 결과, timestamps)는 후속 sync log slice 전까지 구현 대상이 아니다. Embedding은 deterministic fake provider만 사용하고 실제 embedding model/dimension은 후속 quality spike 뒤 확정한다. Sync delivery는 explicit snapshot rebuild only이며 자동 outbox/polling은 후속이다. Archive/delete 반영은 hard delete가 아니라 explicit rebuild가 materialize한 `project_archived`/`draft_archived` metadata status filter로 query 결과에서 제외한다. Archive 이후 기존 stale record를 즉시 숨기려면 재build 또는 후속 automatic sync가 필요하다. Adapter failure는 MongoDB/Core SOT 저장 결과를 rollback하지 않는다.
- Phase 3A source-block hit는 `validate_source_block_record(record)`로 Core SOT 정본을 재조회해 사용 가능 여부를 확인할 수 있다. Stale reason literal은 `project_archived`, `draft_archived`, `snapshot_missing`, `draft_mismatch`, `content_hash_mismatch`, `block_missing`이다. `snapshot_missing`은 snapshot을 조회할 수 없어 다른 stale check를 진행할 정본이 없으므로 단독 reason으로 short-circuit한다. `draft_archived`는 조회된 snapshot의 현재 owning draft 상태 기준이며, record의 stale `draft_id`가 다르면 별도로 `draft_mismatch`도 반환한다. Drift 판정은 `version_id` 비교가 아니라 snapshot `content_hash`, draft pointer, block pointer 정합성 기준이다. 이 검증은 기존 materialized vector record를 자동 삭제하거나 자동 숨김 처리하지 않으며, query/Context Gate 계층이 hit 사용 전 정본 상태를 확인하기 위한 explicit guard다.
- Phase 3A는 `scripts/phase3a_rebuild_source_block_index.py`로 explicit rebuild를 실행할 수 있다. 이 script는 `--project-id`, `--snapshot-id`, `CORE_SOT_MONGO_URI`/`--mongo-uri`를 받아 Core SOT MongoDB에서 snapshot blocks를 읽고 current fake vector adapter에 rebuild한 뒤 JSON summary를 출력한다. JSON summary field는 `project_id`, `snapshot_id`, `target`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`다. Exit code는 full write 성공 0, partial write(`records_attempted != records_written`) 1, usage/config/domain error(no Mongo URI, missing snapshot 등) 2다. Application HTTP API endpoint와 persistent vector backend는 후속이다.
- Phase 3A는 Application HTTP API `POST /projects/{project_id}/snapshots/{snapshot_id}/index/source-blocks/rebuild`로도 explicit rebuild를 실행할 수 있다. JSON summary field는 `project_id`, `snapshot_id`, `target`, `backend`, `records_attempted`, `records_written`, `records_indexed`, `records_query_visible`, `records_archived`다. missing/cross-project snapshot은 404다. v1.6.35부터 이 endpoint는 `create_app`이 소유한 공유 vector index에 write하고(같은 프로세스 context search가 read), summary count(`records_indexed`/`records_query_visible`/`records_archived`)는 해당 rebuild의 `snapshot_id`로 scope해 per-rebuild 의미를 유지한다(누적 없음). v1.6.36부터 `backend`는 wiring에 따라 `chroma`(env `CHROMA_HOST` 설정 시 real 영속 Chroma) 또는 `in_memory_fake`(미설정)다. automatic sync는 후속이다.
- Phase 3B archive outbox 첫 code slice가 구현됐다. Application archive endpoint는 `project_archived`/`draft_archived` event를 Core SOT archive 성공 후 `index_sync_outbox`에 pending entry로 남긴다. Dedup key는 `(project_id, event, source.mongo_collection, source.mongo_id)`라 재archive가 중복 outbox entry를 만들지 않는다. Entry는 nullable `user_id`, canonical `targets.chroma.status`, `targets.chroma.backend="in_memory_fake"`, `status="pending"`, `attempt_count=0`, `max_attempts=3`, `next_attempt_at=null`, `last_error=null`을 가진다. Outbox와 future log는 `sync_request_id`로 조인한다. `index_sync_outbox`는 `mongo_collections.md` 운영 collection 레지스트리에 등록됐다. 오류 타입은 서버/backend 계열 `backend_error`와 데이터 없음/not-found 계열 `not_found`를 분리한다. `analysis_completed`는 오너가 장기적으로 가장 맞는 흐름으로 본 후속 event candidate지만, 아직 code enum에는 열지 않는다.
- Phase 3B one-shot worker 첫 slice가 구현됐다. Worker는 `pending` 또는 10분 이상 지난 stale `running` outbox entry를 claim하고, archive mutation을 실행한 뒤 `index_sync_logs`에 attempt result를 append한다. Terminal-location/index 전략은 terminal 이동을 채택해 `success|failed`가 되면 active outbox entry를 제거하고 terminal history는 `index_sync_logs`가 소유한다. Archive worker-time `not_found`는 idempotent success다. Query-time `not_found`는 후속 LLM orchestration/query selector retry loop의 error type으로 남는다.
- v1.6.37부터 worker command는 `CHROMA_HOST` 설정 시 `ChromaArchiveIndexMutationAdapter`로 real Chroma를 mutate한다: archive event는 매칭 derived source-block record를 **delete**하고(`project_archived`=project 전체, `draft_archived`=project-scoped draft), 대상이 없으면 `DerivedIndexRecordNotFound`→idempotent success다. `CHROMA_HOST` 미설정 시 종전 recording-only fake로 폴백한다. worker summary JSON에 `archive_backend`(`chroma`/`in_memory_fake`)가 포함된다. 실제 Chroma 서버 관통 live smoke는 후속이다.
- ES analyzer, analysis candidate indexing, actual Elasticsearch mutation, `analysis_completed` sync wiring은 미확정이다. Chroma archive delete mutation은 v1.6.37로 구현됐다(worker→real Chroma).

### Phase 4. Agentic Search

정본 세부 문서: [`plans/04-agentic-search.md`](plans/04-agentic-search.md), [`plans/04-agentic-search-kickoff-decisions.md`](plans/04-agentic-search-kickoff-decisions.md)

- 목적에 맞는 ContextPackage 후보를 만든 뒤 Context Gate를 통과시킨다.
- 착수 브리프가 v1.6.30으로 승인됐고 Slice 4.1(domain 계약 + orchestration + Context Gate, planner 주입)이 v1.6.31로, Slice 4.2(터미널 JSON LLM planner adapter)가 v1.6.33으로, Slice 4.3(HTTP API `POST /projects/{id}/context-search` + service async wiring)이 v1.6.34로 구현됐다. 첫 slice literal: purpose `writing_context`, need `current_scene`/`recent_scenes`/`event_context`/`source_quote`. build_context_package는 async이고 Gate는 sync다. HTTP 오류 매핑: invalid 400 / wall-clock 504 / ContextSearchFailed 502 / missing project 404 / planner 미구성 503.
- v1.6.35로 공유 in-process vector index가 도입됐다. `create_app`이 단일 `InMemoryVectorIndexAdapter`(비durable, 재시작 시 소실)를 소유하고, source-block rebuild endpoint가 write하고 기본 wiring된 context search가 read해서 같은 프로세스의 rebuild → context search가 실제 vector hit(stale guard + SOT 재조회 통과)을 서빙한다. 공유 index는 `LLM_GATEWAY_BASE_URL` 유무와 무관하게 생성되고, planner 미구성 시 `/context-search`만 503이다. v1.6.36로 이 공유 vector 백엔드가 env 기반으로 real 영속 Chroma(`CHROMA_HOST` 설정 시 `ChromaVectorIndexAdapter`, 재시작 생존)와 real embedding(`EMBEDDING_SERVICE_URL` 설정 시 `RemoteEmbeddingProvider`, `dragonkue/BGE-m3-ko` 1024-dim)으로 승격 가능해졌고, 미설정 시 종전 fake로 폴백한다. embedding은 llama gateway와 분리된 컨테이너라 vector 백엔드는 LLM-독립이다. real ES lexical 경로는 계속 후속이다.
- planner는 터미널 JSON LLM planner다(1-turn SearchPlan JSON, strict parse + 1회 repair). `TerminalJsonSearchPlanner`가 versioned prompt template `context_search_plan_v1`(task_type `context_search_plan`)로 Gateway `/v1/generate`를 호출하고, enum literal(need/tool) 위반은 repair 1회 후 남으면 `llm_error`다. adapter는 literal 멤버십만 검증하고 plan 의미 검증은 service `_validate_plan`이 소유한다. provider가 async라 planner도 async이며 service 통합은 HTTP wiring slice로 미룬다. tool-call flat loop planner는 Gateway tool-call wire 계약 해소 후 전환한다(브리프 §2.1).
- `context_search` profile은 flat-loop allowlist 3종만 쓴다(전환 후 적용).
- tool success와 `validate_context` success는 Context Gate 통과가 아니다.
- retriever step 실패 error taxonomy는 `backend_error`/`system_error`/`llm_error`/`sot_error`로 시작하고 enum 확장 가능하다. `sot_error`(Mongo SOT reload 실패)는 degraded가 아니라 전체 실패이며, NotFound뿐 아니라 SOT reload 호출에서 탈출하는 모든 non-NotFound 예외(pymongo 장애 포함)를 원형 전파 없이 매핑한다(v1.6.32). vector hit의 snapshot NotFound만 index drift로 보고 `snapshot_missing` soft stale 제외한다. `system_error`는 예약 literal이다.
- package는 단일 schema + purpose literal로 시작한다. 이후 slice에서 Writing용/Analysis 비교용 모두 완성해야 하며(오너 추적 의무), analysis 비교용 필드는 Phase 2B 착수 브리프에서 결정한다. v1.6.38로 이 완성(⑤ candidate 포함 §5 B / ⑧ Analysis 비교용 §8 C)이 **Phase 2B에 종속됨**이 확정됐다(오너 결정 D1=B, `plans/04-context-package-completion-decisions.md`). Writing용 뷰는 현재 package로 Phase 5 MVP에 충분하고, candidate 포함은 canonical/승인 경로가 없어 지금 하지 않으며 `evaluate_context_gate`의 candidate 라벨 금지를 유지한다. v1.6.41로 ⑧ Analysis 비교용 뷰(`analysis_context` purpose + `prior_memory` need + `PriorMemoryItem` 5필수)가 구현됐고, **v1.6.42로 `PriorMemoryItem.scope`가 추가돼 ⑧이 완전 완성**됐다(memory type/scope/status/version/검색 이유). scope는 D2=A로 character만 결정적(name), event/open_question은 None이다. ⑤ candidate 포함은 여전히 후속이다.

### Phase 5. Writing AI

정본 세부 문서: [`plans/05-writing-ai.md`](plans/05-writing-ai.md)

- Writing AI는 DB/검색 tool에 직접 접근하지 않는다.
- MVP `writing_generate` profile은 tool 없음이다.
- 검증된 ContextPackage와 WritingBrief로 WritingCandidate를 만든다.
- 사용자가 accept하기 전에는 draft version이나 canon이 바뀌지 않는다.
- 출력 형식(full text/patch), Gate decision literal, 첫 task type은 미확정이다.

### Phase 6. Review UI

정본 세부 문서: [`plans/06-review-ui.md`](plans/06-review-ui.md)

- 사용자가 후보의 원문 근거, 기존 기억 diff, Gate finding을 보고 approve/reject/edit/defer 한다.
- 승인 전 candidate가 canonical UI나 검색 constraint로 위장되지 않는다.
- 승인 후 MongoDB가 먼저 갱신되고 인덱스는 그 결과를 따른다.
- 승인 결과가 `confirmed`인지 `canonical`인지, merge/split UI 범위는 미확정이다.

## 현재 구현 상태

| Slice | 상태 | 근거 |
|---|---|---|
| LLM Gateway 0.1~0.6 | 구현·검증 완료 | `services/llm_gateway/`, `tests/test_llm_*`, `test_httpx_transport.py` |
| AgentLoopRunner A1 | 구현·검증 완료 | `decision.py`, `budget.py`, A1 verification |
| AgentLoopRunner A2 | 구현·검증 완료 | `registry.py`, A2 verification |
| AgentLoopRunner A3 | 구현·독립 검증 합격(보강) | `completion.py`, `resolution.py`, budget F1 방어 + retry cap, `InvalidBudgetPolicy.decision` |
| AgentLoopRunner provider composition | 구현·독립 검증 합격(보강) | `parser.py`, `runner.py`, `test_agent_loop_runner.py`; I2 forward-lock(provider usage budget before completion, retry non-free), provider runner verification |
| AgentLoopRunner production budget defaults | benchmark 기반 확정 | `docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`, `plans/flat-loop-gate.md` |
| Core SOT minimal skeleton | 구현·조건부 검증 보강 완료 | `services/application/app/core_sot/`, `services/application/app/main.py`, `tests/test_core_sot.py`, `tests/test_application_api.py`; C1/C2/C3 보강 |
| Product Shell UI/Phase 2~6 | 미구현 | 계획 문서만 존재 |

## 다음 구현 경계

- agent_loop 계약층은 A1/A2/A3, self-report parser, provider composition까지 구현·독립 검증됐다.
- runner의 domain tool-call branch는 지금 구현하지 않는다. 선행 계약은 (1) Gateway tool-call response parsing, (2) model tool-call wire format, (3) Phase payload와 실제 tool handler다.
- `ProviderTurnResult`는 현재 terminal provider content와 usage만 표현한다. tool-call 수신 구조는 wire 계약이 생긴 뒤 확장한다.
- `artifact_present`는 현재 runner에 주입되는 결정 함수다. Slice 2A AnalysisCandidate, Slice 4 ContextPackage, Slice 5 WritingCandidate schema가 확정되면 profile별 구조 조건 평가로 교체한다.

## 미확정 결정 목록

다음 항목은 구현자가 임의로 채우지 않는다.

- frontend framework 최종 선택. standalone frontend가 필요해질 때 React 또는 Vue를 기본 후보로 검토한다.
- 외부 queue 제품 선택. 초기 local/personal runtime은 단순한 in-process/background boundary로 시작한다.
- Gateway/model tool-call response wire format
- `confirmed`와 `canonical`의 의미 및 승격 주체
- Phase 2/6 review action idempotency와 부분 승인/부분 retry 정책
- adaptive chunking 또는 길이 기반 episode/section chunking을 Phase 3 파생 index에 도입할지 여부
- Phase 2B taxonomy 확장과 confidence threshold
- Analysis `update/add_evidence/no_change/conflict`의 정확한 public envelope
- Chroma embedding model, ES analyzer, 자동 sync delivery 방식
- ContextPackage의 Analysis 비교용 확장 필드(단일 schema + purpose literal은 v1.6.30으로 확정, Writing용/Analysis 비교용 모두 완성은 추적 의무, 필드는 Phase 2B 착수 브리프에서 결정; v1.6.38로 ⑤ candidate 포함과 함께 Phase 2B 종속 확정 — D1=B; v1.6.41로 ⑧ `analysis_context`/`prior_memory` + `PriorMemoryItem` 5필수 구현; v1.6.42로 `PriorMemoryItem.scope` 추가로 ⑧ 완전 완성; ⑤ candidate 포함은 여전히 후속)
- WritingCandidate 출력 단위(full text/patch)
- Writing Gate decision literal과 editor 처리
- enum/bounds를 쓰는 첫 tool schema 등록 시 validator 확장 방식

## 변경 규칙

1. 계약 literal을 바꿀 때는 해당 테스트와 검증 기록을 함께 갱신한다.
2. spec과 구현이 충돌하면 둘 중 하나를 조용히 선택하지 않는다.
3. 미확정 항목을 구현해야 하면 사용자 결정 또는 좁은 spike로 먼저 계약을 만든다.
4. 문서-only 변경도 링크, 우선순위, status, 관련 HANDOFF를 확인한다.
5. 상세 구현 이력은 daily work log에 기록하고, 현재 actionable 상태만 `HANDOFF.md`에 남긴다.
