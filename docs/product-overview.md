# 제품 한 장 요약 — 무엇을, 누구를 위해, 어디까지

> **기획 축의 진입 문서.** "이 제품이 무엇이고, 어디까지가 MVP이고, 지금 어디까지 왔고, 무엇을
> 일부러 안 하는가"를 한 자리에서 답한다. 코드 구조·계약 정의는 다루지 않는다 — 그것은
> [`system-contract-sot.md`](system-contract-sot.md)다.
>
> **이 문서는 `abstract.md`의 요약본이 아니다.** [`abstract.md`](abstract.md)는 2026-06 아이디에이션
> 초안이고, 그 뒤 **단일 사용자 → 다중 사용자 전환**과 **MVP 범위 조정**이 있었다. 초안을 그대로
> 압축하면 낡은 그림이 정문에 걸리므로, 아래는 **현재 코드가 하는 일 기준**으로 다시 썼다.
> 원안과 달라진 지점은 §5에 따로 모았다.
>
> 기준 시점 **2026-08-02** · 정본 `SoT v1.7.76`.

## 1. 한 문장

사용자의 원고·설정·세계관·문체·분석 결과를 **장기 기억**으로 축적하고, 글을 쓰는 시점마다
**필요한 기억만 근거와 함께 검색해** 모델에 제공하는 **개인 창작 메모리 시스템**이다.

## 2. 풀려는 문제

장편 창작에서 무너지는 것은 문장력이 아니라 **일관성**이다. 인물의 말투가 3장과 17장에서 다르고,
죽은 인물이 되살아나고, 작가 자신도 "그때 그 설정이 뭐였더라"를 못 찾는다.

범용 챗봇은 대화창을 벗어나면 아무것도 기억하지 못하므로 이 문제를 **구조적으로** 풀 수 없다.
그래서 이 시스템의 중심은 생성 모델이 아니라 **기억과 그 기억의 검증**이다. 생성은 마지막 한 단계다.

**핵심 루프**:

```text
작성·저장 → 원문 snapshot → 구조화 기억 후보 추출 → 파생 색인 갱신
→ 필요한 기억 검색 + 정본 재조회 → 글 후보 생성 → Gate 검증 → 사용자 채택
```

## 3. 못박은 제품 원칙 (전 Phase 구속)

| 원칙 | 왜 |
|---|---|
| **AI 출력은 정본이 아니다** — 생성·분석 결과는 전부 `candidate`로 남고 Gate 판정과 사람의 검토를 거쳐야 기억이 된다 | "AI가 쓴 것이 곧 사실"이 되는 순간 기억이 오염되고, 그 오염은 다음 생성의 입력이 되어 복리로 커진다 |
| **기억은 append-only** — 덮어쓰지 않고 버전을 쌓는다 | 잘못된 갱신이 과거를 지우지 못하게 한다. 되돌릴 수 있어야 AI에게 쓰기를 맡길 수 있다 |
| **모든 주장에 근거 포인터**(`source_ref`) — 원문 위치까지 되짚는다 | 작가가 AI의 판단을 **검증**할 수 있어야 한다. 검증 불가능한 기억은 신뢰 대상이 아니다 |
| **프로젝트 격리는 전 계층 강제** — 모든 저장·검색·Gate·tool handler가 `project_id`를 강제한다 | 다른 작품의 설정이 섞이는 것은 품질 저하가 아니라 **제품의 실패**다 |

근거: [`plans/00-foundations.md`](plans/00-foundations.md) "불변 원칙" · 초안 [`abstract.md`](abstract.md) §2.

## 4. MVP 범위 — 원안과 현재 도달점

원안은 [`abstract.md`](abstract.md) §15의 네 묶음이다. **기술 의존성 순서(Phase)와 가치 묶음(MVP)은
1:1이 아니며**, 그 매핑은 [`plans/README.md`](plans/README.md)의 "Phase와 MVP의 관계" 표에 있다.

