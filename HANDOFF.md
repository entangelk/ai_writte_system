# HANDOFF

> **다음 작업자를 위한 현재 상태 스냅샷.** 이력/일지가 아니라 **지금 사실이고 실행 가능한 것**만 둔다.
> 상세 이력은 `docs/daily_logs/`, 독립 검증은 `docs/verifications/`, 주요 마일스톤은 `CHANGELOG.md`.

## Current Status

- 정본 SoT는 `docs/system-contract-sot.md`이며 현재 **v1.6.64**(Approved). SoT가 정본 우선순위이고, 미확정 항목은 추측 구현하지 않는다.
- 개발 진입점은 `docs/plans/README.md`. `docs/` 루트의 설계 문서는 초기 아이디에이션 자료다.
- 구현된 계층(모두 회귀로 잠김, 아래는 현재 동작하는 표면):
  - **LLM Gateway**: FastAPI shell(`/health/live`·`/health/ready`·`/v1/generate`), llama.cpp 호환 provider + httpx async adapter, provider error 5종→HTTP status 매핑.
  - **Core SOT**: project/draft CRUD·version read/export(txt·markdown)·source_ref catalog HTTP API. pymongo(sync) adapter(transaction 기본 + single-writer fallback), idempotency는 unique index 강제.
  - **Agent loop 계약층**: decision 7종·budget 5차원·tool registry·self-report parser·completion 판정·minimal provider composition runner. (tool-call branch는 상류 의존으로 보류 — Active Decisions 참조.)
  - **Analysis(Phase 2A)**: taxonomy 3종 extraction, job 상태 전이, provider/Gateway wiring + JSON repair, job/candidate/run HTTP API.
  - **Memory(Phase 2B.1~2B.7)**: canonical `MemoryEntry` store + candidate 승격(수동/threshold), compare→ActionProposal→versioned upsert(append-only), compare judge(Gateway 1-turn), memory→vector 재색인(async outbox→worker), event/open_question semantic identity(off 기본), character alias 탐지(v1.6.62) + 동명이인 반증·사람 승인 merge/split(v1.6.63, threshold off 기본). conflict review queue(v1.6.59)와 resolve/dismiss(v1.6.61), Review Inbox 목록/상세(v1.6.64)까지 실경로화됐다.
  - **Indexing(Phase 3A/3B + b-2)**: source block index rebuild(HTTP/CLI/deployed smoke), index sync outbox + worker(archive drain + memory reindex drain + **candidate 색인 drain**; one-shot CLI + b-6 증분1 `--loop` compose 서비스). candidate 색인 파이프라인(v1.6.54): `record_candidate(s)` → `CANDIDATE_UPSERTED` outbox → worker composite(vector `candidate_vectors` + lexical ES `candidate_lexical`). candidate 상태 전이(v1.6.61)로 **de-index 실경로화**: `CANDIDATE_REMOVED` 이벤트 → worker `index_candidate` 재유도가 not-needs_review면 delete(색인 self-heal). **ES-lexical backfill(v1.6.58)**: `scripts/phase2b5_reindex_memory.py`(memory vector+lexical)·`scripts/phase2b5_reindex_candidate.py`(candidate vector+lexical) 일괄 backfill — b-6 증분2 accepted limitation #1 해소, outbox 우회 D7 자세, live 실행은 sandbox 밖.
  - **Context search(Phase 4)**: LLM planner + orchestration + Context Gate, HTTP API, 공유 in-process vector index, real Chroma+embedding 백엔드(env 구성 시), canonical memory 포함(⑤ §5 B) + `needs_review` candidate 포함(라벨·micro·권위필드 배제, Gate가 candidate origin만 예외 허용). **canonical·candidate memory retrieval 모두** env로 backend 선택(canonical v1.6.51/52, candidate v1.6.55): `CHROMA_HOST`+`EMBEDDING_SERVICE_URL` 시 **vector relevance**, `ELASTICSEARCH_URL` 시 **ES lexical(nori)**, 둘 다면 **hybrid(RRF)**, 없으면 Mongo-direct — 모두 권위는 Mongo/analysis store 재유도(seam·item·Gate 불변). worker memory/candidate drain은 ES 구성 시 vector+lexical composite. **canonical↔candidate 승격 dedup(v1.6.60)**: candidate_memory step이 승격된 candidate(memory store `find_memory_by_candidate` 링크 존재)를 억제 — `PromotedCandidateResolver` seam(`MemoryService.is_candidate_promoted`, 미주입 시 억제 없음=종전 D7), canonical이 같은 package에 있든 없든 store 권위로 판정(D1), `ExcludedHit reason="candidate_promoted"` trace. `source_candidate_id` identity dedup이라 라이브 불요. Phase 6 candidate de-index 도입 시 상위집합 흡수(forward-defense — v1.6.61로 실경로화).
  - **Review 상태 전이(Phase 6 백엔드, v1.6.61)**: candidate `needs_review→confirmed/rejected` 전이 백엔드 계약(브리프 `plans/06-candidate-state-transition-decisions.md`). 이전 slice들이 남긴 5개 forward-defense stub의 수렴점. **D1=분리 모델**(confirm=`needs_review→confirmed` + canonical promotion[`source_candidate_id`], reject=`needs_review→rejected` 무promotion, 보존[D5]). `AnalysisService.transition_candidate`(상태 머신·legal 2개만·cross-terminal/backward 거부·idempotent) + `analysis/candidate_review.py::CandidateReviewService`(confirm/reject 오케스트레이션: 전이+promote+de-index enqueue+queue 전이). de-index=`CANDIDATE_REMOVED`(D2, worker `index_candidate` 재유도가 not-needs_review면 delete). review_queue `open→resolved`(confirm)/`dismissed`(reject)(D3). idempotent 단건(D4). `POST /projects/{id}/analysis/candidates/{cid}/confirm|reject`(404/409). **미확정 유지(Phase 6 UI slice)**: source deep link·merge/split·부분 승인·Gate finding inbox 통합·frontend.
