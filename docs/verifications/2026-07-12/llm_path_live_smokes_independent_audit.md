# Verification — 실 LLM(12B) 경로 live 관통 4종 독립 감사 (작업자 검증 기록의 적대적 재검증)

## Subject metadata

- 날짜: 2026-07-12
- 요청자: 오너 ("다음 작업 검증해줘 … 적대적 검증과 비차단 항목까지 전부 다 해줘")
- 검증자: Claude Code (오너 지시 독립 감사 — 작업자와 다른 세션, 1차 소스 재도출 + 실 인프라 재실행)
- 대상: 작업자 커밋 `89e61f1`("test: 실 LLM(12B) 경로 live 관통 4종 검증 (튜닝 제외)") 및 그 검증 기록 `docs/verifications/2026-07-12/llm_path_live_smokes.md`(작업자 자체 검증, PASS 판정).
- 정본 스펙 참조: `docs/system-contract-sot.md` v1.6.61 — Phase 2A(analysis 추출), Phase 2B.3.2(compare judge terminal-JSON, line 417 영역), Phase 4(SearchPlan planner·Context Gate·retrieval), `docs/plans/llm-gateway.md`.
- 검증 대상 work source: `git HEAD = 89e61f1`, working tree clean. 커밋은 문서 3파일만(`HANDOFF.md`·`docs/daily_logs/2026-07-12/work_log.md`·`docs/verifications/2026-07-12/llm_path_live_smokes.md`), **신규 코드/스크립트 0**(작업자 클레임과 `git show --stat` 일치).

## Scope

작업자가 "PASS"라고 한 4개 LLM 경로 live smoke와 핵심 관찰(compare judge J1 신호)을 1차 소스(smoke 코드·계약) + 실 llama 스택 재실행으로 재도출. 특히 compare judge의 "wiring PASS, 라벨 불일치는 J1 튜닝" **분리의 정당성**을 집중 검증(가장 강한 반박 가설: smoke가 라벨을 assert한다면 2/4 불일치는 실패여야 한다).

1. **compare judge smoke exit/assert 조건 감사**(wiring vs 품질 분리).
2. **나머지 3종 smoke 구조·"실 llama" 타는 경로 감사**.
3. **4종 live 재실행**(llama·gateway·application 스택 위).
4. **(보너스) archive smoke 2단계 확장 클레임 확인** — work_log가 전회 독립 감사의 PROJECT_ARCHIVED 빈 셀 지적을 닫았다고 주장.
5. **회귀 749 passed 재확인**.

## Methodology

풀스택 머신(Docker 28.5.1, RTX 3060). 작업자가 기동해 둔 8컨테이너(`mongo`·`chroma`·`elasticsearch`·`embedding`·`gateway`·`llama`·`application`·`worker`, 전부 healthy) 재사용. smoke는 worker 이미지(v1.6.61) 컨테이너 안에서 실행. provider/planner/compare judge는 `-e LLAMA_BASE_URL=http://llama:9080`, deployed e2e는 `-e APPLICATION_BASE_URL=http://application:8000`.

```bash
# 회귀
python3 -m pytest -q --ignore=tests/test_memory_mongo.py

# 4종 live smoke 재실행 (작업자 기록의 명령과 동일)
docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker python scripts/phase2a_provider_live_smoke.py
docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker python scripts/phase4_context_search_planner_live_smoke.py
docker compose run --rm --no-deps -e LLAMA_BASE_URL=http://llama:9080 worker python scripts/phase2b3_compare_judge_live_smoke.py
docker compose run --rm --no-deps -e APPLICATION_BASE_URL=http://application:8000 worker python scripts/phase4_context_search_deployed_smoke.py

# archive 2단계 확장 클레임 확인
grep -n "PROJECT_ARCHIVED\|DRAFT_ARCHIVED\|enqueue_project_archived" scripts/phase3b_archive_chroma_live_smoke.py
```

## Findings

### 1. compare judge "wiring vs 품질" 분리 — smoke 설계와 1:1 (반박 가설 기각)

