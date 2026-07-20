# Decision brief — 문체/어투 계약(설정·관찰·검증)과 생성 분량 제어

상태: `결정 확정 (2026-07-20) — D0=B / D1=A / D2=A / D3=A / D4=B / D5=A / D6=A, 구현 미착수`
정본 연결: [`../system-contract-sot.md`](../system-contract-sot.md) (v1.7.20), [`writing-workspace-v2-w0-contract.md`](writing-workspace-v2-w0-contract.md) (§ProjectBrief), [`05-writing-ai.md`](05-writing-ai.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md), [`07-conversational-authoring.md`](07-conversational-authoring.md), [`product-readiness-backlog.md`](product-readiness-backlog.md)
작성: 2026-07-20 (오너 분석 반영 개정)

> **오너 결정 완료(2026-07-20)** — D0~D6이 아래 "Owner decisions" 절에 확정 기입됐다. 각 D절의 옵션 표와 추천은 그 결정에 이른 분석 기록이며, **충돌 시 "Owner decisions" 절이 우선**한다. 구현은 아직 착수하지 않았다.

## Decision needed

문체/어투를 **저자가 설정하고(입력)**, **분석이 관찰하며(추출)**, **Gate가 그 둘의 일치를 검증하는(대조)** 세 층을 어떻게 계약할지, 그리고 생성 분량 제어를 어디까지 노출할지를 확정한다. 부수적으로 **현재 어투 계약이 두 곳에 중복 존재하는 모순**도 함께 정리한다.

## 핵심 프레이밍 — 문체는 하나가 아니라 세 축이다 (오너 분석)

기존 논의가 "문체"를 한 덩어리로 다뤄 막혀 있었다. 오너 분석으로 **키(key)의 유무**를 기준으로 셋이 갈린다는 것이 드러났다.

| 축 | 안정적 키 | 저자 설정 | 분석 관찰 | Phase 7과의 관계 |
|---|---|---|---|---|
| **작품 전체 문체** | project | ○ | △ | Phase 5 미완성 계약 (Phase 7 아님) |
| **캐릭터 어투** | **character** | ○ | **○** | **Phase 7이 못 풀고 남긴 것을 푸는 방향** |
| 분위기/mood | **없음** | △ | ○ | Phase 7 §6(4) 답(scene 태그)이 유효 — **이 브리프 범위 밖** |

**왜 이 구분이 Phase 7과 충돌이 아닌가**: Phase 7이 분위기·톤을 directive 대상에서 뺀 이유는 아이디에이션 원문([`../chat-revision-ideation.md`](../chat-revision-ideation.md) L200)에 명시돼 있다 —

> mood/atmosphere(분위기), tone/voice(톤·문체) 등은 개체가 아니라 장면/문체 속성이다. **"아린"처럼 키를 못 박으므로** use/skip/importance를 개체처럼 못 붙인다. → scene/chapter 범위 태그 또는 `StyleSignal`로 다룬다(directive 대상 아님).

즉 차단 사유는 **"안정적 키의 부재"**다. **캐릭터 어투는 캐릭터라는 키를 갖는다.** 따라서 캐릭터 어투를 개체(캐릭터)에 붙이는 것은 Phase 7의 판단을 뒤집는 게 아니라 **그 판단의 전제를 만족시키는 유일한 하위 사례**다. 분위기/mood는 여전히 키가 없으므로 Phase 7 몫으로 남긴다(이 브리프 Deferred).

## 계약 모순 선surface (CLAUDE.md §1 — 조용히 한쪽을 고르지 않는다)

**어투(tone) 계약이 두 개 있고, 하나만 살아 있다.**

| | `ProjectBriefVersion.tone` | `WritingBrief.tone` |
|---|---|---|
| 위치 | Core SOT 정본 (`core_sot/models.py:40`) | Phase 5 계약 (`writing/models.py:155`) |
| 타입 | `str \| None` (자유 텍스트 1개) | `tuple[str, ...]` (다중) |
| 영속 / API / UI | append-only version + idempotency, 4 endpoint, ProjectOverview (`ProjectOverview.tsx:18`) | **전부 없음** |
| 프롬프트 | `<project_brief authority="canonical">- tone:` (`prompt.py:80`) | `_format_brief` (`prompt.py:128`) — **`main.py`에 `WritingBrief`/`brief=`가 0회라 런타임 도달 불가** |
| 의미 | 작품 정보의 일부 (정본) | "Optional style guidance. **Not project memory — never a fact source**" (`writing/models.py:149`) |

