# 세션 48 독립 검증 — 무순위 절단 경고 · event/open_question shortlist 배선

- 일자: 2026-09-09
- 요청자: 오너 ("작업 Ai가 작업한거 확인해서 검증하고 의심하고 또 의심해줘")
- 검증자: Claude Code — 세션 48 구현자와 **다른 세션**
- 대상: 커밋 `2d97fe4`·`e82c9ed`·`0aa9966`·`69aed20`·`7a34e21`·`36591c6`(main, push 안 함) — 구현 2건(`e82c9ed` 무순위 절단 경고 · `7a34e21` shortlist 배선) + 브리프 2건 + 기록 갱신
- 정규 스펙 참조: [`docs/plans/pending-candidate-identity-grouping-decisions.md`](../../plans/pending-candidate-identity-grouping-decisions.md)(C 노선, Slice 1 seam 계약) · [`docs/plans/02b-6-semantic-identity-resolution-decisions.md`](../../plans/02b-6-semantic-identity-resolution-decisions.md)(D4=A — threshold 추측 거부) · S-1 D3(run당 새 판정 20쌍 상한) · [`docs/guides/verification.md`](../../guides/verification.md)
- 작업 출처: 커밋 6건(working tree clean, 시작 시 `git status --short` 무출력 확인)

## Scope

1. `e82c9ed` — 무순위 mongo-direct 절단 경고(canonical·candidate 양쪽, `degraded` 미사용 주장, 패턴 sweep 주장)
2. `7a34e21` — `VectorCandidateShortlistRetriever` + main.py 조립(임계값 미생성·미배선 no-op 보존·K=5·env override·20쌍 상한과의 관계)
3. 분석 주장 3겹(판정 1:1 쌍 · 정본 payload 비누적 · 컨텍스트 예산 그리디 하드 캡)
4. 브리프 2건의 사실 주장(원설계 `ContextCompressor` 누락 · `MACRO_NEEDS` 위치화 · `MemoryEntry` chapter 축 부재 · 실측 카운트)
5. 기록 갱신(work_log 세션 48 · HANDOFF 4곳 · CHANGELOG 1행 · 증분 귀속 +11셀/+2 subtest)
6. 백엔드 전수 재실행

## Methodology

- 코드: `git show` 전문 독독 + 실 기호 대조(Chroma 어댑터 `query_similar` 시그니처·`derive_memory_index_text` 투영·`JudgingBudget`·조립 지점 유일성).
- 초점: `python3 -m pytest tests/test_candidate_shortlist.py tests/test_context_search_canonical_memory.py tests/test_context_search_candidate_memory.py tests/test_docs_indexes.py -q` → **54 passed / 303 subtests**(22.67s).
- 변이: 선제 `git status --short` 무출력 확인 후 **6종**(구현자 표 5종의 재유도 + 검증자 자체 1종). 각각 적용→초점 실행→`git checkout -- <path>`→`git status --short` 무출력 확인. 결과는 요약 라인으로 판독(FAILED|SUBFAILED — `grep FAILED` 만으로는 subtest 실패를 놓는다).
- 실측: `docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system --eval '…countDocuments'` · `docker exec ai_writte_system-application-1 env`(벡터 다리 스위치).
- 전수: 호스트 `python3 -m pytest -q > /tmp/full_suite_2026-09-09_verify.log 2>&1; echo EXIT=$?`(test-mongo 27020 기동 상태, dev 스택 전체 구동 중).

## Findings

### 1. `e82c9ed` — 무순위 절단 경고

- [`service.py:196-202`](../../../services/application/app/context_search/service.py)(canonical)·`:417-423`(candidate) — `len > limit`일 때만 `_warn_unranked_truncation` 호출. **`degraded` 미변경 확인**(diff에 무관, `_run_canonical_memory_step` 미배선 분기의 `failure=None` 규약 그대로 — "step 실패 ≠ 미배선 능력" 구분 보존).
- 패턴 sweep 주장 사실: candidate 형제(`MongoDirectCandidateMemoryRetriever`)에 동일 결함이 나란히 존재했고 함께 수리됨.
- 회귀 4셀 양방향(under 2·over 2). over 셀이 경계값(상한==개수는 절단 아님, `>` vs `>=`)까지 잠근다.
- 로그 형태는 `rerank.py` 폴백 경고 선례와 동일한 "조용히 삼키지 않는다" 계열 — HTTP 계약 무변.

