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

**질문한 그 경로(정본이 쌓여 판정 프롬프트가 커진다)는 구조적으로 막혀 있다.** 세 겹이다: ① 판정은 후보 1 + 정본 1 쌍이라 인물의 사실 전부가 한 프롬프트에 실리는 지점이 없다(`compare_judge.py:139-152`) ② 정본 payload가 누적되지 않는다 — `update` 는 교체, `add_evidence` 는 이전 payload 보존이고 커지는 `source_ref_ids` 는 프롬프트에 안 실린다(`memory/service.py:363-372`) ③ 컨텍스트 예산이 그리디 하드 캡이다(`context_search/service.py:1213-1234`(`_apply_budget`), 상한 8).

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

---

## 세션 48 후속 — 독립 검증 조건 폐쇄 (검증 `6d1e151`)

독립 검증 판정 **조건부 합격 · 차단 2건**([`session48_unranked_warning_and_shortlist_wiring.md`](../../verifications/2026-09-09/session48_unranked_warning_and_shortlist_wiring.md)). 전수 수치(2975/4091)·변이 5종·실측 0건이 전부 재현됐고 **차단 둘 다 코드 결함이 아니라 기록 갱신 누락**이었다. 검증자가 제6변이(상한 `break` 삭제)를 추가로 유도해 그것도 기명 셀이 잡았다.

### 차단 1 — dedup 브리프 상태가 낡았다

`event-open-question-canonical-dedup-decisions.md` 와 인덱스 행이 **`Proposed — 오너 결정 대기`** 로 남아 있었다. 오너는 ⓒ를 채택했고 구현(`7a34e21`)까지 끝난 뒤였다. **같은 세션의 압축 층 브리프는 갱신하면서 이것만 빠뜨렸다** — 결정이 브리프에 도착한 시점(대화)과 구현이 끝난 시점이 달라, 구현을 끝내고 브리프로 돌아가지 않았다.

**가드가 못 잡는 이유가 중요하다**: 문서↔인덱스 **일치**만 보므로 **둘 다 낡으면 초록**이다. 상태 정본이 둘인 구조(문서 머리 + 인덱스 열)의 알려진 한계이고, 셋째 축(구현 여부)은 기계가 모른다.

**폐쇄**: 브리프 상태를 `Resolved` 로 올리고, **브리프가 스스로 무엇이 됐는지 말하도록** `## ✅ 오너 결정` 절을 본문에 넣었다(구현 커밋·임계값을 안 만든 이유·미배선 시 no-op·실데이터 미실행). 후속 고려의 *"threshold 정본은 하나여야 한다"* 는 **임계값을 안 만드는 것으로 해소됐다**고 연결했다.

### 차단 2 — 루트 README 전수 기준선 미갱신

`README.md` 의 회귀 가드 행이 **2,964 / 4,089**(세션 47 기준선)에 멈춰 있었다. 슬라이스 종결마다 갱신되던 관례(2954→2963→2964)를 세션 48이 자기 종결 수치로 잇지 않았다. **가드 밖 숫자라 아무 셀도 안 문다.** → **2,975 / 4,091** 로 갱신.

**두 차단의 공통 뿌리**: 종결 시 *게시 상태*(브리프 상태·README 수치)가 실제를 못 따라간 것이 한 세션에서 두 번 났다. 둘 다 가드 사각이라 사람이 보기 전엔 안 드러난다.

### 비차단 하드닝

| 항목 | 처리 |
|---|---|
| `limit=0` 이 이웃 1개를 돌려준다 | **고쳤다.** 루프가 담고 나서 상한을 보므로 0 이 *"아무도 안 데려온다"* 가 아니었다(직접 재현 확인). `__init__` 에서 `limit < 1` 을 **거절**한다 — 조용히 1로 올리지 않는다(조립 설정이라 기동에서 알아야 하고, 판정 팬아웃으로 뒤늦게 드러나면 원인이 멀다). 양방향 셀 2개 추가(0·-1 거절 / `limit=1` 은 유효) |
| env K 파싱 | `int(os.environ.get(...))` → 집안 헬퍼 `_env_int` 로 통일 |
| work_log 줄좌표가 `e82c9ed` 이전 기준 | `service.py:1167-1188` → **`context_search/service.py:1213-1234`**(내 헬퍼 삽입으로 46줄 밀렸다). 나머지 둘(`compare_judge.py:139-152`·`memory/service.py:363-372`)은 재측정 결과 **여전히 정확**해 그대로 뒀다 |
| shortlist 실데이터 미실행 | **dev 스택 env 가 이미 조건을 충족한다**(`CHROMA_HOST`·`EMBEDDING_SERVICE_URL` 실측 존재) — 즉 **이미지 재빌드 시점에 즉시 활성화**된다. HANDOFF 함정 절에 그 사실을 붙였다. 첫 도그푸드에서 K=5 와 run당 20쌍 상한의 배분 관측이 필요하다 |

