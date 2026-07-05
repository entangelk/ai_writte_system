# Phase 2B 착수 결정 브리프 — 기존 기억 대조와 canonical memory

상태: `Resolved (2026-07-05) — D1=A, D2=B(시스템 threshold gate·fixture 근거), D3=A, D4=A, D5=A`
기준 문서: [`../system-contract-sot.md`](../system-contract-sot.md), [`02-analysis-pipeline.md`](02-analysis-pipeline.md) §Phase 2B, [`analysis-memory-taxonomy.md`](analysis-memory-taxonomy.md), [`02-analysis-kickoff-decisions.md`](02-analysis-kickoff-decisions.md), [`04-context-package-completion-decisions.md`](04-context-package-completion-decisions.md)
목적: Phase 2B(기존 기억 대조·변경 제안) 구현 전에 추측 구현을 피하기 위한 최소 결정을 한 화면에 모은다. Phase 2A 패턴대로 첫 sub-slice를 최소로 좁히고, 넓은 taxonomy·자동화는 추측 구현하지 않는다.

## 현재 확정된 경계 (결정이 아니라 사실)

- Phase 2A는 prior memory 없이 `needs_review` candidate만 만든다(`create` only). candidate는 `analysis_candidates`에 저장되고 Gate/사용자 승인 없이 canonical이 되지 않는다.
- **canonical memory store는 아직 없다.** Phase 2A candidate는 전부 `needs_review`이며 승인/승격 경로가 없다. 따라서 "기존 기억 대조"의 상대(=승인된 기억)가 존재하지 않는다 — 이것이 2B가 먼저 채워야 할 공백이다.
- 2026-07-05 오너 결정(SoT v1.6.38, `04-context-package-completion-decisions.md`, D1=B)으로 Phase 4의 ⑤(candidate 포함)과 ⑧(Analysis 비교용 ContextPackage)이 **Phase 2B에 종속**됐다. 즉 canonical memory와 비교용 package는 2B가 소유한다.
- Analysis AI 경계(불변): 원문에 없는 사실 보충 금지, 기존 기억 직접 덮어쓰기/merge 금지, canon 확정 금지. AI는 근거·비교 결과를 담은 candidate만 낸다(`02-analysis-pipeline.md` §Analysis AI 경계).
- 비교 작업은 `flat-loop-gate.md`의 `analysis_compare` allowlist만 쓰는 bounded flat loop, sub-agent 없음.
- taxonomy sketch(미확정): `MemoryEntry` 후보 필드는 `project_id / memory_type / subtype / scope_type / scope_id / value|payload / provenance / source_refs / confidence / status / valid_from|valid_until|scene range / version / supersedes / analysis_job_id`(`analysis-memory-taxonomy.md` §저장 모델).
- 대조 action 후보(미확정): `create / update / add_evidence / no_change / conflict`, 그리고 `merge/split`은 자동 실행 금지·review 후보만.

## 제안하는 첫 sub-slice (2B.1): canonical memory store + candidate 승격

근거: 대조 상대가 없으면 compare/action 판정이 성립하지 않는다. 부트스트랩 순서상 **승인된 memory를 만드는 경로가 먼저**다. 2B.1은 compare AI를 아직 켜지 않고, 아래만 세운다.

- `MemoryEntry` domain model(canonical memory 저장 단위) + Mongo collection + 필수 idempotency/조회 index.
- `needs_review` candidate → `MemoryEntry` **승격(promote/approve)** 연산: 사용자 승인 기반, 원본 candidate의 source_refs/provenance/payload를 보존하며 첫 version을 만든다.
- 승격은 versioned(첫 version=1), 이후 update는 이전 version 보존(2B.3에서 upsert 연결).
- HTTP surface: candidate 목록에서 승인 → memory 생성/조회(최소).

이후 sub-slice(2B.2 prior-memory 검색/비교 package = ⑧, 2B.3 compare→action 판정, 2B.4 versioned upsert/재색인, ⑤ Writing context에 canonical 포함)는 2B.1이 canonical store를 세운 뒤 순차 확정한다. 이 브리프는 그 순서와 첫 slice 경계를 잠그되, 2B.2+ 세부는 각 slice 착수 시 확정한다.

---

## 결정 필요 항목

### D1. 첫 sub-slice를 canonical store+승격(2B.1)로 시작하는가

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. canonical store+승격 먼저 | 2B.1로 memory 저장+승인 경로를 세우고, compare는 후속 | 대조 상대를 먼저 확보, ⑤/⑧ 종속 해소의 토대, 부트스트랩 순서에 맞음 | compare 가치는 다음 slice에야 보임 |
| B. compare 먼저 | 대조 로직/action 판정을 먼저, store는 나중 | 2B의 핵심 novelty를 먼저 봄 | 대조 상대(canonical)가 없어 fixture로만 검증 가능, 실사용 불가 |