가장 강한 반박 가설: "smoke가 라벨 일치를 assert한다면, 4 boundary 중 2개 불일치는 smoke 실패여야 하는데 작업자가 '전부 succeeded'라 했다 → 모순이거나 회피다."

코드 대조(`scripts/phase2b3_compare_judge_live_smoke.py`):
- **line 116-121**: `_BOUNDARY_PAIRS` 주석 — "These are smoke **INPUTS, not assertions**: the run prints whichever action the 12B actually picks, giving empirical signal on whether the prompt distinguishes the boundaries (the J1 follow-up the slice deferred)."
- **line 9 (docstring)**: "giving empirical signal on whether the prompt distinguishes the boundaries (the J1 follow-up the slice deferred)."
- **line 204-208**: exit 조건 — `ok = all(entry["status"] in {"succeeded", "invalid"} ...); return 0 if ok else 1`. 주석: "Exit 0 only when every pair reached a terminal judge outcome (succeeded or an invalid/bad-JSON result after repair). A provider_error on any pair means the Gateway/llama.cpp wiring is down → non-zero."

결론: smoke는 **애초에 라벨 정확도를 assert하지 않음**. exit 조건은 "wiring이 terminal outcome(succeeded/invalid)에 도달했는가"이며, provider_error(파이프라인 다운)만 실패. 작업자의 "wiring PASS, 라벨 불일치는 J1 튜닝" 분리는 회피가 아니라 **smoke 원래 설계와 정확히 일치**. 반박 가설 기각.

### 2. "실 llama 12B" 관통 경로 — 4종 전부 real llama

- **compare judge / provider / planner smoke**: `create_gateway_app(provider=LlamaCppProvider(transport=HttpxJsonTransport(base_url=llama:9080), ...))` + `httpx.ASGITransport(app=gateway_app)`. gateway **로직**은 인프로세스 ASGI로 돌리되, gateway가 호출하는 `LlamaCppProvider`의 transport는 `HttpxJsonTransport(base_url=http://llama:9080)` = **실 llama 컨테이너**. 작업자 기록 §3 "gateway(ASGITransport 인프로세스)→judge" 표현 정확(gateway 코드 인프로세스, llama 추론 real).
- **deployed e2e smoke**: `APPLICATION_BASE_URL=http://application:8000` HTTP 호출 → application 컨테이너 내부 배선의 gateway → real llama. 완전 배포 경로.

두 패턴 모두 실 12B 추론(`google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0`) 관통. 작업자 "실 12B" 클레임 정당.

### 3. 4종 live 재실행 — 전부 PASS 재현

| Smoke | exit | 핵심 결과(독립 취득) | 작업자 기록과 일치 |
|---|---|---|---|
| Phase 2A provider | 0 | `status:succeeded`, candidates=3(민아/파란 편지/준호 source_refs), HTTP 200 | 일치 |
| Phase 4 planner | 0 | `status:succeeded`, 2-step SearchPlan(current_scene/mongo + source_quote/vector, 각 step_id·need·tools·query 완비) | 일치 |
| 2B.3.2 compare judge | 0 | 4 pair 전부 `status:succeeded`(terminal) → wiring PASS | 일치(terminal 측면) |
| Phase 4 deployed e2e | 0 | `{rebuild:200, records_written:6, backend:chroma, search:200, gate:pass, degraded:False, macro:2, micro:6}` | **전 필드 완전 일치** |

### 4. compare judge 비결정성 실증 — 작업자 "J1 신호 + 라벨 변동" 클레임 정확

| 의도 boundary | 작업자 실행 산출 | 감자(본 검증) 실행 산출 | 패턴 |
|---|---|---|---|
| update | conflict | conflict | **체계적 과잉**(2/2 일관) |
| add_evidence | add_evidence | add_evidence | 정확 |
| no_change | add_evidence | **no_change** | 변동(샘플링) |
| conflict | conflict | conflict | 정확 |

