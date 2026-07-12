# 검증 기록 — Phase 6 Context Gate finding 영속화 (SoT v1.6.65)

## Subject metadata

- **날짜**: 2026-07-12
- **요청자**: 오너(사용자). 요청: "작업 AI가 작업한 부분 확인하고 검증하고 의심하고 또 의심해줄래? 적대적 검증과 비차단 항목까지 포함해서." 주요 변경: reject Gate finding만 영속화, 공통 저장 모델, `/context-search` 필수 `idempotency_key`, 결정적 finding ID + replay 중복 방지, 저장 실패 → 502, open → resolved|dismissed 동일 terminal replay 멱등 / cross-terminal → 409, candidate action 자동 연동 없음, request/result SHA-256 fingerprint + 안정 pointer ID 저장, Review Inbox에 `gate_findings` additive, Gate 전용 list/detail API, resolve/dismiss API, Mongo/in-memory repository.
- **검증자**: Claude(독립 감사 — 구현 작업자 아님)
- **대상 slice/artifact**: Phase 6 Context Gate finding 영속화 + Review Inbox 통합. 구현 `services/application/app/context_search/gate_findings.py`(신규 188줄)·`gate_findings_mongo.py`(신규 62줄)·`main.py`(route 4 + helper + wiring, +106줄). 회귀 `tests/test_gate_findings.py`(신규 2)·`tests/test_context_search_api.py`(+3 게이트 회귀). 계약 갱신 SoT v1.6.65·브리프 `plans/06-gate-finding-persistence-decisions.md`(신규, D1~D8 승인)·`plans/06-review-ui.md`(checkbox)·`docs/mongo_collections.md`·`scripts/phase4_context_search_deployed_smoke.py`·기타 fixture 3종 `idempotency_key` 반영.
- **정본 계약 참조**: `docs/system-contract-sot.md` v1.6.65(버전 테이블). 승인 브리프 `plans/06-gate-finding-persistence-decisions.md` D1~D8=A + §9 첫 회귀 매트릭스. 선행: Review Inbox v1.6.64·candidate 상태 전이 v1.6.61.
- **소스**: working tree, uncommitted(`e48342c` v1.6.64 Review Inbox 백엔드 위).

## Scope

1. **계약 자체 일관성** — SoT v1.6.65 ↔ 브리프 D1~D8 ↔ §9 회귀 목록 ↔ `06-review-ui.md` checkbox 정합. 승인 경계(reject-only + pass 확장 여지, 502, 멱등/lifecycle, 자동 연동 없음, 최소 envelope, additive + Gate API) 교차 검증.
2. **D1 reject-only 영속화** — `persist_rejection`의 pass 가드 + 향후 pass 감사 이력 확장 여지(Gate result origin/fingerprint 보존).
3. **D2 persistence 실패 → 502** — `GateFindingError` 매핑 경로 + handler try/except 범위.
4. **D3 idempotency** — `/context-search` 필수 `idempotency_key`, 빈 값 거부, 결정적 ID 알고리즘 `(project_id, key, ordinal, check)` canonical JSON SHA-256, project 격리.
5. **D4 lifecycle** — open→resolved/dismissed, same-terminal replay 멱등, cross-terminal 409, backward 금지.
6. **D5 자동 연동 없음** — candidate action ↔ Gate finding 상태 분리.
7. **D6 저장 payload** — request/result SHA-256 fingerprint + 안정 pointer ids + clock 주입 timestamp.
8. **D7 Review Inbox 표현** — 기존 `items` 불변 + `gate_findings` additive + `origin=context_gate` + Gate 전용 list/detail API.
9. **D8 public API** — inbox 통합, Gate list/detail, resolve/dismiss 동일 slice.
10. **회귀 품질** — 결정 브리프 §9 회귀 매트릭스 6종 under/over-strict + boundary matrix 빈 셀 점검.
11. **전체 suite 재현** — 778/48 독립 재실행.
12. **Mongo adapter 검증 범위** — 다른 Mongo 레포와의 live/index 테스트 일관성.
13. **적대적** — fingerprint 결정성 직접 재계산, replay silent-override 위험, contract 자체 모순.

