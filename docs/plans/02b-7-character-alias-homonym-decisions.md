# Phase 2B.7 착수 결정 브리프 — character 별칭/동명이인 semantic 보강 (c)

**상태**: Resolved (오너 결정 2026-07-12 — D1=A 탐지만·D2=A 별칭만 먼저·D3~D8 추천 잠금). 코드 착수 2026-07-12.
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.61)
**선행**: 2B.3(compare + 결정적 scope key, D2=A) · 2B.5(memory→vector 재색인, `memory_vectors` 채움) · 2B.6(event/open_question semantic seam + `query_similar` read 인프라) 완료.
**관련 경계**: 2B.3 `plans/02b-3-analysis-compare-action-decisions.md` **D2=A** · 2B.6 `plans/02b-6-semantic-identity-resolution-decisions.md` **D5=A**.

---

## 왜 지금 / 스코프

HANDOFF Next Tasks #1 후보 **(c) character 별칭/동명이인 semantic 보강**. 2B.6이 event/open_question용 semantic 매칭 seam(`EmbeddingSemanticMatcher` + `query_similar`)을 세우면서 character는 명시적으로 제외했다(D5=A: "character는 결정적 name key 유지, character semantic은 별도 결정"). 이 브리프가 그 "별도 결정"을 연다.

**해결 대상은 결정적 name-key의 두 실패 모드다**:

1. **별칭(alias) = false negative**: 같은 인물, 다른 표기. canonical `김철수`가 있는데 새 candidate가 `철수`/`김 대리` → `normalize_name`이 다른 `scope_id` → 매칭 0 → **create로 중복 canonical 양산**. 결정적 key로는 원천적으로 못 잡는다.
2. **동명이인(homonym) = false positive**: 다른 인물, 같은 표기. 서로 다른 두 `김철수`(다른 등장인물) → 같은 `scope_id` → 매칭 → judge가 같은 인물로 오인 → update/no_change/conflict로 **두 인물을 뭉갬**.

**현재 character 경로가 semantic seam을 우회한다**: `_find_matches`(`compare.py:184`)는 `scope is not None`(character)이면 `list_memories`를 scope로 필터할 뿐 `_semantic_matcher`를 절대 부르지 않는다(`compare.py:195-199`는 `scope is None` 분기 전용). 즉 2B.6 인프라가 있어도 character엔 닿지 않는다.

**서브 머신 가능 여부**: 이 머신은 **풀스택(Mongo·Chroma·ES·embedding·llama 전부 healthy)** — 오너 확인됨. 따라서 이 slice는 계약+fake 회귀뿐 아니라 **실 embedding 캘리브레이션까지 여기서 관통 가능**(2B.6이 캘리브레이션을 sandbox 밖으로 미룬 것과 다른 조건). 단 threshold 실값은 실 데이터 관찰이 필요하므로 여전히 D5(off 기본)로 안전하게 세우고 캘리브레이션은 라이브 관찰 배치로 뽑는다.

---

## 현재 확정된 경계 (결정이 아니라 사실)

- **결정적 character scope**: `derive_scope`(`memory/scope.py:34`) → `MemoryScope("character", normalize_name(name))`. `normalize_name` = whitespace collapse + casefold(`scope.py:29`). 그 외 유형은 `None`.
- **compare 0/1/>1 로직**(`compare.py:139-182`): matches 0 → `create`(결정적, LLM 없음); 1 → judge(update/add_evidence/no_change/conflict); >1(중복 canonical) → 결정적 `conflict`.
- **semantic read 인프라(2B.6, 이미 존재)**: `EmbeddingSemanticMatcher.match`(`semantic_matcher.py:61`)가 `derive_memory_index_text` 투영 → embed → `query_similar(project_id, memory_type, vector, limit)` → threshold·canonical·self-exclusion 필터 후 **top-1** 반환(D6=A). character도 같은 `memory_vectors`(`memory_type="character_observation"`)에 색인돼 있어 **인프라 재사용 가능**.
- **2B.3 D2=A 정본 경계**(`plans/02b-3-...:122`, SoT 반영): "character만 결정적 name key로 identity 대조. **별칭/동명이인은 `merge`/`split` review 후보(자동 병합 없음)**." — 이 slice가 건드리는 바로 그 경계.
- **2B.6 D5=A**(`plans/02b-6-...`): "character는 결정적 name key 유지(2B.3 D2=A 존중), semantic은 event/open_question 전용. **character semantic은 별도 결정**."
- **merge/split review queue**: v1.6.59로 `review_queue` store 영속화(conflict→open), v1.6.61로 resolve/dismiss 전이 실경로화. 단 **merge/split action 산출 자체는 미발화**(스키마만 열림, 2B.4 D4 / 2B.6 후속). 즉 "conflict로 surface" 채널은 이미 있다.

