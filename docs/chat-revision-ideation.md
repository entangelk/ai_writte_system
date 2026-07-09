# 대화형 수정 · 아이디에이션 회의 · 저작 지시 메타데이터 — 기획 아이디에이션

> **승격됨(2026-07-09)**: 이 아이디에이션은 정식 페이즈 계획 [`plans/07-conversational-authoring.md`](plans/07-conversational-authoring.md)(**Phase 7**)로 올렸다. 이 문서는 **아이디에이션 원본(근거·논의 이력)**으로 보존한다. 확정된 결정·슬라이스는 페이즈 문서를 정본으로 본다.

상태: `아이디에이션 (Draft)` — 확정 계약 아님. 구현 착수 전 오너 결정 + 별도 착수 브리프 필요. **1차 오너 방향 반영(2026-07-09, §1.5), 2차 심화(§3.5 T7~T11 · §4.5 scope taxonomy 초안 · §4.6 감독 모드), Phase 7로 승격.**
성격: 신규 기능 아이디어를 기존 아키텍처에 접붙여 **열린 질문을 정리**하는 문서. `docs/` 루트 아이디에이션 자료와 같은 지위(문서 우선순위 최하위, `system-contract-sot.md` 참조).
관련 기존 자료: `abstract.md`(§1.2 사용자 체감 기능, §2.4/2.5 AI 출력=candidate, §4.1 글쓰기 요청 흐름, §6 Writing AI, §7 Analysis AI), `plans/06-review-ui.md`, ⑤ Writing ContextPackage(SoT §5 B), Core SOT draft/version 계약(SoT §Core SOT).

---

## 1. 요청 요약 (오너 아이디어)

현재 글쓰기 챗봇은 "새로 작성"에 가깝다(요청하면 완전히 새 글을 생성). 여기에 다음을 확장하고 싶다.

1. **부분 수정** — 이미 생성/작성된 글의 일부만 고친다(전체 재생성 아님).
2. **아이디에이션 회의** — 생성된 글을 놓고 "이 장면 어떻게 풀까" 같은 대화/브레인스토밍을 한다.
3. **내부 데이터 제공은 동일** — 위 두 기능도 지금과 같은 컨텍스트(⑤ Agentic Search ContextPackage)를 받아야 한다.
4. **분석에도 확장** — 캐릭터 분석·사건 분석 등에서도 같은 대화형 수정/회의가 있으면 좋다.
5. **저작 지시 메타데이터** — 나중에 맥거핀(떡밥) 설정을 위해 "쓰기/안쓰기", "중요도" 같은 값을 곁들여 저장한다.
6. **생성물의 DB 관리** — 아이디에이션·부분수정을 하려면 생성된 글이 메모리 캐시에 머물지 않고 **DB 단위**로 관리돼야 한다.

---

## 1.5 오너 1차 방향 + 검토 반영 (2026-07-09)

오너가 §6 열린 질문에 준 1차 방향과, 그 과정에서 드러난 추가 검토를 정리한다(확정 아님, 착수 브리프에서 최종 확정).

**오너 방향**
- **분리 확정(T1)**: 수정(candidate·Gate)과 회의(advisory)를 분리한다. "어떻게 될지 모르니 일단 분리, 최악의 경우 Gate 통로가 하나 더 느는 정도"라 저비용 안전.
- **version은 명시 시그널 때만(T2)**: 생성 턴을 version으로 두지 않는다. 저장/중간저장/채택 같은 **사용자 시그널**을 받을 때만 version 확정. 3계층 분리 채택.
- **미채택 AI 산출은 low-stakes 보존(T2)**: "굳이 필요하냐"는 유보가 있으나 "일단 저장해두면 쓸 곳은 있다"로 보존 방향. 단, 별도 1급 컬렉션이 꼭 필요한지는 열린 sub-질문(→ 검토 D).
- **대화 로그 필요 + think 분리(T2)**: 대화 로그는 필수. **think 모드일 때 "생각(reasoning)" 콘텐츠를 응답 콘텐츠와 분리**해 저장·주입해야 한다. 오픈마인드로 설계.
- **정보관리 층 일반화(T6/E)**: use/skip·중요도는 맥거핀만이 아니라 **분석에서 나오는 모든 산출(캐릭터·사건 등)에 적용되는 "내 글 정보관리" 층**으로 본다.

