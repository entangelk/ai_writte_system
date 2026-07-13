# 착수 결정 브리프 — Phase 5.9 후속 Writing persisted loop audit (L9 B)

상태: `Resolved — P1=B, ~~P2=A~~→P2=B(opt-in), P3=A, P4=A, P5=A (2026-07-13 오너 승인; P2는 같은 날 재개정)`

## P2 재개정 — 2026-07-13 (SoT v1.6.78 → v1.6.79)

독립 검증의 H3(감사 쓰기 실패가 성공한 loop 결과를 raw 500으로 잃음)를 논의하던 중, 오너가 더 근본적인 방향을 지시했다: **"감사와 실제 loop 작업을 분리하고, 항상이 아니라 필요할 때만 감사한다. on/off 토글로 사용자가 loop 실행 시 바로 적용할 수 있게."** 이는 앞서 승인·잠근 **P2=A(모든 종료 자동 감사)를 P2=B(opt-in)로 되돌리는 개정**이다(CLAUDE.md §5 — 기록된 결정과 충돌하므로 명시하고 확인함).

- **채택: A(request 플래그) + 기본 off**. `/writing/revise-and-gate` 요청에 `persist_audit` 플래그를 두고, loop는 서버 권위로 trail을 항상 in-memory 계산하되 **플래그가 true일 때만 persist**한다. 기본값은 env(`WRITING_LOOP_AUDIT_DEFAULT`, 기본 false)로 조정 가능하며 요청 플래그가 override한다.
- **H3 흡수**: persist는 loop critical path 밖의 격리된 optional 단계다. persist 단계를 try/except로 감싸 **실패해도 loop 결과는 그대로 반환**하고 `audit_id=null` + `audit_error`를 additive로 싣는다 — 감사 실패는 정의상 loop 결과를 죽이지 못한다. degrade vs fail-loud 질문은 소멸한다.
- **P2=A에서 바뀌는 것**: SoT v1.6.78 P2=A 리터럴, "no run unaudited" 불변식, `test_every_termination`/H2(모든 200 status 감사)·pre-loop 미기록 테스트가 "opt-in; 기본 off; 플래그 true일 때만 persist; pre-loop 거부는 on이어도 미기록; persist 실패는 격리" 로 개정된다.
- **유지되는 것**: P1=B(bodyless trail)·P3=A(append-only uuid)·P4=A(list/detail read)·P5=A(immutable, retention 운영과제)·side-effect 격리(Core SOT/Analysis/memory 0)·`audit_id` additive는 불변. 감사가 켜졌을 때의 레코드 구조·읽기 계약은 종전과 동일하다.
- **Tradeoff(오너 인지)**: opt-in은 P2=A의 "L4 상향 판단용 균일 관측" 이점을 약화한다. 오너는 로컬 1인 단계에서 loop별 제어·비용·격리를 우선했다 — 필요 시 조사 대상 loop에만 켠다.

## 오너 결정 — 2026-07-13

추천 묶음 **P1=B, P2=A, P3=A, P4=A, P5=A**를 그대로 승인. 추가 지시:

- **P5 / P3 — 오래된 run은 검증 보조자료로 쓰일 수 있으니 보존한다.** append-only(P3=A)로 재시도까지 모든 run을 각각 남기고, immutable(P5=A)로 자동 삭제하지 않는다. retention(TTL/archive)은 이 슬라이스에서 구현하지 않되 스키마가 그 확장을 막지 않도록 두고 **명시된 운영과제**로 남긴다. 즉 P5 미룸은 "정리 로직 없음"이며 "run 폐기"가 아니다 — 감사·검증 대조를 위해 보존이 기본이다.

관련 정본: SoT v1.6.77(§ v1.6.77 로그, Writing bounded loop), `05-writing-bounded-loop-decisions.md`(L6=A first→C, L9=A first→B, "승인 후 첫 회귀 경계" 8·follow-up considerations), 선례 `06-gate-finding-persistence-decisions.md`(v1.6.65 durable Gate finding store)

## Decision needed

