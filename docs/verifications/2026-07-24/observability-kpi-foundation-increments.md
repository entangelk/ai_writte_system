# 독립 검증 — 관측 KPI 페이즈 기반 증분 1~3 (per-call 감사 레코드 + 게이트 파생점수)

## Subject metadata

- **날짜**: 2026-07-24
- **요청자**: 오너 ("작업 AI가 작업한거 확인해서 검증하고 의심하고 또 의심해줄래?")
- **검증자**: 독립 검증 AI (Claude Code)
- **대상 slice**: 관측 KPI 첫 slice의 **기반 증분 1~3** — 통합 per-LLM-call 감사 레코드 + in-memory/Mongo repo + service + 게이트 파생점수 `gate_quality_score()`.
- **정본(계약) 참조**: [`docs/plans/observability-kpi-decisions.md`](../../plans/observability-kpi-decisions.md) — 승인 상태 `D1=B · D2=C[파생 먼저] · D3=A · D4=A · D5(계약 의무대로)` (2026-07-24). 추가로 `writing/gate.py` 의 decision 불변(파생점수 정당성의 하중받는 근거) 및 `writing/models.py` 의 `WritingGateDecision` enum.
- **피검증 작업 출처**: working tree, **미커밋**(`git status`: `?? services/application/app/observability/`, `?? tests/test_llm_call_audit*.py`, `M docs/daily_logs/2026-07-24/work_log.md`). HEAD = `9e625d5`.
- **피검증자 주장**(`work_log.md` "Task — 관측 KPI 첫 slice 기반 증분(1~3)"): 증분1 레코드+repo+service+파생점수, 증분2 Mongo 어댑터(fake-collection round-trip), 증분3 스키마 lock 관례 확인; 회귀 16개(10 passed / 5 subtests) green; 신규 모듈 미와이어라 기존 1471 회귀 무영향.

---

## Scope

이 검증은 **기반 증분 1~3**에 한정한다. 증분4(호출부 계츭 와이어링)·증분5(read API + SoT 반영)는 work_log가 **미착수**로 명시하므로 범위 밖.

확인 표면:

1. **계약(brief) 읽기** — D1~D5 승인 내용, 특히 D2(파생점수 방식)와 D5(SoT·schema lock 반영 범위).
2. **레코드·파생점수 구현** — `observability/llm_call_audit.py`.
3. **Mongo 어댑터** — `observability/llm_call_audit_mongo.py`.
4. **정당성의 하중받는 근거** — `gate.py` 의 `decision == max(recommended_decision)` 강제 및 `WritingGateDecision` enum 실제 멤버.
5. **회귀 테스트** — `tests/test_llm_call_audit.py`, `tests/test_llm_call_audit_mongo.py`.
6. **선례 대조** — `writing/loop_audit_mongo.py`·`context_search/gate_findings_mongo.py` 및 그 테스트(index명·round-trip 관례).
7. **무영향 주장** — 신규 모듈의 와이어링 부재, main.py import 무결성, suite 수집.

---

## Methodology

재현에 필요한 모든 명령. 환경: repo root `/mnt/d/devel/에베베/ai_writte_system`, `python3 = 3.12.3`, `pymongo = 4.16.0`(시스템), test-mongo 불필요(Mongo 테스트는 fake collection 사용).

```bash
# 1. 회귀 실구동
PYTHONPATH=. python3 -m pytest tests/test_llm_call_audit.py tests/test_llm_call_audit_mongo.py -v
# → 10 passed, 5 subtests passed

# 2. over-strict / round-trip 가드 mutation (각 변이 → 해당 회귀만 fail 확인, 이후 복원)
A=services/application/app/observability/llm_call_audit.py
M=services/application/app/observability/llm_call_audit_mongo.py
cp "$A" /tmp/A.bak; cp "$M" /tmp/M.bak
sed -i '/WritingGateDecision.BLOCK: 0.0,/d' "$A"   # M1: every_decision_literal fail
sed -i 's/NEEDS_USER_REVIEW: 0.6,/NEEDS_USER_REVIEW: 0.9,/' "$A"   # M2: score_values fail
sed -i -e 's/NEEDS_USER_REVIEW: 0.6,/NEEDS_USER_REVIEW: 0.5,/' -e 's/RETRIEVE_MORE: 0.5,/RETRIEVE_MORE: 0.6,/' "$A"   # M3: ordering fail
sed -i 's/total_tokens=doc.get("total_tokens", 0),/total_tokens=doc.get("latency_ms", 0),/' "$M"   # M4: round-trip fail
sed -i 's/llm_call_audits_by_project_created/llm_call_audits_by_project_desc/' "$M"   # M5: index-name fail
# (각각 실행 후 cp /tmp/*.bak 복원)

# 3. 무영향 / import 무결성
grep -rn "observability.llm_call_audit\|LlmCallAuditService\|MongoLlmCallAuditRepository" services/ frontend/  # → 0 (미와이어)
PYTHONPATH=. python3 -c "import services.application.app.main as m; print(hasattr(m,'create_app'))"  # → True
PYTHONPATH=. python3 -m pytest --co -q 2>&1 | tail -1   # → 1482 tests collected

# 4. SoT 미반영 확인
grep -n "gate_quality_score\|llm_call_audit\|LlmCallSite\|_GATE_DECISION_QUALITY\|파생점수\|판단 정도" docs/system-contract-sot.md   # → 0
```

