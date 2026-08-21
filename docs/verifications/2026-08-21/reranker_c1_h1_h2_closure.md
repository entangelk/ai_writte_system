# 폐쇄 커밋 `92b9b24`(조건 C1 + H1·H2) 독립 검증 — 승격 확인

## Subject metadata

- **날짜**: 2026-08-21
- **요청자**: 오너 — *"작업 AI가 작업했던 부분 확인해서 검증하고 의심하고 또 의심해줄래? 커밋 독립검증(92b9b24) […] 그 뒤로 작업이 좀 진행되어서 저 커밋부분만 독립 검증해주면 될꺼같아."*
- **검증자**: 이 세션 — `92b9b24` 구현 세션이 아니고, §조건 폐쇄 재검 표를 쓴 세션도 아니다.
- **대상 커밋**: `92b9b24`(fix: fail-open 을 단계 전체로 + 유일-생성자 가드 별칭 인식 + H2 문언 정정)
- **정본 참조**: [`docs/verifications/2026-08-20/reranker_slice.md`](../2026-08-20/reranker_slice.md) — 조건 C1(블로킹)·H1·H2 원문과 §조건 폐쇄(**★ 구현 세션이 나중에 쓴 절** — 그대로 믿지 않고 전 항을 재유도했다). 배경 계약: [`docs/plans/reranker-slice-decisions.md`](../../plans/reranker-slice-decisions.md) 결정 4-①③("검색이 죽지 않는다").
- **작업 트리 상태**: 검증 시작 HEAD `1f9df97`, clean. **대상 두 파일(`rerank.py`·`test_rerank.py`)은 `92b9b24` 이후 무변** 확인(`git diff 92b9b24 HEAD` — 이후 커밋은 기록 계열과 제품명 스윝뿐). 검증 중 체크포인트 2건: 재현 스크립트 신규 `ee57a16`·R3b 갱신 `33461cc`. 뮤테이션 사이마다 `git status --short` 공백 확인.

## Scope

1. **★ C1 폐쇄 — 단계 전체 fail-open**: 코드 구조·`FailOpenScopeTest` 4셀 감사·런타임 재현(Part 1 출력 뒤집힘).
2. 폐쇄 세션 자체 재검 표(**C1-M1~M3**)의 같은 diff 재유도 — 페어링 대조.
3. **H1 폐쇄**: RV-B1/B2 뒤집힘 재실증·임베딩 처방(`_constructor_names`)과의 동형성·잔여(할당 별칭) 확인.
4. **H2 폐쇄**: 문언 정정 확인 + 셀 이름 잔여 조사.
5. 인계 **"볼 만한 축 셋"**([`docs/daily_logs/2026-08-20/work_log.md:840-843`](../../daily_logs/2026-08-20/work_log.md)) — ① `except Exception` 경계 과대 ② `assertNoLogs` 스코프 ③ 재현 스크립트 R3b 낡은 리터럴(차기 검증자 위임 — 이행).
6. 포커스·전수 회귀.

## Methodology

- 포커스: `python3 -m pytest -q tests/test_rerank.py tests/test_eval_retrieval_ranking.py` → **32 passed / 29 subtests**(종전 28/26 + 폐쇄분 4셀·3서브테스트[투영 3예외형] — 델타 산술 정합).
- 재현: [`repro_reranker_c1_closure.sh`](repro_reranker_c1_closure.sh)(**신규 작성·커밋** — C1-M1~M3 + H1 잔여) + [`2026-08-20/repro_reranker_slice.sh`](../2026-08-20/repro_reranker_slice.sh) 전체(Part 1·2·3·4).
- 뮤테이션: verification.md "clean-tree" 분기 — `mutfile` 리터럴 `count==1` 단정(적용 여부를 흉내 내지 않게), 복원 `git checkout --` + `git status --short` 공백 매번 확인. 판독은 **요약 줄과 `FAILED|SUBFAILED` 둘 다**(grep FAILED 만 읽으면 subtest 실패를 놓친다 — 그 낡은 병은 이 저장소가 이미 두 번 기록했다).
- R3b 갱신 검증: 낡은 리터럴(`except RerankProviderError:` 계열 — count=0)을 새 경계 리터럴로 교체한 뒤 **그 블록을 실행해 물리는 것을 확인**(11 failed).
- 전수: `python3 -m pytest -q` — test-mongo 27020 healthy(`docker ps`로 확인 — §"Recording a measurement" 절차).

## Findings

### 1. ★ C1 — 구조·셀·런타임, 전부 폐쇄 주장과 일치

