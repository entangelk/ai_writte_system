# 검증 기록 — 베타 `long` report 실패 / 포인터 루트원인 실측 (코드 변경 0)

## Subject metadata

- **날짜**: 2026-07-29
- **요청자**: 오너(entangelk) — "작업 AI가 작업한 거 확인해서 검증하고 의심하고 또 의심해줄래?"
- **검증자**: Claude(본 세션)
- **검증 대상**: 작업자가 2026-07-29 베타에서 수행한 **조사 슬라이스(코드 변경 0, 문서 3)**. 핵심 주장은
  "`long` 프리셋이 실제 원고 분량 입력에서 4/4 실패하며, 원인은 한글 밀도(2.4배)가 아니라
  항목별 **포인터 렌더링이 예산 회계에서 통째로 빠진 것(12.7배)**이다."
- **정본 사양 참조**: `docs/plans/context-budget-korean-tokens-decisions.md` **§2-3**(작업자가 오늘
  추가한 베타 실측 절) 및 그 절이 인용하는 코드 표면. §2-1/§2-2(알파 산술 대조)는 §2-3의 선행
  서술로서 범위에 포함.
- **검증 대상 작업의 출처**: **working tree, uncommitted**(`git status`: `M HANDOFF.md` ·
  `M docs/plans/context-budget-korean-tokens-decisions.md` · `?? docs/daily_logs/2026-07-29/`).

> **비고(검증 성격)**: 이 슬라이스는 구현이 아니라 **조사**다. 따라서 "should-fire / should-NOT-fire
> 경계 매트릭스" 형태의 행동 계약은 없다. 본 검증은 작업자의 **측정·코드 인용·결론이 사실인가**를
> 1차 소스에서 재도출하는 것을 목적으로 한다. 경계 매트릭스 규칙은 아래 "방법론"의 코드-대-계약
> 정합성 항목으로 대체한다.

## Scope

1. **코드 인용 정합성** — work_log/§2-3이 인용한 모든 `file:line`이 소스와 일치하는가.
2. **루트원인 메커니즘** — 예산 회계가 포인터를 "한 토큰도 세지 않는다"는 코드 주장.
3. **측정 수치** — `token_estimate_total=887` · 생성 컨텍스트 2,412 tok · report 컨텍스트 11,304 tok ·
   포인터 몫 79% · report 합계 12,462 tok (독립 재구성으로 교차).
4. **실제 실패 재현** — DB 감사에서 `writing_generation` 성공 vs `writing_report` `provider_error`.
5. **창/임계 추론** — prompt>n_ctx→400, prompt<n_ctx ∧ prompt+max_tokens>n_ctx→200.
6. **문서 정합성** — 브리프 §2-3 + R-e 추가, HANDOFF ★ 재서술·401 부채 6종·자가 검수.
7. **부수 주장** — 감사 관측 한계(total_tokens only), 401 6종, 프론트 "다시 시도".

## Methodology (재현 가능한 명령)

모든 측정은 **작업자가 쓴 것을 읽지 않고** 1차 소스에서 재도출했다. 기계 상태(2026-07-29):
스택은 `docker ps`로 **healthy 7 + healthcheck 없는 2(worker·generation_worker)** 확인(작업 로그
상태와 일치). 외부 LLM 서버 `192.168.1.22:9080` 도달 확인, `/props` = `n_ctx=8192 · total_slots=1`.

- **코드 읽기**: 각 인용 위치를 직접 read(`provider.py`·`context_pointer.py`·`prompt.py`·`report.py`·
  `transport.py`·`payload.py`·`llm_call_audit.py`·`GenerationPad.tsx`·`main.py`·`generation_worker.py`·
  `diagnose_writing_gate.py`).
- **DB 직접 집계**(프로젝트 mongo, `docker exec ai_writte_system-application-1 python` →
  `pymongo` to `ai_writing_system`): `llm_call_audits`를 `call_site × outcome`으로 group +
  `total_tokens` 합; `writing_generation_jobs`의 `status/failure_reason/output_length`;
  `source_blocks`/`source_snapshots`/`projects`로 시드 규모·`content_hash` 길이 확인.
