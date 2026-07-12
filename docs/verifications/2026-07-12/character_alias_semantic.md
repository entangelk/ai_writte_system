# 검증 기록 — (c) character 별칭 semantic 보강 (SoT v1.6.62)

## Subject metadata

- **날짜**: 2026-07-12
- **요청자**: 오너(사용자). 요청: "작업 AI가 작업한 거 확인하고 검증하고 의심하고 또 의심해줘. 적대적 검증과 비차단 항목 포함 검증까지 해서."
- **검증자**: Claude(독립 감사 — 구현 작업자 아님)
- **대상 slice/artifact**: (c) character 별칭 semantic 보강. 착수 브리프 `docs/plans/02b-7-character-alias-homonym-decisions.md`, 구현 `services/application/app/analysis/compare.py`·`services/application/app/main.py`, 회귀 `tests/test_analysis_compare.py::CharacterAliasTest`·`tests/test_analysis_compare_api.py`, 라이브 smoke `scripts/phase2b7_character_alias_live_smoke.py`, 계약 갱신 SoT v1.6.62.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.62(버전 테이블 line 36, 구현 추적 line 389). 선행 경계: 2B.3 D2=A(`plans/02b-3-analysis-compare-action-decisions.md`)·2B.6 D5=A(`plans/02b-6-semantic-identity-resolution-decisions.md`).
- **소스**: working tree, uncommitted(`git status` — compare.py·main.py·테스트·문서 modified, smoke·브리프 untracked). 커밋 안 됨(작업 AI 명시).

## Scope

본 검증이 점검하는 이산 표면:

1. **계약 자체 일관성** — SoT v1.6.62 ↔ 착수 브리프 02b-7 ↔ 선행 2B.3 D2=A·2B.6 D5=A 교차 정합. 계약 충돌 surface → 오너 결정(D1=A·D2=A) 흐름의 실제성.
2. **구현 코드** — `compare.py` alias seam 진입 분기·action·matched id·judge 우회; `main.py` 공유 빌더·별도 env·fail-fast guard.
3. **회귀 테스트** — `CharacterAliasTest` 4 + `test_analysis_compare_api.py` 2의 under/over-strict 양방향 잠금 유효성; StubEmbedding 함정의 실제 작동.
4. **경계 매트릭스 추적** — 브리프 매트릭스 10행이 어느 테스트에 잠기는가(직접 vs 위임). **빈 cell 없음** 입증.
5. **위임 타당성** — alias_matcher가 재사용하는 `EmbeddingSemanticMatcher`의 자체 테스트(`test_analysis_semantic_matcher.py`)가 self-exclusion·canonical-only·top-1·memory_type·projection을 실제로 잠그는가.
6. **적용 경로 연속성** — alias conflict의 `matched_memory_id`가 `apply.py` review_queue에 실제로 전달되는가("review_queue 풍부" 주장 검증).
7. **라이브 smoke 정직성** — 관통·wiring 검증 vs 라벨 정확도·threshold 실값 미검증 명시(D5/D7); self-exclusion 버그 smoke 포착·수정의 정직성.
8. **문서 갱신 정확** — SoT 버전 테이블/구현 추정/구현-추적 단락, HANDOFF, work_log, CHANGELOG.
9. **전체 suite 재현** — 755 passed / 48 skipped 재현, `git diff --check` clean.

## Methodology

CLAUDE.md "Verification Records" 절차: 계약 scope 먼저 구축 → 경계 매트릭스 작성 → 매트릭스를 잠그는 회귀 추적 → 빈 cell 탐지 → 위임 타당성 독립 확인. 재현 가능한 정확한 명령:

```bash
# 1. 변경 범위 파악
git status
git diff --stat
git log --oneline -8

# 2. 계약/구현/테스트 원문 읽기(교차 검증용)
#    - docs/plans/02b-7-character-alias-homonym-decisions.md (브리프, 매트릭스 line 119-132)
#    - services/application/app/analysis/compare.py (alias seam: line 145-183)
#    - services/application/app/analysis/semantic_matcher.py (EmbeddingSemanticMatcher.match: line 61-89)
#    - services/application/app/memory/scope.py (derive_scope character-only: line 34-43)
#    - services/application/app/indexing/memory_index.py (query_similar 필터·정렬: line 100-125)
#    - services/application/app/analysis/apply.py (conflict→review_queue: line 102-122)

# 3. 회귀 테스트 원문 읽기(under/over-strict 각 assertion 추적)
git diff tests/test_analysis_compare.py tests/test_analysis_compare_api.py

# 4. 위임 타당성 — 2B.6 자체 matcher 테스트가 잠그는 경계 확인
grep -nE "^class |def test_" tests/test_analysis_semantic_matcher.py

# 5. suite 재현(독립)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py   # → 755 passed, 48 skipped
python3 -m pytest -q tests/test_analysis_compare.py tests/test_analysis_compare_api.py

# 6. whitespace/서식
git diff --check                                              # exit 0

# 7. 계약 갱신 정확(SoT 버전 테이블·구현-추적 단락 순서)
grep -n "^- v1\.6\." docs/system-contract-sot.md
```

