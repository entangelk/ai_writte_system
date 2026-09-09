# 2026-09-09 작업 로그

## 목표

- Slice 2 종결 독립 검증([`verifications/2026-09-09/slice2_withdrawal_grace_closure.md`](../../verifications/2026-09-09/slice2_withdrawal_grace_closure.md), 판정 **합격 · 차단 0**)이 남긴 **하드닝 2건**을 오너 지시로 닫는다("검증기록 확인해서 보강할 부분 보강해줘").

---

## 세션 47 — 검증 하드닝 2건: 낡은 주석 · 인덱스 단면 가드 (커밋 `0d0e8a7`)

### 1. 하드닝 ① — `SCENE_NOTE_MAX_CHARS` 주석이 오너 상한 변경을 못 따랐다

`core_sot/service.py` 주석이 *"원고 본문 상한(`DRAFT_RAW_TEXT_MAX_CHARS` = 4000)의 **3배**"* 라고 적혀 있었으나 오너의 6000자 변경(2026-09-08, `97bc149`) 이후 12000은 **2배**다. 값 자체는 오너 결정 그대로(검증 기록도 "값 무변"으로 확인) — **주석만 뒤처진 것**이고 `tests/test_scene_notes.py` 독스트링이 이미 올바른 서술(*"배수는 2가 됐다 · 근거는 물려받지 않았다"*)을 갖고 있었다. 주석을 그 서술에 맞추고 독스트링이 정본임을 pointer 로 박았다. **주석은 가드가 못 보는 면**이라는 것이 이 하드닝의 존재 이유 — 다음 사람이 `service.py` 주석만 읽고 근거를 잘못 인용할 여지를 닫는다.

### 2. 하드닝 ② — 검증 인덱스 단면 날짜 가드 (도달성 가드가 못 보던 축)

검증이 발견한 실결함: 09-08 기록 둘이 `### 2026-09-07` 단면 아래 끼어 있었다. 기존 가드(`test_every_verification_record_is_reachable_from_the_index`)는 **링크가 열리는지만** 보고 어느 단면 아래인지는 못 본다 — 날짜가 어긋나도 293건 전건 초록이었다.

**★ 첫 초안이 바로 오탐을 냈다 — over-strict 를 설계 단계에서 직접 겪었다.** 단면 안의 모든 dated 링크를 검사하는 버전을 먼저 썼더니 정상 문서에서 곧바로 2건이 물렸다: `2026-08-21/reranker_c1_h1_h2_closure.md` 이 08-20 단면의 행에서, `2026-08-10/accept_activity_cell_reinforcement.md` 이 08-09 단면의 행에서 — **잘못 끼워진 행이 아니라 설명 칸의 상호 참조**(후속 기록을 가리키는 정상 링크)였다. 단면 밖 본문에도 서술 링크 4건이 있다. 그래서 검사 대상을 **표 행의 첫 열(기록 열) 링크**로 좁혔다 — 실측으로 첫 열 링크 293개·유니크 293·디스크 293과 정확히 쌍대임을 확인하고, 쌍대 단정을 함께 넣어 "단면 밖으로 빠지거나 아예 못 들어간 행"도 같이 잡히게 했다.

### 변이 (커밋 `0d0e8a7` → 변이 → 원복 → clean 확인, 2회 전부)

| 변이 | diff | 재실패 |
|---|---|---|
| MU 라벨 지연 재도입 | `### 2026-09-08` → `### 2026-09-07`(실결함의 모양) | **1실패** — 그 단면 아래 전 행(기록 2건)이 물린다 |
| MO 과잉 — 전 행 검사 | `findall(cells[1])` → `findall(line)` | **1실패(정상 문서에서)** — 상호 참조 2건을 물어 정상 인덱스가 깨진다 |

### Verification (세션 47)