- **독립 재구성**(골드 패스): 작업자가 쓴 문서를 전혀 읽지 않고, **프로덕션** `build_context_package`로
  무거운 시드 프로젝트(`6a694675…0ae`)의 패키지를 빌드 → **프로덕션** `format_context_package`로
  `include_pointers True/False` 렌더 → **프로덕션 모델 토크나이저**(`/tokenize`,
  `192.168.1.22:9080`)로 토큰화. 스크립트는 stdin으로 pipe(컨테이너 fs에 기록 안 함).
- **창 프로브**(호스트 `python3` → `192.168.1.22:9080`): (1) prompt 20,000 tok + `max_tokens=64`,
  (2) prompt 3,000 tok + `max_tokens=6144`.
- **문서 diff**: `git diff docs/plans/context-budget-korean-tokens-decisions.md` + `grep HANDOFF.md`.

## Findings

### F1. 코드 인용 — 전부 정확 (합격)

인용한 줄을 소스와 대조했다. 모두 정확.

| 인용 | 소스 실측 | 평가 |
|---|---|---|
| `provider.py:13-18` total=prompt+completion | `TokenUsage.total_tokens = prompt+completion`(`:17-19`) | ✓ |
| `context_pointer.py:26` `POINTER_KEYS` 4키 | `("collection","document_id","version_id","content_hash")` | ✓ |
| `context_pointer.py:94-99` `pointer_json` | `json.dumps(..., separators=(",",":"))` | ✓ |
| `prompt.py:113-126` 렌더링 형식 | `:124` `- [label] {text}`(포인터 없음) / `:125-126` `- [label] {pointer_json} {text}` | ✓ |
| `report.py:139-141` `include_pointers=True` | `_request`가 `format_context_package(package, include_pointers=True)`(`:140-141`) | ✓ |
| `transport.py:122-128` 4xx→`REQUEST_REJECTED`/`retryable=False` | `:122-128` 정확 | ✓ |
| `payload.py:69-71` 모든 호출에 `enable_thinking` | `template_kwargs.setdefault("enable_thinking", …)`(`:70-71`) | ✓ |
| `GenerationPad.tsx:20` "생성 모델 호출에 실패했습니다." | 정확; 추가로 **"다시 시도" 버튼**이 `:63-65`에 렌더됨 | ✓ |
| `main.py:4121` long async 경로 | `if output_length in (MEDIUM, LONG):`(`:4121`) | ✓ |
| `generation_worker.py:85` `llm_call_scope` | `with llm_call_scope(...)`(`:85`) | ✓ |
| `diagnose_writing_gate.py:240` 시드 위임 401 | `seed_context`가 무인증 `POST /drafts`(`:236-242`) | ✓ |

작업 로그가 "인용 줄 번호 4건이 어긋나 고쳤다"고 한 것도 확인 결과 현재는 전부 정합.

### F2. 루트원인 메커니즘 — 코드에서 확정 (합격)

- `estimate_tokens(text) = max(1, (len(text)+3)//4)` — **문자열 길이/4**. (`context_search/service.py:540-541`)
- `token_estimate_total = sum(item.token_estimate for item in included)` (`:620`). 각
  `token_estimate = estimate_tokens(text)` (`:812/:919/:1089`). **포인터는 1 토큰도 더하지 않는다.**
- 비대칭: `format_context_package`의 docstring(`prompt.py:54-57`)이 "Only that one turn opts in
  [to pointers]: the generation and revise prompts produce prose, not pointers"로 명시. report만
  `include_pointers=True`(`report.py:140-141`).

→ "예산 회계는 `text`만 세고 포인터는 안 센다"는 코드 주장은 **참**이다.

### F3. 측정 수치 — 독립 재구성으로 사실상 완전 일치 (합격)

골드 재구성(프로덕션 서비스·렌더러·토크나이저) 결과:

| 항목 | 작업자 주장 | 독립 재구성 | 차이 |
|---|---|---|---|
| macro_items | 69 | **69** | 0 |
| `token_estimate_total` | 887 | **887** | 0 (재계산 `sum(len/4)`=887도 일치) |
| 컨텍스트(포인터 없음) | 4,588자 / 2,412 tok | 4,588자 / **2,411** tok | +1 tok |
| 컨텍스트(포인터 포함) | 18,586자 / 11,304 tok | 18,586자 / **11,303** tok | +1 tok |
| 포인터 몫 | 79% (8,892 tok) | **78.7%** (8,892 tok) | ≈0 |
| 과소평가 배수 | 12.7배 | **12.7배** | 0 |
| report system 프롬프트 | 473 tok | **473** tok | 0 |
| report 프롬프트 합계(후보 1,000자) | 12,462 tok | **12,461** tok | +1 tok |

+1 tok 차이는 작업자가 `/tokenize` 호출 시 `add_special=True`(BOS 1개 추가)를 쓴 반면 재구성은
`add_special=False`를 써서 발생. 설명 가능하고 유의미하지 않다. **수치는 사실상 완전 재현**됐다.

`content_hash`가 "64자"라는 주장도 실데이터로 확인(`source_snapshots.content_hash` 길이=64, sha256 hex).

### F4. 실제 실패 — DB에서 재현 (합격)

`llm_call_audits`(총 44건, 전부 2026-07-29) 집계:

- **무거운 입력** `heavy-long-1..4`: `writing_generation` 4/4 **success**(토큰
  **4,570·4,623·4,685·5,209**), `writing_report` 4/4 **`provider_error`**(`total_tokens=0`,
  `error_type=provider_request_rejected`). `writing_generation_jobs` 8건 = **4 succeeded + 4
  failed(`failure_reason=provider_error`, `output_length=long`)**.
- **얇은 입력** `long-report-probe-1/2/3`: generation success(토큰 1,105·1,207·1,158·1,114 ≈ 평균
  1,146), report success + repair 구조. job 성공.

헤드라인("무거운 입력 → generation 4/4 성공인데 report 4/4 provider_error, job 4/4 실패")은
**DB에서 그대로 재현**된다. `error_type=provider_request_rejected`는 `transport.py`의
`REQUEST_REJECTED` 매핑과 일치.

### F5. 창/임계 추론 — "200 vs 400"은 확인, "조용한 잘림"은 추론 (조건부 합격)

- `/props` = `n_ctx=8192`(확인).
- **Probe 1**(prompt 20,000 tok > 8,192) → **400 `exceed_context_size_error`,
  `n_prompt_tokens=20016`**. 작업 로그 재현과 **수치까지 동일**.
- **Probe 2**(prompt 3,000 tok < 8,192, but +6,144 = 9,144 > 8,192) → **200**(`finish_reason=stop`).

→ "llama.cpp는 prompt 자체가 n_ctx 이내면 prompt+max_tokens가 넘어도 400을 주지 않는다"는
§2-3⑦의 **하중 지반(200이지 400이 아니다)은 확인**됐다. 따라서 창 16,384에서 report
prompt(12,461)는 400이 아니라 200을 받는다. 단, **"그 뒤 출력이 잘려 `invalid_report`가 된다"는
부분은 직접 관측하지 못했다**(16,384-창 서버에서 report가 3,922 tok 이상을 뱉는 경우를 재현하지
않음). 이는 **구조적으로 건전한 추론**(잔여 3,922 < 요청 6,144)이며 작업자도 추론으로 서술했으므로
블로킹은 아니다. 다만 "측정"이 아닌 "추론"임은 기록에 명시됐어야 한다 — §2-3⑦는 표의 16,384 행을
과거형 단정("출력만 잘림")으로 쓰고 있어, 직접 재현된 8,192 행과 동급의 확신처럼 읽힌다.

### F6. 문서 정합성 (합격, 사소한 nit)

- **브리프 §2-3 + R-e**: `git diff`로 확인. §2-1 "빈도 미측정" 단락을 취소선+§2-3으로 redirect,
  §2-3 ①~⑦ 신설, K-6 표에 **R-e 신설**(장단점 포함), **추천은 R-a에서 옮기지 않음**. 작업 로그
  서술과 일치. R-e가 인용한 `report.py:62` allowlist 구조도 확인.