- `update`(단검 숙련도 획득 vs 미숙)이 양쪽 실행 모두 `conflict`로 판정 → 비결정적 변동이 아니라 **프롬프트의 체계적 편향**("과거 기록과 다르면 conflict" 쪽). 이것은 J1 프롬프트 튜닝의 핵심 입력 데이터.
- `no_change`(검은 머리 동의어)가 실행마다 `add_evidence`/`no_change`로 변동 → 샘플링 의존 경계 케이스.
- 작업자 기록 §Issues(line 81) "LLM 산출은 매 실행 달라질 수 있음(온도·샘플링) ... 정확한 action 라벨은 재실행 시 변동 가능" 클레임이 본 재실행으로 실증됨. wiring 통과 판정(terminal outcome)은 안정적.

### 5. (보너스) archive smoke 2단계 확장 — 작업자 클레임 정확, 전회 감사 빈 셀 닫힘

전회 독립 감사(`indexing_live_smokes_independent_audit.md` §1 boundary matrix)가 "PROJECT_ARCHIVED(project 전체 delete) 분기는 live smoke가 안 탐 — `_archive_where` 코드와 회귀에 의존"을 비차단 관찰로 남겼음. work_log(line 57)가 이것을 "PROJECT_ARCHIVED live gap 닫음 — smoke 2단계 확장"으로 닫았다고 주장.

코드 대조(`scripts/phase3b_archive_chroma_live_smoke.py`, 177줄 = 전회 153줄에서 +24):
- **line 130-133 (Phase 1)**: DRAFT_ARCHIVED — project-scoped draft narrowing.
- **line 140-143 (Phase 2)**: `outbox.enqueue_project_archived(project_id=project_id)` — 주석 "whole-project wipe. Every remaining derived record ... **closes the PROJECT_ARCHIVED branch of `_archive_where` that DRAFT_ARCHIVED alone does not exercise live**."
- **line 159-161**: `project_archived_worker_succeeded`, `remaining_after_draft_archived`, `remaining_after_project_archived` 보고.

작업자 클레임 정확. 전회 감사의 빈 셀(회귀 의존)이 **live 검증으로 승격**됨. 검증→작업→재검증 피드백 루프가 건강하게 닫혔음을 확인. (본 smoke는 `5e8b077`에 이미 반영됐고, `89e61f1` 범위 밖이지만 감사 무결성 차원에서 확인.)

### 6. 회귀 — 독립 재확인

`python3 -m pytest -q --ignore=tests/test_memory_mongo.py` → **749 passed, 48 skipped, 99 subtests passed in 12.38s**. 신규 코드 0이므로 종전과 동일.

## Issues / Risks

- **결함 없음**. 4종 PASS·관찰(J1 신호)·"신규 코드 0"·회귀 749 전부 독립 재현.
- **비차단 (gateway 컨테이너 관통 편중)**: provider/planner/compare judge smoke는 gateway를 컨테이너가 아닌 인프로세스 ASGI로 돌림. gateway **컨테이너 배포 헬스/배선** 관통은 deployed e2e smoke 하나에만 의존. gateway 코드 자체는 동일하므로 기능 검증은 되나, gateway 컨테이너 자체의 live 건전성이 단일 smoke에 집중. (운영상 마이너)
- **비차단 (compare judge 라벨 품질 live 검증 부재)**: smoke가 라벨을 assert하지 않으므로(setup 의도), "프롬프트가 4 boundary를 올바로 구분하는가"는 live smoke로 영원히 검증 안 됨. update→conflict 체계적 편향이 프로덕션 compare 경로(Phase 6 candidate review 통합 시)에 영향할 수 있으나, 현재는 J1 튜닝 과제로 명시적 연기됨. J1 튜닝 시 **별도 deterministic 벤치마크**(fake provider 회귀가 잠근 라벨 + real llama 정확도 측정)가 필요 — live smoke만으로는 부족.
- **비차단 (비결정성)**: 본 감자 실행의 compare judge no_change 결과가 작업자 실행과 다름(샘플링). wiring 판정은 안정적이나, 정확한 라벨/plan query 문구는 재실행마다 변동. 판정 신호는 구조·상태지 문자열 동일성 아님.

