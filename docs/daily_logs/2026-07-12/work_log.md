# Work Log — 2026-07-12

## Goals

- 오너가 선택한 (c-2): 동명이인 반증, character threshold calibration, merge/split write를 구현한다.

- HANDOFF와 2026-07-11 work log를 읽고 다음 작업을 진행한다.
- 오너 지시: "여기는 테스트도 가능한 머신이니까 확인해서 진행" → 이전 세션이 서브 머신에서 막았던 **live 관통 검증**(HANDOFF Next Tasks #2/#3, "코드 완료, sandbox 밖 막힘")을 실 인프라 위에서 실행한다.

## Completed work

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

## Next steps

- **(c) 후속 잔여**: 동명이인 false-positive 반증(name-key=1 분기, 별도 증분), character alias threshold 실값 캘리브레이션(라이브 cosine 분포 배치, off→발화), merge/split write 경로(Phase 6 UI).
- **여전히 sandbox 밖 남은 것**: 2B.6 event/open_question semantic threshold 실 캘리브레이션, compare judge J1 프롬프트 판별 튜닝(deterministic 벤치마크 요), (b-4) hybrid 튜닝(실 데이터).
- HANDOFF Next Tasks #1 남은 후보: (b-4)·Phase 6 UI(frontend 미확정이라 백엔드 API 확장 위주). 다음 slice 오너 선택 대기.
- **오너 지시 시** 신규 smoke 3개(gateway·candidate·**alias**) + (c) 구현 커밋.
- 인프라 스택은 기동 상태로 남겨둠; 정리 필요 시 `docker compose down`.