추천: **A.** 승인된 memory가 있어야 compare가 실재하고, Phase 4 ⑤/⑧ 종속도 canonical store가 생겨야 풀린다.

### D2. candidate status / 승격 상태 literal과 자동 승격 여부

Phase 2A는 `needs_review` 고정. 2B는 승인 후 상태가 필요하다. (`02-analysis-pipeline.md` 미결 항목: "confirmed 자동 승격 허용할지".)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 사용자 승인만(자동 승격 없음) | `needs_review` → 사용자 승인 → `canonical` MemoryEntry. AI는 자동 승격 안 함 | 2A 안전 원칙 유지, "AI가 canon 확정 금지"와 일치 | 사람 개입 필요 |
| B. confidence 기반 자동 승격 | 높은 confidence는 자동 `confirmed` | 사람 부담↓ | fake embedding/미검증 confidence 위에서 자동 canon화는 위험, review 지위 미확정 |

추천은 A였으나 **오너 결정 = B(confidence 기반 자동 승격)** (2026-07-05).

**⚠ 스펙 경계와의 긴장 (CLAUDE.md §1에 따라 명시):** B는 아래 두 확정 문구와 표면적으로 충돌한다.
- `02-analysis-pipeline.md` §Analysis AI 경계: "canon을 확정하지 않는다."
- `02-analysis-kickoff-decisions.md` §4: "confirmed/canonical 자동 승격 여부가 미확정… 사용자 검토 전 canon으로 보이지 않게 하는 것이 안전."

**제안하는 화해 프레이밍 (오너 확인 필요):**
1. **AI가 아니라 시스템 정책이 승격한다.** Analysis AI는 종전대로 confidence를 담은 candidate만 낸다("canon 확정 금지" 유지). 승격은 AI 판단이 아니라 **결정적 threshold gate**(시스템 규칙)가 수행한다 — 이 구분으로 §Analysis AI 경계는 깨지지 않는다.
2. **threshold 이상만 자동 canonical, 미만은 `needs_review` 유지 + 수동 승인 경로 보존.** 즉 자동 승격은 사용자 검토를 대체하는 게 아니라 고신뢰 후보만 앞당긴다. 수동 승인 경로(D1의 2B.1)는 그대로 둔다.
3. **threshold 값은 추측하지 않는다.** budget 기본값을 Gemma benchmark로 확정했듯(SoT v1.6.13), 자동 승격 threshold도 유형별 품질 fixture/benchmark로 확정한다. 첫 slice는 threshold를 **주입 가능한 설정값**으로 두고, 근거 fixture 전에는 보수적(예: 자동 승격 사실상 off에 가까운 높은 값 또는 명시 설정)로 시작한다.
4. status literal: MemoryEntry는 `canonical`. 자동 승격 대상은 `canonical`로 바로 가되 provenance/confidence/threshold 근거를 memory에 기록해 감사 가능하게 한다. candidate에는 `promoted` 표식(또는 memory join)을 남긴다.

이 화해가 확정되면 2A §4 "미확정" 항목이 "system-threshold 자동 승격 + 미만 수동"으로 닫힌다. 오너가 다른 해석을 원하면(예: AI 경계 문구 자체를 개정, 또는 threshold 없이 전량 자동) 그 방향을 canonical로 명시해야 한다.

### D3. entity/identity resolution 자동화 범위

같은 대상인지 판별하는 key가 필요하다(taxonomy §유형별 질문). (`02-analysis-pipeline.md` 미결 항목.)

| 선택지 | 설명 | 장점 | 단점 |
|---|---|---|---|
| A. 결정적 key 매칭만 | `memory_type + scope_type + scope_id`(+정규화 name) 완전일치로만 동일 대상 판정 | 추측 없음, 재현 가능 | 별칭·동명이인은 못 잡음(→ merge/split review 후보로) |
| B. 의미적(embedding) resolution | 유사도로 동일 대상 추정 | 별칭 흡수 | fake embedding 위 추측, 오매칭 위험 |

추천: **A(결정적 key).** 첫 slice는 결정적 identity key만. 별칭/동명이인은 `merge/split proposal` review 후보로 남기고 자동 병합 안 함(taxonomy §대조).

### D4. 대조 action literal 집합 (2B.3 예고, 여기선 계약만 확정)

| 선택지 | 설명 |
|---|---|
| A. taxonomy 그대로 | `create/update/add_evidence/no_change/conflict` + `merge/split`(review-only, 자동 실행 금지) |
| B. 축소 | 첫 compare slice는 `create/no_change/conflict`만, update/add_evidence 후속 |