## Methodology

```bash
# 1. 변경 범위
git status; git diff --stat
# 신규: gate_findings.py, gate_findings_mongo.py, test_gate_findings.py, 06-gate-finding-persistence-decisions.md

# 2. 계약 원문 end-to-end (스코프: 브리프 D1~D8 + §9 + SoT v1.6.65 changelog + 06-review-ui checkbox)
# Read docs/plans/06-gate-finding-persistence-decisions.md (전체)
git diff docs/system-contract-sot.md docs/plans/06-review-ui.md docs/mongo_collections.md

# 3. 구현 원문
# Read services/application/app/context_search/gate_findings.py (전체 188줄)
# Read services/application/app/context_search/gate_findings_mongo.py (전체 62줄)
git diff services/application/app/main.py                       # route 4 + helper + wiring + 502/400 매핑
sed -n '1931,2005p' services/application/app/main.py            # context-search endpoint + _build_context_search_request

# 4. 회귀 원문
# Read tests/test_gate_findings.py (전체 87줄)
git diff tests/test_context_search_api.py tests/test_analysis_context_api.py tests/test_context_search_shared_index.py scripts/phase4_context_search_deployed_smoke.py

# 5. ★ focused 회귀 독립 재실행
python3 -m pytest tests/test_gate_findings.py tests/test_context_search_api.py -q -p no:cacheprovider

# 6. ★ 전체 suite 독립 재실행
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# 7. fingerprint 결정성·격리·구분성 직접 재계산(추측 금지 — 알고리즘 재실행)
python3 -c "from ...gate_findings import derive_gate_finding_id; ..."   # 5가지 입력 변형

# 8. idempotency_key pattern sweep — 모든 /context-search 호출 지점 누락 여부
grep -rn "context-search" --include="*.py" tests/ scripts/

# 9. D4 패턴 일관성 — 기존 review queue lifecycle(OPEN/RESOLVED/DISMISSED)·candidate transition idempotent_replay 대조
grep -n "RESOLVED\|DISMISSED\|idempotent_replay" services/application/app/analysis/review_queue.py services/application/app/analysis/candidate_review.py

# 10. 결정 브리프 §9 회귀 매트릭스 — 6종 각각 traced regression 존재 추적
grep -rn "candidate.*finding\|inbox\[.items.\|items\b" tests/test_context_search_api.py tests/test_analysis_apply_api.py
```

## Findings

### 1. 계약 자체 일관성 — PASS

SoT v1.6.65 changelog(`docs/system-contract-sot.md` line 35-36) ↔ 브리프 승인 결과 D1~D8(line 137-144) ↔ `06-review-ui.md` checkbox(line 72) 교차 읽기. 모순 없음.

- changelog "reject finding만 durable store" ↔ D1=A; "pass 감사 이력과 immutable GateRun manifest는 확장 가능 후속"이 D1 부가("pass 감사 이력 저장을 추가할 수 있게") 및 D6 후속 메모(line 146-156)와 정합.
- "persistence 실패 502" ↔ D2=A. "필수 idempotency key / 결정적 finding id" ↔ D3=A. "open→resolved/dismissed / candidate action 자동 연동 없음" ↔ D4=A·D5=A.
- "request/result fingerprint와 안정 pointer ids" ↔ D6=A. "기존 inbox items 불변 + gate_findings additive / Gate list/detail/resolve/dismiss API" ↔ D7=A·D8=A.

### 2. D1 reject-only — PASS (코드 + 회귀)

