# Decision brief — LLM 파이프라인 관측(KPI) 페이즈

상태: `Approved — 2026-07-24 (D1=B · D2=C[파생 먼저] · D3=A · D4=A · D5=계약 의무대로)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md), [`product-readiness-backlog.md`](product-readiness-backlog.md) QUAL-1
관련 코드: [`../../services/application/app/writing/loop_audit.py`](../../services/application/app/writing/loop_audit.py) `StoredWritingLoopRun`, [`../../services/application/app/writing/gate.py`](../../services/application/app/writing/gate.py), [`../../services/application/app/context_search/service.py`](../../services/application/app/context_search/service.py), [`../../services/application/app/analysis/compare_judge.py`](../../services/application/app/analysis/compare_judge.py)
계기: 오너 지시(2026-07-24) — "실제 운영 단계에서 LLM 성능·검색·작성이 제대로 진행되는지 KPI를 잡아 로그화". 쿼리 플래너·판단 AI(게이트)의 판단 결과, 생성 횟수 등 기본 카운트 + **게이트가 이전 LLM 작성 품질을 판단한 정도**를 지표화한다.

## 이 페이즈가 QUAL-1이 아닌 이유 (오너 명시, 2026-07-24)

- **QUAL-1** = *제품* 품질 지표(원고가 좋은가·게이트 경고가 유용한가)를 **사람이 dogfood 중 수기 기록**. dogfood 트리거에 종속.
- **이 페이즈** = *시스템/LLM 파이프라인*의 결정·카운트·판단정도를 **백엔드가 자동 계측·영속**. dogfood와 독립된 관측 인프라.
- 두 트랙은 서로 먹여준다(KPI 데이터가 QUAL-1 판단의 근거가 됨) 그러나 **별개**다. 이 브리프는 QUAL-1을 재작성하지 않는다 — 백로그 QUAL-1은 그대로 두고, 이 페이즈는 그 위 독립 항목이다.
- 백로그 운영 규칙 2·5(트리거 전 예방 구현 금지 / dogfood 재현 문제만 백엔드화)는 **오너 직접 지시로 상위 우선**한다. 그 결정과 근거를 `daily_logs/2026-07-24/work_log.md`에 기록한다.

## 현재 확정된 경계 (이미 있는 것 — 중복 구현 금지)

- **Writing loop은 이미 영속 계측됨**: [`loop_audit.py`](../../services/application/app/writing/loop_audit.py) `StoredWritingLoopRun`이 run당 `revision_rounds`·`retrieval_rounds`·`gate_evaluations`·`final_gate_decision`·`error_type`·`loop_status`·`total_tokens`·`wall_clock_ms` + stage별 status를 저장한다. **여기에 KPI를 새로 수집하는 게 아니라 집계해 읽는 게 gap이다.**
- **Writing Gate는 이미 구조화된 판단을 방출함**: [`gate.py`](../../services/application/app/writing/gate.py)가 `decision`(pass/needs_user_review/reject) + finding별 `severity`(ERROR/WARNING)·`type`·`recommended_decision`을 낸다. "이전 LLM이 잘 썼는지에 대한 판단 정도"는 **이 출력에서 파생 가능**하다.
- **게이트 오프라인 정확도 하네스 존재**: [`gate_quality.py`](../../services/application/app/writing/gate_quality.py)는 라벨 fixture 대비 게이트 정확도를 재는 오프라인 벤치(라이브 KPI 아님).
- **계측이 비어 있는 곳**: context planner·`compare_judge`·analysis extractor는 호출 시 `TokenUsage`를 계산하지만 **loop_audit 같은 영속 감사 레코드가 없다.** 여기가 실제 신규 수집이 필요한 지점.
- **에러 계약(H3)은 닫혀 있음**: 새 read endpoint를 추가하면 `responses=`에 realistic 에러(503 저장소 face 포함)를 선언해야 하고 전수 가드가 빠뜨림을 잡는다.

## 구현을 막는 오너 결정 (D1~D5)

---

## D1. 관측 데이터 저장 구조

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. loop_audit 확장 | 기존 writing `StoredWritingLoopRun`에 필드만 추가 | 가장 작음, 기존 collection 재사용 | writing 전용 — planner·compare·extractor는 여전히 미계측 |
| B. 통합 per-LLM-call 감사 collection | 모든 LLM 호출부(planner·gate·compare·extractor·generation)가 공통 스키마 레코드 1건 기록: `{call_site, project_id, request_id/job_id, model, outcome, decision/verdict, token_usage, latency_ms, error_type}` | 한 스키마로 전 호출부 커버, KPI 집계의 단일 read-model 토대, loop_audit는 rollup으로 유지 | 새 collection/schema 추가, loop_audit와 granularity 이중화(요약 vs 원자) 정리 필요 |
| C. append-only event store | 스트리밍/이벤트 소싱 백엔드 | 가장 풍부 | 백로그가 "미리 만들지 말라"고 명시한 telemetry event store 그 자체, 로컬 1인 범위 초과 |

**추천: B.** 실제 gap이 planner/compare/extractor 미계측 + writing은 이미 rollup이 있음이라, **호출부 공통의 원자적 per-call 레코드**가 정확히 그 구멍을 메우고 집계 read-model의 단일 토대가 된다. loop_audit는 writing-loop 요약으로 존치(중복 아님 — 요약 vs 원자 계층). C는 오너가 이미 각하한 방향.

## D2. 게이트 "판단 정도"의 지표화 방식 (오너 핵심 요구)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 파생 점수 | 기존 게이트 출력(decision + severity findings)에서 점수 계산(예: pass/needs_review/reject → 가중, ERROR/WARNING 개수 반영). 게이트 프롬프트·계약 무변 | LLM 계약 변경·재보정 위험 없음, 지금 데이터로 즉시 산출 | 게이트가 "얼마나 잘 썼나"를 직접 자기평가한 건 아니고 결정 경계에서 역산한 근사 |
| B. 게이트가 명시 점수 방출 | 게이트 스키마에 `quality_score`(예 0–1) 필드 추가 — LLM이 직접 판단 정도를 출력 | 오너 요구("판단 정도를 함께 추출")에 가장 직접적, 결정 경계보다 세밀 | 게이트 contract 변경 + **출시 프롬프트 본문 immutable 규칙**(신규 버전 필요, sha256 핀 확장) + 점수 보정/신뢰도 검증 부담 |
| C. A 먼저, B 후속 | 파생 점수를 기본 지표로 잠그고, 명시 점수는 별도 slice | 즉시 지표 + 세밀도는 필요 입증 후 | 두 슬라이스로 나뉨 |

**추천: C(= A 먼저).** 게이트는 이미 판단을 구조화(decision+severity)해 방출하므로 A가 "추출"을 이미 만족한다. B는 프롬프트 버저닝·보정 비용이 별개이고 파생 점수가 너무 거칠다고 입증된 뒤가 옳다. 단 **오너 요구 문구는 B에 가깝다** — A의 파생 점수가 원하는 "판단 정도"를 충분히 담는지 승인 시 확인 바람. (원한다면 첫 slice를 B로 올릴 수 있으나 프롬프트 immutable 함정을 함께 계약해야 함.)

## D3. 첫 slice에 잠글 KPI 범위

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 파이프라인 카운트 + 게이트 파생점수 | per-call 레코드 + 기본 카운트(생성·게이트평가·재시도·승격) + 루프 미수렴율 + D2-A 점수 | 오너가 명시한 항목 + 최소 확장, 지금 데이터로 채워짐 | 캘리브레이션·인프라율은 후속 |
| B. A + 인프라 건전성·repair율 | 502/503/504 발생율, `report field must be an array` 비-배열/repair율, 빈-검색율 | 운영 건전성까지 한 번에 | 범위·회귀 표면이 커짐 |
| C. A + 게이트 캘리브레이션 | 게이트 판단 vs 사용자 accept/edit 대조(과엄/과관대) | 최고가치 품질 지표 | **실 accept/edit ground truth 필요** → 데이터 희소, QUAL-1 신호와 겹침 |

**추천: A.** 오너가 명시한 것(플래너/게이트 결정, 생성 카운트, 게이트 판단정도)에 정확히 대응하고 기존 데이터로 즉시 값이 찍힌다. B는 다음 slice(에러 계약과 자연 연결), C는 accept/edit 신호가 쌓인 뒤(QUAL-1과 합류).

## D4. 노출 방식 (read-out)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. read-only 집계 API | `GET /projects/{id}/observability/kpi` 등 영속 감사 위 집계 반환 | 대시보드 없이 값 확인·계약 가능, H3 선언으로 잠금 | endpoint 계약·집계 쿼리 설계 필요 |
| B. structured log line | 호출부마다 JSON 로그 1줄(외부 스크랩용) | ops 친화, 백엔드 무상태 | 질의/집계는 외부 도구 의존 |
| C. A + B | 영속 + 로그 동시 | 둘 다 | 표면 최대 |

**추천: A(+ 선택적 B).** 오너가 대시보드는 후속 페이즈로 명시 분리했으므로 첫 slice는 **영속 + 집계 read API**로 값이 보이게 하고, 원하면 per-call structured 로그(B)를 얇게 더한다. 대시보드는 이 API를 소비.

## D5. 계약·스키마 반영 범위

- **SoT**: 오너가 수정 허용. per-call 감사 레코드의 계약(필드·리터럴 enum: `call_site`, `outcome`)과 게이트 파생점수 정의를 정본에 명시.
- **schema lock**: 착수 시 확인 — `schemas/`의 JSON 스키마는 **W0 공개 API 계약 전용**이고 내부 audit collection(선례 `writing_loop_audits`·`gate_findings`)은 거기 등록하지 않는다. 이 부류의 실제 lock은 **`*_mongo.py`의 field round-trip + index-name 테스트**다(그 선례 그대로 따른다). `docs/mongo_collections.md`는 설계기 카탈로그라 sibling audit collection도 미등록이므로, `llm_call_audits`만 추가하면 오히려 drift를 만든다 — 편집하지 않는다.
- **H3**: 신규 read endpoint는 `responses=`에 realistic 에러(404·503 저장소 face)를 선언 — 전수 가드가 빠뜨림을 잡는다.
- **게이트 프롬프트(D2-B 선택 시만)**: 출시 프롬프트 immutable — 본문 수정 금지, 신규 버전 + sha256 핀 확장.

## Follow-up considerations (이 결정이 열어둬야 할 문)

- per-call 레코드 스키마의 `call_site`/`outcome` enum은 **미래 호출부(대화형 수정 Phase 7 등)를 수용**하도록 일반적으로 둔다.
- D2-A 파생점수 공식은 게이트 severity 체계가 바뀌면 함께 갱신되도록 한 곳(단일 함수)에 둔다.
- 집계 API는 후속 대시보드가 소비할 것을 전제로 필드를 안정적으로 명명.
- 캘리브레이션(D3-C)이 소비할 accept/edit 신호의 출처(accept endpoint + edit distance)를 미리 식별해 두되 구현은 후속.

## Deferred / out of scope (이번에 결정 안 함)

- **대시보드/시각화** — 오너 명시로 다음 페이즈.
- **게이트 명시 quality_score(D2-B)** — A의 파생점수가 거칠다고 입증되면.
- **게이트 캘리브레이션 KPI(D3-C)** — 실 accept/edit 데이터가 쌓인 뒤, QUAL-1과 합류.
- **planner/analysis의 별도 성능 튜닝** — 관측이 문제를 드러낸 뒤.
- **외부 event store/queue(D1-C)** — 각하.

## 승인 전 보류

D1~D5 승인(또는 조정) 전에는 코드·스키마·SoT를 건드리지 않는다. 승인 후 첫 구현 slice는 D1-B의 per-call 감사 레코드 + 스키마 lock + D3-A 최소 카운트/게이트 파생점수 + D4-A read API 하나를 제안한다(회귀: 레코드 round-trip, 집계 정확성, endpoint H3 선언, 게이트 파생점수 경계값).