`WritingBrief`는 `style_rules`/`preferred_patterns`/`forbidden_patterns`까지 갖추고 프롬프트 조립·서비스 시그니처(`service.py:85`)가 완성돼 있으나 **호출부가 넘기지 않아 죽은 경로**다. 테스트만 서비스 레벨로 직접 주입해 살아 있는 것처럼 보인다(`tests/test_writing.py:212`). D1에서 반드시 한쪽으로 정리한다.

## 현재 동작 (grounding)

**설정(입력)**
- `ProjectBrief`의 `premise/genre/tone/pov/constraints`가 정본이며 프롬프트에 `<project_brief authority="canonical">`로 실린다(`prompt.py:75-89`).
- 문체 **예시(few-shot) 슬롯은 어디에도 없다**. 전부 규칙 서술형이다.
- 캐릭터별 어투 설정 수단은 **없다**.

**관찰(분석)**
- taxonomy 3종 고정: `character_observation`/`event_observation`/`open_question_observation`.
- `character_observation` payload는 **정확히 `("name","observation")`**만 허용하고, 필드가 하나라도 다르면 거부한다(`analysis/schema.py:15-35` — `observed_fields != allowed_fields`).
- Phase 7 §2가 "분석 추출 taxonomy 확장 **안 한다**(2A D5=A 유지)"를 명시한다.
- `MemoryHintType.STYLE_SIGNAL`이 이미 존재하나(`writing/models.py:81`) 이는 Writing self-report의 힌트 타입이지 분석 산출 타입이 아니다.

**검증(Gate)**
- Gate는 `format_context_package(package)`를 사용하므로 **이미 `<project_brief>`(tone·pov 포함)를 프롬프트에서 본다**(`gate_prompt.py:67`).
- **"설정 vs 작성" 대조는 이미 작동하는 선례가 있다 — POV다.** `ProjectBrief.pov`(설정)와 후보 산문을 대조해 `pov` finding을 낸다.
- 그러나 템플릿이 **`Check only: do_not_use, POV, and continuity`**로 명시적으로 닫혀 있다(`gate_prompt.py:21`). finding type도 `do_not_use|pov|continuity` 3종이다(`writing/models.py:52`).
- **자동 revise 대상은 continuity 전용**이다(`_eligible_revision_finding` → `_is_eligible_continuity_revise`, `revise_gate.py:541`). 새 finding type은 기본적으로 루프가 무시한다.

**분량**
- 출력 길이 = `WRITING_GENERATE_MAX_TOKENS` 기본 **1024, 서버 전역 고정**(`main.py:585`). 요청 파라미터가 아니라 UI 조절 불가, 소/중/대 없음.
- 요청 필드 `max_tokens`는 **출력이 아니라 입력 컨텍스트 예산**(`ContextBudget`, `main.py:2991`)이다. 프론트는 4096 상수 고정(`WritingPanel.tsx:24`).
- 원고 자체 분량 제한은 **전무**(`raw_text` 제약·`maxLength` 없음, `UnitKind`는 분류일 뿐).

---

## D0 — 범위: 세 축 중 어디까지

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 작품 문체 + 분량만 | 캐릭터 어투·Gate 검증은 후속 | 최소 표면 | 오너가 짚은 핵심(캐릭터 어투 분리·정합 검증)을 미해결 |
| B. **작품 문체 + 캐릭터 어투 + Gate 정합 검증 + 분량** | 설정·관찰·검증 세 층을 한 슬라이스로 | 축이 서로 맞물려 있어 함께 설계해야 일관됨. Gate 배관이 이미 있어 증분이 작음 | 결정 수가 많음(D0~D6), 한 슬라이스 범위가 큼 |
| C. B + 분위기/mood | 전부 | 완전 | **Phase 7 §6(4) 선점** — 키 없는 속성의 거버넌스는 Phase 7 설계가 필요 |

**추천: B.** 세 축을 쪼개면 "설정은 있는데 검증이 없다" 또는 "관찰은 하는데 설정과 못 잇는다" 같은 반쪽 상태를 거치게 된다. Gate 배관(`project_brief`가 이미 Gate 프롬프트에 있음)과 POV 선례 덕분에 검증 층의 실제 증분은 **finding type 1개 + 템플릿 절**로 작다. mood는 키가 없어 성격이 다르므로 C는 배제한다.