| 가치 묶음 | 원안(2026-06) | 지금 |
|---|---|---|
| **MVP 1 — 저장·분석·검색 루프** | 저장 → 5종 추출 → 색인 → Agentic Search → 이어쓰기 | **동작한다.** 추출은 **관찰 3종**으로 좁혔다(§5) · 검색은 벡터(Chroma/BGE-m3-ko) + lexical(ES/nori) **RRF 하이브리드 융합** · 검색 결과는 반드시 Mongo 정본을 재조회해 검증한 뒤 ContextPackage가 된다 |
| **MVP 2 — Continuity Gate** | Continuity·POV·떡밥 Gate를 각각, 수정 재생성 loop | **하나의 Writing Gate**로 섰다(§5) — 지적 유형 `do_not_use·pov·continuity·style`, 판정 5종(`pass·revise·retrieve_more·needs_user_review·block`). **bounded revise/retrieve loop**까지 화면에 있다 |
| **MVP 3 — 개인 문체 / Voice RAG** | 과거 글에서 문체를 **학습**(voice_samples·style_profiles) | **미착수.** 대신 문체를 사용자가 **선언**한다 — 프로젝트 브리프의 `style_rules`·`preferred_patterns`·`forbidden_patterns`·`style_examples`. Gate의 `style` 지적은 **판정을 바꾸지 않는다**(의도) |
| **MVP 4 — Project Memory Console** | 인물 카드·타임라인·떡밥 목록·관계 목록 + 승인 UI | **승인 UI만 섰다** — Review Inbox에서 후보를 확인·승인·거절·수정·병합·분할한다. 카드/타임라인/관계 그래프는 **오너 결정 대기**로 미룬 상태다(§6) |

## 5. 원안에서 **달라진** 것 (초안만 읽으면 틀리는 지점)

1. **단일 사용자 → 다중 사용자.** 초안과 [`plans/00-foundations.md`](plans/00-foundations.md)는
   "MVP는 단일 사용자 제품이고 계정·로그인·권한은 구현하지 않는다"고 적었다. **2026-07-26 오너
   결정으로 그 유예가 만료됐다.** 지금은 계정(Argon2id)·서버 세션·프론트 로그인·**프로젝트 소유권
   격리**·관리자 tier·영구 파기가 전부 서 있다. `project_id` 격리가 **대체된 것이 아니라** 그 위에
   소유권이 얹혔다.
2. **추출 5종 → 관찰 3종.** 초안의 `Character·Event·Location·Foreshadowing·Relation`은
   `character_observation·event_observation·open_question_observation`으로 좁혀졌다. 장소·관계는
   **미착수**이고, 떡밥은 "미회수 떡밥"이라는 독립 엔티티가 아니라 **열린 질문 관찰**로 들어온다.
3. **Gate 4종 분리 → Writing Gate 하나.** 초안은 Context/Continuity/POV/Foreshadowing Gate를 각각
   두었지만, 실제로는 **한 번의 판정이 네 유형의 지적을 낸다**. 판정은 가장 심각한 지적 하나로
   결정되며 — 이 단순화의 한계는 [`observability-kpi-rationale.md`](observability-kpi-rationale.md) §3에
   명시돼 있다.
4. **문체는 학습이 아니라 선언.** 위 MVP 3 참조.
5. **관측이 제품 기능으로 들어왔다.** 초안에 없던 축이다. LLM을 부르는 **8개 호출부 전부**가 표준
   감사 레코드를 남기고, 그것을 집계한 KPI 화면이 프로젝트별·전역으로 있다. 근거는
   [`observability-kpi-rationale.md`](observability-kpi-rationale.md).

## 6. 지금 일부러 **안 하는** 것

미루는 데에는 각각 근거가 있고, 대부분 **트리거가 오면 여는 백로그**
([`plans/product-readiness-backlog.md`](plans/product-readiness-backlog.md))로 분리돼 있다.

- **공유·협업 글쓰기** — 1 project 1 owner. 권한 등급·workspace·`members[]`는 미래 확장이며,
  현재 설계가 그 문을 닫지 않게 돼 있다.
- **뉴럴 cross-encoder 리랭커** — 구현하기로 **결정은 됐고 코드는 없다**. 지금 리랭킹은 RRF 융합뿐이다.
- **대화형 저작(Phase 7)** · **중첩 chapter→scene tree** · **관계 그래프·완전 타임라인** — 오너 결정 선행.
- **자기 가입(sign-up) 표면** — 계정을 만들 화면이 없다. 자기 가입을 열지는 **제품 결정**이라
  임의로 만들지 않았다(§7).