- **구조**: [`rerank.py:89-114`](../../../services/application/app/context_search/rerank.py) — 투영(94)·프로바이더 호출(95)·순열 검사(96-102, 위반은 `RerankProviderError` 로 상승)·재조립(103)이 **한 `try` 안**에 있고, 경계는 `except Exception` + `# noqa: BLE001`(104), `logging.WARNING` + `exc_info=True`(111-112), 원래 순서 반환(113). 모듈 docstring(12-20)도 "단계 전체"로 갱신 — **계약 문언과 잠금이 같은 폭**(이 조건의 본질이 그 간극이었다).
- **셀 감사**(`FailOpenScopeTest`, [`tests/test_rerank.py:132-192`](../../../tests/test_rerank.py)): (a) 투영 3 예외형 서브테스트 — ValueError·KeyError·TypeError(payload 모양 드리프트 계열의 현실 벡터) (b) 어댑터가 못 감싼 비예상 예외(RuntimeError) (c) **로그 셋** — 메시지("reranking failed")와 예외형("RuntimeError") 둘 다 단정 (d) **over-strict** — 정상 경로 `assertNoLogs`. 전부 호출자가 의존하는 공개 표면(반환 순서·로그)을 잠근다.
- **런타임**: repro Part 1 — `text_of` 가 `ValueError` 를 던지면 **"결과: 정상 반환(fail-open 작동)"** + WARNING/traceback 출력. 종전 "새어나감"에서 뒤집혔다 — 폐쇄 확인 문헌이 지정한 정확히 그 관측이다.

### 2. C1-M1~M3 같은 diff 재유도 — 전부 일치

| 뮤테이션 | 재유도 결과(이 세션) | 폐쇄 세션 표 |
|---|---|---|
| C1-M1 경계를 다시 `except RerankProviderError` | **5 failed** — 투영 3 서브테스트 + 비예상 예외 셀 + 로그 셀 | "FailOpenScopeTest 3셀 + subtest" ✓ |
| C1-M2 경고 제거(조용한 fail-open) | 로그 셀만 **1 failed** | ✓ |
| C1-M3 정상 경로도 경고 | `assertNoLogs` 셀 **1 failed**("Unexpected logs found") | ✓ |

under-strict(M1)·over-strict(M3) **양방향 모두 문다.**

### 3. H1 — 뒤집힘 재실증 + 처방 동형성 + 잔여 문언 정직성

- repro Part 2 재실행: **RV-B1**(모듈 속성 `_rr.RerankingRetriever(…)`)·**RV-B2**(별칭 `RR(…)`) 모두 유일-생성자 셀 **FAILED**(종전 침묵) ✓.
- **처방 동형성**: 임베딩 `_constructor_names`([`tests/test_embedding_assembly.py:75-93`](../../../tests/test_embedding_assembly.py) — asname 수집)과 이 셀([`tests/test_rerank.py:418-432`](../../../tests/test_rerank.py))의 실질 차이는 속성 검사가 원이름 고정(`attr == "RerankingRetriever"`)이라는 것뿐이다. `from … as RR` 뒤 `mod.RR(…)` 형태를 임베딩 셀은 잡고 이 셀은 못 잡지만, 그 형태는 별칭을 다른 네임스페이스에 심는 **이름 재결합 계열**로 양쪽 가드 모두 문언에 명시한 잔여 바깥의 자연스러운 경계다. 현실적 벡터(직접 별칭 호출·모듈 속성 호출)는 잡힌다.
- **잔여 확인**: 할당 별칭(`X = RerankingRetriever; X(…)`)을 main.py 에 투입 → **22 passed 침묵**. 셀 문언이 잠금보다 넓게 서술됐는지 보는 방향 실증 — **문언 과대 없음**(잔여가 문언 그대로 존재한다).

### 4. H2 — 원문 자리는 정정, 셀 이름에 잔여

- [`rerank.py:212-217`](../../../services/application/app/context_search/rerank.py) 주석이 *"요청 순서"* → **"응답에 담긴 순서"** 로 정정됐고 정정 사유(H2, 2026-08-20)가 그 자리에 기록돼 있다 ✓. 안정 정렬이 보존하는 성질에 대한 서술("같은 응답이 언제나 같은 순서를 낸다")도 정확하다.
- R6b(동률 인덱스 역순) 재유도 시 동률 셀이 여전히 물림 ✓(repro Part 3).
- **잔여**: 셀 이름 자체(`test_ties_keep_the_request_order`, [`tests/test_rerank.py:340`](../../../tests/test_rerank.py))가 여전히 "request order" 다. 행동은 유효 — 동률이 **요청 순서로 온 응답**을 시험하므로 — 그러나 H2 가 정정한 문언이 셀 이름에는 살아 있다. 아래 Hardening(H2-a).

### 5. 인계 "볼 만한 축 셋" 판정

