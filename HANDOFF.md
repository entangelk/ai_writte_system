# HANDOFF

> **다음 작업자를 위한 현재 상태 스냅샷.** 이력/일지가 아니라 **지금 사실이고 실행 가능한 것**만 둔다.
> 상세 이력은 `docs/daily_logs/`, 독립 검증은 `docs/verifications/`, 주요 마일스톤은 `CHANGELOG.md`.

## Current Status

- 정본 SoT는 `docs/system-contract-sot.md`이며 현재 **v1.6.50**(Approved). SoT가 정본 우선순위이고, 미확정 항목은 추측 구현하지 않는다.
- 개발 진입점은 `docs/plans/README.md`. `docs/` 루트의 설계 문서는 초기 아이디에이션 자료다.
- 구현된 계층(모두 회귀로 잠김, 아래는 현재 동작하는 표면):
  - **LLM Gateway**: FastAPI shell(`/health/live`·`/health/ready`·`/v1/generate`), llama.cpp 호환 provider + httpx async adapter, provider error 5종→HTTP status 매핑.
  - **Core SOT**: project/draft CRUD·version read/export(txt·markdown)·source_ref catalog HTTP API. pymongo(sync) adapter(transaction 기본 + single-writer fallback), idempotency는 unique index 강제.
  - **Agent loop 계약층**: decision 7종·budget 5차원·tool registry·self-report parser·completion 판정·minimal provider composition runner. (tool-call branch는 상류 의존으로 보류 — Active Decisions 참조.)
  - **Analysis(Phase 2A)**: taxonomy 3종 extraction, job 상태 전이, provider/Gateway wiring + JSON repair, job/candidate/run HTTP API.
  - **Memory(Phase 2B.1~2B.6)**: canonical `MemoryEntry` store + candidate 승격(수동/threshold), compare→ActionProposal→versioned upsert(append-only), compare judge(Gateway 1-turn), memory→vector 재색인(async outbox→worker), event/open_question semantic identity(off 기본).
  - **Indexing(Phase 3A/3B)**: source block index rebuild(HTTP/CLI/deployed smoke), index sync outbox + one-shot worker(archive drain + memory reindex drain).
  - **Context search(Phase 4)**: LLM planner + orchestration + Context Gate, HTTP API, 공유 in-process vector index, real Chroma+embedding 백엔드(env 구성 시), canonical memory 포함(⑤ §5 B) + `needs_review` candidate 포함(라벨·micro·권위필드 배제, Gate가 candidate origin만 예외 허용).
- **Compose 런타임**: base `docker-compose.yml`(application + Mongo replica set + gateway[외부 llama 클라이언트] + embedding + chroma). opt-in `docker-compose.llama.yml`로 in-stack llama.cpp GPU 서버(port 9080)를 띄운다. runbook: `docs/runbooks/local-llama-server.md`.
- **테스트**: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **630 passed / 45 skipped**(2026-07-08 기준). skip은 대부분 live Mongo/Chroma/embedding 미가용 통합 테스트.

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
- event/open_question semantic identity는 compare `_find_matches`에서 처리한다(2B.6 D1=A). semantic 매칭은 **off 기본**(D4=A): `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 미설정 시 always-create 보존, 실 embedding 캘리브레이션 후 발화. character는 결정적 name-key 유지.
- Writing ContextPackage의 memory 포함(⑤ §5 B, v1.6.48 canonical + v1.6.50 candidate): retrieval 레이어(현재 Mongo-direct, 랭킹 없음)와 권위 재유도(항상 store 재검증)를 분리 설계했다. 후속에서 retrieval을 vector(`memory_vectors`)·ES로 교체해도 item 변환·Gate는 불변. **candidate 포함(v1.6.50)**: candidate는 `status=candidate`·`review_status` 라벨 + `micro_evidence`만 + 권위필드(constraints/do_not_use) 배제(Phase 6 §62 위장 금지). Gate candidate 금지는 폐지가 아니라 candidate origin(`analysis_candidates`)만 예외로 좁힘. `needs_review→confirmed/rejected` 전이는 Phase 6이라 현재 승격 candidate는 canonical·candidate 양쪽 노출 가능(D7 no-dedup 수용).

### 추적 부채
- 없음. (이전 부채 #8 `ProviderError`→502는 조사 결과 stale — 두 경로 모두 이미 502였음 — 로 v1.6.49에서 명시 분기+회귀 lock으로 폐쇄했다.)

## Owner Decisions Needed

- 없음. **다음 구현 slice 선택은 대기 중**(Next Tasks #1 후보 참조).

## Next Tasks

1. **다음 구현 slice 선택**(각 후보는 착수 브리프 필요). Phase 2B(2B.1~2B.6) + ⑤ Writing canonical(v1.6.48)·candidate(v1.6.50) inclusion까지 관통 완료. 후보:
   - **(b) Writing memory retrieval의 vector/검색엔진 확장** — canonical·candidate 둘 다 현재 Mongo-direct(랭킹 없음). retrieval 레이어를 `memory_vectors` vector(relevance)·ES lexical로 교체(item 변환·Gate 불변; 두 retriever가 같은 seam).
   - **(c) character 별칭/동명이인 semantic 보강**(2B.3 D2=A 확장).
   - **(d) conflict/merge/split review queue 영속화.**
   - **(e) canonical↔candidate semantic dedup**(v1.6.50 D7 후속 — 같은 지식이 승격 후 canonical·candidate 양쪽에 나타나는 것 정리; Phase 6 review 상태 전이와 함께 검토).
2. **sandbox 밖 실행(코드 완료, 여기서 막힘)**:
   - 2B.6 threshold 실 캘리브레이션 — 실 embedding(BGE-m3-ko)+데이터로 유사/비유사 event pair cosine 분포 관찰 → `ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 확정·env 설정(off 기본이라 미설정 시 미발화).
   - 2B.5 live smoke(`scripts/phase2b5_memory_reindex_live_smoke.py`: promote→outbox→worker→실 `memory_vectors` 관통) + 필요 시 backfill(`scripts/phase2b5_reindex_memory.py`).
   - 곁가지: 2B.3.2 compare judge live smoke, worker→real Chroma archive live smoke.
