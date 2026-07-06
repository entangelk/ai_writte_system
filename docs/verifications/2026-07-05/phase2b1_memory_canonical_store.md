# Verification — Phase 2B.1 canonical MemoryEntry store + candidate 승격

## Subject metadata

- 날짜: 2026-07-05
- 요청자: 오너 (“다음 작업 검증해줘. 작업한 것만 검증해줘” — Phase 2B.1)
- 검증자: Claude Code (독립 감사, 작업자와 무관)
- 대상 slice: Phase 2B.1 canonical `MemoryEntry` store + candidate 승격 (SoT v1.6.40)
- 정본 스펙 참조:
  - `docs/plans/02b-analysis-compare-kickoff-decisions.md` — 2B.1 slice 경계(§“제안하는 첫 sub-slice”) 및 Owner decisions D1=A / D2=B(화해·threshold 확정) / D3=A / D5=A. D4/D6/D7은 2B.1 범위 밖.
  - `docs/system-contract-sot.md` v1.6.39(결정) / v1.6.40(구현) changelog 및 §Phase 2B
  - `services/application/app/analysis/models.py` — 2A `AnalysisCandidate`/`AnalysisCandidateType`/`AnalysisProvenance`(D5=A 재사용 대상)
- 검증 대상 work source: working tree, uncommitted (branch `phase4-slice-4-2-planner`). 신규 `services/application/app/memory/` 패키지 + `tests/test_memory_{phase2b,api,mongo}.py` + `main.py`/`analysis/service.py`/문서 수정. **이전 worker→real Chroma 검증(F1)의 HANDOFF 클레임 폐쇄 여부는 2B.1 범위 밖** — 본 검증은 2B.1 작업물만 다룬다.

## Scope

1. **스펙 계약**: 2B.1 slice 경계(MemoryEntry model + Mongo collection/index + candidate 승격 + version=1 + HTTP surface) 및 D2=B threshold gate 화해, D5=A enum 재사용, D3 위임 경계.
2. **구현 코드**: `memory/models.py`, `memory/repository.py`, `memory/service.py`, `memory/mongo_repository.py`, `memory/__init__.py`, `main.py`(엔드포인트 4종 + factory), `analysis/service.py`(get_candidate 추가).
3. **회귀 테스트**: `tests/test_memory_phase2b.py`(service), `tests/test_memory_api.py`(HTTP), `tests/test_memory_mongo.py`(skip-aware live Mongo).
4. **문서 정합**: SoT v1.6.40, work_log, CHANGELOG, HANDOFF, mongo_collections.md.

## Methodology

스펙 우선(scoping-first). 브리프 §“제안하는 첫 sub-slice(2B.1)”와 D2=B 화해·threshold 확정에서 boundary matrix를 먼저 세운 뒤, 코드 리터럴 ↔ 테스트 ↔ 문서에 매핑. 작업자 클레임(회귀 17+3, 489/48)은 독립 재도출. 클레임된 boundary는 실제 실행/재현으로 확정.

```bash
# diff 파악
git status --short; git diff --stat HEAD
git diff HEAD -- services/application/app/main.py services/application/app/analysis/service.py
git diff HEAD -- docs/system-contract-sot.md docs/mongo_collections.md CHANGELOG.md HANDOFF.md docs/daily_logs/2026-07-05/work_log.md

# 스펙 독해(경계 조항까지)
sed -n '17,150p' docs/plans/02b-analysis-compare-kickoff-decisions.md   # 2B.1 slice 경계 + D2 threshold 화해

# 코드-스펙 대조
sed -n '1,130p' services/application/app/analysis/models.py             # AnalysisCandidate: scope 필드 부재 확인(D3 위임 근거)
# memory/{models,repository,service,mongo_repository}.py 전문 독해
# main.py: _default_memory_service / 엔드포인트 4종 / _memory_payload

# import 방향·index 코드-문서 일치
grep -rn "from services.application.app.memory" services/application/app/analysis/   # 단방향 memory→analysis 확인
grep -n "uniq_memory_candidate_promotion\|memory_entries_by_project" services/application/app/memory/mongo_repository.py docs/mongo_collections.md

# 테스트 재현(클레임 검증)
python3 -m unittest discover tests          # Ran 537 OK (skipped=48)  → passed=489
python3 -m pytest -q tests                  # 489 passed, 48 skipped
git diff --check                            # exit 0

# F2 재현: auto_promote_job 재호출 시 promoted 배열 동작 (test_memory_api 헬퍼 재사용)
python3 -c "import sys; sys.path.insert(0,'tests'); import test_memory_api as T; \
  c,a,p=T._build(auto_promotion_threshold=0.9); cand=T._seed_candidate(a,project_id=p,logical_key='lk',confidence=0.95); j=cand.job_id; \
  r1=c.post(f'/projects/{p}/analysis/jobs/{j}/auto-promote').json(); \
  r2=c.post(f'/projects/{p}/analysis/jobs/{j}/auto-promote').json(); \
  r3=c.post(f'/projects/{p}/analysis/jobs/{j}/auto-promote').json(); \
  s=c.get(f'/projects/{p}/memory').json()['memory']; \
  print(len(r1['promoted']),len(r2['promoted']),len(r3['promoted']),len(s))"
# 출력: 1 1 1 1  → stored=1 이지만 promoted는 재호출마다 1개씩 반복 보고
```

