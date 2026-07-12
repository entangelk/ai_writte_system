# 검증 기록 — (c-2) 동명이인 semantic 반증 + merge/split reconciliation (SoT v1.6.63)

## Subject metadata

- **날짜**: 2026-07-12
- **요청자**: 오너(사용자). 요청: "(c-2) 구현 완료. 핵심 변경: 동일 이름 character도 semantic 하한 미달 시 judge 대신 conflict / homonym threshold off 기본 / 라벨 JSONL calibration CLI / review-queue 기반 merge|split reconciliation API(merge=evidence append version, split=별도 canonical, confirmed 전이 + de-index, same-action 멱등·다른 action 409). 검증해줘."
- **검증자**: Claude(독립 감사 — 구현 작업자 아님)
- **대상 slice/artifact**: (c-2) character 동명이인 semantic 반증 + merge/split reconciliation. 구현 `services/application/app/analysis/compare.py`(homonym 분기)·`semantic_matcher.py`(`EmbeddingCharacterIdentityVerifier`)·`reconciliation.py`(신규)·`review_queue.py`(`get`/`mark_resolved` + resolution 필드)·`review_queue_mongo_repository.py`·`main.py`(wiring + route)·`character_threshold.py`(신규)·`scripts/calibrate_character_identity_threshold.py`(신규 CLI). 회귀 `tests/test_analysis_compare.py`·`tests/test_character_reconciliation.py`(신규)·`tests/test_character_threshold.py`(신규). 계약 갱신 SoT v1.6.63.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.63(버전 테이블 line 36). 선행: (c) v1.6.62(`docs/verifications/2026-07-12/character_alias_semantic.md` PASS). 브리프 결정 `docs/plans/02b-7-character-alias-homonym-decisions.md` "(c-2) Owner decisions — 2026-07-12".
- **소스**: working tree, uncommitted(`git status` — 코드·테스트·문서 modified, 신규 5개 untracked). v1.6.62는 `52ca1bb`로 커밋됨.

## Scope

1. **계약 자체 일관성** — SoT v1.6.63 ↔ 브리프 (c-2) 결정 5항 ↔ 선행 (c) v1.6.62·2B.3 D2=A 정합. "탐지만·자동 병합 없음" 경계의 연속성.
2. **homonym 반증 구현** — `compare.py` homonym 분기 진입 조건·action·matched id·judge 우회·off 기본.
3. **identity verifier** — `EmbeddingCharacterIdentityVerifier.supports_same_identity` 직접 pair cosine, `derive_memory_index_text` 호환성, memory.memory_type 타입.
4. **reconciliation 구현** — merge(`record_evidence_version`)·split(`promote_candidate`)·CONFIRMED 전이·de-index·idempotency(same-action replay)·different-action 거부. 의존 서비스 메서드(`get_candidate`·`transition_candidate`·`record_evidence_version`) signature/반환형 실재.
5. **review_queue 확장** — `get`·`mark_resolved`·resolution 필드 영속화(mongo).
6. **calibration 로직** — `calibrate_threshold` balanced_accuracy 최대·동점 stricter·양 라벨 필수; CLI embedding 점수화·env 자동변경 없음.
7. **wiring / HTTP route** — `_build_character_homonym_verifier` off 기본 + fail-fast; reconcile route 등록·OpenAPI 노출·예외 매핑.
8. **회귀 테스트 품질** — homonym under/over-strict, reconciliation merge/split/replay/different-action, calibration 경계.
9. **전체 suite 재현** — 작업 AI "7%에서 멈춰 중단·전체 green 미주장" 보고의 **독립 재검증**(hang 비재현 확인이 핵심).
10. **문서 갱신 정확** — SoT·CHANGELOG·HANDOFF·work_log.

## Methodology