## D1 — 작품 전체 문체를 어디에 두는가 (계약 모순 해소)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `ProjectBrief` 확장 | 살아 있는 W2 정본에 `style_examples`·`forbidden_patterns` 등을 추가하고 **`WritingBrief`는 삭제** | 계약 1개로 통일, append-only version·idempotency·history·UI 재사용, 모순 즉시 해소 | Core SOT 정본 schema 변경(+OpenAPI). "작품 정보"에 문체가 섞임 |
| B. `WritingBrief` 부활 | 별도 엔티티로 영속/API/UI 신설 + `brief=` 배선 | 작품 정보 ⟂ 문체 관심사 분리 | **W2가 이미 한 일(version·idempotency·history·UI)을 재구현**, tone이 두 곳에 남아 모순 지속 |
| C. 신규 `StyleGuide` 엔티티 | 제3의 정본 신설 | 도메인 분리 최선 | 비용 최대, 계약 2개를 3개로 |

**추천: A.** (1) W2가 문체에도 그대로 필요한 append-only version/optimistic base/idempotency/history/archived 경계를 이미 구현했다 — B/C는 재구현이다. (2) `tone`이 이미 여기 있으므로 모으면 **모순이 자연 소멸**한다(B는 유지). (3) 로컬 1인 단계에서 엔티티를 늘리는 비용이 관심사 분리 이득보다 크다.

## D2 — few-shot 예시의 형태 (작품 문체)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 자유 텍스트 예시 N개 | `style_examples: [str]`에 작가가 자기 문장을 붙여넣음 | 단순, one-shot·few-shot 모두 커버, **초안이 없는 신규 작품에도 사용 가능** | 개수·길이 상한 필요(컨텍스트 예산 잠식) |
| B. 원고 구간 참조 | 기존 version의 span을 예시로 지목 | 정본과 자동 동기화, 중복 저장 없음 | 앵커 stale 처리 필요(D10 재사용), **초기 원고가 없으면 못 씀** |
| C. 예시 없음 | 규칙 서술만 배선 | 최소 | **오너 요구의 핵심 미해결** |

**추천: A first, B는 후속.** 문체는 서술보다 예시가 압도적으로 잘 전달되고, A는 신규 작품에서도 쓸 수 있다. 상한은 SoT v1.7.20 scratch 선례대로 **"기본값 + env 조정 가능"**으로 두고 dogfood 관찰로 확정하길 권한다.

## D3 — 생성 분량 제어

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 프리셋 3단(짧게/보통/길게) | 출력 토큰을 요청 파라미터로 승격, 서버가 프리셋→토큰 매핑 소유 | 작가 언어, 서버가 상한 통제 유지, UI 계약이 모델 교체에 불변 | 매핑 숫자 결정 필요(잠정값 후 조정) |
| B. 토큰 직접 입력 | 숫자 입력 | 정밀 | 작가에게 토큰은 무의미한 단위, 오입력 위험 |
| C. 현행 유지 | 전역 1024 고정 | 변경 0 | "한 문단만"/"장면 통째로" 구분 불가 |

**추천: A.** **주의**: 기존 요청 필드 `max_tokens`는 입력 컨텍스트 예산이므로 **새 필드는 반드시 다른 이름**(예: `output_length`)을 쓰고 기존 필드 의미를 바꾸지 않는다(5개 endpoint가 이 필드를 공유한다).

## D4 — 캐릭터 어투: 관찰을 어떤 모양으로 담는가 ★ 핵심 갈림길

`character_observation` payload가 **exact-match `("name","observation")`**이고 taxonomy 확장은 금지(2A D5=A)라는 제약 아래 선택한다.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 자유 텍스트 `observation`에 서술 | "말투: 짧고 건조하게 끊어 말한다" 형태로 기존 필드에 넣음 | **schema 변경 0**, taxonomy 무변, 즉시 가능 | 구조가 없어 **Gate가 기계적으로 대조하기 약함**, 일반 관찰과 섞여 검색·표시에서 구분 불가 |
| B. payload에 `aspect` 필드 추가 | `("name","observation","aspect")`로 확장, `aspect=voice\|trait\|...` | taxonomy 3종은 유지하면서 **어투를 식별 가능**, Gate 대조와 UI 필터링이 실효 | Core SOT/analysis schema 변경 + 기존 candidate 마이그레이션 고려, exact-match 계약 수정 |
| C. 신규 candidate type | `character_voice_observation` 추가 | 가장 명시적 | **2A D5=A·Phase 7 §2 정면 위반**(taxonomy 동결) |