- 코드 `gate_findings.py:88-89`: `if gate.decision != "reject": return ()`. pass는 저장 0건.
- 확장 여지 보존: `persist_rejection`이 pass 분기에서도 `request`/`package`/`gate`를 인자로 받으며, `result_fingerprint`가 `decision`·`findings`·`package_status`를 포함(`gate_findings.py:104-112`)해 Gate result origin을 보존 → 향후 pass 감사 이력 추가 시 동일 모델 재사용 가능(D1 부가 조건 충족).
- 회귀: `test_gate_findings.py:37-41` `test_pass_is_not_stored_and_reject_replay_is_idempotent`에서 pass → `()` 단언(under-strict). over-strict 방어(정상 reject가 pass로 잘못 무시되는 경우)는 동일 테스트의 `len(self.repo.entries) == 2`(line 53)가 함께 잠금.

### 3. D2 persistence 실패 → 502 — PASS (코드 + 회귀)

- handler `main.py:1956-1962`: `persist_rejection`을 내부 try로 감싸 `except Exception as exc: raise GateFindingError(str(exc)) from exc`.
- 외부 매핑 `main.py:1972-1975`: `except GateFindingError as exc: raise HTTPException(status_code=502, detail=f"gate finding persistence failed: {exc}")`.
- 회귀: `test_context_search_api.py:199-214` `test_gate_finding_persistence_failure_is_502`가 `_FailingGateFindingService`로 `RuntimeError`를 주입 → 502 + detail `"persistence failed"` 포함 단언. 실제 repository 예외 경로(replace_one 실패 등)가 아닌 stub 예외지만, 매핑 자체를 잠금.

### 4. D3 idempotency — PASS (코드 + 회귀 + 알고리즘 입증)

- 필수화: `main.py:748` `ContextSearchHttpRequest.idempotency_key: str`(default 없음 → pydantic 필수). 빈 값 거부 `main.py:1984-1985` `if not body.idempotency_key.strip(): raise ValueError` → 매핑 `main.py:1940-1941` `except ValueError → 400`.
- 결정적 ID: `gate_findings.py:165-170` `derive_gate_finding_id` = `"gf:" + sha256(canonical_json({project_id, idempotency_key, ordinal, check}))`. canonical JSON = `sort_keys=True, separators=(",",":")`(`gate_findings.py:173-176`). 계약 D3 "canonical JSON SHA-256"과 정합.
- **직접 재계산 입증**(추측 금지):
  - deterministic(동일 입력 2회): `a == b` True.
  - cross-project 격리(`p1`/`p2` 같은 key): `a != c` True.
  - ordinal 구분(ordinal 0 vs 1 같은 check): `a != d` True.
  - key 구분(같은 project 다른 key): `a != e` True.
  - prefix: `"gf:"`.
- 회귀: `test_gate_findings.py:70` `assertNotEqual(finding.id, other.id)`(cross-project 격리) + `:52` 동일 key replay `first == replay`(무중복). `test_context_search_api.py:259-262` `test_empty_idempotency_key_is_400`(빈 값 → 400, under-strict).

### 5. D4 lifecycle — PASS (코드 + 회귀)

- `gate_findings.py:149-162` `transition`:
  - `target is OPEN → raise InvalidGateFindingTransition`(backward 금지, line 152-153).
  - `finding.status is target → return finding, True`(same-terminal 멱등, line 154-155).
  - `finding.status is not OPEN → raise InvalidGateFindingTransition`(cross-terminal 409, line 156-159).
  - 정상 전이 시 `replace(..., status=target, terminal_at=clock())`(line 160-162).
- 매핑 `main.py:1810-1812` `except InvalidGateFindingTransition → 409`.
- 패턴 일관성: `analysis/review_queue.py:35-41` `ReviewQueueStatus`(OPEN/RESOLVED/DISMISSED)와 동일 세 상태, `candidate_review.py:47` `idempotent_replay: bool` 시맨틱과 일치 → 브리프 D4 "v1.6.61 review queue lifecycle과 같은 패턴 재사용" 충족.
- 회귀: `test_gate_findings.py:71-86`(resolved 성공 `replay=False` · same-terminal replay `replay=True` · cross-terminal `assertRaises(InvalidGateFindingTransition)`) + API 수준 `test_context_search_api.py:247-258`(resolve 200 · repeat `idempotent_replay=True` · dismiss after resolve → 409). under/over-strict 양방향 잠김.

