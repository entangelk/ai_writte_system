# 제품명 스윕(`29299e5`) + 비차단 3건 보강(`cfcb182`) 독립 검증

## Subject metadata

- **날짜**: 2026-08-21
- **요청자**: 오너 — *"29299e5도 독립 검증해 주고 작은거니까 이어서, 보강작업 한 cfcb182 것도 독립검증 합쳐서 해줘."*
- **검증자**: 이 세션 — 두 커밋 모두 이 세션의 작업이 아니다. `cfcb182` 는 이 검증자의 재검 기록([`reranker_c1_h1_h2_closure.md`](reranker_c1_h1_h2_closure.md))이 남긴 Hardening 을 닫은 커밋이고, **그 세션이 재검 기록에 단 폐쇄 주석도 검증 대상**으로 삼았다(구현 세션이 검증 기록에 쓴 것은 그대로 믿지 않는다 — 92b9b24 때와 같은 형태).
- **대상 커밋**: `29299e5`(제품명 세 자리 + 백엔드 스윕 가드) · 기록 `1f9df97` · `cfcb182`(H2-a·H2-b·비순열 로그 보강) · 기록 `919c9dd`
- **정본 참조**: [`HANDOFF.md`](../../../HANDOFF.md) §Active Decisions 제품명(D5 — "화면만이 아니다") · [`docs/daily_logs/2026-08-21/work_log.md`](../../daily_logs/2026-08-21/work_log.md) D-2026-08-21-a(세 title 의 정확 글자)·§Verification 표(M1~M5·N1~N4) · 인계 "볼 만한 축"(29299e5 두 항)
- **작업 트리 상태**: 검증 시작 HEAD `919c9dd`, clean. **대상 파일은 각 커밋 이후 무변** — 서비스 main 네 파일+`test_product_name.py` 는 `29299e5` 이후, `test_rerank.py` 는 `cfcb182` 이후 `git log` 로 확인. 체크포인트 1건: 재현 스크립트 `90b89c2`.

## Scope

1. **29299e5** — 세 `title=` 변경·스윕 가드 3셀 감사·OpenAPI 실측·`schema.d.ts` 무영향 주장.
2. 구현자 뮤테이션 **M1~M5** 같은 diff 재유도(같은 파일·같은 줄).
3. 검증자 자체 축 — compose 스캔 여부(M6)·변형 표기 맹점(M7)·서비스 구분자 잠금(M8)·**★ 은퇴명 잔존 저장소 전수 조사**(README·LICENSE).
4. **cfcb182** — "프로덕션 0줄" 확인·셀 개명/갈리는 입력/비순열 로그 셀 감사.
5. 보강 세션 뮤테이션 **N1~N4·R6b(페어링 1→2)** 같은 diff 재유도 + 재검 기록 폐쇄 주석 정합성.
6. 인계 **볼 축 넷** 판정(29299e5 둘 · cfcb182 둘) + 포커스·전수.

## Methodology

- 포커스: `tests/test_product_name.py` → **3 passed / 3 subtests** · `tests/test_rerank.py` → **23 passed / 26 subtests**(22+1셀·24+2서브테스트).
- 실측: `python3 scripts/dump_openapi.py` 의 `info.title` · `schema.d.ts` grep · 잔존 조사 `grep -rl[n] "AI Writing System"`(대소문자 구분/무시 두 번).
- 뮤테이션: [`repro_product_name_and_hardening.sh`](repro_product_name_and_hardening.sh)(**신규 작성·커밋**) — clean-tree 분기, 리터럴 `count==1` 단정, 복원 `git checkout --` + status 공백, 요약 줄+`FAILED|SUBFAILED` 함께 판독.
- 전수: `python3 -m pytest -q` — test-mongo 27020 healthy(`docker ps` 확인).

## Findings

### 1. 29299e5 — 세 자리·셀·실측, 전부 주장과 일치