**추천: B.** A는 지금 싸지만 **D5(Gate 정합 검증)를 사실상 불가능하게 만든다** — 자유 서술에서 "설정한 어투"를 기계적으로 뽑아 대조할 수 없다. C는 명시적으로 금지된 taxonomy 확장이다. B는 **"taxonomy 3종 동결"은 지키면서 payload만 확장**하는 유일한 경로다. 다만 이는 exact-match 계약 수정이므로 **오너가 taxonomy 동결의 의도가 "3종 유지"인지 "payload까지 불변"인지 확인해 줘야 한다** — 전자면 B가 합법, 후자면 A로 후퇴해야 하고 D5는 축소된다.

## D5 — Gate 문체/어투 정합 검증

"설정한 문체 ↔ 작성된 문체"를 Gate가 판정할지. 배관은 이미 있다(Gate가 `project_brief`를 봄, POV가 동일 패턴의 선례).

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. `style` finding type 추가, **warning 전용·자동 revise 제외** | 위반을 알리되 루프가 자동 수정하지 않음 | 오탐 비용이 낮음(사람이 판단), 기존 자동 revise 정책(continuity 전용) 무변 | 사용자가 매번 수동 처리 |
| B. `style` 추가 + 자동 revise 대상 포함 | continuity처럼 자동 교정 | 손이 덜 감 | **문체는 POV/continuity보다 주관적이라 오탐 시 멀쩡한 문장을 고침**, revise 예산 잠식 |
| C. Gate 미변경 | 검증 안 함 | 변경 0 | 오너가 짚은 "설정과 실제가 같은가"를 미해결 |

**추천: A.** 근거: Gate quality baseline 21/21은 **경계가 명확한 케이스**에서 나온 수치다(`docs/benchmarks/2026-07-15/`). 문체 일치는 본질적으로 흐릿해 오탐 위험이 구조적으로 높고, 자동 revise에 넣으면 **Gate가 틀렸을 때 멀쩡한 산문을 고쳐 놓는다**. 기존 정책도 "실 오판 재현 fixture가 생길 때만 Gate 프롬프트를 손댄다"는 자세를 이미 취하고 있으므로, warning으로 시작해 실사용 근거가 쌓이면 조이는 것이 일관된다. **캐릭터 어투 검증은 D4=B일 때만 실효**하다(A면 대조 기준이 자유 서술이라 약함).

## D6 — 설정 ↔ 관찰 충돌 시 우선순위

작가가 설정한 어투와 분석이 관찰한 어투가 다를 때(작가가 의도적으로 바꿨을 수도, 실수일 수도) 무엇이 이기는가.

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. Phase 7 D7 트리 재사용 | `저자 설정 > canonical 관찰 > candidate 관찰`을 문체에도 적용한다고 **명시** | 이미 승인된 원칙 재사용, 새 규칙 없음, Phase 7 도착 시 자연 정합 | 문체는 D7이 상정한 "서사 사실"이 아니므로 적용 범위를 명문화해야 함 |
| B. 문체 전용 규칙 신설 | 별도 우선순위 정의 | 문체 특성 반영 | 규칙 2개, Phase 7 도착 시 충돌 |
| C. 미정의 | 정하지 않음 | — | **경계 미잠금** — 다음 작업자가 추측 |

**추천: A.** D7(`저자 directive(override) > canonical 관찰 > candidate 관찰`)은 이미 잠긴 원칙이고, "저자 의도가 AI 관찰을 이긴다"는 문체에도 그대로 타당하다. 다만 D7 원문이 서사 사실을 상정하므로 **"문체/어투에도 적용한다"를 이 브리프가 명시**해야 잠긴다. 실제 효과: Gate는 **설정을 기준으로** 후보를 판정하고, 관찰은 설정을 덮어쓰지 않는다.

---

## Follow-up considerations (열어둘 문)