라이브 smoke(`scripts/phase2b7_character_alias_live_smoke.py`)는 풀스택 인프라(Mongo·Chroma·embedding) 의존이라 본 검증 환경에서 재실행하지 않고, **코드 정적 검증 + 작업 AI의 라이브 결과 보고 정직성**을 검증 대상으로 함(smoke 자체는 wiring·self-cleanup·정직성 disclaimer가 코드로 잠겨 있음을 확인).

## Findings

### 1. 계약 자체 일관성 — PASS

- **계약 충돌 surface 실제성 확인**: 브리프 §"헤드라인 긴장 1"(line 38-45)이 2B.3 D2=A "별칭/동명이인은 review 후보, **자동 병합 없음**"과 (c)의 (A)탐지 vs (B)자동해소 양 해석이 정반대임을 명시하고, "임의로 고르지 않는다" → D1에서 오너 확정 요청. 오너 결정 D1=A(탐지만)·D2=A(별칭만 먼저)가 브리프 line 156-166에 기록. CLAUDE.md §1(계약 충돌 surface) 절차 준수.
- **선행 경계 정합**: 2B.3 D2=A(자동 병합 없음)를 D1=A가 존중(alias→conflict, judge 미호출 = 자동 update/merge 아님). 2B.6 D5=A("character semantic은 별도 결정")가 이 slice로 열림. SoT v1.6.62 구현 추정(line 389)과 브리프 본문 일치.
- **계약 ↔ 구현 리터럴**: env `ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD`(브리프 D4 line 94-95 ↔ `main.py:_build_character_alias_matcher`), seam `alias_matcher: SemanticMemoryMatcher | None`(`compare.py:117`), off 기본(None ↔ `main.py` env 미설정 시 None 반환), action `CompareAction.CONFLICT`(`compare.py:167`), matched_memory_id=canonical(`compare.py:168`, `alias.id`). 전부 변형 없이 반영.

### 2. 구현 코드 — PASS

- **진입 분기 정확**(`compare.py:150-174`): `if not matches:`(결정적 name-key 0) → `if scope is not None and self._alias_matcher is not None:` → alias 조회 → 히트 시 CONFLICT. `scope.py:37`이 CHARACTER_OBSERVATION만 scope를 만들므로 `scope is not None` = character 한정 → **D2=A(별칭=character만) 정합**. event/open_question은 scope=None이라 alias 분기 진입 불가.
- **judge 우회(D1=A)**: alias 히트 시 곧바로 `ActionProposal(... CONFLICT ...)` 반환, judge 호출 부재(`compare.py:164-174`). 자동 update/merge 물리적 불가.
- **name-key≥1 경로 불변**(`compare.py:184-217`): alias 분기는 `if not matches:` 안에만. matches≥1이면 judge 경로로 흐름. alias_matcher 미참조.
- **main.py 공유 빌더**(`main.py:382-427`): `_build_memory_semantic_matcher(threshold_env)`로 2B.6 `_build_semantic_matcher`·신규 `_build_character_alias_matcher`가 같은 본문을 공유. fail-fast guard 메시지가 env명을 동적 포함(`f"{threshold_env} + CHROMA_HOST ..."`). CHROMA_HOST 없거나 threshold env 없으면 None 반환(off). 임계치+CHROMA_HOST 있는데 EMBEDDING_SERVICE_URL 없으면 RuntimeError.

### 3. 회귀 테스트 품질 — PASS

`CharacterAliasTest` 4 + `test_analysis_compare_api.py` 2를 under/over-strict 양방향으로 각 검증:

- `test_alias_surfaces_conflict_without_auto_merge`: under-strict(alias 누락 시 CONFLICT 아님 → fail) + over-strict(`FakeJudge(UPDATE)` 주입 후 `len(judge.calls) == 0` 검사 → judge로 넘어가면 fail). **양방향 guard**.
- `test_alias_below_threshold_is_create`: over-strict(타 인물 영희가 alias로 오판되면 CONFLICT → fail).
- `test_alias_off_by_default_is_create`: over-strict(matcher 미주입 시 종전 결정적 create 보존).
- `test_same_name_uses_deterministic_path_not_alias`: **StubEmbedding 함정**. canonical text(`Ariel\nbrave`)만 table에 두고 candidate text(`Ariel\nbold`)는 누락. alias.match()가 잘못 호출되면 `derive_memory_index_text` → `StubEmbedding.embed("Ariel\nbold")` → AssertionError → 테스트 실패. over-strict guard로 실제 작동 확인(`semantic_matcher.py:64-67`이 candidate payload를 embed). 영리하고 유효.
- `test_character_alias_wiring_without_embedding_url_fails_fast`: RuntimeError 메시지에 `EMBEDDING_SERVICE_URL`·`ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD` 둘 다 포함 검사.
- `test_character_alias_wiring_off_by_default_returns_none`: env 미설정 시 None.

### 4. 경계 매트릭스 추적 — PASS (빈 cell 없음)

브리프 매트릭스(line 119-132) 10행의 잠금 위치(직접=이 slice 회귀 / 위임=`EmbeddingSemanticMatcher` 자체 테스트):

| 분기 | 방향 | 잠금 위치 |
|---|---|---|
| threshold off → 결정적만 | over-strict | **직접** `test_alias_off_by_default_is_create` + wiring `test_character_alias_wiring_off_by_default_returns_none` |
| name-key=1 → judge 경로 | over-strict | **직접** `test_same_name_uses_deterministic_path_not_alias` |
| name-key=0 + above → conflict(alias) | under-strict | **직접** `test_alias_surfaces_conflict_without_auto_merge` |
| name-key=0 + below → create | over-strict | **직접** `test_alias_below_threshold_is_create` |
| 자동 update/merge 안 함(D1=A) | over-strict | **직접** `test_alias_surfaces_conflict_without_auto_merge`(`judge.calls==0`) |
| self-exclusion | over-strict | **위임** `test_analysis_semantic_matcher.py::test_self_exclusion`(`semantic_matcher.py:85`) |
| canonical-only | over-strict | **위임** `test_analysis_semantic_matcher.py::test_superseded_index_record_skipped`(`semantic_matcher.py:83`) |
| cross-project 격리 | over-strict | **위임** `query_similar`의 `project_id` equality 필터(`memory_index.py:110`, 모든 2B.6 테스트가 단일 project_id 스코프) |
| projection 일치(derive_memory_index_text) | under-strict | **위임** `test_similar_event_matches_prior_canonical` + 동일 함수 재사용(`semantic_matcher.py:64` ↔ 쓰기 path) |
| top-1(D6=A) | over-strict | **위임** `test_analysis_semantic_matcher.py::test_top_1_only`(`semantic_matcher.py:88`) |

**빈 cell 없음**: 위임 5행은 `EmbeddingSemanticMatcher`의 동일 동작에 대한 잠금이며, alias_matcher는 같은 클래스의 인스턴스(threshold만 분리)이므로 동일 보장을 상속. CLAUDE.md "빈 cell = blocking" 기준 충족.

### 5. 위임 타당성 — PASS

`test_analysis_semantic_matcher.py`(`SemanticMatcherTest` line 137-223)가 독립적으로 아래 경계를 잠금을 grep으로 확인:
- `test_top_1_only`(line 165) · `test_memory_type_scoped`(line 181) · `test_self_exclusion`(line 198) · `test_superseded_index_record_skipped`(line 211) · `test_similar_event_matches_prior_canonical`(line 138) · `test_dissimilar_event_below_threshold_no_match`(line 151).

`EmbeddingSemanticMatcher.match`(`semantic_matcher.py:61-89`)가 memory_type 필터(line 70, `candidate.candidate_type.value` → character candidate는 `"character_observation"`)·canonical 필터(line 83)·self-exclusion(line 85, `entry.analysis_job_id == job_id`)·top-1(line 88)을 인스턴스 무관 동일하게 수행. alias 인스턴스도 동일 코드 경로. 위임은 클래스 동일성에 기반하므로 타당.

### 6. 적용 경로 연속성(apply → review_queue) — PASS

