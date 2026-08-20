# 리랭커 슬라이스(7a88ac1·f14917b) + 임베딩 조건 폐쇄(a9bca6d) 재검 — 독립 검증

## Subject metadata

- **날짜**: 2026-08-20 (베타)
- **요청자**: 오너 — *"다음작업 검증해줘. 미검증 3커밋에 대해서 전부 진행해주면 돼. 리랭커 슬라이스 완료했습니다."* (구현자 자문: *"② fail-open이 정말 모든 실패를 덮는가가 제가 스스로 의심하는 자리 — 지금 text_of가 예외를 던지면 데코레이터가 안 잡습니다"*)
- **검증자**: 이 세션 — 리랭커 슬라이스 구현 세션이 아니다(같은 날 `cd1d82d`·임베딩 어댑터 검증을 한 세션).
- **대상 커밋**: `7a88ac1`(seam+어댑터+데코레이터·4-①) · `f14917b`(하네스+external·4-②) · `a9bca6d`(임베딩 조건 B1 폐쇄 — **재검 대상**, 승격 확정은 아래 Findings 7) · 기록 계열 `4201b16`·`0b0ae73`·`4189a58`(감사로 덮음)
- **정본 참조**: [`docs/plans/reranker-slice-decisions.md`](../../plans/reranker-slice-decisions.md)(Resolved) — 결정 2·3·4 확정문 · §산출물 · §"구현에서 정해진 것" · §남은 것(트리거 표)
- **작업 트리 상태**: 검증 시작 HEAD `4201b16`, clean. 재현 스크립트 체크포인트 `5a0ca0a` 포함. 뮤테이션 사이마다 `git status --short` 공백 확인.

## Scope

1. **★ 구현자 자문 축 — fail-open 이 "모든 실패"를 덮는가.** `text_of`(텍스트 투영) 예외의 행동 실증 + 셀 문언과의 대조.
2. 조립 가드의 우회 가능성(`RerankingRetriever` 유일-생성자 셀) — B1(임베딩)과 같은 이름-재결합 계열인가.
3. 구현자 뮤테이션 R1~R7 같은 diff 재유도(두 차례의 뮤테이션 실수 정정 기록 포함).
4. 산출물 4건(2=A seam·no-op · 3=A 데코레이터+가드 · 4-① 배선·안전성 셋 · 4-② 하네스 무정답+경계셀) · env 표기 · 표기 3분할.
5. **임베딩 조건 B1 폐쇄(`a9bca6d`) 독립 재검** — 폐쇄 세션의 자체 승격을 검증자가 확인.
6. 전수 `2350/1/2582` 재현.

## Methodology

- 포커스: `tests/test_rerank.py tests/test_eval_retrieval_ranking.py` → 기준 **28 passed / 26 subtests**(18+10셀).
- **런타임 실증**(C1): `text_of` 가 `ValueError` 를 던지는 상태에서 `retrieve()` 를 직접 호출([repro 스크립트](repro_reranker_slice.sh) Part 1).
- **뮤테이션 10종**(RV-A·RV-B1·RV-B2·R1·R2·R3b·R4·R5·R6b·R7 + 하네스 경계 .jsonl 투입): clean-tree 분기, 리터럴 `count==1` 단정(이 단정이 검증자의 들여쓰기 실수 R6b 1회를 잡았다 — 구현자가 R3·R6 초판에서 겪은 것과 같은 병, 기록함), 복원 `git checkout --` + status 공백.
- 임베딩 B1 폐쇄 재검: [`repro_embedding_assembly.sh`](repro_embedding_assembly.sh) 전체 재실행(V1 뒤집힘 확인).
- 전수: `python3 -m pytest -q`(test-mongo 27020 healthy — §"Recording a measurement" 절차).

## Findings

### 1. ★ 구현자 자문 축 — fail-open 은 "모든 실패"를 안 덮는다(→ 조건 C1)