- `style_examples`가 컨텍스트 예산을 잠식한다. 예시 총량이 커지면 `ContextPackage` 검색 몫이 줄어 품질이 역전될 수 있다 — 상한과 토큰 회계 지점을 함께 본다.
- 프리셋→토큰 매핑, 예시 개수 상한은 scratch 선례대로 **env 조정 가능 + 기본값 계약**으로 두면 dogfood 관찰이 곧 근거가 된다.
- D4=B의 `aspect`는 나중에 mood/scene 속성이 들어올 자리이기도 하다. 값 집합을 캐릭터 전용으로 못 박지 말고 확장 가능하게 둔다.
- 캐릭터 어투 **설정**(저자가 "아린은 이렇게 말한다")의 저장 위치는 D1=A를 따르면 ProjectBrief가 아니라 **캐릭터 개체 쪽**이 자연스럽다 — 이 브리프는 관찰(D4)과 검증(D5)을 우선 잠그고, 설정 저장은 D4 결정 후 같은 키(character) 위에 얹는다.
- Gate가 style을 보게 되면 프롬프트가 길어져 Gate 토큰 예산에 영향이 있다(현재 `WRITING_GATE_MAX_TOKENS` 1024).

## Deferred / out of scope

- **분위기/mood**(키 없는 속성) — Phase 7 §6(4) scene/style 태그 설계 몫.
- 문체 위반의 자동 교정(D5=B) — warning 운영 근거가 쌓인 뒤 재검토.
- few-shot 예시를 원고 span으로 참조(D2=B) — **오너가 채택하지 않음**(후속 후보로도 두지 않는다). 특정 구간이 필요하면 그 구간을 자유 텍스트로 붙여넣는다.
- 원고 분량(회차 길이) 관리·경고 — 생성 분량과 다른 축.
- `preferred_patterns`를 검색 랭킹에 연결(Phase 7 D9 importance 접점).
- 캐릭터 어투의 **자동 승격**(관찰 → 설정) — D6=A가 "관찰은 설정을 덮지 않는다"를 못박으므로 범위 밖.
- **비동기 생성**(백그라운드 실행·완료 알림·대기 중 집필) — 방향은 채택하나 별도 브리프. 아래 "후속 브리프 후보" 절 참조(정본 stale-base 계약 결정을 동반한다).

## Owner decisions — 확정 (2026-07-20)

- **D0 = B** — 작품 문체 + 캐릭터 어투 + Gate 정합 검증 + 분량을 한 슬라이스로. 분위기/mood는 키가 없어 Phase 7 몫으로 제외한다.

- **D1 = A** — `ProjectBrief` 확장, **`WritingBrief`는 삭제**. W2의 append-only version·idempotency·history·UI를 재사용하고 tone 중복 모순을 소멸시킨다.

- **D2 = A only** — 자유 텍스트 예시만. **원고 구간 참조(B)는 채택하지 않는다**(후속 후보로도 두지 않음). 오너 근거: 초기 원고 작성 시 아이디에이션 단계를 거치게 되며, 특정 구간을 예시로 쓰고 싶으면 **그 구간을 직접 자유 텍스트로 붙여넣는 편이 낫다**. (확인: 오너가 기억한 아이디에이션 단계는 **Phase 7 P3 `ideate`로 계획만 있고 미구현**이다. 따라서 현재 동작하는 경로는 자유 텍스트뿐이며 D2=A로 충분하다.)

- **D3 = A**, 프리셋 매핑 **1024 / 2048 / 4096**:
  | 프리셋 | 출력 토큰 | 의미 | 실측 예상 시간(≈45 tok/s) |
  |---|---|---|---|
  | 짧은 수정 | 1024 | 현재 기본값. **오너 실사용 기준으로 "짧은 수정" 체감** | ~23초 |
  | 중간부터 이어쓰기 | 2048 | | ~46초 |
  | 전체 작성 | 4096 | | ~91초 |
  - 최초 제안(8192)은 **실측 ~45 tok/s에서 ~182초가 걸려 `LLM_GATEWAY_TIMEOUT_SECONDS=120`을 초과, 기능 자체가 실패**하므로 오너가 4096으로 낮췄다.
  - **⚠ 구현 시 필수 제약**: **4096(~91초)은 자동 revise 루프를 탈 수 없다** — `WRITING_LOOP_MAX_WALL_CLOCK_MS=60000`을 초과한다. 이는 결함이 아니라 의도된 경계다(긴 생성을 자동 루프에 태우면 비용이 폭증한다). 프리셋이 루프(`/writing/revise-and-gate`)에 어떻게 노출되는지를 구현 시 명시적으로 다루고, 큰 프리셋은 단일 generate 경로로 제한한다. **`WRITING_LOOP_MAX_TOTAL_TOKENS=10000`·`WALL_CLOCK_MS=60000`은 B2b 실측(4991tok/51755ms)에 오너가 ~2배 여유를 승인한 값이므로 이 슬라이스에서 조용히 바꾸지 않는다.**
  - **새 요청 필드는 반드시 다른 이름**(예: `output_length`)을 쓴다. 기존 `max_tokens`는 **입력 컨텍스트 예산**이며 5개 endpoint가 공유한다.