- `test_docs_indexes.py` **16 passed / 303 subtests** · `test_scene_notes.py` 포함 초점 **41 passed / 306 subtests**.
- 변이 MU·MO 각 1실패 확인 후 원복, 매번 `git status --short` 대상 경로 무출력 확인.
- **백엔드 전수 `2964 passed / 1 skipped / 4089 subtests · EXIT=0`**(호스트, 커밋 `422e79c`, 2268초, test-mongo ON). skip 1 = live Chroma. **증분 전건 귀속**: 셀 **+1**(새 가드) · subtest **+3** = 검증 기록 파일(위생 파일 subtest +1 · 판정행 subTest +1) + 이 작업 로그 파일(위생 +1) — 새 가드 셀 자체는 subtest 를 내지 않는다. 최종 커밋은 기존 파일 내용 수정만 남으므로 이 수치는 그대로 유효하다.


---

## 세션 48 — RAG 확장성 분석 → 무순위 절단 신호 · ⓒ 배선 · 브리프 2건 (커밋 `e82c9ed`·`7a34e21`·`2d97fe4`·`0aa9966`·`69aed20`)

### 목표

오너 질문: *"인물에 대한 사건·설명이 많아지면 판단하는 AI의 컨텍스트가 커져 에러가 나지 않을까?"* — 잠재 위험 분석. 분석 결과에서 나온 것을 오너 결정에 따라 구현까지.

### 1. 분석 — 걱정한 경로는 안전하고, 다른 셋이 위험하다

**질문한 그 경로(정본이 쌓여 판정 프롬프트가 커진다)는 구조적으로 막혀 있다.** 세 겹이다: ① 판정은 후보 1 + 정본 1 쌍이라 인물의 사실 전부가 한 프롬프트에 실리는 지점이 없다(`compare_judge.py:139-152`) ② 정본 payload가 누적되지 않는다 — `update` 는 교체, `add_evidence` 는 이전 payload 보존이고 커지는 `source_ref_ids` 는 프롬프트에 안 실린다(`memory/service.py:363-372`) ③ 컨텍스트 예산이 그리디 하드 캡이다(`service.py:1167-1188`, 상한 8).

실제 위험 셋:

- **축 B — 검색 품질이 조용히 무너진다(가장 크리티컬, 오너 동의).** event/open_question은 결정적 scope key가 없고 semantic matcher가 기본 off라 **항상 `create`**. 재분석마다 같은 사건이 새 정본이 된다. 그 위에서 `MongoDirectCanonicalMemoryRetriever` 가 `query` 를 무시하고 저장 순서 앞 8개를 자르므로(폴백 구성일 때) **오래된 것만 영원히 실린다.** 예외도 로그도 없다.
- **축 C — 팬아웃.** 후보↔후보 판정은 O(n²)이고 실제로 run 1회 수백 쌍이 관측돼 2026-09-05에 20/run 상한이 들어갔다. 상한은 이월이라 풀이 더 빨리 자라면 못 따라잡는다.
- **축 D — 창 가드가 배포 구성에서 안 돈다.** 이미 **2026-09-08에 오너가 ⓐ로 확정한 사안**이었다(`k3-context-window-guard-decisions.md`). 그래서 **브리프를 쓰지 않았다** — 하루 전 결정을 다시 브리프로 만드는 것은 CLAUDE.md가 금지하는 "만들어낸 브리프"다. 분석이 축 D에서 새로 더한 것은 없다.

### 2. 구현 — 무순위 절단을 경고로 드러낸다 (커밋 `e82c9ed`)

`degraded` 는 쓰지 않았다. **이 파일에서 `degraded` 는 step 실패를 뜻하고 미배선 능력은 실패가 아니다** — `_run_canonical_memory_step` 의 미배선 분기가 `failure=None` 으로 그 구분을 이미 새겨 뒀다. 거기에 다른 뜻을 얹으면 HTTP 계약 의미가 바뀐다. 대신 `rerank.py:146-149` 폴백 경고와 같은 형태(*"조용히 삼키지 않는다"*)의 로그로 남겼다.

**패턴 sweep에서 하나 더 나왔다** — 같은 무순위 절단이 `MongoDirectCandidateMemoryRetriever` 에도 나란히 있어 함께 고쳤다. 한쪽만 고치면 후보 경로는 여전히 말없이 최근 후보를 버린다.