### 오너 결정 — D7 (2026-09-09)

압축 층 슬라이스에 **`constraints`/`do_not_use` 를 포함**한다. 근거: 층이 노리는 것이 *"길어져도 초반 규칙·지시사항을 끝까지 준수"* 인데 그 절반인 제약을 빼면 층을 만들고도 목적을 반만 이룬다. 오너가 이 방향을 *"독립된 작업 메모리를 상시 참조해 초반 규칙을 끝까지 지킨다"* 로 설명했고, 대조 결과 구조(별도 층·상시 참조·드릴다운·진행 상태=`open_question`)는 브리프와 일치했다. 갱신 경로만 다르다 — **모델이 노트에 직접 쓰는 것이 아니라 승인된 정본에서 파생·재생성**된다(D1 파생 결정의 귀결).

**착수 시 먼저 그을 경계**를 D7 말미에 남겼다: `do_not_use` 내용이 대부분 POV·시점에서 유도되는데 `timeline_constraints`·`pov_constraints` 는 범위 밖이라, (a) 압축본이 아는 범위 안에서만 · (b) 셋을 한 묶음 중 하나를 열 때 정한다.

### Verification (조건 폐쇄)

- 초점 `test_candidate_shortlist.py` **9 passed / 2 subtests**(7→9, 신규 2셀) · 조건 폐쇄 초점 묶음 **83 passed / 911 subtests**.
- 변이 양방향 2종: **MU-4** `if limit < 1:` → `if False:` (검증 무력화) → `test_a_limit_below_one_is_rejected_at_assembly` **2 SUBFAIL**(limit=0·-1) · **MO-4** `< 1` → `< 2`(경계 과잉 조임) → `test_a_limit_of_one_is_still_valid` **1실패**. 각각 원복 후 `git status --short`·`git diff HEAD` 무출력 확인.
- **백엔드 전수 `2977 passed / 1 skipped / 4095 subtests · EXIT=0`**(호스트, 커밋 `c08e1fc`, 1938초, test-mongo ON). skip 1 = live Chroma.
- **증분 전건 귀속**: 세션 48 종결 수치 2975/4091 대비 **셀 +2**(limit 거절·limit=1 유효) · **subtest +4** = 거절 셀의 `subTest` 2(limit 0·-1) + 검증자 기록 파일 1건(위생 +1 · 검증 인덱스 판정행 +1, 커밋 `6d1e151`).
- **루트 README 회귀 가드 행도 이 수치로 갱신했다**(2,975/4,091 → **2,977/4,095**) — 차단 2가 지적한 관례를 닫자마자 다시 낡히지 않기 위해서다.

## 오너 결정 — D7 경계 (2026-09-09, 세션 48 후속)

**(a) 아는 범위 안에서 · 세 축**으로 확정. 오너가 두 번에 걸쳐 좁혔고 **두 번 다 내 근거를 정정했다.**

1. *"아는 범위 안에서 하는 게 맞지 않나? 어차피 아는 범위라는 게 결국 최신일 테니"* → (a) 채택. **다만 "최신" 은 정확히 틀렸다** — `do_not_use` 에서 최신은 독이다(9장 지식이 5장으로 샌다). 올바른 문언은 **"현재 집필 위치까지"** 이고, **D2(챕터 단위)가 그것을 공짜로 준다**(챕터 경계가 곧 시점). D2 를 고를 때의 근거는 재생성 비용이었으므로 **이 배당은 그때 못 본 것**이다.
2. *"인물별 지식 축도 분석에서 검토를 거쳐 완성되는 거 아냐?"* → **내 유예 근거가 틀렸다.** 나는 *"챕터 순서로 유도 가능한가"* 를 물었는데(불가능이 맞다), 오너 말은 **유도하지 말고 추출하라**는 것이었다. `character_observation` payload 가 자유 서술이라 지금 스키마로도 표현되고, 추출→승인 경로가 이미 그 일을 한다.

**그 결과 원설계의 `pov_constraints`·`timeline_constraints` 를 별도 기계로 들여오지 않는다** — 정본에서 나오는 두 축이 됐고, 유예 목록에서 뺐다.

