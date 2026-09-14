# 관측성 Slice — `finish_reason` 기반 repair 연쇄 측정

상태: **Draft — 오너 결정 필요**  
작성: 2026-09-14  
상위 계약: [`../system-contract-sot.md`](../system-contract-sot.md) §LLM 파이프라인 관측(KPI) · 기존 호출 감사 [`observability-kpi-decisions.md`](observability-kpi-decisions.md) · 호출부 매핑 [`observability-site-mapping-decisions.md`](observability-site-mapping-decisions.md)

## 배경과 목표

다섯 JSON/구조화 응답 파서(`analysis/extractor.py`, `analysis/compare_judge.py`,
`analysis/identity_judge.py`, `analysis/planner.py`, `writing/retrieval.py`)는 최초
응답이 파싱에 실패하면 한 번 repair를 호출한다. 최초 응답의
`finish_reason == "length"`는 같은 출력 상한에서 재호출해도 다시 잘릴 수 있어
비용·지연만 소비할 위험이 있다.

현재 `StoredLlmCall`은 호출부·상관 ID·결과·토큰·지연·오류를 감사하지만,
`finish_reason`, repair 시도 여부, 부모 호출과의 관계가 없다. 따라서 운영 데이터로
"length 뒤 repair가 얼마나 실행됐고, 실제로 몇 번 회복됐는가"를 판정할 수 없다.

이 슬라이스의 목표는 **정책을 즉시 바꾸는 것**이 아니라, 원고·프롬프트·AI 응답 본문을
저장하지 않고 repair 효율을 판정할 최소 관측 계약을 시행하는 것이다.

## Decision needed

기존 per-call 감사 레코드에 repair 연쇄 메타데이터를 확장할지, 별도 관측 저장소를
만들지 결정해야 한다. 이 선택은 Mongo 스키마·기존 KPI read-model·운영 조회 경로를
정하므로 코드에서 추론할 수 없다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 기존 호출 감사 확장 | `StoredLlmCall`에 종료 사유·시도 번호·부모 호출 ID를 선택 필드로 추가하고 기존 감사 경로에서 기록 | 기존 per-project/전역 조회와 보존 정책을 재사용, 호출별 토큰·지연과 바로 결합, 별도 저장소/권한 경계 없음 | 감사 레코드·Mongo adapter·기존 fixture의 선택 필드 이행 필요 |
| B. 별도 repair 연쇄 원장 | 최초 파싱 실패마다 별도 repair-chain 행을 쓰고 호출 감사는 그대로 둠 | 연쇄 집계 모양을 독립적으로 설계 가능 | 같은 사실이 두 저장소에 중복되고 토큰/지연 조인이 필요, 새 API·보존·권한 계약이 생김 |
| C. 구조화 로그만 | 애플리케이션 로그에 메타데이터만 남기고 영속 KPI는 만들지 않음 | 변경량이 가장 작고 즉시 관찰 가능 | 로그 보존/검색 환경에 의존, 프로젝트별·전역 추세와 비용 회복률을 신뢰성 있게 집계할 수 없음 |

**추천: A. 기존 호출 감사 확장.** 현재 단계는 로컬 1인 dogfood 직전이며, 이미 9개
호출부의 감사·KPI·프로젝트/전역 권한 경계가 존재한다. repair는 독립 업무가 아니라 그
호출 중 일부이므로 별도 원장을 만들면 같은 호출 비용의 정본이 둘이 된다.

## 선택 A의 시행 계약

오너가 A를 확정하면 다음 필드를 **모두 nullable/후행 호환**으로 `StoredLlmCall`과
Mongo 저장 형식에 추가한다. 과거 행의 `None`은 "모름"이며 `stop`이나 0으로 채우지
않는다.

| 필드 | 값 | 목적 |
|---|---|---|
| `finish_reason` | gateway가 돌려준 원문 리터럴 또는 `None` | 최초/repair 응답이 `length`였는지 판정 |
| `repair_attempt` | `0`=최초 호출, `1`=첫 repair, `None`=repair 개념이 없는 호출 | 같은 site의 정상 독립 호출과 repair를 분리 |
| `repair_parent_call_id` | repair 행만 최초 호출의 audit ID, 아니면 `None` | 동일 `correlation_id` 안의 여러 호출을 정확히 연결 |

`repair_attempt=0`은 repair를 지원하는 다섯 경로의 최초 provider 호출에만 기록한다.
repair가 없는 호출은 억지로 0을 쓰지 않고 `None`으로 남긴다. repair 응답은
`repair_attempt=1`과 부모 ID를 기록한다. 한 번 repair 계약이므로 2 이상은 이번
슬라이스 범위 밖이며, 나중에 다회 repair가 생기면 그때 확장한다.

파싱 결과의 감사 의미도 고정한다.

- 최초 응답이 파싱 실패해 repair로 넘어가면 최초 행은 `PARSE_ERROR`다. provider 호출은
  성공했더라도 이 제품이 그 출력을 거부했음을 나타낸다.
- repair가 파싱을 통과하면 repair 행은 `SUCCESS`; 다시 거부되거나 provider 오류면 해당
  행의 실제 terminal outcome을 기록한다.
- `finish_reason`은 provider가 알려 준 경우에만 기록한다. 예외로 응답 자체를 못 받은
  `PROVIDER_ERROR`에는 `None`이 맞다.
- 감사 레코드에는 원고, 프롬프트, `content`, parser 오류 원문, API 키를 넣지 않는다.

## 측정과 정책 개방 기준

