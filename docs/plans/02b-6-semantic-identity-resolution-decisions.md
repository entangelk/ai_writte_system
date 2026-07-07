# Phase 2B.6 착수 결정 브리프 — event/open_question 의미적 identity resolution

**상태**: Resolved (오너 결정 완료 2026-07-07) — 구현 완료(SoT v1.6.47, off 기본). 실 embedding threshold 캘리브레이션만 sandbox 밖 후속.
**정본 SoT**: `docs/system-contract-sot.md` (현재 v1.6.46)
**선행**: 2B.3(compare + 결정적 scope key)·2B.5(memory→vector 재색인, `memory_vectors` 채움) 완료.

---

## 현재 확정된 경계 (결정이 아니라 사실)

- **event/open_question은 지금 항상 `create`다.** compare의 `_compare_candidate`가 `derive_scope`를 부르는데(`analysis/compare.py:118`), character만 결정적 name key를 내고 event/open_question은 `None`(`memory/scope.py`). `_find_matches`는 `scope is None`이면 `()`를 반환(`compare.py:172-173`)해 매칭이 0개 → `create`. 그래서 같은 event/open_question이 반복 추출되면 canonical이 계속 누적된다(**누적 오너 확인 대상**, 2B.3/2B.5에서 이월).
- **`memory_vectors` index는 2B.5가 채운다(쓰기 완료).** promote·auto-promote·apply 3경로가 `MemoryService` choke point로 `MEMORY_UPSERTED`를 enqueue → worker가 embed(`derive_memory_index_text`) 후 `memory_vectors` collection에 upsert(canonical-only). **하지만 읽기(query) 경로는 없다** — `MemoryVectorIndexAdapter` Protocol(`indexing/memory_index.py`)은 `upsert_memory_records`/`delete_memory_record`/`list_memory_records`만 있고 `query_similar`가 없다.
- **참고 선례**: source_block 쪽 `query_similar(project_id, vector, limit)`(`indexing/chroma.py:155`, `indexing/service.py:262`)가 벡터 검색의 기존 패턴이다. embedding 스택(`RemoteEmbeddingProvider` BGE-m3-ko + Chroma cosine)도 이미 있다.
- **compare 배선**: `_default_compare_service(memory)`(`main.py`)가 env `LLM_GATEWAY_BASE_URL` 있을 때만 judge를 붙인다. embedding/vector index는 현재 compare에 주입되지 않는다(context search 쪽만 받음).
- **2B.3 D2=A 경계**: character는 결정적 name key만, 별칭/동명이인은 `merge`/`split` review 후보(자동 병합 금지). 이 slice가 이 경계를 건드리는지 여부는 D5에서 결정.

---

## ⚠ 헤드라인 긴장

### 긴장 1 — semantic seam이 **어느 레이어**에 들어가나 (문서 간 모호성, CLAUDE.md §1)

HANDOFF와 2B.2는 "`PriorMemoryBackend`를 vector semantic 검색으로 교체"라 적었다. 그러나 **`PriorMemoryBackend`(2B.2, `context_search/prior_memory.py`)는 coarse 패키징**이다 — 한 job의 candidate group을 비교 대상으로 묶어 별도 endpoint(`/analysis/jobs/{job_id}/context`)로 내보내는 것이고, memory_type 필터일 뿐 per-candidate identity 매칭을 하지 않는다. **event/open_question을 실제로 always-create로 만드는 지점은 2B.3 compare의 `_find_matches`**다. 따라서:

- **누적 문제를 실제로 해소하려면 semantic은 compare `_find_matches`에 들어가야 한다.** PriorMemoryBackend를 semantic으로 바꿔도 compare의 always-create는 그대로다.
- 두 seam이 다른 의미다. 임의로 하나를 고르지 않고 **D1에서 오너 확정**한다.

### 긴장 2 — similarity threshold가 **추측값**이다 (품질 fixture 부재)

벡터 검색은 랭킹된 결과를 낸다. "이건 같은 subject다 / 아니다"를 가르는 유사도 임계값은 실 embedding + 실 데이터로 캘리브레이션해야 하는데 그 fixture가 아직 없다. 이는 auto-promotion threshold(SoT v1.6.39 **D2=B**: "추측값으로 canon 양산 금지, 기본 off, fixture 후 확정")와 같은 상황이다. threshold를 잘못 잡으면 (a) 너무 낮으면 서로 다른 event를 같은 것으로 오판(잘못된 update/no_change), (b) 너무 높으면 여전히 누적. **D4에서 오너가 방향(보수적 off 기본 vs 초기값 채택 vs judge 위임)을 정한다.**

---

## 제안하는 slice 범위 (2B.6)