### 6. D5 자동 연동 없음 — 코드 구조적 충족, **회귀 부재 (조건부 합격 조건 #1)**

- 코드: `candidate_review.py`·`review_queue.py` 어디에도 `gate_findings` 참조 없음. 구조적으로 분리됨(자동 연동 로직 부재 = D5=A 충족).
- **그러나 브리프 §9 회귀 목록(line 122)이 "candidate action이 finding 상태를 바꾸지 않음"을 명시적으로 요청했는데, 이를 검증하는 회귀가 없다.** candidate confirm/reject 호출 후에도 gate finding이 `OPEN`으로 유지됨을 잠그는 end-to-end 회귀 부재. 향후 누군가 `candidate_review.py`에 `gate_findings.transition` 호출을 실수로 넣어도 아무 테스트가 잡지 못함(cross-component 부정적 boundary 미보호).
- 빈 셀: 브리프 §9.5 해당.

### 7. D6 저장 payload — PASS (코드 + 회귀)

- `request_fingerprint` = sha256({project_id, query, purpose, needs, current_position})(`gate_findings.py:92-103`).
- `result_fingerprint` = sha256({decision, findings[{check, detail}], package_status, token_estimate_total})(`gate_findings.py:104-112`).
- 안정 pointer ids: `gate_findings.py:179-187` `_pointer_ids`가 `source_ref_ids` ∪ `snapshot_id` ∪ `pointer.document_id` ∪ `pointer.version_id`를 정렬 튜플로 수집. Mongo SOT 정본 재조회용 안정 id 한정(D6=A "ContextPackage 전체 snapshot 저장 아님" 경계 존중).
- clock 주입: `gate_findings.py:80-83` `GateFindingService(repository, *, clock=None)` → 기본 `datetime.now(UTC)`. D6 "created_at/terminal timestamp는 repository clock 주입값" 충족.
- 회귀: `test_gate_findings.py:54-55` `request_fingerprint`/`result_fingerprint` non-empty 단언. fingerprint 알고리즘 자체는 본 검증의 직접 재계산(findings §4)으로 입증.

### 8. D7 Review Inbox 표현 — 코드 충족, **items 불변 회귀 부재 (조건부 합격 조건 #2)**

- `main.py:1756-1759`: 기존 `items`(candidate 행)는 그대로 두고 `gate_findings` 키 추가(additive).
- `_gate_finding_payload`(`main.py:1778-1801`)에 `"origin": "context_gate"`(line 1780). 계약 D7 "origin=context_gate"과 정합.
- Gate 전용 API: `GET .../analysis/gate-findings`(list, `main.py:1803-1811`)·`GET .../analysis/gate-findings/{finding_id}`(detail, `main.py:1813-1818`).
- 회귀: `test_context_search_api.py:242-243` `inbox["gate_findings"]` + `finding["origin"] == "context_gate"` + `finding["check"]`(additive + origin 잠금).
- **그러나 브리프 §9(line 123)가 "기존 inbox items envelope 불변"을 명시적으로 요청했는데, 이를 검증하는 회귀가 없다.** `test_reject_persists_to_inbox_and_transitions`의 fixture에는 candidate items가 없어서, additive 추가 시 기존 `items`가 보존됨을 검증할 수 있는 테스트가 아예 없음. 빈 셀: 브리프 §9.6 해당. candidate items가 있는 inbox에서 gate_findings를 추가해도 items 배열(envelope)이 불변임을 잠르는 회귀 필요.

### 9. D8 public API — PASS (코드 + 회귀)

- resolve/dismiss: `main.py:1819-1829`가 공용 `_transition_gate_finding`(`main.py:1803-1817`) 호출 → 동일 404/409/멱등 매핑. 계약 D8 "inbox 통합, Gate list/detail, resolve/dismiss 같은 slice" 충족.
- 회귀: `test_context_search_api.py:244-258` resolve 200 · idempotent replay · dismiss 409.