- **D4 = B** — `character_observation` payload에 `aspect` 필드 추가. **오너가 taxonomy 동결의 의미를 "3종 유지"로 확정**했으므로 payload 확장은 합법이다(2A D5=A·Phase 7 §2 위반 아님). 이로써 D5의 기계적 대조가 실효를 갖는다.

- **D5 = A** — `style` finding type 추가, **warning 전용 · 자동 revise 제외 · block 없음**. 오너 근거: 어투 이탈은 **저자가 알아차리면 충분**하고, **의도적으로 다르게 쓰는 경우도 정당**하므로 차단하거나 재생성 루프를 태우면 안 된다. (기존 자동 revise가 continuity 전용이라 기본 동작이 이미 이에 부합하며, 명시적으로 잠그면 된다.)

- **D6 = A + 사용자 확인이 최종** — 우선순위는 **설정 우선**(Phase 7 D7 트리 `저자 설정 > canonical 관찰 > candidate 관찰`을 문체/어투에도 적용). 단 **차단이 아니라 경고**이며, D5와 같은 이유로 **의도적 변경 가능성을 전제**해 **최종 결정은 사용자 선택**이다.
  - **관찰 → 설정 자동 반영 기능은 만들지 않는다.** 저자가 설정을 바꾸고 싶으면 직접 수정한다. (확인: **ProjectBrief는 이미 append-only version + history API**(`GET /projects/{id}/brief/versions`)이므로, 직접 수정하면 **이력이 자동 보존된다**. 오너가 우려한 "설정 변경의 히스토리"는 신규 작업 없이 이미 충족된다.)

## 후속 브리프 후보 — 비동기 생성 (이 슬라이스 밖)

오너가 D3 논의 중 제안했다: 긴 생성을 **백그라운드로 돌리고**, 결과를 분할 화면 오른쪽 탭에 복사 가능한 형태로 띄우고, 완료 시 알림을 주어 **대기 중에도 집필을 계속**하게 한다.

**방향은 타당하나 이 브리프 범위 밖이며, 별도 브리프가 필요하다.** 근거:

- **일부는 이미 있다**: 분할 화면 오른쪽 rail은 **W1으로 구현 완료**이고 생성 결과는 이미 편집기가 아니라 rail에 뜬다. 없는 것은 **백그라운드 실행 · 완료 알림 · 대기 중 집필**이다.
- **정본 계약과 충돌한다(핵심)**: Writing은 **깨끗한 최신 저장 version에서만** 허용되고(D1=A), accept는 `base_version_id`로 **stale 시 409**를 낸다. 따라서 "대기 중 집필 계속"은 현 계약에서 **"생성이 끝나면 채택할 수 없다"**와 같은 뜻이 된다. stale base를 어떻게 다룰지(재생성/병합/경고 후 강제 채택)는 **정본 계약 결정**이다.
- **신규 인프라가 필요하다**: Writing job 모델(생성/상태/결과), 백그라운드 실행 경로(현 worker는 **색인 outbox drain 전용**이며 LLM 작업의 fire-and-forget 선례가 없다), 알림 표면.
- **시너지**: `writing_drafts_scratch`(SoT v1.7.20)가 **비동기 결과의 자연스러운 착지점**이다 — 이미 draft별 미채택 후보를 보관한다.
- **알림 방식 주의**: 브라우저 Notification API는 권한 거부 시 조용히 실패하므로, 탭 배지/인앱 표시가 현실적이다.