- **런타임 실증**: `text_of` 가 `ValueError` 를 던지면 `RerankingRetriever.retrieve` 는 그 예외를 **그대로 새어나가게 한다** — `[ValueError] 이(가) 그대로 새어나감 — 검색 경로가 죽는다`([`rerank.py:80-85`](../../../services/application/app/context_search/rerank.py) 의 `except RerankProviderError` 가 프로바이더 오류만 잡고, try 블록 안의 투영 컴프리헨션은 안 잡는다). 구현자의 자문이 정확했다.
- **왜 조건인가**: [`FailOpenTest`](../../../tests/test_rerank.py) docstring 이 *"**모든 실패가** 원래 순서로 떨어진다"* 라고 단정하고, 브리프 4-①③이 잠그려는 값은 *"검색이 죽지 않는다"* 다. 투영(`derive_memory_index_text`)은 **이 슬라이스가 검색 경로에 새로 넣은 호출**이므로(색인 시점에만 쓰이던 함수), 그 예외로 검색이 죽는다면 그 길은 이 슬라이스가 만든 것이다. 문언("모든 실패")이 잠금보다 넓다 — mypy H4(셀 문언 과대)와 B1(현실적 벡터)의 중간 모양이고, 벡터(payload 모양 드리프트)는 저장 데이터가 시간에 따라 변하는 저장소에서 무시할 수준이 아니다. **폐쇄 형태 둘**(오너 선택): (i) **단계 전체 fail-open** — 투영 컴프리헨션 포함 try 범위를 넓히거나 `except Exception`(재발생 제외 정책을 문언으로) — 권장. (ii) 문언 스코프 — "프로바이더 실패"로 좁히고 브리프 4-①③에 투영 예외가 열려 있음을 명시. 폐쇄 확인은 [repro 스크립트](repro_reranker_slice.sh) Part 1 의 출력이 *"새어나감"* → *"원래 순서 반환"* 으로 뒤집히는 것이다.

### 2. 조립 가드 우회 — 유일-생성자 셀의 이름-재결합 맹점(비차단 H1)

| 뮤테이션 | 가드 반응 |
|---|---|
| RV-B1 `import …rerank as _rr` 후 `_rr.RerankingRetriever(…)`(main.py 내 두 번째 생성 경로) | **침묵 — 18 passed** |
| RV-B2 `from … import RerankingRetriever as RR` 후 `RR(…)` | **침묵 — 18 passed** |
| R1/R2 감싸기 누락(계약 자리) | **잡음** — both-sites 셀 subtest |

- [`test_the_wrapper_is_the_only_place_that_builds_the_decorator`](../../../tests/test_rerank.py) 는 `ast.Name` 원이름만 세므로 속성·별칭 생성이 우회한다 — **임베딩 B1 과 같은 계열**이고, 이 셀은 B1 폐쇄(`a9bca6d`, 같은 날) **뒤에** 작성됐는데 그 학습(asname 맵)이 적용되지 않았다. 다만 브리프가 요구한 가드(감싸기 누락 방지, R1/R2)는 **소리 내게 작동**하고 이 셀은 보강 셀이므로 조건이 아니라 권고로 둔다(H1). 처방은 `a9bca6d` 의 `_constructor_names` 를 그대로 옮기는 것.
- 가드 스캔이 `main.py` 한 파일인 것은 브리프 계약 자리(조립 지점 둘)와 정합 — 새 검색 계열은 `_build_*_memory_retriever` 이름 패턴 셀이 분류를 강요한다(실증: 셀 존재 확인).

### 3. R1~R7 같은 diff 재유도 — 전부 일치

| # | 재유도 결과 | 구현자 주장 |
|---|---|---|
| R1 정본 감싸기 누락 | both-sites 셀 `_build_canonical_memory_retriever` subtest 실패 ✓ | ✓ |
| R2 candidate 감싸기 누락 | 같은 셀 `_build_candidate_memory_retriever` subtest 실패 ✓ | ✓ |
| R3b fail-open→fail-closed | `test_a_provider_error_returns_the_original_order` 실패 ✓ | ✓ |
| R4 순열 검사 제거 | non-permutation 셀 5 subtest 실패(짧다·길다·중복·범위 밖·빈 응답 전부) ✓ | ✓ |
| R5 0·1개도 호출 | nothing-to-reorder 셀 subtest 2 실패 ✓ | ✓ |
| R6b 동률 인덱스 역순 | `test_ties_keep_the_request_order` 실패 ✓(첫 시도는 검증자가 들여쓰기 8칸으로 써 `count=0` 단정에 걸렸다 — 고쳐 재실행. 구현자의 R6b 초판 교훈과 동일한 형태) | ✓ |
| R7 bool 인덱스 허용 | malformed 셀 `index is bool` subtest 실패 ✓ | ✓ |

- 구현자가 R3·R6 초판 실패(문법 오류로 수집 사망·행동 no-op)를 **스스로 기록하고 다시 했다**는 서술은 재유도 결과(두 뮤테이션이 최종적으로 물어야 하는 셀이 정확히 물림)와 정합한다.