- **diff**: 세 서비스의 `FastAPI(title=…)` 한 줄씩 — `에-라잇 Application`·`에-라잇 Embedding Service`·`에-라잇 LLM Gateway`(D-2026-08-21-a 의 글자 그대로).
- **실측**: `dump_openapi.py` → `{'title': '에-라잇 Application', 'version': '0.1.0'}` ✓. `frontend/src/api/schema.d.ts` 에 제품명·은퇴명 **모두 0건** — "재생성해도 diff 0" 주장과 정합(title 을 타입으로 옮기지 않는다) ✓.
- **셀 감사**([`tests/test_product_name.py`](../../../tests/test_product_name.py)): ① 행위 셀 — 앱을 실제로 조립해 `app.title` 을 본다(소스 grep 이 아님) ② 완전성 셀 — 저장소 전체 `.py`+`docker-compose*` − {`.git`,`__pycache__`,`node_modules`,`tests`,`docs`,`frontend`} ③ over-strict 셀 — `DEFAULT_DB_NAME == "ai_writing_system"`(식별자 방어). **셀 이름이 스코프를 정확히 말한다**(`no_backend_source`) — 문언이 잠금보다 넓지 않다.
- 하드코딩 회피 주장(네 번째 최상위 패키지 계열)도 코드에서 확인 — 스캔이 디렉터리 목록이 아니라 전체 순회+제외 집합이다.

### 2. M1~M5 같은 diff 재유도 — 전부 일치

| 뮤테이션 | 재유도 결과(이 세션) | 구현자 표 |
|---|---|---|
| M1 application title → 옛 이름 | **2 failed** — 행위 셀 SUBFAILED(application) + 완전성 셀 | 2 ✓ |
| M2 embedding | 같은 두 셀(SUBFAILED embedding) | 2 ✓ |
| M3 gateway | 같은 두 셀(SUBFAILED llm_gateway) | 2 ✓ |
| M4 무관한 .py 주입(`scripts/index_sync_worker.py:1`) | 완전성 셀 **단독** | 1 ✓ |
| M5 (over-strict) 식별자 개명 | 식별자 셀 **단독** | 1 ✓ |

### 3. 자체 축 M6~M8 — compose 는 잡고, 변형 표기·구분자는 침묵

- **M6**(compose 에 은퇴명 주입): 완전성 셀 발화 ✓ — `docker-compose*` 가 스캔 대상임을 실행으로 확인(계약 문언과 정합).
- **M7**(변형 표기 `"AI writing System"` 주입): **침묵**(3 passed). 정확 일치가 식별자 오탐 회피를 위해 문언화된 의도다. **저장소 전체에서 변형 표기 잔존은 실측 0건**(대소문자 무시 grep) — 오늘은 이론적 맹점이고, 측정 기록으로만 남긴다.
- **M8**(`title="에-라잇 App"`): **침묵**(3 passed). 셀은 `startswith(제품명)` + `NotIn(은퇴명)` 만 잠그고 **D-2026-08-21-a 가 명시한 정확 글자 셋을 단정하지 않는다** — 서비스 구분자(Application→App 등) 드리프트는 아무 셀도 못 본다. 아래 H-P2.

### 4. ★ 은퇴명 잔존 전수 조사 — README H1·LICENSE 가 모든 스윕 밖에 있다

