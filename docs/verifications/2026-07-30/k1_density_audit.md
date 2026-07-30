# 검증 기록 — K-1 한글 토큰 밀도 환산 + 입력 예산 기본 8192

## Subject metadata

- **날짜**: 2026-07-30
- **요청자**: 오너(entangelk) — “다음작업 검증해줘. K-1 완료, 커밋 2개입니다. 트리 clean.”
- **검증자**: Claude(독립 검증 에이전트)
- **대상 슬라이스/산물**: K-1(a) — 토큰 추정 환산을 `len/4`→`len/1.7`(한글 실측)로 바꾸고, 입력 ContextPackage 예산 기본값을 4096→8192로 올림(오너 지시 ①·④). **K-1(c)(색인 시점 정확 계수)은 착수 안 함**.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.7.63(본문 §Phase 5 “입력 예산 기본 8192·환산 len/1.7” + 버전 로그), `docs/plans/context-budget-korean-tokens-decisions.md` §3 K-1·§3-1(K-1(a) 결과 블록), 선행 K-3(v1.7.62) 가드.
- **검증 대상 소스**: 커밋 2건 — `640f804`(환산 len/1.7, K-1(a)) · `83bcbd6`(예산 8192 + 프론트 + 스키마, SoT v1.7.63). HEAD = `83bcbd6`. 트리 clean.

## Scope

1. **환산**(`service.py::estimate_tokens`): `len/4` → `ceil(len/1.7)`, 상수 `KOREAN_CHARS_PER_TOKEN=1.7`, min 1.
2. **예산 기본**(`main.py`): `DEFAULT_CONTEXT_BUDGET_TOKENS=8192`, 6개 요청 본문 통합(복제 리터럴 제거).
3. **프론트 동기화**(`WritingPanel.tsx`): `MAX_TOKENS=4096→8192`(명시적 전송 → 서버 기본만 올리면 효과 없음).
4. **공개 계약**: `schema.d.ts` 6개 `@default 4096→8192`.
5. **K-1(c) 미구현 확인**: 색인 경로에 토큰 저장·LLM 의존 추가 없음.
6. **회귀 + 뮤테이션 매트릭스**(양방향).

## Methodology

- 계약 읽기: SoT v1.7.63 본문·버전 로그·§Phase 5; 브리프 §3 K-1·§3-1(K-1(a) 실측 블록). K-3 가드와의 독립성·(c) 근거 소멸 점검.
- 코드 읽기: `service.py::estimate_tokens`(환산 식)·`main.py::DEFAULT_CONTEXT_BUDGET_TOKENS` + 6개 본문·`WritingPanel.tsx::MAX_TOKENS`.
- 산술 검증(Python): 환산 식 `-(-len*10//17)` = ceil(len/1.7) 인 경계값·코퍼스; 초과 산술 `7,656+465+4,033+6,144`.
- 공개 계약: `gen:api`로 **독립 재생성** 후 `diff src/api/schema.d.ts`(커밋본 정확 일치).
- (c) 미구현: `indexing/`·`memory/`·`context_search/models.py`에서 `token_count`/`LLMProvider`/`tokenizer` grep.
- 백엔드 회귀: `PYTHONPATH=. pytest tests/test_context_search.py tests/test_application_api.py tests/test_context_search_candidate_memory.py tests/test_context_search_canonical_memory.py`.
- 프론트 회귀: `npx vitest run src/writing/WritingPanel.test.tsx`.
- 전체 수집: `pytest --collect-only -q`.
- **독립 뮤테이션 4종**(Edit → 해당 셀 → 실패 → 역방향 Edit 원복, 트리 clean·마커 0으로 확인): 환산 되돌림 · 과잉 보수화(1.7→1.4) · 예산 되돌림 · 본문 1개 리터럴화.

## Findings

### 1. 환산 — `service.py:561-567`

- `KOREAN_CHARS_PER_TOKEN = 1.7`; `estimate_tokens = max(1, -(-len(text)*10//17))` = `ceil(len/1.7)`(min 1). Python 검증: `''→1`, `'가'→1`, `17→10`(정확), `18→11`(올림), `100→59`, 코퍼스 21,774→**12,809**(실측 12,747, 비 0.995 — 무편향).
- 회귀 셀(`test_context_search.py::TokenEstimateTest`) 양방향: `estimated ≥ 12,747`(under-strict: len/4 되돌림 → 5,444 밑돌아 실패) AND `estimated ≤ 12,747×1.1=14,022`(over-strict: 1.4 → 15,553 웃돌아 실패). 이것이 “1.4~1.5가 아니라 1.7”인 근거를 셀이 단정.