**검토에서 드러난 추가 고려(오너가 예상 못 했을 수 있는 지점)**
- **A. 분석 대화(D) ≈ 저작 지시(E)일 수 있다**: 분석 candidate는 원문 근거(`source_ref`/offset)에 묶인 "관찰"이다. 챗으로 "이 관찰 이렇게 바꿔줘"는 원문 근거 없는 **저자 주장/주석**일 때가 많아, 새 관찰 candidate(근거 필요)보다 **정보관리 층의 저자 오버라이드/주석**으로 모델링하는 게 계약상 깨끗하다. → E를 일반화하면 D가 상당 부분 흡수된다.
- **B. 정보관리 값은 memory 버전 id가 아니라 안정 식별자(scope key)에 매달아야 한다**: memory는 append-only(버전마다 새 id)라 `memory_id`에 걸면 다음 버전에서 고아가 된다. 캐릭터 이름/사건 identity 등 **scope key(2B.3)**에 걸어 승격·버전업에도 살아남게 한다.
- **C. 중요도 ≠ confidence(다른 축)**: confidence=AI 관찰 확신도, importance=저자가 매긴 무게. 섞지 않는다. importance는 검색 랭킹 힌트로 자연 연결(→ b-4 hybrid 튜닝 트랙과 접점).
- **D. 미채택 AI 산출의 중복 가능성**: `conversation_turn(assistant, revision_proposal)`이 이미 생성 텍스트를 담으므로 그 턴이 곧 후보다. 별도 `generated_candidate` 컬렉션 없이 "assistant 턴 → 채택 시 version 승격"이 더 단순. 3계층은 유지하되 이 중복은 열린 sub-질문.
- **E. think 콘텐츠의 처리 규칙**: reasoning 콘텐츠는 (a) **초안에 절대 미편입**, (b) 다음 턴 컨텍스트 **재주입에서 기본 제외(또는 요약만)**. `conversation_turn`에 `content_channel: thinking|answer` 분리 필요.

---

## 2. 기존 시스템과의 접점 (무엇이 이미 있고 무엇이 새로운가)

이미 있는 것(재사용 대상):
- **Core SOT**: `projects / drafts / draft_versions / snapshots / source_blocks`. draft 저장은 `idempotency_key` 필수, **명시적 version save만**(autosave는 후속). text/offset은 raw snapshot 기준(offset=code point, `content_hash`=UTF-8 SHA-256), `source_ref` span은 한 `source_block` 안에 포함.
- **⑤ Writing ContextPackage**: `context_search`가 purpose=`writing_context`로 macro/micro/constraints/do_not_use + canonical/candidate memory를 패키징하고 Gate가 통제. **부분수정·회의도 이 seam을 그대로 쓴다(요청 4).**
- **Writing 생성 계약층**: agent loop `writing_generate`(tool 없음, terminal content). abstract §6은 `WritingRequest.task_type`(예: `continue_scene`)·`output_mode: draft_patch`·`selection{start,end}`·`WritingOutput{candidate_id, output_type, self_reported_constraints, claims, status:candidate}`를 이미 그린다 — **부분수정의 씨앗은 존재하나 다중 턴·영속 세션은 미설계.**
- **Analysis**: extract → `candidate`(needs_review) → compare(scope/semantic) → ActionProposal → versioned upsert → canonical `MemoryEntry`(append-only). taxonomy에 `Foreshadowing`/`OpenQuestion` 존재, Writing Gate에 "unresolved 떡밥 통제" 항목 존재.
- **원칙**: (§2.5) **모든 AI 출력은 candidate**이고 Gate/검토를 거쳐야 canon이 된다. (§7) Analysis AI는 **canon을 확정하지 않는다**(결정적 시스템 승격만).

새로 필요한 것(이 문서의 대상):
- (A) 생성물/대화를 담는 **영속 세션·대화 엔티티**.
- (B) **수정(revision) 모드** — 선택 구간을 고치는 draft_patch 생성 + Gate.
- (C) **아이디에이션(회의) 모드** — 초안에 바로 쓰지 않는 **자문(advisory)** 대화.
- (D) **분석 대화** — 캐릭터/사건 분석 candidate에 대한 대화형 수정.
- (E) **저작 지시 메타데이터** — use/skip + 중요도 등 authorial directive(관찰이 아닌 지시).

