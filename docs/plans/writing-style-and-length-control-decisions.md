# Decision brief — 문체 지시(예시 포함)와 생성 분량 제어

상태: `Draft — 오너 결정 대기 (구현 미착수)`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md) (v1.7.20), [`writing-workspace-v2-w0-contract.md`](writing-workspace-v2-w0-contract.md) (§ProjectBrief), [`05-writing-ai.md`](05-writing-ai.md), [`07-conversational-authoring.md`](07-conversational-authoring.md), [`product-readiness-backlog.md`](product-readiness-backlog.md)
작성: 2026-07-20

> 이 문서는 **제안 브리프**다. "Owner decisions" 절은 비어 있으며, 오너가 각 결정을 채운 뒤에만 구현을 착수한다.

## Decision needed

AI에게 **문체를 예시로 가르치는 수단**(few-shot)과 **생성 분량을 고르는 수단**을 추가할지, 한다면 어느 계약 위에 얹을지를 확정한다. 부수적으로, **현재 어투 계약이 두 곳에 중복 존재하는 모순**을 어느 쪽으로 정리할지도 함께 결정해야 한다.

## 계약 모순 선surface (CLAUDE.md §1 — 조용히 한쪽을 고르지 않는다)

**어투(tone) 계약이 두 개 있고, 하나만 살아 있다.**

| | `ProjectBriefVersion.tone` | `WritingBrief.tone` |
|---|---|---|
| 위치 | Core SOT 정본 (`core_sot/models.py:40`) | Phase 5 계약 (`writing/models.py:155`) |
| 타입 | `str \| None` (자유 텍스트 1개) | `tuple[str, ...]` (다중) |
| 영속 | append-only version + idempotency (W2) | **없음** |
| API | GET/PUT/history 4종 (W2) | **없음** |
| UI | ProjectOverview에서 편집 (`ProjectOverview.tsx:18`) | **없음** |
| 프롬프트 | `<project_brief authority="canonical">- tone:` (`prompt.py:80`) | `[WRITING BRIEF] Tone:` (`prompt.py:128` `_format_brief`) — **호출부가 `brief=`를 넘기지 않아 도달 불가** |
| 의미 | 작품 정보의 일부 (정본) | "Optional style guidance. **Not project memory — never a fact source**" (`writing/models.py:149`) |

`WritingBrief`는 `style_rules`/`preferred_patterns`/`forbidden_patterns`까지 갖춘 채 프롬프트 조립(`_format_brief`)과 서비스 시그니처(`service.py:85`)가 **완성돼 있으나**, `main.py`가 `brief=`를 전달하지 않아(`main.py:2995-3004`) 런타임에 **절대 실행되지 않는 죽은 경로**다. 테스트만 서비스 레벨에서 직접 주입해 살아 있는 것처럼 보인다(`tests/test_writing.py:212`).

이 모순은 **이 브리프에서 반드시 한쪽으로 정리한다**(D1). 방치하면 다음 작업자가 "어투는 어디에 넣나"에서 매번 추측하게 된다.

## Phase 경계 — 이건 Phase 7인가? (D0의 근거)

지난 scratch 브리프와 같은 게이트 질문이 필요한지 검토했다. **결론: 프로젝트 단위 문체·분량은 Phase 7이 아니다. 단, 장면/인물 단위로 내려가면 Phase 7이다.**

- **Phase 7 P5 저작 감독(directive)은 "메모리 거버넌스"다** — 서사 사실에 대한 use/hold/skip·importance·override와 우선순위 트리(D6/D7/D9). 대상이 **분석 산출(서사 사실)**이다.
- **문체 지시는 명시적으로 메모리가 아니다** — `WritingBrief` 독스트링이 "Not project memory — never a fact source"로 이미 계약해 뒀다. 즉 축이 다르다.
- **따라서 `WritingBrief` 배선/확장은 Phase 5의 미완성 계약을 닫는 일이지 Phase 7 진입이 아니다.** GATE-1(UX-1+QUAL-1)에 막히지 않는다.
- **단 하나의 경계**: Phase 7 §6 미결 (4)가 **"속성형(분위기·톤)=scene/style 태그 분리"**를 P5 착수 브리프 대상으로 남겨 뒀다. 이는 **장면/개체 단위 톤 태그**를 뜻한다. 그러므로 이 슬라이스를 **프로젝트 단위**로 한정하면 Phase 7과 겹치지 않고, **장면별/인물별 문체**로 넓히는 순간 Phase 7 P5 영역을 선점하게 된다.