### 10. 회귀 품질 — focused 재현 PASS, **§9 매트릭스 2종 빈 셀**

- focused 독립 재실행: `tests/test_gate_findings.py tests/test_context_search_api.py` → **14 passed**(작업 AI "focused 41"은 service 레벨 회귀까지 포함한 더 넓은 범위; 본 검증은 게이트 직접 회귀 14종으로 한정 재현).
- 결정 브리프 §9 회귀 매트릭스 추적 결과:
  - §9.1 pass 저장 없음 / reject N개 저장 → 잠김.
  - §9.2 same-key replay 무중복 / cross-project 격리 → 잠김.
  - §9.3 persistence 실패 → 502 → 잠금.
  - §9.4 same-terminal replay 멱등 / cross-terminal 409 → 잠김.
  - **§9.5 candidate action이 finding 상태 변경 안 함 → 빈 셀**(Findings §6).
  - **§9.6 기존 inbox items envelope 불변 → 빈 셀**(Findings §8).
- 추가 빈 셀: gate-findings detail/list/resolve/dismiss의 **404 분기**(없는 project·없는 finding)가 코드에 구현됨(`main.py:1806-1807, 1814-1815, 1809-1811` `except (NotFound, GateFindingNotFound) → 404`)에도 불구하고, 이를 잠그는 회귀가 없다. cross-terminal 409는 잠겨 있는데 404는 잠기지 않은 비대칭.

### 11. 전체 suite 재현 — PASS