---

## 3. 헤드라인 긴장 (CLAUDE.md §1 — 임의 결정 없이 surface)

### T1. "모든 AI 출력 = candidate" 원칙 ↔ 회의 대화 — **[오너 방향: 분리]**
브레인스토밍 대화 턴은 초안에 편입될 글이 아니라 **자문**이다. 이걸 전부 `draft_candidate`로 만들어 Writing Gate에 태우면 부정합(회의 답변은 canon 검사 대상이 아님). 반대로 아무 기록도 안 남기면 요청 6(DB 관리)과 어긋난다.
→ **수정 제안(초안에 반영될 텍스트)**과 **회의 발화(자문)**를 출력 종류로 분리한다. 전자는 candidate·Gate 적용, 후자는 세션 로그로 영속하되 Gate 비적용(또는 경량 안전성만). "최악의 경우 Gate 통로 하나 추가"라 저비용.

### T2. "명시적 version save만" ↔ 생성물 DB 관리 — **[오너 방향: 3계층, version=명시 시그널]**
현재 draft_version은 사용자가 명시 저장할 때만 생긴다. 생성된 후보·대화 버퍼는 커밋된 version도 아니고 순수 캐시도 아닌 **중간 계층**이다. 매 생성 턴을 draft_version으로 승격하면 version 이력이 AI 후보로 오염된다.
→ 3계층 분리: **committed draft_version**(저장/중간저장/채택 등 **사용자 시그널** 때만) ⟂ **generated candidate**(AI 산출, 미채택 — low-stakes 보존) ⟂ **conversation turn**(대화 로그). candidate가 채택될 때만 version으로 승격(abstract §4.1 "accept하면 draft version으로 저장").
→ **미채택 산출 중복 주의(검토 D)**: `conversation_turn(assistant, revision_proposal)`이 이미 생성 텍스트를 담으므로 별도 `generated_candidate` 컬렉션이 정말 필요한지 열린 sub-질문. "턴이 곧 후보"로 단순화 가능.
→ **think 분리(검토 E)**: 대화 로그의 각 턴은 `content_channel: thinking|answer`를 구분. thinking은 초안 미편입 + 컨텍스트 재주입 기본 제외(또는 요약).

### T3. 컨텍스트 "동일" ↔ 다중 턴 대화 상태
요청 4는 "내부 데이터 제공 동일"(=같은 ContextPackage). 그런데 다중 턴 회의는 **이전 대화 이력**도 프롬프트에 필요하다. abstract는 Writing AI를 무상태(ContextPackage만 봄)로 뒀다.
→ 대화 이력은 ContextPackage에 섞지 말고 **별도 채널**(agent loop turn history와 유사)로 주입하되, 검색 기반 컨텍스트는 종전 seam 그대로 유지 — "데이터 제공 동일" 불변, 대화 상태는 직교 축.

### T4. 부분수정의 앵커링
수정 대상 구간은 Core SOT의 raw-offset/`content_hash`/`source_block` 앵커 계약을 그대로 써야 한다(임의 span 인용은 후속). 수정이 **커밋된 version**을 대상으로 하는지 **미채택 generated candidate**를 대상으로 하는지에 따라 앵커 기준 스냅샷이 달라진다.
→ 수정 요청은 `{target_kind: draft_version|generated_candidate, pointer, selection}`로 대상을 명시. 패치는 새 candidate를 낳고(원본 불변), 채택 시 version 승격.

