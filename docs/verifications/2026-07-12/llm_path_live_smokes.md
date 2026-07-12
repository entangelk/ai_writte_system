# Verification — 실 LLM(12B) 경로 live 관통 4종 (full-stack, sandbox-external)

## Subject metadata

- 날짜: 2026-07-12
- 요청자: 오너 ("다음 작업 이어서 … 튜닝 부분 빼고 진행할 수 있는 걸로")
- 검증자: Claude Code (풀스택 머신 live 실행)
- 대상: HANDOFF Next Tasks가 "실 llama 12B gateway 필요"로 sandbox 밖에 남겨둔 LLM 의존 live smoke — Phase 2A provider 추출, Phase 2B.3.2 compare judge, Phase 4 planner, Phase 4 deployed context search e2e.
- 정본 스펙 참조: SoT v1.6.61 — Phase 2A(analysis 추출), Phase 2B.3(compare judge terminal-JSON), Phase 4(SearchPlan planner·Context Gate·retrieval), `docs/plans/llm-gateway.md`(Gateway 계약).
- 검증 대상 work source: `git HEAD = 5e8b077`(직전 인덱싱 live 검증 커밋 이후), working tree — **신규 코드/스크립트 없음**(4개 smoke 전부 사전 존재), 문서만 산출.
- 모델: `google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`(공식 QAT GGUF Q4_0), llama.cpp `server-cuda`, RTX 3060(10.8GB free), ctx 8192.

## Scope

실 12B 추론이 필요해 서브 머신에서 막혔던 4개 live smoke를 in-stack llama 서버(`docker-compose.llama.yml`, GPU) 위에서 관통 확인한다. 각 smoke는 계약의 wiring(gateway→llama→terminal-JSON 파싱→도메인 산출)을 검증하며, 모델 판단 품질은 별도(empirical 신호). **튜닝(프롬프트 판별 튜닝·threshold 캘리브레이션·hybrid RRF 튜닝)은 오너 지시로 이번 범위 제외** — compare judge의 J1 신호는 관찰만 기록하고 조정하지 않는다.

1. **인프라**: `docker-compose.llama.yml` override로 llama(GPU)+gateway(→llama)+application 기동.
2. **Phase 2A provider 추출**: Application→Gateway→llama 실 추출 관통.
3. **Phase 2B.3.2 compare judge**: 4 matched-pair boundary(update/add_evidence/no_change/conflict)를 실 12B로 판정, terminal-JSON 파싱.
4. **Phase 4 planner**: ContextSearchRequest→실 12B→SearchPlan(structured JSON).
5. **Phase 4 deployed e2e**: application HTTP→source-block rebuild(실 Chroma)→context-search→gateway→실 llama planner→orchestration→retrieval→Context Gate→ContextPackage.

## Methodology

풀스택 머신(Docker 28.5.1, RTX 3060). 모델은 `llama_models` 볼륨에 6.7GB 캐시(gguf+mmproj) → 재다운로드 없이 로드. smoke는 전부 worker 이미지 컨테이너 안에서 실행(정확한 의존성 + in-network DNS). compare judge/planner/provider는 `LLAMA_BASE_URL=http://llama:9080`로 llama 직접, deployed e2e는 `APPLICATION_BASE_URL=http://application:8000`.

```bash
docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d   # 전부 healthy
curl -sf http://localhost:9080/health                                    # {"status":"ok"}

docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker \
  python scripts/phase2b3_compare_judge_live_smoke.py
docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker \
  python scripts/phase4_context_search_planner_live_smoke.py
docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker \
  python scripts/phase2a_provider_live_smoke.py
docker compose run --rm --no-deps -e APPLICATION_BASE_URL=http://application:8000 worker \
  python scripts/phase4_context_search_deployed_smoke.py
```

## Findings

### 1. 인프라 — PASS

`docker compose ps` → llama·gateway·application·mongo·chroma·elasticsearch·embedding 전부 `healthy`. llama `GET /health` → `{"status":"ok"}`. 모델 캐시 로드로 llama는 up 직후 Healthy.

### 2. Phase 2A provider 추출 — PASS

exit 0, `run_http_status: 200`, `final_job.status: succeeded`, **candidates=3**(원문에서 character/event observation 추출, provenance `source_observed`). `provider_result`에 실 토큰 카운트(prompt/completion). Application→Gateway→llama 추출 wiring 실증.

### 3. Phase 2B.3.2 compare judge — PASS (wiring), J1 신호 기록

4 boundary pair **전부 `status: succeeded`**(terminal-JSON 파싱 성공, exit 0). 실 12B가 gateway(ASGITransport 인프로세스)→judge→action label 관통.

