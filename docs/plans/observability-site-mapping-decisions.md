# 관측 KPI 증분 C — site 매핑 · scope 개방 범위 결정 브리프

상태: `Approved — 2026-07-26 (오너 결정: D1 분리 · D2 신규 리터럴 2개 · D3 전 경로+worker · D4 재분류)` · 구현: SoT v1.7.47
관련: `observability-kpi-decisions.md`(승인 D1=B·D2=C·D3=A·D4=A), `observability-instrumentation-seam-decisions.md`(승인 C안), SoT v1.7.46 §"LLM 파이프라인 관측(KPI)"

## Decision needed

증분 C의 대상은 HANDOFF·SoT에 **`compare_judge`·`query_planner`·`writing_generation` 3개**로 적혀 있다. 착수 전 실측 결과 그 3개가 **실제 코드 구조와 1:1로 대응하지 않는다**:

1. **`call_site` 리터럴은 5개인데 실제 LLM 어댑터는 8개다.** `query_planner` 한 리터럴에 대응하는 planner가 **둘**이고, writing loop의 **reviser·reporter 호출은 어느 리터럴에도 매핑돼 있지 않다**.
2. **provider를 감싸는 것만으로는 레코드가 생기지 않는다.** 레코드는 `llm_call_scope`가 열린 요청 경로에서만 만들어지는데, 지금 scope를 여는 곳은 **`main.py:2602`(analysis run)·`main.py:3780`(gate) 두 곳뿐**이다. 나머지 워크플로 — 특히 주력인 revise-and-gate loop — 는 provider를 감싸도 **레코드 0건**이 된다(HANDOFF가 경고한 "조용한 0건" 그 자체).

이 둘은 계약 리터럴과 집계 의미론을 정하는 문제라 임의로 고르면 오너를 선택하지 않은 경로에 묶는다. 기존 계약은 "새 호출부는 새 멤버로 추가하며 스키마 변경이 아니다"까지만 말하고, **어느 어댑터가 어느 멤버인지는 침묵**한다.

### 실측한 어댑터 ↔ 리터럴 대응표