### T5. Analysis 대화 ↔ "canon 확정 금지" 경계 — **[검토: 근거 유무로 갈림, 상당 부분 T6에 흡수]**
캐릭터/사건 분석을 대화로 고치면, 그 산출이 **새 candidate**(안전, 기존 승격 파이프라인 통과)인지 **canonical memory 직접 편집**(경계 침범)인지가 갈린다.
→ **핵심 구분(검토 A)**: 챗 산출이 *원문 근거가 있으면* 새 관찰 candidate(source_ref 필수, 기존 파이프라인), *근거 없는 저자 주장/주석이면* **T6의 저작 지시 층**으로 간다(관찰 사칭 금지). 어느 경우든 canonical을 대화가 직접 덮어쓰지 않는다(append-only·§7 경계 보존).
→ 결과: "분석 대화(D)"는 (1) 근거 있는 재관찰 = 기존 candidate 경로, (2) 근거 없는 조정 = 저작 지시(E)로 갈라진다. **D의 상당 부분이 E로 흡수**된다.
→ **span ⟂ mode 직교(오너 방향)**: "원문 span 지정(=근거/grounding)"과 "모드(revise vs ideate)"는 **별개 축**이다. 같은 span을 수정에도, 아이디에이션에도 쓸 수 있으나 **출력은 각각 다른 채널에 별도 기록**한다(revise→revision_proposal/candidate, ideate→advisory turn). 핵심 불변: **advisory가 자동으로 patch(수정)로 승격되지 않는다** — 승격은 사용자 명시 시그널만(T2와 정합). 이래서 "섞임"을 구조적으로 차단.

### T6. 저작 지시 vs 관찰 — **[오너 방향: 맥거핀 넘어 모든 분석 산출로 일반화]**
현재 provenance는 `source_observed`/`ai_inferred`(둘 다 "관찰"). use/skip·중요도·"아직 회수 금지"는 **저자의 지시(authorial directive)**로 관찰과 성격이 다르다. 관찰 memory에 그냥 얹으면 "AI가 관찰한 사실"과 "저자가 정한 방침"이 섞인다.
→ **제3의 층**으로 분리: `authoring_directive` — 맥거핀(떡밥)뿐 아니라 **캐릭터·사건 등 모든 분석 산출에 붙는 "내 글 정보관리" 층**. `{use: use|hold|skip, importance: n, note}` + 저자 오버라이드/주석.
→ **식별자 주의(검토 B)**: directive는 `memory_id`(append-only라 버전마다 새 id → 고아)가 아니라 **안정 식별자(scope key: 캐릭터 이름·사건 identity, 2B.3)**에 매단다. 승격·버전업에도 살아남는다.
→ **축 구분(검토 C)**: `importance`(저자 무게) ≠ `confidence`(AI 관찰 확신도). importance는 검색 랭킹/컨텍스트 선별 힌트로 연결(b-4 hybrid 튜닝 접점). provenance=`authorial` 신설 후보.
→ Writing Gate의 Foreshadowing Control이 directive를 **읽어** 통제(예: `hold` 떡밥 회수 시 revise). ContextPackage 포함 시 `skip`→do_not_use, 저자 지시임을 라벨(canon 사칭 아님).

---

## 3.5 추가 검토 (2차, 2026-07-09) — 정하고 가야 할 것

### T7. 대화 ↔ draft 앵커 staleness
찍은 span은 특정 `draft_version` + `content_hash`에 묶인다(Core SOT raw-offset 계약). 대화 도중 새 version이 저장되면 이전 span 참조는 **stale**이 될 수 있다.
→ conversation_turn의 target은 `{version, content_hash, block_id, offset}`로 앵커하고, 버전 변화 시 **기존 source_ref 재검증(stale guard)** 계약을 재사용. stale이면 재조회/경고.

### T8. patch 적용 → version 승격 규칙
`revise` 산출은 **부분(patch)**인데 `draft_version`은 **전체 draft 텍스트**다. 채택 시 patch를 전체에 병합해 새 version을 만들어야 한다.
→ 승격 = "patch 적용 결과 전체 텍스트"를 새 version으로 저장(원본 version 불변, append). 병합 충돌(그 사이 원본이 바뀐 경우) 처리 규칙 필요 — content_hash 불일치 시 재적용/거부(T7과 연동).

### T9. directive 생명주기 · 충돌
같은 scope key에 use/importance가 시간에 따라 바뀔 수 있다.
→ **latest-wins vs append-이력** 결정 필요(관찰 memory는 append-only지만 directive는 "현재 방침"이라 latest-wins가 자연스러울 수 있음 — 단 이력 감사 원하면 append). 그리고 **저자 `use` ↔ Gate canon-conflict 충돌** 시 우선순위: 지시(의도)와 정합(consistency)은 다른 관심사 — 지시가 정합을 무효화하지 않고, `hold` 위반처럼 **Gate가 flag하되 저자가 override 가능**한 관계로 두는 게 후보.