- **Compose 런타임**: base `docker-compose.yml`(application + Mongo replica set + gateway[외부 llama 클라이언트] + embedding + chroma + **elasticsearch**[nori, v1.6.53] + **worker**[b-6 증분1]). application에 `ELASTICSEARCH_URL` 배선 → 배포 canonical·candidate retriever 기본 = **hybrid(vector+lexical RRF)**. ES는 자체 `services/elasticsearch/Dockerfile`(공식 ES + analysis-nori, single-node·보안 off). opt-in `docker-compose.llama.yml`로 in-stack llama.cpp GPU 서버(port 9080)를 띄운다. runbook: `docs/runbooks/local-llama-server.md`. **worker(index 색인 적재 drain)는 상시 compose 서비스**(`--loop` drain + SIGTERM graceful shutdown, b-6 증분1 / SoT v1.6.56) — 이전 수동/out-of-band에서 전환. atomic outbox claim이 이미 이중 실행을 막아 single-replica로 안전. **outbox per-sink bookkeeping 완료**(b-6 증분2 / SoT v1.6.57, G3=B/G4=B): enqueue는 targets 빈 dict(sink-agnostic)로 두고 worker가 claim 시 configured sink(vector/lexical)를 materialize, 각 sink가 독립 `attempt_count`/`last_error`를 가져 한 sink가 죽어도 healthy sink는 SUCCESS로 동결·재색인되지 않고 all-terminal 시에만 entry 삭제. composite `drain(entry, skip=SUCCESS)`가 per-sink `SinkOutcome`을 반환(all-or-nothing raise 폐지). retriever는 인덱스 비어도 graceful.
- **테스트**: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **773 passed / 48 skipped / 99 subtests**(2026-07-12, v1.6.64 Review Inbox + 독립 감사 후속 2). skip은 대부분 live Mongo/Chroma/embedding 미가용 통합 테스트.

## Active Decisions

표준 제약(향후 작업을 구속하는 것)만 둔다. 완료 이력은 `CHANGELOG.md`, 근거는 각 `docs/plans/*-decisions.md` 브리프에 있다.

### 문서 · 프로세스
- 아이디에이션과 계획이 충돌하면 임의 구현 없이 사용자 결정을 받는다. 나중 요청이 기록된 결정·설계 방향과 충돌하면 어느 쪽이 canonical인지 먼저 확인한다.
- Phase를 계획의 주 축으로, MVP는 별도 축으로 관리한다. 원본 `docs/abstract.md`는 보존한다.

