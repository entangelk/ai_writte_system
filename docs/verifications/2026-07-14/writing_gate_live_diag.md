# 검증 기록 — Phase 5.10 D1=A Writing Gate live diagnostics CLI

## Subject metadata

- **날짜**: 2026-07-14
- **요청자**: 오너(사용자) — "작업 AI가 작업한 부분 확인해서 검증하고 의심하고 또 의심해줄래? … LLM은 192.168.1.22:9080 외부 포트를 사용하면 되는데 무조건 안된다고 한건 아닌지까지"
- **검증자**: 독립 검증자(Claude, 작업자와 다른 session)
- **대상 slice/artifact**: Phase 5.10 D1=A operator-only Writing Gate live diagnostics(SoT v1.6.82)
  - `services/application/app/writing/gate_live_diag.py`(신규)
  - `scripts/diagnose_writing_gate.py`(신규)
  - `tests/test_writing_gate_live_diag.py`(신규)
  - production seam: `services/application/app/main.py`(`_default_writing_gate_service`에 `provider=None` 추가)
  - 문서 갱신: `docs/system-contract-sot.md`(v1.6.81→v1.6.82), `CHANGELOG.md`, `HANDOFF.md`, `docs/daily_logs/2026-07-14/work_log.md`, `docs/plans/05-writing-gate-live-diagnostics-decisions.md`(Resolved 표시)
- **정본 참조**: `docs/system-contract-sot.md` v1.6.82, `docs/plans/05-writing-gate-live-diagnostics-decisions.md`(D1=A/D2=A), `docs/plans/05-writing-persisted-loop-audit-decisions.md`(P1 bodyless / P2 opt-in), `docs/plans/05-writing-loop-benchmark-decisions.md`(B4 실측 전 default-off)
- **작업 출처**: working tree, uncommitted(`git status` — 6개 수정 + 3개 untracked).

## Scope

정본 계약을 먼저 좁혀 읽었다. 본 slice의 계약은 착수 결정 브리프 `05-writing-gate-live-diagnostics-decisions.md`(D1=A/D2=A)가 정하며, SoT v1.6.82 changelog가 그 요약이다. 브리프가 연쇄 참조하는 한에서 P1 bodyless 정책(왜 raw output이 없는지), B4 “실측 전 default-off”(왜 즉시 remediation하지 않는지), 그리고 재현 대상인 `/writing/revise-and-gate` 사전 Gate 파이프라인(`main.py` endpoint, `gate_prompt.py`의 `json_object()` parser, `WritingGateService.evaluate_metered`)까지 포함했다. 관련 없는 이전 plan iteration·아이디에이션은 제외.

경계 행렬(boundary matrix) — 브리프 D1=A가 이 slice에 요구하는 분기:
- **should**: Gate raw response + exact strict-parse error를 stdout에 출력; production과 동일 model/prompt template/`thinking=false`/`max_tokens`; 동일 ContextSearchRequest shape; 읽기/판정 메서드만 호출.
- **should NOT**: Mongo/audit/API response/file 어디에도 저장; D2 없이 prompt/repair/parser 변경(완화) 없음.

검증 대상 표면(정본→구현→회귀→live를 한 덩어리로):
1. **정본(브리프) 계약**: D1=A/D2=A, Follow-up #1/#2, Deferred.
2. **진단 코어 구현**: `gate_live_diag.py`.
3. **CLI 구현**: `scripts/diagnose_writing_gate.py`(+ `main.py` seam).
4. **회귀 테스트**: `tests/test_writing_gate_live_diag.py`.
5. **재현 대상 production 경로**: `gate_prompt.py` parser, `WritingGateService`, `main.py` `_WRITING_CONTINUE_SCENE_NEEDS` / `_default_writing_gate_service`.
6. **작업 AI의 “live 실행 불가” 주장 검증**: 본 머신 실제 상태(docker stack·게이트웨이·원격 LLM 도달성·benchmark project) + 실제 live 실행.
7. **D2=A evidence 획득(작업 AI가 미룬 단계)**: live 실행으로 raw Gate output 확보.

## Methodology

독립 재도출. 작업자 주장을 그대로 수용하지 않았다.

