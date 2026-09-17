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

## Issues found

| 문제 | 원인 | 해소/대응 | 결과 |
|---|---|---|---|
| 분석 탭의 HTTP 502 | 외부 LLM 제공자가 네 key 슬롯 모두에 429를 반환해 gateway가 `provider_overloaded`로 종료 | 분석 job은 실패 상태와 원인을 보존한다. 제공자 과부하가 풀린 뒤 화면의 재시도 경로 사용 | 재시도 1회까지 같은 원인으로 실패했음을 확인 |
| 이어쓰기 long 생성 실패 | 컨텍스트 검색의 query planner가 네 key 슬롯에서 모두 `provider_unavailable`; gateway 최종 503 | 실패 job의 재시도 경로 사용. 같은 시각대 후속 medium job 성공으로 배선 변경은 불필요 | 본문 생성 전 실패했으며 scratch 결과는 생성되지 않음 |
| 사용자 오류 문구의 원인 식별이 어려움 | 화면은 generation job의 `context_search_failed`를 일반 문구로 요약하고, 세부 제공자 사유는 저장하지만 표시하지 않음 | 이번 진단 범위에서는 변경하지 않음 | 운영 로그·감사 기록을 봐야 `unavailable`과 `overloaded`를 구분 가능 |

## Decisions

- 이번 요청은 원인 진단으로 한정했다. 외부 제공자 일시 장애가 증명됐고 서버·컨테이너는 정상이라 재시작, 재배포, 데이터 수정은 하지 않았다.
- HANDOFF는 변경하지 않는다. 이번 관측은 일시적인 외부 상태이며 다음 작업자의 현재 개발 방향을 바꾸는 지속 상태가 아니다.
- CHANGELOG는 변경하지 않는다. 제품 설계나 기능 변경이 없다.

## Next steps

- 사용자는 잠시 뒤 실패한 분석 job과 이어쓰기 job을 다시 시도할 수 있다.
- 같은 오류가 반복되면 gateway의 key별 `provider_overloaded`/`provider_unavailable` 빈도와 외부 제공자 상태·quota를 함께 확인한다.
- 후속 개선을 원하면 generation pad와 분석 오류 상자에 retryable 제공자 사유를 안전한 사용자 문구로 구분 노출하는 별도 UX 작업을 검토한다.