## 7. 핵심 위험과 현재 대응

초안 §16이 꼽은 다섯 위험은 전부 살아 있고, 대응이 **구현된 형태로** 서 있다. 남은 공백도 함께 적는다.

| 위험 | 현재 대응 | 남은 공백 |
|---|---|---|
| **분석 AI의 과잉 추론** — 원문에 없는 설정을 지어내 저장 | `source_ref` 필수 · candidate 기본값 · Gate 또는 사람 승인 없이는 canonical이 되지 않음 | 추출 프롬프트의 오분류 빈도는 dogfood 관찰 항목 |
| **파생 색인 stale** — 정본은 바뀌었는데 벡터/lexical이 옛 데이터를 반환 | 검색 hit를 그대로 쓰지 않고 **Mongo 정본을 재조회**해 version/hash를 확인 · 재색인은 async outbox→worker이며 canonical을 만드는 **모든 경로가 단일 choke point**를 지난다 | — |
| **Writing AI의 컨텍스트 오해** | ContextPackage가 confirmed/candidate를 구분하고 `do_not_use`·constraints를 명시 · 사후 Writing Gate | Gate 판정 대비 실제 채택 행동의 캘리브레이션은 실사용 데이터 이후 |
| **프로젝트 간 기억 오염** | 전 계층 `project_id` 강제 + Context Gate가 타 프로젝트 항목을 제거 · 그 위에 HTTP 소유권 403 | — |
| **컨텍스트 창 초과** (초안에 없던, 실사용에서 나온 위험) | 예산을 **창에서 유도**하고, 그래도 넘는 요청은 모델을 부르기 전에 400으로 거부 | 출력이 잘렸는지(`finish_reason`)는 아직 직접 관측되지 않는다 |
| **저장소 무인증 노출** (다중 사용자 전환이 만든 위험) | 저장소·내부 서비스를 `127.0.0.1`에만 바인드 — 위험을 자격증명이 아니라 **노출면 축소**로 없앴다(오너 결정) | 저장소 **자체는 여전히 무인증**이다. 포트를 다시 열면 위험이 그대로 돌아온다. 자격증명은 원격 배포 시점으로 유예 |

## 8. 정직한 공백 — 제품으로서 아직 비어 있는 것

- **스택을 처음 켠 사람은 로그인할 수 없다.** 가입 화면이 없고, 계정 생성은 관리자 전용 API거나
  부트스트랩 스크립트다. 관리자 화면 자체가 오너 결정에 막혀 있다.
- **실사용(dogfood)이 아직 시작되지 않았다.** 기술적 선행 조건은 없고 착수 판단만 남았다. 따라서
  "원고가 실제로 좋아지는가"에 대한 제품 품질 데이터는 아직 없다 — 지금 있는 숫자는 전부
  *시스템* 지표이지 *작품* 지표가 아니다.
- **운영 단계는 로컬 1인**이다. 세 대의 머신(배포용·개발용·노트북)을 옮겨 다니는 개인 환경이며,
  원격 다중 호스트 배포는 아직 계기가 오지 않았다.

## 9. 더 읽을 곳

| 궁금한 것 | 어디 |
|---|---|
| 전체 구상·대안 검토 (2026-06 초안, **현재 상태와 다를 수 있음**) | [`abstract.md`](abstract.md) |
| 확정된 제품 경계·불변 원칙 | [`plans/00-foundations.md`](plans/00-foundations.md) |
| Phase ↔ MVP 매핑, 착수 결정 브리프 인덱스 | [`plans/README.md`](plans/README.md) |
| 운영 KPI를 왜 그렇게 잡았는가 | [`observability-kpi-rationale.md`](observability-kpi-rationale.md) |
| 확정된 계약의 현재 정본 | [`system-contract-sot.md`](system-contract-sot.md) |
| 지금 무엇이 돌고 있고 어디가 함정인가 | [`../HANDOFF.md`](../HANDOFF.md) |
