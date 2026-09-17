# 2026-09-17 Work Log

## Goals

- 배포 환경에서 관측된 분석 502와 이어쓰기 생성 실패의 발생 지점과 원인을 읽기 전용으로 확인한다.
- 애플리케이션 결함, 서버 자원 고갈, 외부 추론 제공자 장애를 증거로 구분한다.
- 분석 추출 400(`source_ref_id must exactly match the source_ref catalog`)의 근본 원인인 "서버 id가 LLM 입력에 실림"을 계약 수준으로 제거한다(SoT v1.8.73).

## Completed work

### 배포 환경 분석·이어쓰기 실패 진단

- 저장소 계약과 `frontend/nginx.conf`, 분석 runner, 비동기 generation worker, LLM gateway의 오류 매핑을 대조했다.
- 배포 환경의 컨테이너 상태, application/gateway 로그, Mongo의 `analysis_jobs`·`writing_generation_jobs`·`llm_call_audits`를 읽기 전용으로 조회했다.
- 분석 run은 2026-09-17 05:11:10 UTC와 재시도한 05:16:47 UTC에 모두 외부 제공자의 429로 실패했다. gateway는 매번 API key 네 슬롯을 모두 시도한 뒤 `provider_overloaded`를 반환했고, application이 계약대로 HTTP 502로 변환했다.
- 이어쓰기 long job은 04:53:02~04:54:51 UTC에 실제 본문 생성 전 `query_planner` 단계에서 실패했다. 네 key 슬롯 모두 `provider_unavailable`이었고 gateway 최종 응답은 503, 저장된 job 사유는 `context_search_failed / llm_error: planner provider error: provider is unavailable`이었다.
- 같은 프로젝트의 다음 medium job은 04:56:56 UTC에 시작해 query planner·writing generation·writing report를 모두 통과하고 05:01:48 UTC에 성공했다. 영구 배선 오류나 요청 데이터 결함보다 외부 제공자의 시간대별 불안정이라는 판정 근거다.
- 코드·설정·운영 데이터는 변경하지 않았다.

### 전역 Gemini 모델 폴백과 429 조합별 cooldown

- 오너가 분석뿐 아니라 이어쓰기를 포함한 모든 LLM 호출에 전역 모델 체인을 쓰기로 확정했다. 후속 확인에서 기존 기본 모델도 포함한 총 3개가 의도였음이 명확해져, 로컬 `.env`는 `LLAMA_DEFAULT_MODEL=gemma-4-31b-it`, `LLAMA_MODELS=gemma-4-31b-it,gemini-3.5-flash-lite,gemini-3.1-flash-lite`로 맞추고 `.env.example`도 같은 운영 예시로 갱신했다.
- 새 분석 전용 env를 만들지 않았다. 기존 gateway 계약이 요청의 명시 모델을 첫 순위, `LLAMA_MODELS`를 후속 폴백으로 합성하고 중복을 제거하므로 전 호출부가 이미 같은 체인을 소비한다.
- 구현 전에 기존 정책의 모순을 발견했다. 첫 모델에서 네 key가 모두 429이면 key-global 60초 cooldown 때문에 fallback 모델 차례에는 시도 가능한 key가 0개였다. 오너에게 선택지를 제시했고 **B — LLM 429 cooldown을 `(key, model)` 조합 단위로 축소**가 확정됐다.
- `SlidingWindowRateLimiter`는 key-global cooldown(401/403)과 `(key, model)` cooldown(429)을 분리했다. RPM window는 계속 key-global이라 모델 변경으로 키당 분당 상한을 우회할 수 없다.
- 임베딩·리랭커에는 모델 폴백이 없으므로 동기 key rotation 코드는 건드리지 않았다. 패턴 스윕과 `git blame`에서 세 축의 원래 정책이 같은 2026-08-22 슬라이스에서 의도적으로 도입됐음을 확인했고, 이번 오너 결정이 LLM 축만 좁힌다는 경계를 정본에 기록했다.
- SoT v1.8.72와 기존 fallback 결정 문서·CHANGELOG를 갱신했다. HANDOFF는 완료 서술을 중복하지 않는 snapshot 규칙에 따라 변경하지 않았다.
- 회귀: 신규/수정 셀을 포함한 `tests/test_llm_fallback.py` 21 passed/7 subtests, gateway·env·HTTP 매핑·compose 관련 7파일은 **92 passed/140 subtests**.

### 분석 추출 프롬프트 v7 — 서버 소유 id를 LLM 경계 밖으로(쓰러진 작업 이어받기)