### 인물 지식 축에서 새로 드러난 저장 제약

- 인물 scope key 가 정규화 이름이라 **인물 하나 = 정본 하나**이고 모든 관찰이 한 엔트리로 모여 덮인다 → *"5장의 아린"* 과 *"9장의 아린"* 이 정본에 공존 못 한다.
- `_versioned_upsert` 가 새 버전에 `analysis_job_id = candidate.job_id` 를 박으므로 **인물 정본은 갱신마다 최신 장으로 이사한다** — 엔트리 단위 장 귀속이 불안정하다.
- **그러나 데이터는 이미 있다**: append-only 로 이전 버전이 `SUPERSEDED` 보존되고 각 버전이 자기 `analysis_job_id` 를 들고 있어 `job → snapshot_id → SourceSnapshot.draft_id → Draft.chapter_id` 로 장이 유도된다(**실측 확인** — `SourceSnapshot.draft_id` 존재, `derive_scope` 인물=정규화 이름). **버전 체인이 곧 장별 인물 상태 이력**이다.
- 필요한 것은 **압축 층이 버전 체인을 걷는 읽기 경로** 하나뿐이고, 그것은 압축 층만 쓰므로 **canonical-only 계약을 안 건드린다**.
- **비용**: 앞의 두 축은 장 귀속만 풀면 끝인데 이 축은 읽기 경로가 추가다 — 슬라이스가 커진다. 브리프에 그대로 적었다.
- **부수 소득**: 장 귀속 숙제의 답이 반쯤 나왔다 — 인물 메모리는 **엔트리가 아니라 버전 단위**로 장에 귀속시킨다(새 필드 없이 기존 이력으로 성립).

---

## 세션 49 — 계정 탈퇴 Slice 3 착수 실측 → 결정 브리프 (구현 없음)

핸드오프 Next Tasks 1번(계정 탈퇴 Slice 3~5)을 착수하려 실측부터 했고, **계획서와 코드가 어긋나는 지점 하나**와 **선례를 그대로 따르면 자기 발을 무는 지점 하나**가 나와 구현 전에 멈추고 브리프를 썼다.

### 1. 실측 — 계정 축 컬렉션 전수 (`db_name` 인덱싱 + 필드 이름)

| 컬렉션 | 사용자 축 키 | `user_id` 필드 스윕이 보는가 | 파기 대상 |
|---|---|---|---|
| `users` | `_id` | ✗ | 계정 행(마지막) |
| `sessions` | `user_id` 필드 | ✓ | ✓ |
| `writing_generation_jobs` | `user_id` 필드 (+`project_id`) | ✓ | ✓(프로젝트 파기가 이미) |
| `index_sync_outbox`·`index_sync_logs` | `user_id` 필드지만 **값이 항상 `None`**(`indexing/service.py:439`) | 컬렉션은 발견되나 일치 0건 | ✗ |
| **`request_quota_policies`** | **`_id` = user_id**(`quota/policy_mongo.py:46`) | **✗** | ✓ |
| `request_usage_ledger` | `target_user_id` | ✗ | 남긴다(D4) |
| `admin_audit_events` | `admin_user_id`/`target_user_id` | ✗ | 남긴다 |
| `login_failures` | **`_id` = username**(`auth/login_guard_mongo.py:39`) | ✗ | 제3의 축 |
| `access_grants(_uses)`·`activity_events` | 행위자 + `project_id` | ✗ | 프로젝트 파기가 |

### 2. 발견 ① — 계획서 D4 절이 회원 한도 정책에 대해 틀렸다

계획서는 *"세션·색인·생성 job·**회원 한도 정책**도 `user_id` 를 쓰지만 … 쓸이 대상인 것이 맞다"* 라고 적었는데, `request_quota_policies` 는 **`user_id` 필드를 쓰지 않는다** — `_id` 가 곧 user_id 다(회원당 한 행이라는 P1 계약을 DB 가 강제하게 한 의도적 설계라 그 자체는 옳다). 즉 *"필드 이름이 파기의 opt-in/opt-out 스위치"* 라는 계약이 **사용자 축에서는 컬렉션 하나를 조용히 빠뜨린다.** 계획서에 정정 표시를 달되 **무엇으로 정정할지는 고르지 않고** 브리프로 보냈다(CLAUDE.md §1 — 스펙 모순은 어느 쪽이 정본인지 오너에게 묻는다).

### 3. 발견 ② — 규칙을 `_id` 로 넓히면 사용자명 묘비를 스스로 지운다