### T10. scope key 충돌 (동명이인·별칭)
directive를 정규화 이름 scope key에 걸면 **동명이인**이면 충돌하고 **별칭**이면 갈라진다.
→ HANDOFF Next Tasks의 **(c) character 별칭/동명이인 semantic 보강**과 직결. 정보관리 층은 이 해소 위에 서야 안전(임시로는 명시 entity id 지정 허용).

### T11. 저작 감독 ↔ AI canon 경계 · Phase 6 중복 — **[오너 제안: directive=감독 모드]**
directive를 "메모리를 메인으로 두고 저장 버전을 분석·관리·감독하는 저자 통제면"으로 재구성(§4.6). 여기서 두 경계가 걸린다.
→ **§7 경계**: 감독을 *AI가 자동*으로 하면 "Analysis AI는 canon 확정 금지"를 넘는다. → 감독은 **저자 주도 또는 AI 제안-only**, canonical override는 **저자만**(append-only 보존).
→ **Phase 6 중복**: "저자가 메모리 버전 큐레이션/감독"은 계획된 Phase 6 review UI(confirmed/rejected)와 같은 표면. → 중복 설계 금지, **directive = Phase 6 검토/큐레이션 + 저자 의도 메타의 통합체**로 함께 설계.

---

## 4. 제안하는 개념 형태 (스케치 — 확정 아님)

> 아래는 논의를 위한 후보 모양이며, 컬렉션/필드/literal은 전부 오너 결정 + 착수 브리프에서 확정한다.

### 4.1 데이터 계층 (T2 해소안)

```text
draft_version        (기존)  사용자가 명시 시그널(저장/중간저장/채택)로 확정한 정본 이력. append 계약 유지.
conversation         (신규)  하나의 편집/회의 세션. project_id + draft_id(옵션) + mode: writing|analysis.
conversation_turn    (신규)  세션 내 발화. role: user|assistant,
                             kind: revision_proposal | advisory,
                             content_channel별 본문: { answer, thinking? }   # think 분리(검토 E)
                             revision_proposal 턴은 생성 텍스트(+ used_context_package_id,
                             self_reported_constraints, claims, target pointer/selection)를 담는다 = 후보 겸용.
generated_candidate  (선택)  미채택 산출을 별도 1급으로 둘지 열린 sub-질문(검토 D).
                             turn이 후보를 겸하면 불필요할 수 있음 — low-stakes 보존이면 turn으로 충분.
```

- **회의 모드**는 `conversation_turn(kind=advisory)`만 남기고 draft를 건드리지 않는다(T1).
- **수정 모드**는 `conversation_turn(kind=revision_proposal)`이 patch 후보를 담고 → 사용자 채택 시 version 승격(T2/T4). 원본 불변.
- **think 분리(검토 E)**: `thinking` 채널은 초안 미편입 + 재주입 기본 제외.
- 대화 이력은 별도 채널로 프롬프트에 주입, 검색 컨텍스트(ContextPackage)는 종전 그대로(T3).

### 4.2 요청 표면 (기존 WritingRequest 확장 후보)

```text
purpose ∈ { writing_context(기존) }              # 컨텍스트 검색은 동일 seam
task_type ∈ { generate(기존), revise(신규), ideate(신규) }
input: { conversation_id?, target: {kind, pointer, selection?}, user_instruction }
```

- `revise`/`ideate`는 새 purpose가 아니라 **task 축 확장** — 컨텍스트 제공은 동일(요청 4).
- `revise` 산출 = generated_candidate(patch) + Writing Gate 적용.
- `ideate` 산출 = advisory turn(초안 미반영, Gate 비적용 또는 안전성만).

### 4.3 Analysis 대화 (D, T5) — 근거 유무로 두 갈래