---

## ⚠ 헤드라인 긴장

### 긴장 1 — (c)는 D2=A "자동 병합 없음"을 **확장/완화**한다 (CLAUDE.md §1 계약 충돌)

2B.3 D2=A는 "별칭/동명이인은 review 후보, 자동 병합 없음"으로 **명시적으로 잠갔다**. (c)를 두 방향으로 해석할 수 있고, 그 함의가 정반대다:

- **해석 A — 탐지 강화(자동 병합 유지 금지)**: semantic은 별칭/동명이인 *모호성을 탐지*해서 `conflict`(review)로 surface만 한다. 자동 update/merge는 여전히 안 한다 → **D2=A와 정합**(탐지만 개선). AI는 proposal, 병합은 사람 검토라는 memory 철학과도 일치.
- **해석 B — 자동 해소(D2=A 완화)**: semantic이 별칭을 찾으면 곧장 judge로 넘겨 update/add_evidence로 **자동 병합**한다 → **D2=A 위반**. 오너가 명시적으로 완화를 승인해야 한다.

**임의로 고르지 않는다.** D1에서 오너가 방향을 확정한다. (추천은 A — 기존 계약 존중, 완화는 되돌리기 어려운 canon 오염 위험.)

### 긴장 2 — 두 실패 모드는 **메커니즘이 반대**다

- **별칭(false negative)**: name-key 매칭이 **0**일 때 semantic으로 *추가 후보를 찾는다*(매칭을 늘림).
- **동명이인(false positive)**: name-key 매칭이 **1**일 때 semantic으로 *그 매칭이 진짜인지 반증한다*(매칭을 줄임/의심).

하나의 "semantic 보강"이 아니라 **두 개의 독립 기능**이다. 한 slice에 둘 다 넣을지, 별칭만 먼저 할지 D2에서 정한다. (추천: 둘 다 같은 `query_similar` 인프라를 쓰지만 분기가 달라 회귀·리스크가 다르므로, **별칭 탐지 먼저(D2=A)**, 동명이인은 후속 증분 — 단계 분리.)

### 긴장 3 — threshold 추측값 (2B.6 긴장 2 재연)

별칭/동명이인 판정 임계값은 실 embedding + 실 데이터로만 캘리브레이션된다. auto-promotion(SoT v1.6.39 D2=B)·2B.6 D4=A와 같은 상황. 잘못 잡으면 (낮으면) 다른 인물을 별칭으로 오판, (높으면) 여전히 누적. **off 기본**으로 세우고 이 머신에서 라이브 관찰로 실값을 뽑는다(D5).

---

## 제안 slice 범위 (2B.7)

**포함(해석 A + 별칭 우선 기준)**:
- character candidate가 name-key 매칭 0일 때, `memory_vectors`(`memory_type="character_observation"`)에서 semantic으로 가까운 canonical character를 조회 → threshold 위면 **`conflict`(alias 후보, review)로 surface**(자동 update 아님). rationale에 "semantic alias candidate: <matched name>" 명시.
- 재사용: `EmbeddingSemanticMatcher`의 embed·`query_similar`·canonical/self-exclusion 필터. character 전용 threshold 주입 seam(env-gate, 기본 off).
- compare `_find_matches`/`_compare_candidate`에 character alias 분기 추가(결정적 name-key 우선, 0일 때만 semantic fallback).
- fake embedding 회귀로 seam·분기·off 기본·projection 일치·conflict surface를 양방향 잠금 + **실 embedding 라이브 관통**(풀스택 머신).

**제외(후속/D2에 따라)**:
- 동명이인(homonym) false-positive 반증(name-key=1일 때 semantic 의심) — D2에서 이번 포함 여부 결정.
- 자동 별칭 병합(해석 B) — D1에서 배제 확정 시 영구 제외.
- merge/split action 산출(스키마만 열림 유지), threshold 실값 확정(라이브 관찰 후속 배치).

---

## 결정 필요 항목