**포함**: event/open_question candidate가 `memory_vectors`의 의미적으로 가까운 canonical과 대조되도록 compare `_find_matches`에 semantic 경로를 추가.
- `MemoryVectorIndexAdapter`에 `query_similar` 추가(fake + Chroma).
- compare에 embedding + memory vector search backend 주입 seam(env-gated).
- candidate projection → embed → query(project+memory_type scope) → threshold 위 결과를 matches로.
- 기존 0/1/>1 로직 재사용(0→create, 1→judge, 필요 시 conflict).

**제외(후속)**: character 별칭/동명이인 semantic 보강(2B.3 D2=A merge/split review), threshold 실캘리브레이션(sandbox 밖 live/fixture), ⑤ Writing canonical 포함.

---

## 결정 필요 항목

### D1. semantic seam 레이어 [헤드라인 1]
- **A**: compare `_find_matches`에 semantic 경로 추가(character=결정적 유지, event/open_question=semantic). always-create 누적을 실제로 해소. `PriorMemoryBackend`는 이 slice와 무관(coarse 패키징 그대로).
- **B**: `PriorMemoryBackend`를 semantic으로 교체(2B.2 packaging endpoint). compare는 안 바뀜 → 누적 미해소.
- **C**: 둘 다.
- 추천: **A** — 누적 문제의 실제 지점이 compare다. HANDOFF의 "PriorMemoryBackend 교체" 표현은 seam 위치를 부정확하게 적은 것으로 보고, A로 정정 제안.

### D2. `query_similar` 추가 형태
- `MemoryVectorIndexAdapter` Protocol + `InMemoryMemoryVectorIndexAdapter`(cosine) + `ChromaMemoryVectorIndexAdapter`(collection.query)에 `query_similar(*, project_id, memory_type, vector, limit)` 추가. Chroma where = `{$and:[project_id, memory_type, ...]}`(canonical-only는 status 필터 또는 index가 canonical만 담으므로 자동).
- 추천: source_block `query_similar` 미러 + memory_type 필터 추가. canonical-only는 이미 index 불변식(2B.5 self-heal)이라 status 필터 불필요(재확인 대상).

### D3. query 벡터 생성 + 주입 seam
- candidate를 `derive_memory_index_text`(2B.5 projection, 쓰기와 **동일**해야 검색 품질 성립)로 투영 → embedding provider로 embed → `query_similar`. compare service에 `embeddings` + `memory_vector_search` 주입(judge와 같은 env-gate 패턴, 없으면 semantic 경로 off).
- 추천: 쓰기/읽기가 같은 projection·같은 embedding 모델을 쓰도록 강제(불일치 시 검색 무의미).

### D4. similarity threshold 정책 [헤드라인 2]
- **A(보수적 off 기본, D2=B 선례)**: threshold 주입값·기본 `None`(off) → off면 event/open_question은 **종전대로 always-create**(안전, 회귀 없음), threshold 설정 시에만 semantic 매칭. 품질 fixture 후 실값 확정.
- **B(초기값 채택)**: 보수적 초기 threshold(예: cosine ≥ 0.85)를 지금 박고 live 관찰로 조정.
- **C(judge 위임)**: threshold로 top-K만 좁히고 "같은 subject인가"의 최종 판정을 judge(LLM)에 넘김(결정적 임계 대신 의미 판정).
- 추천: **A** — D2=B와 정합(추측값으로 canon 병합 금지). off 기본이면 이 slice는 seam+query 인프라를 안전하게 세우고, 실제 semantic 매칭은 fixture 캘리브레이션 후 켠다. 오너가 "지금 켜고 싶다"면 B, "판정을 LLM에"면 C.

### D5. character 경로 유지 여부
- **A**: character는 결정적 name key 유지(2B.3 D2=A 존중), semantic은 event/open_question 전용. 별칭/동명이인은 merge/split review 후속.
- **B**: character도 semantic 보강(별칭/오타 매칭).
- 추천: **A** — 2B.3 D2=A 경계를 이 slice에서 넓히지 않는다. character semantic은 별도 결정.

### D6. semantic 매칭 다중 결과 의미
- character의 `>1`은 결정적 `conflict`(중복 canonical). semantic의 `>1 above-threshold`는 정당하게 다른 event일 수 있어 conflict로 보면 오탐이다.
- **A**: top-1(최고 유사도) 1개만 matches로 → 0→create/1→judge. 나머지는 무시("가장 가까운 기존 것과 비교"). conflict는 judge가 낼 수 있음.
- **B**: threshold 위 전부를 matches로 → `>1`이면 character처럼 conflict.
- 추천: **A** — semantic은 랭킹이라 top-1 비교가 자연스럽고 conflict 오탐을 피한다.

### D7. 판정 품질 검증 경계
- semantic 매칭·threshold 캘리브레이션 품질은 실 embedding + 실 데이터 fixture/live로만 검증 가능(sandbox 밖). 이 slice의 sandbox 내 회귀는 fake embedding으로 seam·query·threshold 분기·projection 일치를 잠그고, 실 품질은 live 후속.
- 추천: 4.1→4.2 리듬 — 이 증분은 계약+fake+회귀, 실 embedding 캘리브레이션 fixture/live는 후속.