`/writing/revise-and-gate` bounded loop(v1.6.77)는 현재 **호출 내 ephemeral**이다 — candidate·report·GateRun·ContextPackage·`stages`가 모두 응답에만 존재하고 저장되지 않아 재접속 감사·replay가 불가능하다. L9=A first→B가 "persisted loop audit"를 명시적 후속으로 열어 두었다. 이제 **loop 실행을 durable audit trail로 영속화**하려면 다음이 확정돼야 한다: (1) 무엇을 어느 입도로 저장하는가, (2) 언제/무조건 저장하는가, (3) run identity와 idempotency, (4) 읽기 API 형태, (5) audit 기록의 lifecycle. 이 중 어느 것도 기존 계약에서 하나로 도출되지 않으며, 각각 public schema·retention·비용을 다르게 구속한다.

## 현재 확정된 경계 (이 브리프가 바꾸지 않는 것)

- L1~L9(v1.6.77)의 **행동 정책**은 확정·구현·회귀 잠금 완료다. 이 슬라이스는 관측/감사 표면만 추가하며 loop 종료 조건·자격·budget·decision 의미는 건드리지 않는다.
- L6에서 이미 응답에 `loop:{status,revision_rounds,retrieval_rounds,gate_evaluations}` + `stages:[{stage,ordinal,status}]`를 additive로 공개했다(비영속). stage literal = `revise|report|gate|retrieve_plan|context_search|merge`, stage status = `completed|failed|no_change`, loop status = `pass|terminal_decision|not_eligible|budget_exhausted|no_change|failed`.
- **side effect 불변식 유지**: L9=A/A의 "save/accept/Analysis 0"은 그대로다. 이 슬라이스가 추가하는 유일한 side effect는 **감사 레코드 쓰기 1건**이며, 정본(Core SOT draft/version)·Analysis job·memory에는 아무 영향이 없다.
- 선례 v1.6.65 Gate finding store가 확립한 패턴(Protocol repository + `InMemory*` + Mongo adapter + 결정적 fingerprint id + service 계층)을 재사용한다. 저장 계층 자체는 신규 포크가 아니라 **채택된 기본값**이다.
- provider token `usage`는 아직 domain 결과 계약을 통과하지 않는다(B2 미구현). 따라서 이 슬라이스의 audit 레코드는 **token/latency 집계를 담지 않는다** — 그 필드는 B2가 usage plumbing을 연 뒤 additive로 붙인다.

## Options table

### P1 — 영속화 입도 (record granularity)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 요약 only | 최종 candidate text + 최종 GateResult + loop counts + `stages`(name/ordinal/status)만 저장. 중간 artifact·pointer 없음 | schema 최소, 응답과 거의 동형이라 구현·retention 비용 최저 | "왜 그 종료에 도달했는가"의 단계별 근거(어떤 finding이 revise를 유발, 어떤 pointer로 merge)를 재구성 불가 |
| B. 요약 + 단계별 audit trail | A + 각 stage에 `input/output candidate hash`, revise 유발 `trigger finding fingerprint`, retrieval `ContextPackage pointer ids`를 immutable trail로 | bounded-loop 브리프 follow-up(line 129)이 지목한 감사 목표를 정확히 충족; 본문 대신 hash/pointer라 저장 비용 제한 | schema가 A보다 넓고 fingerprint 규칙을 계약으로 고정해야 함 |
| C. 전체 payload | 각 단계 candidate/report/ContextPackage 본문 전체를 저장 | 완전 byte-for-byte replay | 비영속 첫 감사에 retention·PII·용량 부담 과도, L6=C("전체 중간 artifact")를 선점 |

추천: **B**. bounded-loop 브리프 follow-up이 이미 "stage ordinal, trigger finding fingerprint, input/output candidate hash, ContextPackage pointer를 immutable audit trail로"라고 명시했다. hash/pointer 기반은 정본 재조회로 필요한 본문을 언제든 재유도하면서(Core SOT/ContextPackage는 pointer로 재조회 가능) 저장 비용을 억제한다. 완전 본문 replay(C)는 별도 immutable manifest 결정으로 미룬다(v1.6.65 GateRunManifest 선례와 동일한 후속 취급).