## Verdict

**PASS**. 작업자의 "실 LLM(12B) 경로 live 관통 4종 PASS" 판정은 독립 재실행(4종 전부 exit 0 + JSON 필드 재현, deployed e2e는 전 필드 완전 일치)·코드 감사(compare judge exit 조건 = terminal outcome, 라벨은 INPUTS not assertions)·비결정성 실증(update→conflict 체계적 편향 + no_change 변동)으로 전면 확인됨.

가장 공격한 의심점(compare judge wiring/품질 분리가 회피인가)은 smoke 설계 자체(line 9, 116-121, 204-208)가 작업자 주장과 1:1로 기각. 추가로, 전회 감사의 비차단 관찰(PROJECT_ARCHIVED live gap)이 작업자에 의해 실제로 닫혔음을 확인(검증 루프 건강). "신규 코드/스크립트 0" 클레임도 `git show --stat`으로 확인(문서 3파일만).

## Outstanding items

- **커밋 완료**: 본 검증 대상은 `89e61f1`로 이미 커밋됨(오너 커밋). working tree clean.
- **인프라**: llama 포함 8컨테이너 기동 유지 중(오너 지시). 정리 시 `docker compose -f docker-compose.yml -f docker-compose.llama.yml down`.
- **여전히 sandbox-밖 잔여(전부 튜닝, 최후속)**: 2B.6 semantic threshold 캘리브레이션, (b-4) hybrid RRF 튜닝, compare judge J1 프롬프트 튜닝 — 본 감사 범위 밖. 비-튜닝 live 검증 배치는 인덱싱 4종(1차) + LLM 4종(2차)으로 소진됨.

## Reproduction

```bash
docker compose -f docker-compose.yml -f docker-compose.llama.yml up -d   # 8컨테이너 healthy 대기
curl -sf http://localhost:9080/health                                      # {"status":"ok"}
python3 -m pytest -q --ignore=tests/test_memory_mongo.py                   # 749 passed / 48 skipped
# 4종 live smoke (위 Methodology 블록 명령)
```
통과 신호: provider `run_http_status:200`·`final_job.status:succeeded`·candidates=3, planner `status:succeeded` + step 구조, compare judge 4 pair `status∈{succeeded,invalid}` + exit 0, deployed `{rebuild:200, search:200, gate:pass, degraded:False, macro:2, micro:6}`.

## 보강 반영 (2026-07-12 후속, 작업자)

오너 지시에 따라 본 감사의 비차단 관찰을 반영. 1차로 검증 기록 문서에 정밀화했고, 이후 오너 재지시("문서 말고 실제 코드/테스트를 보강")에 따라 **#1은 신규 smoke로 실제 코드 보강**했다.

1. **비차단 #1 (gateway 컨테이너 관통 편중) → 코드 보강**: 검증 기록 §5/Issues 명시에 더해 `scripts/gateway_generate_live_smoke.py` 신규 — gateway 컨테이너 `GET /health` + `POST /v1/generate`를 직접 POST해 계약 응답(text·finish_reason·usage) assert(실행 PASS: `ok:true`, usage 28 tokens). deployed e2e에만 의존하던 gateway 컨테이너 HTTP 커버리지를 격리 smoke로 보강.
2. **비차단 #2 (compare judge 라벨 품질 live 미검증)** — §3 "범위 한계" + Issues #2에 "smoke가 라벨 assert 안 함 → 프롬프트 판별 정확도는 live smoke로 영원히 미검증, J1은 별도 deterministic 벤치마크(fake 회귀 라벨 + real 정확도) 선행 필요" 명시.
3. **비차단 #3 (비결정성)** — §3 "비결정성 정밀화"에 감사 재실행 결과 반영: `update`→conflict 2회 일관(체계적 편향, J1 우선 타깃), `no_change` 변동(샘플링). wiring 판정은 안정.

이전 인덱싱 감사 때와 동일한 검증→작업→재검증 루프 유지. J1 튜닝 배치 착수 시 #2의 "deterministic 벤치마크 설계"를 브리프에 포함할 것.