| 의도 boundary | 12B 산출 action | 일치 |
|---|---|---|
| update | conflict | ✗ |
| add_evidence | add_evidence | ✓ |
| no_change | add_evidence | ✗ |
| conflict | conflict | ✓ |

**wiring은 PASS**(4/4 terminal outcome). **J1 empirical 신호(비차단, 튜닝 대상)**: 2/4가 의도 라벨과 불일치 — `update`(단검 다룰 수 있게 됨 vs 못 다룸)를 conflict로, `no_change`(검은 머리 동의어)를 add_evidence로 과잉 판정. 프롬프트가 conflict/add_evidence 쪽으로 편향된다는 신호이며, 이는 **deferred J1 프롬프트 튜닝** 입력 데이터일 뿐 wiring 결함이 아니다(smoke의 exit 조건 = terminal outcome 도달이며 라벨 일치 아님). 오너 지시대로 튜닝은 이번 범위 밖 — 신호만 기록.

### 4. Phase 4 planner — PASS

exit 0, `status: succeeded`. 실 12B가 유효한 SearchPlan(structured JSON) 산출 — 2 step(`current_scene`/mongo, `source_quote`/vector), 각 step_id·need·tools·query 필드 완비. planner terminal-JSON wiring 실증.

### 5. Phase 4 deployed context search e2e — PASS

exit 0, `rebuild_http_status: 200`, `search_http_status: 200`.
- **rebuild**: `rebuild_backend: chroma`, `rebuild_records_written: 6` — source-block 색인이 실 Chroma에 6건 적재.
- **planner**: 실 llama가 2-step plan(mongo+vector) 산출.
- **retrieval + Gate**: `gate_decision: pass`, `macro_count: 2`, `micro_count: 6`, **`degraded: False`**(fallback/degrade 없이 완전 정상 경로).

application HTTP→rebuild(실 Chroma)→context-search→gateway 컨테이너→실 llama planner→orchestration→mongo+실 Chroma vector retrieval→Context Gate→ContextPackage 전 경로가 실 인프라 위에서 관통. degraded=False라 어떤 sub-retriever도 fallback으로 접히지 않음.

## Issues / Risks

- **wiring 결함 없음**. 4종 전부 exit 0 + 각 계약 산출물(candidates/action/SearchPlan/ContextPackage) 정상.
- **비차단 (compare judge J1 신호)**: §3 표대로 2/4 boundary가 의도 라벨과 불일치. 프롬프트 판별 품질 개선(J1)은 **튜닝 과제로 최후속**(오너 지시로 이번 제외). 이번 실행은 그 튜닝에 쓸 empirical 근거를 남김.
- **비차단 (비결정성)**: LLM 산출은 매 실행 달라질 수 있음(온도·샘플링). wiring 통과 판정(terminal outcome/HTTP 200/plan 구조)은 안정적이나, 정확한 action 라벨·plan query 문구는 재실행 시 변동 가능. 판정 신호는 구조·상태이지 문자열 동일성이 아님.
- **운영**: llama 컨테이너는 GPU 점유(≈7GB). 유휴 시 `docker compose -f docker-compose.yml -f docker-compose.llama.yml down` 또는 llama만 stop.

## Verdict

**PASS** — 실 12B 의존이라 서브 머신에서 막혔던 4개 LLM 경로 live 관통이 in-stack GPU llama 위에서 전부 wiring 확인됨(provider 추출·compare judge terminal·planner·deployed e2e). compare judge J1 프롬프트 판별 품질은 튜닝 과제로 분리(오너 지시로 이번 범위 밖), empirical 신호만 기록.

## Outstanding items

- **미커밋**: 본 검증 기록 + work_log/HANDOFF 갱신(문서만, 코드·스크립트·계약·SoT 무변). 커밋은 오너 지시 대기.
- **여전히 남은 sandbox-밖(이번 미포함)**: 2B.6 semantic threshold 실 캘리브레이션 = **튜닝(제외)**, (b-4) hybrid RRF 튜닝 = **튜닝(최후속, 제외)**, compare judge J1 프롬프트 튜닝 = **튜닝(제외)**. 비-튜닝 live 검증은 이번 배치로 소진.
- **인프라**: llama 포함 전체 스택 기동 유지(오너가 다음 작업 위해 두라 지시).

## Reproduction

위 Methodology 명령을 순서대로 실행. 통과 신호: 각 smoke exit 0 + provider `run_http_status:200`·`final_job.status:succeeded`, compare judge 4 pair `status:succeeded`, planner `status:succeeded`, deployed `rebuild/search_http_status:200`·`degraded:False`.