- **사건**: 배포 서버에서 기본 `gemma-4-31b-it`이 네 key 모두 429로 실패하고 폴백된 `gemini-3.5-flash-lite`가 응답은 했지만 255개 항목 카탈로그에 없는 24자 `source_ref_id`를 복사해, 정확 일치 검증이 `schema_invalid` 400을 반환했다(job 재시도 2회 소진). 감사 로그가 응답 본문을 저장하지 않아 잘못된 ID의 실측값은 확인 불가다.
- **오너 정정**: 최초 제안("r1/r2 짧은 별칭을 주고 서버가 변환")은 여전히 LLM에게 식별자를 다루게 하는 방식이라 기각됐다. 확정 계약 — **실제 source_ref id는 LLM 요청에 한 글자도 들어가지 않고, 모델은 카탈로그 배열의 순번만 선택한다. 실제 ID·offset·hash 조립은 전적으로 서버 소관이다.**
- **이어받기**: 앞선 작업 AI가 구현 도중 쓰러져 작업트리에 구현 일부와 테스트가 남아 있었다. 상속 시점의 집중 테스트 5파일 85 passed/25 subtests, API 묶음 129 passed/581 subtests로 구현 완결을 확인한 뒤 체크포인트 커밋(`a77fcc2`)으로 고정하고 검증을 이어갔다.
- **구현(프롬프트 v7, `analysis_extract_v7`)**: 카탈로그 렌더를 `{source_ref_index, quote}`로 축소했고 snapshot 축에서 `project_id`/`snapshot_id`/`content_hash`/`block_ids`를, advisory 보고서에서 서버 id 키 전부와 `related_context_pointers`를 제거했다(`_without_server_identifiers`). 모델 출력 앵커는 `{"source_ref_index": N}` 하나이고 파서(`_source_anchor`)가 그 순번의 카탈로그 행 `SourceRef`에서 id/span/quote/hash를 조립한다(범위 밖 순번·legacy id 앵커·5필드 앵커 거부). repair는 잘못된 원문 출력을 되보내지 않고(`invalid_content` 파라미터 제거) 정제된 본문·순번 카탈로그로 재생성한다. v6은 출시 동결본으로 seed·sha 핀 유지, `main.py`의 in-memory/Mongo 두 seed 경로에 v7을 추가했다.
- **무변 확인**: 저장되는 candidate의 `source_ref_ids`, `logical_key`(조립 앵커 기준이라 값 무변), 검토함·후보 저장·적용 API의 외부 형식은 그대로다.
- **패턴 스윕(30초 예산)**: `source_ref_id` 사용처 전수 구분 — 나머지 전부는 서버 저장/API 계약(apply·mongo·core_sot·memory·context_search 내부)이고 LLM 프롬프트로 흐르는 잔존은 없었다. writing report는 이미 번호 인용+서버 매핑(K-6=R-e), query planner·compare/identity judge는 서버 id 무사용, `writing/retrieval.py:273`의 pointer 참조는 예산 중복제거용 내부 값이다. 분석 extract가 마지막 경로였다.
- **회귀**: 집중 5파일 85 passed/25 subtests, API 묶음 129 passed/581 subtests, **전체 스위트 2939 passed/148 skipped/4274 subtests**, 문서 위생(`test_docs_indexes`·`test_product_name`·`test_service_policy_contract`) 36 passed/408 subtests.
- **배포(오너 push 후)**: 배포 서버 `main`을 `d4853057`에서 `7dbdeb04`로 fast-forward하고, 실행 중 컨테이너의 compose 구성 라벨(`docker-compose.yml` + `docker-compose.external-embedding.yml`)을 확인한 뒤 같은 조합으로 공유 앱 이미지를 재빌드했다. 이미지를 쓰는 다섯 서비스(application·admin·generation_worker·worker·withdrawal_worker)를 재생성했고, 컨테이너 내부 코드에서 `analysis_extract_v7` 확인, `/health` 200, restart count 0, 재기동 후 3분 로그에 오류 없음. 배포 Mongo `prompt_templates`에 `analysis_extract_v1`~`v7` 전량 seed를 확인했다(신규 버전이라 `PromptTemplateConflict` 없음 — 부팅 seed가 그 자체로 검증).

#### Verification(v7 슬라이스)