`apply.py:102-122`: conflict 분기에서 `self._review_queue.enqueue(... matched_memory_id=proposal.matched_memory_id ...)`. alias conflict의 `matched_memory_id`(=canonical id, `compare.py:168`)가 review_queue entry에 실제로 전달됨. SoT v1.6.62 "D3=A(conflict surface + matched id 실음 → review_queue 풍부)"·work_log "apply.py는 무변경 확인 — alias conflict가 review 큐를 풍부하게 함" 주장 **사실 확인**. alias conflict는 candidate가 항상 job에 있으므로 `by_id.get(candidate_id)` None 경미발생.

### 7. 라이브 smoke 정직성 — PASS

`scripts/phase2b7_character_alias_live_smoke.py`:
- docstring(line 15-17, 23)이 "관통·wiring 검증이지 **라벨 정확도·threshold 실 캘리브레이션은 후속**(D5/D7)"을 명시. SoT·work_log 주장과 일치.
- `alias_ok = action is CONFLICT and matched_memory_id == canonical.id`(line 203-206), `far_ok = action is CREATE`(line 207) — coarse 2경계만 assert.
- self-exclusion 버그 포착·수정 정직 기록(work_log "구현 중 잡은 smoke 버그: canonical을 같은 job_id로 승격 → self-exclusion 배제 → canonical job을 `smoke-job-prior`로 분리"). 이는 프로덕션 코드 결함이 아니라 smoke 시나리오 결함이며, **오히려 D6 self-exclusion이 live에서 실제로 작동함을 입증**(긍정적 부산물).
- self-cleanup(Chroma record line 200 + Mongo docs line 201) 구현.

### 8. 문서 갱신 — PASS (비차단 관찰 1건, 아래 Issues)

- SoT 버전 테이블(line 36)에 v1.6.62 역순 최상단 추가. 본문 §"미확정으로 남은 것"(line 383)의 "character 별칭 semantic 보강" 항목이 "별칭 false-negative 방향은 v1.6.62로 닫힘, 동명이인 반증·threshold 실 캘리브레이션은 후속 잔여"로 정확히 갱신. 구현 추정(line 389) 추가.
- HANDOFF(Current Status·Active Decisions·Next Tasks·Verification·project 구조·scripts 목록) 일관 갱신. 테스트 749→755 갱신.
- CHANGELOG 최상단 추가. work_log "4차 작업" 추가 + Next steps 갱신.

### 9. 전체 suite 재현 — PASS