---

## Findings

### F1. 회귀는 실구동 시 주장대로 green (주장 사실)

`10 passed, 5 subtests passed`. work_log "10 passed / 5 subtests"와 일치.

### F2. 게이트 파생점수의 하중받는 근거는 **사실이다** — `decision == max(recommended_decision)` 강제 확인

`writing/gate.py:129-132`:
```python
expected = max((item.recommended_decision for item in decision_driving),
               key=_PRIORITY.get, default=WritingGateDecision.PASS)
if decision is not expected:
    raise ValueError("decision does not match finding priority")
```
`_PRIORITY`(`gate.py:33-35`): `PASS=0 < REVISE=1 < RETRIEVE_MORE=2 < NEEDS_USER_REVIEW=3 < BLOCK=4`. 즉 `decision` 은 decision-driving finding들의 `recommended_decision` 중 **최우선** 값으로 강제된다. work_log가 "decision이 finding 우선순위를 이미 인코딩"이라 한 것은 코드 직독으로 참.

### F3. `WritingGateDecision` enum 실제 멤버 = 5개, 파생점수 맵이 전수 커버 (over-strict 가드 진짜)

`writing/models.py:55-60`: `PASS, REVISE, RETRIEVE_MORE, NEEDS_USER_REVIEW, BLOCK`. `_GATE_DECISION_QUALITY`(`llm_call_audit.py:69-75`)도 같은 5개 키. `test_every_decision_literal_has_a_score`(`test_llm_call_audit.py:39-45`)가 `set(WritingGateDecision) == set(_GATE_DECISION_QUALITY)` 단정. **mutation M1**(BLOCK 엔트리 제거) → 이 테스트만 fail 확인. 향후 enum에 6번째 멤버 추가 시 이 테스트가 잡는다(과엄격 가드 양방향 성립).

### F4. mutation 5종 — 각각 해당 회귀 하나만 정확히 물었다 (가드 진짜)

| 변이 | 물린 회귀 | 방향 |
|---|---|---|
| M1 `_GATE_DECISION_QUALITY` BLOCK 제거 | `test_every_decision_literal_has_a_score` | over-strict(미래 멤버 강제) |
| M2 `NEEDS_USER_REVIEW 0.6→0.9` | `test_score_values_are_pinned_and_bounded` | 값 고정(under-strict) |
| M3 NUR(0.6)↔RETRIEVE_MORE(0.5) 교환 | `test_score_ordering_reflects_writing_quality` | 순서 고정(under-strict) |
| M4 `_call` total_tokens←latency_ms | `test_add_and_list_round_trip_newest_first` | _doc↔_call drift |
| M5 index 이름 변이 | `test_installs_project_created_index_with_stable_name` | lock 리터럴 |

복원 후 10 green 재확인, 백업과 `diff` 공백(working tree 무결).

### F5. Mongo 어댑터는 선례를 충실히 미러 (memory `mongo-adapter-needs-fake-collection-test` 실수 미반복)

`llm_call_audit_mongo.py` ↔ `writing/loop_audit_mongo.py` 정확 대조:
- index명 패턴 `<collection>_by_<fields>`: `llm_call_audits_by_project_created` vs `writing_loop_audits_by_project_created`(`loop_audit_mongo.py:19`). 동일 패턴.
- index 키 `[("project_id",1),("created_at",-1)]`(`loop_audit_mongo.py:17-18`). 동일.
- list sort `[("created_at",DESC),("_id",DESC)]`. 동일.
- `insert_one` append-only(never replace)·`from_uri` classmethod·`_doc`/`_call` round-trip helper. 동일.
- 테스트 4종도 `test_writing_loop_audit_mongo.py`의 4종과 1:1 대응(index명·field round-trip·append-only·legacy 기본값). `test_writing_loop_audit_mongo.py:96-130` 참조.

과거 `scratch_mongo`가 fake-collection 테스트를 빠뜨려 지적받은 부류의 실수를 이번엔 반복하지 않았다.

### F6. "미와이어, 기존 회귀 무영향" — 구조적으로 참

