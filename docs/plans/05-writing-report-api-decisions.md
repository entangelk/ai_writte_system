# 착수 결정 브리프 — Phase 5.5 Writing report 재평가 API

상태: `Resolved — A (inline now), B additive later`

관련 정본: SoT v1.6.71, `05-writing-self-report-decisions.md` D3/D6

## Decision needed

확정 후속인 `POST /projects/{project_id}/writing/report`를 비영속 inline candidate 재평가 API로 지금 열지, WritingCandidate 영속화 뒤 candidate id 기반 API로 열지 결정해야 한다. 기존 브리프는 D3에서 API를 필수 후속으로 확정했지만 Follow-up에서는 candidate persistence/identity 이후로 제한하고 Deferred에서는 그 영속화를 현재 범위 밖으로 두어, 현재 입력 계약을 정본에서 하나로 도출할 수 없다.

## Owner decision — 2026-07-13

- **A 채택**: 비영속 inline candidate 재평가 API를 먼저 구현하고 ContextPackage는 서버가 기존 context-search 입력으로 재구성한다.
- **B 확장 보존**: 향후 persisted WritingCandidate/report와 감사 이력을 도입할 수 있도록 id 기반 조회·재평가 API를 additive로 연다. 현재 slice는 저장소·revision·감사 entity를 미리 만들지 않는다.
- 이유: 현재 generate가 비영속 candidate를 반환하므로 같은 extractor를 가장 작은 변경으로 재사용하되, 이후 감사 이력의 필요성을 막지 않는다.

## Options table

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. inline candidate API를 지금 구현 | request에 `WritingRequest`, 현재 `WritingCandidate`, ContextPackage 재구성에 필요한 입력을 받고 기존 extractor로 report를 다시 산출한다 | persistence 없이 작게 끝나며 기존 generate 합성과 같은 extractor를 즉시 재사용한다 | client가 candidate 본문·metadata를 다시 보내야 하고 server-owned candidate identity/기존 report revision 이력이 없다 |
| B. candidate persistence 후 id 기반 API | WritingCandidate/report entity와 stable id를 먼저 설계한 뒤 `{candidate_id}`를 기준으로 재평가한다 | 서버 권위 identity, 조회/404, report revision·감사 이력을 일관되게 설계할 수 있다 | 단순 재평가 API보다 선행 slice가 커지고 D6=C entity 설계까지 결합될 수 있다 |
| C. 두 단계로 구현 | 지금 inline API를 열고, persistence 후 id 기반 endpoint를 additive로 추가한다 | 즉시 재평가와 장기 identity 경로를 모두 제공한다 | public surface가 두 개가 되고 client 선택·중복 계약·향후 deprecation 부담이 생긴다 |

## Recommendation + reason

**A를 채택했다.** 현재 로컬 1인 프로젝트 단계에서 generate가 이미 비영속 inline candidate를 반환하고 같은 extractor 합성 경로가 회귀로 잠겨 있다. 첫 slice를 side-effect-free 재평가로 제한하면 신규 저장소 없이 D3의 “동일 extractor 재사용”을 가장 작은 변경으로 실현할 수 있다. persistence가 생길 때 id 기반 API는 별도 계약으로 추가하고, inline API는 명시적으로 저장·revision·감사 이력을 만들지 않는다고 잠근다.

## Follow-up considerations

- persistence 도입 시 persisted candidate/report를 서버에서 읽는 id 기반 endpoint를 additive로 둘지 inline endpoint를 대체할지 별도 결정한다.
- inline 요청에서도 `project_id`/request/candidate identity 불일치는 provider 호출 전에 거부한다.
- report는 candidate text를 바꾸거나 저장하지 않으며 Gate/Analysis/canonical write를 자동 실행하지 않는다.
- strict parse, 1회 repair, provider error/timeout mapping은 v1.6.71 계약을 그대로 재사용한다.
- ContextPackage를 client가 제출할지 서버가 기존 context-search 입력으로 재구성할지는 A 선택 시 세부 계약으로 함께 잠가야 한다.

## Deferred / out of scope

- WritingCandidate/report entity 영속화와 revision history
- stable context pointer/full `related_context_pointers` schema
- report 재평가 뒤 Gate·accept·Analysis 자동 실행
- agent-loop `self_report=finalize|defer` 종료채널 변경

## 승인 후 첫 구현 slice

1. 선택한 identity 경계와 request/response/error literal을 SoT와 이 브리프에 확정한다.
2. public HTTP 양방향 회귀를 먼저 추가한다: 정상 재평가, project/request/candidate 불일치 pre-provider 거부, malformed→repair, repair 실패, provider 502/timeout 504, side effect 없음.
3. 기존 `WritingCandidateReportService`와 strict parser를 그대로 재사용해 최소 endpoint만 구현한다.
4. focused writing/report/gate/accept 회귀 후 LLM 제외 전체 스위트를 실행한다.
5. `192.168.1.22:9080`에서는 endpoint가 제공하는 응답·생성·Think 범위 안에서 strict JSON/repair wiring smoke만 수행하고, tool calling이나 프로젝트 전용 품질을 주장하지 않는다.
