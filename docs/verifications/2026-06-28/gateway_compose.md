# gateway compose 편입 + gateway app shell 독립 검증

## Subject Metadata

- **날짜**: 2026-06-28
- **요청자**: 사용자 ("gateway를 compose에 추가하되, llama.cpp 서버는 compose가 띄우지 않는 구조로… 진행 완료했어요")
- **검증자**: Claude (본 세션)
- **대상**: gateway FastAPI shell + Dockerfile + compose 편입. **커밋 해시가 요청에 없었고 `git log bc7d1bb..HEAD`에도 gateway 커밋이 없음 → 변경이 working tree에 uncommitted 상태로 존재**(`git status`로 확인).
- **작업 출처**: **working tree, uncommitted**. `git status`: modified `docker-compose.yml`·`services/llm_gateway/requirements.txt`·CHANGELOG·HANDOFF·work_log; untracked `services/llm_gateway/app/main.py`·`services/llm_gateway/Dockerfile`·`tests/test_llm_gateway_app.py`.
- **정본 spec 참조**: `docs/system-contract-sot.md` v1.5 §143-167 (LLM Gateway 계약), `docs/plans/llm-gateway.md`. gateway provider/transport 계층은 기존 커밋(`23c3519` Slice 0.6 등)에 존재; 이번 표면은 FastAPI shell + compose 편입.
- **검증 입장**: (1) 작업자 보고 "전체 discover가 test_application_api 첫 TestClient에서 장시간 멈춰 중단"을 독립 재현/진단, (2) SoT gateway 계약(§143-167) 정합, (3) llama.cpp 외부 의존 + LLAMA_BASE_URL override 구조, (4) test 견고성, (5) **uncommitted provenance** 명시.

## Scope

1. **provenance**: 작업자가 "진행 완료"라 했으나 커밋 여부 확인
2. **★ discover 멈춤 재현/진단**: gateway 변경과의 인과관계, 본 검증 환경에서의 재현 여부
3. **gateway app(main.py) ↔ SoT §143-167 정합**: 독립 컨테이너, MongoDB/ES 비접근, trust_env=false, 5 provider error 매핑, completion 응답 계약
4. **compose gateway 서비스**: llama.cpp 외부 의존, LLAMA_BASE_URL override, extra_hosts, healthcheck(live/ready 분리)
5. **Dockerfile**: cache-friendly
6. **test_llm_gateway_app.py**: FakeLLMProvider 주입 단위 테스트 견고성
7. **focused 18개 + 전체 discover 숫자 재계산**

## Methodology

### 1. provenance + 커밋 식별

```bash
git log --oneline bc7d1bb..HEAD     # gateway 커밋 부재 → 44407a2(archive follow-up)가 최신
git status                          # working tree에 gateway 변경이 untracked/modified로 존재
```

### 2. ★ discover 멈춤 재현 (타임아웃 보호)

```bash
timeout 90 python3 -m unittest discover -s tests 2>&1 | tail    # 멈춤 감지
env | grep -iE "CORE_SOT|LLAMA|COMPOSE"                          # 환경 의존성 원인 추정
```

### 3. SoT §143-167 정합 — contract↔코드 대조

main.py의 import/의존/매핑을 §143-167 literal과 대조.

### 4. Boundary matrix (gateway endpoint 분기 → test trace)

`/health/live`·`/health/ready`·`/v1/generate`(정상/빈 messages/provider error) 분기를 test에 매핑.

### 5. focused 재실행 + 숫자 교차 검증

```bash
python3 -m unittest tests.test_llm_gateway_app tests.test_llama_provider_client tests.test_httpx_transport
```

## Findings

### Surface 1 — provenance (★)

작업자가 "진행 완료했어요"라 했으나 **gateway 변경이 커밋되지 않았다**. `git status`:
- modified: `docker-compose.yml`, `services/llm_gateway/requirements.txt`, CHANGELOG, HANDOFF, work_log
- untracked: `services/llm_gateway/app/main.py`, `services/llm_gateway/Dockerfile`, `tests/test_llm_gateway_app.py`