### 2. 예산 기본 — `main.py:1854` + 6개 본문(1862·1873·1889·1900·1919·2022)

- `DEFAULT_CONTEXT_BUDGET_TOKENS = 8192`; 6개 요청 본문이 상수 참조(복제 리터럴 제거). OpenAPI 전수 셀(`test_application_api.py::ContextBudgetDefaultTest`): `DEFAULT_CONTEXT_BUDGET_TOKENS==8192` · `len(bodies)==6`(lock-list) · 각 본문 default==상수.

### 3. 프론트 동기화 — `WritingPanel.tsx`

- `MAX_TOKENS = 8192`(구 4096). 화면이 이 값을 명시적으로 실어 보내므로 서버 기본만 올리면 제품에 반영 안 됨 — 프론트 payload 셀이 `max_tokens: 8192`를 단정(3곳)해 한쪽만 바꾸면 깨짐.

### 4. 공개 계약 — `schema.d.ts`

- **독립 재생성 후 `diff` = 커밋본 정확 일치**. K-1 변경 = 6개 `@default 4096→8192`.

### 5. K-1(c) 미구현 — 확인

- `indexing/`·`memory/`·`context_search/models.py`에 `token_count`/`num_tokens` 필드 없음; `indexing/`에 `LLMProvider`/`provider.generate`/`/tokenize` 없음(임베딩 전용). **(c)는 착수하지 않았고 색인 경로에 LLM 의존이 새로 들어가지 않았다.** 작업자 주장과 일치.

### 6. 초과 산술 — 확인

- `7,656 + 465 + 4,033 + 6,144 = 18,298`; `− 16,384 = 1,914`. 브리프/SoT “만재+long −1,914”와 정확 일치. 이 초과는 조용한 잘림이 아니라 K-3 가드의 400.

### 7. 회귀 + 뮤테이션

- 백엔드 K-1 표면: **182 passed / 406 subtests**(환산·예산·memory 회귀). 원복 후 재 **155 passed / 406 subtests**.
- 프론트 WritingPanel: **47 passed**.
- 전체 수집: **1739 collected**(=1738 통과 + 1 스킵, 작업자 주장 일치). import 손상 없음.
- **독립 뮤테이션 4종, 전부 해당 셀에서 실패**(원복 후 트리 clean·마커 0·수집 1739 확인):
  - 환산 되돌림 → `ceil(len/1.7)`를 `len/4`로: 코퍼스 셀 `5,444 < 12,747`(under-strict) + 결정성 셀.
  - 과잉 보수화 1.7→1.4: 코퍼스 셀 `15,553 > 14,022`(over-strict, “멀쩡한 항목이 잘린다”).
  - 예산 되돌림 8192→4096: 전수 셀 `4096 != 8192`.
  - 본문 1개(ContextSearchHttpRequest) 리터럴 4096: 전수 셀 `4096 != 8192`(통합이 부분 발산을 잡음).

## Issues / Risks

### Blocking (계약 의무) — 없음

경계 행렬 빈 셀 없음. SoT(v1.7.63) 내부 일관. 코드 동작이 SoT와 일치. K-3 가드가 서버 계수를 써서 이 상수가 틀려도 창 초과 요청이 통과하지 않는다는 핵심 주장이 뮤테이션(환산 되돌림)으로 입증됨 — 상수는 예산 집행에만 쓰이고 가드는 독립.

### Hardening recommendations (비차단)