`python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **755 passed, 48 skipped, 3 warnings, 99 subtests passed in 11.05s**. HANDOFF·SoT·work_log 주장(755/48)과 정확히 일치. `git diff --check` exit 0(clean).

## Issues / Risks

**차단 이슈: 없음.** 계약 위반·빈 boundary cell·라벨 미assert 숨김·silent 자동 병합 모두 발견 안 됨.

**비차단 관찰**(오너 판단 항목, 코드 무변 권고):

- **Obs1 — SoT 구현-추적 산문 단락의 버전 비정렬(문서 일관성)**. `grep -n "^- v1\.6\." docs/system-contract-sot.md` 결과: line 388(v1.6.47) → line 389(**v1.6.62**) → line 390(v1.6.46) → line 391(v1.6.45). v1.6.62가 v1.6.47과 v1.6.46 사이에 삽입됨. 이 단락은 원래부터 strict 역순이 아님(47 다음 46/45가 이미 역순 혼재 — 기존 부채). **버전 테이블(line 34-, 추적 표면)은 정확히 역순**이므로 핵심 추적에는 영향 없음. v1.6.62를 2B.6(47) 직후에 둔 것은 의미론적 흐름(2B.6→2B.7) 우선으로 보이나, 엄밀 버전 번호 정렬 원칙을 따르려면 단락 전체 재정렬이 필요(기존 부채와 함께 처리 권고).
- **Obs2 — alias path 컨텍스트의 self-exclusion/cross-project/top-1 직접 회귀 부재(위임 타당성 명시)**. 이 slice 회귀 +6은 seam 진입 분기에 집중하고, matcher 내부 필터(행 6·7·8·10)는 `test_analysis_semantic_matcher.py`에 위임. 같은 클래스 인스턴스라 위임은 타당(Findings §5). 다만 character alias 컨텍스트 특유 시나리오 — 예: 같은 job에서 character canonical을 promote하고 같은 job의 candidate가 alias 비교 시 self-exclusion이 canonical을 drop하는 것 — 이 character 회귀로 직접 잠기지 않음. 라이브 smoke가 간접 증명(canonical job 분리 이유가 self-exclusion). 위임이 명시적이므로 빈 cell 아님.
- **Obs3 — rationale 표현이 브리프 제안과 상이(사소)**. 브리프 §제안 slice 범위(line 63)는 rationale에 "semantic alias candidate: **<matched name>**(canonical 이름)"을 제안했으나, 구현은 `compare.py:170-173`에서 candidate 이름 + canonical **id** 사용(`canonical memory {alias.id}`). id가 canonical payload 안의 이름보다 정확한 영구 참조. SoT/브리프 어디도 rationale 문자열 리터럴을 계약으로 고정하지 않았으므로 구현 자유도 범위. 브리프 본문을 id 참조로 갱신하거나 그대로 두어도 무방.
- **Obs4 — alias on + semantic off 조합의 명시적 회귀 부재(wiring)**. `ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD`만 설정하고 `ANALYSIS_SEMANTIC_MATCH_THRESHOLD`는 미설정한 조합(event/open_question은 always-create, character는 alias 발화)이 `main.py`에서 두 빌더가 독립적이라 자연스럽게 지원되나, 이 조합을 명시적으로 잠그는 회귀 없음. wiring 분리가 자명하므로 위험 낮음.

## Verdict

**PASS (조건 없음).**

적대적·독립 재검증 결과:
- 계약 충돌을 surface 하고 오너 결정(D1=A·D2=A)을 받은 뒤 구현 — CLAUDE.md §1·Verification Records 절차 준수.
- 경계 매트릭스 10행에 **빈 cell 없음**(직접 5 + 위임 5, 위임은 `EmbeddingSemanticMatcher` 동일 클래스 인스턴스에 기반).
- 계약 ↔ 구현 ↔ 테스트 리터럴 정합(env·seam·action·matched id·off 기본·top-1·projection).
- under/over-strict 양방향 guard(StubEmbedding 함정 포함) 유효.
- pytest 755/48 독립 재현, `git diff --check` clean.
- 라이브 smoke가 라벨 정확도 미assert를 정직히 명시하고 self-exclusion live 작동을 부산물로 입증.
- "review_queue 풍부" 주장(`apply.py:118` 전달) 사실 확인.

비차단 관찰 4건(Obs1 문서 정렬·Obs2 위임 명시성·Obs3 rationale 표현·Obs4 wiring 조합)은 모두 코드 무변 권고 또는 문서 일관성 개선이며, 합격 조건이 아님.

## Outstanding items

- **작업 미커밋**: 본 slice 구현(compare.py·main.py·테스트)·신규 smoke(`scripts/phase2b7_character_alias_live_smoke.py`)·브리프(`docs/plans/02b-7-...`)·문서 갱신이 working tree에만 있음. 작업 AI가 "오너 지시 시 커밋" 대기 중. 오너 커밋 승인 여부가 다음 단계.
- **후속 slice(이 slice 범위 밖, 브리프·SoT에 명시)**: (c-2) 동명이인 false-positive 반증(name-key=1 분기, 메커니즘 반대)·character alias threshold 실값 캘리브레이션(라이브 cosine 분포 배치, off→발화)·merge/split write 경로(Phase 6 UI). 본 검증은 별칭 방향(name-key=0)만 다룸.
- **Obs1 문서 재정렬**: 오너가 SoT 구현-추적 산문 단락의 strict 역순 정렬을 원하면 기존 부채(47→46→45)와 함께 v1.6.62 위치 조정. 우선순위 낮음.

## Reproduction

```bash
# 전체 suite 재현(독립)
python3 -m pytest -q --ignore=tests/test_memory_mongo.py
# 기대: 755 passed, 48 skipped, 3 warnings

# 이 slice 회귀만
python3 -m pytest -q tests/test_analysis_compare.py::CharacterAliasTest \
  tests/test_analysis_compare_api.py
# 기대: 6 passed

# 위임 경계 잠금 확인(2B.6 matcher 자체)
python3 -m pytest -q tests/test_analysis_semantic_matcher.py
# 기대: 전부 passed

# 서식
git diff --check   # exit 0

# 계약 정합(브리프 매트릭스 ↔ 코드 ↔ 테스트 교차)
grep -nE "^- v1\.6\." docs/system-contract-sot.md   # Obs1: v1.6.62 위치
```