### 3. 구현 — event/open_question shortlist 배선 (커밋 `7a34e21`)

**Slice 1이 열어 둔 seam을 조립부가 채운 적이 없어 event/open_question은 한 번도 그룹으로 묶인 적이 없었다.** character만 정규화 이름으로 살아 있었다. `candidate_vectors` 를 재사용하는 어댑터(`analysis/candidate_shortlist.py`)를 만들고 `main.py` 조립부에 주입했다.

**유사도 임계값을 만들지 않았다.** 이웃 상위 K만 뽑고 `same|different|uncertain` 은 identity judge(LLM)가 판정한다. 2B.6 D4=A가 거부한 것은 *"추측 threshold로 canon을 병합하는 것"* 인데, 여기서 틀린 선택의 대가는 정본 오염이 아니라 **리뷰 노이즈**이고 의미 판정자는 이미 judge다. K는 의미적 컷오프가 아니라 **팬아웃 예산**이고 비용은 run당 20쌍 상한이 이미 묶는다. 임계값을 새로 만들면 그 값이 무엇을 뜻하는지 아무도 못 말하는 상수가 하나 는다.

import 방향 확인: `analysis.candidate_shortlist → indexing.memory_index → analysis.models` 로 역방향이 없다. `indexing.candidate_index` 는 `analysis.service` 를 import하므로 그 모듈 대신 **쓰는 한 메서드만** 구조적 Protocol로 받았다.

벡터 다리가 없는 배포는 builder가 `None` 이라 종전 no-op 그대로 — 회귀 없음.

### 변이 (커밋 → 변이 → 원복 → clean 확인, 5회 전부)

| 변이 | diff | 재실패 |
|---|---|---|
| MU 절단 경고 제거 | `service.py` canonical 분기의 `_warn_unranked_truncation` 호출 삭제 | **1실패** — `test_warns_when_the_unranked_backend_drops_entries` |
| MO 과잉 경고 | `if len(canonical) > limit:` → `>= limit:` | **1실패** — `test_does_not_warn_when_everything_fits`(전부 실리는 호출까지 경고) |
| MU focal 미제외 | `candidate_shortlist.py` 의 `if hit.candidate_id == candidate.id: continue` 삭제 | **1실패** — `test_focal_itself_is_never_shortlisted` |
| MU pool 필터 무력화 | `by_id.get(...)` → 없으면 즉석 후보 생성 | **1실패** — `test_hits_outside_the_pool_are_dropped` |
| MO 빈 pool 과잉 호출 | `if not pool: return ()` 조기 반환 삭제 | **1실패** — `test_empty_pool_buys_no_embedding_and_no_query` |

### 4. 브리프 2건

- `event-open-question-canonical-dedup-decisions.md`(`2d97fe4`) — 선택지 5개. **막을 수 있는 축이 둘인데 둘 다 꺼져 있다**는 것이 조사에서 처음 드러난 사실이다. 오너 **ⓒ**(candidate 축 배선) 채택 → 위 3번으로 구현.
- `context-compaction-layer-decisions.md`(`0aa9966`→`69aed20`) — 압축 층. **원설계에 `ContextCompressor` 가 있었고 구현에서 빠졌다**(`agentic_search_flow.md:315`). Macro/Micro 층도 이름만 남아 macro가 요약이 아니라 위치가 됐다. 오너 확정 D1=파생+트리거 · D2=챕터 기준 드릴다운 · D3=B(**시점 정정 확정**) · D4=A · D5=A선·B후속 · D6=정본 총계 16건.

### 사용자 결정과 근거 (세션 48)