### 아키텍처
- monorepo + 독립 LLM Gateway/Worker, Application API backend = FastAPI. Worker는 Application 코드/계약을 공유하되 느슨히 결합하고 나중에 별도 entrypoint/process로 분리 가능하게 둔다.
- MVP는 계정/인증 없는 단일 사용자 시스템이며 프로젝트 경계는 `project_id`로 유지한다.
- frontend framework는 보류(필요해지면 React/Vue 후보). editor shell(frontend)은 현재 범위 밖.
- 초기 local runtime은 외부 queue 제품을 전제하지 않고 in-process/background boundary로 시작한다.
- Dockerfile/Compose는 dependency manifest 복사·설치 레이어를 소스 복사보다 앞에 두어 빌드 캐시를 보존한다.
- 외부 `/mnt/d/devel/gemma4_12b`는 선택적 provenance이며 현재 repo runtime dependency가 아니다. model/quant = 공식 QAT GGUF Q4_0.
- compose 기본 gateway는 `LLAMA_BASE_URL`(기본 `http://host.docker.internal:9080`)의 외부 llama.cpp 호환 endpoint를 호출한다. 계약은 `GET /health` + `POST /v1/chat/completions`(OpenAI 호환 + `chat_template_kwargs`)뿐이다.
- embedding 서비스는 gateway와 분리한다(LLM-독립). real vector = Chroma + `dragonkue/BGE-m3-ko`(1024-dim); `CHROMA_HOST`/`EMBEDDING_SERVICE_URL` 미구성 시 fake fallback.

### Core SOT 계약
- text/reference는 raw snapshot 기준: offset = raw Unicode code point, `content_hash` = raw UTF-8 SHA-256, `normalized_text_hash`는 v1 필수 아님. `source_blocks` = Markdown heading / 단독 `---`·`***` scene marker / 빈 줄 paragraph deterministic split이며 AI 추론 split은 넣지 않는다.
- `source_ref` span은 하나의 `source_block` 안에 포함된다(다중 block 인용은 후속).
- persistence: Docker 정상 runtime = MongoDB transaction 기본, non-transaction fallback = **single-writer local/test 전용**(동시성 안전은 transaction 경로 담당). 명시적 version save only(autosave 후속). draft save는 `idempotency_key` 필수이며 같은 `project_id+draft_id+idempotency_key` 재시도는 같은 `draft_version`을 반환한다.
- project/draft는 archive(soft delete)하고 snapshot/version/source_ref는 보존한다. archive = 읽기 허용 + 본문 쓰기·rename 차단(409). SOT 본문은 archive 무관 항상 불변이라 source_ref 생성은 archived에서도 허용된다.
- adaptive/semantic/length chunking은 Phase 3+ 파생 index 후보다. MongoDB raw snapshot 정본을 대체하지 않고 pointer/version/hash로 재조회 가능해야 한다.

### Agent loop / flat loop (계약층 — 현재 더 진행하지 않음)
- sub-agent spawn은 제외하고 bounded flat loop만 사용한다.
- 종료 decision 7종: `completed`/`awaiting_review`/`blocked`/`budget_exhausted`/`invalid_tool_arguments`/`tool_error`/`provider_error`. self-report wire = provider 응답 JSON top-level `self_report` = 정확히 `finalize`|`defer`(nested는 종료채널 아님).
- registry = Application/Worker 소유, task별 서버 allowlist, strict JSON Schema. v1 validator 범위 = `{required, type, additionalProperties, array items}`; enum/bounds는 해당 keyword를 쓰는 tool 첫 등록 시점까지 deferred. read-only v1 tool 6종. `project_id`는 신뢰된 실행 context에서 주입(모델 인자 아님).
- allowlist: `analysis_compare` 5 tool, `context_search` 3 tool, `writing_generate` no tool.
- budget 5차원(iteration/wall-clock/total-token/tool-call/repeated-call), retry도 같은 budget을 소비하며 초과를 성공으로 위장하지 않는다. production 기본값은 Gemma Q4 benchmark(`docs/benchmarks/2026-06-30/gemma_q4_llama_cpp_repeats3_warmup1.json`) 근거: `analysis_compare` 2/45s/1024/5/repeat2/retry1+1, `context_search` 3/60s/1536/8/repeat2/retry1+1, `writing_generate` 1/120s/1024/no tool/retry1. 모델·quant·prompt·tool latency가 바뀌면 benchmark를 다시 만들어 재확정.
- completion 판정 = 하이브리드(구조 조건 AND self-report). 종료채널(finalize/defer) ⟂ candidate status(산출물 데이터 채널).
- **보류 사유**: tool-call branch는 (1) Gateway tool-call parsing 미구현, (2) model tool-call wire format 미계약, (3) `ProviderTurnResult`가 terminal content만 받는 구조 — 3중 상류 의존이 해소돼야 착수한다. `artifact_present`도 task별 payload schema 확정 시 profile별로 교체한다.