### D1. (c)의 계약 방향 [헤드라인 1 — 오너 확정]
- **A(탐지 강화, 추천)**: semantic은 별칭/동명이인을 `conflict`(review)로 surface만. 자동 병합 없음 → D2=A 정합.
- **B(자동 해소)**: semantic 매칭을 judge로 넘겨 자동 update/merge. D2=A 완화(오너 명시 승인 필요).
- 추천: **A**.

### D2. 이번 slice가 다루는 실패 모드 [헤드라인 2]
- **A(별칭만, 추천)**: name-key=0 → semantic alias 탐지 → conflict. 동명이인 반증은 후속.
- **B(둘 다)**: 별칭 + 동명이인(name-key=1일 때 semantic distance로 반증 → 매칭 무효화/conflict).
- 추천: **A** — 단계 분리(리스크·회귀 다름). 오너가 "둘 다"면 B.

### D3. semantic 결과의 compare action 매핑
- name-key=0 + semantic top-1 above-threshold일 때:
  - **A(conflict, 추천)**: 결정적 `conflict`로 surface(별칭 후보, review 큐). judge 안 부름(자동 판정 회피, D1=A 정합).
  - **B(judge)**: 그 매칭을 judge로 넘겨 update/add_evidence/no_change/conflict 판정(D1=B 쪽 성향).
- 추천: **A** — D1=A면 자동 판정을 피하고 review로. (D1=B 선택 시 B.)

### D4. character threshold 분리
- character 별칭 threshold를 event/open_question threshold와 **별도 주입값**으로. character는 name 신호가 강해 서로 다른 임계가 자연스럽다.
- 추천: 별도 env(`ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD`), 기본 `None`(off).

### D5. off 기본 + 캘리브레이션 경계 [헤드라인 3]
- **A(off 기본, 추천)**: threshold 미설정 시 character는 **종전대로 결정적 name-key만**(회귀 0, 안전). 설정 시에만 alias 탐지 발화. 실값은 이 풀스택 머신에서 라이브 관찰(candidate/canonical cosine 분포)로 뽑아 후속 확정.
- **B(초기값 채택)**: 보수적 초기 threshold를 지금 박음.
- 추천: **A**(2B.6 D4=A·auto-promo D2=B 선례와 정합).

### D6. 다중 매칭 의미
- semantic above-threshold가 여러 개면?
- **A(top-1, 추천)**: 최고 유사도 1개만(2B.6 D6=A 미러). 그것과의 alias conflict를 surface.
- **B(전부 conflict)**: 여러 별칭 후보를 한 conflict에 담음.
- 추천: **A** — 2B.6 일관.

### D7. 품질 검증 경계
- sandbox 회귀: fake embedding으로 seam·분기·off 기본·projection 일치·conflict surface 양방향 잠금.
- 라이브(이 머신): 실 embedding으로 별칭 탐지 관통 + cosine 분포 관찰(threshold 후속 확정 근거). **단 라이브 smoke는 라벨 정확도를 assert하지 않는다**(2B.6·J1 감사 교훈) — 관통·wiring 검증이지 판별 정확도 검증이 아님을 명시.
- 추천: 계약+fake 증분 + 라이브 관통(threshold 실값은 관찰만, 확정은 후속 배치).

### D8. wiring / HTTP
- compare endpoint 불변. `_default_compare_service`가 character threshold + embedding + memory vector search 있을 때 alias 분기를 켠다(없으면 결정적만). 2B.6 `_build_semantic_matcher`의 wiring guard(`CHROMA_HOST` 있고 `EMBEDDING_SERVICE_URL` 없으면 fail-fast) 패턴 재사용.
- read-after-write eventual consistency(방금 promote된 canonical은 worker drain 전 미검색 가능) = 2B.6 수용 경계 그대로(self-exclusion이 대부분 흡수).

---

## 경계 매트릭스 (구현 시 회귀 잠금 예정)