- **HANDOFF ★**(line 126): "미확인 가설" → "★ 확인됨 — 오늘 배포에서 실제로 깨져 있다"로
  **재서술**(append 아님). 수치(887/11,304/12.7배/79%/2,412)는 본 검증과 일치.
- **HANDOFF 401 부채**(line 124): "최소 **6종**" — smoke 4종(줄번호 인용) + diagnose 2종
  (`diagnose_writing_report.py`·`diagnose_writing_gate.py:240`). 작업 로그 ⑥과 일치.
- **자가 검수 헤더**(line 7): "202줄"이라 했으나 `wc -l HANDOFF.md` = **201** (마지막 줄의 trailing
  newline 차이; 1차 artifact). 헤더가 "★는 덧붙이지 않고 다시 썼다 / 2줄 덜어냄 / 3줄 추가"까지
  구체적으로 기술한 점은 CLAUDE.md HANDOFF 규칙(완료 서술 중복 금지)을 성실히 이행.

### F7. 부수 주장 (합격)

- **감사 관측 한계**: `StoredLlmCall`(`llm_call_audit.py:105-124`)은 `total_tokens`(int)만 보관.
  `prompt_tokens`/`completion_tokens` 분해·`finish_reason`·`truncated` 전부 없음. "잘림이 감사에서
  원리적으로 안 보인다"는 주장 **참**.
- **401 6종**: smoke 4종은 D8-3 인증 시행으로 무조회 401(구조), diagnose 2종은 F1에서 무인증
  `POST /drafts` 확인.
- **프론트 "다시 시도"**: `GenerationPad.tsx:63-65`에서 실패 job마다 "다시 시도" 렌더. 같은 입력 →
  같은 패키지(12,461 tok) → 같은 400이므로 재시도는 **결정적**으로 같은 실패. 주장 **참**.

## Issues / Risks

### Blocking (계약 의무 위반)
**없음.** 이 슬라이스는 조사(코드 변경 0)이며 행동 계약 경계를 건드리지 않는다. 작업자의 모든
하중 주장은 1차 소스로 확인됐다.

### Hardening recommendations (비블로킹 — 문서 정밀도)

작업자의 **결론에는 영향이 없지만**, work_log 표가 DB와 완전히 맞지 않는 정밀도 nit들:

1. **무거운 generation 토큰 범위**: work_log "4,623~5,209"이나 DB 실측은
   **4,570~5,209**(`heavy-long-4`=4,570). 하단이 53 tok 좁게 보고됐다.
2. **얇은 입력 콜 수**: work_log 표(report 4 calls/3 corr, gen 3)가 DB(report 5 calls/3 corr —
   `probe-1`이 report 3·gen 2회, gen 4회)와 안 맞는다. 방향(성공 + repair 구조)은 유효하나 표의
   정확한 카운트는 DB에서 재현되지 않는다. 비하중 영역.
3. **threshold-1000…7000 스윕**: DB에 7건의 `writing_report` `provider_error`(correlation
   `threshold-*`)가 더 있으나 work_log 표에 열거되지 않았다. §2-3 재구성(후보 산문 길이 스윕)의
   부산물로 보이나, "관통 결과 8회"와 이 7건의 관계가 명시되지 않았다.
4. **잔류 project 수**: work_log "project 3개"이나 DB는 **4개**(thin 2 + heavy 2).
5. **HANDOFF "202줄" vs `wc -l` 201**: trailing newline artifact(사소함).
6. **시드 "3,586자" vs 인덱스 3,449자**: 블록 경계 정규화로 설명 가능(사소함).

이들은 K-1·K-6 결정 근거를 바꾸지 않는다. 정리한다면 work_log 표 ①·②와 HANDOFF 줄 수 정도.

## Verdict

**합격.**

작업자의 핵심 주장 세 축 — (a) `long`이 무거운 입력에 4/4 실패, (b) 원인이 포인터 렌더링 누락
(887 vs 11,304, 12.7배), (c) "생성은 되는데 report만 죽는" 비대칭 — 을 1차 소스(DB·프로덕션
코드·프로덕션 토크나이저)에서 **독립적으로 재현**했다. 특히 F3의 골드 재구성은 작업자 수치와
**1 tok 오차 이내**로 일치한다. 오너 결정(K-1·K-6)에 들어가는 입력은 **정확**하다.