1. **git diff**: `git status`, `git diff services/application/app/main.py`, `git diff docs/system-contract-sot.md`, `git diff CHANGELOG.md` — 변경 범위와 “기본 동작 무변” 주장 확인.
2. **머신 상태 조사(“live 불가” 주장 반박용)**:
   - `docker ps`, `docker compose ls`
   - gateway env: `docker exec ai_writte_system-gateway-1 printenv | grep LLAMA`
   - gateway ready: `curl http://localhost:8011/health/ready`
   - 원격 LLM 도달성: `timeout 5 bash -c 'cat </dev/null >/dev/tcp/192.168.1.22/9080'`
   - benchmark project 존재: `mongosh ... db.projects.find()`; audit의 `error_type`: `db.writing_loop_audits.findOne(...)`
3. **정적 검증**: `python3 -m py_compile` (3 파일).
4. **회귀 테스트**: `python3 -m pytest tests/test_writing_gate_live_diag.py -q`; 추가로 gate 인접 suite `test_writing_gate.py test_writing_loop_audit.py test_writing_loop_budget.py`(main.py seam 회귀 확인).
5. **Live 실행(결정적)**: image rebuild 후 `docker compose run --rm --no-deps application python scripts/diagnose_writing_gate.py --project-id <benchmark> --current-position <DRAFT> <VERSION> --request-id gate-diag-verify[-2]`.
6. **no-write live 검증**: 진단 request_id로 audit 생성 건수 `db.writing_loop_audits.find({request_id:{$in:[...]}}).count()`, draft 증가 여부.
7. **root cause 확정**: fence 유무에 따른 `json.loads` 동작을 python3로 직접 재현.

## Findings

### 1. D1=A slice 구현 — 정본 계약 부합 (PASS)