## Boundary matrix (스펙에서 도출한 lock list)

| # | boundary (스펙 출처) | 코드 리터럴 | 테스트 매핑 |
|---|---|---|---|
| B1 | MemoryEntry: status `canonical` 단일, version=1, 감사 필드(브리프 2B.1 + D2 감사성) | `models.py:22-45` | `test_manual_promote_creates_canonical_first_version_preserving_candidate` |
| B2 | memory_type/provenance 2A enum 재사용, taxonomy 3종 (D5=A) | `models.py:16-19,35-37` | 동일(+ `test_memory_mongo` round-trip이 enum 복원) |
| B3 | 수동 승격: confidence 무관 항상 canonical (D2 수동 경로) | `service.py:98-134`(`mode=MANUAL` → applied_threshold=None) | `test_manual_promote_creates...`, API `test_promote_candidate_creates...` |
| B4 | gate off 기본 → confidence=1.0도 미승격 (D2 보수적, over-strict) | `service.py:93-96`(`threshold is not None and ...`) | `test_gate_is_off_by_default_and_promotes_nothing`, API `test_auto_promote_off_by_default...` |
| B5 | gate: confidence >= threshold (경계 포함, under-strict) | `service.py:96`(`>=`) | `test_gate_fires_at_or_above_threshold`, API `test_auto_promote_fires_only_at_or_above_threshold` |
| B6 | 미만 candidate needs_review 유지 + 수동 경로 보존 (D2=B both-direction) | `service.py:145-159`(None 반환) | `test_gate_does_not_fire_below_threshold_but_manual_still_promotes`, API 대응 |
| B7 | 승격 idempotency: (project_id, source_candidate_id) unique | `service.py:108-113`, `mongo_repository.py:51-58` | `test_manual_promote_is_idempotent_per_candidate`, `test_repeated_promotion_replays_via_find...`, `test_unique_index_rejects_second_promotion...` |
| B8 | first-wins: 첫 승격 mode/threshold 덮어쓰기 금지 | `service.py:108-113`(find hit 시 기존 반환) | `test_auto_then_manual_promotion_is_idempotent` |
| B9 | threshold 주입(`MEMORY_AUTO_PROMOTION_THRESHOLD`) + applied_threshold 감사(AUTO만) | `main.py:155-177`, `service.py:115-119` | API `test_auto_promote_fires...`(applied_threshold=0.9), service `test_gate_fires...` |
| B10 | cross-project 격리(get/list) | `service.py:161-181` | `test_get_memory_enforces_project_isolation`, `test_list_memories_is_scoped_to_project` |
| B11 | HTTP 404: candidate/project/memory 부재 | `main.py` 엔드포인트 except 매핑 | `test_promote_missing_candidate_returns_404`, `test_promote_on_missing_project_returns_404`, `test_get_missing_memory_returns_404` |
| B12 | Mongo 영속 round-trip(skip-aware) | `mongo_repository.py:104-137` | `test_promoted_memory_round_trips_through_fresh_service` |
| B13 | auto_promote_job 재호출 시멘틱 (D2 spec-silent) | `main.py` auto_promote_job 루프 | **(없음 — 아래 F2)** |

## Findings

### 1. 스펙 계약 (브리프 2B.1 + D2=B 화해)

2B.1 slice 경계(브리프 line 17-26): MemoryEntry model + Mongo collection/index + needs_review candidate → MemoryEntry 승격(원본 source_refs/provenance/payload 보존, 첫 version=1) + HTTP surface. D2=B 화해(line 116-): AI가 아닌 결정적 threshold gate가 승격, threshold 이상만 자동 canonical, 미만은 needs_review+수동, threshold는 주입 설정값이며 근거 fixture 전까지 보수적. 감사성으로 confidence/적용 threshold/source_refs/provenance/analysis_job_id 기록 요구.