| 변이 | 대상 | 기대한 실패 | 결과 |
|---|---|---|---|
| 카탈로그 렌더에 `source_ref_id` 되살리기 | `services/application/app/analysis/prompt_builder.py:81`(_source_ref_payload) | `test_build_request_contains_template_snapshot_and_source_ref_catalog`, `test_v7_strips_report_pointers_and_server_source_ids`, extractor의 요청 무-ID·repair 무-ID 단정 3셀 | 5셀 재실패 후 원복 |
| 순번 0을 거부하도록 과교정(`< 0` → `<= 0`) | `services/application/app/analysis/extractor.py`(_source_anchor 경계 검사) | 정상 경로 조립 셀 전반(extractor·runner·API의 유효 순번 경로) | 16셀 재실패 후 원복 |
| 보고서 `related_context_pointers` 스트립 제거 | `services/application/app/analysis/prompt_builder.py:105` | `test_v7_strips_report_pointers_and_server_source_ids` | 1셀 재실패 후 원복 |

- 세 변이 후 `git status --short` 빈 트리(HEAD=`a77fcc2`) 확인. 상속 시점에 앞선 작업자가 "구 계약 구현이 신규 회귀에 실패함"을 이미 실측했다(신규 테스트 선행 작성).

### Verification

| 변이 | 대상 | 기대한 실패 | 결과 |
|---|---|---|---|
| 429 cooldown을 다시 key-global로 변경 | `services/llm_gateway/app/fallback.py:209` | `test_overloaded_cools_only_the_key_model_combination_short`가 fallback 모델 미호출로 실패 | 실패 확인 후 원복 |
| 429 cooldown 호출 제거 | `services/llm_gateway/app/fallback.py:209` | 같은 테스트가 실패 조합의 cooldown 부재를 검출해 실패 | 실패 확인 후 원복 |

- 두 변이 뒤 `git diff --exit-code`로 체크포인트 커밋과 바이트 단위 동일함을 확인했다.
- 사용자 정정 뒤 `docker compose config`에서 application·generation worker의 `LLM_GATEWAY_MODEL=gemma-4-31b-it`, gateway의 `LLAMA_MODELS=gemma-4-31b-it,gemini-3.5-flash-lite,gemini-3.1-flash-lite`를 확인했다.
- 최종 관련 회귀는 **92 passed/140 subtests**, 문서 인덱스·저장소 위생은 **29 passed/970 subtests**다. 문서 1차 실행에서 README의 SoT 표기가 v1.8.71로 남은 것을 검출해 v1.8.72로 동기화한 뒤 재통과했다.

### 실패 job 재시도의 영구 상한 폐지(오너 정정, SoT v1.8.74)

- **사건**: 프롬프트 v7 배포 직후 오너가 막힌 원고를 재분석하려 했으나 **409 "this job was already retried 2 times (limit 2)"**. 원인은 두 정책의 조합이다 — ① S-1 D2(2026-09-05, 오너 확정)의 job당 재시도 상한 2회, ② UI의 snapshot당 결정적 키 `analyze:<snapshotId>`(D5=A, `client.ts:1417`). 같은 snapshot의 재분석은 항상 같은 job으로 수렴하므로 초기 실행+재시도 2회를 실패로 소진한 원고는 **UI 경로로 영원히 재분석 불가**해진다. 오늘 아침 제공자 불안 40분이 세 번의 기회를 전부 태웠다.
- **오너 정정(기록된 결정의 충돌 통보와 재결정)**: S-1 D2의 상한을 오너에게 그대로 보고했고, 오너는 "재시도 상한이 영구 봉쇄를 만드는 것은 말이 안 된다 — 상한이 없어야 한다", "옵션 ②(UI 새 키 발급)뿐 아니라 ③(상한 제거)까지 하라"고 정정했다. 최초 제안했던 옵션 ①(현행 유지, 재저장으로 회피)은 기각됐다.
- **구현(상한만 폐지, 방어는 유지)**: `retry_policy.py`에서 `MAX_JOB_RETRIES`·`RetryLimitReached`를 제거하고 `analysis/service.py:retry_failed_job`·`writing/generation_job.py:mark_pending_for_retry`의 상한 검사를 지웠다(양쪽이 한 정책 — S-1의 한몸 원칙 유지). 라우터의 409 매핑 제거, `api/errors.py` 주석 갱신. **유지된 방어 셋**: 마지막 실패 후 60초 쿨다운(429+Retry-After), 재시도 입장 게이트(정지 403·소진 402), 확인된 재실행 +1 과금(8.2b G4=D). `retry_count`는 상한 없이 오르는 감사값으로 남는다. 409 선언은 계속 유효하다(non-failed 재시도의 상태충돌이 생산) — OpenAPI/`schema.d.ts` 무변.
- **②를 구현하지 않은 이유**: 상한이 사라지면 UI의 409 대체 경로(새 키 발급)는 도달 불가능한 죽은 코드가 된다. 목표(영구 봉쇄 제거)는 ③이 완전히 달성하므로 Simplicity First에 따라 넣지 않았다.
- **정직한 노출 기록**: 생성 job 재실행은 성공 시점 과금이라 실패 반복은 무과금이고(감사 §A.3의 원 우려), 이제 쿨다운·입장 게이트만 빈도를 묶는다. 분석의 확인된 재실행은 +1 과금이라 노출이 없다. SoT v1.8.74 행에 이 내용을 명시했다.
- **테스트 선행·변이**: 상한 셀 3개를 새 계약으로 먼저 재작성하고 현행 구현에서 실패(3 failed)를 확인한 뒤 구현했다. 변이 3종 — ① 분석에 상한 복원(2셀 재실패) ② 생성에 상한 복원(1셀 재실패) ③ 쿨다운 검사 제거(2셀 재실패, over-strict 방향) — 전부 원복 후 트리 클린 확인. 집중 묶음(분석 job 상태·생성 job·API·writing·quota) 301 passed/613 subtests, **전체 스위트 2939 passed/148 skipped/4274 subtests**(셀 재작성이라 총수는 기준선과 동일).
- **배포(오너 push 후)**: 배포 서버 `main`을 `2287097`로 fast-forward하고 같은 compose 조합으로 공유 앱 이미지를 재빌드, 다섯 서비스를 재생성했다. 컨테이너 내부 `retry_policy.py`에서 `MAX_JOB_RETRIES` 부재(0 매치)를 확인했고 application·admin healthy, restart count 0, `/health` 200, 재기동 후 로그 오류 0건이다.

