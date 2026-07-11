# Work Log — 2026-07-11

## Goals

- HANDOFF와 2026-07-10 work log를 읽고 다음 작업을 진행한다.
- 오너 지시: **가장 작은, 독립적으로(오너 브리프 없이) 진행 가능한 슬라이스**부터 처리 → HANDOFF Project Structure 누락 정합.
- 이어서 오너가 **(e) canonical↔candidate dedup**을 선택(서브 머신이라 라이브 테스트/튜닝 불가 제약). 라이브 없이 가능한지 조사 후 착수.

## Completed work

### HANDOFF Project Structure — `phase3a_rebuild_source_block_index.py` 누락 정합 (문서 전용)

- **선택 근거**: HANDOFF Next Tasks #1의 실 후보((b-4) 튜닝·(c) 별칭 semantic·(e) canonical↔candidate dedup·Phase 6)는 전부 오너 선택 + 착수 결정 브리프가 선행이라 임의 착수 불가. 반면 이 gap은 2026-07-10 work_log:56에서 "인접 gap(수정 안 함, §3 준수) … 필요 시 별도 정합에서 처리"로 명시적으로 남겨둔 자족적 소부채 — 오너 브리프 불필요, 100% sandbox 안 검증 가능, 계약·프로덕션 코드 무변. 오너의 "가장 작은 독립 슬라이스 먼저" 지시에 정확히 부합.
- **문제**: `HANDOFF.md` Project Structure `scripts/` 블록의 glob `phase3a_*_smoke.py`(구 129행)는 `phase3a_deployed_rebuild_smoke.py`는 잡지만 **`phase3a_rebuild_source_block_index.py`(CLI rebuild, `_smoke`로 안 끝남)는 안 잡혀** 목록에 표현이 없다. HANDOFF:11은 이미 이 경로를 "source block index rebuild(HTTP/CLI/deployed smoke)"로 서술하는데 정작 스크립트 목록엔 CLI 진입점만 빠져 있었다.
- **대조 실증**: `ls scripts/` 14개(`__init__.py`·`__pycache__` 제외) 전수를 Project Structure와 대조 → 유일 누락이 `phase3a_rebuild_source_block_index.py` 하나임을 확인(나머지 13개는 명시 또는 glob에 잡힘). 파일은 `scripts/phase3a_rebuild_source_block_index.py:1` docstring "Run Phase 3A explicit source-block index rebuild for one snapshot"로 성격 확인.
- **수정**(외과적, 문서 1파일 1행): 구 129행 glob 나열에서 `phase2a_*_smoke.py` 다음, `phase3a_*_smoke.py` 앞에 `phase3a_rebuild_source_block_index.py(CLI rebuild)`를 명시 추가.

## Issues found

- 없음.

## Decisions

- **SoT 버전 bump 안 함**: 문서(HANDOFF) 1행 정합 — 계약 literal·public interface·SoT 버전·프로덕션 코드 무변, 동작 변화 0. 버전 로그에 항목을 만들지 않는다.

## Verification

- `git diff --check` clean. 변경은 `HANDOFF.md` Project Structure `scripts/` 1행뿐.
- `ls scripts/` 전수 ↔ Project Structure 대조로 이 항목이 유일 잔여 누락임을 재확인(2026-07-10:56 인접 gap closure).

## 2차 작업 — (e) canonical↔candidate 승격 dedup (SoT v1.6.60)

- **선택 근거 / 라이브 가능성 조사**: 오너가 (e)를 선택하며 "서브 머신이라 라이브 테스트·튜닝 불가, 가능한가?"를 물음. 조사 결과 **(e)는 이름과 달리 embedding/semantic 캘리브레이션 불요**. D7이 수용한 중복은 "**승격 후** 같은 지식이 canonical·candidate 양쪽 노출"인데, 이 링크가 결정적으로 존재한다:
  - 승격 시 canonical `MemoryEntry.source_candidate_id = candidate.id`(`memory/service.py:167`) + memory store `find_memory_by_candidate` 조회기(`memory/mongo_repository.py:77`·`InMemoryMemoryRepository:79`).
  - candidate `ContextItem.pointer.document_id = candidate.id`. → "candidate.id == 어떤 canonical의 source_candidate_id"면 같은 지식. **cosine 없이 identity 매칭**이라 100% sandbox 검증 가능.
  - 승격돼도 candidate status는 `needs_review`로 남아(전이는 Phase 6) `list_needs_review_candidates`가 계속 반환하는 게 중복 원인. `context_search/service.py:349-350`의 D5=A 주석("promoted candidates are served by the canonical path instead")은 aspirational이었고 (e)가 이를 실현.