기존 KPI read-model 또는 그와 같은 읽기 경로에 다음 파생 집계를 추가한다. 원시 행을
고치는 것이 아니라 조회 시 접는다.

| 지표 | 정의 |
|---|---|
| `length_repair_attempts` | 최초 행이 `finish_reason=length`이고 repair 행이 존재하는 수 |
| `length_repair_recoveries` | 위 repair 행이 `SUCCESS`인 수 |
| `length_repair_recovery_rate` | recoveries / attempts; attempts=0이면 `None` |
| `length_repair_tokens`·`latency_ms` | 위 repair 행의 사용량 합계; provider가 모르면 기존 `None` 의미를 유지 |

각 지표는 call site별, 프로젝트별, 전역 관리자별로 같은 `_fold` 경로에서 계산한다.
화면 추가는 이 슬라이스 범위 밖이다. 기존 관리자/프로젝트 KPI 응답에 후행 선택 필드로
노출할지, 내부 저장 관측 후 다음 read-out 슬라이스로 미룰지는 A 확정과 함께 정한다.

정책 변경(`finish_reason=length`면 repair 건너뜀)은 **이 슬라이스에서 금지**한다.
최소 20회의 `length_repair_attempts` 또는 14일 관찰 중 먼저 충족하는 시점에 아래를
판정 근거로 다음 결정 브리프를 연다.

- 회복률과 절대 회복 건수
- site별 repair 토큰·지연 비용
- `length` 외 파싱 실패 repair의 회복률(정상 repair를 과잉 차단하지 않기 위함)
- provider/model 변경 여부와 표본 기간

표본이 작거나 회복 사례가 의미 있게 있으면 정책은 유지한다. `length` 뒤 회복률이
낮고 비용이 확인되면, 해당 site에만 `length` repair 단락을 제안한다. 다섯 경로를
일괄 변경하지 않는다.

## 구현 순서와 소유 경계

1. **결정 기록** — 오너가 A/B/C를 확정한다. A가 아니면 이 문서의 필드·검증 절은
   적용하지 않고 선택지에 맞는 별도 후속을 만든다.
2. **스키마·저장소** — A일 때 `llm_call_audit.py`의 도메인 모델, Mongo/in-memory
   adapter, 직렬화 fixture를 nullable 필드로 이행한다. 기존 행·기존 fixture가
   무변으로 읽히는 회귀를 먼저 만든다.
3. **계측 seam** — `ObservedProvider`/`llm_call_scope`가 provider 응답의
   `finish_reason`과 call audit ID를 전달할 수 있게 최소 확장한다. audit 쓰기 실패가
   요청 결과를 바꾸지 않는 기존 `finally` 격리는 유지한다.
4. **다섯 repair 경로 배선** — 최초 호출과 repair 호출을 위 계약으로 기록한다.
   `analysis/extractor.py`, `analysis/compare_judge.py`, `analysis/identity_judge.py`,
   `analysis/planner.py`, `writing/retrieval.py`만 대상이다.
5. **집계** — `_fold` 한 곳에서 프로젝트·전역이 같은 정의를 사용하게 한다. 공개
   응답을 넓히면 schema 생성물·`responses=`·프런트 타입도 같은 변경에서 갱신한다.
6. **문서 승격** — 시행된 필드와 결정값을 SoT의 LLM 관측 절·버전 행에 옮기고, 이
   브리프 상태를 Resolved로 바꾼다.

## 검증 완료 기준

- 기존 레코드(새 필드 없음)를 읽어도 집계·API가 실패하지 않는다.
- 각 다섯 경로에서 `length → repair 성공`, `length → repair 재파싱 실패`,
  `stop → repair 성공`을 fixture provider로 재현한다. 본문을 저장하지 않는 것도
  저장 어댑터 단정으로 확인한다.
- 첫 호출과 repair가 같은 `correlation_id`이되 `repair_parent_call_id`로 정확히
  연결되고, 독립된 같은-site 호출과 섞이지 않는다.
- `_fold`의 프로젝트/전역 집계가 같은 원시 행에서 같은 site별 수치를 낸다.
- 양방향 변이: (under) `length`의 finish reason 또는 parent link 기록을 제거하면
  연쇄 집계 셀이 실패한다. (over) `stop` repair까지 `length` 비용으로 세거나
  `finish_reason=None`을 `length`로 취급하면 정상 repair/미상 응답 셀이 실패한다.
- 관련 backend 집중 테스트, 문서 인덱스·hygiene, 변경된 공개 계약이면 schema/프런트
  테스트를 실행한다. 이후 독립 검증자가 mutation으로 승격 재검한다.

## Follow-up considerations

- 다회 repair 또는 retry/backoff가 도입되면 `repair_attempt`의 2 이상과 직접 부모
  연결을 다시 설계한다. 지금의 "한 번" 가정에 맞춰 미리 일반화하지 않는다.
- 이 지표가 운영 화면의 시간 범위·페이지네이션 요구를 만들면 Phase 9 F1의 트리거와
  함께 화면 확장을 연다.
- 분석 worker가 실제로 durable audit store에 쓰는지 배포 뒤 `correlation_id` 기준으로
  확인한다. scope 밖 script/diagnostic은 기존 계약대로 계속 제외한다.

## Deferred / out of scope

- `finish_reason=length`에서 repair를 즉시 건너뛰는 정책 변경.
- 원고/프롬프트/AI 응답 본문 또는 parser 오류 전문의 저장·로그 기록.
- 새 모니터링 벤더, 알림, 대시보드 화면, 보존 기간 변경.
- repair가 아닌 일반 provider 재시도·quota 정책 변경.