유일한 조건부: F5의 "16,384 → 조용한 잘림"은 "200 vs 400"까지는 측정이나 "잘림" 자체는 추론이다.
블로킹은 아니지만, §2-3⑦가 이를 측정처럼 서술했으므로 향후 16,384-창 환경에서 report가 잔여
예산을 넘는지 한 번 더 재면 신뢰가 완전해진다.

## Outstanding items (오너 다음 단계에 영향)

- **미커밋 상태**(작업자 의도): 컨텍스트 예산 트랙은 K-1·K-3~K-6이 전부 오너 결정 대기라 코드
  변경 없이 문서만 working tree에 있음. 커밋 여부는 오너 판단.
- **화면 육안 확인 미수행**: 스택이 떠 있고 감사·프로브 데이터(heavy long report probe /
  long report probe project)가 있어 HANDOFF Next Tasks 3(a) 관측 화면 확인(성공/실패 분포,
  실패 UX)을 **지금** 할 수 있으나, 브라우저·사람 눈이 필요해 본 검증 범위 밖.
- **진단 스크립트 401 부채**(⑥): 같은 장애 재조사 시 원인 관측 도구가 막혀 있음. 작업자가
  우회(앱 코드 직접 재구성)한 리그는 repo에 없다 — 본 검증의 F3 재구성 스크립트(/tmp, 세션
  한정)가 사실상 같은 우회의 재현이므로, 영구화를 원하면 진단 스크립트에 로그인을 붙이는 쪽이
  낫다(작업자 권고와 동일).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# (1) 스택 상태 + 외부 LLM 도달
docker ps --format '{{.Names}}\t{{.Status}}'
python3 -c "import httpx;print(httpx.get('http://192.168.1.22:9080/props',timeout=10).json()['default_generation_settings']['n_ctx'])"
# → healthy 7 + worker 2 (healthcheck 없음) ; n_ctx=8192

# (2) DB 감사 집계 (독립 재현 of F4)
docker exec ai_writte_system-application-1 python -c "
import pymongo,os
from collections import defaultdict
db=pymongo.MongoClient(os.environ.get('MONGO_URL','mongodb://mongo:27017'))['ai_writing_system']
g=defaultdict(lambda:defaultdict(int))
for d in db['llm_call_audits'].find({},{'_id':0,'call_site':1,'outcome':1}):
    g[d['call_site']][d['outcome']]+=1
for s in sorted(g): print(s, dict(g[s]))
print('jobs', [(j['status'],j.get('failure_reason')) for j in db['writing_generation_jobs'].find({},{'_id':0,'status':1,'failure_reason':1})])
"

# (3) 루트원인 수치 (독립 재구성 of F3) — 스크립트는 stdin pipe (컨테이너 fs 미기록)
#     /tmp/reconstruct_pkg.py: build_services().context_search.build_context_package(...)
#     → format_context_package(include_pointers=True/False) → /tokenize
docker exec -i -e PYTHONPATH=/app ai_writte_system-application-1 python - < /tmp/reconstruct_pkg.py
# → 69 items / est 887 / no-ptr 2411 / ptr 11303 / share 78.7% / 12.7x / sys 473 / total 12461

# (4) 창 프로브 (독립 재현 of F5)
python3 -c "
import httpx;b='http://192.168.1.22:9080'
def chat(p,m):return httpx.post(b+'/v1/chat/completions',json={'model':'x','messages':[{'role':'user','content':p}],'max_tokens':m},timeout=120)
print('probe1', chat('가'*40000,64).status_code)          # 400
print('probe2', chat('가'*6000,6144).status_code)          # 200
"

# (5) 문서 diff (F6)
git diff docs/plans/context-budget-korean-tokens-decisions.md
grep -n '마지막 자가 검수\|최소 6종\|★ 확인됨' HANDOFF.md
```