### P2 — 영속화 트리거 (when/whether to persist)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 항상 자동 | 모든 `/writing/revise-and-gate` 호출이 종료(정상·partial 실패) 시 audit 레코드 1건을 쓴다 | 완전한 감사 커버리지, client 계약 무변 | 모든 호출에 쓰기 1건 추가(로컬 1인 단계에선 무해) |
| B. opt-in flag | request에 `persist_audit=true`일 때만 저장 | rollout 선택 | 한 endpoint가 두 실행 의미·두 테스트 행렬; 감사 누락 가능 |
| C. 종료 status 필터 | 예: `pass` 제외하고 non-pass/budget/failed만 저장 | 저장량 절감 | "정상 통과한 loop"의 감사가 사라져 분포 측정(follow-up 128) 불가 |

추천: **A**. 로컬 1인 프로젝트 단계에서 쓰기 1건은 비용이 아니며, L4 상향 필요성 판단(follow-up 128: revise→retrieve vs retrieve→revise 빈도, 동일 decision 반복)은 **모든 종료를 균일하게** 관측해야 성립한다. flag(B)는 endpoint에 두 의미를 얹어 v1.6.77 계약을 흐린다.

### P3 — run identity·idempotency

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 서버 생성 uuid + created_at | append-only, 매 호출이 새 run id | loop는 provider 샘플링 비결정성이 있어 같은 입력이 다른 결과를 내므로 idempotent replay 개념이 애매한데, 이를 회피 | 같은 요청 재시도가 중복 run을 남김 |
| B. 결정적 fingerprint id | Gate finding처럼 `project+request+...` fingerprint를 run id로, 재시도 시 기존 run 반환 | 재시도 dedup, 선례 일관 | loop 결과가 비결정적이라 "같은 id, 다른 실제 실행"의 의미 충돌; 재시도가 새 실행을 감사에서 숨김 |

추천: **A**. Gate finding(v1.6.65)은 결정적 finding id가 맞았다 — reject finding은 request/result fingerprint로 dedup되는 idempotent 대상이었기 때문이다. 그러나 **loop 실행은 provider 샘플링으로 비결정적**이라, 같은 요청의 두 번째 실행은 첫 번째와 다른 candidate/Gate/stages를 낳는 **별개의 감사 사건**이다. 결정적 id로 묶으면 두 번째 실행을 감사에서 지운다. 따라서 append-only uuid + `created_at`이 감사 진실성에 맞다. (idempotent replay가 필요해지면 request fingerprint를 별도 index 필드로 저장해 "같은 요청의 run들"을 조회 가능하게 두는 것으로 충분하다 — id 자체를 결정화하지 않는다.)

### P4 — 읽기 API 형태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. list(project) + detail(run_id) | `GET /projects/{id}/writing/loop-audits`(요약 목록, created_at desc) + `GET .../loop-audits/{run_id}`(전체 trail) | Gate finding list/detail 선례와 동형, 프론트가 한 계약으로 구동 | endpoint 2개 |
| B. detail only | run_id detail 조회만, 목록 없음 | 표면 최소 | run_id를 이미 알아야만 조회 가능 — 감사 진입점 부재 |

추천: **A**. loop endpoint 응답에 `audit_id`를 additive로 실어 주고, 목록/상세 두 read endpoint를 v1.6.65 Gate finding·Review Inbox와 같은 형태로 연다. list는 요약(run id, status, counts, created_at)만, detail은 P1=B 전체 trail을 반환한다.

### P5 — audit 레코드 lifecycle

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. immutable append-only | 쓴 뒤 상태 전이·수정 없음. 순수 감사 기록 | 감사 무결성, 계약 최소 | 오래된 run 정리(retention)는 별도 운영 과제로 미룸 |
| B. lifecycle 전이 도입 | Gate finding처럼 open→resolved/dismissed 같은 전이 | 후속 워크플로 연동 | loop run은 "해소" 대상이 아니라 사건 기록이라 전이 의미가 없음 |