- **① 경계 과대(프로그래밍 오류까지 삼키는가)**: `BaseException` 계열(`KeyboardInterrupt`·`SystemExit`)은 전파 — 삼키지 않는다. `Exception` 안의 프로그래밍 오류는 삼키되 WARNING + 전체 traceback 가 남는다(그것이 폐쇄가 택한 설계). *"로그는 남지만 테스트는 초록"* 인 상황의 실체: 투영이 고장 나면 `test_the_returned_order_follows_the_provider`([`tests/test_rerank.py:67-75`](../../../tests/test_rerank.py), 순서가 실제로 바뀜을 단정)가 실패한다 — fail-open 반환값 `("a","b","c")` 는 기대값 `("c","a","b")` 와 다르다. 즉 고장이 fail-open 뒤에 숨어 스위트가 초록인 길은 **실패 주입 상황뿐**이고 그 초록은 `FailOpenScopeTest` 의 계약 자체다. 운영에서의 검출기는 WARNING(폐쇄 문언의 설계 의도)이다.
- **② `assertNoLogs` 스코프**: 셀은 `services.application.app.context_search.rerank` 로거 한 곳만 본다(이름 인자 + `level=WARNING`) — 다른 로거의 경고를 막지 않는다(오탐 없음). C1-M3 에서 정확히 그 로거의 경고만 잡히는 것도 확인.
- **③ R3b 낡은 리터럴 — 이행 완료**: 새 경계 리터럴로 갱신(커밋 `33461cc`), Part 2 echo 2건("현재 침묵" → "폐쇄 후 실패")도 정정. 갱신된 R3b(`except Exception:` → `raise`, fail-closed) 재실행 **11 failed** 로 물림 확인 — 프로바이더 오류 셀 + 비순열 5서브테스트 + FailOpenScope 3셀·3서브테스트.

### 6. 전수 회귀

- **`2357 passed · 1 skipped · 2589 subtests`**(1244초, 등재 전 트리 실측) — `1f9df97` 실측(2357/1/2589)과 정확히 일치. 체인 전체 정합: 2350/2583(슬라이스 검증 기준) → `92b9b24` +4셀·3서브테스트 → 2354/2586(`90164df` 기록) → 제품명 스윕 +3셀 → 2357/2589. skip 1 = live Chroma. 이 기록 등재 후 기대 subtest 2590(등재분 +1).

## Issues / Risks

### Blocking (조건)

- 없다.

### Hardening recommendations (비차단)

> **[전부 닫힘 2026-08-21 `cfcb182` — 오너 취사 결과: 셋 다 채택. 프로덕션 코드 0줄.]** 아래 원문은 발행 시점 그대로 두고, 각 항에 폐쇄 결과를 붙인다.

- **H2-a — 동률 셀 이름 잔여**: `test_ties_keep_the_request_order`([`tests/test_rerank.py:340`](../../../tests/test_rerank.py))는 H2 가 정정한 문언("요청 순서 유지")을 이름에 그대로 담고 있다. 잠근 성질("같은 응답이 언제나 같은 순서")에 맞는 이름(예: `test_ties_keep_the_response_order`) 또는 전제 문언("정합 서버에서 요청 순서와 일치")을 docstring 으로.
  - **[닫힘 `cfcb182`]** `test_ties_keep_the_response_order` 로 개명 + docstring 에 전제("정합 서버가 동률을 요청 순서로 보낼 때만 둘이 겹치고, 계약은 그것을 약속하지 않는다")를 명시. 종전 이름은 저장소 어디에서도 참조하지 않았다(과거 기록 셋은 **그때 잰 이름**이므로 그대로 둔다 — `daily_logs/2026-08-20/work_log.md` 표 2곳 · `reranker_slice.md` R6b 행 · 이 기록 위 §H2).
- **H2-b — 동률 응답 순서 셀 부재**: 동률이 **요청 순서가 아닌 순서**로 온 응답(예: `results` 가 `[2,0,1]` 동점)에서 응답 순서 보존을 단정하는 셀이 없다. 현재 셀은 두 해석이 우연히 겹치는 입력만 시험한다 — R6b 는 잡지만 "응답 순서 보존" 성질 자체는 잠기지 않는다.
  - **[닫힘 `cfcb182`]** 같은 셀에 **두 해석이 갈리는 입력**(응답 `[2,0,1]` 전부 동점 → 기대 `(2,0,1)`)을 subtest 로 더했다. 종전 입력은 회귀로 남긴다.
  - **★ 지적이 가리킨 구멍이 가상이 아니었다.** 새 뮤테이션 **N1**(`sort(key=(-score, index))` — 동률을 **오름차순 인덱스**로 tie-break)은 **종전 셀이 원리적으로 못 본다**: 그 배치에서 동률은 요청 순서와 같아지므로 종전 입력의 기대값 `(0,1,2)` 가 그대로 나온다. 실측 — N1 에서 **새 subtest 만 실패**(`SUBFAILED(response='응답이 다른 순서로 왔다')`, 나머지 23 passed). 즉 H2-b 는 "성질이 안 잠겼다" 를 넘어 **실재하는 뮤테이션 계열 하나가 통째로 안 보이는 상태**였다.
  - **R6b(원본 리터럴, 내림차순 인덱스)의 페어링이 바뀐다: 1 → 2** — 이제 두 subtest 를 모두 문다(`repro_reranker_slice.sh` 재실행 실측: `2 failed, 23 passed, 24 subtests`). 스크립트 리터럴은 무변.