- **오너 결정**(AskUserQuestion 2문, 브리프 `docs/plans/04-canonical-candidate-dedup-decisions.md`): **D1=승격됐으면 항상 억제**(store 권위 — canonical이 같은 package에 있든 없든 억제; merge-only 방식 배제, D5=A 정합)·**D2=지금 retrieval-time interim 억제**(상태 모델·색인 무변; Phase 6 candidate de-index 도입 시 상위집합 흡수 forward-defense).
- **구현**(외과적, additive):
  - `memory/service.py`: `is_candidate_promoted(project_id, candidate_id)` public 메서드(→`repo.find_memory_by_candidate is not None`).
  - `context_search/service.py`: `PromotedCandidateResolver` structural Protocol(`MemoryService` 구조적 충족) + `ContextSearchService.__init__`에 optional `promoted_candidate_resolver`(**미주입 시 억제 없음 = 종전 D7 하위호환**). `_run_candidate_memory_step`이 retrieval 후 kept/suppressed 분할 — suppressed는 `ExcludedHit(record_id, reason="candidate_promoted")`로 trace 기록(hits_considered=전체·items_produced=kept). resolver 예외는 기존 candidate step try/except의 `backend_error` degrade로 접힘(정직한 degrade).
  - `main.py`: `_default_context_search_service`가 `promoted_candidate_resolver=memory` 배선.
- **패턴 sweep(§4)**: candidate item 표면화 경로는 `_run_candidate_memory_step`(`_item_from_candidate` 유일 호출) 하나뿐 — 억제가 이 경로를 덮음. `list_needs_review_candidates`(retriever 내부)는 step을 거쳐 억제되고, Gate `candidate_item_not_allowed`(service.py:1185)는 D2 범위 밖(다른 origin 안전선). 다른 leak 경로 없음.
- **회귀 +6**(양방향 guard):
  - `tests/test_context_search_candidate_memory.py::CanonicalCandidateDedupTest`(5): 승격 억제+trace(under-strict)·혼합 부분억제(양방향)·미승격 유지(over-strict)·resolver 미주입 D7 하위호환(over-strict)·resolver 예외 degrade.
  - `tests/test_memory_phase2b.py::IsCandidatePromotedTest`(1): 승격 링크 양방향 + project/candidate scope.
- **성격**: 새 seam + 동작 확장 → SoT v1.6.60 bump. 계약 literal·public 응답 envelope 무변(억제 candidate가 애초에 package에 안 실림); trace `ExcludedHit.reason` 문자열 `"candidate_promoted"` 신규(내부 trace).

### Verification (2차)