### Analysis / Memory (Phase 2·2B)
- taxonomy 3종(`character_observation`/`event_observation`/`open_question_observation`), provenance `source_observed`/`ai_inferred`, confidence range 강제.
- 기억 갱신은 AI가 직접 덮어쓰지 않고 검색·대조·Gate·검토·versioned upsert를 거친다. memory는 append-only(version마다 새 id, 이전 id는 `superseded`).
- canonical memory는 별도 `memory_vectors` collection(`IndexRecordKind.MEMORY`)에 **canonical-only**로 색인한다. 트리거 = async outbox→worker(2B.5 D3=B). commit-후-enqueue skew는 정기 memory backfill이 유일 수렴 수단이다. enqueue는 `MemoryService` choke point로 중앙화(promote/versioned upsert 3경로를 한 번에 커버).
- event/open_question semantic identity는 compare `_find_matches`에서 처리한다(2B.6 D1=A). semantic 매칭은 **off 기본**(D4=A): `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 미설정 시 always-create 보존, 실 embedding 캘리브레이션 후 발화. character는 결정적 name-key가 **1차**이며, **별칭 semantic 보강은 v1.6.62로 추가**(브리프 `plans/02b-7-character-alias-homonym-decisions.md`, D1=A 탐지만·D2=A 별칭만): name-key 매칭 0일 때만 alias matcher(2B.6 `EmbeddingSemanticMatcher` 재사용, 별도 env·off 기본)로 다른 이름 canonical과의 의미적 근접을 조회 → 히트 시 `conflict`(review, 자동 병합 없음 — 2B.3 D2=A "자동 병합 없음" 존중). name-key≥1은 종전 judge 경로 불변. 동명이인 false-positive 반증(name-key=1 분기)·threshold 실 캘리브레이션·merge/split write는 후속.
- Writing ContextPackage의 memory 포함(⑤ §5 B, v1.6.48 canonical + v1.6.50 candidate): retrieval 레이어와 권위 재유도(항상 store 재검증)를 분리 설계했다 — retrieval을 교체해도 item 변환·Gate는 불변. **canonical retrieval은 v1.6.51 vector + v1.6.52 ES lexical/hybrid(RRF)로 실현**(`VectorCanonicalMemoryRetriever` `memory_vectors` cosine, `LexicalCanonicalMemoryRetriever` ES nori, `HybridCanonicalMemoryRetriever` RRF 융합; 전부 `get_memory` 권위 재유도→canonical-only; env로 backend 선택, 없으면 Mongo-direct). worker drain은 ES 시 vector+lexical composite. **outbox per-target bookkeeping은 미룸**(enqueue는 배포 ES 구성 모름→영구 pending 회피, worker가 configured sink로만 fan-out). **candidate retrieval도 v1.6.54 색인 파이프라인 + v1.6.55 retriever로 실현**(`VectorCandidateMemoryRetriever`·`LexicalCandidateMemoryRetriever`·`HybridCandidateMemoryRetriever`, 전부 `get_candidate` 권위 재유도→needs_review-only, canonical과 동형 env 선택; 색인은 별도 `candidate_vectors`/`candidate_lexical` 물리 분리). candidate 색인 de-index·drain self-heal delete는 **v1.6.61 Phase 6 전이로 실경로화**(`CANDIDATE_REMOVED` + not-needs_review 재유도 delete); retriever needs_review 필터도 전이된 candidate를 실제로 배제. **candidate 포함(v1.6.50)**: candidate는 `status=candidate`·`review_status` 라벨 + `micro_evidence`만 + 권위필드(constraints/do_not_use) 배제(Phase 6 §62 위장 금지). Gate candidate 금지는 폐지가 아니라 candidate origin(`analysis_candidates`)만 예외로 좁힘. `needs_review→confirmed/rejected` 전이는 Phase 6이지만, **승격 candidate 양쪽 노출은 v1.6.60 dedup으로 닫힘**(retrieval-time 억제, 아래 항목).
- **canonical↔candidate 승격 dedup(v1.6.50 D7 후속, v1.6.60)**: 승격 candidate는 status가 `needs_review`로 남아 candidate retriever가 계속 반환하는데, 그 canonical 사본이 같은 지식을 이미 grounding하므로 candidate_memory step이 억제한다(브리프 `plans/04-canonical-candidate-dedup-decisions.md`). **D1=승격됐으면 항상 억제**(store 권위 `find_memory_by_candidate`, `source_candidate_id` identity 링크 — canonical이 같은 package에 있든 없든; D5=A "승격 candidate는 canonical 경로로만 서빙"에 부합)·**D2=retrieval-time interim 억제**(context_search 조립 단계 additive, 상태 모델·색인 무변). `PromotedCandidateResolver` seam(`MemoryService.is_candidate_promoted`)은 optional — 미주입 시 억제 없음(종전 D7 하위호환). embedding 아닌 identity dedup이라 라이브 불요. Phase 6 candidate de-index 도입 시 상위집합으로 흡수되는 forward-defense.
- **conflict review queue 영속화(2B.4 후속, v1.6.59)**: conflict를 결정적 id로 durable `review_queue`에 멱등 upsert한다. resolve/dismiss는 v1.6.61, 사람 승인 merge/split reconciliation은 v1.6.63, candidate+conflict Review Inbox read surface는 v1.6.64로 실경로화됐다.

### 추적 부채
- 없음. (이전 부채 #8 `ProviderError`→502는 조사 결과 stale — 두 경로 모두 이미 502였음 — 로 v1.6.49에서 명시 분기+회귀 lock으로 폐쇄했다.)

## Owner Decisions Needed

- **Phase 6 Review Inbox 백엔드 완료(v1.6.64)**: candidate+open conflict 통합 목록, matched canonical diff, source_ref pointer. 남은 Phase 6 결정은 부분 승인/retry·candidate edit/version 정책·Gate finding persistence·frontend.

- **(c-2) 완료(v1.6.63)**: 동명이인 직접 semantic 반증(off 기본), 라벨 기반 calibration harness, review-entry 기반 append-only merge/split write. production threshold 실값 채택은 실제 라벨 데이터 실행 결과 검토 대기.

- (d) review queue(v1.6.59)·(e) 승격 dedup(v1.6.60)·Phase 6 candidate 전이(v1.6.61)·(c) character alias(v1.6.62)·**(c-2) 동명이인 반증/calibration harness/merge-split write(v1.6.63) 완료**. production threshold 실값 채택은 라벨 데이터 실행 결과 검토 대기다. 다음 slice는 오너 선택 대기((b-4) hybrid 튜닝 / Phase 6 UI 잔여).

## Next Tasks

1. **다음 slice는 오너 선택 대기**((d) review queue 영속화·(e) 승격 dedup·Phase 6 candidate 상태 전이 백엔드(v1.6.61)·**(c) character 별칭 semantic(v1.6.62)** 완료). 후보는 각 착수 브리프 필요. 관통 완료: ⑤ retrieval·색인(canonical v1.6.48~55, candidate v1.6.54/55)·compose ES(v1.6.53)·b-6 worker compose(v1.6.56/57)·ES-lexical backfill(v1.6.58)·(d) review queue(v1.6.59)·(e) 승격 dedup(v1.6.60)·Phase 6 candidate 상태 전이(v1.6.61)·**(c) character 별칭 semantic(v1.6.62, 라이브 관통 PASS)**. 남은 후보:
   - **(b-4) hybrid 튜닝** — RRF k(현재 60)·per-signal 가중치·sub-retriever fetch depth를 실 데이터로 캘리브레이션(canonical·candidate 공통). *실 embedding/데이터 의존 → 서브 머신 막힘, 최후순위.*
   - **(c-2) 완료(v1.6.63)** — 동명이인 반증·calibration harness·merge/split write 완료. 남은 것은 실제 라벨 데이터로 threshold 값을 산출·검토해 production env를 발화하는 운영 튜닝이다.
   - **Phase 6 UI 잔여** — 상태 전이(v1.6.61)·merge/split write(v1.6.63)·Review Inbox 목록/상세+source pointer(v1.6.64) 완료. 남은 것: 부분 승인/부분 retry·candidate edit/version 정책·Gate finding 영속화 및 inbox additive 통합·frontend(framework 미확정 보류).
2. **sandbox 밖 실행 — 비-튜닝 live 검증 배치 소진(2026-07-12, 풀스택 머신)**:
   - **✅ 인덱싱 live 4종**: 2B.5 memory reindex·⑤ §8 ES lexical/hybrid·b-2 candidate 색인·Phase 3B archive→실 Chroma delete(DRAFT+PROJECT) — 실 Mongo·Chroma·ES·embedding 위에서 PASS(`docs/verifications/2026-07-12/indexing_live_smokes.md`, 오너 독립 감사 PASS). 실행법: `docker compose up -d mongo chroma elasticsearch embedding` 후 `docker compose run --rm --no-deps worker python scripts/<smoke>.py`.
   - **✅ 실 LLM(12B) 경로 live 4종**: Phase 2A provider 추출·2B.3.2 compare judge·Phase 4 planner·Phase 4 deployed e2e — in-stack llama(`docker-compose.llama.yml`, GPU) 위에서 wiring PASS(`docs/verifications/2026-07-12/llm_path_live_smokes.md`). 실행법: `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d` 후 `docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker python scripts/<smoke>.py`(deployed는 `-e APPLICATION_BASE_URL=http://application:8000`).
   - **남은 sandbox-밖 = 전부 튜닝(최후속)**: 2B.6 semantic threshold 실 캘리브레이션(cosine 분포 관찰→`ANALYSIS_SEMANTIC_MATCH_THRESHOLD`), (b-4) hybrid RRF 튜닝, compare judge **J1 프롬프트 판별 튜닝**. J1 live 신호: `update`→conflict가 **재실행에도 일관(체계적 편향, 우선 타깃)**, `no_change`는 샘플링 변동. **J1 착수 브리프는 별도 deterministic 벤치마크(fake 회귀 라벨 + real 정확도)를 반드시 포함**해야 함 — live smoke는 라벨을 assert하지 않아 프롬프트 판별 정확도를 검증하지 못한다(오너 독립 감사 비차단 #2).
3. **Phase 4 real vector 잔여**: real embedding quality spike, ES lexical 튜닝(§8 (b-4)). embedding 이미지 CPU-only torch pin은 오너 지시로 최후순위(GPU 기본 유지). 운영 주의: `docker compose restart chroma application`은 `depends_on: service_healthy`를 보장하지 않아 application이 Chroma ready 전에 실패할 수 있다 — Chroma까지 재시작한 뒤 `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d application`처럼 health dependency를 다시 적용한다.
4. **보류 계약층**: `/v1/generate-structured`(비용 확인으로 보류, adapter가 JSON 검증+1회 repair 소유), domain tool-call branch(상류 의존 해소 후), task별 `artifact_present`(payload schema 확정 시).
5. **Phase 7(대화형 수정·아이디에이션·저작 감독) 계획 수립됨** — 신규 페이즈 계획 `plans/07-conversational-authoring.md`(아이디에이션 원본 `docs/chat-revision-ideation.md`). **순차 구현**이라 Phase 5(글 생성)·Phase 6(검토) 이후 착수하며, directive 감독면(P5)은 Phase 6와 공동 설계. 확정 결정 D1~D10·슬라이스 P1~P5는 계획 문서에 있고, 슬라이스별 착수 브리프는 구현 시점에. *지금 당장 착수 대상 아님(현재 실 타깃은 Next Tasks #1 후보 / 순차상 Phase 5·6 선행).*

## Verification

- 현재 시스템 전체 스위트: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **773 passed / 48 skipped / 99 subtests**. `git diff --check` clean.
- **Review Inbox 독립 적대적 검증 PASS(조건 없음)**: `docs/verifications/2026-07-12/review_inbox_backend.md`. Obs1 실제 Core SOT source_ref의 resolved pointer 전체 envelope, Obs2 direct-promoted+needs_review candidate 억제를 HTTP 회귀로 보강했다.
- **(c-2) 오너 독립 적대적 검증 PASS(조건 없음)**: `docs/verifications/2026-07-12/character_homonym_reconciliation.md`. Obs1 전체 suite 결과를 정정했고, Obs2 reconcile HTTP 200/404/409 영속 회귀 4개와 Obs4 `MemoryError`/`InvalidCandidateStateTransition` 명시 409 매핑을 보강했다.
- **(c) character 별칭 semantic 라이브 관통(2026-07-12, 풀스택 머신) — PASS**: `scripts/phase2b7_character_alias_live_smoke.py` — Mongo promote→worker drain→실 Chroma `memory_vectors`→compare alias(실 BGE-m3-ko + Chroma query_similar). `철수`(별칭)→`conflict`+canonical id·`영희`(타인)→`create`, threshold 0.7, `memory_backend: chroma+elasticsearch`, self-cleaning. **관통·wiring 검증이며 라벨 정확도·threshold 실값 캘리브레이션은 후속**(D5/D7).
- **(c) 오너 독립 적대적 검증 PASS(조건 없음)**: `docs/verifications/2026-07-12/character_alias_semantic.md` — 경계 매트릭스 10행 빈 cell 없음(직접 5+위임 5), judge 우회·apply review_queue 전달·scope character 한정 재도출 확인, pytest 755/48 독립 재현. 비차단 관찰 4건 중 **Obs2(alias self-exclusion)·Obs4(scope-less 미영향)를 회귀로 실경로 보강**(mutation bite 재실증, 757 passed); Obs1(SoT 산문 순서, 기존 부채)·Obs3(rationale id, 계약 미고정)은 코드 무변.
- **live 관통 검증(2026-07-12, 풀스택 머신) — 2배치**:
  - **인덱싱 4종**: 2B.5 memory reindex·⑤ §8 ES lexical/hybrid·b-2 candidate 색인·Phase 3B archive→실 Chroma delete(DRAFT+PROJECT 2분기)를 실 Mongo·Chroma·ES(nori)·embedding 위에서 전부 PASS(`docs/verifications/2026-07-12/indexing_live_smokes.md`). **오너 독립 적대적 감사 PASS(조건 없음)**(`indexing_live_smokes_independent_audit.md`) — 비차단 관찰 3건 보강(PROJECT_ARCHIVED live 승격 포함). 신규 smoke 2개(candidate·archive) 프로덕션·계약·SoT 무변.
  - **실 LLM(12B) 경로 4종**: Phase 2A provider 추출·2B.3.2 compare judge·Phase 4 planner·Phase 4 deployed e2e를 in-stack llama(GPU) 위에서 wiring PASS(`docs/verifications/2026-07-12/llm_path_live_smokes.md`). **오너 독립 적대적 감사 PASS(조건 없음)**(`llm_path_live_smokes_independent_audit.md`) — 비차단 관찰 3건(gateway 컨테이너 관통 편중·라벨 품질 live 미검증·비결정성) 검증 기록에 보강(코드 무변). compare judge J1 프롬프트 판별은 튜닝 과제로 분리(신호만 기록). v1.6.61 독립 검토 CONDITIONAL PASS → 최종 합격(`docs/verifications/2026-07-11/candidate_state_transition.md`), 비차단 관찰 2건 closure(Obs1 rejected→needs_review 거부 테스트·Obs2 CANDIDATE_REMOVED routing 테스트+docstring). mutation 3종 양방향 bite(불법 전이·idempotency·routing, cp 복원). v1.6.60 독립 검토 조건부 합격 → 최종 합격(`docs/verifications/2026-07-11/canonical_candidate_dedup.md`), 비차단 관찰 I1~I3 closure.
  - 종전 3 환경-의존 failed(`ConnectElasticsearchTest`, b-5 도입)는 2026-07-10 skip guard(`@unittest.skipUnless(importlib.util.find_spec("elasticsearch"))`)로 해소 — 패키지 없는 sandbox에선 skip(45→48), 있는 환경에선 종전대로 3개 실행(회귀 잠금 유지). 테스트 전용 수정, 계약·프로덕션 코드 무변. **양방향 실증됨**(2026-07-10 검증 보강): 패키지 격리 설치(PYTHONPATH 주입, 시스템 무오염) 시 전체 스위트 **707 passed/45 skipped**로 3개 실행·PASS, 미주입 시 704/48로 원상복구.
  - `--ignore=tests/test_memory_mongo.py`는 프로젝트 검증 관례다(해당 4개는 사전-존재 localhost Mongo env artifact이며 코드 회귀가 아니다).
  - skip 45개는 live Mongo/Chroma/embedding 미가용 통합·smoke 테스트(sandbox 밖에서 실행).
- live/배포 검증 이력은 `docs/verifications/YYYY-MM-DD/`에 있다. 각 slice의 자체 회귀·mutation 재실증 상세는 `docs/daily_logs/YYYY-MM-DD/work_log.md`에 있다.

## Project Structure

```text
docker-compose.yml               # base: application + Mongo replica set + gateway(외부 llama 클라이언트) + embedding + chroma + elasticsearch(nori)
docker-compose.llama.yml         # opt-in override: in-stack llama.cpp GPU 서버(server-cuda, -hf 12B QAT, port 9080)
.dockerignore / .gitignore
docs/
├── runbooks/local-llama-server.md   # 로컬 llama.cpp GPU 서버 opt-in 기동/설정/smoke runbook
├── README.md                    # 문서 분류와 진입점
├── system-contract-sot.md       # 정본 계약 SoT(Approved, v1.6.64)
├── abstract.md / *.md           # 보존된 아이디에이션 원본과 주제별 상세
├── plans/                       # 계획 + 착수 결정 브리프(README 인덱스)
│   ├── README.md · 00-foundations.md · implementation-plan.md
│   ├── 01-core-sot.md ~ 06-review-ui.md   # Phase별 계획
│   ├── flat-loop-gate.md · llm-gateway.md · gemma4-reuse.md · product-shell.md · analysis-memory-taxonomy.md
│   ├── 02-* / 02b-* / 03-* / 04-*-decisions.md   # slice별 착수 결정 브리프(대부분 Resolved)
├── benchmarks/2026-06-30/       # Gemma Q4 budget 기본값 근거
├── daily_logs/2026-06-24 … 2026-07-08/work_log.md   # 상세 이력
└── verifications/2026-06-24 … 2026-07-08/           # 독립 검증 기록
services/
├── elasticsearch/Dockerfile     # 배포 ES = 공식 ES 8.13.4 + analysis-nori(v1.6.53); compose build 컨텍스트
├── llm_gateway/app/             # main(shell) · payload · provider · errors · transport · client · httpx_transport
├── embedding/app/main.py        # FastAPI /embed·/health, dragonkue/BGE-m3-ko lazy 로드
└── application/app/
    ├── main.py                  # FastAPI shell + 전 도메인 HTTP wiring
    ├── core_sot/                # models · splitter · repository · mongo_repository · service
    ├── analysis/                # models · schema · extractor · runner · source · service · repository · mongo_repository
    │                            #   + compare(+ character 별칭 alias_matcher seam, v1.6.62) · compare_judge · semantic_matcher(2B.6, 별칭도 재사용) · apply(2B.4) · review_queue(+mongo, 2B.4 후속 v1.6.59) · candidate_review(Phase 6 상태 전이, v1.6.61)
    ├── memory/                  # 2B.1 canonical store: models · scope · service · repository · mongo_repository
    ├── indexing/               # models · embedding · chroma · memory_index(2B.5/6) · memory_lexical_index(§8 ES) · candidate_index(b-2 vector) · candidate_lexical_index(b-2 ES) · service · mongo_repository
    ├── context_search/          # models · planner · service(⑤ canonical+candidate memory retriever/gate + 승격 dedup resolver, (e) v1.6.60)
    └── agent_loop/              # decision · budget · registry · parser · completion · resolution · runner
tests/                           # 71개 모듈(도메인별 회귀 + live/smoke skip-aware) + fixtures/core_sot.py
scripts/
├── smoke_llm_provider.py · benchmark_llm_provider.py
├── phase2a_*_smoke.py · phase3a_rebuild_source_block_index.py(CLI rebuild) · phase3a_*_smoke.py · phase4_context_search_*_smoke.py · phase4_lexical_memory_live_smoke.py
├── index_sync_worker.py         # 3B archive + 2B.5 memory reindex + b-2 candidate 색인 drain (--loop compose 서비스, b-6 증분1)
├── phase2b3_compare_judge_live_smoke.py · gateway_generate_live_smoke.py(gateway 컨테이너 /v1/generate 직접, 2026-07-12 신규)
├── phase2b7_character_alias_live_smoke.py   # (c) character 별칭 alias→conflict 라이브 관통(실 embedding+Chroma, self-cleanup, 2026-07-12 신규)
├── phase2b_candidate_index_live_smoke.py · phase3b_archive_chroma_live_smoke.py   # b-2 candidate·3B archive live 관통 smoke(2026-07-12 신규, Mongo doc self-cleanup)
└── phase2b5_reindex_memory.py · phase2b5_reindex_candidate.py(둘 다 vector+lexical backfill, v1.6.58) · phase2b5_memory_reindex_live_smoke.py
```