→ 코드가 이 모두를 정확히 실현. D2 감사성 5개(confidence/applied_threshold/source_ref_ids/provenance/analysis_job_id)가 `MemoryEntry`에 모두 존재(`models.py:38-45`). threshold 기본 `None`(off)은 D2 “보수적(거의 off에 가까운 높은 값 또는 명시 설정)”의 가장 보수적 해석 — spec-silent하나 추측값으로 canon 양산 금지라는 D2 정신과 정합.

### 2. 구현 코드

스펙-코드 일치:

- `evaluate_auto_promotion` (`service.py:93-96`): `threshold is not None and candidate.confidence >= threshold`. `>=`로 경계값 포함 → B5 under-strict 정확.
- 수동 경로 (`service.py:98-134`): `mode=MANUAL`일 때 applied_threshold=None, status=CANONICAL, version=1. candidate의 payload/provenance/source_ref_ids/confidence 보존(`immutable_payload`). B1/B3 정확.
- idempotency (`service.py:108-113`, `InMemoryMemoryRepository.put_memory:60-67`, `MongoMemoryRepository:51-58,87-93`): find_memory_by_candidate 선행 → hit 시 idempotent_replay=True(동일 memory). put_memory DuplicatePromotionRequest catch로 동시성 race까지 보장. B7 양쪽(in-process + cross-service)에서 lock.
- first-wins (`service.py:108-113`): find hit이면 기존 memory 반환, mode/threshold 덮어쓰지 않음. B8.
- D5=A enum 재사용 (`models.py:16-19`): `AnalysisCandidateType`/`AnalysisProvenance`를 2A에서 import. 중복 정의 없음.
- Mongo (`mongo_repository.py`): `memory_entries` collection, unique index `uniq_memory_candidate_promotion (project_id, source_candidate_id)`, query index `memory_entries_by_project`. `DuplicateKeyError→DuplicatePromotionRequest` 매핑.
- import 단방향: `analysis/{service,models}.py`는 `memory`를 import하지 않는다(grep 결과 없음). `memory→analysis` 단방향. `pymongo`는 `_default_memory_service`/`MongoMemoryRepository` lazy 경로에 한정. 순환 없음.
- `analysis/service.py` get_candidate 추가(5줄): `_require_candidate`의 얇은 공개 래퍼. HTTP 승격이 candidate를 project 격리로 로드하기 위함. 기존 2A 로직 변경 없음.

### 3. 회귀 테스트

실행 재현:

- `python3 -m unittest discover tests` → **Ran 537 OK (skipped=48)** → passed=489. 작업자 클레임과 일치.
- `python3 -m pytest -q tests` → **489 passed, 48 skipped, 95 subtests passed**. 작업자 클레임(489/48)과 정확히 일치.
- `git diff --check` → exit 0.

boundary 커버리지(B1~B12): under-strict(버그 재현 시 재실패)와 over-strict(정상 case 무손상)가 양방향으로 잠겨 양호. 특히:

- B4 over-strict: `test_gate_is_off_by_default...`가 confidence=1.0도 gate off 시 미승격 + repo 0건을 명시 → “추측값으로 canon 미양산” D2 의도까지 lock.
- B5 under-strict: confidence==0.9(==threshold)가 승격 + applied_threshold=0.9 + AUTO_THRESHOLD mode 검증 → 경계 조건 명시.
- B6 both-direction: 미만(0.89)은 auto 미승격(repo 0) + 직후 수동 승격 canonical → 수동 경로 보존까지 한 테스트에서 양방향.
- B7 양측: in-memory idempotency(test_memory_phase2b) + Mongo find replay/unique index race guard(test_memory_mongo, skip-aware)로 저장소 무관 idempotency lock.
- B8 first-wins: auto(0.8) 후 manual 같은 candidate → idempotent_replay=True, mode=AUTO_THRESHOLD 유지(덮어쓰기 아님).

### 4. 문서 정합

- work_log “Completed work”: 구현 리터럴·회귀 17+3·D3 위임 결정 상세 기록. 정합.
- CHANGELOG: v1.6.40 행 추가. 정합.
- HANDOFF: Phase 2B.1 행 추가, Next Tasks 1을 2B.2로 갱신, 오너 확인 대상 명시. 정합.
- mongo_collections.md: §39B memory_entries 추가, index 이름/필드가 코드와 100% 일치(`uniq_memory_candidate_promotion`/`memory_entries_by_project`). round-trip 예시의 `applied_threshold` null(manual) 표기도 코드와 일치.