| # | LLM 어댑터 | 조립 지점 | 호출 구조 | 현 리터럴 |
|---|---|---|---|---|
| 1 | `TerminalJsonSearchPlanner` (context search) | `main.py:838` | 1회 + 비-JSON 시 repair 1회 (`planner.py:113-116`) | `query_planner`? |
| 2 | `TerminalJsonWritingRetrievalPlanner` (revise loop) | `main.py:1872` | loop 내부, retrieval round당 1회 (`revise_gate.py:463`) | `query_planner`? |
| 3 | `TerminalJsonCompareJudge` | `main.py:630` | **matched pair당 1회 + repair 1회** (`compare_judge.py:112,116`) | `compare_judge` ✅ |
| 4 | `WritingService`(generate) | `main.py:670` | 요청당 1회 (`service.py:111`) | `writing_generation` ✅ |
| 5 | `WritingCandidateReportService` | `main.py:675`(writing 내부, #4와 **동일 인스턴스**) · `main.py:1822`(loop용 별도) | generate 뒤 1회 + loop마다 재호출 | **없음** |
| 6 | `WritingRevisionService` | `main.py:1828` | loop의 revision round당 1회 (`revise_gate.py:362,407`) | **없음** |
| 7 | `WritingGateService` | `main.py:729` | 이행 완료(v1.7.45) | `writing_gate` ✅ |
| 8 | `VersionedPromptAnalysisExtractionAdapter` | `main.py:600` | 이행 완료(v1.7.43) | `analysis_extractor` ✅ |

`#5`의 첫 조립 지점은 `#4`와 **같은 provider 인스턴스를 공유**한다(`_build_report_service(provider)`). 즉 `#4`를 감싸면 report 호출도 자동으로 같은 `call_site`를 달고 들어온다 — 리터럴을 분리하려면 이 조립을 손대야 한다.

### 실측한 scope 개방 갭

`build_context_package`를 부르는 요청 경로는 **7곳**(`/context-search`·`/writing/generate`·`/writing/gate`·`/writing/report`·`/writing/revise`·`/writing/revise-and-gate`·`/writing/accept`)인데 scope를 여는 곳은 gate 하나다. 그리고 **revise-and-gate loop 안의 gate 호출은 지금도 기록되지 않는다** — `writing_gate` site의 현재 레코드는 독립 `/writing/gate` endpoint 호출만이다.

async 생성 worker(medium/long preset)는 `job.project_id`·`job.request_id`를 **실제로 갖고 있다** — "추측한 project_id" 문제가 없는 유일한 scope 밖 경로다. 여기를 열지 않으면 **긴 생성(비싼 호출)이 KPI에서 통째로 빠진다.**

## D1 — planner 두 개를 한 리터럴로 묶을 것인가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 분리** (추천) | context planner = `query_planner`, writing retrieval planner = 신규 `writing_retrieval_planner` | 서로 다른 프롬프트·`max_tokens`·실패 경로를 가진 두 서브시스템을 집계에서 구분 · 실패 급증 시 어느 쪽인지 바로 보임 | 리터럴 1개 추가(계약이 이미 허용) |
| B. 통합 | 둘 다 `query_planner` | 리터럴 무변, 지금 가장 작음 | **되돌릴 수 없다** — 나중에 분리해도 과거 레코드는 이미 뭉개져 있어 소급 복원 불가 |

## D2 — reviser·reporter 호출을 어떻게 매핑할 것인가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 신규 리터럴 2개** (추천) | `writing_revision`·`writing_report` 추가 | 생성/수정/자기보고가 토큰·지연·실패율에서 분리됨(loop 비용의 대부분이 어디인지가 바로 KPI로 나옴) | 리터럴 2개 추가 · `#5` 조립 분리 필요 |
| B. `writing_generation`에 통합 | 세 호출을 한 site로 | 리터럴 무변 | 한 워크플로에 3종 호출이 섞여 "생성이 비싼가 report가 비싼가"를 영영 못 가른다 |
| C. 이번 증분 제외 | reviser·reporter 미계측 유지 | 슬라이스 최소 | **loop 토큰 합계가 조용히 불완전해진다** — 집계가 실제보다 적게 나오는데 그 사실이 레코드에 안 남는다 |

## D3 — scope를 어디까지 열 것인가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. LLM을 부르는 전 경로 + async worker** (추천) | 위 7개 endpoint + 생성 worker + compare endpoint | KPI가 실제 파이프라인을 덮는다 · worker는 실 project_id/job_id를 가져 추측 없음 | 슬라이스가 커진다(배선 회귀도 경로마다 필요) |
| B. 동기 endpoint만 | worker 제외 | 작음 | **medium/long 생성이 KPI에서 통째로 누락** — 오너가 보려는 비싼 호출이 바로 그것 |
| C. 최소(compare·context-search·generate) | 3 site 문자 그대로 | 가장 작음 | 주력 워크플로(revise-and-gate)가 레코드 0건 — 집계 API를 켜도 볼 것이 거의 없다 |

## D4 — repair 구조 site의 terminal parse 실패를 재분류할 것인가

`compare_judge`·context planner는 extractor와 **같은 구조**(본 호출 + repair)이고, repair까지 실패하면 도메인이 최종 거부한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| **A. 마지막 호출만 `parse_error`로 재분류** (추천) | gate 방식. `annotate_last`가 **repair 호출 1건만** 건드리므로 회수된 첫 호출은 `success` 유지 | SoT의 `parse_error` 정의("도메인이 끝내 거부한 호출")와 일치 · repair 빈도 지표 무손상 | extractor(v1.7.46, 재분류 안 함)와 **불일치** → extractor도 A로 맞추는 후속이 필요 |
| B. 재분류하지 않음 | extractor 선례 유지 | site 간 일관 · 추가 변경 없음 | 최종 거부까지 `success`로 집계돼 **성공률이 실제보다 높게** 나온다(gate와 반대 방향 왜곡) |

## Follow-up considerations

- 리터럴을 늘리면 증분 5(집계 API)의 site별 응답이 그만큼 넓어진다. 공개 계약이므로 `responses=`·schema 재생성 대상.
- D4를 A로 고르면 extractor 정렬은 **별도 증분**으로 분리한다(이행 무손실 증명이 따로 필요).
- `#5`의 provider 인스턴스 공유를 푸는 것은 조립 변경이라 조립 가드 회귀가 site마다 필요하다.

## Deferred / out of scope

- 증분 5 집계 API 자체(이 브리프는 무엇을 기록할지만 정한다).
- `gate_quality_score`의 D2-B 후속(severity/개수 보충).
- worker 외 scope 밖 경로(script·diagnostic)는 계속 미기록.