추천: **A**. loop run은 사람이 resolve/dismiss하는 review 항목(Gate finding·conflict)과 성격이 다른 **불변 사건 기록**이다. 전이는 의미가 없고, retention/정리 정책은 필요해질 때 별도로 연다.

## Recommendation + reason

채택 제안 묶음: **P1=B, P2=A, P3=A, P4=A, P5=A**.

즉 — 모든 `/writing/revise-and-gate` 호출이 종료 시 **append-only immutable audit 레코드 1건**을 남기고(uuid + created_at), 그 레코드는 loop 요약(status·counts) + stage별 **hash/fingerprint/pointer 기반 trail**(본문 아님)을 담는다. `GET .../writing/loop-audits`(목록) + `GET .../writing/loop-audits/{id}`(상세) 두 read API를 v1.6.65 선례와 동형으로 열고, 저장은 `WritingLoopAuditRepository` Protocol + `InMemory*` + Mongo adapter로 배선한다. loop endpoint 응답에는 `audit_id`만 additive로 추가한다.

근거: 로컬 1인 프로젝트 단계에서 감사 커버리지(P2=A)와 진실성(P3=A append-only)을 우선하고, 저장 비용은 hash/pointer(P1=B)로 억제한다. 행동 계약(v1.6.77)과 side-effect 불변식(save/accept/Analysis 0)은 그대로 두고 관측 표면만 additive로 확장한다. 완전 본문 replay(P1=C)와 token/latency 집계는 각각 별도 manifest·B2 후속으로 명시 분리한다.

## Follow-up considerations (이 결정이 열어 둬야 할 문)

- **B2 usage 계측**이 열리면 audit 레코드에 stage별 provider token/latency·search hit·context token을 additive 필드로 붙인다(스키마를 미리 그 방향으로 남겨 둠).
- **완전 재현**이 필요해지면 P1=C 전체 payload 또는 별도 immutable `WritingLoopManifest`(v1.6.65 `GateRunManifest` 선례)를 검토한다.
- **stable candidate/GateRun pointer**가 생기면 audit trail의 hash를 그 안정 id로 교체·연결한다(현재는 hash가 pointer 대용).
- **retention/정리** 정책(오래된 run TTL·archive)은 감사량이 문제가 될 때 연다.

## Deferred / out of scope

- 중간 candidate/report/ContextPackage **본문** 영속(P1=C)과 byte-for-byte replay
- provider **token/latency 집계**(B2 usage contract 선행)
- audit 레코드 **lifecycle 전이**·retention TTL
- loop **행동 정책** 변경(budget 상향, multi-finding, 새 decision) — v1.6.77 확정 불변
- save/accept/Analysis 연동, idempotent loop **replay**(재실행이 아닌 조회만)
- frontend

## 승인 후 첫 회귀 경계 (P1=B·P2=A·P3=A·P4=A·P5=A 채택 가정)

1. 모든 종료(정상 6종 status + partial `failed`)가 audit 레코드 1건을 남긴다. 성공·partial 실패 양쪽에서 `stages` 순서가 레코드에 보존된다.
2. audit 레코드는 append-only다 — 같은 요청 재시도는 **새 run id**를 만들고 기존 레코드를 수정하지 않는다(두 사건 모두 조회 가능).
3. 레코드는 본문이 아니라 stage별 hash/fingerprint/pointer를 담는다 — candidate 본문 문자열은 detail의 최종 candidate에만 있고 중간 stage에는 hash만 있다.
4. `GET .../loop-audits`는 project isolation을 지키고 created_at desc로 요약만 반환한다. `GET .../loop-audits/{id}`는 타 project run에 404, 전체 trail을 반환한다.
5. audit 쓰기는 Core SOT draft/version·Analysis job·memory에 side effect 0이다(no-save spy).
6. loop endpoint 응답은 기존 `{candidate,gate,loop,stages}` + `audit_id`만 additive로 확장한다(기존 필드 불변).
7. token/latency 필드는 이 슬라이스에 **없다**(B2 forward-defense — 존재하면 회귀 실패).