- `gate_live_diag.py` `run_gate_diagnosis`: context→revise→report→gate 사전 파이프라인을 동일 collaborators로 재현, 각 단계를 `stage_trace`에 기록, Gate raw response를 `capture.gate_capture()`로 회수(WRITING_GATE_TEMPLATE 일치 항목). `MeteredCallError`의 cause가 `InvalidWritingGateResult`면 `invalid_gate_result`, 아니면 `gate_provider_error`로 분류 — 브리프가 요구한 exact strict-parse error 노출에 부합. 읽기/판정 메서드(`build_context_package`/`revise`/`enrich`/`evaluate_metered`)만 호출.
- `RawCaptureProvider`: 위임형 proxy. `generate`는 내부 provider를 그대로 호출 후 캡처 — production 동작 변경 없음.
- `scripts/diagnose_writing_gate.py` `build_services`: Gate를 `_default_writing_gate_service(provider=capture)`로 production factory 재사용 → prompt template·`LLM_GATEWAY_MODEL`/`WRITING_GATE_MAX_TOKENS`·`thinking=false`·`max_tokens`가 구조적으로 production과 동일(re-derive 아님). `--current-position` 옵션으로 idempotent seed write까지 회피 가능.
- `main.py` seam(`_default_writing_gate_service(*, provider=None)`): 기본값 `None`일 때 실제 `GatewayGenerateProvider` 생성(무변). `_build_revise_service`/`_build_report_service`가 이미 provider를 받는 선례와 일치. diff는 14줄, surgical.
- `format_diagnosis`: SENSITIVE 경고·stage trace·strict parse 결과·raw 블록(`-----BEGIN RAW-----`)·usage를 stdout 전용 텍스트로 출력. 머신 파싱용 구조를 의도적으로 배제(브리프 follow-up #1 부합).

### 2. 회귀 테스트 — 양방향 guard 존재 (PASS)

`tests/test_writing_gate_live_diag.py` 13 passed. 경계 행렬 매핑:
- **parity(under-strict)**: `test_production_factory_gate_request_parity` / `test_build_services_gate_request_parity` — env(`LLM_GATEWAY_MODEL`/`WRITING_GATE_MAX_TOKENS`)를 바꾸면 캡처된 request의 model/max_tokens/thinking/system prompt가 따라가는지 검증(config drift 시 fail). `test_build_search_request_matches_endpoint_shape` — `needs`=`_WRITING_CONTINUE_SCENE_NEEDS`, purpose=WRITING_CONTEXT, query fallback, budget 동형.
- **capture(under-strict + over-strict)**: `test_raw_capture_on_strict_parse_failure`(rogue key → `invalid_gate_result`, raw 보존 — parser 완화 시 `ok`로 flip해 fail)와 `test_raw_capture_on_successful_parse`(정상 → `ok`)가 양방향.
- **upstream 분류**: context/revise/report 각 실패 시 `UPSTREAM_ERROR` + `upstream_stage` + stage trace 절단(3 case). 
- **provider error 분류**: `test_gate_provider_error_is_classified` — `ProviderError(UNAVAILABLE)` → `gate_provider_error`, raw=None.
- **no-write spy**: `test_no_write_methods_are_invoked` — 호출 시퀀스가 `[build_context_package]`/`[revise]`/`[enrich]` 정확히 일치(write 경로 도달 시 spy log 발산 → fail).
- **format**: SENSITIVE·invalid_gate_result·raw·usage·`gate thinking: false` 출력; upstream 시 “not reached” 문구.

### 3. 작업 AI의 “live 실행 불가” 주장 — **허위(사실과 다름)**

작업 AI는 handoff/worklog에 “이 sandbox에는 full-stack이 없어 live 실행은 불가능합니다”라고 기록했다. 실제 머신 상태:

| 주장 | 실제 |
|---|---|
| full-stack 없음 | **전 스택 2시간째 실행 중**(healthy): application(:8000)·worker·embedding(:8002)·elasticsearch(:9200)·mongo(:27019)·gateway(:8011)·chroma(:8003) |
| (원격 LLM 미언급) | gateway env `LLAMA_BASE_URL=http://192.168.1.22:9080`, `/health/ready`=`{"status":"ready"}`, `LLAMA_DEFAULT_MODEL=google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`(브리프의 “Remote Gemma Q4”). `192.168.1.22:9080` 도달 **OPEN**(사용자 지적 포트) |
| (benchmark project 미언급) | **“B2b Writing Loop Benchmark 2026-07-14”** project(`6a5591e3…`) 존재 + 동 project audit에 `error_type:"invalid_gate_result"` 반복 기록(revise/report completed, gate failed, total_tokens 실측) |

유일한 실제 장애물: 새 파일(`gate_live_diag.py`/`diagnose_writing_gate.py`)이 image에 bake되고 volume mount가 없어, 실행 중인 image(2026-07-14T01:31:52Z 빌드)에 새 파일이 없음 → **image rebuild 필요**. 그러나 deps layer가 캐시되어 rebuild는 **약 6초**(services/scripts COPY 레이어만 갱신). 이는 “불가능”이 아니라 “명령 1회”이며, 작업 AI가 밝힌 이유(“full-stack 없음”)와도 무관하다. 사용자의 의심(“무조건 안 된다고 한 건 아닌지”)은 적중했다.

### 4. Live 실행 성공 + D2=A evidence 획득 (작업 AI가 미룬 단계 수행)

image rebuild 후 read-only 경로(`--current-position`)로 2회 live 실행. **둘 다 정상 종료**하며 동일 failure 재현:

```
Stage trace: context ok / revise ok / report ok / gate failed
Strict parse: INVALID — invalid_gate_result
  error: writing gate produced an invalid result: writing gate content must be JSON
Gate served_by_model: google/gemma-4-12B-it-q4_0-gguf:Q4_0
```

root cause(브리프 D2=A가 요구한 exact 위반 clause) — Gate raw output이 **markdown code fence(``` ```json … ``` ```)로 감싸져** 있고, `gate_prompt.py:71` `json_object()`가 `json.loads(content)`를 fence strip 없이 직접 호출 → `JSONDecodeError` → “content must be JSON”. 검증:
- as-is(fence 포함): `JSONDecodeError` → 관측된 실패.
- fence strip 후: `json.loads` **정상** → JSON 자체는 유효(decision/findings/checked_constraints 모두 정상 enum/구조).

즉 위반 clause는 **JSON 구조·enum·priority·evidence가 아니라 “markdown fence 래핑”**이다. Gate의 추론 자체는 정상(중복 문장을 continuity finding으로 지적, decision=revise)이고, 출력 포맷(fence)만 strict parser에 걸린다.

### 5. no-write — live에서도 성립 (PASS)

진단 request_id(`gate-diag-verify`, `gate-diag-verify-2`)로 생성된 `writing_loop_audits` = **0건**. “B2b benchmark context” draft도 3개 그대로(`--current-position` 사용). 회귀 단위 테스트뿐 아니라 **실제 live 실행**에서도 진단은 Mongo/audit/draft 어디에도 쓰지 않는다(브리프 P1/P2 경계 준수).

## Issues / Risks

### Blocking (contract 의무) — 없음

D1=A slice의 should/should-NOT 분기가 모두 회귀에 매핑되고, 양방향 guard가 존재하며, public literal·schema·서비스 경계 변화 없다. 정본 자기모순 미발견. spec-silent-but-code-enforced 갭 미발견. no-write는 live로 확인.

### Hardening recommendations (non-blocking)

- `format_diagnosis`의 `prompt_version` 기본값 `"writing_gate_v1"`가 hard-coded 상수 — 실제 prompt template version과 연동되지 않는 표시 전용 값. (현재 계약상 회귀 대상 아님.)
- 회귀에 markdown-fence 케이스는 없음(D2=A가 parser 변경을 별도 브리프로 미뤘으므로 slice 범위 밖). 단, D2 remediation이 “fence strip”으로 결정되면 parser 회귀에 fence 케이스가 필수로 추가되어야 한다.

## Verdict

**합격(PASS)** — D1=A operator-only diagnostic CLI는 정본 계약(parity·read-only·classification·SENSITIVE 처리)을 정확히 구현했고, 회귀는 양방향 guard를 갖추며, main.py seam은 무변이고, **live 실행으로 no-write와 parity가 실측 확인**됐다.

단, **작업 AI의 “live 실행 불가” 주장은 허위**이며 이것이 본 slice의 다음 단계(D2=A evidence 획득)를 차단한 유일한 원인이었다. 검증자가 동일 머신에서 image rebuild(약 6초) 후 live 실행해 evidence를 직접 확보했다. 따라서 slice 자체는 합격이나, “다음 단계가 막혀 있다”로 기록된 handoff/worklog 기술은 정정이 필요하다.

## Outstanding items

1. **(오너 결정 필요) D2=A remediation 브리프**: root cause가 “markdown fence 래핑”으로 확정됐으므로, 다음 중 하나를 별도 결정 브리프로 확정해야 한다 — (a) `json_object()`에서 ```json/``` fence strip 후 parse(parser 정규화, 구조 완화 아님), (b) JSON repair 1회 추가, (c) Gate prompt에 fence 금지 지시, (d) 조합. 검증자 권장: (a)+(c) — JSON 자체가 유효하므로 fence strip은 public contract를 약화시키지 않고, prompt 금지는 발생을 줄인다. 단 D2=A에 따라 이 결정·구현은 본 검증 범위 밖이며 오너 판단이다.
2. **image rebuild가 이미 수행됨**: 본 검증을 위해 `docker compose build application`을 실행했다. 새 image(`sha256:68e43b4b…`)에는 diagnostic 파일이 포함됐고, 임시 `run` 컨테이너만 이를 사용했다. 장기 실행 `ai_writte_system-application-1` 서비스는 여전히 old image이므로, 오너가 운영 application에 diagnostic 코드를 반영하려면 별도 `docker compose up -d --force-recreate application`이 필요하다(diagnostic는 별도 `run` 경로이므로 운영 동작에는 영향 없음).
3. **정정 대상**: work_log/HANDOFF의 “live 실행 불가” 기술을 “image rebuild 1회로 live 실행 가능, D2=A evidence 확보 완료”로 정정 권고(본 검증 기록이 근거).

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
# 1. 머신 상태
docker ps                                    # 전 스택 healthy
docker exec ai_writte_system-gateway-1 printenv | grep LLAMA   # LLAMA_BASE_URL=http://192.168.1.22:9080
curl -s http://localhost:8011/health/ready   # {"status":"ready"}
# 2. 정적 + 회귀
python3 -m py_compile services/application/app/writing/gate_live_diag.py scripts/diagnose_writing_gate.py tests/test_writing_gate_live_diag.py
python3 -m pytest tests/test_writing_gate_live_diag.py tests/test_writing_gate.py tests/test_writing_loop_audit.py tests/test_writing_loop_budget.py -q
# 3. live 실행(image rebuild 후, read-only 경로)
docker compose build application
docker compose run --rm --no-deps application python scripts/diagnose_writing_gate.py \
  --project-id 6a5591e39b2af0f7bf826937 \
  --current-position 6a5592fc9b2af0f7bf826938 6a5592fc9b2af0f7bf826939 \
  --request-id gate-diag-verify
# 4. no-write 확인
docker exec ai_writte_system-mongo-1 mongosh --quiet --host localhost:27017 ai_writing_system \
  --eval 'db.writing_loop_audits.find({request_id:{$in:["gate-diag-verify","gate-diag-verify-2"]}}).count()'  # 0
# 5. root cause 재현(fence)
python3 -c "import json,re; r='\`\`\`json\n{\"decision\":\"revise\"}\n\`\`\`'; \
 print('as-is', end=' '); json.loads(r)"   # JSONDecodeError
```