`python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **778 passed / 48 skipped / 99 subtests passed**(11.89s, exit 0). 작업 AI 보고(778/48)와 정확히 일치.

### 12. Mongo adapter 검증 범위 — 비차단 관찰

- `gate_findings_mongo.py:14-17`이 compound index `gate_findings_by_project_status`를 생성하나, 이를 검증하는 테스트가 없다.
- 다른 Mongo 레포는 `test_core_sot_mongo.py`·`test_analysis_mongo.py`·`test_memory_mongo.py`·`test_indexing_mongo.py` 및 각 `*_mongo_indexes.py` 단위 테스트를 가짐. `MongoGateFindingRepository`는 in-memory repository(`test_gate_findings.py`)로만 검증되어, live Mongo 위에서의 tz-aware datetime round-trip·`_id` 충돌 처리·index 생성·`list_open` 정렬이 실경로 검증되지 않음.
- `main.py:295-303` `_default_gate_finding_service()`가 `CORE_SOT_MONGO_URI` env로 Mongo adapter를 생성하는 wiring도 테스트에서 미검증(모든 테스트가 주입된 service 또는 in-memory 기본값 사용). sandbox live-Mongo 제약과 일관된 회피이지만, 다른 레포가 최소한 `*_mongo_indexes.py`를 두는 패턴과의 차이.

### 13. 적대적 — PASS

- **fingerprint 결정성**: 본 검증이 직접 재계산(findings §4) — deterministic·격리·구분성 모두 입증.
- **replay silent-override 위험**: 같은 `idempotency_key`로 detail이 다른 finding이 오면, `gate_findings.py:120-123`이 `existing`을 반환해 새 detail을 무시. 이는 D3 "retry 중복 방지" 의도에 부합(client가 같은 key를 재사용하면 의도적 replay). 다만 같은 key로 의도적으로 다른 결과를 보내면 silent하게 첫 결과로 동결됨 — 계약 경계 내(client 책임).
- **contract 자체 모순**: 없음(findings §1).
- **idempotency_key pattern sweep 누락**: `/context-search`를 HTTP로 호출하는 모든 fixture(`test_context_search_api.py` `_body`, `test_context_search_shared_index.py` `_search_body`, `test_analysis_context_api.py:248`, `scripts/phase4_context_search_deployed_smoke.py:103`)에 key 반영 확인. 특히 `test_analysis_context_api.py:245-257` `test_analysis_context_purpose_rejected_on_writing_endpoint`에 key 추가(`"analysis-purpose-reject"`)한 것은 정확한 수정 — key 없으면 pydantic 422로 purpose 거부(400) 검증이 idempotency_key 검증 전에 먹혀 purpose 분기를 잠그지 못했을 것. service 레벨 테스트(`test_context_search*.py` 대부분)는 도메인 `ContextSearchRequest`를 직접 생성하므로 key 불필요(`ContextSearchRequest`는 `idempotency_key` 필드가 없음 — HTTP 레이어에만 존재, 설계 일관적).

## Issues / Risks

- **[BLOCKING-CONDITION #1] 결정 브리프 §9.5 회귀 부재**: "candidate action이 finding 상태를 바꾸지 않음" 회귀 없음. D5=A(자동 연동 없음)는 코드 구조로 충족하나, 브리프가 명시한 부정적 boundary lock이 빠져 cross-component 회귀 보호 없음. candidate confirm/reject API 호출 후 관련 gate finding이 `OPEN`으로 유지됨을 잠르는 회귀 필요(under-strict: 연동이 실수로 추가되면 재실패; over-strict: 정상 분리 케이스 확인).
- **[BLOCKING-CONDITION #2] 결정 브리프 §9.6 회귀 부재**: "기존 inbox items envelope 불변" 회귀 없음. D7=A(additive)는 코드로 충족하나, candidate items가 있는 inbox에서 `gate_findings` 추가 후 기존 `items` 배열이 불변임을 잠르는 회귀 필요(under-strict: additive가 items를 깨면 재실패; over-strict: gate_findings만 추가되고 items는 동일).
- **[NON-BLOCKING] 404 boundary 회귀 부재**: gate-findings detail/list/resolve/dismiss의 없는 project·없는 finding → 404 분기가 코드에 있으나 회귀 없음. cross-terminal 409와의 비대칭. contract prose에 404가 명시되지 않았으므로(spec-silent-but-code-enforced 경계), contract에 404를 명시하거나 회귀를 추가해 경계를 닫는 것을 권장.
- **[NON-BLOCKING] Mongo adapter live/index 검증 부재**: findings §12. 다른 Mongo 레포 패턴과의 차이. sandbox 제약이 일부 설명하나, 최소한 `gate_findings_by_project_status` index 생성 검증(`*_mongo_indexes.py`류)이 일관성 관점에서 권장.
- **[NON-BLOCKING] `persist_rejection` 예외 재래핑**: `main.py:1961-1962` `except Exception`이 이미 `GateFindingError`인 예외도 문자열로 재래핑. 기능적 영향 없음(실제 발생 경로는 repository RuntimeError → GateFindingError 래핑이 전부). 경미.
- **[NON-BLOCKING] backward 전이 dead path**: `gate_findings.py:152-153` `target is OPEN → raise` 분기는 open으로 가는 API가 없어 도달 불가능한 방어 코드. 무해.

## Verdict

**조건부 합격 (Conditional Pass)**.

이유(load-bearing):

1. 핵심 계약 D1~D4·D6·D8은 코드 구현 + traced regression으로 잠겼고, fingerprint 결정성은 본 검증이 독립 입증했으며, 전체 suite 778 passed를 재현했고, 계약 자체 일관성에 모순이 없다. 시스템은 건전하게 동작한다.
2. **그러나 정본 계약(승인 브리프 §9)이 명시적으로 요구한 회귀 매트릭스 6종 중 2종(§9.5 candidate action 영향 없음, §9.6 inbox items 불변)이 누락되어 boundary matrix에 빈 셀이 존재한다.** CLAUDE.md "The boundary matrix has no empty cells — empty cells are blocking findings regardless of the green bar" 원칙에 따라, 이 두 lock이 추가되기 전까지는 합격이 아니다.

**합격 전환 조건**:
- (필수) 결정 브리프 §9.5 회귀 추가 — candidate confirm/reject 후 gate finding `OPEN` 유지 under/over-strict.
- (필수) 결정 브리프 §9.6 회귀 추가 — candidate items가 있는 inbox에서 `gate_findings` additive 후 기존 `items` envelope 불변 under/over-strict.
- (권장) gate-findings 404 boundary 회귀 추가(없는 project·없는 finding), 및/또는 contract에 404 경계 명시.
- (권장) Mongo adapter index/live 검증 추가로 다른 Mongo 레포 패턴과 정렬.

합격 전환은 회귀 추가 후 본 검증의 Outststanding items #1·#2가 close됨을 독립 확인한 시점으로 한다.

## Outstanding items

1. **[검증 보류 — 회귀 추가 대기]** 결정 브리프 §9.5 candidate action ↔ gate finding 분리 회귀 미추가. 오너 결정 필요: 회귀 추가 승인 여부.
2. **[검증 보류 — 회귀 추가 대기]** 결정 브리프 §9.6 inbox items 불변 회귀 미추가. 오너 결정 필요: 회귀 추가 승인 여부.
3. **[오너 결정 대기]** 404 boundary 회귀 + contract 명시 여부(권장).
4. **[오너 결정 대기]** Mongo adapter live/index 검증 추가 여부(권장).
5. **[커밋 대기]** 변경이 working tree에 uncommitted. 회귀 조건 충족 후 커밋.

## Reproduction

```bash
# 변경 범위
git status; git diff --stat