계획서 Slice 3 의 3번이 *"사용자명 한 값 보존(`project_name_history` 와 같은 모양)"* 인데, 그 선례의 `_id` 키잉은 **우연이 아니라 명시된 설계**다 — `deletion/project_name_history_mongo.py` 머리말이 *"`_id` is the project id **on purpose**: … `purge_reconciler.py` … cannot mistake this collection for orphaned project data"* 라고 적었다. **이 저장소에서 "파기를 살아남는다"의 기존 표식이 곧 `_id` 키잉**이므로, 사용자 축 스윕에 `_id` 규칙을 더하면 데몬이 방금 자기가 쓴 묘비를 지운다. 두 실측이 **한 갈림길의 양쪽**이라 따로 물을 수 없어 한 브리프에 묶었다.

### 4. 브리프 — [`slice3-withdrawal-purge-daemon-decisions.md`](../../plans/slice3-withdrawal-purge-daemon-decisions.md)

- 발견 규칙 4안(ⓐ 필드 스윕+손목록 · **ⓑ 두 규칙 스윕 + 보존 표식을 `target_user_id` 로 통일(추천)** · ⓒ 서비스마다 `purge_user()` · ⓓ 데몬은 프로젝트만, 잔류는 reconciler).
- 범위 2안(**ⓔ Slice 3 = 데몬 + reconciler 스크립트, 관리자 화면은 Slice 4(추천)** · ⓕ 화면까지 한 슬라이스). D3 의 *"관리자 화면에 잔여 정리"* 와 Slice 4 의 *"화면"* 이 한 편집을 서로 자기 것이라 말하던 것을 드러냈다(Slice 0·5 의 §6 승격 중복과 같은 모양).
- 후속 고려에 `login_failures`(`_id` = username) 제3의 축, 파기 본체 `HTTPException` 경계, 부분 파기 표시 자리, `deletion/` 패키지, archive→purge 강제 순서를 남겼다.

### 5. 아직 하지 않은 것

**코드 한 줄도 안 건드렸다.** 데몬·묘비·부분 파기 표시가 전부 위 결정에 매달려 있어, 먼저 지으면 답에 따라 버리게 된다. Slice 3 이 막히면 **Next Tasks 2번(랜딩 + 동의 게이트)** 이 다음 자리다.

### Verification (세션 49)

- 문서 전용 변경. `tests/test_docs_indexes.py` + `tests/test_repo_hygiene.py` **25 passed / 907 subtests · EXIT=0**.
- 등재 가드가 **실제로 물었다**: 브리프 파일을 더하고 인덱스 행만 넣었더니 개수 주장 4건(`docs/plans/README.md` 전체·브리프 · 루트 `README.md` 전체·브리프)이 SUBFAIL — 135→136 · 114→115 로 갱신해 초록. 가드가 없었으면 두 README 가 조용히 낡았다.
- 새 회귀 셀 없음(행위 변경 없음).

---

## 세션 49 이어서 — 랜딩 축 ① 약관 값 조달 반영 (커밋 `b6c5aa5`·`c8f106e`)

Slice 3 이 오너 대기가 되어, HANDOFF Next Tasks 2번(랜딩 + 동의 게이트)의 첫 단계인 **약관 대괄호 넷 치환**으로 옮겼다. **셋만 채웠고 그것이 옳다.**

### 1. 발견 — 시행일을 채우면 문서가 없는 기능을 시행 중이라고 말한다

브리프 착수 순서는 *"① 대괄호 넷 치환 + 버전 `draft-0` → 시행 버전 문자열 + 미시행 표식 제거"* 였다. 그런데 [`docs/legal/README.md`](../../legal/README.md) 의 §8 표가 **`시행 전제` 열**을 갖고 있고 두 줄이 아직 안 끝났다:

| 축 | 시행 전제 | 지금 |
|---|---|---|
| 계정 탈퇴(약관 제8조 3·4항 · 방침 제5조 3항) | 셀프 탈퇴 + 30일 유예 **파기** 구현 | Slice 0~2 만 닫혔다. **파기 데몬이 없어 "30일이 지나면 파기됩니다" 가 일어나지 않는다** |
| 추론 경계 밖 전송 고지(방침 제4조 · 제3조 안내 상자) | 가입 동의 게이트 구현 | 미착수 — **"시행일 이후 가입자에 한합니다" 가 성립 안 한다** |