## Issues / Risks

### F1. [NON-BLOCKING — 문서 메타 정정] SoT 계약 버전 메타 미갱신

`docs/system-contract-sot.md`의 changelog 표(line 36)와 §Phase 2B(line 362)에는 v1.6.40 행/내용을 추가했으나, **문서 상단 메타를 v1.6.40으로 올리지 않았다**:

- line 4: `계약 버전: v1.6.39` (v1.6.40 미반영)
- line 89: 인덱스 표 `| 이 문서 | ... | Approved SoT v1.6.39 |` (v1.6.40 미반영)
- line 6: `최근 갱신일: 2026-07-05` (날짜는 동일날이라 OK)

직전 버전들(v1.6.36→37 등)에서는 이 메타가 항상 함께 올라갔는데, 이번에 누락됐다. changelog와 메타가 엇갈리면 독자가 “현행 계약 버전”을 v1.6.39로 오독. 동작에는 무관 → non-blocking. 정정 권고(line 4와 인덱스 표를 v1.6.40으로).

참고: `memory/service.py:13`와 `main.py:159` 주석의 “SoT v1.6.39 D2=B” 인용은 **정확**하다 — D2=B 결정 자체가 v1.6.39에서 확정됐고 v1.6.40에서 구현됐으므로, 결정 출처로서 v1.6.39를 인용하는 것은 버그가 아니다. F1은 “메타 버전 번호 미갱신”만 가리킨다.

### F2. [NON-BLOCKING — 보고 시멘틱 + untested boundary] auto_promote_job 재호출 시 `promoted[]` 중복 보고

`main.py`의 `auto_promote_job` 엔드포인트는 `promote_candidate`가 candidate의 `status`(NEEDS_REVIEW)를 변경하지 않으므로, **같은 job을 재호출할 때마다 idempotent replay 결과도 `promoted` 배열에 append**된다. 실제 재현(test_memory_api 헬퍼 사용):

```
call1 promoted=1, call2 promoted=1, call3 promoted=1, actual stored memory=1
```

저장 memory는 1건(idempotency 정상 작동)이지만, HTTP 응답의 `promoted[]`는 재호출마다 같은 memory를 반복 보고한다. 클라이언트가 “이번 호출에 새로 승격된 memory 수”를 알 수 없다.

- 데이터 정합성 위반은 아니다(memory 건수는 보장됨).
- 스펙(D2/D1)은 auto-promote 재호출 시멘틱을 명시하지 않는다 → spec-silent.
- 다만 idempotency 시멘틱과 충돌: `promote_candidate`/수동 엔드포인트는 `idempotent_replay` 플래그로 신규/재생을 구분하나, `auto_promote_job`은 그 구분 없이 replay도 `promoted`에 넣는다.
- 이 boundary를 다루는 회귀가 없다(B13 빈 칸). CLAUDE.md “boundary matrix has no empty cells” 관점에서 빈 칸이나, 그 boundary 자체가 스펙에 없어 “추적할 branch가 없는” 상태.

non-blocking. 권고 둘 중 하나: (a) `result.idempotent_replay`가 True면 `promoted`에 넣지 않도록 해 “이번 호출 신규 승격” 시멘틱으로 좁히거나, (b) 응답에서 `promoted`의 의미를 “threshold 만족 현재 canonical memory”로 명시하고 스펙/문서에 기록. 어느 쪽이든 재호출 회귀 1개 추가를 권고.

### F3. [NON-BLOCKING — 작업자 명시적 오너 확인 대상] D3 scope key 2B.3 위임 경계

작업자가 D3 entity/scope key 매칭을 2B.1에서 구현하지 않고 2B.3에 위임했다(유일성은 source_candidate_id로만). 이 결정의 사실 근거와 합리성을 독립 검증:

- **근거 사실 확인(참)**: `AnalysisCandidate`(`analysis/models.py:65-77`) 필드는 id/project_id/job_id/task_id/candidate_type/action/status/provenance/confidence/source_ref_ids/payload이며 **scope_type/scope_id/name이 없다**. 작업자 주장(“candidate에 scope 필드가 없어 D3 key 산출이 추측”)은 사실.
- **브리프 정합**: 2B.1 slice 경계(line 17-26)는 MemoryEntry model + 승격 + version=1 + HTTP surface이고 scope key를 요구하지 않는다. line 23은 “이후 update는 이전 version 보존(2B.3에서 upsert 연결)”로 update/merge를 2B.3에 위임. D3=A는 “결정적 key 매칭”이고, 그 적용 시점이 compare/update(2B.3)라는 작업자 해석은 합리적.
- 브리프가 2B.1에 “필수 idempotency/조회 index”를 요구(line 19)하나, 이것의 작업자 실현은 `(project_id, source_candidate_id)` unique index = “같은 candidate 재승격 idempotency”이지 “같은 entity 중복 canonical 방지(D3)”가 아니다. 작업자는 전자만 2B.1에서, 후자를 2B.3에서 의식적으로 분리했다.

→ 결함이 아니다. 합리적 slice 경계. 다만 **작업자가 스스로 “오너 확인 대상”으로 명시한 경계**이므로, 오너가 2B.1에서 scope-key 유일성 강제를 의도했는지 확인이 필요한 상태로 둔다(work_log/HANDOFF/SoT v1.6.40에 이미 명시됨). 본 검증은 이 결정의 합리성을 확인만 한다.

## Verdict

**합격 (pass).**

- 스펙-코드-테스트-문서 정합성 양호: D1=A(2B.1 store+승격)/D2=B(결정적 threshold gate, AI 아님, 보수적 off 기본)/D5=A(2A enum 재사용)를 정확히 구현했고, gate 양방향(over-strict off·under-strict 경계·both-direction 수동 보존), idempotency(in-memory + Mongo race guard), first-wins, Mongo round-trip이 모두 회귀로 잠겨 있다. 전체 suite 537/489 재현, 작업자 클레임과 정확히 일치. mongo_collections index가 코드와 100% 일치.
- F1(SoT 메타 버전 미갱신)·F2(auto_promote_job 재호출 promoted 중복 보고)는 non-blocking 정정/권고. F1은 2줄 정정, F2는 재호출 회귀 1개 추가로 폐쇄 가능.
- F3(D3 위임 경계)은 결함이 아니라 작업자 명시 오너 확인 대상 — 합리성 확인됨, 오너 판단 대기.
- 차단 조건 없음.

## Outstanding items

- F1: SoT 상단 `계약 버전`/인덱스 표를 v1.6.40으로 정정(작업자/오너).
- F2: auto_promote_job 재호출 시멘틱 확정 + 재호출 회귀 추가 권고(작업자/오너 결정).
- F3: D3 scope key 위임 경계 오너 확인(work_log/HANDOFF/SoT에 명시됨) — 확인되면 2B.3에서 D3 key 산출/identity 충돌 boundary를 fixture와 확정.
- 자동 승격 threshold 실제 수치: 품질 fixture 전까지 `None`(off) 유지(D2 보수적 기본).
- 커밋/푸시 미실행 — 오너 요청 시 진행.

## Reproduction

```bash
# 스펙-코드 대조
sed -n '17,150p' docs/plans/02b-analysis-compare-kickoff-decisions.md   # 2B.1 경계 + D2 threshold 화해
sed -n '65,77p'  services/application/app/analysis/models.py            # AnalysisCandidate: scope 필드 부재(D3 위임 근거)
# services/application/app/memory/{models,repository,service,mongo_repository}.py 전문

# 테스트 재현
python3 -m unittest discover tests          # Ran 537 OK (skipped=48) → 489 passed
python3 -m pytest -q tests                  # 489 passed, 48 skipped
git diff --check                            # exit 0

# F2 재현 (auto_promote_job 재호출)
python3 -c "import sys; sys.path.insert(0,'tests'); import test_memory_api as T; \
  c,a,p=T._build(auto_promotion_threshold=0.9); cand=T._seed_candidate(a,project_id=p,logical_key='lk',confidence=0.95); j=cand.job_id; \
  r1=c.post(f'/projects/{p}/analysis/jobs/{j}/auto-promote').json(); \
  r2=c.post(f'/projects/{p}/analysis/jobs/{j}/auto-promote').json(); \
  s=c.get(f'/projects/{p}/memory').json()['memory']; \
  print('promoted call1/call2 =', len(r1['promoted']), len(r2['promoted']), '/ stored =', len(s))"
# 기대: promoted call1/call2 = 1 1 / stored = 1   (memory 1건이지만 promoted는 재호출마다 반복 보고)
```