### 2. `7a34e21` — shortlist 배선

- seam 계약 확인: [`identity_judging.py:266-268`](../../../services/application/app/analysis/identity_judging.py)(retriever `None` → `()` 반환 no-op)·`:250-258`(character 정규화 이름 경로 — "character만 살아 있었다" 사실).
- **임계값 미생성 확인**: 어댑터 전체에 유사도 컷오프 없음. K는 `DEFAULT_CANDIDATE_SHORTLIST_LIMIT=5`(fanout 예산), env `ANALYSIS_CANDIDATE_SHORTLIST_LIMIT`로 조정 가능.
- ★ **테스트가 전부 fake 인덱스라 실 어댑터와 어긋나도 통과하는 지점을 형 검사로 닫음**: 실제 `ChromaCandidateVectorIndexAdapter.query_similar`([`indexing/chroma.py:500-522`](../../../services/application/app/indexing/chroma.py))가 구조적 Protocol과 정확히 일치(키워드 전용 인자·`project_id`+`candidate_type` where 필터·`limit<1` 가드).
- 읽기 투영 = 색인 쓰기 투영: [`candidate_index.py:145`](../../../services/application/app/indexing/candidate_index.py)이 쓰기에 같은 `derive_memory_index_text`를 사용 — "같은 투영" 주장 성립.
- import 방향: `analysis.candidate_shortlist → indexing.memory_index`/`indexing.models`만 — 순환 없음(`indexing.candidate_index`의 `analysis.service` import를 구조적 Protocol로 회피).
- 조립 지점 유일(`main.py:904` 한 곳, grep 확인), 의존 이름(`ChromaCandidateVectorIndexAdapter`·`connect_chroma_collection`·`CANDIDATE_VECTOR_COLLECTION`·`_build_embedding_provider`) 전부 모듈 레벨 import — **미실행 경로의 NameError 위험 없음**.
- 20쌍 상한: `DEFAULT_MAX_NEW_RELATIONS_PER_RUN=20`([`identity_judging.py:68`](../../../services/application/app/analysis/identity_judging.py)) + `JudgingBudget`(run 단위 뮤터블, runner가 run마다 하나) — "K는 상한과 함께 읽는 팬아웃 예산" 구조 성립.

### 3. 분석 주장 3겹 — 전부 원전에서 성립

- ① 판정 1:1: [`compare_judge.py:139-152`](../../../services/application/app/analysis/compare_judge.py)(후보 1 + 정본 1의 payload만 프롬프트에) · `identity_judge.py:135-144`(left/right 두 payload만).
- ② 정본 payload 비누적: [`memory/service.py:363-372`](../../../services/application/app/memory/service.py)(`evidence_only`면 `target.payload` 보존, `update`는 교체; 커지는 `source_ref_ids`는 프롬프트에 무관).
- ③ 하드 캡: `_apply_budget`([`service.py:1213-1222`](../../../services/application/app/context_search/service.py), 그리디 `total + token_estimate <= max_tokens` 아니면 제외·`budget_excluded` 기록). 단 work_log 인용 `1167-1188`은 `e82c9ed` 이전 줄좌표(아래 Hardening).

### 4. 브리프 사실 주장 — 전부 대조 일치

- [`agentic_search_flow.md`](../../agentic_search_flow.md) 모듈 표에 `ContextCompressor | token budget에 맞게 압축` 행 존재, 구현에는 `_apply_budget` 절단만 — "원설계에 있었고 구현에서 빠졌다" 성립.
- `MACRO_NEEDS = (CURRENT_SCENE, RECENT_SCENES)`([`context_search/models.py:89`](../../../services/application/app/context_search/models.py)) — "macro가 요약이 아니라 위치" 성립.
- `MemoryEntry`에 chapter 필드 0건(grep) — D2 숨은 전제 기록 성립.
- auto-promotion "Off by default (``None``)"([`memory/service.py:171`](../../../services/application/app/memory/service.py)) + 컨테이너 env에 `MEMORY_AUTO_PROMOTION_THRESHOLD` 부재 — D3 정정의 전제 성립.
- **실측 재측정 일치**(mongosh·env 직접): `memories 0 · analysis_candidates 0 · analysis_jobs 0 · source_blocks 640 · drafts 12` · 컨테이너 env `CHROMA_HOST=chroma`·`EMBEDDING_SERVICE_URL=http://embedding:8002` 존재·`ANALYSIS_SEMANTIC_MATCH_THRESHOLD` 부재.