- `conversation(mode=analysis)`. 대화 산출은 canonical을 직접 편집하지 않는다(§7 경계).
- **(1) 근거 있는 재관찰**: 원문 span을 가리키면 새 분석 candidate(source_ref 필수) → 기존 compare/승격 경로.
- **(2) 근거 없는 저자 조정**: "이 캐릭터는 사실 이렇게 봐줘"류는 관찰 사칭 금지 → **§4.4 저작 지시(오버라이드/주석)**로 기록. → D의 상당 부분이 E로 흡수(검토 A).

### 4.4 저작 지시 / 정보관리 층 (E, T6) — 맥거핀 넘어 모든 분석 산출

```text
authoring_directive (신규)  target = 안정 식별자(scope key: 캐릭터 이름·사건 identity 등, 2B.3)
                            → memory 버전 id 아님(append-only 고아 방지, 검토 B)
                            use ∈ { use, hold, skip }   # hold = 아직 회수 금지(맥거핀 대기)
                            importance ∈ 0..n           # 저자 무게 (≠ confidence, 검토 C)
                            note / override(자유 서술: 저자 주석·조정)
                            provenance = authorial(관찰과 구분)
```

- 맥거핀(떡밥)뿐 아니라 **캐릭터·사건 등 모든 분석 산출**에 붙는 "내 글 정보관리" 층.
- Writing Gate의 **Foreshadowing Control**이 directive를 읽어 통제: `hold` 떡밥 회수 시 revise.
- `importance`는 검색 랭킹/컨텍스트 선별 힌트(b-4 hybrid 튜닝 접점); `confidence`(AI 확신도)와 별개 축.
- ContextPackage 포함 시 `skip`→do_not_use 등으로 연결하되 **저자 지시임을 라벨**(canon 사칭 아님).

---

### 4.5 정보관리 대상(scope) taxonomy 초안 (오너 요청 — 임의 분리 작성)

> **중요 사전 결정**: taxonomy를 늘리는 것은 2A에서 의도적으로 3종(character/event/open_question)으로 좁힌 결정(D5=A)을 다시 여는 일이다. 아래 확장 리스트는 세 방향 중 하나를 전제한다 — (a) **기존 3종 정체성에만** directive를 붙임(최소, D5 유지), (b) 분석 추출과 **별개의 개체 레지스트리**를 신설해 directive만 이 위에 얹음(추출은 3종 유지, 등록은 수동/파생), (c) **분석 taxonomy 자체를 확장**(D5 재개, 큼). *권장은 (b) — 추출 경계는 지키면서 저자 정보관리 대상을 넓힌다.*

**(1) 정체성 있는 개체 — 안정 scope key 가능 (directive 主 대상)**

| scope_type | scope_id 유도(후보) | 비고 |
|---|---|---|
| character(인물) | 정규화 이름 | 기존 2B.3 결정적 키. 동명이인=T10 |
| item(아이템/물건) | 정규화 이름 | 은단검 등 — **맥거핀·떡밥 주 대상** |
| location(장소) | 정규화 이름 | |
| organization(조직/세력) | 정규화 이름 | |
| event/incident(사건) | 사건 identity | 현재 semantic(2B.6), 결정적 키는 후속 |
| relationship(관계) | 정렬된 인물쌍 | 파생 키 |
| concept/setting_rule(설정·세계관 규칙) | 정규화 라벨 | |
| foreshadowing/open_question(떡밥·미해결) | 기존 open_question id + 회수상태 | `hold`/`use`의 핵심 축 |