```bash
# 1. 변경 범위
git status; git diff --stat

# 2. 계약/구현 원문 교차 읽기
git diff docs/plans/02b-7-character-alias-homonym-decisions.md docs/system-contract-sot.md
git diff services/application/app/analysis/compare.py services/application/app/analysis/semantic_matcher.py \
       services/application/app/analysis/review_queue.py services/application/app/analysis/review_queue_mongo_repository.py
# 신규 파일: Read reconciliation.py / character_threshold.py / scripts/calibrate_*.py

# 3. 의존 서비스 메서드 실재 + signature 검증 (추측 금지)
grep -n "def record_evidence_version\|def promote_candidate\|def get_candidate\|def transition_candidate" \
  services/application/app/memory/service.py services/application/app/analysis/service.py
sed -n '225,300p' services/application/app/memory/service.py    # _versioned_upsert evidence_only 동작
sed -n '500,560p' services/application/app/analysis/service.py  # get_candidate/transition_candidate 반환형
grep -n "memory_type" services/application/app/memory/models.py

# 4. 회귀 원문 읽기(under/over-strict 추적)
git diff tests/test_analysis_compare.py
# Read tests/test_character_reconciliation.py tests/test_character_threshold.py

# 5. ★ 전체 suite 독립 재실행 (작업 AI hang 보고 재검증) — timeout 묶어 로그 파일화
timeout 180 python3 -m pytest --ignore=tests/test_memory_mongo.py -v -p no:cacheprovider > /tmp/pytest_full.log 2>&1
echo "EXIT: $?"; tail -5 /tmp/pytest_full.log

# 6. route 등록 + OpenAPI 노출 실제 확인 (app introspection)
python3 -c "import services.application.app.main as m; app=m.create_app(); \
  print([r.path for r in app.routes if 'reconcile' in getattr(r,'path','')]); \
  print({p: list(mth.values())[0].get('responses',{}).keys() for p,mth in app.openapi()['paths'].items() if 'reconcile' in p})"

# 7. reconcile HTTP route 회귀 존재 여부
grep -rn "reconcile" tests/ | grep -v "character_reconciliation.py:"

# 8. 서식
git diff --check
```

## Findings

### 1. 계약 자체 일관성 — PASS

- 브리프 (c-2) 결정 5항(`plans/02b-7-...:167-171`)과 SoT v1.6.63(버전 테이블 line 36) 정합. (c) v1.6.62의 "탐지만·자동 병합 없음" 경계를 (c-2)가 이어받아 **사람 승인 merge/split write**로 실현 — 자동 병합 아님(reconcile은 open review entry에 대한 명시적 인간 action).
- homonym 반증도 conflict surface(브리프 line 167). merge/split은 오직 reconcile API 경유(브리프 line 169-170). 동일 action replay 멱등·다른 action 거부(브리프 line 171). 전부 구현에 반영.

### 2. homonym 반증 구현 — PASS

- `compare.py:206-219`: `memory = matches[0]`(name-key=1) 후 `if scope is not None and self._homonym_verifier is not None and not supports_same_identity(...) → CONFLICT`. 브리프 line 167("name-key=1이어도 직접 semantic similarity가 하한 미달이면 judge 대신 conflict")과 정합.
- **off 기본**: `homonym_verifier is None`이면 분기 skip → 종전 judge 경로(`compare.py:198-` 미변경).
- **judge 우회**: 하한 미달 시 곧바로 CONFLICT 반환, judge 호출 부재.
- matches>1(중복 canonical)은 line 184-196에서 이미 CONFLICT → homonym 분기는 항상 matches==1. self-exclusion/cross-project는 `_find_matches`가 보장(character path의 `entry.scope == scope` + `analysis_job_id != job_id` 필터).

### 3. identity verifier — PASS

- `semantic_matcher.py:99-119`: candidate·canonical 각각 `derive_memory_index_text` 투영 → embed → cosine ≥ floor. 직접 pair 비교(query_similar 아님) — 브리프 line 167("선택 canonical과 candidate의 직접 semantic similarity") 정합.
- `MemoryEntry.memory_type: AnalysisCandidateType`(`models.py:39`) → `derive_memory_index_text(memory.memory_type, ...)` 호환(`memory_index.build_memory_index_record`가 이미 동일 필드 사용).

### 4. reconciliation 구현 — PASS

- `reconciliation.py:49-104`:
  - **RESOLVED 분기(52-63)**: `resolution_action != action.value or not resolution_memory_id` → ValueError("different action")(→409). same-action → `idempotent_replay=True`, **write 없이 early return**(transition/de-index/mark_resolved 전). 정확한 idempotency.
  - **OPEN 아니면(64-65)**: ValueError(→409).
  - **character-only(69-70)**: CHARACTER_OBSERVATION 아니면 ValueError.
  - **merge(72-80)**: `matched_memory_id` 없으면 ValueError; `record_evidence_version(target=matched_memory_id)`. superseded=matched_memory_id.
  - **split(81-86)**: `promote_candidate(MANUAL)`(별도 canonical). superseded=None.
  - **CONFIRMED 전이 + de-index(88-95)**: `transition_candidate(CONFIRMED)`, `transition.changed`일 때만 `enqueue_candidate_removed`.
  - **mark_resolved(97-99)**: resolution_action/memory_id 영속.