→ 본 검증은 **working tree(uncommitted)** 기준. 작업자가 보고한 Docker smoke(build/up/curl)도 working tree 기준이었을 것. Outstanding items에 커밋 대기 명시.

### Surface 2 — ★ discover 멈춤 재현 불가 (작업자 보고와 불일치)

작업자 보고: "전체 unittest discover -s tests는 기존 test_application_api의 첫 TestClient 구간에서 장시간 멈춰 중단… focused suite와 Docker smoke로 검증".

**본 검증 재현 결과**:
```
timeout 90 python3 -m unittest discover -s tests
→ Ran 211 tests in 0.362s ... OK (skipped=27)   EXIT=0 (멈추지 않음)
```
**멈추지 않는다.** 211개 0.362초 통과. 작업자 보고와 정면 불일치.

**원인 추정**:
```
env | grep -iE "CORE_SOT|LLAMA|COMPOSE"  → (관련 env 없음)
```
본 검증 환경엔 `CORE_SOT_MONGO_URI`가 없다. 반면 작업자 환경에 이 env가 설정되어 있었다면 — `test_application_api`의 첫 test(`test_health_endpoint`)가 `TestClient(create_app())` → `create_app._default_service`가 `CORE_SOT_MONGO_URI`를 읽어 Mongo 연결 시도 → Mongo가 응답하지 않으면 **hang**. 이 경로는 `services/application` 코드이며 **gateway 변경과 완전히 별개 모듈**이다.

**결론**: discover 멈춤은 (a) 본 검증 환경에서 재현되지 않으며, (b) gateway 변경과 인과관계가 없다(별개 모듈). 작업자 환경의 `CORE_SOT_MONGO_URI` env 의존 latent 이슈 추정. 작업자가 discover를 포기하고 focused+Docker smoke로만 검증한 것은 **불필요하게 보수적**이었고 전체 회귀 검증을 놓쳤을 가능성이 있다 — 본 검증이 211개 통과로 전체 회귀 이상 없음을 보완 증명.

### Surface 3 — gateway app ↔ SoT §143-167 정합 (★ 핵심)

| SoT clause | 구현(main.py) | 정합 |
|---|---|---|
| §143 Gateway는 독립 컨테이너 | compose gateway 서비스(docker-compose.yml:52-79) | ✓ |
| §145 Gateway는 MongoDB/ChromaDB/ES 접근 안 함 | main.py에 Mongo/ES import 없음; httpx로 llama upstream만 | ✓ |
| §146 domain tool registry/terminal decision 소유 안 함 | gateway app에 tool registry 없음 | ✓ |
| §147-153 5 provider error literal | `ProviderErrorCode`(errors.py) + `_status_for_error`(main.py:69-78) 매핑 | ✓ |
| §155-160 completion 응답(model/content/finish_reason/usage tokens) | `/v1/generate` 반환(main.py:160-168) | ✓ (`total_tokens` 부가, 정합 위반 아님) |
| §161 usage 누락/invalid → provider_invalid_response(502) | `_status_for_error` else→502 | ✓ |
| §163 명시적 token count 0 유효 | payload/provider 계층에서 처리(기존) | ✓ |
| §165 HttpxJsonTransport trust_env=false 기본 | `_build_provider`: `trust_env=_env_bool("LLAMA_TRUST_ENV", False)`(main.py:58) | ✓ |
| §167 tool-call parsing 미구현 | gateway app에 parsing 없음 | ✓ |

SoT gateway 계약 위반 없음.

### Surface 4 — `_status_for_error` provider error → HTTP 매핑 (main.py:69-78)

| code | HTTP | 잠금 |
|---|---|---|
| TIMEOUT | 504 | (test_llm_gateway_app 미커버) |
| OVERLOADED | 429 | (미커버) |
| UNAVAILABLE | 503 | ✓ `test_provider_error_uses_stable_public_envelope` (test_llm_gateway_app.py:79) |
| REQUEST_REJECTED | 400 | (미커버) |
| INVALID_RESPONSE(else) | 502 | (미커버) |