### 4. 산출물 4건 — 확정값 넷과 일치

- **2=A seam+어댑터·no-op**: 주소 없으면 `build_rerank_provider_from_env()` → **`None`**(셀 `test_no_address_means_no_provider_at_all` — 임베딩 fake 와 의도적으로 다름을 docstring 으로 정당화) · 주소 있는데 모델 없으면 기동 시 `ValueError` · 접미 `/v1` 벗기기 + 경로 안 `v1` 무영향(임베딩과 같은 패턴, over-strict 셀 존재).
- **3=A 데코레이터**: 두 조립 자리가 `_rerank_wrapped` 로 모으고 vector-only·lexical-only 도 감쌈(main.py diff 확인) · **도메인 코드 0줄**(`Hybrid*Retriever` 본체 무변 — diff 는 배선 교체뿐) · Protocol 무변 · 새 컨테이너 0.
- **4-① 배선·안전성 셋**: 순서 변경(3셀 — 순서·투영 통과·0·1개 미호출) · 끌 수 있음(None=정상값) · fail-open(프로바이더 오류·비순열 5종) ✓ — 단 fail-open의 "모든 실패" 문언은 Findings 1.
- **4-② 하네스**: `scripts/eval_retrieval_ranking.py` 157줄 — `--input` JSONL + `--k`; 지표 recall@k(절단)·**MRR(절단 안 함 — 3위와 30위가 같아지지 않는다)**·nDCG(이분 등급); **"구성 이름 → 순위 목록" 포맷**(재색인 전후가 아니라 임베딩 교체·RRF k 조정 비교에도 쓰이는 설계 그대로); 일부 질의에만 있는 구성 거부 셀 ✓; **경계셀 실증 — 저장소에 `.jsonl` 를 넣으면 `test_the_repository_ships_no_evaluation_set` 실패**(가짜 파일 투입으로 확인). 정답(gold)은 표본 외 없음 ✓.
- **wire 의 계약 수정(D2=A 글자 vs 성질)**: OpenAI 에는 rerank 엔드포인트가 없다는 지적은 사실이고(OpenAI API 에 `/v1/rerank` 는 없다), generic 자리는 Cohere 가 낸 `POST /v1/rerank`(Jina·Voyage·TEI·infinity 공유)다 — **정본의 글자가 아니라 겨눈 성질을 따랐고 그 판단을 브리프 §"구현에서 정해진 것"에 박았다** ✓. wire 셀이 경로·요청 `{model,query,documents}`·응답 `results[{index,relevance_score}]`·Bearer 를 각각 단정.
- **env 표기**: `RERANK_API_URL/MODEL/KEY` 셋 다 대시 `${VAR-}`, external 에서 **`:?` 아님**(리랭커 없이 뜨는 것이 정상 구성) — 브리프 위임 표와 일치. 배포 렌더에서 셋 다 빈 값 통과·rc=0 확인(임베딩 검증과 같은 `--env-file /dev/null` 절차).
- **표기 3분할**: HANDOFF 부채 줄이 "외부 API 리랭커 붙일 수 있음(기본 꺼짐) · self-host 미구현 · 품질 평가 미실시" 로 갈라졌고 헤더 표기 규칙 줄과 정합(§228·§320 확인).

### 5. mypy 가 실제로 값을 낸 사례(구현자 서술) — 정합

구현자는 "조립에 텍스트 투영을 넣으며 import 를 빠뜨렸는데 import main 은 통과, mypy 가 `Name "derive_memory_index_text" is not defined` 로 잡았다"고 적었다 — 이는AST 가드(실행되지 않는 참조는 못 봄)와 mypy(정적)의 역할 분담 서술과 정합하고, 오늘 아침 슬라이스(typecheck 가드)가 같은 날 오후 슬라이스를 구한 형태다.

### 6. 전수 회귀

- **`2350 passed · 1 skipped · 2583 subtests`**(1171초, 이 기록 등재 후 트리에서 실측) — **passed 2350 · skip 1 은 구현자 예고와 정확히 일치**하고, subtest 는 2583 = 구현자 실측 2582 + **이 기록의 인덱스 등재분 1**(판정 열 전수 셀). 산출 경로: `2322/1/2556`(폐쇄분 뒤) + 셀 28(`test_rerank` 18 · eval 10) + subtest 26. skip 1 = live Chroma.

### 7. 임베딩 조건 B1 폐쇄(`a9bca6d`) 독립 재검 — **승격 확정**