- 의존 메서드 전부 실재·signature 일치(`memory/service.py:232 record_evidence_version`, `:148 promote_candidate`, `analysis/service.py:508 get_candidate`, `:513 transition_candidate`).
- **merge payload 보존 검증**: `_versioned_upsert(evidence_only=True)`(`memory/service.py:255-273`)가 target.payload·provenance 보존 + source refs union + version+1 + supersedes=target + confidence max. 브리프 line 169("canonical payload/name 보존 + evidence union append-only version") 정확히 일치. D5 idempotency(`find_memory_by_candidate`) 내장.

### 5. review_queue 확장 — PASS

- `review_queue.py:162-181`: `get`(`KeyError` if not found/project mismatch → route 404), `mark_resolved`(RESOLVED면 no-op, OPEN 아니면 ValueError → 409).
- `review_queue_mongo_repository.py:84-116`: `get_entry` 추가, `resolution_action`/`resolution_memory_id` 영속화(`_entry_doc`·`_to_entry` 양방향). InMemory repo도 `get_entry` 구현.

### 6. calibration 로직 — PASS

- `character_threshold.py:23-31`: 고유 score 내림차순 threshold 후보 → 각 confusion matrix → `balanced_accuracy` 최대, 동점 시 **stricter(더 높은) threshold**. `predicted_same = score >= threshold` 방향이 homonym verifier(`cosine >= floor`)와 일치.
- 양 라벨 필수(`:24-27`): same/different 하나라도 없으면 ValueError. 빈 입력도 거부.
- CLI(`calibrate_*.py`): JSONL `{"left_text","right_text","same_identity"}` → 실 embedding 점수화 → `calibrate_threshold` → recommended_threshold/balanced_accuracy/confusion 출력. **env 자동 변경 없음**(브리프 line 168 "production 값을 자동 설정하지 않는다" 정합). `same_identity` bool 타입 강제.
- 테스트 수치 검산: `((0.95,T),(0.9,T),(0.6,F),(0.2,F))` → threshold 0.9에서 TP=2/TN=2/FP=0/FN=0, balanced_acc=1.0 ✓. 단일 라벨 거부 ✓.

### 7. wiring / HTTP route — PASS (비차단 관찰 2·4·5, 아래 Issues)

- `_build_character_homonym_verifier`(`main.py:414-426`): env 미설정 → None(off); 설정 시 EMBEDDING_SERVICE_URL 필요(fail-fast).
- route `POST /projects/{project_id}/analysis/review-queue/{entry_id}/reconcile`(`main.py:1633-1655`): `ReconciliationAction(request.action)` 파싱 → reconcile. except `(NotFound, AnalysisNotFound, MemoryNotFound, KeyError)`→404, `ValueError`→409. response: entry_id/action/memory_id/superseded_memory_id/idempotent_replay.
- app introspection: route 정상 등록, OpenAPI paths에 노출(POST). responses는 `['200','422']`(404/409 명시 없음 — 비차단 관찰 5).

### 8. 회귀 테스트 품질 — PASS (비차단 관찰 3, 아래 Issues)

- homonym(`test_analysis_compare.py:160-184`): `below_floor → CONFLICT(judge.calls==0, verifier.calls==1)` under-strict + `above_floor → judge(judge.calls==1)` over-strict. 양방향. `FakeIdentityVerifier`로 verifier 호출 추적.
- reconciliation(`test_character_reconciliation.py`): merge → evidence version(payload 보존·refs union·supersedes·old SUPERSEDED·CONFIRMED) + **replay idempotent**; split → 별도 canonical(≠old.id) + superseded=None + RESOLVED + **different-action(MERGE) → ValueError("different action")**.
- calibration(`test_character_threshold.py`): 경계 분리 threshold 선택 + 동점 stricter + 양 라벨 필수.

### 9. ★ 전체 suite 재현 — PASS (hang 비재현, 핵심 발견)