- 정확 일치 `"AI Writing System"` 의 잔존(의도적 제외 셋[docs 이력·frontend 자기 스윕·백엔드 테스트 자기 스윕] 바깥): **[`README.md:1`](../../../README.md) 의 H1 `# AI Writing System`** · **[`LICENSE:1`](../../../LICENSE) 제목줄** · `HANDOFF.md:164`(가드가 무엇을 금지하는지 적는 서술 — 테스트가 금지 문자열을 적어야 하는 것과 같은 부류, 무해).
- 백엔드 스윕은 `.py`+`docker-compose*` 만, 프론트 스윕은 `frontend/` 만 본다 — **README H1 은 어느 쪽 사정거리에도 없다.** 두 스윕의 docstring 이 원칙으로 적는 *"노출되는 모든 자리에서 하나"* ·HANDOFF D5 *"화면만이 아니다"* 와 어긋나는 **살아있는 잔존**이며, 이 슬라이스가 치유하려던 병("가드의 사정거리 밖에서 열 달 green")의 정확히 같은 모양이다.
- **조건이 아닌 이유**: 이 커밋의 계약(HANDOFF H2 = *API 문서의* 제품명) 범위 밖이고, 셀 문언은 스코프를 과대 서술하지 않으며, README 는 어느 결정문에도 열린 적 없는 미결 표면이다(2026-08-11 프론트 스윕 검증 기록에도 없음 — 확인). **오너 결정 요청(H-P1)**: README H1(및 LICENSE 제목줄)을 제품명으로 바꾸거나 "저장소 메타데이터"로 남긴다는 문언을 남긴다.
- 인계 볼 축 판정: ① 제외 목록 누락 — **실재했다(위)**. ② 변형 표기 의도 — 측정됨(잔존 0, 문언화된 의도와 정합).

### 5. cfcb182 — 프로덕션 0줄·셀 감사 일치

- **diff**: `tests/test_rerank.py` 하나(48+/11−) — **"프로덕션 코드 0줄" 주장 ✓**(stat 으로 확인).
- **개명 셀** `test_ties_keep_the_response_order`: 이름이 성질("같은 응답이 언제나 같은 순서")에 맞고, docstring 이 전제("정합 서버가 동률을 요청 순서로 보내 줄 때만 둘이 겹친다")를 명시, **두 서브테스트** — 겹치는 입력(회귀로 보존) + 갈리는 입력(응답 `[2,0,1]` 동점 → 기대 `(2,0,1)`).
- **로그 셀** `test_a_response_that_is_not_a_permutation_is_logged_too`: WARNING 발생 + **원인 `"not a permutation"` 잔존**까지 단정(프로바이더 장애와 구별).

### 6. N1~N4·R6b 같은 diff 재유도 — 전부 일치

| 뮤테이션 | 재유도 결과(이 세션) | 보강 세션 기록 |
|---|---|---|
| N1 동률 오름차순 인덱스 tie-break | **새 subtest 만** SUBFAILED(response='응답이 다른 순서로 왔다') — 나머지 green | ✓ |
| N2 내림차순 변형 | 같은 새 subtest 만 | ✓ |
| N3 순열 검사를 `return items` 로 | **새 로그 셀만 실패 — 기존 비순열 5 subtest 전부 green**(26 subtests passed) | ✓ |
| N4 `exc_info=False` | **2 failed** — 새 로그 셀 + 기존 `…logged_rather_than_swallowed`(오류 메시지 `'RuntimeError' not found in …` — 원인 소멸이 정확히 그 셀을 문다) | ✓ |
| R6b 원본 리터럴 | **2 SUBFAILED**(두 subtest 모두) — 요약 `2 failed, 23 passed, 24 subtests` | "페어링 1→2" ✓(재현 실측과 문장까지 동일) |