`grep` 결과 신규 모듈을 import 하는 app/frontend 코드 **0건**(테스트 파일만). 따라서 런타임에 기존 회귀가 신규 코드에 닿을 경로가 물리적으로 없다. 추가로 `main.py` import 정상, `pytest --co` 전체 **1482개 수집 오류 0**(직전 1472 + 신규 10 = 1482 정확히 일치). work_log "기존 1471 회귀 무영향" 주장은 구조적으로 입증됐다. (전체 suite 재실행은 ~10분 소요; 신규 코드가 닿을 경로가 없으므로 생략해도 무방하다 — 재실행은 부가확인일 뿐 결론을 바꾸지 않는다.)

### F7. 레코드 스키마 — brief D1-B 스케치와의 차이는 정당한 일반화

`StoredLlmCall`(`llm_call_audit.py:88-107`) 필드: `id, project_id, call_site, correlation_id, model, outcome, decision, gate_quality_score, total_tokens, latency_ms, error_type, created_at`. brief D1-B 스케치 `{call_site, project_id, request_id/job_id, model, outcome, decision/verdict, token_usage, latency_ms, error_type}` 대비:
- `request_id/job_id` → `correlation_id`: brief Follow-up(#1, line 76)가 "미래 호출부 수용하도록 일반적으로"를 요구한 것과 일치. docstring(`:93-95`)도 근거 명시. 정당.
- `token_usage`(객체 추정) → `total_tokens`(int): `StoredWritingLoopRun` 선례(brief line 17)가 `total_tokens` 를 쓰므로 미러. 정당.
- `gate_quality_score`(D2 산출물)·`id`·`created_at` 추가. 합리.

---

## Issues / Risks

### Blocking (계약 의무)

**없음.** boundary matrix(아래)의 계약 필수 분기는 모두 named 회귀로 추적되며, 빈 칸 없다.

- `call_site` enum 5값(`llm_call_audit.py:43-47`): opaque 문자열로 저장, 값별 동작 분기 없음 → 멤버십 외에 lock할 분기 없음. `query_planner`/`writing_gate`/`writing_generation`은 회귀에 등장; `compare_judge`/`analysis_extractor`는 미등장이나 분기가 없으므로 빈 칸 아님(후술 hardening).
- `outcome` enum 4값(`:53-56`): `success`/`provider_error` 등장; `parse_error`/`budget_exceeded` 미등장이나 동일 이유로 빈 칸 아님.
- 파생점수: 5 decision 전수 매핑(M1)·값 고정(M2)·순서 고정(M3) — 모두 양방향 lock.
- round-trip: field-for-field(M4)·append-only·legacy 기본값 — lock.
- brief ↔ 구현 리터럴 일치(`gate_quality_score`, enum 값). 모순 없음.

### Hardening recommendations (비차단)

**H1 — 파생점수 "double-count" 정당화가 기술적으로 느슨하다 (근거 정정 권장).**
`llm_call_audit.py:13-19`(module docstring)와 `:59-61`(주석)·work_log가 "decision이 finding 우선순위를 인코딩하므로 별도 severity 항은 이중 계산"이라 한다. 이는 절반만 맞다:
- `gate.decision` 은 decision-driving finding들의 **최우선 `recommended_decision` 하나**만 취한다(`gate.py:129`). finding의 **개수/조합** 정보는 버린다. 예: `[REVISE(warning,구조), NEEDS_USER_REVIEW(warning,톤)]` → decision=NEEDS_USER_REVIEW → 점수 0.6. 그런데 구조적 REVISE 결함이 실존함에도 0.6(거의 pass)이 된다. severity/개수를 더하면 **중복이 아니라 손실된 신호를 보충**한다.
- 또한 `gate.py:_PRIORITY`는 **escalation routing 우선순위**(NUR > RETRIEVE_MORE > REVISE)이지, writing 품질 순위가 아니다. 점수가 NUR(0.6) > RETRIEVE_MORE(0.5) > REVISE(0.3) 로 **중간 셋이 역전**된 것은 routing 우선순위와 다른, "결함 발견 여부"语义에 기반한 별개 판단이다(자체로는 정당 — M3로 의도적 lock 확인). 하지만 "double-count 방지"라는 적힌 근거는 이 역전을 설명하지 못한다.
- **권장**: docstring/주석의 근거를 "decision-category 기반의 **거친 근사치**(D2-C 'A 먼저'), 단순성을 위해 finding 개수/severity는 의도적 제외"로 고쳐 쓸 것. 현재 문구대로 두면 후속자가 "severity는 중복이니 넣을 필요 없다"로 오독해, D2-B(명시 점수) 후속 slice에서 정보 손실을 놓친다.

**H2 — 헤드라인 KPI의 구체 점수값/decision-only 범위에 대해 오너 확인이 기록되지 않았다.**
brief D2-A 설명은 "ERROR/WARNING 개수 반영"을 언급하지만, 구현은 **decision-only**(severity 미사용). 이는 D2-C("A 먼저")의 해석으로 정당화되나, brief line 45가 명시적으로 *"A의 파생 점수가 원하는 '판단 정도'를 충분히 담는지 승인 시 확인 바람"* 이라 한 항목이다. work_log(385-405)는 `D2=C` 승인만 기록하고, **구체 값(1.0/0.6/0.5/0.3/0.0)과 decision-only 범위가 오너 의도에 부합하는지의 확인 근거는 없다**. 차단은 아님(D2=C가 파생 방식을 위임)이나, 헤드라인 지표인 만큼 오너에게 구체 값/범위를 한 번 눈으로 확인받을 것을 권장.

**H3 — `call_site`/`outcome` enum의 미사용 멤버 회귀 커버 (선택).**
`compare_judge`·`analysis_extractor`·`parse_error`·`budget_exceeded`가 어떤 회귀에도 등장하지 않는다. opaque 저장이라 분기는 없으나, 한 줄 parametrize로 전 enum round-trip을 잠그면 향후 call_site에 의미 부여 시 회귀가 즉시 보호된다. 필수 아님.

---

## Verdict

**합격 (PASS)** — 기반 증분 1~3에 한하여.

이유(하중받는 근거):
1. 피검증자의 핵심 주장 7개(F1~F7)를 1차 소스에서 **모두 재도출 확인**. 특히 파생점수 정당성의 근간인 `decision == max(recommended_decision)` 강제를 `gate.py:129-132`에서 직확인.
2. 회귀 10개가 주장대로 green이며, mutation 5종(M1~M5)으로 **각 가드가 실제로 결함을 잡음**을 입증 — 거짓 green 아님. 양방향(under/over-strict) 모두 확인.
3. Mongo 어댑터가 선례(`loop_audit_mongo`)를 충실히 미러했고, memory에 기록된 `scratch_mongo` 실수를 반복하지 않았다.
4. "미와이어·무영향"이 구조적으로 입증됐다(import 경로 0건 + 수집 1482 오류 0).
5. brief ↔ 구현 리터럴 일치, 계약 모순 없음. boundary matrix 빈 칸 없음.

차단 사유 없음. H1~H3은 비차단 hardening/확인 후보.

---

## Outstanding items (오너 다음 단계에 영향)

1. **D5 SoT 반영 미완료**(증분5로 이관중). `git status`가 `system-contract-sot.md` 미변경을 확인하며, grep으로 SoT 본문에 `call_site`/`outcome` enum·파생점수 정의의 선행 언급이 **0건**임을 확인. brief D5가 "per-call 레코드 계약(필드·리터럴 enum)·파생점수 정의를 정본에 명시"를 의무화한다. work_log는 이를 증분5 버킷으로 미뤘다. → **증분3만 단독 커밋하면 canonical SoT가 새 리터럴을 아직 반영하지 않은 상태로 커밋**된다. 오너 판단: (a) "foundation, SoT pending 증분5"로 명시 후 지금 커밋, (b) 증분5까지 끝내 SoT 반영이 포함된 상태로 한 번에 커밋.
2. **오너 확인 권장(H2)**: 파생점수 구체 값(1.0/0.6/0.5/0.3/0.0)과 decision-only 범위가 "판단 정도" 의도에 부합하는지. brief line 45가 승인 시 확인을 요청한 항목이나 work_log에 확인 근거 없음.
3. 작업 AI가 묻는 커밋 시점 질문(지금 커밋+증분4 / 증분4·5 한 번에)은 위 (1)(2)와 연결된 오너 방향 결정.

---

## Reproduction

```bash
cd /mnt/d/devel/에베베/ai_writte_system
PYTHONPATH=. python3 -m pytest tests/test_llm_call_audit.py tests/test_llm_call_audit_mongo.py -v
# 기대: 10 passed, 5 subtests passed

# mutation 증명(M1~M5)은 Methodology 절의 스크립트. 각 변이 후 해당 회귀 1개만 fail, 복원 후 10 green.

# 무영향·SoT 미반영 확인
grep -rn "observability.llm_call_audit\|LlmCallAuditService\|MongoLlmCallAuditRepository" services/ frontend/   # → 0
PYTHONPATH=. python3 -m pytest --co -q 2>&1 | tail -1   # → 1482 tests collected
grep -cn "gate_quality_score\|llm_call_audit\|_GATE_DECISION_QUALITY" docs/system-contract-sot.md   # → 0
```