작업 AI 보고: *"전체 suite도 7% 이후 장시간 무출력로 중단했으므로 이번 변경에 대해 전체 green을 주장하지 않는다."*

**독립 재실행**: `timeout 180 python3 -m pytest --ignore=tests/test_memory_mongo.py -v -p no:cacheprovider` → **EXIT 0, 763 passed, 48 skipped, 3 warnings, 99 subtests passed in 12.07s**(로그 860행이 12초에 생성 → hang 아님). 이전(755) 대비 +8.

→ **작업 AI의 "hang"은 비재현**. 현재 working tree 코드는 전체 green. 작업 AI 환경 특이적(추정: stdout 버퍼링·백그라운드 프로세스 관리·WSL2 터미널) 일시 현상으로 보임. 작업 AI가 보수적으로 "전체 green 미주장"한 것은 정직하나, 실제로는 통과. 이 slice의 회귀 763개는 양호.

### 10. 문서 갱신 — PASS

- SoT 버전 테이블 line 36(v1.6.63, 역순 최상단). CHANGELOG 최상단. HANDOFF(Current Status v1.6.63·Owner Decisions·Next Tasks 갱신). work_log(Goals·Completed·Decisions·Verification).
- `git diff --check` exit 0(clean).

## Issues / Risks

**차단 이슈: 없음.** 계약 위반·자동 병합·의존 메서드 부재·빈 boundary cell·silent 쓰기 전부 발견 안 됨.

**비차단 관찰**:

- **★ Obs1 — 작업 AI "전체 suite hang" 비재현(보고 정확성·가장 중요)**. 작업 AI가 "7% 이후 무출력로 중단, 전체 green 미주장"으로 보고했으나, 독립 재실행 시 **763 passed / 12.07s / exit 0**로 정상 완료(hang 비재현). 원인은 작업 AI 환경 특이적(WSL2 stdout 버퍼·백그라운드 프로세스 관리 추정). **현재 코드는 전체 green**이므로, HANDOFF/work_log의 "전체 green 미주장" 표현은 과도하게 보수적 — 오너는 이 slice가 실제로 green임을 인지할 것. (work_log를 763 passed로 정정 권고.)
- **Obs2 — reconcile HTTP route 회귀 부재(public envelope 미잠금)**. `test_character_reconciliation.py`는 service 단위(`service.reconcile` 직접 호출)이고, **route의 404/409 status 매핑·response envelope이 HTTP 테스트로 직접 잠기지 않음**(`grep reconcile tests/` → route HTTP 테스트 0건). 작업 AI가 "OpenAPI reconcile route 확인"이라 한 assert는 영속 테스트로 남지 않은 것으로 보임. service 로직은 잠겨 있으나, route→HTTP status 매핑(KeyError→404, ValueError→409, `ReconciliationAction("invalid")`→409) 자체는 회귀로 보장되지 않음. 추천: `POST .../reconcile` 200/404(entry/project 누락)/409(different-action·non-open·invalid-action) HTTP 회귀 추가. 기존 `test_analysis_apply_api.py` review-queue 라우트 패턴과 동형.
- **Obs3 — homonym off 기본 / scope-less 미진입 직접 회귀 부재**. homonym 회귀는 verifier True/False 두 방향만. `verifier=None`(off 기본)과 `scope=None`(event/open_question 미진입)은 기존 `CompareMatchTest`(judge 경로)와 `compare.py:206`의 `scope is not None` 조건에 위임. (c) v1.6.62 검증 Obs4와 동일한 위임 패턴. 위임 명시적이라 빈 cell 아님.
- **Obs4 — route 예외 매핑 간극 → 잠재적 500**. reconcile route except는 `(NotFound, AnalysisNotFound, MemoryNotFound, KeyError)`→404, `ValueError`→409. 그러나 `record_evidence_version`이 matched canonical이 non-canonical일 때 raise하는 `MemoryError`, transition이 불법일 때 `InvalidCandidateStateTransition`은 route에 안 잡힘 → 500. 드문 시나리오(matched canonical이 이미 superseded된 경우만 MemoryError; transition은 CONFIRMED가 멱등 no-op라 사실상 raise 안 함). 비차단이나 route except에 `MemoryError` 추가로 방어 권장.
- **Obs5 — OpenAPI responses 404/409 미노출**. POST /reconcile responses = `['200','422']`. route가 raise하는 404/409가 OpenAPI에 명시 안 됨(FastAPI가 HTTPException 자동 문서화 안 함). 기존 confirm/reject route도 동일 패턴으로 보여 이 slice만의 문제는 아님. 공개 schema 소비자 관점 간극.
- **Obs6 — calibration discrete threshold**. `calibrate_threshold` 후보가 입력 score의 고유값 집합에 한정(연속 최적화 아님). balanced_accuracy는 동일 구간에서 일정하므로 stricter 선택이 보정하지만, 정확한 optimal 경계를 놓칠 수 있음. harness 참고값이므로 허용 범위.
- **Obs7 — 작업 AI 회귀 숫자 보고 비일관**. work_log "21 passed(핵심) / 31 passed(compare+wiring)" vs 실제 suite net +8(755→763). 21+31=52와 불일치는 기존 테스트 재실행/집계 기준 차이로 보이나, suite green이 핵심이므로 비치명.