- [`repro_embedding_assembly.sh`](repro_embedding_assembly.sh) 전체 재실행: **V1(별칭 import)이 `16 passed` → 가드 실패로 뒤집혔다**(가드가 asname 맵으로 잡는다) · V1b(모듈 속성) 여전히 잡음 · **V1c(할당 별칭)는 셀 문언에 명시된 잔여로 침묵** — 처방 (i) 그대로. H2(디렉터리 분류 강요 — `_SCANNED`/`_OUT_OF_SCOPE` + 반대 방향 셀)·H1(env 표기 셀)·관측(`if __name__` 위치)도 폐쇄 확인. 폐쇄 세션이 자체 승격을 선언했으나 **독립 재검이 없는 승격이었으므로, 이 재실행으로 승격이 확정됐다.** 폐쇄 세션이 인덱스 행·기록 Verdict 줄을 갱신하지 않은 채 남겨둔 것(판정 분포와 불일치)을 이 기록과 함께 바로잡는다(아래 Outstanding).

## Issues / Risks

### Blocking (조건)

- **C1 — fail-open 이 투영(`text_of`) 예외를 안 덮는다**(Findings 1). 셀 문언 *"모든 실패"* · 브리프 값 *"검색이 죽지 않는다"* 와 행동이 어긋난다. 폐쇄: (i) 단계 전체 fail-open(권장) 또는 (ii) 문언·브리프 스코프 명시. 확인: 재현 스크립트 Part 1 출력 뒤집힘.

### Hardening recommendations (비차단)

- **H1 — 유일-생성자 셀의 속성·별칭 우회**(Findings 2). B1 폐쇄 학습(`_constructor_names`)을 이 셀에도 적용하거나, 셀 문언을 "원이름 직접 생성"으로 좁힌다.
- **H2 — 동률 문언 정밀도**: [`rerank.py:190`](../../../services/application/app/context_search/rerank.py) 주석 *"점수 동률에서는 요청 순서를 유지한다"* 는 **응답이 동률 항목을 요청 순서로 보낼 때만** 참이다(안정 정렬은 응답 순서를 보존한다). 셀(`test_ties_keep_the_request_order`)도 그 전제의 응답만 시험한다. R6b 가 물긴 하지만, 문언을 "응답의 동률 순서를 유지(정합 서버에서 요청 순서)"로 정확히 하거나 인덱스 tie-break 를 명시 계약으로 만드는 편이 정직하다.
- (관측) 구현자·검증자가 같은 날 같은 뮤테이션 실수(행동을 안 바꾸는 diff / 들여쓰기로 미적용)를 각각 한 번씩 냈다 — `count==1` 단정과 "행동이 바뀌었는가 먼저 보기"가 둘 다 잡았다. 재현 스크립트에 그 교훈을 주석으로 박아 뒀다.

## Verdict

**조건부 합격** — C1(fail-open의 text_of 예외 미달 폐쇄)을 닫을 것. 나머지는 전부 성립: R1~R7 같은 diff 재현 · 산출물 4건이 확정값 넷과 일치(no-op 기본·데코레이터 도메인 0줄·하네스 무정답+경계셀 실증) · D2=A 글자-성질 계약 수정이 사실에 맞고 브리프에 기록됐으며 · 임베딩 조건 B1 폐쇄는 독립 재검으로 **승격 확정**됐다.

## Outstanding items

- **조건 C1 폐쇄 대기(오너 선택: (i) 단계 전체 fail-open 권장 / (ii) 문언 스코프)** — 폐쇄 커밋은 새 미검증 1커밋이 되고, 재현 스크립트 Part 1 로 재검한다.
- **임베딩 기록 승격 정리**: 인덱스 행 판정 `조건부 합격` → `합격(승격)`, 판정 분포(조건부 70→69·합격 176→177)를 이번 커밋에서 바로잡는다(폐쇄 세션이 놓친 자리 — Findings 7).
- dogfood(GATE-1)가 리랭커 품질 판정·임베딩 배치 트리거를 당기는 구조는 변함없고, **그 전에 외부 키**가 선행(기본 꺼짐 — no-op 대 no-op)이라는 서술은 유예 표와 정합.

## Reproduction

```bash
bash docs/verifications/2026-08-20/repro_reranker_slice.sh          # C1 실증 + RV-B + R1~R7 + 경계셀
bash docs/verifications/2026-08-20/repro_embedding_assembly.sh      # B1 폐쇄 재검(V1 뒤집힘)
python3 -m pytest -q tests/test_rerank.py tests/test_eval_retrieval_ranking.py
```