- `python3 -m pytest tests/test_context_search_candidate_memory.py tests/test_memory_phase2b.py -q` → **24 passed**.
- **mutation 재실증**: `_run_candidate_memory_step`의 억제 조건을 `... is not None and False`로 무력화 → 승격 억제·혼합·resolver 예외 degrade 3 test 재실패(under-strict bite 확인), 미승격/미주입 over-strict 2 test는 통과. revert 후 5 passed.
- `create_app` boot: `MemoryService`가 `PromotedCandidateResolver`를 구조적으로 충족(`is_candidate_promoted` callable·미승격 False) 실증.
- 전체: `python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **724 passed / 48 skipped**(종전 718 + 6). `git diff --check` clean.
- 문서: SoT v1.6.60 버전 로그·헤더·§416 body, CHANGELOG, HANDOFF(Current Status·Active Decisions·Owner Decisions·Next Tasks·Verification·Project Structure) 갱신. 브리프 신설.
- **미검증(sandbox 밖)**: 실 배포에서 실 승격 candidate가 억제되는 live 관통(코드는 fake·InMemory repo로 대칭 검증; 실 Mongo `find_memory_by_candidate`는 프로젝트 mongo repo 검증 관례대로 sandbox 밖).

## 검증 후속 보강 (오너 독립 검토 조건부 합격 → 비차단 관찰 I1~I3 closure)

오너가 별도 세션 독립 검토를 수행 → **조건부 합격(CONDITIONAL PASS)**, 비차단 관찰 I1~I3 제기. 각 항목을 **독립 재확인**(단순 수용 아님) 후 타당한 것을 보강했다. 독립 검증 기록: `docs/verifications/2026-07-11/canonical_candidate_dedup.md`(최종 합격).

- **I1 — N>1 전부 승격 경계 미커버**: 기존 `test_mixed_only_suppresses_promoted`는 c1만 승격이라 "전부 승격 시 전부 억제"(early-stop/break 부재)를 잠그지 못함. 코드(`service.py:837-846` 루프)는 이미 올바르나 회귀가 없었다. **`test_all_candidates_promoted_all_suppressed` 신규**(`_PromotedResolver("c1","c2")` → micro 공집합·excluded={c1,c2}·전부 reason=candidate_promoted). mutation 재실증: 억제 무력화 시 이 test FAIL(v1.6.59 I1 parametrization 패턴과 동형).
- **I2 — project scope 배선 미커버(integration)**: unit test `IsCandidatePromotedTest`가 `is_candidate_promoted` scope는 잠그지만, integration에서 resolver가 `request.project_id`로 질의되는지는 미잠금. **`test_resolver_is_queried_with_request_project_id` 신규**(`_ProjectRecordingResolver("project-2","c1")` → request는 project-1 → c1 미억제·`seen_projects`=={project-1}). 하드코딩/candidate-derived project 전달을 방어. mutation 시 resolver 미호출로 bite.
- **I3 — mutation 재실증 증거 보강**: 종전 work_log는 "억제 무력화 → 3 test 재실패"만 기술(v1.6.59의 "revert diff empty 확인" 수준 증거 부족). **엄밀 재실행·기록**:
  - pre-mutation sha256 = `dadbe55336cec68c0c4fdacab6987cecdd311dc43ad30a3a43b59f1aacc48ade`.
  - `self._promoted_candidate_resolver is not None` → `... and False`(억제 완전 무력화) → `CanonicalCandidateDedupTest` **5 failed / 2 passed**(FAILED: promoted·mixed·all-promoted[I1]·project-scope[I2]·degrade / PASSED: 미승격 유지·미주입 하위호환 over-strict 2종).
  - revert 후 sha256 **정확 일치**(residue 0), 7 passed 재확인 → under-strict bite + 정확 복원 실증.
- 보강 후: `CanonicalCandidateDedupTest` 5→7, 전체 **726 passed / 48 skipped**(종전 724 + I1/I2 2). `git diff --check` clean.
- **커밋**: working tree uncommitted. 프로젝트 관례상 커밋은 오너 지시 대기(작업자 임의 커밋 안 함).

## Next steps

- HANDOFF Next Tasks #1의 남은 실 후보는 **오너 선택 대기**이며 **전부 라이브/규모 의존**((b-4) hybrid 튜닝[실 데이터, 최후순위]·(c) character 별칭 semantic[실 embedding]·Phase 6[신규 페이즈]) — 서브 머신에서 라이브 없이 진행 가능한 후보는 현재 소진.
- **오너 지시 시 v1.6.60 커밋**(구현 + 검증 후속 보강 포함).
- (e) 후속: candidate de-index 실경로·resolve/dismiss 전이는 Phase 6에서 이 억제를 상위집합으로 흡수. 실 Mongo 승격 dedup live 관통은 sandbox 밖.
- sandbox 밖 후속(코드 완료, 여기서 막힘)은 무변: 2B.6 threshold 캘리브레이션·2B.5/b-2/b-6 live 관통·ES-lexical/vector live backfill.