# focused 게이트 회귀 (14 passed)
python3 -m pytest tests/test_gate_findings.py tests/test_context_search_api.py -q -p no:cacheprovider

# 전체 suite (778 passed / 48 skipped / 99 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider

# fingerprint 결정성·격리·구분성 직접 입증
python3 -c "
from services.application.app.context_search.gate_findings import derive_gate_finding_id
a = derive_gate_finding_id(project_id='p1', idempotency_key='k', ordinal=0, check='stale_item')
b = derive_gate_finding_id(project_id='p1', idempotency_key='k', ordinal=0, check='stale_item')
c = derive_gate_finding_id(project_id='p2', idempotency_key='k', ordinal=0, check='stale_item')
d = derive_gate_finding_id(project_id='p1', idempotency_key='k', ordinal=1, check='stale_item')
e = derive_gate_finding_id(project_id='p1', idempotency_key='other', ordinal=0, check='stale_item')
assert a == b and a != c and a != d and a != e and a.startswith('gf:')
print('fingerprint OK:', a)
"

# §9.5 / §9.6 빈 셀 확인 (재판정 전에는 빈 출력이었음)
grep -rn "candidate.*finding\|finding.*candidate" tests/test_analysis_apply_api.py
grep -n 'items\b' tests/test_context_search_api.py tests/test_analysis_apply_api.py
```

---

## Re-verification (재판정) — 2026-07-12

- **검증자**: Claude(원 판정과 동일, 구현 작업자 아님)
- **트리거**: 오너가 작업 AI의 보강(conditional pass 차단 조건 + 권장 회귀) 후 커밋을 요청. 검증자는 재판정 후 커밋에 포함.
- **대상 보강 범위**: `tests/test_analysis_apply_api.py`(+81줄, `GateFindingInboxIsolationTest` 2종)·`tests/test_context_search_api.py`(`test_gate_finding_routes_return_404_for_missing_scope_or_id`)·`tests/test_gate_findings_mongo.py`(신규 2종). HANDOFF·CHANGELOG·work_log에 보강 및 783 결과 반영.

### 차단 조건 폐쇄 확인

- **BLOCKING-CONDITION #1 (§9.5) → 폐쇄**: `test_candidate_confirm_and_reject_do_not_close_gate_finding`(`tests/test_analysis_apply_api.py`)가 subTest로 confirm/reject 두 action을 각각 수행 후 `gate_service.get(...).status.value == "open"`을 단언. gate finding을 persist한 뒤 candidate transition API를 관통 호출해도 finding이 OPEN으로 유지됨을 잠금.
  - under-strict: candidate_review에 gate_findings 전이 호출이 실수로 추가되면 재실패.
  - over-strict: 정상 분리 케이스(confirm·reject 둘 다 영향 없음)를 subTest로 각각 확인.
- **BLOCKING-CONDITION #2 (§9.6) → 폐쇄**: `test_gate_findings_are_additive_without_changing_candidate_items`가 candidate item이 있는 inbox에서 gate finding 추가 전후를 `before`/`after`로 비교 — `before["items"] == after["items"]`(기존 items 불변) + `before["items"][0]["candidate_id"] == candidate.id`(candidate 실재) + `before["gate_findings"] == []` / `len(after["gate_findings"]) == 1`(additive만 추가). 빈 fixture가 아니라 실제 candidate item이 있는 envelope에서 additive 불변을 잠금.
  - under-strict: additive가 items를 깨면 재실패.
  - over-strict: items 보존 + gate_findings만 1개 추가(과잉 누락 방지).

### 권장 회귀 추가 확인

- **404 boundary**: `test_gate_finding_routes_return_404_for_missing_scope_or_id`가 missing project list · missing finding detail · missing finding resolve 세 경로 404를 잠금. 원 판정의 비대칭(cross-terminal 409는 잠기고 404는 미잠금) 해소.
- **Mongo adapter**: `tests/test_gate_findings_mongo.py`가 compound index literal `[("project_id",1),("status",1)]` + name `gate_findings_by_project_status`(`test_installs_project_status_index_with_stable_name`)와 upsert/get round-trip + open-only scope + `_id` 결정적 정렬(`gf:z`를 먼저 upsert해도 `gf:a` 선행, `test_upsert_get_and_open_listing_round_trip`)을 잠금. **다만 in-memory `_Collection` fake 기반이라 실제 PyMongo BSON 직렬화·tz-aware datetime round-trip·실제 인덱스 동작은 여전히 미검증(비차단 관찰 유지).**

### Suite 재현

- focused(`tests/test_gate_findings.py tests/test_gate_findings_mongo.py tests/test_context_search_api.py tests/test_analysis_apply_api.py::GateFindingInboxIsolationTest`): 작업 AI 보고 43 passed + 2 subtests.
- 전체 `python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider` → **783 passed / 48 skipped / 101 subtests**(12.17s, exit 0). 작업 AI 보고와 정확히 일치. 독립 재실행으로 확인.

### 최종 Verdict — **합격 (Pass)**

두 차단 조건(§9.5 candidate action 분리, §9.6 inbox items additive 불변)이 under/over-strict 양방향 회귀로 폐쇄되었고, 권장 404/Mongo 회귀도 추가되었으며, 전체 suite 783 passed를 독립 재현했다. 원 판정의 조건부 합격 조건이 모두 충족되어 **합격으로 전환**한다.

남은 비차단 관찰(합격을 막지 않음):
- Mongo adapter 회귀가 fake client 기반이라 live BSON/tz round-trip·실제 인덱스 동작은 미검증. 다른 Mongo 레포가 실제 `MongoClient` 기반이면 일관성을 위해 live 단위 테스트 추가 권장(후속).
- 404가 contract prose에 명시되지 않았으나(spec-silent-but-code-enforced), 이제 회귀로 잠겨 boundary는 닫혔다. contract 명시는 선택.

### Reproduction (재판정)

```bash
# 보강 회귀 확인
grep -n "def test_" tests/test_gate_findings_mongo.py
grep -n "GateFindingInboxIsolationTest\|def test_" tests/test_analysis_apply_api.py | tail -5
grep -n "test_gate_finding_routes_return_404" tests/test_context_search_api.py

# 전체 suite (783 passed / 48 skipped / 101 subtests)
python3 -m pytest --ignore=tests/test_memory_mongo.py -q -p no:cacheprovider
```