- **축 B가 가장 크리티컬** — 오너 판단. 배선(ⓒ)을 먼저 하고 압축은 별도로 논의.
- **압축본은 파생 + 트리거**(D1). 근거: 요약은 LLM 산출이라 틀릴 수 있는데 파생이면 재생성으로 고쳐지고 정본이면 오염이 영구화된다. 실측 정본 0건이라 품질 상수를 정직하게 못 고른다.
- **압축 단위는 챕터**(D2). 오너 근거: *"장이 닫혔다"* 를 시스템이 알게 하려면 장 개수를 미리 지정하고 재분석 버튼까지 열어야 한다. 구현자 보강 근거: D1이 파생인 이상 **재생성 빈도가 곧 비용**이고, 장은 닫히면 안 바뀌지만 엔티티 프로필은 매 장면마다 낡는다. **원설계는 엔티티별이고 챕터는 유효시점 필터였다** — 갈라지는 지점이라 브리프 경계 5에 사유와 함께 명시했다.
- **D3 시점 정정 수용** — 분석 완료는 `needs_review` 후보만 만들고 정본은 승인에서 생긴다(auto-promotion 기본 off·이 머신 미설정, 실측). 트리거를 *정본이 바뀔 때* 로 옮기니 **D4의 stale 판정이 곧 D3** 가 되어 결정 하나가 줄었다.
- **D6 = 정본 총계 16건**. 오너 근거: *"랭킹에 표시되더라도 드릴해서 들어가야 하니까"* — 검색 상한 8을 넘기 시작하면 압축 층이 할 일이 있고 16은 그 2배. 단위(프로젝트 총계)는 세 해석이 크게 달라 브리프에 못박았다.

### Issues found — 전수 중 문서 수정으로 5실패 (내 실수)

- **문제**: 첫 전수가 5실패로 끝났다 — 전부 `test_docs_indexes.py` 의 카운트 주장·도달성이고 코드 실패는 0이었다.
- **원인**: 전수가 도는 중에 브리프 2건을 디스크에 썼다. **이것은 이미 알려진 함정**(*"기록을 인덱스 등재 전 디스크에 쓴 채 전수를 돌리면 문서 가드가 실패한다"*)인데, *"문서 가드는 파일명 알파벳 순으로 일찍 돌 것"* 이라는 **검증하지 않은 추론**으로 그 함정을 덮었다. 실제로는 늦게 돌았다.
- **해결**: 배선까지 마친 뒤 디스크를 건드리지 않고 재전수. 두 번째 실행은 무실패.
- **교훈**: 실행 순서를 추론으로 단정하지 않는다. 알려진 함정을 우회하려면 **재는 것**이지 추론하는 것이 아니다. 전수 창과 기록 쓰기는 분리한다 — 예외 없이.

### Verification (세션 48)

- 초점: `test_candidate_shortlist.py` **7 passed** · 인접 스위트(identity judging·wiring·context search 양쪽·typecheck) **87 passed / 3 subtests**.
- 변이 5종 각 1실패 확인 후 원복, 매번 `git status --short` 무출력 + `git diff HEAD` 무출력 확인.
- **백엔드 전수 `2975 passed / 1 skipped / 4091 subtests · EXIT=0`**(호스트, 커밋 `7a34e21`, 1760초, test-mongo ON). skip 1 = live Chroma.
- **증분 전건 귀속**: 기준선 2964/4089 대비 **셀 +11**(무순위 경고 4 = canonical 2 + candidate 2 · shortlist 어댑터 6 · 배선 1) · **subtest +2**(새 plans 문서 2건 × `test_repo_hygiene.py:236` 파일별 위생 subtest). 문서 수정은 전수 뒤에 했으므로 `test_docs_indexes.py` 는 별도로 재실행해 확인했다(**16 passed / 303 subtests**).

### Next steps

- 압축 층은 **D6 트리거(프로젝트 canonical 총계 16건) 대기**. 열 때 먼저 풀 것: 정본의 장 귀속 규칙(브리프 후속 고려 — `MemoryEntry` 에 chapter 축이 없고 `add_evidence` union 이 장 경계를 흐린다).
- 배선된 shortlist는 **실데이터에서 아직 한 번도 안 돌았다**(정본·후보 0건). 첫 도그푸드에서 K=5와 run당 20쌍 상한의 배분이 실제로 맞는지 관측 대상.