## Issues found

| 문제 | 원인 | 해소/대응 | 결과 |
|---|---|---|---|
| 프롬프트 v7 배포 직후 재분석이 409 "already retried 2 times"로 막힘 | S-1 D2 재시도 상한 2회 × snapshot당 결정적 임팟턴시 키 조합 — 실패 3회 누적 원고가 UI에서 영구 재분석 불가 | 오너 정정으로 상한 폐지(쿨다운·입장 게이트·+1 과금 유지) | 재시도는 이제 상한 없이 항상 열림(마지막 실패 후 60초만 대기) |

| 문제 | 원인 | 해소/대응 | 결과 |
|---|---|---|---|
| 분석 탭의 HTTP 502 | 외부 LLM 제공자가 네 key 슬롯 모두에 429를 반환해 gateway가 `provider_overloaded`로 종료 | 분석 job은 실패 상태와 원인을 보존한다. 제공자 과부하가 풀린 뒤 화면의 재시도 경로 사용 | 재시도 1회까지 같은 원인으로 실패했음을 확인 |
| 이어쓰기 long 생성 실패 | 컨텍스트 검색의 query planner가 네 key 슬롯에서 모두 `provider_unavailable`; gateway 최종 503 | 실패 job의 재시도 경로 사용. 같은 시각대 후속 medium job 성공으로 배선 변경은 불필요 | 본문 생성 전 실패했으며 scratch 결과는 생성되지 않음 |
| 사용자 오류 문구의 원인 식별이 어려움 | 화면은 generation job의 `context_search_failed`를 일반 문구로 요약하고, 세부 제공자 사유는 저장하지만 표시하지 않음 | 이번 진단 범위에서는 변경하지 않음 | 운영 로그·감사 기록을 봐야 `unavailable`과 `overloaded`를 구분 가능 |
| 429에서 모델 폴백이 실행되지 않음 | cooldown이 key-global이라 첫 모델의 429가 다음 모델까지 막음 | 오너 결정 B로 LLM 429만 `(key, model)` cooldown으로 축소 | 같은 key의 fallback 모델 호출 가능, 실패 조합 재호출은 60초 차단 |
| 분석 400 "source_ref_id must exactly match the source_ref catalog" | 폴백 모델이 255개 항목 카탈로그에서 비슷한 24자 id를 복사 오류 — v6 카탈로그 렌더가 실제 id를 실어 모델에게 복사시키는 구조였음 | 프롬프트 v7로 서버 id를 LLM 경계 밖으로 이동(순번 선택+서버 조립) | 해당 job은 재시도 2회 소진으로 새 idempotency_key 재실행 필요. 배포 후 구조적으로 재발 불가 |
| 감사 로그가 LLM 응답 본문을 저장하지 않아 잘못된 id 실측 불가 | `llm_call_audits`가 응답 메타데이터만 기록 | 이번 슬라이스에서 변경하지 않음 — v7으로 원천(모델이 id를 냄)이 사라져 진단 필요성도 축소 | 본문 저장 확대는 별도 정책 결정 대상 |