## Verdict

**PASS (조건 없음).**

적대적·독립 재검증 결과:
- 계약(SoT v1.6.63·브리프 c-2 5항) ↔ 구현 ↔ 테스트 정합. (c) v1.6.62 "자동 병합 없음" 경계를 사람 승인 reconcile으로 정확히 이어받음.
- homonym 반증(name-key=1 + 직접 pair cosine 하한 미달 → CONFLICT, off 기본)·merge(evidence append version, payload 보존)·split(별도 canonical)·CONFIRMED+de-index·same-action idempotent·different-action 거부 전부 구현·검증.
- 의존 서비스 메서드 4종 전부 실재·signature/반환형 일치(추측 아닌 grep+원문 확인).
- **★ 작업 AI의 "전체 suite hang"은 비재현 — 763 passed / 12.07s / exit 0**. 현재 코드 green. 작업 AI의 보수적 보고는 정직하나 실제 통과.
- route 정상 등록 + OpenAPI 노출(app introspection).
- `git diff --check` clean.

비차단 관찰 7건은 코드 무변 권고 또는 보고/문서 정확성 개선이며 합격 조건이 아님. 그중 **Obs2(reconcile HTTP route 회귀 부재)** 와 **Obs4(route 예외 매핑 500 간극)** 가 후속 보강 가치가 가장 큼(둘 다 route의 public envelope/status 보장).

## Outstanding items

- **작업 미커밋**: 본 slice는 working tree에만 있음(v1.6.62 `52ca1bb` 위). 오너 커밋 승인 대기.
- **production threshold 실값 채택(이 slice 범위 밖)**: homonym/alias threshold는 off 기본. calibration CLI는 harness만 제공(production env 자동 변경 안 함). 실제 라벨 데이터로 threshold 산출·검토 후 env 발화는 운영 튜닝(HANDOFF Next Tasks 명시).
- **reconcile route HTTP 회귀 보강(Obs2)**·**route 예외 매핑 방어(Obs4)**: 후속 보강 권장.
- **merge/split UI**: Phase 6 UI slice(프론트엔드 미확정 보류).

## Reproduction

```bash
# ★ 전체 suite(작업 AI hang 비재현 확인)
timeout 180 python3 -m pytest --ignore=tests/test_memory_mongo.py -v -p no:cacheprovider > /tmp/p.log 2>&1
echo "EXIT: $?"; tail -3 /tmp/p.log
# 기대: EXIT 0, 763 passed, 48 skipped (약 12초)

# 이 slice 회귀만
python3 -m pytest -q tests/test_character_threshold.py \
                   tests/test_character_reconciliation.py \
                   tests/test_analysis_compare.py tests/test_analysis_compare_api.py
# 기대: 전부 passed

# route 등록 + OpenAPI 노출(app introspection)
python3 -c "import services.application.app.main as m; app=m.create_app(); \
  print([r.path for r in app.routes if 'reconcile' in getattr(r,'path','')])"
# 기대: ['/projects/{project_id}/analysis/review-queue/{entry_id}/reconcile']

# 의존 메서드 실재
grep -n "def record_evidence_version\|def get_candidate\|def transition_candidate" \
  services/application/app/memory/service.py services/application/app/analysis/service.py

# 서식
git diff --check   # exit 0
```