### 5. 기록 갱신

- work_log 세션 48: 변이 표(5종 diff·기명 셀)·증분 귀속·Issues 절(전수 중 문서 수정으로 5실패 — 자기 실수의 원인·해결·교훈 구비) — records-and-handoff.md 요구 충족.
- HANDOFF: 함정 1줄(shortlist 벡터 다리 env)·결정표 2행·미수리 1행(무순위 폴백)·유예+트리거 1행(압축 층 D6) — "수술적 4곳" 일치. 유예 항목 전부 트리거 부착.
- CHANGELOG 1행. 증분 산술 검증: 셀 +11(경고 4 + shortlist 6 + 배선 1 = 신규 테스트 함수 수와 정확히 일치) · subtest +2(plans 문서 2건 × [`test_repo_hygiene.py:236`](../../../tests/test_repo_hygiene.py) 파일별 subTest — 라인 확인).

### 6. 변이 6종 — 전부 기명 재실패(요약 라인 판독)

| 변이 | diff | 재실패 셀 |
|---|---|---|
| MU-1 | canonical `_warn_unranked_truncation` 호출 블록 삭제 | `test_warns_when_the_unranked_backend_drops_entries` **1실패** |
| MO-1 | canonical `if len(canonical) > limit:` → `>=` | `test_does_not_warn_when_everything_fits` **1실패** |
| MU-2 | focal 제외 `continue` 2줄 삭제 | `test_focal_itself_is_never_shortlisted` **1실패** |
| MU-3 | `by_id.get(hit.candidate_id)` → `by_id.get(hit.candidate_id, pool[0])` | `test_hits_outside_the_pool_are_dropped` **1실패** |
| MO-2 | `if not pool: return ()` 조기 반환 삭제 | `test_empty_pool_buys_no_embedding_and_no_query` **1실패** |
| MU-4(검증자 추가) | `if len(selected) >= self._limit: break` 삭제 | `test_limit_caps_the_shortlist_and_asks_for_one_spare` **1실패** |

구현자 표 5종은 전부 재유도 가능하고 동일 셀에 적중. MU-4는 구현자 표에 없던 축(상한 break)으로, 테스트 독스트링의 주장("상한을 지우면 5가 재실패한다")을 독립 확인. 매번 원복 후 `git status --short` 무출력 확인.

### 7. 전수 재실행 — 수치까지 재현

호스트·test-mongo(27020) 기동·dev 스택 전체 구동 상태: **`2975 passed / 1 skipped / 4091 subtests · EXIT=0`**(2313.29s). **세션 48 보고(2975/1/4091)와 완전 일치.** skip 1 = live Chroma. 소요시간 차이(보고 1760s ↔ 재현 2313s)는 dev 스택 동시 구동에 따른 환경 차이로 판정 무관.

## Issues / Risks

### Blocking (contract obligations)

- **dedup 브리프 상태 미갱신 — 기록 간 모순.** [`event-open-question-canonical-dedup-decisions.md:3`](../../plans/event-open-question-canonical-dedup-decisions.md)이 `Proposed — 오너 결정 대기`로 남아 있고 [`docs/plans/README.md:73`](../../plans/README.md)의 인덱스 행도 같은 상태를 게시하는데, 오너는 ⓒ를 채택했고 구현(`7a34e21`)까지 끝났다(HANDOFF 결정 표·CHANGELOG·work_log "사용자 결정과 근거" 전부 그렇게 기록). 채택된 브리프는 예외 없이 `Resolved`(+결정 내용)로 갱신되는 관례이며([`02b-4`](../../plans/02b-4-memory-versioned-upsert-decisions.md)·[`05-writing-gate`](../../plans/05-writing-gate-decisions.md)·[`09-1`](../../plans/09-1-activity-timeline-screen-decisions.md) 등 전수 확인), **같은 세션의 압축 층 브리프는 갱신했다** — 이것만 빠졌다. 가드(`test_the_index_status_column_matches_the_document`)는 문서↔인덱스 **일치**만 검사해 둘 다 낡으면 통과하는 맹점. 다음 독자가 열린 결정으로 오해해 재브리프(CLAUDE.md가 금지하는 제조 브리프)하거나 결정 대기로 오인할 여지.
- **루트 README 전수 기준선 미갱신.** [`README.md:104`](../../../../README.md)가 `**2,964 passed / 4,089 subtests**`(세션 47 기준선, `6b476bf`)인데 세션 48 종결 전수는 **2975/4091**이다. 이 줄은 슬라이스 종결마다 갱신되는 관례다(`5288b7c` 2954→2963 · `6b476bf` 2963→2964 — `git log -L 104,104:README.md`로 확인)인데 세션 48은 자기 종결 수치를 올리지 않았다. 가드 밖의 숫자 주장이라 아무 테스트도 물지 않는다 — 위 브리프 상태와 같은 부류(종결 시 게시 상태가 실제를 따라가지 못함)의 두 번째 사례.