### D8. wiring / HTTP
- compare endpoint(`POST .../compare`)는 그대로. `_default_compare_service`가 embedding+memory vector index 있을 때 semantic backend를 붙이고, 없으면 event/open_question은 종전 always-create(off). read-after-write: 방금 promote된 memory는 worker drain 전이라 index에 없을 수 있음(eventual consistency) — self-exclusion(같은 job 제외)이 대부분 흡수하나, 타 job 최근 promote는 다음 compare까지 안 잡힐 수 있음(수용 경계, backfill/재compare로 수렴).
- 추천: env-gate + eventual consistency를 수용 경계로 명시.

---

## 후속 (이 브리프 범위 밖)

- similarity threshold 실 캘리브레이션(fixture + live, sandbox 밖).
- character 별칭/동명이인 semantic 보강(2B.3 D2=A 확장).
- conflict/merge/split review queue 영속화, ⑤ Writing canonical 포함.

## 누적 오너 확인 대상 (이 slice가 해소)

- event/open_question을 identity 대조 제외(항상 create)로 둬 의미적 resolution 전까지 canonical/벡터가 중복 누적되던 것 — **이 slice(D1=A + D4)가 바로 그 해소 지점**이다. D4=off 기본이면 "인프라는 세우되 실 매칭은 fixture 후"라 누적은 캘리브레이션 완료 시 닫힌다.

## 결정 요약 (추천값)

| # | 결정 | 추천 |
|---|------|------|
| D1 | semantic seam 레이어 | A (compare `_find_matches`) — **헤드라인, 오너 확정** |
| D2 | query_similar 추가 | source_block 미러 + memory_type 필터 |
| D3 | query 벡터/주입 | 쓰기와 동일 projection·embedding, env-gate seam |
| D4 | threshold 정책 | A (보수적 off 기본, D2=B 선례) — **헤드라인, 오너 확정** |
| D5 | character 경로 | A (결정적 유지, semantic은 event/open_question 전용) |
| D6 | 다중 매칭 | A (top-1 비교, conflict 오탐 회피) |
| D7 | 품질 검증 | 계약+fake 증분 + 실 캘리브레이션 live 후속 |
| D8 | wiring | env-gate + eventual consistency 수용 경계 |

## Owner decisions — 2026-07-07

- **D1 = A.** semantic 매칭은 compare `_find_matches`에 들어간다(character=결정적 name key 유지, event/open_question=semantic). always-create 누적의 실제 지점이 compare이므로 이것이 문제를 해소한다. `PriorMemoryBackend`(2B.2 coarse 패키징)는 이 slice와 무관하며, HANDOFF/2B.2의 "PriorMemoryBackend 교체" 표현은 seam 위치를 부정확히 적은 것으로 정정한다.
- **D4 = A.** threshold는 주입값·기본 `None`(off). off면 event/open_question은 종전대로 always-create(회귀 보존·안전), threshold 설정 시에만 semantic 매칭이 켜진다. 실값은 실 embedding+실 데이터 fixture로 캘리브레이션 후 확정(auto-promotion threshold SoT v1.6.39 D2=B와 정합 — 추측값으로 canon 병합 금지). 이 slice는 seam+query 인프라를 안전하게 세운다.
- **D2 = 추천 잠금.** `query_similar(*, project_id, memory_type, vector, limit)`를 `MemoryVectorIndexAdapter` Protocol + in-memory fake + Chroma에 추가(source_block 미러 + memory_type 필터).
- **D3 = 추천 잠금.** candidate를 쓰기와 **동일한** `derive_memory_index_text` projection + 동일 embedding 모델로 embed해 query. compare에 embedding + memory vector search + threshold 주입(env-gate, judge와 같은 패턴).
- **D5 = A.** character는 결정적 name key 유지(2B.3 D2=A 존중), semantic은 event/open_question 전용.
- **D6 = A.** semantic은 top-1(최고 유사도, self-exclusion·canonical 필터 후) 1개만 matches로. conflict 오탐 회피(랭킹 특성). conflict는 judge가 낼 수 있음.
- **D7 = 추천 잠금.** 이 증분은 계약+fake(fake embedding)+회귀. 실 embedding threshold 캘리브레이션 fixture/live는 후속(sandbox 밖).
- **D8 = 추천 잠금.** compare endpoint 불변, `_default_compare_service`가 embedding+memory vector+threshold 있을 때 semantic matcher를 붙인다. read-after-write eventual consistency(방금 promote된 memory는 worker drain 전이라 미검색 가능)는 수용 경계(self-exclusion이 대부분 흡수, backfill/재compare로 수렴).