- **"종전 셀이 원리적으로 못 본다"(N1) 실증**: N1 배치에서 동률은 요청 순서와 같아지므로 종전 입력의 기대값이 그대로 나온다 — 보강 세션의 서술과 정확히 일치하는 관측이었다.
- **재검 기록 폐쇄 주석 정합성**(구현 세션이 [`reranker_c1_h1_h2_closure.md`](reranker_c1_h1_h2_closure.md)에 단 것): N1·N3·R6b 수치 전부 이번 재유도와 일치 · "종전 이름은 저장소 어디에서도 참조하지 않았다" — grep 결과 코드/테스트 참조 0, 역사 기록(워크로그·검증 기록)에만 존재 ✓ · **"미검증 커밋 0" 정정은 정확했다** — 그 시점(96294c8) 저장소 전체 미검증은 0이 아니었다(29299e5·1f9df97). 원 오류는 이 검증자의 기록이었고 정정이 맞다.
- **인계 볼 축 판정(cfcb182)**: ① *동률 셀의 "응답 순서 보존" 이 계약인가 안정 정렬의 우연인가* — **우연이 아니다.** Python 정렬 안정성은 언어 보증이고([`rerank.py:212-217`](../../../services/application/app/context_search/rerank.py) 주석이 그 선택을 문언으로 명시), 셀은 문언과 정확히 같은 것을 잠근다. 주석이 강조하는 부하 성질은 결정론("같은 응답이 언제나 같은 순서")이고 응답 순서 보존은 그보다 **강한 정책**이다 — 셀이 정책을 잠그는 것은 잠금=문언이므로 과대가 아니고, 정렬을 바꾸는 순간(N1·N2) 주석과 셀이 같이 요구되는 것이 **의식적 계약 개정을 강제하는 설계된 마찰**이다. ② *`not a permutation` 을 traceback(`exc_info`)에서 읽는 단정이 과대한가* — **아니다.** 메시지 본문("reranking failed; falling back to fusion order")에는 원인이 없으므로 exc_info 의존은 "원인이 남는다"와 "폴백이 로그된다"를 구별하는 셀의 목적 그 자체다(N4 가 그 결합을 증명). 예외 문구에 묶인 것은 진단 계약 — 부분 응답(`top_n`)을 장애와 오진하지 않게 하는 문구이므로, 문구를 바꾸면 셀이 물어야 한다.

### 7. 전수 회귀

- **`2358 passed · 1 skipped · 2592 subtests`**(1296초) — `919c9dd` 실측과 정확히 일치. 체인: 2357/2589(`1f9df97`) → 이 검증자 기록 등재 +1 subtest → `cfcb182` +1셀(로그)+2서브테스트(동률 0→2) → 2358/2592. skip 1 = live Chroma. 이 기록 등재 후 기대 subtest 2593(등재분 +1).

## Issues / Risks

### Blocking (조건)

- 없다.

### Hardening recommendations (비차단)

> **[전부 닫힘 2026-08-21 — H-P1 은 오너 결정(D-2026-08-21-d) `c1fed21` · H-P2·M7 은 `924b0ab`.]** 원문은 발행 시점 그대로 두고 각 항에 폐쇄 결과를 붙인다.

- **★ H-P1 — 오너 결정 요청: README H1·LICENSE 제목줄의 은퇴명 잔존.** 모든 스윕의 사정거리 밖에 있는 살아있는 잔존(Findings 4). 바꾸거나 의도 잔존으로 문언화한다. 결정이 나면 그 자리를 잡는 셀/스윕 확장 여부도 함께 정한다.
  - **[닫힘 `c1fed21`]** 오너가 **교체**를 택했다(D-2026-08-21-d) — `README.md:1` `# 에-라잇` · `LICENSE:1` `에-라잇 — License`. 저작권자(`entangelk`)는 무변이라 법적 의미는 바뀌지 않는다.
  - **자리를 고치는 것으로 끝내지 않았다** — 지적의 핵심이 *"이 슬라이스가 치유하려던 병과 같은 모양"* 이었으므로 **스윕을 그 자리까지 넓혔다**(`_FRONT_DOOR = ("README.md", "LICENSE")`). 확장자 규칙으로 열지 않은 이유: `HANDOFF.md`·`CHANGELOG.md` 가 함께 들어오는데 **그 둘은 이력이라 은퇴명이 남아 있는 것이 맞다**(이 기록이 `HANDOFF.md:164` 를 무해로 분류한 것과 같은 판단).
  - **이름 목록은 자기가 비는 것을 못 본다** → 존재 트립와이어 셀(`test_the_front_door_files_are_actually_there_to_be_swept`)을 함께 뒀다. 뮤테이션 **P7**(`LICENSE` 를 옮김) 실측: 트립와이어 subtest + 스윕 셀 **둘 다** 발화.
  - 뮤테이션 **P5**(README H1 되돌림) · **P6**(LICENSE 제목줄 되돌림) 각각 스윕 셀 1건 발화 — **종전에는 둘 다 침묵이었다.**