## Decisions

- 이번 요청은 원인 진단으로 한정했다. 외부 제공자 일시 장애가 증명됐고 서버·컨테이너는 정상이라 재시작, 재배포, 데이터 수정은 하지 않았다.
- HANDOFF는 변경하지 않는다. 이번 관측은 일시적인 외부 상태이며 다음 작업자의 현재 개발 방향을 바꾸는 지속 상태가 아니다.
- 최초 진단 작업에서는 제품 설계나 기능 변경이 없어 CHANGELOG를 바꾸지 않았다. 후속 폴백 구현은 계약 변경이라 별도 행을 추가했다.
- 후속 구현 결정: 분석 전용 변수를 만들지 않고 기존 전역 `LLAMA_DEFAULT_MODEL`+`LLAMA_MODELS`를 사용한다. 모든 분석·이어쓰기 call site가 기존 기본 모델과 신규 폴백 두 개로 이루어진 같은 3단 체인을 쓴다.
- 후속 오너 결정: **B** — 429 cooldown은 LLM의 `(key, model)` 조합 단위다. 키 RPM과 401/403 cooldown은 key-global로 유지한다.
- 오너 정정(프롬프트 v7): **서버가 관리하는 id는 LLM 경계를 넘지 않는다.** "짧은 별칭 r1/r2를 주고 서버가 변환"하는 제안도 식별자를 모델에게 다루게 하는 방식이라 기각됐다("소스 id는 서버에서 관리가 가능한데 왜 LLM까지 들어가지"). 확정 계약: 모델은 요청 로컬 배열 순번만 선택하고 id·offset·hash 조립은 전적으로 서버가 한다.
- 오너 정정(재시도 상한, S-1 D2 폐지): **실패 job 재시도에 영구 상한이 있어서는 안 된다.** "분석 실패 2번(초기+재시도 2회)으로 원고가 영원히 분석 불가해지는 것은 말이 안 된다" — 옵션 ②(UI 새 키 발급)·③(상한 제거) 모두를 지시했다. 폐지된 것은 횟수 상한뿐이고 쿨다운 60초·입장 게이트·확인 재실행 +1 과금은 유지한다. 생성 job 축의 잔여 노출(성공 시점 과금이라 실패 재시도는 무과금 — 감사 §A.3 우려의 재개방)을 통보했으나 오너는 회복 경로 영구 봉쇄가 더 큰 결함이라고 판정했다(1인 운영 단계). ②는 ③으로 도달 불가능해져 구현하지 않았다(죽은 코드 방지).

## Next steps

- 사용자는 잠시 뒤 실패한 분석 job과 이어쓰기 job을 다시 시도할 수 있다.
- 같은 오류가 반복되면 gateway의 key별 `provider_overloaded`/`provider_unavailable` 빈도와 외부 제공자 상태·quota를 함께 확인한다.
- 후속 개선을 원하면 generation pad와 분석 오류 상자에 retryable 제공자 사유를 안전한 사용자 문구로 구분 노출하는 별도 UX 작업을 검토한다.
- 실패했던 분석·이어쓰기를 다시 실행해 실제 제공자 응답과 3단 폴백 결과를 관측한다.
- 프롬프트 v7 배포: 오너가 `main`을 push하면 배포 서버에서 fast-forward 후 공유 앱 이미지(`ai_writte_system-app`)를 재빌드하고 그 이미지를 쓰는 컨테이너(application·generation worker 등)를 재생성한다. 부팅 시 `prompt_templates`에 v7이 seed되고(신규 버전이라 conflict 없음) 어댑터 기본 조회가 v7로 넘어간다. 이어 400이 났던 snapshot을 새 `idempotency_key`로 재분석해 순번 선택 계약의 실제 응답을 관측한다.
- 재시도 상한 폐지 배포: 같은 절차로 배포한다. 배포 뒤 막혔던 원고는 **재저장 없이** 화면의 "이 원고 분석"으로 즉시 재분석된다(기존 failed job이 재시도 경로로 PENDING으로 되돌아간다 — 마지막 실패가 05:48 UTC라 쿨다운은 이미 지났다).