### Hardening recommendations (non-blocking)

- `ANALYSIS_CANDIDATE_SHORTLIST_LIMIT` env 파싱 엣지: 정수 아닌 값→조립 시 `ValueError`, `0`→이웃 1개 반환(break 검사가 append 뒤), 음수→`query_similar`의 `limit must be positive`. 기존 env 관례(`CHROMA_PORT` int 파싱)와 같은 형태라 위반은 아니나, 첫 도그푸드 전 K 점검 시 함께 볼 값.
- work_log 분석 인용 ③의 `service.py:1167-1188`은 `e82c9ed`(46줄 추가) 이전 줄좌표 — 인용 시점에는 정확했으나 로그 공시 시점(HEAD `36591c6`)의 좌표와 어긋남. 기록 정확성 니트.
- 배선된 shortlist는 실 Chroma·실 임베딩과 한 번도 실행되지 않았다(정본·후보 0건 — 실측). 개발 스택 컨테이너 env가 이미 `CHROMA_HOST`+`EMBEDDING_SERVICE_URL`을 갖춰 **이미지 재빌드 즉시 활성화**된다. 첫 도그푸드에서 그룹 형성·K 배분(run당 20쌍을 character와 나눔) 관측 필요(HANDOFF에 기록된 사항).

## Verdict

**조건부 합격** — ① dedup 브리프([`event-open-question-canonical-dedup-decisions.md:3`](../../plans/event-open-question-canonical-dedup-decisions.md))의 상태 라인과 [`docs/plans/README.md:73`](../../plans/README.md) 인덱스 행을 `Resolved`(ⓒ 채택·구현 `7a34e21` 완료)로 갱신할 것 · ② [`README.md:104`](../../../../README.md)의 전수 기준선을 2975/4091로 갱신할 것.

근거: 구현·회귀·변이·브리프 사실관계·실측·전수 전부 재검증되어 이견 없음(변이 6/6 기명 적중, 실측 5개 컬렉션·env 전부 일치, 전수 수치까지 재현). 차단물은 기록 계약 위 모순 둘(닫힌 결정이 열린 것으로 게시 · 종결 기준선 숫자 미갱신)이며, 모두 몇 줄 안 되는 수정으로 닫힌다.

## Outstanding items

- 커밋 6건(세션 48)+본 검증 기록 커밋, push 안 함(오너가 push).
- 압축 층 D6 트리거 대기(정본 총계 16건; 현재 0건 — 실측).
- Blocking 조건(브리프 상태 갱신)은 오너 승인 후 적용 — 검증자가 임의로 고치지 않는다(verification.md "실패를 조용히 고치지 않는다").

## Reproduction

```bash
git status --short   # clean 확인(변이 전제)
python3 -m pytest tests/test_candidate_shortlist.py tests/test_context_search_canonical_memory.py tests/test_context_search_candidate_memory.py tests/test_docs_indexes.py -q
# → 54 passed, 303 subtests
docker exec ai_writte_system-mongo-1 mongosh --quiet ai_writing_system \
  --eval 'for (const c of ["memories","analysis_candidates","analysis_jobs","source_blocks","drafts"]) print(c+": "+db.getCollection(c).countDocuments({}))'
# → memories 0 · analysis_candidates 0 · analysis_jobs 0 · source_blocks 640 · drafts 12
python3 -m pytest -q > /tmp/full_suite.log 2>&1; echo EXIT=$?; tail -3 /tmp/full_suite.log
# → 2975 passed, 1 skipped, 4091 subtests · EXIT=0
# 변이: 위 표의 diff를 적용 → 초점 실행(1실패 확인) → git checkout -- <path> → git status --short 무출력
```