## 현재 동작 (grounding)

- **문체**: `ProjectBrief.tone` 자유 텍스트 1줄만 실효. 예시 문단 슬롯 없음, 금칙 패턴 없음.
- **출력 분량**: `WRITING_GENERATE_MAX_TOKENS` 기본 **1024**로 서버 전역 고정(`main.py:585`). 요청 파라미터가 아니라 **UI에서 조절 불가**. 소/중/대 구분 없음.
- **입력 컨텍스트 예산**: 요청 `max_tokens` 기본 4096 → `ContextBudget`(`main.py:2991`). 프론트는 `MAX_TOKENS = 4096` 상수를 모든 호출에 동일하게 전송(`WritingPanel.tsx:24`). 이름이 출력 토큰과 같아 혼동을 부른다.
- **원고 분량 관리**: **전혀 없다.** `SaveDraftRequest.raw_text`에 길이 제약 없고(`main.py:1190`), Core SOT에도 없고, 편집기 textarea에 `maxLength` 없다. `UnitKind`(`chapter|scene|other`)는 **분류일 뿐 분량 개념이 아니다**(`core_sot/models.py:20`). 회차 분할은 순수 수동 판단이다.

## D0 — 범위: 어디까지 이번 슬라이스인가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 프로젝트 단위 문체 + 분량 프리셋 | 작품 하나에 문체 지시(예시 포함)와 생성 분량 선택을 붙인다. 장면/인물 단위는 안 함 | Phase 7 미진입(GATE-1 무관), 계약 표면 최소, 실사용 효용의 대부분을 커버 | 장면마다 톤을 바꾸고 싶으면 후속 필요 |
| B. A + 장면/인물 단위 문체 태그 | 회차·인물별로 톤/말투를 따로 지정 | 표현력 최대 | **Phase 7 §6(4) 선점** → GATE-1 게이트 논쟁 재발, 범위 급증 |
| C. 분량 제어만 | 문체는 현행 `ProjectBrief.tone` 유지, 출력 토큰 프리셋만 노출 | 가장 저렴 | 문체 중복 모순(D1)이 방치됨, few-shot이라는 핵심 요구 미해결 |

**추천: A.** 오너의 원 요구("어투를 퓨샷/원샷으로")의 핵심은 프로젝트 문체이고, 장면 단위는 Phase 7이 이미 자기 몫으로 표시해 둔 영역이다. A는 GATE-1과 무관하게 지금 할 수 있고, B로 넓히는 순간 dogfood 전에 Phase 7 진입 논쟁을 다시 열어야 한다.

## D1 — 문체를 어디에 두는가 (계약 모순 해소)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `ProjectBrief` 확장 | 살아 있는 W2 정본에 `style_examples`·`forbidden_patterns` 등을 필드 추가. `WritingBrief`는 삭제 | 계약 1개로 통일, append-only version·idempotency·history·UI를 **그대로 재사용**, 모순 즉시 해소 | Core SOT 정본 schema 변경(+OpenAPI/마이그레이션). "작품 정보"에 문체가 섞임 |
| B. `WritingBrief` 부활 | 별도 엔티티로 영속/API/UI를 새로 만들고 `brief=`를 배선 | 작품 정보 ⟂ 문체 관심사 분리, 기존 4필드 설계 재사용 | **저장소·API·UI·version 정책을 전부 신설**(W2가 이미 한 일의 재구현), tone이 두 곳에 남아 모순 지속 |
| C. 신규 `StyleGuide` 엔티티 | 제3의 정본을 새로 설계 | 가장 깨끗한 도메인 분리 | 비용 최대, 기존 두 계약을 셋으로 늘림 |

**추천: A.** 근거: (1) W2가 이미 **append-only version + optimistic base + idempotency + history + archived 경계**를 문체에도 그대로 필요한 형태로 구현해 뒀다 — B/C는 이걸 재구현한다. (2) `tone`이 이미 ProjectBrief에 있으므로, 문체를 여기로 모으면 **모순이 자연 소멸**한다(B는 모순 유지). (3) 로컬 1인 프로젝트 단계에서 엔티티 수를 늘리는 비용이 관심사 분리 이득보다 크다. **`WritingBrief`는 이 결정과 함께 삭제한다**(죽은 경로를 남기지 않는다).