| 분기 | 방향 | 잠금 대상 |
|---|---|---|
| threshold off → character 결정적 name-key만(종전) | over-strict | off인데 semantic이 발화하면 실패(회귀 보존) |
| name-key=1(동일 표기) → 종전 judge 경로 유지 | over-strict | 별칭 분기가 name-key 매칭을 가로채면 실패 |
| name-key=0 + semantic above-threshold → conflict(alias) | under-strict | 별칭 탐지 누락 시 실패 |
| name-key=0 + semantic below-threshold → 종전 create | over-strict | 임계 미달인데 conflict 나면 실패 |
| semantic 매칭이 자동 update/merge를 하지 않음(D1=A) | over-strict | 자동 병합 발생 시 실패 |
| self-exclusion(같은 job promote memory 미매칭) | over-strict | 자기 job 산출과 매칭되면 실패 |
| canonical-only(superseded id 미매칭) | over-strict | non-canonical 매칭 시 실패 |
| cross-project 격리 | over-strict | 타 프로젝트 character 매칭 시 실패 |
| query projection = 쓰기 projection(`derive_memory_index_text`) 일치 | under-strict | projection 불일치 시 실패(검색 무의미) |
| top-1(D6=A) | over-strict | 다중 매칭을 전부 반환하면 실패 |

---

## 후속 (이 브리프 범위 밖)

- 동명이인 false-positive 반증(D2=A 선택 시) — 별도 증분.
- character alias threshold 실값 확정(라이브 cosine 분포 배치, off→발화).
- merge/split action 산출(review 큐가 별칭 conflict를 실제 merge로 전환하는 write 경로) — Phase 6 UI slice.
- J1 유형 프롬프트 판별 튜닝과 무관(이 slice는 결정적 임계 + conflict surface, judge 프롬프트 미변).

## 결정 요약 (추천값)

| # | 결정 | 추천 |
|---|------|------|
| D1 | (c) 계약 방향 | **A (탐지 강화, 자동 병합 없음)** — 헤드라인, 오너 확정 |
| D2 | 실패 모드 범위 | **A (별칭만 먼저)** — 헤드라인, 오너 확정 |
| D3 | action 매핑 | A (conflict surface, judge 미호출) |
| D4 | threshold 분리 | 별도 env, 기본 off |
| D5 | off 기본 + 캘리브레이션 | A (off 기본, 라이브 관찰 후속) |
| D6 | 다중 매칭 | A (top-1) |
| D7 | 품질 검증 | 계약+fake + 라이브 관통(라벨 미assert) |
| D8 | wiring | env-gate + 2B.6 guard 재사용 |

## Owner decisions — 2026-07-12

- **D1 = A (탐지만).** semantic은 별칭/동명이인을 `conflict`(review)로 surface만 한다. 자동 update/merge 없음 — 2B.3 D2=A "자동 병합 없음" 계약을 존중하고, AI는 proposal·병합은 사람 검토라는 memory 철학을 유지한다. 되돌리기 어려운 canon 오염을 회피한다.
- **D2 = A (별칭만 먼저).** 이번 slice는 name-key=0일 때 semantic alias 탐지만. 동명이인(name-key=1일 때 semantic 반증)은 메커니즘·회귀·리스크가 반대라 별도 후속 증분으로 분리한다.
- **D3~D8 = 추천 잠금** (D1=A·D2=A 정합):
  - D3 = A: name-key=0 + semantic top-1 above-threshold → 결정적 `conflict`(alias 후보), judge 미호출.
  - D4 = 별도 env `ANALYSIS_CHARACTER_ALIAS_MATCH_THRESHOLD`, 기본 `None`(off).
  - D5 = A: off 기본(회귀 0). 실값은 이 풀스택 머신 라이브 cosine 관찰로 후속 확정.
  - D6 = A: top-1(2B.6 D6=A 미러).
  - D7 = 계약+fake 회귀 + 라이브 관통(라벨 미assert — 관통·wiring 검증이지 판별 정확도 아님).
  - D8 = env-gate + 2B.6 `_build_semantic_matcher` wiring guard 재사용.

## (c-2) Owner decisions — 2026-07-12

- name-key=1이어도 선택 canonical과 candidate의 직접 semantic similarity가 주입 하한 미만이면 judge 대신 `conflict`; `ANALYSIS_CHARACTER_HOMONYM_MATCH_THRESHOLD` 미설정은 off. 검색 miss/index lag는 반증으로 쓰지 않는다.
- 라벨된 same/different identity text pair로 threshold와 confusion matrix를 산출하되 production 값을 자동 설정하지 않는다.
- merge는 open review entry의 `matched_memory_id`에 candidate evidence를 append-only 새 version으로 합치고 canonical payload/name을 보존한다.
- split은 open review entry가 가리키는 candidate를 별도 canonical로 승격한다. 자동 evidence 분할은 하지 않는다.
- reconcile action은 `merge|split`; resolution action/result memory를 기록해 같은 action replay는 멱등, 다른 action replay는 거부한다.