3. **Phase 4 real vector 잔여**: worker→real Chroma live smoke(archive→outbox→worker→실 Chroma record 삭제), ES lexical 경로(§8, 착수 브리프 필요), real embedding quality spike. embedding 이미지 CPU-only torch pin은 오너 지시로 최후순위(GPU 기본 유지). 운영 주의: `docker compose restart chroma application`은 `depends_on: service_healthy`를 보장하지 않아 application이 Chroma ready 전에 실패할 수 있다 — Chroma까지 재시작한 뒤 `docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d application`처럼 health dependency를 다시 적용한다.
4. **보류 계약층**: `/v1/generate-structured`(비용 확인으로 보류, adapter가 JSON 검증+1회 repair 소유), domain tool-call branch(상류 의존 해소 후), task별 `artifact_present`(payload schema 확정 시).

## Verification

- 현재 시스템 전체 스위트: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **630 passed / 45 skipped**. `git diff --check` clean.
  - `--ignore=tests/test_memory_mongo.py`는 프로젝트 검증 관례다(해당 4개는 사전-존재 localhost Mongo env artifact이며 코드 회귀가 아니다).
  - skip 45개는 live Mongo/Chroma/embedding 미가용 통합·smoke 테스트(sandbox 밖에서 실행).
- live/배포 검증 이력은 `docs/verifications/YYYY-MM-DD/`에 있다. 각 slice의 자체 회귀·mutation 재실증 상세는 `docs/daily_logs/YYYY-MM-DD/work_log.md`에 있다.

## Project Structure

```text
docker-compose.yml               # base: application + Mongo replica set + gateway(외부 llama 클라이언트) + embedding + chroma
docker-compose.llama.yml         # opt-in override: in-stack llama.cpp GPU 서버(server-cuda, -hf 12B QAT, port 9080)
.dockerignore / .gitignore
docs/
├── runbooks/local-llama-server.md   # 로컬 llama.cpp GPU 서버 opt-in 기동/설정/smoke runbook
├── README.md                    # 문서 분류와 진입점
├── system-contract-sot.md       # 정본 계약 SoT(Approved, v1.6.48)
├── abstract.md / *.md           # 보존된 아이디에이션 원본과 주제별 상세
├── plans/                       # 계획 + 착수 결정 브리프(README 인덱스)
│   ├── README.md · 00-foundations.md · implementation-plan.md
│   ├── 01-core-sot.md ~ 06-review-ui.md   # Phase별 계획
│   ├── flat-loop-gate.md · llm-gateway.md · gemma4-reuse.md · product-shell.md · analysis-memory-taxonomy.md
│   ├── 02-* / 02b-* / 03-* / 04-*-decisions.md   # slice별 착수 결정 브리프(대부분 Resolved)
├── benchmarks/2026-06-30/       # Gemma Q4 budget 기본값 근거
├── daily_logs/2026-06-24 … 2026-07-07/work_log.md   # 상세 이력
└── verifications/2026-06-24 … 2026-07-07/           # 독립 검증 기록
services/
├── llm_gateway/app/             # main(shell) · payload · provider · errors · transport · client · httpx_transport
├── embedding/app/main.py        # FastAPI /embed·/health, dragonkue/BGE-m3-ko lazy 로드
└── application/app/
    ├── main.py                  # FastAPI shell + 전 도메인 HTTP wiring
    ├── core_sot/                # models · splitter · repository · mongo_repository · service
    ├── analysis/                # models · schema · extractor · runner · source · service · repository · mongo_repository
    │                            #   + compare · compare_judge · semantic_matcher(2B.6) · apply(2B.4)
    ├── memory/                  # 2B.1 canonical store: models · scope · service · repository · mongo_repository
    ├── indexing/               # models · embedding · chroma · memory_index(2B.5/6) · service · mongo_repository
    ├── context_search/          # models · planner · service(⑤ canonical+candidate memory retriever/gate)
    └── agent_loop/              # decision · budget · registry · parser · completion · resolution · runner
tests/                           # 65개 모듈(도메인별 회귀 + live/smoke skip-aware) + fixtures/core_sot.py
scripts/
├── smoke_llm_provider.py · benchmark_llm_provider.py
├── phase2a_*_smoke.py · phase3a_*_smoke.py · phase4_context_search_*_smoke.py
├── index_sync_worker.py         # 3B archive drain + 2B.5 memory reindex drain
├── phase2b3_compare_judge_live_smoke.py
└── phase2b5_reindex_memory.py · phase2b5_memory_reindex_live_smoke.py
```