추천: **A를 계약 목표로, 실제 구현은 2B.3에서**. literal 집합은 A로 확정하되(문서·SoT), compare 구현 slice에서 판정 경계(update vs add_evidence vs no_change)를 fixture와 함께 잠근다. `merge/split`은 항상 review 후보(자동 실행 없음)로 못박는다.

### D5. Phase 2B taxonomy 확장 범위

| 선택지 | 설명 |
|---|---|
| A. 2A 3종 유지 | `character_observation/event_observation/open_question_observation`만 canonical로 승격 가능. 확장은 후속 |
| B. 지금 확장 | mood/theme/location/relation 등 추가 |

추천: **A(2A 3종 유지).** 2A §1 원리대로 실제 소비자(Writing/Search)가 있는 최소 유형만. 확장은 별도 후속.

### D6. Analysis 비교용 ContextPackage(⑧) 필드 — 2B.2 예고

taxonomy는 비교용 package가 Writing용과 다르며 "기존 값, 상태, source, version, 비교 이유"를 반드시 포함해야 한다고 명시(§비교용 ContextPackage). 이 필드 확정은 **2B.2 착수 시** ContextSearch `purpose="analysis_context"` 신설과 함께 한다. 이 브리프는 그 종속만 명문화한다(여기서 필드를 추측 확정하지 않음).

### D7. ⑤ Writing context에 canonical memory 포함 — 후속

canonical MemoryEntry가 생기면 Writing용 context search가 `status="canonical"` memory를 안전하게 포함할 수 있다(미검증 candidate가 아니라 승인된 canon). 이는 2B.1(store) 이후 별도 slice에서 `evaluate_context_gate`의 candidate 금지 규칙을 "canonical 허용 + 미승인 candidate 금지"로 정련하며 연다. 여기선 종속만 명문화.

## 후속 (이 브리프 범위 밖)

- 2B.2 prior-memory 검색/비교 package(⑧, `analysis_context` purpose), 2B.3 compare→action 판정, 2B.4 versioned upsert/재색인.
- ⑤ Writing context canonical 포함(D7), 자동 승격/중간 status(D2 B), 의미적 entity resolution(D3 B), taxonomy 확장(D5 B).
- TimelineFact/CharacterKnowledge, diff 기반 증분 재분석, 복잡 graph resolution.

## Owner decisions — 2026-07-05

- **D1 = A.** 첫 sub-slice는 canonical store + candidate 승격(2B.1). compare/action은 후속.
- **D2 = B (confidence 기반 자동 승격), 화해 = 시스템 threshold gate.** AI는 candidate만 내고(경계 유지), 결정적 threshold gate가 승격한다. threshold 이상=자동 canonical, 미만=needs_review+수동. threshold는 fixture/benchmark 근거이며 그 전까지 보수적 주입 설정값. (상세: 아래 "D2=B 화해·threshold 확정".)
- **D3 = A.** 결정적 key(`memory_type + scope_type + scope_id` + 정규화 name) 매칭만. 별칭/동명이인은 merge/split review 후보.
- **D4 = A(작업자 기본).** action literal `create/update/add_evidence/no_change/conflict` + `merge/split`(review-only). 판정 경계는 2B.3에서 fixture와 확정.
- **D5 = A(작업자 기본).** taxonomy는 2A 3종 유지. 확장은 후속.
- D6/D7: 2B.2(⑧ `analysis_context` package)/후속(⑤ canonical 포함) 종속 명문화 — 이 브리프는 구현하지 않음.

## D2=B 화해·threshold 확정 (2026-07-05)

- **화해 = 시스템 threshold gate.** Analysis AI는 종전대로 confidence 담은 candidate만 낸다("canon 확정 금지" 유지, AI 경계 문구 개정 불필요). 승격은 AI가 아니라 **결정적 threshold gate**(시스템 정책)가 한다. threshold 이상만 자동 `canonical`, 미만은 `needs_review` 유지 + 수동 승인 경로 보존.
- **threshold = fixture/benchmark 근거.** budget 기본값을 Gemma benchmark로 확정한 선례(SoT v1.6.13)대로, 자동 승격 threshold도 품질 fixture/benchmark로 도출한다. 그 근거가 서기 전까지 **첫 slice는 threshold를 주입 가능한 설정값**으로 두고 **보수적(거의 off에 가까운 높은 값)** 기본으로 시작한다 — 추측값으로 canon을 양산하지 않는다.
- 감사성: 자동 승격된 MemoryEntry는 승격 근거(confidence, 적용 threshold, source_refs, provenance, analysis_job_id)를 기록해 나중에 재검토 가능해야 한다.
