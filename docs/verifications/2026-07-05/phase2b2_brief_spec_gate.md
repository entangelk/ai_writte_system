# Verification — Phase 2B.2 착수 브리프 스펙 게이트 검증

## Subject metadata

- 날짜: 2026-07-05
- 요청자: 오너 (“브리프 항목이 맞는지 검증을 안했었네. 읽어보고 검증하고 의심해줄래? 결정을 모두 기입했다”)
- 검증자: Claude Code (독립 감사)
- 대상: `docs/plans/02b-2-analysis-context-package-decisions.md` — Phase 2B.2 착수 결정 브리프. 상태 `Resolved (2026-07-05) — D1=A, D2=A(semantic seam), D3=A, D4=B(A 포함 hybrid), D5=A, D6=B`. 코드 착수 예정 2026-07-06.
- 정본 스펙 참조(교차 검증용):
  - `docs/plans/02b-analysis-compare-kickoff-decisions.md` §D6 (2B.2에 ⑧ 위임)
  - `docs/plans/04-agentic-search-kickoff-decisions.md` §8 (package 경계 A→C, ⑧ Analysis 절)
  - `docs/plans/04-context-package-completion-decisions.md` (⑧ 추적 이관: “memory type/scope, status/version, 검색 이유” 확장 필드)
  - `docs/plans/analysis-memory-taxonomy.md` (§비교용 ContextPackage 5필수, memory record 필드)
  - 2B.1 구현 `services/application/app/memory/models.py`(MemoryEntry 필드 — PriorMemoryItem 매핑 원천)
  - 기존 `services/application/app/context_search/models.py`(ContextSearchRequest/ContextPackage/ContextItem)
- 검증 대상 work source: working tree의 브리프 문서(신규/기입). **코드 착수 전 스펙 게이트 검증** — 구현 검증이 아님.

## Scope

브리프 **결정 항목 자체**의 적절성을 코드 구현과 분리해 검증:

1. **결정 항목 적절성**: D1~D6가 2B.2 slice 범위에 맞는가, 빠진 boundary는 없는가.
2. **결정 간 정합성**: 작업자 주장 “D1+D4+D6 상호 강화 / D5 error taxonomy 일치 / D4 2레이어 / 모순·이상 없음” 검증.
3. **선행 계약 정합**: 02b D6 위임, §8 ⑧ 추적, taxonomy 5필수, 2B.1 MemoryEntry 구조와 충돌 여부.
4. **문서 내부 일관**: 결정 본문 ↔ Owner decisions ↔ 요약표의 리터럴 일치.

## Methodology

CLAUDE.md의 스펙 검증 원칙을 브리프에 적용 — “cross-check the contract against itself”, “선행 계약과 정합”, “boundary matrix에 빈 칸 없음”. 코드를 먼저 보지 않고 선행 계약에서 lock list를 세운 뒤 브리프 결정을 매핑.

```bash
# 브리프 본문 + 결정 독해
sed -n '1,121p' docs/plans/02b-2-analysis-context-package-decisions.md

# 선행 계약 교차
sed -n '93,104p' docs/plans/02b-analysis-compare-kickoff-decisions.md          # 02b D6 위임
sed -n '81,101p' docs/plans/04-context-package-completion-decisions.md         # ⑧ 추적 이관(확장 필드)
sed -n '45,95p'  docs/plans/analysis-memory-taxonomy.md                        # memory record + 비교용 5필수
grep -n "⑧\|analysis_context\|§8\|package 경계" docs/plans/04-agentic-search-kickoff-decisions.md

# 2B.1 MemoryEntry ↔ PriorMemoryItem 매핑 원천
# services/application/app/memory/models.py (MemoryEntry 필드)
# 기존 ContextSearchRequest/ContextPackage/ContextItem 구조
sed -n '70,160p' services/application/app/context_search/models.py

# 문서 내부 리터럴 일치 (D6 경로 등)
grep -n "analysis/context\|jobs/{job_id}/context\|/context" docs/plans/02b-2-analysis-context-package-decisions.md
```

## Boundary matrix (선행 계약에서 도출한 lock list)