게다가 오너가 정한 **시행일 2026-09-08 은 이미 지났다**(오늘 09-09). 그 표 자신이 *"시행일 전에 구현이 끝나야 약관이 참이 된다"* 고 적어 두었으므로, 지금 채우면 그 문장을 스스로 어긴다. → **값 셋만 반영하고 시행일·버전·미시행 표식은 건드리지 않았다.** 시행일 재확정을 HANDOFF 오너 결정 대기 표에 올렸다(2건째).

### 2. 반영한 값 셋 (본문 5곳)

| 자리 | 값 | 본문 |
|---|---|---|
| `[운영자]` | entangelk | 약관 제1조 |
| `[문의 연락처]` | kdtyohan@gmail.com | 약관 제11조 · 방침 제8조 5항 · 방침 말미 |
| `[추론 서비스 사업자]` | Google (Gemini API) | 방침 제4조 3항 |

방침 제4조 3항의 꼬리 문장(*"시행 시 이 항목에 구체적으로 밝힙니다"*)은 채워진 뒤 낡으므로 **"배포 구성이 바뀌면 이 항목도 함께 고칩니다"** 로 바꿨다 — 브리프가 경고한 연결(벤더 변경 ↔ 방침)을 문서 자신에 심었다.

### 3. 가드 둘 (`tests/test_service_policy_contract.py`)

- **핀 셀** `test_the_three_procured_values_are_filled_in_both_drafts` — 값이 들어갔고 그 대괄호가 안 남았다. 정본이 문서뿐이라 상징 참조로는 못 잠근다(`MIN_PASSWORD_LENGTH` 선례).
- **결합 가드** `test_the_effective_date_and_the_unenforced_marker_move_together` — *시행일 대괄호가 있다 ⟺ 미시행 표식이 있다*. 갈라지면 문서가 자기 지위를 두 가지로 말한다.

### 4. ★ 변이가 가드의 사각을 드러냈다 — 한 번 실패하고 고쳤다

**MU-1(시행일만 채우고 표식 유지)이 처음에 통과했다.** 가드가 재는 것은 대괄호 *문자열의 존재*인데, 내가 쓴 머리말이 설명하려고 같은 표기를 **언급**해서 본문을 다 채워도 초록이었다. 머리말을 *"시행일 자리"* 로 고치고 **그 규칙이 곧 가드의 전제**임을 docstring 에 적었다(`c8f106e`). 같은 계열을 값 가드에서도 한 번 겪었다 — 처음 쓴 머리말이 대괄호 셋을 나열해 **3 SUBFAIL** 로 잡혔고, 그때는 가드가 옳고 문서가 틀렸다.

### 변이 (커밋 `c8f106e` → 변이 → 원복 → clean 확인, 3회 전부)

| # | 방향 | 변이 | 결과 |
|---|---|---|---|
| **MU-1** | under | 시행일 자리 셋을 2026-09-08 로 채우고 `미시행` 표식 유지 | 결합 가드 **2 SUBFAIL**(약관·방침) |
| **MO-1** | over | 표식만 `시행 중` 으로 걷고 시행일 대괄호 유지 | **4 SUBFAIL** — 기존 미시행 셀 2 + 결합 가드 2 |
| **MU-2** | under | 약관 제11조의 연락처를 대괄호로 되돌림 | 핀 셀 **1 SUBFAIL**(placeholder=`[문의 연락처]`) |

3회 모두 `git checkout -- docs/legal/` 뒤 `git status --short`·`git diff HEAD --stat` 무출력 확인. **변이 전에 커밋이 먼저였다**(§6 프리플라이트: `b6c5aa5` → MU-1 → `c8f106e` → MU-1·MO-1·MU-2).

### Verification (세션 49 이어서)

- 초점 `tests/test_service_policy_contract.py` **7 passed / 41 subtests · EXIT=0**(5→7 셀, 신규 2).
- `tests/test_docs_indexes.py` 동반 **초록**(23 passed / 345 subtests, 두 파일 합산).
- 백엔드 전수는 이 슬라이스 종결 시점에 돌린다 — 지금은 문서 + 문서 가드 변경이다.

### Next steps

- **시행일 재확정이 오너 대기**다. 그것과 무관하게 ②(프런트 `/terms`·`/privacy` + 푸터)·③(랜딩 본문)은 **본문이 이미 확정된 값을 담고 있어** 착수 가능하다 — D2=ⓐ 가 요구하는 **본문 대조 가드**를 함께 둔다.
- ④ 동의 게이트는 **시행 버전 문자열이 입력**이라 시행일 결정 뒤다.