**(2) 정체성 없는 속성 — scope key 부적합 (다른 자리, 검토 이상한부분 #1)**

- mood/atmosphere(분위기), tone/voice(톤·문체) 등은 개체가 아니라 **장면/문체 속성**이다. "아린"처럼 키를 못 박으므로 use/skip/importance를 개체처럼 못 붙인다. → **scene/chapter 범위 태그** 또는 `StyleSignal`로 다룬다(directive 대상 아님).

**(3) timeline 순위 (오너 요청 — "글 내 시간순")**

- 각 개체/directive에 **story-time 순위**를 부여해 검색 랭킹·"현재 장면 이전/이후" Gate와 연결.
- **주의(검토 이상한부분 #3)**: 회상/플래시백이 있으면 story-time은 전순서(total order)가 아니다. → **chapter-scene 서수**를 proxy 순위로 쓰고, 진짜 story-time은 부분순서(partial order)/구간으로 둔다.
- `event/incident`의 실제 발생 시점과 **서술 순서(narrative order)**를 구분(같은 사건이 회상으로 뒤에 서술될 수 있음).

### 4.6 directive를 "저작 감독(authoring supervision) 모드"로 재구성 (오너 제안, 2026-07-09)

directive를 개체에 붙는 정적 메타데이터가 아니라, **메모리를 메인으로 두고 그 위에서 저장 버전을 분석·관리·감독하는 저자의 통제면**으로 본다(§4.4를 이 프레이밍으로 흡수).

**두 스케일**
- **Macro(감독) directive**: 세션/개체 수준 저자 거버넌스 — use/hold/skip·importance·override. 메모리 store + 개체 레지스트리(§4.5 (b)) 위에서 동작.
- **Micro(국소) directive**: 글 쓰는 도중의 소형 교정 — "은단검은 사실 은색" 같은 작은 메모리/디테일을 full 분석 job 없이 즉석 반영. **draft patch(T8)와 결합된 한 제스처**가 될 수 있다(프로즈 + 메모리 동시 교정, 원자성은 열린 질문).

**서사 사실 우선순위(narrative fact precedence) — 새 정리 (오너 방향: latest-win + directive 우선)**
```text
저자 directive (override)  >  canonical 관찰  >  candidate 관찰
```
- latest-win 기본, directive가 더 큰 힘("글은 쓰면서 수정된다"). AI 관찰은 저자 directive를 무효화하지 못한다.
- CLAUDE.md의 "스펙 우선순위 트리"의 서사 사실판 — 충돌 시 임의 판단 없이 이 트리로 조정.

**경계(반드시 유지, T11)**
- "감독"은 **저자(사람) 주도 또는 AI 제안(proposal)-only**. AI 감독 모드가 canonical을 **자동 확정/덮어쓰기 하지 않는다**(§7 Analysis 경계·append-only 보존). canonical override 권한은 **저자만**.
- 이 감독 모드는 **Phase 6 review UI(confirmed/rejected 큐레이션)와 상당 부분 겹친다** → 중복 설계 말고 **함께 설계**. directive = Phase 6 검토/큐레이션 표면 + 저자 의도 메타(use/hold/skip/importance)의 통합체.

---

## 5. 가능한 단계 분할 (phasing 후보 — 우선순위는 오너 결정)

- **P1 — 대화·생성물 영속(A)**: `conversation`/`conversation_turn`(content_channel think 분리 포함) 컬렉션과 저장 계약. version=명시 시그널만(T2). `generated_candidate` 별도 1급 여부는 여기서 결정(검토 D). *다른 기능의 토대라 먼저.*
- **P2 — 수정 모드(B)**: `task_type=revise` + patch 앵커링(T4) + Writing Gate 재사용. accept→version 승격.
- **P3 — 아이디에이션 모드(C)**: `task_type=ideate` advisory 대화. Gate 자세(비적용/경량) 확정(T1).
- **P5 — 저작 감독 모드 / 정보관리 층(E, §4.6)**: 개체 레지스트리(§4.5 (b)) + `authoring_directive`(scope key 앵커, importance≠confidence, latest-win, 우선순위 트리) + Gate Foreshadowing Control 연동(T6). 맥거핀 use/hold/skip·중요도 + 저자 override. macro/micro 두 스케일. **Phase 6 review와 통합 설계**(T11).
- **P4 — 분석 대화(D)**: analysis conversation. 근거 있으면 candidate 경로, 없으면 P5 directive로(T5) — **P5에 상당 부분 의존**.

권장 순서(오너 확정 대기): **P1 → P2 → P5 → (P3·P4)**. P2/P3는 P1 위에 서고, P4는 P5(directive) 위에 상당 부분 선다. P5는 P1과 독립 시작 가능하나 Gate 연동은 P2, 큐레이션 표면은 Phase 6와 맞물린다.

---

## 6. 오너 결정이 필요한 열린 질문

**방향 나온 것(§1.5·§3.5·§4.6, 착수 브리프에서 최종 확정)**
- T1 회의/수정 **분리** ✔ / T2 **3계층·version=명시 시그널** ✔ / T6 정보관리 층 **모든 분석 산출로 일반화** ✔ / think **채널 분리** ✔ / **span ⟂ mode 직교·별도 기록**(T5) ✔ / advisory→patch **자동 승격 금지** ✔.
- **§4.5 대상 확장 = (b) 별개 개체 레지스트리** ✔ (추출은 3종 유지, directive만 레지스트리 위에 얹음).
- **directive = 저작 감독 모드(§4.6)** ✔ / **latest-win 기본 + directive 우선(우선순위 트리: 저자 directive > canonical > candidate)** ✔ / 경계: **AI 자동 canon 확정 금지, 저자만 override, Phase 6와 통합 설계**(T11) ✔.
- **micro directive 원자성** ✔ — draft patch + memory 교정은 **같은 것에서 파생이므로 한 트랜잭션(atomic, 둘 다 성공/롤백)**으로 묶는다.
- **Phase 7로 승격** ✔ — 정식 페이즈([`plans/07-conversational-authoring.md`](plans/07-conversational-authoring.md)), 슬라이스별 착수 브리프는 구현 시점에.

**아직 결정 필요 / 새로 생긴 것**
1. **micro→macro 승격 임계**: micro(국소) directive가 어느 규모/영향부터 full 분석 job(compare/승격)으로 올라가나? (원자성은 확정.)
2. **Phase 6 통합 범위(T11)**: directive 감독 모드를 Phase 6 review UI로 흡수 설계? 아니면 P5가 Phase 6의 선행 슬라이스?
3. **directive 이력 정책(T9)**: latest-win은 확정 — 다만 이전 값의 **감사 이력**을 append로 남길지(현재 방침만 vs 변경 이력)?
4. **개체 레지스트리 등록 경로(§4.5 (b))**: 개체(아이템·장소 등)는 어떻게 레지스트리에 오르나 — 수동 등록 / 분석 3종에서 파생 / micro-directive로 즉석 생성?
5. **속성형(분위기·톤) 처리**: directive 대상에서 빼고 scene/style 태그로 두는 방향 확정?
6. **timeline 순위 모델**: chapter-scene 서수 proxy + partial order 방향 확정? 발생시점 vs 서술순서 둘 다 둘지?
7. **미채택 산출 1급 여부(검토 D)**: `conversation_turn`이 후보 겸용, 별도 `generated_candidate` 미도입? 둔다면 보존 정책(무기한 vs 만료)?
8. **동명이인 scope key(T10)**: HANDOFF (c) 별칭/동명이인 해소가 선행? 임시로 명시 entity id 지정 허용?
9. **directive 강제 수준(T6)**: Gate가 `hold` 위반을 revise로 강제? `importance`를 검색 랭킹 실제 반영(b-4 합류) vs 표시만?
10. **앵커 staleness·patch 승격(T7·T8)**: 버전 변화 시 span 재검증 = source_ref stale guard 재사용 확정? patch→전체 병합→새 version 규칙(충돌 처리)?
11. **대화 상태 주입(T3)**: 별도 채널 확정? 다중 턴 길이/요약 정책? thinking 재주입 규칙(제외/요약)?
12. **수정 대상·앵커(T4)**: 커밋 version만 vs 미채택 턴도? 다중 block 선택 허용 시점(현재 source_ref 단일 block 제약)?
13. **우선순위**: 권장 **P1 → P2 → P5 → (P3·P4)** 동의? (P4 분석대화는 P5 directive에 상당 의존.)

---

## 7. 범위 밖 / 주의

- 이 문서는 **아이디에이션**이며 계약이 아니다. 코드·SoT·계획 문서는 이 문서만으로 바뀌지 않는다(문서 우선순위 최하위).
- frontend editor/chat UI 자체는 현재 범위 밖(HANDOFF Active Decisions: editor shell 보류)이며, 여기서는 백엔드 데이터·계약 형태만 다룬다.
- 실제 구현은 오너가 위 열린 질문을 결정한 뒤, 해당 기능별 `plans/*-decisions.md` 착수 브리프로 옮겨 확정한다.
- 기존 아이디에이션(`abstract.md`)·계획과 충돌하는 부분이 발견되면 임의 구현 없이 오너 확인.