## D2 — few-shot 예시의 형태

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 자유 텍스트 예시 N개 | `style_examples: [str]`, 작가가 자기 문장을 붙여넣음 | 단순, 작가가 이해하기 쉬움, one-shot·few-shot 둘 다 커버 | 개수·길이 상한 정책 필요(토큰 예산 잠식) |
| B. 원고에서 구간 참조 | 기존 version의 `source_ref` span을 예시로 지목 | 정본과 자동 동기화, 중복 저장 없음 | 앵커 stale 처리 필요(D10 계약 재사용), 초기 원고가 없으면 못 씀 |
| C. 예시 없음 (규칙 서술만) | 현행 유지 + `style_rules` 배선만 | 최소 | **오너 요구의 핵심을 미해결** |

**추천: A first, B는 후속.** 문체는 서술보다 예시가 압도적으로 잘 전달되고, A는 "초안이 아직 없는 신규 작품"에서도 쓸 수 있다(B는 못 쓴다). B는 A의 상위집합이 아니라 다른 UX라 나중에 additive로 얹을 수 있다. **상한은 잠정값으로 두고 dogfood 관찰 후 조정**하는 scratch 선례(SoT v1.7.20 "기본값 + 운영자 조정")를 따르길 권한다.

## D3 — 생성 분량 제어

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 프리셋 3단 (짧게/보통/길게) | 출력 토큰을 요청 파라미터로 승격하고 UI에 3버튼. 서버가 프리셋→토큰 매핑 소유 | 작가 언어로 표현됨, 서버가 상한 통제 유지, 계약 표면 작음 | 매핑 숫자를 정해야 함(잠정값 후 조정) |
| B. 토큰 직접 입력 | 사용자가 숫자 입력 | 정밀 | 작가에게 토큰은 의미 없는 단위, 오입력 위험 |
| C. 현행 유지 | 서버 전역 1024 고정 | 변경 0 | "한 문단만" / "장면 통째로"를 구분 못 함 |

**추천: A.** 작가가 다루는 단위는 토큰이 아니라 "얼마나 길게"다. 프리셋→토큰 매핑을 서버가 소유하면 나중에 모델이 바뀌어도 UI 계약은 불변이다. **주의**: 현재 요청 필드 `max_tokens`는 **입력 컨텍스트 예산**이라 출력용과 이름이 충돌한다 — 새 필드는 반드시 다른 이름(예: `output_length`)을 쓰고, 기존 필드 의미를 바꾸지 않는다.

## Follow-up considerations (열어둘 문)

- `style_examples`가 컨텍스트 예산을 잠식한다. 예시 총량이 커지면 `ContextPackage` 검색 몫이 줄어 품질이 역전될 수 있다 — 상한과 토큰 회계 지점을 함께 본다.
- 프리셋→토큰 매핑과 예시 개수 상한은 **scratch 선례처럼 env 조정 가능 + 기본값 계약**으로 두면 dogfood 관찰이 곧 근거가 된다.
- 장면/인물 단위 문체(Phase 7 §6(4))로 넓힐 때 `ProjectBrief` 필드가 그대로 scope key를 받을 수 있게, 필드명을 프로젝트 전용으로 못 박지 않는다.
- Writing Gate는 문체 위반을 보지 않는다(현 finding type = `do_not_use|pov|continuity`). 문체 준수를 Gate가 판정할지는 별도 결정이며 이 슬라이스 밖이다.

## Deferred / out of scope

- 장면별·인물별 문체/말투 태그 (Phase 7 P5 §6(4)).
- 문체 위반에 대한 Gate finding type 추가.
- 원고 분량(회차 길이) 관리·경고 — 현재 제한이 전무하나, 이는 **생성 분량과 다른 축**이며 별도 결정이다.
- `WritingBrief`의 `preferred_patterns`를 검색 랭킹에 연결하는 것(D9 importance 접점, Phase 7).
- few-shot 예시를 원고 span으로 참조(D2=B) — A 이후 additive 후속.

## Owner decisions — (다음 세션에서 채움)

- **D0** 범위: _대기_
- **D1** 문체 저장 위치(계약 모순 해소): _대기_
- **D2** few-shot 예시 형태: _대기_
- **D3** 생성 분량 제어: _대기_