- (관측) **비순열 경로의 로그 단정 부재**: 순열 검사가 `try` 안으로 들어왔다는 주장("한 곳에서 떨어진다")의 관측 가능한 차이는 그 경로의 WARNING 인데, 로그 셀은 프로바이더 예외 경로만 잠근다. 계약(fail-open)은 순열 검사가 밖에 있어도 만족하므로 조건이 아니라 관측으로 남긴다.
  - **[닫힘 `cfcb182`]** `FailOpenScopeTest::test_a_response_that_is_not_a_permutation_is_logged_too` 신설 — WARNING 이 나는 것과 **원인이 `not a permutation` 으로 남는 것**까지 단정한다(프로바이더 장애와 구별되지 않으면 부분 응답 `top_n` 을 장애로 오진한다).
  - **관측이 정확했다는 실증**: 뮤테이션 **N3**(순열 검사를 `return items` 로 — 경계 **밖** 배치와 반환값이 동형)에서 **기존 `FailOpenTest` 비순열 셀 5 subtest 는 전부 green** 이고 **새 셀만 실패**한다. 반환값이 같으니 로그 말고는 갈릴 것이 없다는 지적 그대로다.
  - 곁가지: `R4`(순열 검사 제거)와 `N4`(`exc_info=False`)도 이 셀을 문다 — 후자는 기존 로그 셀과 함께 2 failed.

## Verdict

**합격** — C1 폐쇄(단계 전체 fail-open + WARNING)는 구조·셀 감사·런타임 재현·양방향 뮤테이션(C1-M1 5failed·C1-M2·C1-M3) 전층에서 성립한다. H1(RV-B1/B2 뒤집힘·처방 동형성·잔여 문언 정직성)·H2(원문 정정, 셀 이름 잔여는 비차단)도 확인. 폐쇄 세션의 자체 재검 표는 과장 없이 일치했다. **→ [`reranker_slice.md`](../2026-08-20/reranker_slice.md) 의 조건부 합격을 승격 확인**(임베딩 B1 승격과 같은 절차 — 인덱스 행·기록 Verdict 줄·판정 분포를 이 커밋에서 정리).

## Outstanding items

- **리랭커 슬라이스 기록 승격 정리**(이 커밋으로 이행): reranker_slice.md Verdict 줄 승격 표기·인덱스 행 `**합격**` 전환·판정 분포 갱신 — 폐쇄 세션이 남겨둔 자리(임베딩 사례와 같은 모양).
- dogfood(GATE-1) 선행 = 외부 키(변함없음). ~~이 승격으로 **미검증 커밋 0**.~~ **[정정 2026-08-21]** 리랭커 계열은 0 이 맞지만 **저장소 전체로는 0 이 아니었다** — 같은 날 먼저 들어온 `29299e5`(제품명 H2)·`1f9df97`(그 기록)이 미검증이고, 이 보강 커밋 `cfcb182` 도 그렇다. HANDOFF §마감 메모 ②는 처음부터 그렇게 적고 있었다. **이 저장소가 다섯 번 밟은 계열**(미검증 목록을 문구에서 유도)이라 그대로 남긴다 — 정확한 목록은 `git log <최신 검증기록 커밋>..HEAD`.
- Hardening 3건(H2-a·H2-b·비순열 로그 관측)은 오너 취사 — 어느 쪽도 이 슬라이스 계약에 필요하지 않다.

## Reproduction

```bash
bash docs/verifications/2026-08-21/repro_reranker_c1_closure.sh      # C1-M1~M3 + H1 잔여
bash docs/verifications/2026-08-20/repro_reranker_slice.sh            # Part 1(C1)·2(H1)·3(R1~R7, R3b 갱신분 포함)·4
python3 -m pytest -q tests/test_rerank.py tests/test_eval_retrieval_ranking.py   # 32 passed / 29 subtests
python3 -m pytest -q                                                 # 전수(등재 전 기준 2357/1/2589)
```