- **H1 — `main.py` 예산 주석이 정본과 모순(후보 본문 누락)**: `main.py:1847-1848`이 “예산 8192를 꽉 채운 report 입력은 약 8,100 tok이고 출력 상한 6,144를 더해도 **14,300 < 16,384**(들어감)”라 적지만, 이 8,100 = items(7,656)+system(465)이고 **후보 본문(4,033)을 빠뜨렸다**. 정본 SoT v1.7.63는 같은 scenario를 `7,656+465+4,033+6,144 = 18,298 > 16,384`(**+1,914 초과**)로 잡는다 — **결론이 정반대**. 동작은 SoT대로(가드 400)지만, 상수 바로 옆 주석이 “들어간다”고 단언해 미래 독자(또는 오너)가 8192를 report에 안전하다고 오읽을 수 있다. 후보 본문을 포함해 18,298으로 고칠 것. 행동 결함은 아니다.
- **H2 — 실측 미재현**: 코퍼스 밀도(12,747 tok · 1.708 자/tok)는 외부 12B `/tokenize`로 베타 429블록을 계수한 작업자 보고치. 환산 **식**·셀 경계·`12,809 vs 12,747`(비 0.995)은 검증됐으나 12,747 자체는 독립 재실측 못 함.
- **H3 — 전체 1738 green bar 미종단**: K-1 표면(182) + 수집(1739) 검증. test mongo/es compose 미기동으로 전체 suite는 worker 환경 기준.
- **H4 — 라이브 “Strict parse OK(prompt_tokens 3,257)” 미재현**: 외부 12B 필요.

## Verdict

**합격(PASS)** — 단, 비차단 H1(주석 정정) 권장.

하중 이유: (1) 경계 행렬 빈 셀 없음 — 환산 양방향·예산 6본문 전수·프론트 payload 단정; (2) SoT 내부 일관, 코드가 SoT와 일치; (3) 뮤테이션 4종(양방향)이 독립적으로 해당 셀을 물음 — 특히 환산 되돌림(under-strict)·과잉 보수화(over-strict)가 “1.7이 무편향 선택”인 근거를 셀이 단정; (4) K-3 가드가 서버 계수를 써 이 상수와 독립이라는 핵심 주장이 입증됨(상수 퇴행이 예산을 틀리게 해도 창 초과는 가드가 막음); (5) `schema.d.ts` 재생성이 커밋본과 정확 일치; (6) K-1(c) 미구현·색인 경로 LLM 무의존 확인. H1은 행동이 아닌 주석 오류이며 합격을 가리지 않으나, 정본과 모순되는 “들어간다” 단언이므로 정정 권장.

## Outstanding items

- **커밋 완료**: K-1 2커밋(`640f804`·`83bcbd6`)이 HEAD. 트리 clean.
- **오너 결정 2건(작업자가 남김)**: ⓐ K-1(c) 보류 확정? (추천 보류 — K-3 가드가 상수를 안 쓰므로 (c) 하중 근거 소멸, 회계 비 1.07, (c)는 색인 경로에 LLM 의존 추가) ⓑ R-a(report 전용 예산) 여부 — 만재+long −1,914 해소 vs 가드 400으로 두고 사용자가 분량 줄이게 vs 창 32768 확장.
- **K-4(프론트 글자수 표시·경고)**: 선행(환산 확정)이 끝나 순서상 착수 가능(결정 대기 아님).
- **주석 정정**(H1): `main.py:1847-1848` report 입력에 후보 본문(4,033) 추가해 18,298으로.

## Reproduction

```bash
# 공개 계약 무변
cd frontend && node_modules/.bin/openapi-typescript <(python3 ../scripts/dump_openapi.py) -o /tmp/k.d.ts \
  && diff src/api/schema.d.ts /tmp/k.d.ts   # no output

# 환산 산술
python3 -c "print(-(-21774*10//17), 7656+465+4033+6144, 7656+465+4033+6144-16384)"  # 12809 18298 1914

# 백엔드 + 프론트
PYTHONPATH=. python3 -m pytest tests/test_context_search.py tests/test_application_api.py \
  tests/test_context_search_candidate_memory.py tests/test_context_search_canonical_memory.py -q  # 182 passed
cd frontend && npx --no-install vitest run src/writing/WritingPanel.test.tsx   # 47 passed

# 수집
PYTHONPATH=. python3 -m pytest --collect-only -q   # 1739 collected

# 뮤테이션(예: 환산 되돌림) — service.py estimate_tokens 의
# `-(-len(text)*10//17)` 를 `(len(text)+3)//4` 로 바꾼 뒤:
PYTHONPATH=. python3 -m pytest tests/test_context_search.py -q -k "density or estimate"  # FAILED (5444 < 12747)
```
