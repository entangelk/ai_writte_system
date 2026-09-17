# 2026-09-17 Work Log

## Goals

- 배포 환경에서 관측된 분석 502와 이어쓰기 생성 실패의 발생 지점과 원인을 읽기 전용으로 확인한다.
- 애플리케이션 결함, 서버 자원 고갈, 외부 추론 제공자 장애를 증거로 구분한다.

## Completed work

### 배포 환경 분석·이어쓰기 실패 진단

- 저장소 계약과 `frontend/nginx.conf`, 분석 runner, 비동기 generation worker, LLM gateway의 오류 매핑을 대조했다.
- 배포 환경의 컨테이너 상태, application/gateway 로그, Mongo의 `analysis_jobs`·`writing_generation_jobs`·`llm_call_audits`를 읽기 전용으로 조회했다.
- 분석 run은 2026-09-17 05:11:10 UTC와 재시도한 05:16:47 UTC에 모두 외부 제공자의 429로 실패했다. gateway는 매번 API key 네 슬롯을 모두 시도한 뒤 `provider_overloaded`를 반환했고, application이 계약대로 HTTP 502로 변환했다.
- 이어쓰기 long job은 04:53:02~04:54:51 UTC에 실제 본문 생성 전 `query_planner` 단계에서 실패했다. 네 key 슬롯 모두 `provider_unavailable`이었고 gateway 최종 응답은 503, 저장된 job 사유는 `context_search_failed / llm_error: planner provider error: provider is unavailable`이었다.
- 같은 프로젝트의 다음 medium job은 04:56:56 UTC에 시작해 query planner·writing generation·writing report를 모두 통과하고 05:01:48 UTC에 성공했다. 영구 배선 오류나 요청 데이터 결함보다 외부 제공자의 시간대별 불안정이라는 판정 근거다.
- 서버는 점검 시 메모리 available 4.0 GiB, 루트 디스크 available 126 GiB였고 application·generation worker·gateway의 restart count는 모두 0, OOMKilled는 모두 false였다. 로컬 서버 자원 고갈은 원인이 아니다.
- 코드·설정·운영 데이터는 변경하지 않았다.

### 전역 Gemini 모델 폴백과 429 조합별 cooldown

- 오너가 분석뿐 아니라 이어쓰기를 포함한 모든 LLM 호출에 전역 모델 체인을 쓰기로 확정했다. 로컬 `.env`는 `LLAMA_DEFAULT_MODEL=gemini-3.5-flash-lite`, `LLAMA_MODELS=gemini-3.5-flash-lite,gemini-3.1-flash-lite`로 바꾸고 `.env.example`도 같은 운영 예시로 갱신했다.
- 새 분석 전용 env를 만들지 않았다. 기존 gateway 계약이 요청의 명시 모델을 첫 순위, `LLAMA_MODELS`를 후속 폴백으로 합성하고 중복을 제거하므로 전 호출부가 이미 같은 체인을 소비한다.
- 구현 전에 기존 정책의 모순을 발견했다. 첫 모델에서 네 key가 모두 429이면 key-global 60초 cooldown 때문에 fallback 모델 차례에는 시도 가능한 key가 0개였다. 오너에게 선택지를 제시했고 **B — LLM 429 cooldown을 `(key, model)` 조합 단위로 축소**가 확정됐다.
- `SlidingWindowRateLimiter`는 key-global cooldown(401/403)과 `(key, model)` cooldown(429)을 분리했다. RPM window는 계속 key-global이라 모델 변경으로 키당 분당 상한을 우회할 수 없다.
- 임베딩·리랭커에는 모델 폴백이 없으므로 동기 key rotation 코드는 건드리지 않았다. 패턴 스윕과 `git blame`에서 세 축의 원래 정책이 같은 2026-08-22 슬라이스에서 의도적으로 도입됐음을 확인했고, 이번 오너 결정이 LLM 축만 좁힌다는 경계를 정본에 기록했다.
- SoT v1.8.72와 기존 fallback 결정 문서·CHANGELOG를 갱신했다. HANDOFF는 완료 서술을 중복하지 않는 snapshot 규칙에 따라 변경하지 않았다.
- 회귀: 신규/수정 셀을 포함한 `tests/test_llm_fallback.py` 21 passed/7 subtests, gateway·env·HTTP 매핑·compose 관련 7파일은 **92 passed/140 subtests**.

## Issues found

| 문제 | 원인 | 해소/대응 | 결과 |
|---|---|---|---|
| 분석 탭의 HTTP 502 | 외부 LLM 제공자가 네 key 슬롯 모두에 429를 반환해 gateway가 `provider_overloaded`로 종료 | 분석 job은 실패 상태와 원인을 보존한다. 제공자 과부하가 풀린 뒤 화면의 재시도 경로 사용 | 재시도 1회까지 같은 원인으로 실패했음을 확인 |
| 이어쓰기 long 생성 실패 | 컨텍스트 검색의 query planner가 네 key 슬롯에서 모두 `provider_unavailable`; gateway 최종 503 | 실패 job의 재시도 경로 사용. 같은 시각대 후속 medium job 성공으로 배선 변경은 불필요 | 본문 생성 전 실패했으며 scratch 결과는 생성되지 않음 |
| 사용자 오류 문구의 원인 식별이 어려움 | 화면은 generation job의 `context_search_failed`를 일반 문구로 요약하고, 세부 제공자 사유는 저장하지만 표시하지 않음 | 이번 진단 범위에서는 변경하지 않음 | 운영 로그·감사 기록을 봐야 `unavailable`과 `overloaded`를 구분 가능 |
| 429에서 모델 폴백이 실행되지 않음 | cooldown이 key-global이라 첫 모델의 429가 다음 모델까지 막음 | 오너 결정 B로 LLM 429만 `(key, model)` cooldown으로 축소 | 같은 key의 fallback 모델 호출 가능, 실패 조합 재호출은 60초 차단 |

## Decisions

- 이번 요청은 원인 진단으로 한정했다. 외부 제공자 일시 장애가 증명됐고 서버·컨테이너는 정상이라 재시작, 재배포, 데이터 수정은 하지 않았다.
- HANDOFF는 변경하지 않는다. 이번 관측은 일시적인 외부 상태이며 다음 작업자의 현재 개발 방향을 바꾸는 지속 상태가 아니다.
- 최초 진단 작업에서는 제품 설계나 기능 변경이 없어 CHANGELOG를 바꾸지 않았다. 후속 폴백 구현은 계약 변경이라 별도 행을 추가했다.
- 후속 구현 결정: 분석 전용 변수를 만들지 않고 기존 전역 `LLAMA_DEFAULT_MODEL`+`LLAMA_MODELS`를 사용한다. 모든 분석·이어쓰기 call site가 같은 두 모델을 쓴다.
- 후속 오너 결정: **B** — 429 cooldown은 LLM의 `(key, model)` 조합 단위다. 키 RPM과 401/403 cooldown은 key-global로 유지한다.

## Next steps

- 사용자는 잠시 뒤 실패한 분석 job과 이어쓰기 job을 다시 시도할 수 있다.
- 같은 오류가 반복되면 gateway의 key별 `provider_overloaded`/`provider_unavailable` 빈도와 외부 제공자 상태·quota를 함께 확인한다.
- 후속 개선을 원하면 generation pad와 분석 오류 상자에 retryable 제공자 사유를 안전한 사용자 문구로 구분 노출하는 별도 UX 작업을 검토한다.
- 구현 커밋을 오너가 push한 뒤 배포 서버 소스를 동기화하고 gateway·application·generation worker를 재생성한다.