| # | 선행 계약 요구 | 브리프 대응 | 상태 |
|---|---|---|---|
| L1 | 02b D6: 2B.2에서 `purpose="analysis_context"` 신설 | slice 범위 첫 항목 + D3 본문 | ✓ |
| L2 | 02b D6: ⑧ 비교용 package 필드 확정 | D3 PriorMemoryItem 7필드 | ✓(단 scope — L6) |
| L3 | 04-context-package ⑧ 이관: 확장 필드 “memory type/**scope**, status/version, 검색 이유” | memory_type/value/status/version/source_ref_ids/match_reason | **scope 누락(F2)** |
| L4 | §8 A→C: 단일 schema + purpose 분기 | D3=A 단일 ContextPackage 확장 | ✓ |
| L5 | 04-context-package D3 추천: `prior_memory` need 신설 | ContextNeed.PRIOR_MEMORY | ✓ |
| L6 | 02b D3=A: 결정적 key(memory_type+scope_type+scope_id+정규화 name) | D1=A coarse(project+memory_type), scope은 2B.3 위임(헤드라인 긴장 명시) | ✓(경계 명시적) |
| L7 | taxonomy 비교용 5필수: 값·상태·source·version·비교 이유 | value/status/source_ref_ids/version/match_reason | ✓ |
| L8 | D5=A(02b) Analysis AI “canon 확정 금지” 경계 유지 | prior-memory는 canonical만 조회 → AI가 canon 안 만듦 | ✓ |
| L9 | 2B.1 MemoryEntry 필드 → PriorMemoryItem 매핑 가능 | value↔payload 매핑 + provenance/confidence 누락 | **spec-silent(F3)** |
| L10 | Gate purpose 분기 구조 (ContextPackage.purpose 존재) | D5=A purpose별 Gate 규칙 분기 | ✓(구조 존재, 단 F5) |

## Findings

### 1. 선행 계약 정합 (양호)

- **L1/L4/L5/L8**: 02b D6 위임(analysis_context purpose + ⑧ 필드)을 충실히 회수. §8 A→C 단일 schema 원칙 유지. `prior_memory` need 신설. Analysis AI 경계(canonical만 조회) 유지. 모두 정합.
- **L6 헤드라인 긴장 명시적 해소**: 브리프 §“헤드라인 긴장”(line 17-21)이 “2B.2가 2B.3 identity 매칭에 의존해 보인다”는 순서 의존성을 CLAUDE.md §1에 따라 명시하고, D1=A(coarse 후보군 → 정밀 판정)로 해소. 이것은 모범 사례 — 추측 봉합이 아니라 긴장을 드러내고 방향을 정함.
- **D4 2레이어 논리 타당**: 작업자 주장대로 D4 A/B는 경쟁이 아니라 “primitive=memory_type(A) 위에 job-aware 진입면(B)을 얹는” 2레이터. D6=B(HTTP)와 정합. 오너 근거 “compare LLM에 파라미터가 흘러들어가야 하므로 primitive와 job-context 진입면 둘 다 필요” 합리적.
- **D5 error taxonomy 방향 일치**: purpose/단계별 Gate 분기는 기존 error taxonomy(`backend/system/llm/sot_error`) 분기와 같은 방향. 작업자 주장 참.

### 2. 기존 코드와의 호환 (양호, 단 착수 디테일)

- `ContextPackage.purpose` 필드가 이미 존재(`models.py:146`) → D5 purpose 분기 구현 가능.
- `ContextSearchRequest.query`는 현재 **필수 str**(`models.py:79-84`). D4 추천 “재사용하되 analysis_context에서 query/current_position optional”은 호환성 변경을 수반. 브리프가 이를 인지하고 “optional 처리 필요”로 명시했으므로 착수 디테일로 남음 — 비차단.

### 3. 결정 항목 적절성

D1~D6는 2B.2 slice 범위(검색+패키징, 판정/semantic/scope-key/upsert/⑤는 제외)에 적절. “하지 않는 것” 명시(line 30)가 추측 구현을 막는 게이트로 기능. 빠진 boundary 후보는 아래 Issues에서 다룬다.

## Issues / Risks

### F1. [NON-BLOCKING — 문서 내부 모순, 착수 전 정정] D6 엔드포인트 경로 불일치

D6 HTTP 경로가 브리프 내에서 두 가지로 적혀 있다:

- 본문 D6=B 표 (line 94): `POST /projects/{id}/analysis/context` — **job 없음**
- Owner decisions D6 (line 110): `POST /projects/{project_id}/analysis/jobs/{job_id}/context` — **job 있음**

D4=hybrid(job-aware 진입면)와 정합하려면 Owner decision의 job 단위 경로가 맞다. 본문 D6 표의 경로는 D4=A(단순 memory_type 파라미터) 시대의 stale 표면으로 보인다. 작업자 요약(오너에게 보고한 내용)도 `/analysis/jobs/{job_id}/context`로 job 단위를 썼다.

→ concrete한 문서 내부 모순. 착수 전 1줄 정정 권고(본문 D6 표의 경로를 job-aware로, 또는 D6 선택지 자체를 “service-only / job-aware HTTP”로 재구성). CLAUDE.md “문서 내부 모순은 blocking” 원칙을 스펙 문서에 엄격 적용하면 착수 전 닫는 것이干净하나, 결정 자체(D6=B, job 단위)는 Owner decision에 명확하므로 구현 착오로 이어질 가능성은 낮다 → non-blocking 정정.

### F2. [NON-BLOCKING — 오너 확인 권장] §8 ⑧ 추적 닫힘 주장 vs scope 누락

D3 본문/요약이 “§8 C 완성”이라고 주장한다. 그러나 04-context-package-completion “Phase 2B가 이어받는 항목”이 2B.2에 위임한 ⑧ 확장 필드는 **“기존 memory type/scope, status/version, 검색 이유”**다(`04-context-package-completion-decisions.md:100`). 매핑:

- memory_type ✓ / value(기존 값) ✓ / status ✓ / version ✓ / source_ref_ids(source) ✓ / match_reason(검색 이유) ✓
- **scope(scope_type/scope_id) — 누락**

D1=A가 scope 정밀화를 2B.3에 위임했으므로, PriorMemoryItem에 scope 필드가 없다. 이것 자체는 D1 경계와 정합하지만, **§8 ⑧ 추적 항목의 “scope” 확장 필드가 2B.2에서 닫히지 않고 2B.3으로 넘어간다**. 따라서 브리프의 “⑧ 완성” 주장은 과장이다.

두 해석이 가능:

- (a) §8 ⑧의 “scope”는 “검색 key 정밀화” 문제(2B.3 소관)이지 “package 필수 필드”가 아니므로, 2B.2가 package 5필수를 채워 ⑧ package 절은 닫고 scope은 2B.3으로 추적을 좁힌다 — 그렇다면 “⑧ 완성”이 아니라 “⑧ package 필드 완성, scope은 2B.3 추적 유지”로 정확히 기술해야.
- (b) compare(2B.3)가 package에서 scope 정보를 필요로 하면 PriorMemoryItem에 scope_type/scope_id를 지금이라도(coarse라도) 추가해야.

→ 오너 확인 권장: ⑧ 추적 항목을 2B.2에서 닫는 것으로 볼 것인지(그러면 문구 정정), 아니면 scope 추가로 ⑧을 실제로 닫을 것인지. 어느 쪾이든 현재 “§8 C 완성” 문구는 정정 필요.

### F3. [NON-BLOCKING — spec-silent 매핑] PriorMemoryItem.value 출처 + provenance/confidence 누락

- **value ↔ payload 매핑 미정의**: PriorMemoryItem.value의 원천이 spec-silent. 2B.1 `MemoryEntry`는 `value` 필드가 없고 `payload: Mapping[str, Any]`를 가진다(`memory/models.py:40`). D3 본문이 “기존 값(payload)”라고 짚지만, value가 scalar인지 structured Mapping인지, 직렬화에서 어떻게 담기는지 명시 안 됨. “value”라는 이름이 scalar를 암시해 착수 시 혼란 가능. 착수 전 “value = payload(Mapping) 그대로”로 명시 권고.
- **provenance/confidence 누락**: MemoryEntry는 `provenance`/`confidence`를 가지나 PriorMemoryItem(7필드)엔 없다. §8 ⑧/taxonomy 5필수에는 provenance/confidence가 없으므로 계약 위반은 아니다. 그러나 2B.3 compare 판정이 “ai_inferred vs source_observed” `provenance`나 `confidence`에 의존하면(예: 낮은 confidence canon은 update 우선), 2B.3에서 다시 필드를 추가하게 됨. 지금은 §8 ⑧이 안 요구하므로 non-blocking이나, 착수 시 “2B.3 compare가 필요로 하면 확장”을 열어둘 것.

### F4. [NON-BLOCKING — untested boundary] D4 job-aware 진입면의 self-match 위험

D4 hybrid의 진입면이 “그 job이 만든 memory_type 집합”을 유도해 해당 type canonical을 조회한다. 그런데 **2B.1 auto-promote로 같은 job의 candidate가 이미 canonical memory로 승격됐다면, 그 memory 자신이 prior-memory 검색 결과에 포함**된다. compare(2B.3)가 “이 candidate와 같은 대상 = 방금 승격된 자기 자신”을 판정하게 되는 self-match.

브리프가 이 self-exclusion 경계를 정의하지 않는다. “prior-memory”의 정확한 정의(“현재 job 이전에 존재한 canonical” vs “현재 canonical 전체”)도 미정. 착수 시 (a) 조회가 현재 job의 `analysis_job_id != 조회 대상 memory.analysis_job_id` 조건으로 self-exclude하거나, (b) compare(2B.3)가 self-match를 `no_change`로 처리하는 규칙이 필요. 회귀로 lock 권고.

### F5. [NON-BLOCKING — 결정 일부가 착수로 이관] D5 Gate 적용 시점 미확정

D5 본문 마지막이 “단 첫 slice에서 Gate를 analysis_context에 확장할지, 아니면 조회 자체가 project-scoped라 Gate 없이 충분한지는 **구현 시 최소로 정한다**(과설계 회피)”로 마무리. 즉 D5는 “purpose 분기 **구조**를 둔다”까지만 결정하고, “이 slice에서 Gate를 analysis_context에 실제 적용하는가”는 착수로 미뤘다. 결정 항목의 일부가 미결정 상태로 남음. 착수 시 이것을 확정하고 회귀로 lock할 것. (참고: 현재 모든 MemoryEntry가 `status=canonical` 단일이므로, status 기반 Gate 분기는 사실상 no-op이나, 중간 status(`confirmed`) 도입 시 의미를 가짐.)

## Verdict

**조건부 승인 (conditional approval) — 착수 전 정정/확정 권고.**

- 선행 계약 회수와 slice 경계 설정은 양호: 02b D6 위임, §8 A→C, taxonomy 5필수, `prior_memory` need, D5=A enum 정신을 충실히 반영했고, D1 헤드라인 긴장(2B.2↔2B.3 순서 의존)을 명시적으로 드러내 해소한 점은 모범적. D4 2레이어 논리 타당, D5 error taxonomy 방향 일치. 작업자 “모순·이상 없음” 주장은 대체로 성립.
- **단, “모순 없음”은 정확하지 않다**: F1(D6 경로 본문↔Owner 불일치)이 브리프 내부 모순. 착수 전 정정.
- F2(§8 ⑧ “완성” 주장 vs scope 누락)는 오너 확인이 필요한 계약 해석 — ⑧ 추적을 2B.2에서 닫는지 2B.3까지 열지 정해야.
- F3(value↔payload 매핑·provenance/confidence 누락), F4(self-match), F5(Gate 적용 시점)는 착수 중 명시/회귀로 닫을 수 있는 non-blocking.
- 코드 착수 전 F1 정정 + F2 오너 확인이 정리되면 승인.

## Outstanding items

- **F1**: 본문 D6 표의 엔드포인트 경로를 job-aware(`/analysis/jobs/{job_id}/context`)로 정정(착수 전).
- **F2**: §8 ⑧ 추적 닫힘 범위 오너 확인 — (a) “⑧ package 5필수 완성, scope은 2B.3 추적”으로 문구 정정, 또는 (b) PriorMemoryItem에 scope_type/scope_id 추가. SoT ⑧ 추적 항목의 닫힘도 이 결정에 맞춰 기록.
- **F3**: 착수 시 value=payload(Mapping) 매핑 명시 + 2B.3 compare의 provenance/confidence 의존도 평가(필요시 PriorMemoryItem 확장).
- **F4**: 착수 시 self-match 회피 경계 정의 + 회귀(`analysis_job_id` 기반 exclude 또는 2B.3 `no_change` 규칙).
- **F5**: 착수 시 analysis_context Gate 적용 여부 확정 + 회귀.
- SoT 결정 엔트리: 오너가 “결정만” 진행했으므로 **현재 SoT 미변경은 의도적**(착수 시 v1.6.41로 반영 예정). 본 검증은 이 워크플로를 이슈로 보지 않는다.

## Reproduction

```bash
# 브리프 독해
sed -n '1,121p' docs/plans/02b-2-analysis-context-package-decisions.md

# F1 재현: D6 경로 두 곳 비교
grep -n "analysis/context\|jobs/{job_id}/context" docs/plans/02b-2-analysis-context-package-decisions.md
# line 94(본문): /projects/{id}/analysis/context          (job 없음)
# line 110(Owner): /projects/{project_id}/analysis/jobs/{job_id}/context  (job 있음)

# F2 재현: §8 ⑧ 위임 필드 vs PriorMemoryItem
sed -n '100p' docs/plans/04-context-package-completion-decisions.md   # "memory type/scope, status/version, 검색 이유"
grep -n "PriorMemoryItem\|memory_id/memory_type/value" docs/plans/02b-2-analysis-context-package-decisions.md
# → PriorMemoryItem 7필드에 scope_type/scope_id 없음

# F3 재현: MemoryEntry 필드(value 없음, payload 있음)
grep -n "value\|payload\|provenance\|confidence" services/application/app/memory/models.py

# 선행 계약 정합(양호) 재현
sed -n '93,104p'  docs/plans/02b-analysis-compare-kickoff-decisions.md
sed -n '45,95p'   docs/plans/analysis-memory-taxonomy.md
sed -n '70,150p'  services/application/app/context_search/models.py
```