5종 중 1종(UNAVAILABLE)만 lock. 나머지 4종 매핑은 단순 if-chain이라 회귀 위험은 낮으나, **boundary matrix 관점 4/5 미커버**(아래 Issue #2).

### Surface 5 — compose gateway 서비스 구조 (docker-compose.yml:52-79)

- llama.cpp를 compose가 띄우지 않음(작업자 설명 일치). gateway만 서비스로, llama는 외부 endpoint.
- `LLAMA_BASE_URL: "${LLAMA_BASE_URL:-http://host.docker.internal:9080}"`(:59) — 기본 docker host의 9080, env로 override(192.168.1.29:9080 등) 가능.
- `extra_hosts: host.docker.internal:host-gateway`(:66-67) — Linux에서 host.docker.internal 해석(합리적).
- port 8001:8001, healthcheck는 `/health/live`(local-only, liveness) → Docker가 upstream 없이도 container healthy 판정(빠른 실패 회피, 합리적 설계).
- `LLAMA_TRUST_ENV: false` 기본(§165 정합).

### Surface 6 — Dockerfile (cache-friendly)

`services/llm_gateway/Dockerfile`: python:3.12-slim, requirements 먼저 복사/설치 후 소스 복사(layer cache), EXPOSE 8001, `uvicorn services.llm_gateway.app.main:app`(Dockerfile:16). application Dockerfile과 동일 패턴. ✓ requirements.txt에 fastapi/uvicorn 추가됨(diff 확인).

### Surface 7 — test 견고성 + focused 실행

`test_llm_gateway_app.py`(4 test): `FakeLLMProvider` 주입(`create_app(provider=...)`)으로 실제 llama 없이 단위 테스트.
- `test_live_health_does_not_require_llama_upstream`(:20): /health/live 200, upstream 무관 ✓
- `test_generate_calls_provider_and_returns_gateway_envelope`(:29): /v1/generate 정상 envelope + provider.requests 검증 ✓
- `test_empty_messages_are_rejected_before_provider_call`(:70): 빈 messages → 400, provider 호출 0회 ✓
- `test_provider_error_uses_stable_public_envelope`(:79): UNAVAILABLE → 503 + stable envelope ✓

```
python3 -m unittest tests.test_llm_gateway_app tests.test_llama_provider_client tests.test_httpx_transport
→ Ran 18 tests in 0.052s ... OK
```
작업자 주장 18개 통과와 일치. ✓

### Surface 8 — 숫자 재계산

전체 discover 211개 0.362초(27 skip). 기존 206 + archive follow-up(`44407a2`) + gateway app test 4개 ≈ 211. 작업자가 discover를 안 돌려 숫자를 보고하지 않았으나, 본 검증이 211개 통과로 보완.

## Issues / Risks

**차단성 finding 없음** (gateway app/compose 코드 품질 관점).

### Issue #1 (검증 방법론/provenance — 작업자 보고와 불일치)

- (a) **uncommitted**: 작업자가 "진행 완료"라 했으나 gateway 변경이 working tree에만 있음. verification은 working tree 기준으로 수행했으나, main에 반영되려면 커밋 필요.
- (b) **discover 멈춤 재현 불가**: 본 검증 환경에서 211개 0.362초 통과. 작업자가 "discover 멈춤"으로 전체 회귀를 건너뛴 것은 보수적 과잉 — 실제로는 discover 실행 가능했음. 두 이슈 모두 gateway 코드 결함이 아니라 provenance/방법론.

### Issue #2 (비차단, minor — provider error→HTTP 매핑 4/5 미커버)

`_status_for_error`(main.py:69-78)의 5종 매핑 중 UNAVAILABLE→503만 `test_llm_gateway_app`에 lock. TIMEOUT→504, OVERLOADED→429, REQUEST_REJECTED→400, INVALID_RESPONSE→502 매핑 test 없음. 단순 if-chain이라 회귀 위험 낮으나 boundary matrix 빈칸. 권고: parametrize로 5종 lock.

### Risk R1 (비차단 — /health/ready의 upstream /health 가정)

`/health/ready`(main.py:126-146)가 llama upstream의 `/health` endpoint를 가정(llama.cpp server 표준). 다른 llama 배포형태에선 path가 다를 수 있으나, 본 검증 범위 밖(실제 upstream 운영 시점). ready는 수동 점검용이고 Docker healthcheck는 live만 쓰므로 운영 영향 낮음.

### Risk R2 (비차단 — COMPOSE_BAKE panic)

작업자 보고 "기본 docker compose build gateway는 Bake 경로에서 panic → COMPOSE_BAKE=false로 우회". Docker 환경/버전 이슈로 코드 품질과 무관. 기존 환경 패턴. 비차단이나, 운영 문서에 `COMPOSE_BAKE=false` 필요성 명시 권고.

### Risk R3 (비차단 — 작업자 환경 CORE_SOT_MONGO_URI latent hang)

본 검증 추정(Surface 2): 작업자 환경에 `CORE_SOT_MONGO_URI`가 있어 `test_application_api` 첫 TestClient가 Mongo hang. 이는 gateway와 무관한 **기존 application 코드의 env 의존 latent 이슈**. test가 env 존재 시 hang하는 것 자체는 별개 추적 항목 — test runner 격리(`CORE_SOT_MONGO_URI` unset 상태에서 단위 discover) 권고.

## Verdict

**합격**.

- load-bearing 긍정: (1) gateway app(main.py)이 SoT §143-167과 전면 정합(독립 컨테이너·MongoDB/ES 비접근·trust_env=false·5 provider error 매핑·completion 응답 계약), (2) compose 구조가 작업자 설명과 일치(llama.cpp 외부 의존, LLAMA_BASE_URL override, extra_hosts, live/ready 분리 healthcheck), (3) test 4종이 FakeLLMProvider 주입으로 견고, (4) focused 18개 통과, (5) **전체 discover 211개 0.362초 통과로 discover 멈춤 보고가 재현되지 않음** — 작업자가 건너뛴 전체 회귀를 본 검증이 보완 증명.
- 차단성 코드 finding 없음. Issue #1(provenance/discover 방법론)·#2(매핑 4/5 미커버)·R1/R2/R3는 비차단.
- audit subject가 "코드"인 동시에 "작업자 검증 방법론"인 사례 — discover 멈춤 보고를 독립 재현으로 반박하고, uncommitted provenance를 명시한 점이 본 검증의 load-bearing 기여.

## Outstanding items

1. **gateway 변경 커밋 미수행**: main.py·Dockerfile·test_llm_gateway_app.py(untracked) + compose·requirements·docs(modified)가 working tree에 있음. main 반영 시 커밋 필요.
2. **작업자 환경 discover 멈춤 원인 조사**: `CORE_SOT_MONGO_URI` env 의존 hang 추정(Risk R3). 본 검증 환경에선 재현 안 됨. test runner 격리 권고.
3. Issue #2(provider error 매핑 4/5 lock) 보강 — 선택.
4. 선행 archive 검증 Issue #1 follow-up(`44407a2`) 확인 — archived project draft archive 분기 lock으로 폐쇄됨(긍정).
5. gateway compose는 llama.cpp 외부 의존이라 실제 smoke은 upstream 9080 가용 시에만 완전 — 본 검증은 app 단위 test + compose config + (작업자 보고) Docker smoke로 검증.

## Reproduction

```bash
# 1. provenance
git status                                   # gateway 변경이 uncommitted로 표시
git log --oneline bc7d1bb..HEAD              # gateway 커밋 부재

# 2. ★ discover 멈춤 재현 (본 환경에선 멈추지 않음)
timeout 90 python3 -m unittest discover -s tests   # 211, 27 skip, ~0.4s
env | grep -iE "CORE_SOT|LLAMA"                     # (빈 결과 = 멈추지 않는 이유)

# 3. focused 18개
python3 -m unittest tests.test_llm_gateway_app tests.test_llama_provider_client tests.test_httpx_transport

# 4. compose config 검증
docker compose config >/dev/null && echo OK
```