- **H-P2 — 서비스 구분자 미잠금(M8).** D-2026-08-21-a 의 정확 글자 셋을 equality 로 단정하면 구분자 드리프트(Application→App)까지 잠긴다. 현재 잠긴 것은 "제품명 시작+은퇴명 부재"뿐이다.
  - **[닫힘 `924b0ab`]** 첫 셀을 **정확 일치**로 바꿨다(`_DECIDED_TITLES` 표). 뮤테이션 **P1**(= M8 재유도, `title="에-라잇 App"`) → `SUBFAILED(service='application')` — **종전 3셀 전부 침묵에서 뒤집힘.**
  - **표는 데이터라 표 자체가 규칙을 벗어날 수 있다** → 둘째 셀(`test_the_decided_letters_themselves_follow_the_naming_rule`)이 표를 검사한다. 뮤테이션 **P2**(표 항목을 `"AI Writing App"` 으로) → **두 셀 모두** 발화. 새 서비스를 표에 더하면 일반 규칙이 자동 적용된다.
- (관측·조치 불필요) 변형 표기 맹점(M7) — 잔존 0실측, 의도가 문언화돼 있다.
  - **[닫힘 `924b0ab` — 조치 불필요 판정을 뒤집은 것이 아니라 비용이 한 줄이었다]** 스윕을 정규식(`ai[ \t]+writing[ \t]+system`, `IGNORECASE`)으로 바꿔 대소문자·공백 폭 변형을 잡는다. 뮤테이션 **P3**(= M7 재유도) 발화. **밑줄·하이픈 형태는 여전히 안 잡는다** — 그쪽은 식별자(`ai_writing_system` DB 이름 · npm 패키지명)이고, over-strict 뮤테이션 **P4**(식별자 두 형태 주입)에서 **침묵을 확인**했다(오탐 0).

## Verdict

**합격** — 두 커밋 모든 주장이 같은 diff 재유도로 성립한다: 29299e5 는 세 title 실측(`info.title`)·스캔 범위(compose 포함 실행 확인)·M1~M5 전부 일치, cfcb182 는 프로덕션 0줄·N1~N4·R6b 페어링 전부 일치. 보강 세션이 재검 기록에 단 폐쇄 주석도 과장 없이 정확했다(정정된 "미검증 0" 오류의 원 주인은 이 검증자 자신이다). README·LICENSE 잔존은 이 슬라이스 계약 밖의 미결 표면으로 오너 결정 요청(H-P1)으로 분리했다.

## Outstanding items

- ~~**H-P1 오너 결정 대기**~~ **[결정·이행 2026-08-21 `c1fed21`]** 교체 + 스윕 확장. 위 §Hardening 참조.
- ~~미검증: **코드 커밋 0** — 이 기록 계열뿐.~~ **[낡음 — 같은 날 뒤에]** 폐쇄 커밋 `924b0ab`·`c1fed21` 이 들어왔다. **개수를 베끼지 말 것**: 정확한 목록은 `git log <최신 검증기록 커밋>..HEAD` 로 유도(최신 검증 기록 = 이 기록 등재 커밋 — `git log -1 -- docs/verifications/2026-08-21/product_name_and_hardening.md`).
- dogfood(GATE-1) 선행 = 외부 키(변함없음).

## Reproduction

```bash
bash docs/verifications/2026-08-21/repro_product_name_and_hardening.sh   # M1~M8 + N1~N4·R6b
python3 scripts/dump_openapi.py | python3 -c "import json,sys; print(json.load(sys.stdin)['info'])"
grep -rniE "ai[ \t]+writing[ \t]+system" README.md LICENSE                # H-P1 — 폐쇄 후 0건이어야 한다
python3 -m pytest -q tests/test_product_name.py tests/test_rerank.py    # 폐쇄 후 5/8 · 23/26 (폐쇄 전 3/3 · 23/26)
python3 -m pytest -q                                                    # 전수(등재 전 기준 2358/1/2592)
```
