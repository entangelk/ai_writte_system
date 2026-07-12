# Work Log — 2026-07-12

## Goals

- 다음 비튜닝 slice인 Gate finding persistence/Review Inbox 통합을 오너가 검토할 수 있도록 착수 결정 브리프를 작성한다.

- 튜닝을 제외한 다음 작업으로 Phase 6 Review Inbox 백엔드 목록/상세 slice를 구현한다.

- 오너가 선택한 (c-2): 동명이인 반증, character threshold calibration, merge/split write를 구현한다.

- HANDOFF와 2026-07-11 work log를 읽고 다음 작업을 진행한다.
- 오너 지시: "여기는 테스트도 가능한 머신이니까 확인해서 진행" → 이전 세션이 서브 머신에서 막았던 **live 관통 검증**(HANDOFF Next Tasks #2/#3, "코드 완료, sandbox 밖 막힘")을 실 인프라 위에서 실행한다.

## Completed work

### Gate finding persistence decision brief

- `plans/06-gate-finding-persistence-decisions.md` Draft를 추가했다. transient GateFinding의 저장 대상, persistence 실패 자세, identity/idempotency, lifecycle, candidate action 연동, payload, inbox 표현, API를 D1~D8로 분리하고 각 선택지·추천·tradeoff를 명시했다.
- 추천 묶음은 reject-only, persistence 강보장, client idempotency key, open→resolved/dismissed, candidate action 자동 연동 없음, 최소 재현 envelope, 기존 inbox additive section, 명시 transition API다. 오너 결정 전 구현하지 않는다.
- 오너 피드백에 따라 최초 독립 형식 브리프를 프로젝트 기존 관례인 `03-indexing-kickoff-decisions.md` 구조로 전면 재작성했다. `현재 확정된 경계 → 구현을 막는 미확정 항목 → 번호별 선택지/장단점 표/추천 → 첫 구현 slice → 제외 범위 → 승인 결과` 순서를 따른다.

### Gate finding persistence implementation

- 오너가 D1~D8=A를 승인했다. reject-only로 시작하되 pass 감사 이력 확장 가능, persistence 실패 502, client idempotency key, open→resolved/dismissed, candidate action 자동 연동 없음, 최소 재현 envelope, additive inbox, Gate 전용 API를 잠갔다.
- `gate_findings.py` domain/store와 in-memory repository, Mongo adapter를 추가했다. deterministic id와 request/result fingerprint, 안정 pointer ids를 저장한다.
- `/context-search`에 필수 `idempotency_key`를 추가하고 reject findings만 저장한다. Review Inbox `items`는 불변이고 `gate_findings`가 additive로 추가된다.
- Gate finding list/detail/resolve/dismiss API를 추가했다. same terminal replay는 멱등, cross-terminal은 409다.
- 완전 재현은 immutable GateRun manifest(pointer version/hash + planner/prompt/model/backend manifest) 후속으로 브리프에 기록했다.
- focused Gate/context/inbox 회귀 **41 passed**. 전체 `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **778 passed / 48 skipped / 99 subtests**, exit 0. `/context-search` 호출부 pattern sweep으로 모든 실제 request fixture/smoke에 idempotency key를 반영했다.
- 독립 검증 `gate_finding_persistence.md`가 §9 boundary matrix의 빈 셀 2개로 조건부 합격을 판정했다. 필수 D5(candidate confirm/reject 후 finding OPEN 유지)와 D7(candidate items envelope additive 불변)을 HTTP 관통 회귀로 추가했다. 권장 404 missing project/finding 및 Mongo compound index/upsert/get/open 정렬 round-trip도 보강했다. 향후에는 구현 전에 브리프 boundary matrix 각 행을 named test에 먼저 매핑한다.
- 보강 focused **43 passed + confirm/reject 2 subtests**. 최종 전체 **783 passed / 48 skipped / 101 subtests**, exit 0. `git diff --check` clean.

### Phase 6 Review Inbox backend

- 오너 승인 권장안을 `plans/06-review-inbox-backend-decisions.md`에 잠갔다: candidate+open conflict 통합, matched canonical field diff, editor URL 대신 source_ref pointer, 부분 승인/edit/Gate store 제외.
- `ReviewInboxService`를 추가해 미승격 needs_review candidate 한 행에 open conflict를 중첩했다. legacy 직접 승격 candidate는 canonical promotion link로 억제한다.
- `GET /projects/{id}/analysis/review-inbox`와 `GET .../review-inbox/{candidate_id}`를 추가했다. 상세은 payload, source pointer, matched memory, sorted field diff를 반환한다. missing/cross-project/non-review candidate는 404다.
- HTTP 회귀 4개로 목록 통합, 상세 diff/source missing 표시, reconciliation 후 inbox 제거, project 격리를 잠갔다.
- focused `tests/test_analysis_apply_api.py` **22 passed**. 전체 `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` **771 passed / 48 skipped / 99 subtests**, exit 0. 최초 테스트 클래스 상속이 기존 4개를 중복 수집해 775로 보인 것을 발견하고 helper-only 재사용으로 교정했다.
- 독립 적대적 검증 `review_inbox_backend.md` PASS 후 Obs1/Obs2를 보강했다. 실제 Core SOT snapshot/source_ref를 만들어 resolved pointer 8필드를 잠그고, direct promote 후 status가 needs_review에 남아도 inbox list/detail에서 억제됨을 직접 검증했다. focused ReviewInbox **6 passed**, 전체 **773 passed / 48 skipped / 99 subtests**.

### (c-2) character identity reconciliation

- same-name 단일 canonical을 직접 embedding pair로 검증하는 optional homonym verifier를 추가했다. 하한 미달은 matched id를 실은 conflict이며 env 미설정은 종전 judge 경로다.
- 라벨 JSONL text pair를 실 embedding으로 점수화해 balanced accuracy 최대 threshold/confusion을 출력하는 calibration CLI를 추가했다. 양 라벨이 없으면 거부하고 env는 자동 변경하지 않는다.
- review entry ID 기반 merge/split API를 추가했다. merge는 canonical payload 보존+evidence union append-only version, split은 명시 candidate 별도 canonical이다. resolution action/result를 저장해 replay를 잠갔다.

### 상황 확인

- 세션 시작 git 스냅샷은 stale(최상단 d217f54=v1.6.58)이었으나 실제 HEAD는 **47d63a6(SoT v1.6.61)**, working tree clean. v1.6.59/60/61 전부 커밋 완료 상태.
- baseline `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **749 passed / 48 skipped**(HANDOFF와 일치).
- 머신 능력 프로브: Docker 28.5.1 + compose v2.40.2(daemon 실행), RTX 3060(12B QAT 구동 가능), 호스트 python에 pymongo/httpx/fastapi(torch/chromadb/ES는 컨테이너 소관). → **풀스택 머신**. 서브 머신에서 막혔던 live 검증을 실행 가능하다고 판단.

### 인프라 스택 bring-up

- `docker compose build worker elasticsearch` → worker=현재 코드(v1.6.61) 이미지, elasticsearch=official 8.13.4 + analysis-nori 빌드. (기존 application/gateway/embedding 이미지는 6일 전 것이라 worker 이미지 재빌드로 현재 코드 확보.)
- `docker compose up -d mongo chroma elasticsearch embedding` → 전부 healthy. embedding 모델(`dragonkue/BGE-m3-ko`)은 `embedding_cache` 볼륨에 2.1G 캐시돼 재다운로드 없이 즉시 ready. mongo replica set은 기존 볼륨에서 이미 초기화.

### live 관통 4종 실행 — 전부 PASS

전부 worker 이미지 컨테이너 안에서 실행(정확한 의존성 버전 + in-network DNS + 호스트 무오염). 독립 검증 기록: `docs/verifications/2026-07-12/indexing_live_smokes.md`(PASS).

1. **2B.5 memory reindex**(`scripts/phase2b5_memory_reindex_live_smoke.py`, 기존): promote→MEMORY_UPSERTED outbox→worker composite drain→실 Chroma `memory_vectors` 착지. `status:ok`, `memory_backend: chroma+elasticsearch`(벡터+lexical 양 sink fan-out 실증), worker_succeeded 1.
2. **⑤ §8 ES lexical/hybrid**(`scripts/phase4_lexical_memory_live_smoke.py`, 기존): 한국어 "폭풍"→nori 매칭 `storm`, superseded 배제, hybrid RRF 표면화. `ok:true, nori:true`. (스크립트가 sys.path 미삽입이라 `-e PYTHONPATH=/app` 필요.)
3. **b-2 candidate 색인**(`scripts/phase2b_candidate_index_live_smoke.py`, **신규 작성**): record_candidate→CANDIDATE_UPSERTED outbox→worker composite→실 Chroma `candidate_vectors` + 실 ES `candidate_lexical` 양쪽 착지. `status:ok`, `candidate_backend: chroma+elasticsearch`.
4. **Phase 3B archive→Chroma delete**(`scripts/phase3b_archive_chroma_live_smoke.py`, **신규 작성**): 실 Chroma에 2 draft source-block seed→DRAFT_ARCHIVED outbox→worker archive mutation drain→해당 draft만 삭제, control draft 생존. `status:ok`, `archive_backend: chroma`. 2026-07-05 mutation/코드 감사의 live 후속 공백을 채움.

### 신규 스크립트 2개

- `scripts/phase2b_candidate_index_live_smoke.py` — b-2 candidate 관통 live smoke. 기존 candidate live smoke가 없어(HANDOFF가 이 gap을 명시) 2B.5 memory smoke와 동형으로 신규 작성.
- `scripts/phase3b_archive_chroma_live_smoke.py` — archive→실 Chroma delete live smoke. 기존 archive live smoke가 없어 신규 작성.
- 성격: **검증 도구**(test/smoke). 프로덕션 코드·계약·SoT 무변 → SoT bump 없음.

## Issues found

- **b-2 smoke 최초 mismatch — ES refresh 지연**: `lexical_candidate_ids: []`. 원인은 파이프라인 결함이 아니라 `index_candidate_records`가 프로덕션 정상대로 `refresh` 없이 색인(검색은 생성 시점이지 색인 직후 μs가 아님) → 색인 직후 read-back이 refresh_interval(1s) 전에 조회. smoke에 명시적 `indices.refresh` 추가(phase4 lexical smoke가 이미 쓰는 패턴)로 해소. 프로덕션 무변.
- **3B smoke 최초 예외 — Chroma dim mismatch**: `InvalidDimensionException: dimension 3 != 1024`. 배포 `project_memory_vectors`가 실 BGE-m3-ko(1024-dim)로 고정돼 3-dim seed 거부. archive 삭제는 metadata where 기반이라 벡터값 무관 → seed를 1024-dim으로 맞춰 해소. 프로덕션 무관.

## Decisions

- Review Inbox는 현재 영속 가능한 Analysis candidate+conflict만 먼저 통합한다. Gate finding은 store가 생길 때 additive origin으로 확장한다. frontend/editor route는 고정하지 않고 정본 source pointer까지만 제공한다. 부분 승인/retry와 candidate edit는 별도 계약으로 남긴다.

- 오너는 semantic 반증은 conflict만, threshold는 라벨 근거 전까지 off, merge는 evidence 합성, split은 명시 candidate 귀속만 허용하는 안전 경계를 승인했다.

- **live 검증을 다음 작업으로 선택**: HANDOFF Next Tasks #1(다음 slice)은 전부 오너 선택 + 착수 브리프 선행이라 임의 착수 불가. 반면 #2/#3의 live 관통은 "코드 완료, sandbox 밖 막힘"으로 명시적으로 남겨진 자족 검증이고, 오너가 "테스트 가능한 머신이니 확인"을 명시 → 정확히 이 머신에서 채울 gap.
- **SoT bump 없음**: 신규 smoke 2개는 검증 도구. 계약 literal·public 표면·프로덕션 코드 무변, 동작 변화 0.
- **미커밋 유지**: 프로젝트 관례상 커밋은 오너 지시 대기.

## Verification

- 신규 핵심 회귀: `python3 -m pytest -q tests/test_character_threshold.py tests/test_character_reconciliation.py tests/test_analysis_compare.py` → **21 passed**.
- compare wiring 포함: `tests/test_analysis_compare.py tests/test_analysis_compare_api.py` → **31 passed**.
- 독립 검증이 최초 실행기의 hang 보고를 비재현하고 **763 passed / 48 skipped**를 확인했다. 후속 Obs2/Obs4 보강으로 reconcile HTTP 200/404/409 envelope·same-action replay·cross-action/invalid action·superseded target을 4개 회귀로 추가했다. 동기 review route의 AnyIO test-loop 교착을 확인해 blocking 작업이 없는 GET/reconcile을 `async def`로 정렬했다.
- 최종 전체 suite: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **767 passed / 48 skipped / 99 subtests**, exit 0. `git diff --check` 통과.

- 전체 스위트 회귀 무변: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **749 passed / 48 skipped**(신규 스크립트는 pytest 미수집). `git diff --check` clean(신규 untracked 2파일 외 변경 없음).
- live 관통 4종 전부 exit 0 + `status:ok`/`ok:true`. 상세·재현 명령은 `docs/verifications/2026-07-12/indexing_live_smokes.md`.

## 오너 독립 감사 + 보강

오너가 별도 세션에서 **적대적 독립 감사**를 수행 → **PASS(조건 없음)**. 4점 의심(refresh=진짜 smoke 문제?/dim=진짜 seed 문제?/smoke 순환논리?/749 진짜?)을 1차 소스+실 인프라 재실행+관찰 재현으로 전부 작업자 클레임 쪽 확정. 감사 기록: `docs/verifications/2026-07-12/indexing_live_smokes_independent_audit.md`. 비차단 관찰 3건을 반영:

- **refresh flaky 재현성**: 감사가 refresh 제거 변형 4회 실행 → 3회 `[]` mismatch/1회 우연 PASS(timing-dependent flaky) 재현. 검증 기록 §4에 재현성 명시 추가(진단 결론 불변).
- **PROJECT_ARCHIVED live gap 닫음**: `phase3b_archive_chroma_live_smoke.py`를 2단계로 확장 — Phase 1 DRAFT_ARCHIVED(narrowing) + **Phase 2 PROJECT_ARCHIVED(project 전체 wipe) 신규**. 실 재실행 → `remaining_after_project_archived: []` 확인. 감사가 지적한 boundary-matrix 빈 셀(회귀 의존)을 live 검증으로 승격. 검증 기록 §5 갱신.
- **Mongo `smoke-*` 누적**: ops 관심사로 검증 기록 §Issues에 명시(현재 결함 아님).

보강 후 회귀 무변(**749 passed / 48 skipped**), archive smoke 2단계 재실행 PASS.

## 2차 작업 — 실 LLM(12B) 경로 live 관통 4종 (튜닝 제외)

오너가 "다음 작업 이어서, 튜닝 빼고 진행할 수 있는 걸로"(튜닝=최후속) 지시. 남은 live 검증 중 **실 llama 12B 의존 smoke 4종**이 오너 브리프 불필요한 비-튜닝 검증이라 선택. in-stack llama 서버(`docker-compose.llama.yml`, RTX 3060, 모델 캐시 6.7GB)를 기동해 관통. 검증 기록: `docs/verifications/2026-07-12/llm_path_live_smokes.md`(PASS). **신규 코드/스크립트 없음**(4 smoke 사전 존재), 문서만 산출.

- **Phase 2A provider 추출**: exit 0, HTTP 200, job `succeeded`, candidates=3. App→Gateway→llama 추출 관통.
- **Phase 2B.3.2 compare judge**: 4 boundary pair 전부 `succeeded`(terminal-JSON). **wiring PASS**. J1 empirical 신호(비차단, 튜닝 대상): update→conflict·no_change→add_evidence 과잉 판정(2/4 의도 라벨 불일치) — 프롬프트 판별 튜닝은 오너 지시로 제외, 신호만 기록.
- **Phase 4 planner**: exit 0, `succeeded`, 유효 2-step SearchPlan(structured JSON).
- **Phase 4 deployed e2e**: rebuild(실 Chroma 6건)→실 llama planner 2-step→gate `pass`→macro 2/micro 6, `degraded: False`(완전 정상 경로). application HTTP→gateway→llama→orchestration→retrieval→Gate 전 경로 관통.

이로써 비-튜닝 live 검증 배치 소진: 인덱싱 4종(1차) + LLM 경로 4종(2차). 남은 sandbox-밖은 전부 튜닝(2B.6 threshold·(b-4) hybrid·J1 프롬프트) = 최후속.

### 오너 독립 감사(LLM 배치) + 보강

오너가 LLM 배치를 **적대적 독립 감사** → **PASS(조건 없음)**. "wiring/품질 분리가 2/4 불일치를 숨기는 회피인가?" 반박 가설을 smoke 코드(`_BOUNDARY_PAIRS`=INPUTS not assertions, exit=terminal outcome)로 기각. 4종 재실행 전부 PASS 재현. 감사 기록: `docs/verifications/2026-07-12/llm_path_live_smokes_independent_audit.md`. 비차단 관찰 3건 반영(코드 무변, 검증 기록 문서만 보강):

- **#1 gateway 컨테이너 관통 편중**: provider/planner/compare judge는 인프로세스 ASGI → gateway 컨테이너 관통은 deployed e2e 하나뿐(코드 동일→기능 무문제). 검증 기록 §5/Issues 명시.
- **#2 compare judge 라벨 품질 live 미검증**: smoke가 라벨 assert 안 함 → 프롬프트 판별 정확도는 live로 영원히 미검증. **J1 튜닝 브리프에 별도 deterministic 벤치마크(fake 회귀 라벨 + real 정확도) 설계를 포함해야 함**. 검증 기록 §3 범위 한계 명시.
- **#3 비결정성 정밀화**: 감사 재실행 → `update`→conflict 2회 일관(체계적 편향, J1 우선 타깃), `no_change` 변동(샘플링). 검증 기록 §3 반영.

## 3차 작업 — 감사 비차단 항목 코드 보강 (문서 아닌 실제 코드/테스트)

오너 지시: 검증기록(문서)이 아니라 개발한 것 중 **테스트/비차단 항목을 실제로 코드 보강**. 두 감사의 비차단 관찰 중 코드로 고칠 수 있는 것(튜닝 제외)을 실제 수정:

- **LLM 감사 #1 (gateway 컨테이너 관통 편중) → 신규 smoke로 해소**: provider/planner/compare judge는 인프로세스 ASGI라 gateway *컨테이너* HTTP는 deployed e2e에서만 간접 검증됐다. `scripts/gateway_generate_live_smoke.py` 신규 — gateway 컨테이너 `GET /health` + `POST /v1/generate`를 직접 POST해 계약 응답 shape(text·finish_reason·usage.*_tokens) assert. 실행 PASS(`ok:true`, "연결 확인 완료" 에코, usage 28 tokens). 격리된 컨테이너 gateway→llama 경로 커버.
- **인덱싱 감사 #3 (Mongo smoke doc 누적) → self-cleanup + 일회성 sweep**: `phase2b_candidate_index_live_smoke.py`(내 스크립트) + `phase2b5_memory_reindex_live_smoke.py`에 `_cleanup_mongo_docs`(best-effort, 결과 안 가림) 추가 — 각 run이 자기 project_id의 job/task/candidate·memory/index_sync_log doc을 삭제. 재실행 시 누적 0 실증(cleanup 추가 후 run → `remaining smoke-* docs: 0`). 기존 누적분(analysis 7×3 + index_sync_logs 14 + memory_entries 2 = 37건)은 일회성 sweep으로 삭제(0 잔여).
- **LLM 감사 #2 (라벨 품질 벤치마크)**: J1 튜닝 과제라 이번 제외(오너 지시). 착수 브리프에 deterministic 벤치마크 요건으로 남김.

검증: 회귀 749 passed / 48 skipped(신규 smoke·cleanup 모두 pytest 미수집·프로덕션 코드 무변). candidate/memory smoke 재실행 PASS + cleanup 0 잔여, gateway smoke PASS.

## 4차 작업 — (c) character 별칭 semantic 보강 (SoT v1.6.62)

오너 선택: 풀스택 머신 확인 → 서브 머신 막힘 후보였던 **(c) character 별칭/동명이인 semantic**을 여기서 진행.

### 착수 결정 브리프 + 오너 결정

- 신규 브리프 `plans/02b-7-character-alias-homonym-decisions.md`. **계약 충돌을 먼저 surface**: 2B.3 D2=A가 "별칭/동명이인은 merge/split review 후보(**자동 병합 없음**)"로 잠갔고, (c)는 그 경계를 확장 → 임의 구현 금지, 오너 확정 요청(CLAUDE.md §1).
- 두 실패 모드가 메커니즘 반대임을 명시: 별칭(false-negative, name-key=0에서 매칭 *추가*) vs 동명이인(false-positive, name-key=1에서 매칭 *반증*).
- **오너 결정: D1=A(탐지만, 자동 병합 없음)·D2=A(별칭만 먼저)**. D3~D8 추천 잠금.

### 구현 (계약 확장 + off 기본)

- `analysis/compare.py`: `AnalysisCompareService.alias_matcher: SemanticMemoryMatcher | None` 주입 seam 추가. `_compare_candidate`가 결정적 name-key 매칭 0 + scope≠None(character)일 때만 alias 조회 — 히트 시 `conflict`(matched_memory_id=canonical, judge 미호출). name-key≥1은 종전 judge 경로 불변(alias 미호출). 2B.6 `EmbeddingSemanticMatcher`를 그대로 재사용(character candidate → `memory_type="character_observation"` 필터 + `name\nobservation` projection이 쓰기와 일치).
- `main.py`: `_build_semantic_matcher`를 `_build_memory_semantic_matcher(threshold_env)` 공유 빌더로 리팩터 + 신규 `_build_character_alias_matcher`(env `ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD`, 기본 off). fail-fast guard(CHROMA_HOST 有·EMBEDDING_SERVICE_URL 無)는 env명 동적 포함으로 재사용.
- `apply.py`는 무변경 확인 — conflict 브랜치가 이미 `matched_memory_id`를 review_queue로 전달(alias conflict가 review 큐를 풍부하게 함, 안전).

### 회귀 + 라이브

- 회귀 +6: `tests/test_analysis_compare.py::CharacterAliasTest` 4(alias→conflict+matched id·judge 미호출 / below-threshold create / off 기본 create / same-name 결정적 우선 — StubEmbedding에 candidate 텍스트를 빼서 alias 오호출 시 raise로 증명) + `tests/test_analysis_compare_api.py` 2(alias wiring fail-fast·off 기본 none). **755 passed / 48 skipped**(종전 749). `git diff --check` clean.
- **라이브 관통 PASS**: 신규 `scripts/phase2b7_character_alias_live_smoke.py` — Mongo promote→worker drain→실 Chroma `memory_vectors`→compare alias(실 BGE-m3-ko embedding + Chroma query_similar). `철수`(별칭)→`conflict`+canonical id, `영희`(타인)→`create`, threshold 0.7. `memory_backend: chroma+elasticsearch`, self-cleaning.
  - **구현 중 잡은 smoke 버그**: canonical을 compare와 같은 job_id로 승격 → self-exclusion(D6)이 배제해 첫 run이 `create`로 나옴. canonical job을 `smoke-job-prior`로 분리해 해소(프로덕션 코드 아닌 smoke 결함).
  - **정직성(D5/D7)**: 이 smoke는 **관통·wiring 검증**이지 라벨 정확도·threshold 실값 캘리브레이션이 아니다. 별칭/타인 2경계만 확인. 실 cosine 분포 관찰→threshold 확정은 후속.

### 오너 독립 적대적 검증 PASS + 후속 보강

- **검증 기록**: `docs/verifications/2026-07-12/character_alias_semantic.md` — **PASS(조건 없음)**. 경계 매트릭스 10행 빈 cell 없음(직접 5 + 위임 5, `EmbeddingSemanticMatcher` 동일 클래스 인스턴스라 위임 타당), judge 물리적 우회·`apply.py:118` review_queue 전달·`scope.py:37` character 한정을 재도출로 확인, pytest 755/48 독립 재현.
- **비차단 관찰 4건 처리**:
  - **Obs2(alias 경로 self-exclusion 직접 회귀 부재) → 보강**: `test_alias_self_exclusion_same_job` 추가 — canonical을 같은 job으로 승격 시 alias 경로가 self-exclusion으로 canonical을 drop해 `create`(conflict 아님). **라이브 smoke가 처음 밟은 그 시나리오를 직접 잠금**(under-strict).
  - **Obs4(alias on + scope-less 조합 회귀 부재) → 보강**: `test_alias_matcher_does_not_affect_scopeless_candidates` 추가 — alias matcher 있어도 event(scope=None)는 alias 분기 미진입 → `create`. mutation(`scope is not None` 제거)으로 event 테스트 FAIL 실증(가드 bite).
  - **Obs1(SoT 산문 단락 버전 순서) → 보류**: v1.6.62는 47(직전 최대) 뒤라 오름차순상 타당. 45/46/47 역순은 **내가 만들지 않은 기존 부채**라 §3 surgical(내 mess만 정리) 원칙으로 미변경.
  - **Obs3(rationale에 canonical id 사용) → 코드 무변**: SoT/브리프가 rationale 리터럴을 계약으로 고정 안 함. id가 이름보다 정확한 영구 참조라 그대로 유지(검증자도 무방 판정).
- 회귀 +6→**+8**, 전체 **757 passed / 48 skipped**. Obs4 가드 mutation bite 재실증.

## 5차 작업 — Phase 6 candidate edit (SoT v1.6.66)

오너 선택: 튜닝 계열((b-4)·(c-2) threshold·2B.6·J1)을 제외한 다음작업 → **Phase 6 UI 잔여**. 남은 항목이 전부 미확정 오너 결정에 묶여 있어(README §37·SoT 변경 규칙 #3) 먼저 결정을 받음. 오너 결정: **다음 slice=Candidate edit 백엔드**, **edit 반영=원 후보의 새 version**.

### 착수 결정 브리프 + 오너 결정

- 신규 브리프 `plans/06-candidate-edit-decisions.md`. review action 3종(approve/reject/edit) 중 approve·reject는 v1.6.61 완료, 마지막 edit을 연다(수용 기준 §60).
- **오너 결정 D1=원 후보의 새 version**: 편집값으로 candidate의 새 version(append-only)을 mint→confirm→canonical 승격, 원 후보는 보존.
- D2~D6은 D1이 강제하는 파생 계약 — 임의 선택이 아니라 기존 패턴 재사용임을 브리프에 명시(edit-and-confirm 단일 액션·`superseded` terminal·기존 unique index 재사용 idempotency·근거/provenance/confidence 보존·confirm 선례 재사용). 경계 매트릭스 13행.

### 구현 (기존 머신 재사용, 신규 repo 메서드 0)

- `analysis/models.py`: `AnalysisCandidateStatus.SUPERSEDED` 신규 terminal(edit 전용) + `AnalysisCandidate.supersedes_candidate_id: str | None = None`(default None → 기존 생성부 전부 유효, surgical).
- `analysis/service.py`: `AnalysisService.edit_candidate`(+`CandidateEdit`). idempotency는 successor의 `logical_key=f"edit:{원본id}"`가 기존 `(project,task,logical_key)` unique index를 재사용 — `find_candidate_request`로 replay 감지, 동시성은 두 번째 insert가 `DuplicateAnalysisCandidateRequest`→승자 재조회(promote 선례 동형). 신규 repo 메서드 불필요. append-only: successor(confirmed) insert 먼저 → 원본 `superseded` `update_candidate`.
- `analysis/candidate_review.py`: `CandidateReviewService.edit`(+`CandidateEditResult`). confirm 선례 미러 — edit_candidate → promote_candidate(successor, MANUAL) → 원본 de-index(CANDIDATE_REMOVED) + 원본 conflict resolve(edit=승인 계열이라 dismiss 아님). replay면 side effect 미반복.
- `analysis/mongo_repository.py`: `_candidate_doc`/`_to_candidate`에 `supersedes_candidate_id` 직렬화(`.get()` 하위호환). 원본 status 전이는 기존 `update_candidate`의 `$set status`가 그대로 커버.
- `main.py`: `EditCandidateRequest{payload}` + `POST /projects/{id}/analysis/candidates/{cid}/edit` + `_candidate_edit_payload`. 에러 매핑: 404(missing/cross-project) / 409(terminal 후보) / 400(invalid payload, `InvalidAnalysisCandidate`).

### 회귀 (양방향 guard)

- 회귀 +15: `tests/test_candidate_review.py::EditTest` 9(version mint+supersede+promote[링크=successor]·근거 보존·replay 무중복·one-shot 2차 payload가 첫 version replay·needs_review set에서 원본+successor 배제·invalid payload 원본 불변·terminal 후보 409·optional deps·404×2) + `TransitionStateMachineTest.test_superseded_is_not_a_transition_target` 1(over-strict: `superseded`가 confirm/reject 전이 채널로 도달 불가) + `tests/test_analysis_apply_api.py::EditCandidateApiTest` 5(200 flow+inbox drop·replay·400·409·404×2).
- 전체 **798 passed / 48 skipped / 101 subtests**(종전 783). `git diff --check` clean.

### 남은 미확정 (Phase 6 UI slice 유지)

- 부분 승인/부분 retry(create/update/add_evidence/conflict별 세분 승인)·entity merge/split inbox 액션 노출·상태 변경 invalidate 범위·frontend(framework 미확정). candidate edit 반영 위치만 v1.6.66으로 확정.
- **실 Mongo edit round-trip**(원본 superseded `$set` + successor insert 원자성, unique index 동시성)은 sandbox 밖 live 후속.

### 오너 독립 적대적 검증 조건부 합격 → B1 closure

- **검증 기록**: `docs/verifications/2026-07-12/candidate_edit_backend.md` — 브리프 매트릭스 13행을 lock list로 세워 코드·테스트·스펙을 대입하고 6개 mutation으로 guard bite를 적대적 증명. **조건부 합격**: 12/13행 잠김, 5/6 mutation(M1·M2·M4·M5·M6) bite 실증, 계약 자체 무모순, 798/48/101 독립 재도출.
- **B1(차단) — 매트릭스 행 7 "원본 conflict resolve(dismiss 아님)"의 over-strict 미잠금**: 기존 edit 테스트가 `queue.list_open("p1")==()`만 검사 → RESOLVED/DISMISSED 구분 불가. 검증자 mutation M3(`resolve_for_candidate`→`dismiss_for_candidate`)가 bite하지 않음(22 passed). 구현 자체는 correct(`candidate_review.py:154` resolve 호출), 결함은 테스트 coverage.
  - **보강**: `_enqueue_conflict` 헬퍼가 엔트리를 반환(additive)하도록 하고, `test_edit_mints_confirmed_version_supersedes_and_promotes`에 `queue.get(...).status is ReviewQueueStatus.RESOLVED` over-strict assertion 추가. `ReviewQueueService.get`이 status를 노출하므로 헬퍼 신설 불요.
  - **bite 재실증**: M3 재적용 시 `AssertionError: DISMISSED is not RESOLVED`로 FAIL, 복원 후 22 passed. edit 경로만 잠금(기존 confirm/reject의 동일 `list_open==()` 패턴은 내가 만든 mess가 아니라 §3 surgical로 미변경).
  - 전체 **798 passed / 48 skipped**(assertion 추가는 기존 테스트 보강이라 카운트 불변), `git diff --check` clean.
- **비차단 H1~H3(acknowledged, 결함 아님)**: H1 edit 2-연산 원자성(successor insert + 원본 supersede 별도 write, live 후속 acknowledged)·H2 status(409) vs payload(400) 우선순위 계약 미명시(현재 status 우선, 합리적)·H3 in-memory duplicate 미감지(동시성 잠금은 mongo에서만 live, 기존 구조). 코드 무변.

## 6차 작업 — Phase 6 Review Inbox 액션 어포던스 (SoT v1.6.67)

오너 선택: 튜닝 제외 다음 Phase 6 UI 백엔드 slice → **Review Inbox 액션 어포던스**(候補: 부분 승인 / merge-split 일반화 중 오너 선택). 방금 커밋한 AGENTS.md 가이드라인(owner-level 결정 blocking 시 코드 전 decision brief)대로 옵션 테이블로 D1~D3 확정 후 구현.

### 착수 결정 브리프 + 오너 결정

- 신규 브리프 `plans/06-review-inbox-affordances-decisions.md`(새 AGENTS.md 구조: Decision needed·Options table·Recommendation·Follow-up·Deferred + 경계 매트릭스 11행).
- **오너 결정 D1=자격 주석형 descriptor**(`{action, eligible, reason}` — 불가 이유까지)·**D2=candidate+conflict+gate finding 전부**·**D3=list+detail 둘 다**.

### 구현 (read-only 어포던스 계산, 도메인 write·상태 무변)

- `analysis/review_inbox.py`: `ActionAffordance` descriptor + 순수 함수 `candidate_affordances`(confirm/reject/edit 항상 eligible — inbox는 needs_review·미승격만 노출)·`conflict_affordances`(reconciliation.py 자격 규칙 그대로: merge=character+matched canonical, split=character; 불가 이유 문자열)·`gate_finding_affordances(is_open)`(resolve/dismiss=open일 때만). gate 함수는 `is_open: bool`을 받아 review_inbox가 context_search.gate_findings에 의존하지 않게 함(모듈 경계).
- `main.py`: `_affordance_payload` serializer + `_review_inbox_payload`에 candidate `actions`(list+detail) + detail conflict `actions` + `_gate_finding_payload`에 `actions`(review-inbox·`/gate-findings` 양쪽 공유 serializer라 어디서든 노출).
- **자격이 거짓말 안 하도록** reconcile 실제 authority와 일치 확인: 둘 다 character-only, merge만 matched 필요(reconciliation.py:69-74). merge 자격은 resolved `matched_memory` 실체 기준(matched_memory_id 있으나 memory 유실 시 merge 실패하므로 eligible=false가 정직, inbox detail이 이미 resolved만 노출하는 것과 정합).

### 회귀 (양방향 guard)

- 회귀 +7: `ReviewInboxAffordanceTest` 5(pure: candidate 전부 eligible·character-no-matched merge만 차단[split은 matched 불요]·비-character 둘 다 차단·gate open eligible·gate terminal 차단) + `ReviewInboxApiTest` 2(HTTP: list item+gate 어포던스·detail item+character-matched conflict merge/split eligible·전용 `/gate-findings` actions).
- character+matched(merge eligible) 경계는 실객체가 흐르는 HTTP detail 테스트로 잠금(순수 테스트는 matched=None 케이스만 → MemoryEntry 구성 회피).
- 전체 **805 passed / 48 skipped / 101 subtests**(종전 798). `git diff --check` clean.

### 남은 미확정 (Phase 6 UI slice 유지)

- 부분 승인/부분 retry·merge/split를 event/open_question로 일반화·상태 변경 invalidate 범위·frontend(framework 미확정). 어포던스는 선언만 추가.
- descriptor에 action별 href/route(HATEOAS)는 미포함(프론트가 이름→경로 매핑, 필요 시 additive 확장 여지).

### 오너 독립 검증 2건 합격 + 비차단 hardening 보강

- **검증 기록**: `docs/verifications/2026-07-12/candidate_edit_b1_closure.md`(v1.6.66 B1 closure 재검증 → **조건부→합격 승격**)·`docs/verifications/2026-07-12/review_inbox_affordances.md`(v1.6.67 → **합격, 조건 없음**). 어포던스 매트릭스 11행 전수 잠금, 자격 규칙 변형 4종(MA·MB·MC·MD) 전부 bite.
- **보강 적용(사용자 지시 "보강 후 커밋")**:
  - **B1 H1(confirm/reject `list_open==()` gap)**: edit는 B1 closure로 잠갔으나 confirm/reject(이전 슬라이스)는 여전히 `list_open==()`만 검사해 resolve/dismiss 구분 못 하던 기존 부채. 이번에 사용자 명시 지시로 §3 예외 적용 — `test_confirm_...`에 `status is RESOLVED`, `test_reject_...`에 `status is DISMISSED` over-strict assertion 추가. **이제 3개 review action(confirm→resolve·reject→dismiss·edit→resolve) 모두 conflict-queue 상태 방향 일관 잠금.**
    - **bite 재실증**: reject `dismiss→resolve`(고유) → reject 테스트 260行 FAIL; confirm/edit `resolve→dismiss`(전역) → confirm 테스트 201行 FAIL. 복원 무결성 grep 확인(96 resolve/117 dismiss/154 resolve).
    - **repro 정정(검증자 지적)**: 이전 candidate_edit_backend.md의 M3 sed가 동일 들여쓰기라 confirm 첫 매치를 바꿨음(결론은 유효했으나 repro 부정확) — 이번엔 고유 문자열(dismiss)·전역+타겟 테스트로 정확히 타겟.
  - **어포던스 H2(reason 문자열 계약 미고정)**: `reason`은 display text이고 **machine contract는 `action`+`eligible`**임을 브리프·SoT에 명시(소비자는 reason 문자열 pattern-match 금지, localization은 계약 bump 불요).
  - **어포던스 H1(row 11 read-only)**: 순수 함수라 side effect 자체가 없어 의미 있는 assertion 부재 → 정적 커버 유지(검증자 판정 수용, 코드 무변).
- 전체 **805 passed / 48 skipped**(confirm/reject assertion 추가는 기존 테스트 보강이라 카운트 불변), `git diff --check` clean.

## 7차 작업 — Phase 5.1 Writing 생성 (SoT v1.6.68)

방향 결정: Phase 6 리뷰 백엔드는 거의 완성(frontend 미확정으로 소비자 없음)이고, 순차 계획상 앞이던 **Phase 5(글 생성)가 미구현**임을 확인 → 오너가 Phase 5 착수 선택. `agent_loop/registry.py`에 `WRITING_GENERATE` 프로파일만 있고 실제 생성 서비스는 없었음(입력 인프라 ContextPackage·Gateway는 준비 완료).

### 착수 결정 브리프 + 오너 결정

- 신규 브리프 `plans/05-writing-generation-decisions.md`(AGENTS.md 구조 + 경계 매트릭스 10행). Phase 5는 대형이라 첫 slice를 최소 end-to-end로 스코프.
- 핵심 판단: **의미 있는 Writing Gate(do_not_use/POV 위반을 프로즈에서 탐지)는 결정적 문자열 매칭 불가·LLM 기반 필요** → Gate는 독립 slice.
- **오너 결정 Q1=생성만**(Gate 다음 slice)·**Q2=평문 프로즈**(모델은 프로즈만, 서비스가 WritingCandidate 래핑 — 로컬 Gemma의 긴 한국어 창작 프로즈를 JSON string에 넣는 fragility 회피). 파생 D3~D7은 코드베이스 패턴에서 도출(continue_scene 한정·직접 Gateway 1-turn·draft_patch·project isolation·context_search→generate).

### 구현 (신규 writing/ 패키지)

- `writing/models.py`: `WritingRequest`/`WritingBrief`/`WritingCandidate` + `WritingTaskType`(continue_scene)/`WritingOutputType`(draft_patch). WritingCandidate는 self-report 필드(self_reported_constraints)를 계약에 정의하되 slice 1은 비움(Gate slice가 채움). status는 항상 candidate.
- `writing/prompt.py`: master system prompt(writing_agent_prompt §6.1 로컬변형 §17.1) + `format_context_package`(§8.1 컴팩트: do_not_use→constraints→macro→micro 우선순위, candidate origin "candidate (uncertain)" 라벨) + `build_writing_request`(system+user 조립).
- `writing/service.py`: `WritingService.generate` — 1-turn Gateway(compare_judge 패턴, 단 평문이라 JSON parse/repair 불요), 평문→WritingCandidate 래핑. `WritingError`(validation)·`seed_writing_template`. ProviderError는 삼키지 않고 전파(성공 위장 금지). 결정적 안전선: task_type≠continue_scene·빈 instruction·project isolation(request.project_id≠package.project_id)·brief project.
- `main.py`: `_default_writing_service`(LLM_GATEWAY_BASE_URL env gating, compare judge 선례)·create_app `writing_service` 주입·`POST /projects/{id}/writing/generate`(context_search로 package 조립→generate; 미구성 503·WritingError/task 400·ProviderError 502·budget 504)·`_WRITING_CONTINUE_SCENE_NEEDS`(CURRENT_SCENE/RECENT_SCENES/CANONICAL_MEMORY).

### 회귀 (양방향 guard)

- 회귀 +17: `tests/test_writing.py` — prompt 조립 4(do_not_use 우선·canonical/candidate 라벨·instruction/excerpt/context 포함·brief) + generate 7(평문 래핑·status candidate·ProviderError 전파·task/instruction/project isolation/brief project 검증·template 부재) + HTTP 6(200 orchestration+query=instruction·writing 미구성 503·context_search 미구성 503·unsupported task 400·missing project 404·ProviderError 502).
- 테스트 셋업 버그 1건 잡음: fake context search가 고정 project_id를 반환해 project isolation 검증에 걸림 → `replace(package, project_id=request.project_id)`로 실제 동작 미러링(수정).
- 전체 **822 passed / 48 skipped / 101 subtests**(종전 805). `git diff --check` clean.

### 남은 미확정 (후속 slice)

- Writing Gate(pass/revise/retrieve_more/needs_user_review/block, LLM 기반 do_not_use/POV 검증)·accept→save→analysis 재진입·revise/retrieve_more 재생성 루프·구조적 self-report(candidate_claims/new_memory_hints/risk_notes)·revise/outline/critique/rewrite_style task·Continuity/POV/Voice Gate 고도화·editor 적용 단위.
- **실 LLM(12B) live smoke**(실제 continue_scene 생성 품질·do_not_use 준수 관찰)는 sandbox 밖 후속.

### 오너 독립 검증 합격(조건 없음) + 비차단 hardening 보강

- **검증 기록**: `docs/verifications/2026-07-12/writing_generation.md` — **합격(조건 없음)**. 핵심 클레임 3개(평문이라 JSON parse/repair 불요·ProviderError 전파·status 항상 candidate) 코드로 직접 확인, 매트릭스 10행 전수 named test 잠금, mutation 6종(MW1~MW6: status→final·ProviderError 삼킴·isolation 제거·task 체크 제거·do_not_use 순서 뒤바꿈·candidate 라벨 오) 전부 bite.
- **보강 적용(사용자 지시 "보강 후 커밋")**:
  - **H2(orchestration 에러 브랜치 회귀 부재)**: 코드는 `ContextSearchBudgetExceeded→504`·`ContextSearchFailed→502`를 매핑하나 회귀가 없어 orchestration 에러 매핑이 부분만 잠겨 있었다(검증자는 "보고 정확성"으로 표현했으나 이면에 untested branch). HTTP 회귀 +2 추가(504 budget·502 context 실패). `_FakeContextSearch`에 `error` 주입 경로 추가. **bite 재실증**: `status_code=504→500` 변형 시 504 테스트 FAIL, 복원 후 통과(504 매핑 2개 grep 확인).
  - **H1**(self_reported_constraints 빈 값): Gate slice가 채우는 forward-defense(models docstring·브리프·SoT 명시). 코드 무변, Gate slice 착수 시 실제 채움 추적.
  - **H3**(평문 보장은 master prompt 지시 의존, live에서만 검증)·**H4**(budget 5차원 중 max_tokens만, agent_loop runner 보류 연동): 기존 범위/아키텍처 제약, 코드 무변.
- 회귀 +17→**+19**, 전체 **824 passed / 48 skipped**. `git diff --check` clean.

## Next steps

- **(Phase 5 후속)**: Writing Gate slice(LLM 기반 do_not_use/POV 검증) → accept→save 재진입 → 구조적 self-report. 각 착수 브리프 필요.
- **(Phase 6 UI 잔여)**: 부분 승인/부분 retry·merge/split 일반화(event/open_question)·candidate edit **실 Mongo live** 관통·frontend(보류).
- **(c) 후속 잔여**: 동명이인 false-positive 반증(name-key=1 분기, 별도 증분), character alias threshold 실값 캘리브레이션(라이브 cosine 분포 배치, off→발화), merge/split write 경로(Phase 6 UI).
- **여전히 sandbox 밖 남은 것**: 2B.6 event/open_question semantic threshold 실 캘리브레이션, compare judge J1 프롬프트 판별 튜닝(deterministic 벤치마크 요), (b-4) hybrid 튜닝(실 데이터).
- HANDOFF Next Tasks #1 남은 후보: (b-4)·Phase 6 UI(frontend 미확정이라 백엔드 API 확장 위주). 다음 slice 오너 선택 대기.
- **오너 지시 시** 신규 smoke 3개(gateway·candidate·**alias**) + (c) 구현 커밋.
- 인프라 스택은 기동 상태로 남겨둠; 정리 필요 시 `docker compose down`.

## 8차 작업 — Phase 5.2 Writing Gate 착수 브리프

### Goals

- HANDOFF의 권장 다음 타깃인 Writing Gate의 정본 범위를 확인하고, 구현 전에 필요한 owner-level public contract 결정을 표면화한다.

### Completed work

- `docs/plans/05-writing-gate-decisions.md`를 신규 작성했다.
  - 기존 정본이 잠근 다섯 decision literal과 LLM 의미 검증 요구를 보존했다.
  - D1 판정 방식, D2 공개 결과 schema, D3 decision 처리 의미/우선순위, D4 첫 API 경계의 현실적인 선택지를 장단점과 함께 정리했다.
  - 추천안을 D1=A(별도 1-turn)·D2=B(구조화 findings)·D3=A(판정 전용)·D4=A(별도 evaluate API first)로 제시하고, 양방향 회귀 경계 9개를 적었다.
- `HANDOFF.md`의 Owner Decisions Needed와 Next Tasks를 현재 blocking 상태로 갱신했다.

### Issues found

- 문제: `05-writing-ai.md`는 Gate decision 후보와 LLM 기반 필요성만 정의하고, finding schema·decision별 자동 처리·API 경계는 미확정이었다.
- 원인: v1.6.68에서 생성만 의도적으로 먼저 구현하고 Gate를 별도 slice로 유예했다.
- 해결/결과: 구현자가 public contract를 추측하지 않도록 owner decision brief로 전환했다. 오너 선택 전 코드 변경은 하지 않았다.

### Decisions

- 사용자 결정: HANDOFF 후보 중 Writing Gate를 다음 실 타깃으로 선택했다. 생성 slice의 자연스러운 후속이며 accept/save와 구조적 self-report보다 먼저 진행한다.
- 아직 필요한 결정: D1~D4. 추천 이유는 로컬 Gemma 단계에서 평문 생성 계약을 보존하고 fake provider로 Gate 계약을 독립 검증하기 위함이다.

### Next steps

- 오너가 `05-writing-gate-decisions.md`의 D1~D4를 선택하면, 선택을 브리프·SoT에 반영하고 경계 테스트부터 구현한다.

## 9차 작업 — Phase 5.2 Writing Gate 구현 (SoT v1.6.69)

### Goals

- 승인된 D1=A·D2=B·D3=A·D4=A를 정본에 반영하고, 생성과 분리된 LLM Writing Gate를 public API까지 구현한다.
- do_not_use/POV/continuity의 under-strict와 정상 prose의 over-strict 경계를 구조화 findings와 다섯 decision으로 잠근다.

### Completed work

- `writing/models.py`: `WritingGateDecision`, `WritingGateFindingType`, `WritingGateSeverity`, `WritingGateFinding`, `WritingGateResult` 계약을 추가했다.
- `writing/gate_prompt.py`: ContextPackage·원 요청·candidate를 별도 1-turn terminal JSON 판정 prompt로 조립했다.
- `writing/gate.py`: strict parser와 side-effect-free `WritingGateService.evaluate`를 구현했다.
  - 우선순위 `block > needs_user_review > retrieve_more > revise > pass`를 모델 주장에 맡기지 않고 findings로 재계산·검증한다.
  - do_not_use/POV finding은 blocking error로 약화 불가하며, evidence가 실제 candidate text에 포함되는지 재검증한다.
  - request/candidate/package project와 request id를 provider 호출 전에 검증한다.
- `main.py`: 기본 Gate wiring과 `POST /projects/{id}/writing/gate`를 추가했다. Gate는 project-scoped ContextPackage를 다시 구성하되 검색·재생성·저장은 자동 실행하지 않는다. malformed model output/기타 provider=502, provider timeout=504, invalid input=400, 미구성=503이다.
- `tests/test_writing_gate.py`: contract/service/HTTP 회귀 19개(+26 subtests)를 추가했다. 다섯 decision, 우선순위, hard finding 약화 금지, evidence grounding, malformed schema, project/request/package isolation, dependency/provider/context-search error mapping을 양방향으로 검사한다.
- 브리프·`05-writing-ai.md`·SoT·CHANGELOG·HANDOFF를 v1.6.69 상태로 갱신했다.

### Issues found

- D3 오해 가능성: 브리프의 B는 즉시 자동 전체 재생성이고, 오너 의도는 위반 판정 단위만 부분 재생성하는 느슨한 연결이었다. 현재 부분 patch anchor가 없어 B를 택하면 의도와 반대가 된다. D3=A로 확정하고 finding별 evidence/recommended_decision을 후속 연결점으로 남겼다.
- 초기 HTTP 분류에서 malformed LLM JSON이 입력 오류 400으로 합쳐질 수 있었다. 입력 `WritingGateError`와 `InvalidWritingGateResult`를 분리해 provider 결과 오류 502로 바로잡았다.
- 브리프 HTTP matrix의 candidate-not-found는 candidate가 아직 비영속 inline 입력인 현재 API와 맞지 않았다. project 404만 남기고 candidate 영속화 후속 전까지 해당 분기를 제거했다.

### Decisions

- 사용자 결정 D1=A: 내부 LLM 호출 수보다 정확도를 우선한다.
- 사용자 결정 D2=B: decision과 구조화 findings를 함께 반환한다.
- 사용자 의도를 반영한 D3=A: Gate는 판정만 하며, 부분 revise는 evidence anchor를 소비하는 후속으로 느슨하게 연결한다.
- 사용자 결정 D4=A first: 별도 evaluate API로 시작하고 generate→gate 합성은 additive 확장 가능하게 둔다.

### Verification

- focused: `python3 -m pytest -q -p no:cacheprovider tests/test_writing_gate.py tests/test_writing.py` → **38 passed / 26 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **843 passed / 48 skipped / 127 subtests**.
- `python3 -m py_compile`(Gate/prompt/main) 및 `git diff --check` 통과.

### Next steps

- 후보: accept→save→analysis 재진입, finding evidence 기반 부분 revise/retrieve_more orchestration, 구조적 self-report.
- 실 Gemma live에서는 strict JSON 준수와 한국어 do_not_use/POV/continuity 판정 품질을 별도로 관찰한다.

## 10차 작업 — Phase 5.3 accept→save→analysis 착수 브리프

### Goals

- Writing Gate 다음 핵심 흐름인 accept→Core SOT save→Analysis 재진입의 미확정 public write 계약을 구현 전에 분리한다.

### Completed work

- `docs/plans/05-writing-accept-decisions.md` 신규 작성: D1 base version/stale, D2 append literal, D3 Gate 신뢰, D4 idempotency, D5 analysis 재진입 깊이의 전체 옵션과 추천을 정리했다.
- HANDOFF Owner Decisions Needed/Next Tasks에 Phase 5.3 결정 대기를 반영했다.

### Issues found

- 현재 save API는 완성 `raw_text`만 받고 WritingCandidate는 `draft_patch`라 merge literal이 없다.
- GateResult는 비영속이라 client 제출 결과를 신뢰할 수 없고, accept 시 재평가 또는 persistence 결정이 필요하다.
- save는 정본 commit이고 analysis run은 LLM failure가 가능해 한 HTTP 성공/실패로 묶으면 partial-success 의미가 생긴다.

### Decisions

- 사용자 지시: Writing Gate 커밋 후 HANDOFF의 다음 작업을 진행한다. 다음 타깃을 accept→save→analysis 재진입으로 선택했다.
- D1~D5는 owner-level public contract라 추천안을 제시하고 선택 전 코드는 시작하지 않았다.

### Next steps

- 오너가 D1~D5를 확정하면 브리프/SoT에 rationale을 기록하고 경계 테스트부터 구현한다.

### 후속 owner 결정 반영 및 추가 blocking 발견

- D1=A·D3=A·D4=A를 추천안대로, D2=A first→C 확장·D5=A first→C 확장으로 사용자 결정 반영했다.
- 구현 직전 HTTP 경계를 매트릭스로 옮기며 D6(Gate non-pass status/envelope)와 D7(save commit 후 analysis job write 실패 partial-success)을 새로 발견했다. 두 항목은 public 성공/재시도 의미이므로 추천 D6=A·D7=A를 추가하고 코드 착수 전 결정을 요청했다.

## 11차 작업 — Phase 5.3 accept→save→analysis 구현 (SoT v1.6.70)

### Goals

- Gate를 통과한 continue_scene patch만 latest draft에 idempotent 저장하고 새 snapshot으로 pending Analysis job을 생성한다.
- non-pass와 cross-store partial failure를 정본 commit 여부가 숨겨지지 않는 public envelope로 잠근다.

### Completed work

- `writing/accept.py`: `WritingAcceptService`, result/error 계약, 결정적 `_append_patch` 추가.
  - accept replay는 파생 save key의 기존 version을 먼저 찾아 Gate/save를 반복하지 않고 Analysis job을 재유도한다.
  - stale/missing/cross-project/archived를 Gate 전에 검증한다.
  - Gate pass만 save; non-pass는 side effect 없는 정상 result.
  - job write 실패는 saved artifact를 가진 `WritingAcceptAnalysisError`; 계속 실패하는 replay도 같은 partial-success를 보존한다.
- `main.py`: `WritingAcceptRequest`와 `POST /projects/{id}/writing/accept` 추가. 200 accepted/non-pass, 400 invalid, 404 missing, 409 stale/archive, 502 malformed/provider/partial, 504 timeout을 분리했다.
- `tests/test_writing_accept.py`: service 8 + HTTP 7 회귀(+5 invalid subtests). append 3방향, pass/non-pass, stale-before-Gate, same/different key, partial retry convergence, archived replay, missing/invalid/API envelope를 잠갔다.
- 브리프 D1~D7 Resolved, SoT/plan/HANDOFF/CHANGELOG v1.6.70 반영.

### Issues found

- replay에서도 Analysis store가 계속 실패하면 최초 구현은 raw 500으로 샐 수 있었다. replay job 생성도 같은 `WritingAcceptAnalysisError`로 감싸 502 partial-success 계약을 유지했다.
- missing base를 stale 409로 오분류할 가능성을 발견해 base detail 404 확인 후 latest 비교 순서로 고정했다.
- pattern sweep에서 replay lookup이 active-state 검사보다 앞이면 accept 후 archive된 draft가 같은 key replay로 job side effect를 만들 수 있음을 발견했다. Core SOT archive write 정책과 맞춰 project/draft active 검사를 replay보다 앞으로 이동하고 archived replay 회귀를 추가했다.

### Decisions

- 사용자 확정: D2=A first→C client patch 확장, D5=A first→C background run 확장, D6=A, D7=A. D1/D3/D4는 추천 A 유지.

### Verification

- focused(검증 hardening 후): `tests/test_writing_accept.py tests/test_writing_gate.py tests/test_writing.py` → **56 passed / 41 subtests**.
- full(검증 hardening 후): `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **861 passed / 48 skipped / 142 subtests**.
- `python3 -m py_compile`(accept/main), `git diff --check` 통과.

### Next steps

- 구조적 self-report 또는 finding evidence 기반 부분 revise/retrieve orchestration 중 다음 slice 선택.
- D5 C(background Analysis run)는 pending job identity를 그대로 소비하는 additive worker/orchestration으로 확장.

## 12차 작업 — Phase 5.4 structured candidate report 착수 브리프

### Goals

- v1.6.68이 forward-defense로 남긴 빈 구조 필드를 실제로 채우되 평문 prose와 Analysis/canon 경계를 보존한다.

### Completed work

- `docs/plans/05-writing-self-report-decisions.md` 신규 작성: 생성 주체, 최소 typed schema, generate 결합, repair/failure, Gate/Analysis 소비 경계 D1~D5 옵션과 추천.
- HANDOFF Owner Decisions Needed/Next Tasks를 Phase 5.4 결정 대기로 갱신했다.

### Issues found

- prose+JSON 단일 응답은 v1.6.68 Q2 평문 결정을 뒤집는다.
- 아이디에이션의 `related_context_pointers`는 현재 모델 입력에 stable pointer가 없어 그대로 구현하면 id hallucination 위험이 있다.
- agent-loop 종료채널 `self_report=finalize|defer`와 candidate data report가 이름상 혼동될 수 있어 wire field를 분리해야 한다.

### Decisions

- 사용자 지시: v1.6.70 커밋 후 다음 작업 진행. HANDOFF 순서의 구조적 candidate report를 다음 타깃으로 선택했다.
- D1~D5는 public schema와 실패 의미를 바꾸므로 추천안을 제시하고 선택 전 코드는 시작하지 않았다.

### Next steps

- 오너 D1~D5 확정 후 SoT 반영→strict parser 회귀→extractor→generate/Gate 합성 순서로 구현.

### 후속 owner 결정과 D6 blocking

- 사용자 결정: D2=A first→B pointer schema 확장, D3=A 후 별도 B report API 후속 구현 확정, D5=B(Gate+Analysis 모두 report 소비). D1=A/D4=A는 추천 유지.
- D5=B는 Analysis 소비 authority를 새로 연다. source_ref 없이 report에서 candidate를 직접 mint하면 기존 정본/validation 경계를 우회하므로 D6 옵션을 추가했다. 추천 D6=A는 report를 AnalysisJob의 advisory immutable 입력으로 영속하고 runner가 snapshot 독립 extraction prompt에만 보조로 사용하며 direct candidate/memory write를 금지한다.

## 13차 작업 — Phase 5.4 structured candidate report 구현 (SoT v1.6.71)

### Goals

- 평문 생성 계약을 보존하면서 candidate report를 실제 생성하고 Gate·Analysis advisory 경로에 안전하게 연결한다.

### Completed work

- typed claim/hint/risk 모델과 strict report parser(필드/enum/confidence/NaN·bool guard), 별도 extractor+1회 repair를 추가했다.
- 기본 generate가 평문 생성 후 reporter를 느슨하게 합성해 네 필드를 채운다.
- Gate prompt가 report를 typed JSON으로 받고, accept runtime은 서버 report를 pending AnalysisJob advisory copy로 연결한다.
- AnalysisJob/Mongo/SnapshotText/runner prompt가 advisory report를 보존·소비하되 snapshot/source_ref 독립 extraction과 direct candidate/memory mint 금지를 유지한다.
- payload sweep에서 dataclass 내부명(`claim_type/hint_type/risk_type`)이 advisory wire로 샐 가능성을 발견해 public schema의 `type`으로 명시 직렬화하고 회귀로 잠갔다.
- D6=A first→C 확정: 현재 embedded advisory, stable candidate identity 후 별도 report entity+report_id로 승격.

### Issues found

- 아이디에이션 full pointer schema는 현재 extractor 입력에 stable pointer가 없어 id hallucination 위험이 있으므로 A first로 제한했다.
- dataclass 내부 enum field 이름이 advisory wire에 노출될 가능성을 payload sweep에서 발견해 public `type` schema로 명시 직렬화했다.

### Verification

- focused(report/writing/gate/accept/analysis prompt+runner+mongo): **86 passed / 8 skipped / 45 subtests**.
- full: `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **868 passed / 48 skipped / 146 subtests**.
- `python3 -m py_compile`(report/accept/main), `git diff --check` 통과.

### Next steps

- 확정 후속: D3 B `/writing/report` API, D2 B stable context pointers, D6 C candidate/report persistence.

### 독립 검증 PASS 후 hardening

- 검증 기록 `docs/verifications/2026-07-12/writing_accept.md`의 합격 verdict와 H1~H6를 직접 대조했다. 차단 사항은 없었다.
- H1: accept 표면에서 Gate provider unavailable→502/timeout→504, context budget→504/backend→502를 직접 관통하는 HTTP 회귀 추가.
- H2: gate/context 미구성 accept 503 회귀 추가.
- H3: non-pass 4종(revise/retrieve_more/needs_user_review/block)을 전부 parametrize해 동일 no-write outcome 잠금.
- H4: candidate/package 각각의 cross-project 입력이 Gate 전 거부됨을 accept service에서 직접 단언.
- H5: SoT stale 문구를 v1.6.70 paragraph append 확정과 후속 부분 patch 분리로 정정.
- H6: candidate 외곽 whitespace `strip()` 후 append, 내부 whitespace 보존을 브리프에 명문화.
- 직전 Gate B1/B2/B3는 커밋 `ea81eaf`의 named tests(`overstated`, hard finding full boundary, invalid HTTP 400)로 반영되어 있음을 확인했다.

### 독립 검증 조건부 합격 closure

- 검증 기록 `docs/verifications/2026-07-12/writing_gate.md`를 직접 대조했다. 구현은 correct지만 contract-required named test 3곳이 비어 있다는 B1~B3 판정이 타당했다.
- **B1 closure**: lower `revise` finding을 `retrieve_more|needs_user_review|block`으로 과대 판정하는 세 경우를 모두 reject하는 over-strict 회귀 추가. H4도 함께 닫아 `revise→retrieve_more→needs_user_review→block` 전 사슬의 strongest finding 계산을 잠갔다.
- **B2 closure**: `do_not_use|pov` × `(error, revise/retrieve_more/needs_user_review)` 및 `(warning, block/revise/retrieve_more/needs_user_review)` 14개 invalid 조합을 전부 reject하도록 parametrized lock 추가.
- **B3 closure**: 빈 instruction·빈 candidate text·unsupported task type이 각각 HTTP 400인지 직접 단언했다.
- 추가 hardening: package-only cross-project provider-before-call 거부(H5), Gate endpoint context-search budget→504/backend→502, prompt의 evidence 필수 문구(H3), SoT stale 미확정 문구(H2), `writing_agent_prompt.md` §16.2 finding shape(H1)를 v1.6.69와 정합화했다.
- pattern sweep에서 같은 구형 `pov_violation`/`violating_text` 예제가 `contracts.md`와 `mongo_collections.md`에도 반복됨을 확인하고(`git blame`: 2026-06-24 초기 아이디에이션), v1.6.69 exact finding shape로 정합화했다. `mongo_collections.md`에는 Gate persistence/pointer가 아직 후속임을 명시했다. 원본 `abstract.md`는 보존 정책에 따라 변경하지 않았다.
- production Gate 코드는 검증자가 확인한 correct 상태를 유지했다. prompt/doc/test만 보강했다.

### 독립 검증 조건부 합격 closure (self-report v1.6.71)

- 검증 기록 `docs/verifications/2026-07-12/writing_self_report.md`를 직접 대조했다. producer 측(extractor·strict parser·enrich·1회 repair·gate prompt 수신·accept advisory copy + name-leakage guard)은 correct하고 accept 경로 이름 노출 가드는 강하게 잠겨 있으나, contract-required consumer 표면 2곳이 named test로 잠기지 않았다는 B1/B2 판정이 타당했다.
- **사용자 결정**: 오너가 "B1, B2 테스트 추가 + 전체 커밋 + 보강할 부분 다 보강"을 지시했다(구현자 대신 검증자가 보강·커밋 수행). 코드는 correct하므로 production 무변경·test 추가만으로 잠근다.
- **B1 closure**: generate HTTP 테스트가 reporter를 배선하지 않아 응답의 report 필드가 항상 빈 채로 직렬되던 gap을 닫았다. `_FakeReporter`로 4개 report 필드를 채운 candidate를 반환하게 하고, `test_generate_enriches_candidate_report_in_http_response`가 HTTP 응답의 public `type` key + 내부명(`claim_type`/`hint_type`/`risk_type`) 미노출을 단언. HTTP 직렬화를 내부명으로 망가뜨리는 mutation(MUT-2)이 이 test를 FAIL시킴을 실증.
- **B2 closure**: analysis-side advisory 소비 3종을 잠갔다. (1) `_RecordingExtractor`로 report가 부착된 pending job을 run_job했을 때 extractor가 받은 `snapshot.writing_candidate_report`를 단언(runner replace — MUT-B2a FAIL), (2) `build_analysis_extract_request`가 present report를 extract payload에 포함·absent면 null(KeyError 아님)을 단언(prompt_builder — MUT-B2b FAIL), (3) create_job→get_job round-trip으로 advisory 보존을 단언.
- **H3**: gate prompt 직렬화 회귀가 risk_notes만 잠그던 것을 claims·hints의 `type` key + 내부명 미노출까지 확장(MUT-3 FAIL).
- production 코드는 무변경(검증자가 확인한 correct 상태 유지). test만 추가(회귀 +5). mutation 4종 전부 bite, 복구 clean(`diff -q`).
- full suite **873 passed / 48 skipped / 146 subtests**. `py_compile`, `git diff --check` 통과.
